"""Simple in-memory rate limiter."""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class RateWindow:
    start_ts: float
    count: int = 0


class RateLimiter:
    def __init__(self, limit_per_minute: int) -> None:
        self._limit = limit_per_minute
        self._windows: dict[str, RateWindow] = {}

    def allow(self, key: str) -> bool:
        if self._limit <= 0:
            return True
        now = time.time()
        window = self._windows.get(key)
        if window is None or now - window.start_ts >= 60:
            self._windows[key] = RateWindow(start_ts=now, count=1)
            return True
        window.count += 1
        return window.count <= self._limit
