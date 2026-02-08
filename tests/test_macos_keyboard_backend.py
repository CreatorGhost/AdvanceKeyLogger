"""Tests for the native macOS CGEventTap keyboard backend."""
from __future__ import annotations

import sys
import threading
from unittest.mock import MagicMock, patch

import pytest

# Skip entire module on non-macOS platforms
pytestmark = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="macOS-only backend",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_quartz():
    """Return a mock module that provides the Quartz symbols we need."""
    m = MagicMock()
    # Fake constants — just need distinct integer values
    m.kCGSessionEventTap = 1
    m.kCGHeadInsertEventTap = 0
    m.kCGEventTapOptionListenOnly = 1
    m.kCGEventKeyDown = 10
    m.kCGEventKeyUp = 11
    m.kCGEventFlagsChanged = 12
    m.kCGKeyboardEventKeycode = 9
    m.kCFRunLoopCommonModes = "kCFRunLoopCommonModes"
    m.CGEventMaskBit = lambda x: 1 << x
    return m


# ---------------------------------------------------------------------------
# Tests for _SPECIAL_KEYCODE_MAP / format_special_key
# ---------------------------------------------------------------------------


class TestSpecialKeyCodeMap:
    """Verify the keycode-to-name mapping."""

    def test_enter_keycode(self):
        from capture.macos_keyboard_backend import _SPECIAL_KEYCODE_MAP

        assert _SPECIAL_KEYCODE_MAP[36] == "enter"

    def test_space_keycode(self):
        from capture.macos_keyboard_backend import _SPECIAL_KEYCODE_MAP

        assert _SPECIAL_KEYCODE_MAP[49] == "space"

    def test_escape_keycode(self):
        from capture.macos_keyboard_backend import _SPECIAL_KEYCODE_MAP

        assert _SPECIAL_KEYCODE_MAP[53] == "escape"

    def test_arrow_keys(self):
        from capture.macos_keyboard_backend import _SPECIAL_KEYCODE_MAP

        assert _SPECIAL_KEYCODE_MAP[123] == "left"
        assert _SPECIAL_KEYCODE_MAP[124] == "right"
        assert _SPECIAL_KEYCODE_MAP[125] == "down"
        assert _SPECIAL_KEYCODE_MAP[126] == "up"

    def test_modifier_keys(self):
        from capture.macos_keyboard_backend import _SPECIAL_KEYCODE_MAP

        assert _SPECIAL_KEYCODE_MAP[55] == "cmd"
        assert _SPECIAL_KEYCODE_MAP[56] == "shift"
        assert _SPECIAL_KEYCODE_MAP[58] == "alt"
        assert _SPECIAL_KEYCODE_MAP[59] == "ctrl"

    def test_function_keys(self):
        from capture.macos_keyboard_backend import _SPECIAL_KEYCODE_MAP

        assert _SPECIAL_KEYCODE_MAP[122] == "f1"
        assert _SPECIAL_KEYCODE_MAP[120] == "f2"
        assert _SPECIAL_KEYCODE_MAP[111] == "f12"

    def test_navigation_keys(self):
        from capture.macos_keyboard_backend import _SPECIAL_KEYCODE_MAP

        assert _SPECIAL_KEYCODE_MAP[115] == "home"
        assert _SPECIAL_KEYCODE_MAP[119] == "end"
        assert _SPECIAL_KEYCODE_MAP[116] == "page_up"
        assert _SPECIAL_KEYCODE_MAP[121] == "page_down"
        assert _SPECIAL_KEYCODE_MAP[117] == "delete"


class TestFormatSpecialKey:
    """Verify the public helper."""

    def test_known_key(self):
        from capture.macos_keyboard_backend import CGEventTapBackend

        assert CGEventTapBackend.format_special_key(36) == "[enter]"

    def test_unknown_key(self):
        from capture.macos_keyboard_backend import CGEventTapBackend

        assert CGEventTapBackend.format_special_key(999) is None


# ---------------------------------------------------------------------------
# Tests for backend lifecycle (mocked Quartz)
# ---------------------------------------------------------------------------


