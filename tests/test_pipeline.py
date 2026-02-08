"""Tests for middleware pipeline."""
from __future__ import annotations

from typing import Any

from pipeline.base_middleware import BaseMiddleware
from pipeline.context import PipelineContext
from pipeline.core import Pipeline
from pipeline.registry import register_middleware


@register_middleware("test_mw_a")
class MiddlewareA(BaseMiddleware):
    @property
    def name(self) -> str:
        return "test_mw_a"

    @property
    def order(self) -> int:
        return 20

    def process(self, event: dict[str, Any], context: PipelineContext):
        event.setdefault("steps", []).append("a")
        return event


@register_middleware("test_mw_b")
class MiddlewareB(BaseMiddleware):
    @property
    def name(self) -> str:
        return "test_mw_b"

    @property
    def order(self) -> int:
        return 10

    def process(self, event: dict[str, Any], context: PipelineContext):
        event.setdefault("steps", []).append("b")
        return event


@register_middleware("test_mw_drop")
class MiddlewareDrop(BaseMiddleware):
    @property
    def name(self) -> str:
        return "test_mw_drop"

    @property
    def order(self) -> int:
        return 5

    def process(self, event: dict[str, Any], context: PipelineContext):
        return None


def test_pipeline_ordering():
    config = {
        "pipeline": {
            "enabled": True,
            "middleware": [
                {"name": "test_mw_a", "enabled": True},
                {"name": "test_mw_b", "enabled": True},
            ],
        }
    }
    pipeline = Pipeline(config, system_info={})
    result = pipeline.process_event({"type": "test"})
    assert result is not None
    assert result["steps"] == ["b", "a"]


def test_pipeline_drops_event():
    config = {
        "pipeline": {
            "enabled": True,
            "middleware": [
                {"name": "test_mw_drop", "enabled": True},
                {"name": "test_mw_a", "enabled": True},
            ],
        }
    }
    pipeline = Pipeline(config, system_info={})
    result = pipeline.process_event({"type": "test"})
    assert result is None
