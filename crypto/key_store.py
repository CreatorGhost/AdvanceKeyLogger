"""
Simple filesystem key store for E2E keys.
"""
from __future__ import annotations

import base64
import contextlib
import json
import os
import tempfile
from pathlib import Path

_suppress_oserror = contextlib.suppress(OSError)


class KeyStore:
    """Persist keys as base64-encoded files with restrictive permissions."""

    def __init__(self, base_path: str) -> None:
        self._base_path = Path(base_path).expanduser()
        self._base_path.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self._base_path, 0o700)
        except OSError:
            pass

    def load_bytes(self, name: str) -> bytes | None:
        path = self._path(name)
        if not path.exists():
            return None
        data = path.read_text(encoding="utf-8").strip()
        if not data:
            return None
        return base64.b64decode(data.encode("utf-8"))

    def save_bytes(self, name: str, data: bytes) -> None:
        path = self._path(name)
        encoded = base64.b64encode(data).decode("utf-8")
        # Atomic write: write to temp file, fsync, then rename
        dir_fd = None
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self._base_path), prefix=f".{name}_", suffix=".tmp"
        )
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                # fd is now owned by handle; do not close fd separately
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.rename(tmp_path, str(path))
            # fsync the directory to ensure the rename is durable
            try:
                dir_fd = os.open(str(self._base_path), os.O_RDONLY)
                os.fsync(dir_fd)
            except OSError:
                pass
        except BaseException:
            with _suppress_oserror:
                os.unlink(tmp_path)
            raise
        finally:
            if dir_fd is not None:
                with _suppress_oserror:
                    os.close(dir_fd)

    def load_json(self, name: str) -> dict | None:
        path = self._json_path(name)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def save_json(self, name: str, data: dict) -> None:
        path = self._json_path(name)
        # Atomic write: write to temp file, fsync, then rename
        dir_fd = None
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self._base_path), prefix=f".{name}_", suffix=".tmp"
        )
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=True, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.rename(tmp_path, str(path))
            try:
                dir_fd = os.open(str(self._base_path), os.O_RDONLY)
                os.fsync(dir_fd)
            except OSError:
                pass
        except BaseException:
            with _suppress_oserror:
                os.unlink(tmp_path)
            raise
        finally:
            if dir_fd is not None:
                with _suppress_oserror:
                    os.close(dir_fd)

    def _path(self, name: str) -> Path:
        filename = f"{name}.key"
        return self._base_path / filename

    def _json_path(self, name: str) -> Path:
        filename = f"{name}.json"
        return self._base_path / filename
