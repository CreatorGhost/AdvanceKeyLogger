"""
Adaptive Capture Intelligence — dynamically adjusts capture frequency and
strategy based on system load, user activity patterns, and resource budgets.

Integrates with capture modules via the AdaptivePolicy returned by
``AdaptiveEngine.evaluate()``.  The main loop queries the engine each
iteration and applies the policy (e.g. skip screenshots during high CPU,
increase polling during active typing bursts).
"""

from __future__ import annotations

import logging
import platform
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SystemSnapshot:
    """Point-in-time system resource snapshot."""

    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    disk_percent: float = 0.0
    battery_percent: float | None = None  # None = desktop / unknown
    is_on_battery: bool = False
    timestamp: float = field(default_factory=time.time)


@dataclass
class ActivitySnapshot:
    """Recent user-activity summary."""

    events_per_second: float = 0.0
    active_window: str = ""
    idle_seconds: float = 0.0
    typing_burst: bool = False  # True when sustained high keyrate detected


@dataclass
class AdaptivePolicy:
    """Output of the adaptive engine — tells capture modules what to do."""

    capture_interval: float = 1.0  # seconds between collection sweeps
    screenshot_enabled: bool = True
    screenshot_quality: int = 75  # JPEG quality 1-100
    audio_enabled: bool = True
    clipboard_enabled: bool = True
    throttle_reason: str | None = None  # human-readable reason for throttling


# ---------------------------------------------------------------------------
# Adaptive Engine
# ---------------------------------------------------------------------------

class AdaptiveEngine:
    """Evaluate system state and produce an :class:`AdaptivePolicy`.

    Configuration keys (under ``adaptive`` in the global config):

    * ``cpu_high_threshold`` (float, default 80) — CPU% above which heavy
      captures (screenshots, audio) are paused.
    * ``cpu_critical_threshold`` (float, default 95) — CPU% above which all
      non-keyboard captures are paused.
    * ``memory_high_threshold`` (float, default 85) — similar for RAM.
    * ``battery_saver_threshold`` (float, default 20) — on battery below
      this %, reduce capture aggressively.
    * ``idle_pause_seconds`` (float, default 300) — after this much idle
      time, extend the capture interval to ``idle_interval``.
    * ``idle_interval`` (float, default 10) — capture interval during idle.
    * ``burst_interval`` (float, default 0.25) — capture interval during a
      typing burst.
    * ``base_interval`` (float, default 1.0) — normal capture interval.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = (config or {}).get("adaptive", {})
        self._cpu_high = float(cfg.get("cpu_high_threshold", 80))
        self._cpu_crit = float(cfg.get("cpu_critical_threshold", 95))
        self._mem_high = float(cfg.get("memory_high_threshold", 85))
        self._bat_saver = float(cfg.get("battery_saver_threshold", 20))
        self._idle_pause = float(cfg.get("idle_pause_seconds", 300))
        self._idle_interval = float(cfg.get("idle_interval", 10.0))
        self._burst_interval = float(cfg.get("burst_interval", 0.25))
        self._base_interval = float(cfg.get("base_interval", 1.0))

        # Smoothing: keep a rolling window of system snapshots
        self._history: list[SystemSnapshot] = []
        self._max_history = 30  # ~30 seconds at 1 Hz

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        system: SystemSnapshot | None = None,
        activity: ActivitySnapshot | None = None,
    ) -> AdaptivePolicy:
        """Return an :class:`AdaptivePolicy` for the current conditions.

        If *system* is ``None`` the engine takes a fresh snapshot via
        :func:`take_system_snapshot`.
        """
        if system is None:
            system = take_system_snapshot()
        if activity is None:
            activity = ActivitySnapshot()

        # Record history for trend analysis
        self._history.append(system)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        policy = AdaptivePolicy(capture_interval=self._base_interval)

        # --- Battery saver ------------------------------------------------
        if system.is_on_battery and system.battery_percent is not None:
            if system.battery_percent < self._bat_saver:
                policy.capture_interval = self._idle_interval
                policy.screenshot_enabled = False
                policy.audio_enabled = False
                policy.screenshot_quality = 40
                policy.throttle_reason = (
                    f"Battery saver ({system.battery_percent:.0f}%)"
                )
                return policy

        # --- CPU critical -------------------------------------------------
        if system.cpu_percent >= self._cpu_crit:
            policy.capture_interval = self._idle_interval
            policy.screenshot_enabled = False
            policy.audio_enabled = False
            policy.clipboard_enabled = False
            policy.throttle_reason = (
                f"CPU critical ({system.cpu_percent:.0f}%)"
            )
            return policy

        # --- CPU high -----------------------------------------------------
        if system.cpu_percent >= self._cpu_high:
            policy.screenshot_enabled = False
            policy.audio_enabled = False
            policy.screenshot_quality = 50
            policy.throttle_reason = f"CPU high ({system.cpu_percent:.0f}%)"

        # --- Memory high --------------------------------------------------
        if system.memory_percent >= self._mem_high:
            policy.screenshot_enabled = False
            policy.screenshot_quality = 40
            if policy.throttle_reason:
                policy.throttle_reason += f"; memory high ({system.memory_percent:.0f}%)"
            else:
                policy.throttle_reason = f"Memory high ({system.memory_percent:.0f}%)"

        # --- Idle detection -----------------------------------------------
        if activity.idle_seconds >= self._idle_pause:
            policy.capture_interval = self._idle_interval
            if not policy.throttle_reason:
                policy.throttle_reason = (
                    f"User idle ({activity.idle_seconds:.0f}s)"
                )
            return policy

        # --- Typing burst -------------------------------------------------
        if activity.typing_burst:
            policy.capture_interval = self._burst_interval

        return policy

    def get_trend(self, metric: str = "cpu_percent", window: int = 10) -> float:
        """Return the average of *metric* over the last *window* snapshots."""
        recent = self._history[-window:]
        if not recent:
            return 0.0
        return sum(getattr(s, metric, 0.0) for s in recent) / len(recent)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def take_system_snapshot() -> SystemSnapshot:
    """Capture current system metrics.

    Uses ``psutil`` if available; returns zeroed snapshot otherwise.
    """
    snap = SystemSnapshot()
    try:
        import psutil

        snap.cpu_percent = psutil.cpu_percent(interval=0)
        snap.memory_percent = psutil.virtual_memory().percent
        snap.disk_percent = psutil.disk_usage("/").percent

        if hasattr(psutil, "sensors_battery"):
            bat = psutil.sensors_battery()
            if bat is not None:
                snap.battery_percent = bat.percent
                snap.is_on_battery = not bat.power_plugged
    except ImportError:
        logger.debug("psutil not available — adaptive engine using defaults")
    except Exception as exc:
        logger.debug("System snapshot failed: %s", exc)

    snap.timestamp = time.time()
    return snap


def detect_environment() -> dict[str, Any]:
    """Return a fingerprint of the current runtime environment."""
    info: dict[str, Any] = {
        "platform": platform.system(),
        "platform_release": platform.release(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "hostname": platform.node(),
    }
    try:
        import psutil

        info["cpu_count"] = psutil.cpu_count(logical=True)
        info["total_memory_gb"] = round(
            psutil.virtual_memory().total / (1024 ** 3), 1
        )
    except ImportError:
        pass
    return info
