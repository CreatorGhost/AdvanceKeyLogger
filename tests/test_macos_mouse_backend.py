"""Tests for the native macOS CGEventTap mouse backend."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="macOS-only backend",
)


class TestButtonNames:
    def test_standard_buttons(self):
        from capture.macos_mouse_backend import _BUTTON_NAMES

        assert _BUTTON_NAMES[0] == "left"
        assert _BUTTON_NAMES[1] == "right"
        assert _BUTTON_NAMES[2] == "middle"


class TestCGEventTapMouseBackendLifecycle:
    @pytest.fixture(autouse=True)
    def _skip_if_no_quartz(self):
        from capture.macos_mouse_backend import QUARTZ_AVAILABLE
        if not QUARTZ_AVAILABLE:
            pytest.skip("pyobjc-framework-Quartz not installed")

    def test_start_creates_tap_and_thread(self):
        from capture.macos_mouse_backend import CGEventTapMouseBackend

        with patch("capture.macos_mouse_backend.CGEventTapCreate") as mock_create, \
             patch("capture.macos_mouse_backend.CFMachPortCreateRunLoopSource") as mock_src, \
             patch("capture.macos_mouse_backend.CFRunLoopGetCurrent") as mock_rl, \
             patch("capture.macos_mouse_backend.CFRunLoopAddSource"), \
             patch("capture.macos_mouse_backend.CGEventTapEnable"), \
             patch("capture.macos_mouse_backend.CFRunLoopRun"), \
             patch("capture.macos_mouse_backend.CFRunLoopStop"):

            mock_create.return_value = MagicMock()
            mock_src.return_value = MagicMock()
            mock_rl.return_value = MagicMock()

            backend = CGEventTapMouseBackend(MagicMock(), MagicMock())
            backend.start()
            assert backend._running is True
            backend.stop()
            assert backend._running is False

    def test_start_raises_on_tap_failure(self):
        from capture.macos_mouse_backend import CGEventTapMouseBackend

        with patch("capture.macos_mouse_backend.CGEventTapCreate", return_value=None):
            backend = CGEventTapMouseBackend(MagicMock(), MagicMock())
            with pytest.raises(RuntimeError, match="Failed to create CGEventTap"):
                backend.start()

    def test_double_start_is_noop(self):
        from capture.macos_mouse_backend import CGEventTapMouseBackend

        with patch("capture.macos_mouse_backend.CGEventTapCreate") as mock_create, \
             patch("capture.macos_mouse_backend.CFMachPortCreateRunLoopSource") as mock_src, \
             patch("capture.macos_mouse_backend.CFRunLoopGetCurrent") as mock_rl, \
             patch("capture.macos_mouse_backend.CFRunLoopAddSource"), \
             patch("capture.macos_mouse_backend.CGEventTapEnable"), \
             patch("capture.macos_mouse_backend.CFRunLoopRun"), \
             patch("capture.macos_mouse_backend.CFRunLoopStop"):

            mock_create.return_value = MagicMock()
            mock_src.return_value = MagicMock()
            mock_rl.return_value = MagicMock()

            backend = CGEventTapMouseBackend(MagicMock(), MagicMock())
            backend.start()
            backend.start()
            assert mock_create.call_count == 1
            backend.stop()


class TestMouseCallbackDispatch:
    @pytest.fixture(autouse=True)
    def _skip_if_no_quartz(self):
        from capture.macos_mouse_backend import QUARTZ_AVAILABLE
        if not QUARTZ_AVAILABLE:
            pytest.skip("pyobjc-framework-Quartz not installed")

    def test_click_down_dispatches(self):
        from capture.macos_mouse_backend import (
            CGEventTapMouseBackend,
            kCGEventLeftMouseDown,
            kCGMouseEventButtonNumber,
        )

        on_click = MagicMock()
        backend = CGEventTapMouseBackend(on_click, None)
        backend._running = True

        mock_event = MagicMock()
        mock_loc = MagicMock()
        mock_loc.x = 100.0
        mock_loc.y = 200.0

        with patch("capture.macos_mouse_backend.CGEventGetLocation", return_value=mock_loc), \
             patch("capture.macos_mouse_backend.CGEventGetIntegerValueField", return_value=0):
            backend._event_callback(None, kCGEventLeftMouseDown, mock_event, None)

        on_click.assert_called_once_with(100, 200, "left", True)

    def test_click_up_dispatches(self):
        from capture.macos_mouse_backend import (
            CGEventTapMouseBackend,
            kCGEventLeftMouseUp,
        )

        on_click = MagicMock()
        backend = CGEventTapMouseBackend(on_click, None)
        backend._running = True

        mock_loc = MagicMock()
        mock_loc.x = 50.0
        mock_loc.y = 60.0

        with patch("capture.macos_mouse_backend.CGEventGetLocation", return_value=mock_loc), \
             patch("capture.macos_mouse_backend.CGEventGetIntegerValueField", return_value=0):
            backend._event_callback(None, kCGEventLeftMouseUp, MagicMock(), None)

        on_click.assert_called_once_with(50, 60, "left", False)

    def test_move_dispatches_with_throttle(self):
        from capture.macos_mouse_backend import CGEventTapMouseBackend, kCGEventMouseMoved

        on_move = MagicMock()
        backend = CGEventTapMouseBackend(MagicMock(), on_move, move_throttle_interval=0.0)
        backend._running = True

        mock_loc = MagicMock()
        mock_loc.x = 300.0
        mock_loc.y = 400.0

        with patch("capture.macos_mouse_backend.CGEventGetLocation", return_value=mock_loc):
            backend._event_callback(None, kCGEventMouseMoved, MagicMock(), None)

        on_move.assert_called_once_with(300, 400)

    def test_callback_ignored_when_not_running(self):
        from capture.macos_mouse_backend import CGEventTapMouseBackend, kCGEventLeftMouseDown

        on_click = MagicMock()
        backend = CGEventTapMouseBackend(on_click, None)
        backend._running = False

        backend._event_callback(None, kCGEventLeftMouseDown, MagicMock(), None)
        on_click.assert_not_called()
