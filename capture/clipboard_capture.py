"""
Clipboard capture module using pyperclip.

Polls clipboard at a configurable interval and records changes.
"""
from __future__ import annotations

import threading
import time
from typing import Any

import pyperclip
from pyperclip import PyperclipException

from capture import register_capture
from capture.base import BaseCapture


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

    def start(self) -> None:
        with self._lifecycle_lock:
            if self._thread is not None:
                return
            self._stop_event.clear()
            thread = threading.Thread(target=self._run, daemon=True)
            self._thread = thread
            self._running = True
            thread.start()

    def stop(self) -> None:
        with self._lifecycle_lock:
            if self._thread is None:
                return
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
