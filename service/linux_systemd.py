"""
systemd integration for Linux.
"""
from __future__ import annotations

import logging
import os
import shlex
import socket
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


class SystemdManager:
    """Manage systemd user services."""

    def install(self, spec) -> str:
        unit_path = _unit_path(spec.name)
        unit_path.parent.mkdir(parents=True, exist_ok=True)
        unit_path.write_text(_render_unit(spec), encoding="utf-8")

        result = _run(["systemctl", "--user", "daemon-reload"], check=False)
        if result.returncode != 0:
            logger.warning("systemctl daemon-reload failed (rc=%d): %s", result.returncode, result.stderr.strip())
        result = _run(["systemctl", "--user", "enable", "--now", f"{spec.name}.service"], check=False)
        if result.returncode != 0:
            logger.warning("systemctl enable failed (rc=%d): %s", result.returncode, result.stderr.strip())
            return f"Failed to enable systemd service at {unit_path}: {result.stderr.strip()}"
        return f"Installed systemd service at {unit_path}"

    def uninstall(self, spec) -> str:
        result = _run(["systemctl", "--user", "disable", "--now", f"{spec.name}.service"], check=False)
        if result.returncode != 0:
            logger.warning("systemctl disable failed (rc=%d): %s", result.returncode, result.stderr.strip())
        unit_path = _unit_path(spec.name)
        if unit_path.exists():
            unit_path.unlink()
        result = _run(["systemctl", "--user", "daemon-reload"], check=False)
        if result.returncode != 0:
            logger.warning("systemctl daemon-reload failed (rc=%d): %s", result.returncode, result.stderr.strip())
        return f"Uninstalled systemd service {spec.name}"

    def start(self, spec) -> str:
        result = _run(["systemctl", "--user", "start", f"{spec.name}.service"], check=False)
        if result.returncode != 0:
            logger.warning("systemctl start failed (rc=%d): %s", result.returncode, result.stderr.strip())
            return f"Failed to start systemd service {spec.name}: {result.stderr.strip()}"
        return f"Started systemd service {spec.name}"

    def stop(self, spec) -> str:
        result = _run(["systemctl", "--user", "stop", f"{spec.name}.service"], check=False)
        if result.returncode != 0:
            logger.warning("systemctl stop failed (rc=%d): %s", result.returncode, result.stderr.strip())
            return f"Failed to stop systemd service {spec.name}: {result.stderr.strip()}"
        return f"Stopped systemd service {spec.name}"

    def restart(self, spec) -> str:
        result = _run(["systemctl", "--user", "restart", f"{spec.name}.service"], check=False)
        if result.returncode != 0:
            logger.warning("systemctl restart failed (rc=%d): %s", result.returncode, result.stderr.strip())
            return f"Failed to restart systemd service {spec.name}: {result.stderr.strip()}"
        return f"Restarted systemd service {spec.name}"

    def status(self, spec) -> str:
        result = _run(["systemctl", "--user", "is-active", f"{spec.name}.service"], check=False)
        status = result.stdout.strip() if result.stdout else "unknown"
        return f"{spec.name}: {status}"


def _unit_path(name: str) -> Path:
    return Path.home() / ".config" / "systemd" / "user" / f"{name}.service"


def _render_unit(spec) -> str:
    python_path = os.environ.get("PYTHON_BIN", sys.executable)
    project_dir = str(Path(__file__).resolve().parent.parent)
    exec_cmd = f"{shlex.quote(python_path)} -m main --config {shlex.quote(spec.config_path)}"
    return f"""[Unit]
Description={spec.description}
After=network.target graphical-session.target
Wants=graphical-session.target

[Service]
Type=notify
WorkingDirectory={project_dir}
ExecStart={exec_cmd}
Restart=on-failure
RestartSec={spec.restart_sec}
StartLimitBurst={spec.start_limit_burst}
StartLimitIntervalSec={spec.start_limit_interval}
Environment=DISPLAY={spec.display}

[Install]
WantedBy=default.target
"""


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def sd_notify(message: str) -> None:
    """Send a systemd notification message if NOTIFY_SOCKET is set."""
    notify_socket = os.environ.get("NOTIFY_SOCKET")
    if not notify_socket:
        return
    sock = None
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock.connect(notify_socket)
        sock.sendall(message.encode("utf-8"))
    except Exception:
        pass
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
