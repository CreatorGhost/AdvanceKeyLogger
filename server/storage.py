"""Storage helpers for decrypted payloads."""
from __future__ import annotations

import os
import stat as stat_module
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

_last_cleanup_ts = 0.0
_CLEANUP_INTERVAL = 30.0  # seconds between cleanup runs


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

    # Throttle cleanup to avoid O(n) filesystem scan on every request
    global _last_cleanup_ts
    now = time.time()
    if now - _last_cleanup_ts >= _CLEANUP_INTERVAL:
        _last_cleanup_ts = now
        cleanup_storage(base_dir, config)

    return filepath


def cleanup_storage(base_dir: Path, config: dict[str, Any]) -> None:
    retention_hours = config.get("retention_hours")
    max_storage_mb = config.get("max_storage_mb")

    if not retention_hours and not max_storage_mb:
        return

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
        entries: list[tuple[Path, float, int]] = []
        for p in base_dir.glob("payload_*"):
            try:
                st = p.stat()
                if not stat_module.S_ISREG(st.st_mode):
                    continue
                entries.append((p, st.st_mtime, st.st_size))
            except OSError:
                continue
        entries.sort(key=lambda e: e[1])
        total = sum(size for _, _, size in entries)
        for path, _, cached_size in entries:
            if total <= max_bytes:
                break
            try:
                path.unlink()
            except OSError:
                continue
            total -= cached_size
