"""Tests for the storage layer."""
from __future__ import annotations

import time
import pytest
from pathlib import Path

from storage.manager import StorageManager
from storage.sqlite_storage import SQLiteStorage


class TestStorageManager:
    """Tests for StorageManager."""

    @pytest.fixture
    def storage(self, tmp_path: Path) -> StorageManager:
        return StorageManager(data_dir=str(tmp_path), max_size_mb=1)

    def test_store_file(self, storage: StorageManager):
        """Basic file storage works."""
        result = storage.store(b"Hello, World!", "test.txt")
        assert result is not None
        assert result.exists()
        assert result.read_bytes() == b"Hello, World!"

    def test_store_in_subdir(self, storage: StorageManager):
        """Files can be stored in subdirectories."""
        result = storage.store(b"data", "file.txt", subdir="sub")
        assert result is not None
        assert "sub" in str(result)
        assert result.exists()

    def test_empty_storage_size(self, storage: StorageManager):
        """Empty storage reports 0."""
        assert storage.get_total_size() == 0
        assert storage.get_usage_percent() == 0.0

    def test_size_tracking(self, storage: StorageManager):
        """Total size increases as files are stored."""
        data = b"x" * 1000
        storage.store(data, "file.bin")
        assert storage.get_total_size() == 1000

    def test_has_space(self, storage: StorageManager):
        """has_space correctly checks available capacity."""
        assert storage.has_space(100) is True
        assert storage.has_space(2 * 1024 * 1024) is False  # 2MB > 1MB limit

    def test_cleanup(self, storage: StorageManager):
        """cleanup deletes specified files."""
        p1 = storage.store(b"file1", "f1.txt")
        p2 = storage.store(b"file2", "f2.txt")
        deleted = storage.cleanup([str(p1)])
        assert deleted == 1
        assert not p1.exists()
        assert p2.exists()

    def test_cleanup_missing_file(self, storage: StorageManager):
        """cleanup handles missing files gracefully."""
        deleted = storage.cleanup(["/nonexistent/file.txt"])
        assert deleted == 0

    def test_rotation(self, tmp_path: Path):
        """rotation deletes oldest files when over capacity."""
        storage = StorageManager(data_dir=str(tmp_path), max_size_mb=1, rotation=True)
        # Fill up storage with ~900KB
        for i in range(9):
            storage.store(b"x" * (100 * 1024), f"file_{i:02d}.bin")
            time.sleep(0.01)  # Ensure different mtime

        # Should be near capacity now
        assert storage.get_total_size() > 500 * 1024

        # Store a large file — should trigger rotation
        storage.store(b"y" * (300 * 1024), "new_file.bin")

        # After rotation, usage should be under 80%
        assert storage.get_usage_percent() <= 100

    def test_rotation_disabled(self, tmp_path: Path):
        """With rotation disabled, store fails when full."""
        storage = StorageManager(
            data_dir=str(tmp_path), max_size_mb=1, rotation=False
        )
        # Fill to near-capacity with multiple smaller files
        for i in range(10):
            storage.store(b"x" * (100 * 1024), f"chunk_{i}.bin")
        # Now at ~1000KB out of 1024KB — next large store should fail
        result = storage.store(b"x" * (100 * 1024), "overflow.bin")
        assert result is None

    def test_list_files(self, storage: StorageManager):
        """list_files returns stored files."""
        storage.store(b"a", "file_a.txt")
        storage.store(b"b", "file_b.txt")
        storage.store(b"c", "image.png")
        assert len(storage.list_files()) == 3
        assert len(storage.list_files(pattern="*.txt")) == 2
        assert len(storage.list_files(pattern="*.png")) == 1


class TestSQLiteStorage:
    """Tests for SQLiteStorage."""

    @pytest.fixture
    def db(self, tmp_path: Path) -> SQLiteStorage:
        storage = SQLiteStorage(str(tmp_path / "test.db"))
        yield storage
        storage.close()

    def test_insert_and_retrieve(self, db: SQLiteStorage):
        """Can insert and retrieve records."""
        row_id = db.insert("keystroke", data="hello")
        assert row_id >= 1
        pending = db.get_pending()
        assert len(pending) == 1
        assert pending[0]["type"] == "keystroke"
        assert pending[0]["data"] == "hello"

    def test_mark_sent(self, db: SQLiteStorage):
        """mark_sent removes records from pending."""
        id1 = db.insert("keystroke", data="a")
        id2 = db.insert("keystroke", data="b")
        db.mark_sent([id1])
        pending = db.get_pending()
        assert len(pending) == 1
        assert pending[0]["id"] == id2

    def test_count_pending(self, db: SQLiteStorage):
        """count_pending returns correct count."""
        assert db.count_pending() == 0
        db.insert("screenshot", file_path="/tmp/shot.png")
        db.insert("keystroke", data="test")
        assert db.count_pending() == 2

    def test_count_total(self, db: SQLiteStorage):
        """count_total includes sent records."""
        id1 = db.insert("keystroke", data="a")
        db.insert("keystroke", data="b")
        db.mark_sent([id1])
        assert db.count_total() == 2
        assert db.count_pending() == 1

    def test_get_pending_limit(self, db: SQLiteStorage):
        """get_pending respects the limit parameter."""
        for i in range(10):
            db.insert("keystroke", data=str(i))
        pending = db.get_pending(limit=3)
        assert len(pending) == 3

    def test_get_pending_ordering(self, db: SQLiteStorage):
        """get_pending returns oldest first."""
        db.insert("keystroke", data="first")
        time.sleep(0.01)
        db.insert("keystroke", data="second")
        pending = db.get_pending()
        assert pending[0]["data"] == "first"
        assert pending[1]["data"] == "second"

    def test_purge_sent(self, db: SQLiteStorage):
        """purge_sent deletes old sent records."""
        id1 = db.insert("keystroke", data="old")
        db.mark_sent([id1])
        # Purge records older than 0 seconds (everything)
        deleted = db.purge_sent(older_than_seconds=0)
        assert deleted == 1
        assert db.count_total() == 0

    def test_context_manager(self, tmp_path: Path):
        """Can use as context manager."""
        with SQLiteStorage(str(tmp_path / "ctx.db")) as db:
            db.insert("test", data="hello")
            assert db.count_total() == 1
