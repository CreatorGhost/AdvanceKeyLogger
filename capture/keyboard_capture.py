"""
Keyboard capture module.

Captures key presses into an in-memory buffer. On collect(), returns
the buffered keystrokes as a list of dicts.

Backend selection:
  - macOS with pyobjc-framework-Quartz → native CGEventTap backend
  - All other platforms / missing pyobjc  → pynput backend (default)
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

from pynput.keyboard import Key, Listener

from capture import register_capture
from capture.base import BaseCapture
from biometrics.collector import BiometricsCollector
from utils.system_info import get_platform

_logger = logging.getLogger(__name__)

_USE_NATIVE_MACOS = False
if get_platform() == "darwin":
    try:
        from capture.macos_keyboard_backend import CGEventTapBackend, QUARTZ_AVAILABLE

        if QUARTZ_AVAILABLE:
            _USE_NATIVE_MACOS = True
            _logger.debug("Native macOS CGEventTap backend available")
    except ImportError:
        pass


@register_capture("keyboard")
class KeyboardCapture(BaseCapture):
    """Capture keyboard input via pynput."""

    def __init__(self, config: dict[str, Any], global_config: dict[str, Any] | None = None):
        super().__init__(config, global_config)
        self._buffer: list[dict[str, Any]] = []
        self._include_key_up = bool(config.get("include_key_up", False))
        self._max_buffer = int(config.get("max_buffer", 10000))
        global_enabled = bool(
            (global_config or {}).get("biometrics", {}).get("enabled", False)
        )
        self._biometrics_enabled = bool(config.get("biometrics_enabled", False)) and global_enabled
        self._biometrics = (
            BiometricsCollector(max_buffer=self._max_buffer)
            if self._biometrics_enabled
            else None
        )
        self._lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()
        self._listener: Listener | None = None
        self._native_backend: CGEventTapBackend | None = None  # noqa: F821
        self._use_native = _USE_NATIVE_MACOS

    def start(self) -> None:
        with self._lifecycle_lock:
            if self._running:
                return
            if self._use_native:
                self._native_backend = CGEventTapBackend(
                    on_press_callback=self._on_native_press,
                    on_release_callback=self._on_native_release,
                )
                self._native_backend.start()
                self._running = True
                self.logger.info("Keyboard capture started (native macOS backend)")
            else:
                if self._listener is not None:
                    return
                self._listener = Listener(
                    on_press=self._on_press,
                    on_release=self._on_release,
                )
                self._listener.daemon = True
                self._listener.start()
                self._running = True
                self.logger.info("Keyboard capture started (pynput backend)")

    def stop(self) -> None:
        with self._lifecycle_lock:
            if self._native_backend is not None:
                self._native_backend.stop()
                self._native_backend = None
            if self._listener is not None:
                self._listener.stop()
                self._listener.join(timeout=2.0)
                self._listener = None
            self._running = False
            self.logger.info("Keyboard capture stopped")

    def collect(self) -> list[dict[str, Any]]:
        with self._lock:
            if not self._buffer:
                data = []
            else:
                data = list(self._buffer)
            self._buffer.clear()
        if self._biometrics:
            data.extend(self._biometrics.collect())
        return data

    # -- pynput callbacks (receive pynput Key objects) --

    def _on_press(self, key) -> None:
        text = self._format_key(key)
        self._append(text)
        if self._biometrics:
            self._biometrics.on_key_down(text)

    def _on_release(self, key) -> None:
        text = self._format_key(key)
        if self._biometrics:
            self._biometrics.on_key_up(text)
        if not self._include_key_up:
            return
        self._append(f"{text}_up")

    # -- native macOS callbacks (receive pre-formatted strings) --

    def _on_native_press(self, key_str: str) -> None:
        self._append(key_str)
        if self._biometrics:
            self._biometrics.on_key_down(key_str)

    def _on_native_release(self, key_str: str) -> None:
        if self._biometrics:
            self._biometrics.on_key_up(key_str)
        if not self._include_key_up:
            return
        self._append(f"{key_str}_up")

    def _append(self, text: str) -> None:
        if not text:
            return
        with self._lock:
            self._buffer.append(
                {
                    "type": "keystroke",
                    "data": text,
                    "timestamp": time.time(),
                }
            )
            if self._max_buffer > 0 and len(self._buffer) > self._max_buffer:
                self._buffer.pop(0)

    @staticmethod
    def _format_key(key) -> str:
        try:
            if key == Key.space:
                return " "
            if key == Key.enter:
                return "\n"
            if key == Key.tab:
                return "\t"
            if hasattr(key, "char") and key.char is not None:
                return key.char
            return f"[{key.name}]"
        except AttributeError:
            return "[unknown]"
