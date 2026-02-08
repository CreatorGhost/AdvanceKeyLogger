"""
Middleware: Deduplicator
Drops duplicate events within a configured time window.
"""
from __future__ import annotations

import time
from typing import Any

from pipeline.base_middleware import BaseMiddleware, CaptureEvent
from pipeline.context import PipelineContext
from pipeline.registry import register_middleware


@register_middleware("deduplicator")
class Deduplicator(BaseMiddleware):
    @property
    def name(self) -> str:
        return "deduplicator"

    @property
    def order(self) -> int:
        return 30

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._window = float(self.config.get("window_seconds", 5))
        self._types = set(self.config.get("types", ["clipboard", "window"]))
        self._last_seen: dict[str, tuple[str, float]] = {}

    def process(self, event: CaptureEvent, context: PipelineContext) -> CaptureEvent | None:
        event_type = event.get("type", "")
        if event_type not in self._types:
            return event

        value = _extract_value(event)
        if value is None:
            return event

        now = time.time()
        last = self._last_seen.get(event_type)
        if last:
            last_value, last_time = last
            if value == last_value and (now - last_time) <= self._window:
                return None

        self._last_seen[event_type] = (value, now)
        return event


def _extract_value(event: CaptureEvent) -> str | None:
    if "data" in event and isinstance(event["data"], str):
        return event["data"]
    if "path" in event and isinstance(event["path"], str):
        return event["path"]
    return None
