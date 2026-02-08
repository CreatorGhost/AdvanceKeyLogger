"""Storage helpers for decrypted payloads."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def detect_extension(payload: bytes) -> str:
    if payload.startswith(b"{") or payload.startswith(b"["):
        return ".json"
    if payload.startswith(b"PK\x03\x04"):
        return ".zip"
    if payload.startswith(b"\x1f\x8b"):
        return ".gz"
    return ".bin"


def store_payload(payload: bytes, config: dict[str, Any]) -> Path:
    base_dir = Path(str(config.get("storage_dir", "./server_data"))).expanduser()
    base_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    ext = detect_extension(payload)
    filename = f"payload_{timestamp}{ext}"
    filepath = base_dir / filename
    filepath.write_bytes(payload)

    try:
        os.chmod(filepath, 0o600)
    except OSError:
        pass

    return filepath
