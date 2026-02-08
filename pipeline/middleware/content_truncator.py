"""
Middleware: ContentTruncator
Truncates overly long string payloads.
"""
from __future__ import annotations

from typing import Any

from pipeline.base_middleware import BaseMiddleware, CaptureEvent
from pipeline.context import PipelineContext
from pipeline.registry import register_middleware


@register_middleware("content_truncator")
class ContentTruncator(BaseMiddleware):
    @property
    def name(self) -> str:
        return "content_truncator"

    @property
    def order(self) -> int:
        return 40

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._default_max = int(self.config.get("default_max_length", 10_000))
        self._per_type = self.config.get("max_length_by_type", {})

    def process(self, event: CaptureEvent, context: PipelineContext) -> CaptureEvent:
        if "data" not in event or not isinstance(event["data"], str):
            return event

        event_type = event.get("type", "")
        limit = int(self._per_type.get(event_type, self._default_max))
        if limit > 0 and len(event["data"]) > limit:
            event["data"] = event["data"][:limit] + "...[truncated]"
        return event
