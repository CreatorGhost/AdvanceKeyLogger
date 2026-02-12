"""
Mouse capture module.

Captures mouse click (and optional move) events into an in-memory buffer.

Backend selection:
  - macOS with pyobjc-framework-Quartz → native CGEventTap backend
  - All other platforms / missing pyobjc  → pynput backend (default)
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

from pynput.mouse import Listener

from capture import register_capture
from capture.base import BaseCapture
from utils.system_info import get_platform

_logger = logging.getLogger(__name__)

_USE_NATIVE_MACOS = False
if get_platform() == "darwin":
    try:
        from capture.macos_mouse_backend import CGEventTapMouseBackend, QUARTZ_AVAILABLE

        if QUARTZ_AVAILABLE:
            _USE_NATIVE_MACOS = True
            _logger.debug("Native macOS CGEventTap mouse backend available")
    except ImportError:
        pass


@register_capture("mouse")
class MouseCapture(BaseCapture):
    """Capture mouse events via pynput."""

    def __init__(self, config: dict[str, Any], global_config: dict[str, Any] | None = None):
        super().__init__(config, global_config)
        self._events: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._listener: Listener | None = None
        self._track_movement = bool(config.get("track_movement", False))
        self._move_throttle_interval = float(config.get("move_throttle_interval", 0.02))
        self._last_move_ts: float = 0.0
        self._move_ts_lock = threading.Lock()
        self._click_callback = None
        self._lifecycle_lock = threading.Lock()
        self._native_backend: CGEventTapMouseBackend | None = None  # noqa: F821
        self._use_native = _USE_NATIVE_MACOS

    def start(self) -> None:
        with self._lifecycle_lock:
            if self._running:
                return

            if self._use_native:
                self._native_backend = CGEventTapMouseBackend(
                    on_click_callback=self._on_native_click,
                    on_move_callback=self._on_native_move if self._track_movement else None,
                    move_throttle_interval=self._move_throttle_interval,
                )
                self._native_backend.start()
                self._running = True
                self.logger.info("Mouse capture started (native macOS backend)")
            else:
                if self._listener is not None:
                    return
                self._listener = Listener(
                    on_move=self._on_move if self._track_movement else None,
                    on_click=self._on_click,
                )
                self._listener.daemon = True
                self._listener.start()
                self._running = True
                self.logger.info("Mouse capture started (pynput backend)")

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
        now = time.time()
        with self._move_ts_lock:
            if now - self._last_move_ts < self._move_throttle_interval:
                return
            self._last_move_ts = now
        self._record(
            {
                "type": "mouse_move",
                "data": {"x": x, "y": y},
                "timestamp": now,
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

    # -- native macOS callbacks (receive pre-formatted values) --

    def _on_native_click(self, x: int, y: int, button: str, pressed: bool) -> None:
        self._record(
            {
                "type": "mouse_click",
                "data": {
                    "x": x,
                    "y": y,
                    "button": button,
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

    def _on_native_move(self, x: int, y: int) -> None:
        self._on_move(x, y)
