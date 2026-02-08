"""Replay protection for envelopes."""
from __future__ import annotations

import threading
import time


class ReplayCache:
    def __init__(self, ttl_seconds: int = 3600, max_entries: int = 10000) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()

    def seen(self, envelope_id: str) -> bool:
        now = time.time()
        with self._lock:
            self._purge(now)
            if envelope_id in self._seen:
                return True
            if len(self._seen) >= self._max_entries:
                self._purge(now, force=True)
            self._seen[envelope_id] = now
            return False

    def _purge(self, now: float, force: bool = False) -> None:
        if not self._seen:
            return
        cutoff = now - self._ttl
        to_delete = [k for k, ts in self._seen.items() if ts < cutoff]
        for key in to_delete:
            self._seen.pop(key, None)
        if force and self._seen:
            # Drop oldest entries to free space
            sorted_items = sorted(self._seen.items(), key=lambda item: item[1])
            for key, _ in sorted_items[: max(1, len(sorted_items) // 3)]:
                self._seen.pop(key, None)
