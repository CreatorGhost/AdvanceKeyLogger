"""Tests for the native macOS Quartz screenshot backend."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="macOS-only backend",
)


class TestQuartzScreenshotBackend:
    @pytest.fixture(autouse=True)
    def _skip_if_no_quartz(self):
        from capture.macos_screenshot_backend import QUARTZ_AVAILABLE
        if not QUARTZ_AVAILABLE:
            pytest.skip("pyobjc-framework-Quartz not installed")

    def test_capture_returns_true_on_success(self, tmp_path):
        from capture.macos_screenshot_backend import QuartzScreenshotBackend

        out = tmp_path / "test.png"
        backend = QuartzScreenshotBackend()

        mock_cg_image = MagicMock()
        with patch("capture.macos_screenshot_backend.CGWindowListCreateImage", return_value=mock_cg_image), \
             patch.object(backend, "_save_image", return_value=True):
            assert backend.capture(out, "png", 80) is True

    def test_capture_returns_false_when_cg_image_is_none(self, tmp_path):
        from capture.macos_screenshot_backend import QuartzScreenshotBackend

        out = tmp_path / "test.png"
        backend = QuartzScreenshotBackend()

        with patch("capture.macos_screenshot_backend.CGWindowListCreateImage", return_value=None):
            assert backend.capture(out, "png", 80) is False

    def test_capture_returns_false_on_exception(self, tmp_path):
        from capture.macos_screenshot_backend import QuartzScreenshotBackend

        out = tmp_path / "test.png"
        backend = QuartzScreenshotBackend()

        with patch("capture.macos_screenshot_backend.CGWindowListCreateImage", side_effect=RuntimeError("boom")):
            assert backend.capture(out, "png", 80) is False

    def test_save_image_tries_appkit_first(self):
        from capture.macos_screenshot_backend import QuartzScreenshotBackend

        mock_cg_image = MagicMock()
        out = Path("/tmp/test.png")

        with patch("capture.macos_screenshot_backend._CI_AVAILABLE", True), \
             patch("capture.macos_screenshot_backend._save_via_appkit", return_value=True) as mock_appkit:
            result = QuartzScreenshotBackend._save_image(mock_cg_image, out, "png", 80)

        assert result is True
        mock_appkit.assert_called_once()

    def test_save_image_falls_back_to_cgdest(self):
        from capture.macos_screenshot_backend import QuartzScreenshotBackend

        mock_cg_image = MagicMock()
        out = Path("/tmp/test.png")

        with patch("capture.macos_screenshot_backend._CI_AVAILABLE", False), \
             patch("capture.macos_screenshot_backend._CG_DEST_AVAILABLE", True), \
             patch("capture.macos_screenshot_backend._save_via_cgdest", return_value=True) as mock_cgdest:
            result = QuartzScreenshotBackend._save_image(mock_cg_image, out, "png", 80)

        assert result is True
        mock_cgdest.assert_called_once()

    def test_save_image_fails_when_no_helpers(self):
        from capture.macos_screenshot_backend import QuartzScreenshotBackend

        with patch("capture.macos_screenshot_backend._CI_AVAILABLE", False), \
             patch("capture.macos_screenshot_backend._CG_DEST_AVAILABLE", False):
            result = QuartzScreenshotBackend._save_image(MagicMock(), Path("/tmp/x.png"), "png", 80)

        assert result is False
