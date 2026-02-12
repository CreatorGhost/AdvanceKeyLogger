"""
Middleware: ContextAnnotator
Adds host/process/window context to events.
"""
from __future__ import annotations

import os
import subprocess
import sys
from typing import Any

from pipeline.base_middleware import BaseMiddleware, CaptureEvent
from pipeline.context import PipelineContext
from pipeline.registry import register_middleware
from utils.system_info import get_platform


@register_middleware("context_annotator")
class ContextAnnotator(BaseMiddleware):
    @property
    def name(self) -> str:
        return "context_annotator"

    @property
    def order(self) -> int:
        return 20

    def process(self, event: CaptureEvent, context: PipelineContext) -> CaptureEvent:
        sys_info = context.system_info or {}
        event["context"] = {
            "hostname": sys_info.get("hostname"),
            "username": sys_info.get("username"),
            "pid": os.getpid(),
            "process": os.path.basename(sys.argv[0]) if sys.argv else "",
            "window_title": _get_active_window_title(),
        }
        return event


def _get_active_window_title() -> str:
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
            if result.returncode != 0:
                return "Unknown"
            return result.stdout.strip()
        if system == "windows":
            import ctypes  # lazy import

            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buffer = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length + 1)
            return buffer.value.strip()
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
            if result.returncode != 0:
                return "Unknown"
            return result.stdout.strip()
    except Exception:
        return "Unknown"
    return "Unknown"
