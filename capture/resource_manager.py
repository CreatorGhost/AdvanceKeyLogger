"""
Resource Manager — enforces CPU, memory, and disk budgets for capture modules.

Provides a context-manager and decorator pattern for capture operations:

    rm = ResourceManager(config)

    with rm.budget("screenshot"):
        # expensive operation — paused/skipped if over budget
        take_screenshot()

Or as a guard:

    if rm.can_proceed("audio"):
        record_audio_chunk()
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generator

logger = logging.getLogger(__name__)


@dataclass
class ResourceBudget:
    """Configurable resource limits for a named component."""

    name: str
    max_cpu_percent: float = 50.0
    max_memory_mb: float = 200.0
    max_disk_mb: float = 500.0
    priority: int = 5  # lower = higher priority (1-10)
    paused: bool = False
    pause_reason: str = ""


@dataclass
class ResourceUsage:
    """Current resource usage snapshot."""

    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    disk_mb: float = 0.0
    timestamp: float = field(default_factory=time.time)


class ResourceManager:
    """Enforce resource budgets across capture modules.

    Configuration keys (under ``resources`` in the global config):

    * ``cpu_limit`` (float, default 30) — total CPU% budget for all captures.
    * ``memory_limit_mb`` (float, default 300) — total RAM budget in MB.
    * ``disk_limit_mb`` (float, default 1000) — total disk budget in MB for
      captured data (screenshots, recordings, etc.).
    * ``check_interval`` (float, default 5) — seconds between resource checks.
    * ``budgets`` (dict) — per-component overrides, e.g.:
      ``{"screenshot": {"max_cpu_percent": 20, "priority": 3}}``.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = (config or {}).get("resources", {})
        self._cpu_limit = float(cfg.get("cpu_limit", 30))
        self._mem_limit = float(cfg.get("memory_limit_mb", 300))
        self._disk_limit = float(cfg.get("disk_limit_mb", 1000))
        self._check_interval = float(cfg.get("check_interval", 5))
        self._data_dir = cfg.get("data_dir", "data")

        self._budgets: dict[str, ResourceBudget] = {}
        self._usage = ResourceUsage()
        self._lock = threading.Lock()
        self._last_check = 0.0

        # Load per-component budgets from config
        for name, bcfg in cfg.get("budgets", {}).items():
            self._budgets[name] = ResourceBudget(
                name=name,
                max_cpu_percent=float(bcfg.get("max_cpu_percent", 50)),
                max_memory_mb=float(bcfg.get("max_memory_mb", 200)),
                max_disk_mb=float(bcfg.get("max_disk_mb", 500)),
                priority=int(bcfg.get("priority", 5)),
            )

    # ------------------------------------------------------------------
    # Budget registration
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        max_cpu_percent: float = 50.0,
        max_memory_mb: float = 200.0,
        max_disk_mb: float = 500.0,
        priority: int = 5,
    ) -> ResourceBudget:
        """Register (or update) a named resource budget."""
        with self._lock:
            budget = self._budgets.get(name)
            if budget is None:
                budget = ResourceBudget(
                    name=name,
                    max_cpu_percent=max_cpu_percent,
                    max_memory_mb=max_memory_mb,
                    max_disk_mb=max_disk_mb,
                    priority=priority,
                )
                self._budgets[name] = budget
            else:
                budget.max_cpu_percent = max_cpu_percent
                budget.max_memory_mb = max_memory_mb
                budget.max_disk_mb = max_disk_mb
                budget.priority = priority
            return budget

    # ------------------------------------------------------------------
    # Usage tracking
    # ------------------------------------------------------------------

    def refresh(self) -> ResourceUsage:
        """Refresh resource usage (rate-limited by ``check_interval``)."""
        now = time.time()
        with self._lock:
            if now - self._last_check < self._check_interval:
                return self._usage

        usage = ResourceUsage(timestamp=now)
        try:
            import psutil

            proc = psutil.Process()
            usage.cpu_percent = proc.cpu_percent(interval=0)
            usage.memory_mb = proc.memory_info().rss / (1024 * 1024)
        except ImportError:
            pass
        except Exception as exc:
            logger.debug("Resource check failed: %s", exc)

        # Disk usage for data directory (read from config)
        try:
            from pathlib import Path

            data_dir = Path(self._data_dir)
            if data_dir.exists():
                total = sum(f.stat().st_size for f in data_dir.rglob("*") if f.is_file())
                usage.disk_mb = total / (1024 * 1024)
        except Exception:
            pass

        with self._lock:
            self._usage = usage
            self._last_check = now
            self._enforce_budgets(usage)
        return usage

    def _enforce_budgets(self, usage: ResourceUsage) -> None:
        """Pause low-priority components if global limits are exceeded."""
        over_cpu = usage.cpu_percent > self._cpu_limit
        over_mem = usage.memory_mb > self._mem_limit
        over_disk = usage.disk_mb > self._disk_limit

        if not (over_cpu or over_mem or over_disk):
            # Un-pause everything
            for budget in self._budgets.values():
                if budget.paused:
                    budget.paused = False
                    budget.pause_reason = ""
                    logger.info("Resource budget '%s' resumed", budget.name)
            return

        # Sort by priority descending (highest number = lowest priority = pause first)
        sorted_budgets = sorted(
            self._budgets.values(), key=lambda b: -b.priority
        )

        reasons = []
        if over_cpu:
            reasons.append(f"CPU {usage.cpu_percent:.0f}% > {self._cpu_limit:.0f}%")
        if over_mem:
            reasons.append(f"Memory {usage.memory_mb:.0f}MB > {self._mem_limit:.0f}MB")
        if over_disk:
            reasons.append(f"Disk {usage.disk_mb:.0f}MB > {self._disk_limit:.0f}MB")

        reason = "; ".join(reasons)

        for budget in sorted_budgets:
            if not budget.paused:
                budget.paused = True
                budget.pause_reason = reason
                logger.warning(
                    "Pausing '%s' (priority %d): %s",
                    budget.name, budget.priority, reason,
                )
                # Only pause one component at a time — re-evaluate next cycle
                break

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------

    def can_proceed(self, name: str) -> bool:
        """Check if a component is allowed to proceed."""
        self.refresh()
        with self._lock:
            budget = self._budgets.get(name)
            if budget is None:
                return True  # unregistered components are unconstrained
            return not budget.paused

    @contextmanager
    def budget(self, name: str) -> Generator[ResourceBudget | None, None, None]:
        """Context manager that yields the budget if the component can proceed.

        Usage::

            with rm.budget("screenshot") as b:
                if b is None:
                    return  # paused
                take_screenshot(quality=...)
        """
        self.refresh()
        with self._lock:
            b = self._budgets.get(name)
            paused = b is not None and b.paused
            reason = b.pause_reason if b else ""
        if paused:
            logger.debug("Component '%s' paused: %s", name, reason)
            yield None
        else:
            yield b

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Return a status dict suitable for dashboards / heartbeats."""
        with self._lock:
            usage_snapshot = {
                "cpu_percent": self._usage.cpu_percent,
                "memory_mb": round(self._usage.memory_mb, 1),
                "disk_mb": round(self._usage.disk_mb, 1),
            }
            budgets_snapshot = {
                name: {
                    "priority": b.priority,
                    "paused": b.paused,
                    "pause_reason": b.pause_reason,
                }
                for name, b in self._budgets.items()
            }
        return {
            "usage": usage_snapshot,
            "limits": {
                "cpu_limit": self._cpu_limit,
                "memory_limit_mb": self._mem_limit,
                "disk_limit_mb": self._disk_limit,
            },
            "budgets": budgets_snapshot,
        }
