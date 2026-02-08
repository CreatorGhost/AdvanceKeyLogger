"""Tests for utils.self_destruct module."""
from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest

from utils.self_destruct import (
    execute_self_destruct,
    remove_data_directory,
    remove_log_files,
    remove_pid_file,
    remove_sqlite_database,
    secure_delete_file,
    uninstall_service,
)


class TestSecureDeleteFile:
    """Tests for secure_delete_file()."""

    def test_delete_simple(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        secure_delete_file(f, secure_wipe=False)
        assert not f.exists()

    def test_delete_with_wipe(self, tmp_path):
        f = tmp_path / "secret.txt"
        f.write_bytes(b"sensitive data 12345")
        size = f.stat().st_size
        secure_delete_file(f, secure_wipe=True)
        assert not f.exists()

    def test_delete_nonexistent(self, tmp_path):
        f = tmp_path / "nope.txt"
        # Should not raise
        secure_delete_file(f, secure_wipe=True)


class TestRemoveDataDirectory:
    """Tests for remove_data_directory()."""

    def test_removes_tree(self, tmp_path):
        data = tmp_path / "data"
        data.mkdir()
        (data / "screenshots").mkdir()
        (data / "screenshots" / "img.png").write_bytes(b"\x89PNG")
        (data / "captures.db").write_text("db")

        remove_data_directory(str(data), secure_wipe=False)
        assert not data.exists()

    def test_secure_wipe_tree(self, tmp_path):
        data = tmp_path / "data"
        data.mkdir()
        (data / "secret.bin").write_bytes(b"\xff" * 100)

        remove_data_directory(str(data), secure_wipe=True)
        assert not data.exists()

    def test_nonexistent_dir(self, tmp_path):
        # Should not raise
        remove_data_directory(str(tmp_path / "nope"))


class TestRemoveLogFiles:
    """Tests for remove_log_files()."""

    def test_removes_log_and_dir(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        log_file = log_dir / "app.log"
        log_file.write_text("log data")

        remove_log_files(str(log_file), secure_wipe=False)
        assert not log_file.exists()
        assert not log_dir.exists()


class TestRemoveSqliteDatabase:
    """Tests for remove_sqlite_database()."""

    def test_removes_db_and_wal(self, tmp_path):
        db = tmp_path / "captures.db"
        wal = tmp_path / "captures.db-wal"
        shm = tmp_path / "captures.db-shm"
        db.write_text("db")
        wal.write_text("wal")
        shm.write_text("shm")

        remove_sqlite_database(str(db), secure_wipe=False)
        assert not db.exists()
        assert not wal.exists()
        assert not shm.exists()


class TestRemovePidFile:
    """Tests for remove_pid_file()."""

    def test_removes_pid(self, tmp_path):
        pid = tmp_path / "test.pid"
        pid.write_text("12345")
        remove_pid_file(str(pid))
        assert not pid.exists()

    def test_nonexistent_pid(self, tmp_path):
        remove_pid_file(str(tmp_path / "nope.pid"))


class TestUninstallService:
    """Tests for uninstall_service()."""

    def test_calls_service_manager(self):
        with mock.patch("service.ServiceManager") as MockSM:
            mock_instance = MockSM.return_value
            mock_instance.uninstall.return_value = "uninstalled"
            uninstall_service({"service": {"name": "test"}})
            MockSM.assert_called_once_with({"service": {"name": "test"}})
            mock_instance.uninstall.assert_called_once()

    def test_handles_exception(self):
        with mock.patch("service.ServiceManager", side_effect=RuntimeError("fail")):
            # Should not raise
            uninstall_service({})


class TestExecuteSelfDestruct:
    """Tests for execute_self_destruct() orchestration."""

    def test_calls_all_steps(self, tmp_path):
        config = {
            "general": {
                "data_dir": str(tmp_path / "data"),
                "log_file": str(tmp_path / "logs" / "app.log"),
            },
            "storage": {
                "sqlite_path": str(tmp_path / "data" / "captures.db"),
            },
        }
        with (
            mock.patch("utils.self_destruct.remove_data_directory") as m_data,
            mock.patch("utils.self_destruct.remove_log_files") as m_logs,
            mock.patch("utils.self_destruct.remove_sqlite_database") as m_db,
            mock.patch("utils.self_destruct.remove_pid_file") as m_pid,
            mock.patch("utils.self_destruct.uninstall_service") as m_svc,
            mock.patch("utils.self_destruct.remove_program_directory") as m_prog,
        ):
            execute_self_destruct(config, secure_wipe=True, remove_service=True, remove_program=True)

            m_data.assert_called_once_with(str(tmp_path / "data"), secure_wipe=True)
            m_logs.assert_called_once_with(str(tmp_path / "logs" / "app.log"), secure_wipe=True)
            m_db.assert_called_once_with(str(tmp_path / "data" / "captures.db"), secure_wipe=True)
            m_pid.assert_called_once()
            m_svc.assert_called_once_with(config)
            m_prog.assert_called_once()

    def test_skips_service_and_program(self, tmp_path):
        config = {"general": {}, "storage": {}}
        with (
            mock.patch("utils.self_destruct.remove_data_directory"),
            mock.patch("utils.self_destruct.remove_log_files"),
            mock.patch("utils.self_destruct.remove_sqlite_database"),
            mock.patch("utils.self_destruct.remove_pid_file"),
            mock.patch("utils.self_destruct.uninstall_service") as m_svc,
            mock.patch("utils.self_destruct.remove_program_directory") as m_prog,
        ):
            execute_self_destruct(config, remove_service=False, remove_program=False)
            m_svc.assert_not_called()
            m_prog.assert_not_called()
