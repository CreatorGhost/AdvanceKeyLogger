"""
Simple filesystem key store for E2E keys.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path


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
        fd = os.open(str(path), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        fd_owned = True
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                fd_owned = False
                handle.write(encoded)
        finally:
            if fd_owned:
                try:
                    os.close(fd)
                except OSError:
                    pass

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
        fd = os.open(str(path), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        fd_owned = True
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                fd_owned = False
                json.dump(data, handle, ensure_ascii=True, indent=2)
        finally:
            if fd_owned:
                try:
                    os.close(fd)
                except OSError:
                    pass

    def _path(self, name: str) -> Path:
        filename = f"{name}.key"
        return self._base_path / filename

    def _json_path(self, name: str) -> Path:
        filename = f"{name}.json"
        return self._base_path / filename
