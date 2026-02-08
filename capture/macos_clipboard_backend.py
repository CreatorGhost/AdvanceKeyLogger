"""
Native macOS clipboard backend using NSPasteboard (AppKit via pyobjc).

Monitors the general pasteboard's ``changeCount`` to detect clipboard
changes without spawning ``pbpaste`` subprocesses, making it significantly
faster and lighter than pyperclip's polling approach.

Falls back gracefully when pyobjc is not installed (see APPKIT_AVAILABLE).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)

APPKIT_AVAILABLE = False
try:
    from AppKit import NSPasteboard, NSStringPboardType

    APPKIT_AVAILABLE = True
except ImportError:
    pass


class NSPasteboardBackend:
    """Native macOS clipboard monitoring using NSPasteboard."""

    def __init__(
        self,
        on_change_callback: Callable[[str], None],
        poll_interval: float = 2.0,
    ) -> None:
        self._on_change = on_change_callback
        self._poll_interval = poll_interval
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_change_count: int = -1
        self._last_value: str | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start polling the pasteboard change count in a daemon thread."""
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._last_change_count = self._current_change_count()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="nspasteboard-clipboard"
        )
        self._thread.start()
        logger.info("NSPasteboard clipboard backend started")

    def stop(self) -> None:
        """Stop the polling thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("NSPasteboard clipboard backend stopped")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                cc = self._current_change_count()
                if cc != self._last_change_count:
                    self._last_change_count = cc
                    value = self._read_string()
                    if value and value != self._last_value:
                        self._last_value = value
                        self._on_change(value)
            except Exception as exc:
                logger.warning("NSPasteboard read error: %s", exc)
            self._stop_event.wait(self._poll_interval)

    @staticmethod
    def _current_change_count() -> int:
        pb = NSPasteboard.generalPasteboard()
        return pb.changeCount()

    @staticmethod
    def _read_string() -> str | None:
        """Read the current string from the general pasteboard."""
        pb = NSPasteboard.generalPasteboard()
        value = pb.stringForType_(NSStringPboardType)
        return str(value) if value else None
