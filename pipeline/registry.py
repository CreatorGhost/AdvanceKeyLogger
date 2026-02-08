"""
Middleware registry and decorator.
"""
from __future__ import annotations

from typing import Type

from pipeline.base_middleware import BaseMiddleware

_MIDDLEWARE_REGISTRY: dict[str, Type[BaseMiddleware]] = {}


def register_middleware(name: str):
    """Decorator to register a middleware by name."""

    def decorator(cls: Type[BaseMiddleware]) -> Type[BaseMiddleware]:
        if not issubclass(cls, BaseMiddleware):
            raise TypeError(f"{cls.__name__} must inherit from BaseMiddleware")
        _MIDDLEWARE_REGISTRY[name] = cls
        return cls

    return decorator


def get_middleware_class(name: str) -> Type[BaseMiddleware]:
    """Look up a registered middleware class by name."""
    if name not in _MIDDLEWARE_REGISTRY:
        available = ", ".join(sorted(_MIDDLEWARE_REGISTRY.keys()))
        raise ValueError(f"Unknown middleware: '{name}'. Available: {available}")
    return _MIDDLEWARE_REGISTRY[name]


def list_middleware() -> list[str]:
    """Return names of all registered middleware."""
    return sorted(_MIDDLEWARE_REGISTRY.keys())
