"""Tests for service templates."""
from __future__ import annotations

from service.linux_systemd import _render_unit
from service.macos_launchd import _render_plist
from service.manager import ServiceSpec


def _spec():
    return ServiceSpec(
        name="advancekeylogger",
        description="AdvanceKeyLogger Monitoring Service",
        config_path="/tmp/config.yaml",
        restart_sec=10,
        start_limit_burst=3,
        start_limit_interval=60,
        display=":0",
    )


def test_systemd_template_contains_execstart():
    unit = _render_unit(_spec())
    assert "ExecStart" in unit
    assert "Type=notify" in unit
    assert "--config" in unit
    assert "config.yaml" in unit


def test_launchd_template_contains_config():
    plist = _render_plist(_spec())
    assert "<string>main</string>" in plist
    assert "<string>/tmp/config.yaml</string>" in plist
