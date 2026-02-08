"""Client allowlist and registration."""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)


class ClientRegistry:
    def __init__(self, allowed_keys: Iterable[str], clients_file: str | None) -> None:
        self._clients_file = Path(clients_file).expanduser() if clients_file else None
        self._allowed = {key.strip() for key in allowed_keys if key}
        self._lock = threading.Lock()
        if self._clients_file:
            self._load_from_file()

    def is_allowed(self, key_b64: str) -> bool:
        with self._lock:
            if not self._allowed:
                return True
            return key_b64 in self._allowed

    def register(self, key_b64: str) -> None:
        if key_b64:
            with self._lock:
                self._allowed.add(key_b64)
                self._save_to_file()

    def list_keys(self) -> list[str]:
        with self._lock:
            return sorted(self._allowed)

    def _load_from_file(self) -> None:
        if not self._clients_file or not self._clients_file.exists():
            return
        try:
            data = json.loads(self._clients_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        raw_keys = data.get("allowed_keys", []) if isinstance(data, dict) else data
        if not isinstance(raw_keys, list):
            logger.warning("clients file has invalid allowed_keys type, expected list")
            return
        for key in raw_keys:
            if isinstance(key, str) and key.strip():
                self._allowed.add(key.strip())

    def _save_to_file(self) -> None:
        if not self._clients_file:
            return
        self._clients_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {"allowed_keys": sorted(self._allowed)}
        self._clients_file.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
