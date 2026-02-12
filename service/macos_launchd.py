"""
launchd integration for macOS.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


class LaunchdManager:
    """Manage launchd user agents."""

    def install(self, spec) -> str:
        plist_path = _plist_path(spec.name)
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        plist_path.write_text(_render_plist(spec), encoding="utf-8")
        result = _run(["launchctl", "load", "-w", str(plist_path)], check=False)
        if result.returncode != 0:
            logger.warning("launchctl load failed (rc=%d): %s", result.returncode, result.stderr.strip())
            return f"Failed to load launchd agent at {plist_path}: {result.stderr.strip()}"
        return f"Installed launchd agent at {plist_path}"

    def uninstall(self, spec) -> str:
        plist_path = _plist_path(spec.name)
        result = _run(["launchctl", "unload", "-w", str(plist_path)], check=False)
        if result.returncode != 0:
            logger.warning("launchctl unload failed (rc=%d): %s", result.returncode, result.stderr.strip())
        if plist_path.exists():
            plist_path.unlink()
        return f"Uninstalled launchd agent {spec.name}"

    def start(self, spec) -> str:
        label = _label(spec.name)
        result = _run(["launchctl", "start", label], check=False)
        if result.returncode != 0:
            logger.warning("launchctl start failed (rc=%d): %s", result.returncode, result.stderr.strip())
            return f"Failed to start launchd agent {spec.name}: {result.stderr.strip()}"
        return f"Started launchd agent {spec.name}"

    def stop(self, spec) -> str:
        label = _label(spec.name)
        result = _run(["launchctl", "stop", label], check=False)
        if result.returncode != 0:
            logger.warning("launchctl stop failed (rc=%d): %s", result.returncode, result.stderr.strip())
            return f"Failed to stop launchd agent {spec.name}: {result.stderr.strip()}"
        return f"Stopped launchd agent {spec.name}"

    def restart(self, spec) -> str:
        label = _label(spec.name)
        stop_result = _run(["launchctl", "stop", label], check=False)
        if stop_result.returncode != 0:
            logger.warning("launchctl stop failed during restart (rc=%d): %s", stop_result.returncode, stop_result.stderr.strip())
        start_result = _run(["launchctl", "start", label], check=False)
        if start_result.returncode != 0:
            logger.warning("launchctl start failed during restart (rc=%d): %s", start_result.returncode, start_result.stderr.strip())
            return f"Failed to restart launchd agent {spec.name}: {start_result.stderr.strip()}"
        return f"Restarted launchd agent {spec.name}"

    def status(self, spec) -> str:
        label = _label(spec.name)
        result = _run(["launchctl", "list", label], check=False)
        if result.returncode == 0:
            return f"{spec.name}: running"
        return f"{spec.name}: not loaded"


def _plist_path(name: str) -> Path:
    label = _label(name)
    return Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"


def _label(name: str) -> str:
    return f"com.apple.{name}.agent"


def _xml_escape(value: str) -> str:
    """Escape XML special characters in user-provided strings."""
    return (
        value
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _render_plist(spec) -> str:
    python_path = _xml_escape(os.environ.get("PYTHON_BIN", sys.executable))
    label = _xml_escape(_label(spec.name))
    project_dir = _xml_escape(str(Path(__file__).resolve().parent.parent))
    config_path = _xml_escape(spec.config_path)
    out_log = _xml_escape(str(Path.home() / "Library" / "Logs" / "diagnosticd.out.log"))
    err_log = _xml_escape(str(Path.home() / "Library" / "Logs" / "diagnosticd.err.log"))
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
        <string>{config_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>StandardOutPath</key>
    <string>{out_log}</string>
    <key>StandardErrorPath</key>
    <string>{err_log}</string>
</dict>
</plist>
"""


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)
