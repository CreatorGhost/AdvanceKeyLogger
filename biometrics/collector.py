"""
BiometricsCollector captures key down/up timing pairs.
"""
from __future__ import annotations

import threading
import time
from typing import Any


class BiometricsCollector:
    """Collects keystroke timing events for biometrics analysis."""

    def __init__(self, max_buffer: int = 10000) -> None:
        self._pending: dict[str, tuple[float, float | None]] = {}
        self._events: list[dict[str, Any]] = []
        self._last_release: float | None = None
        self._lock = threading.Lock()
        self._max_buffer = max_buffer

    def on_key_down(self, key: str, timestamp: float | None = None) -> None:
        ts = timestamp if timestamp is not None else time.time()
        with self._lock:
            flight_ms = None
            if self._last_release is not None:
                flight_ms = (ts - self._last_release) * 1000.0
            self._pending[key] = (ts, flight_ms)

    def on_key_up(self, key: str, timestamp: float | None = None) -> None:
        ts = timestamp if timestamp is not None else time.time()
        with self._lock:
            if key not in self._pending:
                return
            down_ts, flight_ms = self._pending.pop(key)
            dwell_ms = (ts - down_ts) * 1000.0
            event = {
                "type": "keystroke_timing",
                "key": key,
                "down_ts": down_ts,
                "up_ts": ts,
                "dwell_ms": dwell_ms,
                "flight_ms": flight_ms,
                "timestamp": ts,
            }
            self._events.append(event)
            self._last_release = ts
            if self._max_buffer > 0 and len(self._events) > self._max_buffer:
                self._events.pop(0)

    def collect(self) -> list[dict[str, Any]]:
        with self._lock:
            if not self._events:
                return []
            data = list(self._events)
            self._events.clear()
        return data
