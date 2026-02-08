"""
Middleware: MetricsEmitter
Emits pipeline throughput metrics periodically.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from pipeline.base_middleware import BaseMiddleware, CaptureEvent
from pipeline.context import PipelineContext
from pipeline.registry import register_middleware

logger = logging.getLogger(__name__)


@register_middleware("metrics_emitter")
class MetricsEmitter(BaseMiddleware):
    @property
    def name(self) -> str:
        return "metrics_emitter"

    @property
    def order(self) -> int:
        return 99

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._interval = float(self.config.get("log_interval_seconds", 60))
        self._last_log = time.time()

    def process(self, event: CaptureEvent, context: PipelineContext) -> CaptureEvent:
        now = time.time()
        if now - self._last_log >= self._interval:
            processed = context.metrics.get("processed", 0)
            dropped = context.metrics.get("dropped", 0)
            logger.info(
                "Pipeline metrics: processed=%d dropped=%d uptime=%.1fs",
                processed,
                dropped,
                now - context.start_time,
            )
            self._last_log = now
        return event
