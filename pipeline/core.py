"""
Pipeline executor for capture events.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

from pipeline.base_middleware import BaseMiddleware, MiddlewareError, CaptureEvent
from pipeline.context import PipelineContext
from pipeline.registry import get_middleware_class

logger = logging.getLogger(__name__)


class Pipeline:
    """Execute an ordered middleware chain against capture events."""

    def __init__(self, config: dict[str, Any], system_info: dict[str, Any]) -> None:
        self._config = config
        self._pipeline_config = config.get("pipeline", {})
        self._middlewares: list[BaseMiddleware] = []
        self._context = PipelineContext(config=config, system_info=system_info)
        self._build_middleware()

    @property
    def context(self) -> PipelineContext:
        return self._context

    def _build_middleware(self) -> None:
        middleware_configs = self._pipeline_config.get("middleware", [])
        instances: list[BaseMiddleware] = []
        for entry in middleware_configs:
            if not entry or not isinstance(entry, dict):
                continue
            name = entry.get("name")
            enabled = entry.get("enabled", True)
            if not name or not enabled:
                continue
            cfg = entry.get("config", {}) or {}
            try:
                cls = get_middleware_class(name)
                instances.append(cls(cfg))
            except Exception as exc:
                logger.warning("Failed to load middleware '%s': %s", name, exc)

        # Sort by middleware.order; keep config order as tie-breaker
        self._middlewares = sorted(instances, key=lambda m: m.order)
        logger.info("Pipeline middleware: %s", [m.name for m in self._middlewares])

    def process_event(self, event: CaptureEvent) -> CaptureEvent | None:
        current = event
        for middleware in self._middlewares:
            try:
                current = middleware.process(current, self._context)
            except MiddlewareError as exc:
                logger.error("Middleware error in %s: %s", middleware.name, exc)
                self._context.inc("dropped")
                return None
            except Exception as exc:
                logger.error("Middleware %s crashed: %s", middleware.name, exc)
                self._context.inc("dropped")
                return None

            if current is None:
                self._context.inc("dropped")
                return None

        self._context.inc("processed")
        return current

    def process_batch(self, events: Iterable[CaptureEvent]) -> list[CaptureEvent]:
        output: list[CaptureEvent] = []
        for event in events:
            processed = self.process_event(event)
            if processed is not None:
                output.append(processed)
        return output
