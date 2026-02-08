"""Integration-style tests for the capture -> bundle -> transport pipeline."""
from __future__ import annotations

import time
import io
import zipfile
from pathlib import Path

import pytest

from storage.sqlite_storage import SQLiteStorage
from utils.crypto import generate_key, key_to_base64


# Import helpers from main.py — this may fail in headless environments
# because capture/__init__.py tries to import pynput.
try:
    from main import (
        _apply_encryption,
        _build_report_bundle,
        _cleanup_files,
        _items_from_sqlite,
    )
    _MAIN_AVAILABLE = True
except ImportError:
    _MAIN_AVAILABLE = False

needs_main = pytest.mark.skipif(
    not _MAIN_AVAILABLE,
    reason="main.py imports require display server (pynput/Pillow)",
)


class DummyTransport:
    def __init__(self) -> None:
        self.sent = None

    def send(self, data: bytes, metadata: dict) -> bool:
        self.sent = (data, metadata)
        return True


@needs_main
def test_pipeline_bundle_encrypt_cleanup(tmp_path: Path):
    screenshot = tmp_path / "screenshot_0001.png"
    screenshot.write_bytes(b"fake-image-data")

    items = [
        {
            "type": "screenshot",
            "path": str(screenshot),
            "timestamp": time.time(),
            "size": screenshot.stat().st_size,
        }
    ]

    config = {
        "compression": {"enabled": True, "format": "zip"},
        "encryption": {"enabled": False, "key": ""},
    }
    sys_info = {"hostname": "test", "os": "test", "timestamp": "now"}

    bundle, meta, file_paths = _build_report_bundle(items, config, sys_info)
    assert meta["content_type"] == "application/zip"
    assert file_paths == [str(screenshot)]

    # Validate the bundle has our file inside (via zip inspection)
    with zipfile.ZipFile(io.BytesIO(bundle), "r") as zf:
        names = set(zf.namelist())
        assert "records.json" in names
        assert screenshot.name in names

    # Encryption step
    key = generate_key()
    config["encryption"]["enabled"] = True
    config["encryption"]["key"] = key_to_base64(key)
    encrypted, meta2 = _apply_encryption(bundle, meta, config, data_dir=str(tmp_path))
    assert encrypted != bundle
    assert meta2["filename"].endswith(".enc")

    # Transport receives data
    transport = DummyTransport()
    assert transport.send(encrypted, meta2) is True
    assert transport.sent is not None

    # Cleanup removes files
    _cleanup_files(file_paths)
    assert not screenshot.exists()


@needs_main
def test_pipeline_sqlite_roundtrip(tmp_path: Path):
    db_path = tmp_path / "test.db"
    db = SQLiteStorage(str(db_path))

    screenshot = tmp_path / "shot.png"
    screenshot.write_bytes(b"data")

    db.insert(
        capture_type="screenshot",
        data="",
        file_path=str(screenshot),
        file_size=screenshot.stat().st_size,
    )

    rows = db.get_pending(limit=10)
    items, ids = _items_from_sqlite(rows)
    assert len(items) == 1
    assert ids
    assert items[0]["path"] == str(screenshot)
    db.close()