class TestCGEventTapBackendLifecycle:
    """Start/stop with mocked Quartz calls."""

    @pytest.fixture(autouse=True)
    def _skip_if_no_quartz(self):
        from capture.macos_keyboard_backend import QUARTZ_AVAILABLE

        if not QUARTZ_AVAILABLE:
            pytest.skip("pyobjc-framework-Quartz not installed")

    def test_start_creates_tap_and_thread(self):
        from capture.macos_keyboard_backend import CGEventTapBackend

        on_press = MagicMock()
        on_release = MagicMock()

        with patch("capture.macos_keyboard_backend.CGEventTapCreate") as mock_create, \
             patch("capture.macos_keyboard_backend.CFMachPortCreateRunLoopSource") as mock_src, \
             patch("capture.macos_keyboard_backend.CFRunLoopGetCurrent") as mock_rl, \
             patch("capture.macos_keyboard_backend.CFRunLoopAddSource"), \
             patch("capture.macos_keyboard_backend.CGEventTapEnable"), \
             patch("capture.macos_keyboard_backend.CFRunLoopRun"), \
             patch("capture.macos_keyboard_backend.CFRunLoopStop"):

            mock_create.return_value = MagicMock()  # non-None tap
            mock_src.return_value = MagicMock()
            mock_rl.return_value = MagicMock()

            backend = CGEventTapBackend(on_press, on_release)
            backend.start()

            assert backend._running is True
            assert backend._thread is not None

            backend.stop()
            assert backend._running is False

    def test_start_raises_on_tap_failure(self):
        from capture.macos_keyboard_backend import CGEventTapBackend

        with patch("capture.macos_keyboard_backend.CGEventTapCreate", return_value=None):
            backend = CGEventTapBackend(MagicMock(), MagicMock())
            with pytest.raises(RuntimeError, match="Failed to create CGEventTap"):
                backend.start()

    def test_double_start_is_noop(self):
        from capture.macos_keyboard_backend import CGEventTapBackend

        with patch("capture.macos_keyboard_backend.CGEventTapCreate") as mock_create, \
             patch("capture.macos_keyboard_backend.CFMachPortCreateRunLoopSource") as mock_src, \
             patch("capture.macos_keyboard_backend.CFRunLoopGetCurrent") as mock_rl, \
             patch("capture.macos_keyboard_backend.CFRunLoopAddSource"), \
             patch("capture.macos_keyboard_backend.CGEventTapEnable"), \
             patch("capture.macos_keyboard_backend.CFRunLoopRun"), \
             patch("capture.macos_keyboard_backend.CFRunLoopStop"):

            mock_create.return_value = MagicMock()
            mock_src.return_value = MagicMock()
            mock_rl.return_value = MagicMock()

            backend = CGEventTapBackend(MagicMock(), MagicMock())
            backend.start()
            backend.start()  # should not raise

            assert mock_create.call_count == 1
            backend.stop()


# ---------------------------------------------------------------------------
# Tests for callback dispatch
# ---------------------------------------------------------------------------


class TestCallbackDispatch:
    """Verify that the event callback invokes the right user callback."""

    @pytest.fixture(autouse=True)
    def _skip_if_no_quartz(self):
        from capture.macos_keyboard_backend import QUARTZ_AVAILABLE

        if not QUARTZ_AVAILABLE:
            pytest.skip("pyobjc-framework-Quartz not installed")

    def test_keydown_calls_on_press(self):
        from capture.macos_keyboard_backend import CGEventTapBackend, kCGEventKeyDown

        on_press = MagicMock()
        on_release = MagicMock()
        backend = CGEventTapBackend(on_press, on_release)
        backend._running = True

        mock_event = MagicMock()
        with patch.object(backend, "_resolve_key", return_value="a"):
            backend._event_callback(None, kCGEventKeyDown, mock_event, None)

        on_press.assert_called_once_with("a")
        on_release.assert_not_called()

    def test_keyup_calls_on_release(self):
        from capture.macos_keyboard_backend import CGEventTapBackend, kCGEventKeyUp

        on_press = MagicMock()
        on_release = MagicMock()
        backend = CGEventTapBackend(on_press, on_release)
        backend._running = True

        mock_event = MagicMock()
        with patch.object(backend, "_resolve_key", return_value="b"):
            backend._event_callback(None, kCGEventKeyUp, mock_event, None)

        on_release.assert_called_once_with("b")
        on_press.assert_not_called()

    def test_callback_ignored_when_not_running(self):
        from capture.macos_keyboard_backend import CGEventTapBackend, kCGEventKeyDown

        on_press = MagicMock()
        backend = CGEventTapBackend(on_press, MagicMock())
        backend._running = False

        backend._event_callback(None, kCGEventKeyDown, MagicMock(), None)
        on_press.assert_not_called()


# ---------------------------------------------------------------------------
# Tests for _resolve_key
# ---------------------------------------------------------------------------


class TestResolveKey:
    """Verify key resolution logic."""

    @pytest.fixture(autouse=True)
    def _skip_if_no_quartz(self):
        from capture.macos_keyboard_backend import QUARTZ_AVAILABLE

        if not QUARTZ_AVAILABLE:
            pytest.skip("pyobjc-framework-Quartz not installed")

    def test_special_key_returns_bracketed_name(self):
        from capture.macos_keyboard_backend import CGEventTapBackend

        backend = CGEventTapBackend(MagicMock(), MagicMock())
        mock_event = MagicMock()

        # keycode 36 = enter
        with patch("capture.macos_keyboard_backend.CGEventGetIntegerValueField", return_value=36):
            result = backend._resolve_key(mock_event)
        assert result == "[enter]"

    def test_unicode_char_returned(self):
        from capture.macos_keyboard_backend import CGEventTapBackend

        backend = CGEventTapBackend(MagicMock(), MagicMock())
        mock_event = MagicMock()

        # keycode 0 (not in special map), unicode returns "a"
        with patch("capture.macos_keyboard_backend.CGEventGetIntegerValueField", return_value=0), \
             patch.object(backend, "_get_unicode_string", return_value="a"):
            result = backend._resolve_key(mock_event)
        assert result == "a"

    def test_fallback_to_keycode_string(self):
        from capture.macos_keyboard_backend import CGEventTapBackend

        backend = CGEventTapBackend(MagicMock(), MagicMock())
        mock_event = MagicMock()

        # keycode 200 (not in map), unicode returns ""
        with patch("capture.macos_keyboard_backend.CGEventGetIntegerValueField", return_value=200), \
             patch.object(backend, "_get_unicode_string", return_value=""):
            result = backend._resolve_key(mock_event)
        assert result == "[keycode:200]"
