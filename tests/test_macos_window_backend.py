"""Tests for the native macOS window title backend."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="macOS-only backend",
)


class TestGetActiveWindowTitleNative:
    @pytest.fixture(autouse=True)
    def _skip_if_no_appkit(self):
        from capture.macos_window_backend import APPKIT_AVAILABLE
        if not APPKIT_AVAILABLE:
            pytest.skip("pyobjc AppKit not installed")

    def test_returns_app_with_window_title(self):
        from capture.macos_window_backend import get_active_window_title_native

        with patch("capture.macos_window_backend._get_frontmost_app_name", return_value="Safari"), \
             patch("capture.macos_window_backend._get_window_title_for_app", return_value="Safari — Google"):
            assert get_active_window_title_native() == "Safari — Google"

    def test_falls_back_to_app_name(self):
        from capture.macos_window_backend import get_active_window_title_native

        with patch("capture.macos_window_backend._get_frontmost_app_name", return_value="Finder"), \
             patch("capture.macos_window_backend._get_window_title_for_app", return_value=None):
            assert get_active_window_title_native() == "Finder"

    def test_returns_unknown_when_no_app(self):
        from capture.macos_window_backend import get_active_window_title_native

        with patch("capture.macos_window_backend._get_frontmost_app_name", return_value=None):
            assert get_active_window_title_native() == "Unknown"

    def test_returns_unknown_on_exception(self):
        from capture.macos_window_backend import get_active_window_title_native

        with patch("capture.macos_window_backend._get_frontmost_app_name", side_effect=RuntimeError):
            assert get_active_window_title_native() == "Unknown"


class TestGetFrontmostAppName:
    @pytest.fixture(autouse=True)
    def _skip_if_no_appkit(self):
        from capture.macos_window_backend import APPKIT_AVAILABLE
        if not APPKIT_AVAILABLE:
            pytest.skip("pyobjc AppKit not installed")

    def test_returns_app_name(self):
        from capture.macos_window_backend import _get_frontmost_app_name

        mock_app = MagicMock()
        mock_app.localizedName.return_value = "Terminal"
        mock_ws = MagicMock()
        mock_ws.frontmostApplication.return_value = mock_app

        with patch("capture.macos_window_backend.NSWorkspace") as MockNSWorkspace:
            MockNSWorkspace.sharedWorkspace.return_value = mock_ws
            assert _get_frontmost_app_name() == "Terminal"

    def test_returns_none_when_no_frontmost(self):
        from capture.macos_window_backend import _get_frontmost_app_name

        mock_ws = MagicMock()
        mock_ws.frontmostApplication.return_value = None

        with patch("capture.macos_window_backend.NSWorkspace") as MockNSWorkspace:
            MockNSWorkspace.sharedWorkspace.return_value = mock_ws
            assert _get_frontmost_app_name() is None


class TestGetWindowTitleForApp:
    @pytest.fixture(autouse=True)
    def _skip_if_no_quartz_window(self):
        from capture.macos_window_backend import _QUARTZ_WINDOW_AVAILABLE
        if not _QUARTZ_WINDOW_AVAILABLE:
            pytest.skip("Quartz CGWindowList not available")

    def test_returns_title_with_app_name(self):
        from capture.macos_window_backend import _get_window_title_for_app

        window_list = [
            {"kCGWindowOwnerName": "Safari", "kCGWindowName": "Google"},
            {"kCGWindowOwnerName": "Finder", "kCGWindowName": "Desktop"},
        ]
        with patch("capture.macos_window_backend.CGWindowListCopyWindowInfo", return_value=window_list):
            result = _get_window_title_for_app("Safari")
            assert result == "Safari — Google"

    def test_returns_app_name_when_no_window_title(self):
        from capture.macos_window_backend import _get_window_title_for_app

        window_list = [
            {"kCGWindowOwnerName": "Finder", "kCGWindowName": ""},
        ]
        with patch("capture.macos_window_backend.CGWindowListCopyWindowInfo", return_value=window_list):
            result = _get_window_title_for_app("Finder")
            assert result == "Finder"

    def test_returns_none_when_app_not_found(self):
        from capture.macos_window_backend import _get_window_title_for_app

        window_list = [
            {"kCGWindowOwnerName": "Terminal", "kCGWindowName": "bash"},
        ]
        with patch("capture.macos_window_backend.CGWindowListCopyWindowInfo", return_value=window_list):
            result = _get_window_title_for_app("Safari")
            assert result is None

    def test_returns_none_when_window_list_is_none(self):
        from capture.macos_window_backend import _get_window_title_for_app

        with patch("capture.macos_window_backend.CGWindowListCopyWindowInfo", return_value=None):
            result = _get_window_title_for_app("Safari")
            assert result is None
