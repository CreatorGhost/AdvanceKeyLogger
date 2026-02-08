"""
Mouse capture module using pynput.

Captures mouse click (and optional move) events into an in-memory buffer.
"""
from __future__ import annotations

import threading
import time
from typing import Any

from pynput.mouse import Listener

from capture import register_capture
from capture.base import BaseCapture


@register_capture("mouse")
class MouseCapture(BaseCapture):
    """Capture mouse events via pynput."""

    def __init__(self, config: dict[str, Any], global_config: dict[str, Any] | None = None):
        super().__init__(config, global_config)
        self._events: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._listener: Listener | None = None
        self._track_movement = bool(config.get("track_movement", False))
        self._click_callback = None

    def start(self) -> None:
        if self._listener is not None:
            return

        self._listener = Listener(
            on_move=self._on_move if self._track_movement else None,
            on_click=self._on_click,
        )
        self._listener.daemon = True
        self._listener.start()
        self._running = True
        self.logger.info("Mouse capture started")

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener.join(timeout=2.0)
            self._listener = None
        self._running = False
        self.logger.info("Mouse capture stopped")

    def collect(self) -> list[dict[str, Any]]:
        with self._lock:
            if not self._events:
                return []
            events = list(self._events)
            self._events.clear()
        return events

    def set_click_callback(self, callback) -> None:
        """Set a callback to run on mouse click (used for screenshot capture)."""
        self._click_callback = callback

    def _record(self, event: dict[str, Any]) -> None:
        with self._lock:
            self._events.append(event)

    def _on_move(self, x: int, y: int) -> None:
        self._record(
            {
                "type": "mouse_move",
                "data": {"x": x, "y": y},
                "timestamp": time.time(),
            }
        )

    def _on_click(self, x: int, y: int, button, pressed: bool) -> None:
        self._record(
            {
                "type": "mouse_click",
                "data": {
                    "x": x,
                    "y": y,
                    "button": getattr(button, "name", str(button)),
                    "pressed": pressed,
                },
                "timestamp": time.time(),
            }
        )
        if pressed and self._click_callback:
            try:
                self._click_callback()
            except Exception:
                self.logger.exception("Mouse click callback failed")
