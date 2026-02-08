"""
Abstract base class for all capture modules.

Every capture module (keyboard, mouse, screenshot, clipboard, window)
must inherit from BaseCapture and implement start(), stop(), and collect().

Usage:
    class MyCapture(BaseCapture):
        def start(self) -> None: ...
        def stop(self) -> None: ...
        def collect(self) -> list[dict]: ...
"""
from __future__ import annotations

from abc import ABC, abstractmethod
import logging
from typing import Any


class BaseCapture(ABC):
    """Abstract base class that all capture modules must implement."""

    def __init__(
        self,
        config: dict[str, Any],
        global_config: dict[str, Any] | None = None,
    ) -> None:
        self.config = config
        self.global_config = global_config or {}
        self.logger = logging.getLogger(self.__class__.__name__)
        self._running = False

    @abstractmethod
    def start(self) -> None:
        """
        Start capturing. Must be non-blocking (use threads if needed).

        Called once when the application starts. Set self._running = True.
        """

    @abstractmethod
    def stop(self) -> None:
        """
        Stop capturing and clean up all resources.

        Called once on shutdown. Set self._running = False.
        Cancel any timers, close any file handles, join any threads.
        """

    @abstractmethod
    def collect(self) -> list[dict[str, Any]]:
        """
        Return captured data since last collect() call and clear internal buffer.

        Each item should be a dict with at least:
            {
                "type": str,          # e.g. "screenshot", "keystroke"
                "data": Any,          # the captured data (str, bytes, path)
                "timestamp": float,   # time.time() when captured
            }

        Returns:
            List of capture dicts. Empty list if nothing captured.
        """

    @property
    def is_running(self) -> bool:
        """Whether this capture module is currently active."""
        return self._running

    def __enter__(self) -> BaseCapture:
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.stop()

    def __repr__(self) -> str:
        status = "running" if self._running else "stopped"
        return f"<{self.__class__.__name__} ({status})>"
