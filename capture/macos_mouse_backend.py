"""
Native macOS mouse capture backend using CGEventTap.

Uses pyobjc-framework-Quartz for direct access to macOS Core Graphics
event tap API for mouse click and movement events.

Falls back gracefully when pyobjc is not installed (see QUARTZ_AVAILABLE).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable

logger = logging.getLogger(__name__)

QUARTZ_AVAILABLE = False
try:
    from Quartz import (
        CGEventGetIntegerValueField,
        CGEventGetLocation,
        CGEventMaskBit,
        CGEventTapCreate,
        CGEventTapEnable,
        kCGEventLeftMouseDown,
        kCGEventLeftMouseUp,
        kCGEventMouseMoved,
        kCGEventOtherMouseDown,
        kCGEventOtherMouseUp,
        kCGEventRightMouseDown,
        kCGEventRightMouseUp,
        kCGEventTapOptionListenOnly,
        kCGHeadInsertEventTap,
        kCGMouseEventButtonNumber,
        kCGSessionEventTap,
    )
    from Quartz import (
        CFMachPortCreateRunLoopSource,
        CFRunLoopAddSource,
        CFRunLoopGetCurrent,
        CFRunLoopRun,
        CFRunLoopStop,
        kCFRunLoopCommonModes,
    )

    QUARTZ_AVAILABLE = True
except ImportError:
    pass

# Map CGEvent button numbers to human-readable names.
_BUTTON_NAMES: dict[int, str] = {
    0: "left",
    1: "right",
    2: "middle",
}

# Events that represent a mouse-down.
_MOUSE_DOWN_EVENTS: set[int] = set()
_MOUSE_UP_EVENTS: set[int] = set()
if QUARTZ_AVAILABLE:
    _MOUSE_DOWN_EVENTS = {kCGEventLeftMouseDown, kCGEventRightMouseDown, kCGEventOtherMouseDown}
    _MOUSE_UP_EVENTS = {kCGEventLeftMouseUp, kCGEventRightMouseUp, kCGEventOtherMouseUp}


class CGEventTapMouseBackend:
    """Native macOS mouse capture using CGEventTap."""

    def __init__(
        self,
        on_click_callback: Callable[[int, int, str, bool], None],
        on_move_callback: Callable[[int, int], None] | None = None,
        move_throttle_interval: float = 0.02,
    ) -> None:
        self._on_click = on_click_callback
        self._on_move = on_move_callback
        self._move_throttle = move_throttle_interval
        self._last_move_ts: float = 0.0
        self._thread: threading.Thread | None = None
        self._run_loop_ref = None
        self._tap = None
        self._running = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Create the event tap and start processing on a daemon thread."""
        if self._running:
            return

        mask = (
            CGEventMaskBit(kCGEventLeftMouseDown)
            | CGEventMaskBit(kCGEventLeftMouseUp)
            | CGEventMaskBit(kCGEventRightMouseDown)
            | CGEventMaskBit(kCGEventRightMouseUp)
            | CGEventMaskBit(kCGEventOtherMouseDown)
            | CGEventMaskBit(kCGEventOtherMouseUp)
        )
        if self._on_move is not None:
            mask |= CGEventMaskBit(kCGEventMouseMoved)

        self._tap = CGEventTapCreate(
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionListenOnly,
            mask,
            self._event_callback,
            None,
        )

        if self._tap is None:
            raise RuntimeError(
                "Failed to create CGEventTap for mouse. "
                "Ensure the application has Accessibility permissions."
            )

        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="cgeventtap-mouse"
        )
        self._thread.start()
        logger.info("CGEventTap mouse backend started")

    def stop(self) -> None:
        """Stop the run loop and clean up."""
        self._running = False
        if self._tap is not None:
            CGEventTapEnable(self._tap, False)
        if self._run_loop_ref is not None:
            CFRunLoopStop(self._run_loop_ref)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._tap = None
        self._run_loop_ref = None
        logger.info("CGEventTap mouse backend stopped")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        source = CFMachPortCreateRunLoopSource(None, self._tap, 0)
        self._run_loop_ref = CFRunLoopGetCurrent()
        CFRunLoopAddSource(self._run_loop_ref, source, kCFRunLoopCommonModes)
        CGEventTapEnable(self._tap, True)
        CFRunLoopRun()

    def _event_callback(self, proxy, event_type, event, refcon):
        if not self._running:
            return event

        loc = CGEventGetLocation(event)
        x, y = int(loc.x), int(loc.y)

        if event_type in _MOUSE_DOWN_EVENTS or event_type in _MOUSE_UP_EVENTS:
            pressed = event_type in _MOUSE_DOWN_EVENTS
            btn_num = CGEventGetIntegerValueField(event, kCGMouseEventButtonNumber)
            btn_name = _BUTTON_NAMES.get(btn_num, f"button{btn_num}")
            self._on_click(x, y, btn_name, pressed)

        elif event_type == kCGEventMouseMoved and self._on_move is not None:
            now = time.time()
            if now - self._last_move_ts >= self._move_throttle:
                self._last_move_ts = now
                self._on_move(x, y)

        return event
