"""
Screenshot capture module.

Captures screenshots on-demand and stores them on disk.

Backend selection:
  - macOS with pyobjc-framework-Quartz → native Quartz CoreGraphics backend
    (proper Retina/HiDPI support, faster capture)
  - All other platforms / missing pyobjc  → PIL ImageGrab (default)
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any
import threading

from PIL import ImageGrab

from capture import register_capture
from capture.base import BaseCapture
from utils.system_info import get_platform

_logger = logging.getLogger(__name__)

_USE_NATIVE_MACOS = False
if get_platform() == "darwin":
    try:
        from capture.macos_screenshot_backend import QuartzScreenshotBackend, QUARTZ_AVAILABLE

        if QUARTZ_AVAILABLE:
            _USE_NATIVE_MACOS = True
            _logger.debug("Native macOS Quartz screenshot backend available")
    except ImportError:
        pass


@register_capture("screenshot")
class ScreenshotCapture(BaseCapture):
    """Capture screenshots and save to disk."""

    def __init__(self, config: dict[str, Any], global_config: dict[str, Any] | None = None):
        super().__init__(config, global_config)
        self._format = str(config.get("format", "png")).lower()
        self._quality = int(config.get("quality", 80))
        self._capture_region = str(config.get("capture_region", "full")).lower()
        self._max_count = int(config.get("max_count", 100))
        data_dir = (
            self.global_config.get("general", {}).get("data_dir")
            if self.global_config
            else None
        )
        self._output_dir = Path(data_dir or "./data") / "screenshots"
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._counter = 0
        self._buffer: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._use_native = _USE_NATIVE_MACOS
        self._native_backend: QuartzScreenshotBackend | None = None  # noqa: F821
        if self._use_native:
            self._native_backend = QuartzScreenshotBackend()

    def start(self) -> None:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._running = True
        backend_name = "native macOS Quartz" if self._use_native else "PIL ImageGrab"
        self.logger.info("Screenshot capture started (%s backend)", backend_name)

    def stop(self) -> None:
        self._running = False
        self.logger.info("Screenshot capture stopped")

    def collect(self) -> list[dict[str, Any]]:
        with self._lock:
            if not self._buffer:
                return []
            items = list(self._buffer)
            self._buffer.clear()
        return items

    def capture(self, output_path: Path, fmt: str = "png", quality: int = 80) -> bool:
        """Capture a screenshot to the given path.

        Returns True on success, False on failure.  This is the public API
        that external callers (e.g. SessionRecorder) should use instead of
        accessing private backend attributes directly.
        """
        try:
            if self._use_native and self._native_backend is not None:
                return self._native_backend.capture(output_path, fmt, quality)
            else:
                image = ImageGrab.grab()
                save_kwargs: dict[str, Any] = {}
                if fmt in {"jpg", "jpeg"}:
                    save_kwargs["quality"] = quality
                image.save(str(output_path), **save_kwargs)
                return True
        except Exception as exc:
            _logger.error("capture() failed: %s", exc)
            return False

    def take_screenshot(self) -> Path | None:
        try:
            if not self._running:
                return None
            with self._lock:
                if self._max_count > 0 and self._counter >= self._max_count:
                    self.logger.warning(
                        "Screenshot limit reached (%d). Stopping capture.",
                        self._max_count,
                    )
                    self._running = False
                    return None
                index = self._counter
                self._counter += 1
            if self._capture_region != "full":
                self.logger.warning(
                    "capture_region '%s' not supported, using full screen",
                    self._capture_region,
                )
            filename = f"screenshot_{index:04d}.{self._format}"
            filepath = self._output_dir / filename

            if self._use_native and self._native_backend is not None:
                ok = self._native_backend.capture(filepath, self._format, self._quality)
                if not ok:
                    self.logger.error("Native screenshot capture failed")
                    return None
            else:
                image = ImageGrab.grab()
                save_kwargs: dict[str, Any] = {}
                if self._format in {"jpg", "jpeg"}:
                    save_kwargs["quality"] = self._quality
                image.save(str(filepath), **save_kwargs)

            file_size = filepath.stat().st_size
            with self._lock:
                self._buffer.append(
                    {
                        "type": "screenshot",
                        "path": str(filepath),
                        "timestamp": time.time(),
                        "size": file_size,
                    }
                )
            return filepath
        except Exception as exc:
            self.logger.error("Screenshot failed: %s", exc)
            return None
