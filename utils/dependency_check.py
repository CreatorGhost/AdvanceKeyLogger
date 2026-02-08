"""
Auto-install missing dependencies at startup.

Checks whether required third-party packages are importable and,
when ``auto_install`` is enabled, installs any that are missing via pip.

Usage:
    from utils.dependency_check import check_and_install_dependencies

    installed, failed = check_and_install_dependencies(auto_install=True)
"""
from __future__ import annotations

import importlib
import logging
import subprocess
import sys

logger = logging.getLogger(__name__)

# Mapping of Python import name -> pip package name.
PACKAGE_MAP: dict[str, str] = {
    "pynput": "pynput",
    "PIL": "Pillow",
    "cryptography": "cryptography",
    "pyperclip": "pyperclip",
    "yaml": "pyyaml",
    "requests": "requests",
    "sounddevice": "sounddevice",
    "numpy": "numpy",
    "psutil": "psutil",
    "Quartz": "pyobjc-framework-Quartz",
}


def check_package(import_name: str) -> bool:
    """Return *True* if *import_name* can be imported."""
    try:
        importlib.import_module(import_name)
        return True
    except ImportError:
        return False


def install_package(pip_name: str, timeout: int = 120) -> bool:
    """Install *pip_name* via pip.  Returns *True* on success."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", pip_name],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode == 0:
            logger.info("Successfully installed %s", pip_name)
            return True
        logger.warning("pip install %s failed (rc=%d): %s", pip_name, result.returncode, result.stderr.strip())
        return False
    except subprocess.TimeoutExpired:
        logger.warning("pip install %s timed out after %ds", pip_name, timeout)
        return False
    except Exception as exc:
        logger.warning("pip install %s error: %s", pip_name, exc)
        return False


def check_and_install_dependencies(
    auto_install: bool = False,
    package_map: dict[str, str] | None = None,
) -> tuple[list[str], list[str]]:
    """Check all packages and optionally install missing ones.

    Args:
        auto_install: If *True*, attempt to ``pip install`` missing packages.
        package_map: Override the default :data:`PACKAGE_MAP`.

    Returns:
        ``(installed, failed)`` — lists of pip package names that were
        successfully installed and those that failed / were skipped.
    """
    if package_map is None:
        package_map = PACKAGE_MAP

    installed: list[str] = []
    failed: list[str] = []

    for import_name, pip_name in package_map.items():
        if check_package(import_name):
            continue
        if not auto_install:
            logger.debug("Package '%s' (%s) is missing (auto-install disabled)", import_name, pip_name)
            failed.append(pip_name)
            continue
        logger.info("Package '%s' missing — installing %s ...", import_name, pip_name)
        if install_package(pip_name):
            installed.append(pip_name)
        else:
            failed.append(pip_name)

    if installed:
        logger.info("Installed packages: %s", ", ".join(installed))
    if failed:
        logger.warning("Missing/failed packages: %s", ", ".join(failed))

    return installed, failed
