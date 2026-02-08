"""Tests for the native macOS NSPasteboard clipboard backend."""
from __future__ import annotations

import sys
import time
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="macOS-only backend",
)


class TestNSPasteboardBackend:
    @pytest.fixture(autouse=True)
    def _skip_if_no_appkit(self):
        from capture.macos_clipboard_backend import APPKIT_AVAILABLE
        if not APPKIT_AVAILABLE:
            pytest.skip("pyobjc AppKit not installed")

    def test_start_stop_lifecycle(self):
        from capture.macos_clipboard_backend import NSPasteboardBackend

        on_change = MagicMock()

        with patch.object(NSPasteboardBackend, "_current_change_count", return_value=1):
            backend = NSPasteboardBackend(on_change, poll_interval=0.05)
            backend.start()
            assert backend._thread is not None
            backend.stop()
            assert backend._thread is None

    def test_double_start_is_noop(self):
        from capture.macos_clipboard_backend import NSPasteboardBackend

        with patch.object(NSPasteboardBackend, "_current_change_count", return_value=1):
            backend = NSPasteboardBackend(MagicMock(), poll_interval=0.05)
            backend.start()
            first_thread = backend._thread
            backend.start()  # should not create a second thread
            assert backend._thread is first_thread
            backend.stop()

    def test_change_triggers_callback(self):
        from capture.macos_clipboard_backend import NSPasteboardBackend

        on_change = MagicMock()
        call_count = [0]

        def mock_change_count():
            call_count[0] += 1
            # First call is from __init__/start, second is from _run loop
            return call_count[0]

        with patch.object(NSPasteboardBackend, "_current_change_count", side_effect=mock_change_count), \
             patch.object(NSPasteboardBackend, "_read_string", return_value="hello clipboard"):
            backend = NSPasteboardBackend(on_change, poll_interval=0.05)
            backend.start()
            time.sleep(0.2)  # allow a few poll cycles
            backend.stop()

        on_change.assert_called_with("hello clipboard")

    def test_no_callback_on_same_value(self):
        from capture.macos_clipboard_backend import NSPasteboardBackend

        on_change = MagicMock()
        cc = [0]

        def mock_cc():
            cc[0] += 1
            return cc[0]

        with patch.object(NSPasteboardBackend, "_current_change_count", side_effect=mock_cc), \
             patch.object(NSPasteboardBackend, "_read_string", return_value="same"):
            backend = NSPasteboardBackend(on_change, poll_interval=0.05)
            backend._last_value = "same"  # already seen this value
            backend.start()
            time.sleep(0.15)
            backend.stop()

        # Should not have been called because value didn't change
        on_change.assert_not_called()

    def test_none_read_string_ignored(self):
        from capture.macos_clipboard_backend import NSPasteboardBackend

        on_change = MagicMock()
        cc = [0]

        def mock_cc():
            cc[0] += 1
            return cc[0]

        with patch.object(NSPasteboardBackend, "_current_change_count", side_effect=mock_cc), \
             patch.object(NSPasteboardBackend, "_read_string", return_value=None):
            backend = NSPasteboardBackend(on_change, poll_interval=0.05)
            backend.start()
            time.sleep(0.15)
            backend.stop()

        on_change.assert_not_called()
