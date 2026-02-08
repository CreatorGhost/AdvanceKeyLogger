"""
Middleware: TimestampEnricher
Adds high-precision timestamps and timezone info.
"""
from __future__ import annotations

from datetime import datetime, timezone

from pipeline.base_middleware import BaseMiddleware, CaptureEvent
from pipeline.context import PipelineContext
from pipeline.registry import register_middleware


@register_middleware("timestamp_enricher")
class TimestampEnricher(BaseMiddleware):
    @property
    def name(self) -> str:
        return "timestamp_enricher"

    @property
    def order(self) -> int:
        return 10

    def process(self, event: CaptureEvent, context: PipelineContext) -> CaptureEvent:
        now = datetime.now(timezone.utc)
        event.setdefault("timestamp", now.timestamp())
        event["timestamp_iso"] = now.isoformat()
        event["timestamp_ns"] = now.timestamp_ns()
        event["timezone"] = "UTC"
        return event
