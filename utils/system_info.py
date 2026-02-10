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


def get_system_metrics() -> dict[str, float]:
    """
    Collect system resource metrics (CPU, memory, disk).

    Uses psutil if available, falls back to basic OS stats.

    Returns:
        Dict with keys: cpu_percent, memory_percent, memory_mb,
        disk_percent, disk_free_gb.
    """
    metrics = {
        "cpu_percent": 0.0,
        "memory_percent": 0.0,
        "memory_mb": 0.0,
        "disk_percent": 0.0,
        "disk_free_gb": 0.0,
    }

    try:
        import psutil

        # CPU usage (non-blocking, 0 interval returns cached value)
        metrics["cpu_percent"] = psutil.cpu_percent(interval=0)

        # Memory usage
        mem = psutil.virtual_memory()
        metrics["memory_percent"] = mem.percent
        metrics["memory_mb"] = round(mem.used / (1024 * 1024), 1)

        # Disk usage (root partition)
        disk = psutil.disk_usage("/")
        metrics["disk_percent"] = disk.percent
        metrics["disk_free_gb"] = round(disk.free / (1024 * 1024 * 1024), 1)

    except ImportError:
        # psutil not installed, try basic approach
        try:
            import resource

            # Memory from resource module (Unix only)
            usage = resource.getrusage(resource.RUSAGE_SELF)
            metrics["memory_mb"] = round(usage.ru_maxrss / 1024, 1)  # KB to MB on Linux
        except (ImportError, AttributeError):
            pass

        try:
            # Disk from os.statvfs (Unix only)
            stat = os.statvfs("/")
            total = stat.f_blocks * stat.f_frsize
            free = stat.f_bfree * stat.f_frsize
            used = total - free
            metrics["disk_percent"] = round((used / total) * 100, 1) if total > 0 else 0
            metrics["disk_free_gb"] = round(free / (1024 * 1024 * 1024), 1)
        except (AttributeError, OSError):
            pass

    logger.debug("System metrics collected: %s", metrics)
    return metrics
