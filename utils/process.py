"""
Process management utilities: PID lock and graceful shutdown.

PIDLock prevents multiple instances from running simultaneously.
GracefulShutdown handles SIGINT/SIGTERM for clean exit.

Usage:
    from utils.process import PIDLock, GracefulShutdown

    lock = PIDLock()
    if not lock.acquire():
        print("Another instance is already running")
        sys.exit(1)

    shutdown = GracefulShutdown()
    while not shutdown.requested:
        do_work()
    # Cleanup happens here
"""
from __future__ import annotations

import atexit
import logging
import os
import signal
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class PIDLock:
    """
    Prevents multiple instances from running simultaneously.

    Creates a file containing the current PID. On startup, checks
    if another instance is already running.
    """

    def __init__(self, pid_file: str | None = None) -> None:
        if pid_file is None:
            pid_file = os.path.join(tempfile.gettempdir(), ".system-helper.pid")
        self.pid_file = Path(pid_file)

    def acquire(self) -> bool:
        """
        Attempt to acquire the PID lock.

        Returns:
            True if lock acquired successfully.
            False if another instance is already running.
        """
        if self.pid_file.exists():
            try:
                existing_pid = int(self.pid_file.read_text().strip())
            except (ValueError, OSError):
                logger.warning("Corrupt PID file, removing")
                self.pid_file.unlink(missing_ok=True)
            else:
                if self._is_process_running(existing_pid):
                    logger.error("Another instance is running (PID %d)", existing_pid)
                    return False
                logger.warning("Stale PID file found (PID %d not running), removing", existing_pid)
                self.pid_file.unlink(missing_ok=True)

        try:
            self.pid_file.write_text(str(os.getpid()))
            atexit.register(self.release)
            logger.info("PID lock acquired (PID %d): %s", os.getpid(), self.pid_file)
            return True
        except OSError as e:
            logger.error("Failed to create PID file: %s", e)
            return False

    def release(self) -> None:
        """Release the PID lock by removing the file."""
        try:
            if self.pid_file.exists():
                self.pid_file.unlink()
                logger.info("PID lock released")
        except OSError as e:
            logger.error("Failed to release PID lock: %s", e)

    @staticmethod
    def _is_process_running(pid: int) -> bool:
        """Check if a process with the given PID is running."""
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True


class GracefulShutdown:
    """
    Handle SIGINT (Ctrl+C) and SIGTERM (kill) for clean shutdown.

    Sets `self.requested = True` when a signal is received, allowing
    the main loop to finish its current iteration and clean up.

    Usage:
        shutdown = GracefulShutdown()
        while not shutdown.requested:
            do_work()
    """

    def __init__(self) -> None:
        self.requested = False
        self._original_sigint = signal.getsignal(signal.SIGINT)
        self._original_sigterm = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGINT, self._handler)
        signal.signal(signal.SIGTERM, self._handler)

    def _handler(self, signum: int, frame) -> None:
        sig_name = signal.Signals(signum).name
        logger.info("Received %s, initiating graceful shutdown...", sig_name)
        self.requested = True

    def restore(self) -> None:
        """Restore the original signal handlers."""
        signal.signal(signal.SIGINT, self._original_sigint)
        signal.signal(signal.SIGTERM, self._original_sigterm)
