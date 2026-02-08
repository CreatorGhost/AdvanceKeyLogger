"""
Active window capture module.

Polls for the currently focused window title and records changes.
"""
from __future__ import annotations

import ctypes
import subprocess
import threading
import time
from typing import Any

from capture import register_capture
from capture.base import BaseCapture
from utils.system_info import get_platform


@register_capture("window")
class WindowCapture(BaseCapture):
    """Capture active window title changes."""

    def __init__(self, config: dict[str, Any], global_config: dict[str, Any] | None = None):
        super().__init__(config, global_config)
        self._poll_interval = float(config.get("poll_interval", 2))
        self._buffer: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_title: str | None = None

    def start(self) -> None:
        with self._lifecycle_lock:
            if self._thread is not None:
                return
            self._stop_event.clear()
            thread = threading.Thread(target=self._run, daemon=True)
            self._thread = thread
            self._running = True
            thread.start()

    def stop(self) -> None:
        with self._lifecycle_lock:
            if self._thread is None:
                return
            thread = self._thread
            self._thread = None
        self._stop_event.set()
        thread.join(timeout=5.0)
        if thread.is_alive():
            self.logger.warning(
                "Window capture thread still alive after join; "
                "_stop_event was set"
            )
        self._running = False

    def collect(self) -> list[dict[str, Any]]:
        with self._lock:
            if not self._buffer:
                return []
            items = list(self._buffer)
            self._buffer.clear()
        return items

    def _run(self) -> None:
        while not self._stop_event.is_set():
            title = _get_active_window_title()
            if title and title != self._last_title:
                self._last_title = title
                with self._lock:
                    self._buffer.append(
                        {"type": "window", "data": title, "timestamp": time.time()}
                    )
            self._stop_event.wait(self._poll_interval)


def _get_active_window_title() -> str:
    """
    Get the title of the currently active/focused window.

    Returns "Unknown" if:
    - The platform is not supported
    - The subprocess command fails (non-zero exit code)
    - The subprocess command returns empty output
    - Any exception occurs (command not found, timeout, etc.)
    """
    system = get_platform()
    try:
        if system == "linux":
            result = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            # Check for command failure or empty output
            if result.returncode != 0:
                return "Unknown"
            title = result.stdout.strip()
            return title if title else "Unknown"

        if system == "windows":
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buffer = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length + 1)
            title = buffer.value.strip()
            return title if title else "Unknown"

        if system == "darwin":
            script = (
                'tell application "System Events" to '
                'get name of first application process whose frontmost is true'
            )
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            # Check for command failure or empty output
            if result.returncode != 0:
                return "Unknown"
            title = result.stdout.strip()
            return title if title else "Unknown"

    except Exception:
        return "Unknown"
    return "Unknown"
