"""
Base middleware interface for capture event pipeline.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from pipeline.context import PipelineContext

CaptureEvent = dict[str, Any]


class MiddlewareError(RuntimeError):
    """Raised when a middleware fails and should halt processing."""


class BaseMiddleware(ABC):
    """All middleware must implement this interface."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    @abstractmethod
    def process(
        self,
        event: CaptureEvent,
        context: PipelineContext,
    ) -> Optional[CaptureEvent]:
        """
        Process a capture event.

        Return the event (possibly modified) to pass it downstream.
        Return None to drop the event.
        Raise MiddlewareError to halt the pipeline.
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique middleware name."""

    @property
    def order(self) -> int:
        """Execution order (lower runs earlier)."""
        return 50
