"""Client allowlist and registration."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


class ClientRegistry:
    def __init__(self, allowed_keys: Iterable[str], clients_file: str | None) -> None:
        self._clients_file = Path(clients_file).expanduser() if clients_file else None
        self._allowed = {key.strip() for key in allowed_keys if key}
        if self._clients_file:
            self._load_from_file()

    def is_allowed(self, key_b64: str) -> bool:
        if not self._allowed:
            return True
        return key_b64 in self._allowed

    def register(self, key_b64: str) -> None:
        if key_b64:
            self._allowed.add(key_b64)
            self._save_to_file()

    def list_keys(self) -> list[str]:
        return sorted(self._allowed)

    def _load_from_file(self) -> None:
        if not self._clients_file or not self._clients_file.exists():
            return
        try:
            data = json.loads(self._clients_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        keys = data.get("allowed_keys", []) if isinstance(data, dict) else data
        for key in keys or []:
            if isinstance(key, str):
                self._allowed.add(key)

    def _save_to_file(self) -> None:
        if not self._clients_file:
            return
        self._clients_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {"allowed_keys": sorted(self._allowed)}
        self._clients_file.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
