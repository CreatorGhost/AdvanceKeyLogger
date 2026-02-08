"""
Clipboard capture module.

Polls clipboard at a configurable interval and records changes.

Backend selection:
  - macOS with pyobjc (AppKit) → native NSPasteboard backend
    (no subprocess overhead, uses changeCount for efficient detection)
  - All other platforms / missing pyobjc → pyperclip backend (default)
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

import pyperclip
from pyperclip import PyperclipException

from capture import register_capture
from capture.base import BaseCapture
from utils.system_info import get_platform

_logger = logging.getLogger(__name__)

_USE_NATIVE_MACOS = False
if get_platform() == "darwin":
    try:
        from capture.macos_clipboard_backend import NSPasteboardBackend, APPKIT_AVAILABLE

        if APPKIT_AVAILABLE:
            _USE_NATIVE_MACOS = True
            _logger.debug("Native macOS NSPasteboard clipboard backend available")
    except ImportError:
        pass


@register_capture("clipboard")
class ClipboardCapture(BaseCapture):
    """Capture clipboard text changes."""

    def __init__(self, config: dict[str, Any], global_config: dict[str, Any] | None = None):
        super().__init__(config, global_config)
        self._poll_interval = float(config.get("poll_interval", 5))
        self._max_length = int(config.get("max_length", 10_000))
        self._last_value: str | None = None
        self._buffer: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._use_native = _USE_NATIVE_MACOS
        self._native_backend: NSPasteboardBackend | None = None  # noqa: F821

    def start(self) -> None:
        with self._lifecycle_lock:
            if self._use_native:
                if self._native_backend is not None:
                    return
                self._native_backend = NSPasteboardBackend(
                    on_change_callback=self._on_native_change,
                    poll_interval=self._poll_interval,
                )
                self._native_backend.start()
                self._running = True
                self.logger.info("Clipboard capture started (native macOS backend)")
            else:
                if self._thread is not None:
                    return
                self._stop_event.clear()
                thread = threading.Thread(target=self._run, daemon=True)
                self._thread = thread
                self._running = True
                thread.start()
                self.logger.info("Clipboard capture started (pyperclip backend)")

    def stop(self) -> None:
        with self._lifecycle_lock:
            if self._native_backend is not None:
                self._native_backend.stop()
                self._native_backend = None
            if self._thread is not None:
                thread = self._thread
                self._thread = None
                self._stop_event.set()
                thread.join(timeout=2.0)
        self._running = False

    def collect(self) -> list[dict[str, Any]]:
        with self._lock:
            if not self._buffer:
                return []
            items = list(self._buffer)
            self._buffer.clear()
        return items

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                value = pyperclip.paste()
            except PyperclipException as exc:
                self.logger.warning("Clipboard read failed: %s", exc)
                value = None
            except Exception as exc:
                self.logger.warning("Clipboard read failed: %s", exc)
                value = None

            if value and value != self._last_value:
                self._last_value = value
                if len(value) > self._max_length:
                    value = value[: self._max_length] + "...[truncated]"
                with self._lock:
                    self._buffer.append(
                        {"type": "clipboard", "data": value, "timestamp": time.time()}
                    )

            self._stop_event.wait(self._poll_interval)

    # -- native macOS callback --

    def _on_native_change(self, value: str) -> None:
        """Called by NSPasteboardBackend when clipboard text changes."""
        if len(value) > self._max_length:
            value = value[: self._max_length] + "...[truncated]"
        with self._lock:
            self._buffer.append(
                {"type": "clipboard", "data": value, "timestamp": time.time()}
            )
