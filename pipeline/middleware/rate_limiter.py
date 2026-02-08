"""
Middleware: RateLimiter
Throttles high-frequency events by type.
"""
from __future__ import annotations

import time
from typing import Any

from pipeline.base_middleware import BaseMiddleware, CaptureEvent
from pipeline.context import PipelineContext
from pipeline.registry import register_middleware


@register_middleware("rate_limiter")
class RateLimiter(BaseMiddleware):
    @property
    def name(self) -> str:
        return "rate_limiter"

    @property
    def order(self) -> int:
        return 50

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._max_eps = int(self.config.get("max_events_per_second", 50))
        self._by_type = self.config.get("by_type", {})
        self._window_start = time.time()
        self._counts: dict[str, int] = {}

    def process(self, event: CaptureEvent, context: PipelineContext) -> CaptureEvent | None:
        now = time.time()
        if now - self._window_start >= 1.0:
            self._window_start = now
            self._counts.clear()

        event_type = event.get("type", "unknown")
        limit = int(self._by_type.get(event_type, self._max_eps))
        count = self._counts.get(event_type, 0) + 1
        self._counts[event_type] = count

        if limit > 0 and count > limit:
            return None
        return event
