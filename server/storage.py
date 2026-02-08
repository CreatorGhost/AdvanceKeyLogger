"""Storage helpers for decrypted payloads."""
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
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

    cleanup_storage(base_dir, config)
    return filepath


def cleanup_storage(base_dir: Path, config: dict[str, Any]) -> None:
    retention_hours = config.get("retention_hours")
    max_storage_mb = config.get("max_storage_mb")

    files = [p for p in base_dir.glob("payload_*") if p.is_file()]
    if retention_hours:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=float(retention_hours))
        for path in files:
            try:
                if datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) < cutoff:
                    path.unlink()
            except OSError:
                continue

    if max_storage_mb:
        max_bytes = float(max_storage_mb) * 1024 * 1024
        files = [p for p in base_dir.glob("payload_*") if p.is_file()]
        files_sorted = sorted(files, key=lambda p: p.stat().st_mtime)
        total = sum(p.stat().st_size for p in files_sorted)
        while total > max_bytes and files_sorted:
            oldest = files_sorted.pop(0)
            try:
                size = oldest.stat().st_size
                oldest.unlink()
                total -= size
            except OSError:
                break
