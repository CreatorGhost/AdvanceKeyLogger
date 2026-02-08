"""
Native macOS keyboard capture backend using CGEventTap.

Uses pyobjc-framework-Quartz for direct access to macOS's Core Graphics
event tap API.  This provides reliable Unicode character extraction via
CGEventKeyboardGetUnicodeString, which is superior to manual keycode
mapping.

Falls back gracefully when pyobjc is not installed (see QUARTZ_AVAILABLE).
"""
from __future__ import annotations

import ctypes
import logging
import threading
from typing import Callable

logger = logging.getLogger(__name__)

QUARTZ_AVAILABLE = False
try:
    from Quartz import (
        CGEventGetIntegerValueField,
        CGEventKeyboardGetUnicodeString,
        CGEventMaskBit,
        CGEventTapCreate,
        CGEventTapEnable,
        kCGEventFlagsChanged,
        kCGEventKeyDown,
        kCGEventKeyUp,
        kCGEventTapOptionListenOnly,
        kCGHeadInsertEventTap,
        kCGKeyboardEventKeycode,
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

# ---------------------------------------------------------------------------
# Keycode map for special / non-printable keys (macOS virtual keycodes).
# Regular printable characters are handled by CGEventKeyboardGetUnicodeString.
# ---------------------------------------------------------------------------
_SPECIAL_KEYCODE_MAP: dict[int, str] = {
    36: "enter",
    48: "tab",
    49: "space",
    51: "backspace",
    53: "escape",
    55: "cmd",
    56: "shift",
    57: "caps_lock",
    58: "alt",
    59: "ctrl",
    60: "shift_r",
    61: "alt_r",
    62: "ctrl_r",
    63: "fn",
    # Arrow keys
    123: "left",
    124: "right",
    125: "down",
    126: "up",
    # Function keys
    122: "f1",
    120: "f2",
    99: "f3",
    118: "f4",
    96: "f5",
    97: "f6",
    98: "f7",
    100: "f8",
    101: "f9",
    109: "f10",
    103: "f11",
    111: "f12",
    # Navigation
    115: "home",
    119: "end",
    116: "page_up",
    121: "page_down",
    117: "delete",
    # Media / special
    114: "insert",
    105: "f13",
    107: "f14",
    113: "f15",
    106: "f16",
    64: "f17",
    79: "f18",
    80: "f19",
    90: "f20",
}


class CGEventTapBackend:
    """Native macOS keyboard capture using CGEventTap."""

    def __init__(
        self,
        on_press_callback: Callable[[str], None],
        on_release_callback: Callable[[str], None],
    ) -> None:
        self._on_press = on_press_callback
        self._on_release = on_release_callback
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

        event_mask = (
            CGEventMaskBit(kCGEventKeyDown)
            | CGEventMaskBit(kCGEventKeyUp)
            | CGEventMaskBit(kCGEventFlagsChanged)
        )

        self._tap = CGEventTapCreate(
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionListenOnly,
            event_mask,
            self._event_callback,
            None,
        )

        if self._tap is None:
            raise RuntimeError(
                "Failed to create CGEventTap. "
                "Ensure the application has Accessibility permissions "
                "(System Settings > Privacy & Security > Accessibility)."
            )

        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="cgeventtap-keyboard"
        )
        self._thread.start()
        logger.info("CGEventTap keyboard backend started")

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
        logger.info("CGEventTap keyboard backend stopped")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        """Thread target: attach the tap to a CFRunLoop and run it."""
        source = CFMachPortCreateRunLoopSource(None, self._tap, 0)
        self._run_loop_ref = CFRunLoopGetCurrent()
        CFRunLoopAddSource(self._run_loop_ref, source, kCFRunLoopCommonModes)
        CGEventTapEnable(self._tap, True)
        CFRunLoopRun()

    def _event_callback(self, proxy, event_type, event, refcon):
        """CGEventTap callback — dispatches press / release."""
        if not self._running:
            return event

        if event_type == kCGEventKeyDown:
            key_str = self._resolve_key(event)
            if key_str:
                self._on_press(key_str)
        elif event_type == kCGEventKeyUp:
            key_str = self._resolve_key(event)
            if key_str:
                self._on_release(key_str)
        # kCGEventFlagsChanged is intentionally ignored for now;
        # modifier-only events are not captured.

        return event

    def _resolve_key(self, event) -> str:
        """Return a human-readable string for the key event."""
        keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)

        # Check special key map first
        special = _SPECIAL_KEYCODE_MAP.get(keycode)
        if special is not None:
            return f"[{special}]"

        # Try to get the Unicode character
        char = self._get_unicode_string(event)
        if char:
            return char

        return f"[keycode:{keycode}]"

    @staticmethod
    def _get_unicode_string(event) -> str:
        """Extract the Unicode character from a key event."""
        max_len = 4
        actual_len = ctypes.c_uint32(0)
        buf = (ctypes.c_uint16 * max_len)()

        CGEventKeyboardGetUnicodeString(
            event, max_len, ctypes.byref(actual_len), buf
        )

        length = actual_len.value
        if length == 0:
            return ""

        return "".join(chr(buf[i]) for i in range(length))

    @staticmethod
    def format_special_key(keycode: int) -> str | None:
        """Public helper: look up a keycode in the special key map.

        Returns the bracketed name (e.g. ``"[enter]"``) or *None*.
        """
        name = _SPECIAL_KEYCODE_MAP.get(keycode)
        return f"[{name}]" if name is not None else None
