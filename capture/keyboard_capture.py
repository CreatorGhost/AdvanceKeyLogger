"""
Keyboard capture module using pynput.

Captures key presses into an in-memory buffer. On collect(), returns
the buffered keystrokes as a list of dicts.
"""
from __future__ import annotations

import threading
import time
from typing import Any

from pynput.keyboard import Listener, Key

from capture import register_capture
from capture.base import BaseCapture


@register_capture("keyboard")
class KeyboardCapture(BaseCapture):
    """Capture keyboard input via pynput."""

    def __init__(self, config: dict[str, Any], global_config: dict[str, Any] | None = None):
        super().__init__(config, global_config)
        self._buffer: list[dict[str, Any]] = []
        self._include_key_up = bool(config.get("include_key_up", False))
        self._max_buffer = int(config.get("max_buffer", 10000))
        self._lock = threading.Lock()
        self._listener: Listener | None = None

    def start(self) -> None:
        if self._listener is not None:
            return
        self._listener = Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.daemon = True
        self._listener.start()
        self._running = True
        self.logger.info("Keyboard capture started")

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener.join(timeout=2.0)
            self._listener = None
        self._running = False
        self.logger.info("Keyboard capture stopped")

    def collect(self) -> list[dict[str, Any]]:
        with self._lock:
            if not self._buffer:
                return []
            data = list(self._buffer)
            self._buffer.clear()
        return data

    def _on_press(self, key) -> None:
        self._append(self._format_key(key))

    def _on_release(self, key) -> None:
        if not self._include_key_up:
            return
        self._append(f"{self._format_key(key)}_up")

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
