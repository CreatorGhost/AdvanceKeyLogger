"""
System metadata collection.

Gathers information about the host system (hostname, OS, IP, etc.)
for context and diagnostics.

Usage:
    from utils.system_info import get_system_info

    info = get_system_info()
    print(info["hostname"], info["os"], info["local_ip"])
"""
from __future__ import annotations

import getpass
import logging
import os
import platform
import socket
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def get_system_info() -> dict[str, str]:
    """
    Collect system metadata.

    Returns:
        Dict with keys: hostname, username, os, os_version, os_release,
        architecture, python_version, local_ip, timestamp, pid.
    """
    info = {
        "hostname": _safe_call(socket.gethostname),
        "username": _safe_call(getpass.getuser),
        "os": platform.system(),
        "os_version": platform.version(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "local_ip": _get_local_ip(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pid": str(os.getpid()),
    }
    logger.debug("System info collected: %s", info)
    return info


def get_platform() -> str:
    """
    Returns the current platform as a lowercase string.

    Returns:
        One of: "windows", "linux", "darwin" (macOS).
    """
    return platform.system().lower()


def _get_local_ip() -> str:
    """Get the machine's local IP address."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def _safe_call(func, default: str = "unknown") -> str:
    """Call a function, returning default on any error."""
    try:
        return func()
    except Exception:
        return default
