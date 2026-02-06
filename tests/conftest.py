"""Shared pytest fixtures."""
from __future__ import annotations

import pytest
from pathlib import Path

from config.settings import Settings


@pytest.fixture(autouse=True)
def reset_settings():
    """Reset the Settings singleton before each test."""
    Settings.reset()
    yield
    Settings.reset()


@pytest.fixture
def sample_config(tmp_path: Path) -> Path:
    """Create a temporary config file for testing."""
    config_content = """
general:
  report_interval: 10
  data_dir: "{data_dir}"
  log_level: "DEBUG"

storage:
  backend: "local"
  max_size_mb: 10
  rotation: true

capture:
  screenshot:
    enabled: false

encryption:
  enabled: false

compression:
  enabled: true
  format: "zip"
""".format(data_dir=str(tmp_path / "data"))
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(config_content)
    return config_file
