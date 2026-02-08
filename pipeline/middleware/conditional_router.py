"""
Middleware: ConditionalRouter
Annotates events with a route based on type.
"""
from __future__ import annotations

from typing import Any

from pipeline.base_middleware import BaseMiddleware, CaptureEvent
from pipeline.context import PipelineContext
from pipeline.registry import register_middleware


@register_middleware("conditional_router")
class ConditionalRouter(BaseMiddleware):
    @property
    def name(self) -> str:
        return "conditional_router"

    @property
    def order(self) -> int:
        return 60

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._routes = self.config.get("routes", {})

    def process(self, event: CaptureEvent, context: PipelineContext) -> CaptureEvent:
        event_type = event.get("type", "")
        route = self._routes.get(event_type)
        if route:
            event["route"] = route
        return event
