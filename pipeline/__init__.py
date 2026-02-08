"""
Middleware pipeline package.

Provides a configurable chain of middleware for capture events.
"""
from __future__ import annotations

import logging

from pipeline.core import Pipeline
from pipeline.registry import register_middleware, get_middleware_class, list_middleware

logger = logging.getLogger(__name__)

# Auto-import built-in middleware modules for registration.
for _module in (
    "middleware.timestamp_enricher",
    "middleware.context_annotator",
    "middleware.deduplicator",
    "middleware.content_truncator",
    "middleware.rate_limiter",
    "middleware.conditional_router",
    "middleware.metrics_emitter",
):
    try:
        __import__(f"{__name__}.{_module}")
    except Exception as exc:  # pragma: no cover
        logger.debug("Middleware module '%s' not loaded: %s", _module, exc)

__all__ = [
    "Pipeline",
    "register_middleware",
    "get_middleware_class",
    "list_middleware",
]
