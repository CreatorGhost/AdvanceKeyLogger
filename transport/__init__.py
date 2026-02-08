"""
Transport module plugin registry.

Register new transport modules with the @register_transport decorator:

    from transport import register_transport
    from transport.base import BaseTransport

    @register_transport("my_transport")
    class MyTransport(BaseTransport):
        ...

Then load the configured transport:

    from transport import create_transport
    transport = create_transport(config_dict)
"""
from __future__ import annotations

import logging
from typing import Any

from transport.base import BaseTransport

_TRANSPORT_REGISTRY: dict[str, type[BaseTransport]] = {}


def register_transport(name: str):
    """Decorator to register a transport plugin by name."""
    def decorator(cls: type[BaseTransport]) -> type[BaseTransport]:
        if not issubclass(cls, BaseTransport):
            raise TypeError(f"{cls.__name__} must inherit from BaseTransport")
        _TRANSPORT_REGISTRY[name] = cls
        return cls
    return decorator


def get_transport_class(name: str) -> type[BaseTransport]:
    """Look up a registered transport class by name."""
    if name not in _TRANSPORT_REGISTRY:
        available = ", ".join(sorted(_TRANSPORT_REGISTRY.keys()))
        raise ValueError(f"Unknown transport: '{name}'. Available: {available}")
    return _TRANSPORT_REGISTRY[name]


def list_transports() -> list[str]:
    """Return names of all registered transport modules."""
    return sorted(_TRANSPORT_REGISTRY.keys())


def create_transport(config: dict[str, Any]) -> BaseTransport:
    """
    Instantiate the transport module specified in config.

    Args:
        config: Full config dict. Expects:
            transport:
              method: "email"
              email:
                smtp_server: ...

    Returns:
        An instantiated transport module.
    """
    transport_config = config.get("transport", {})
    method = transport_config.get("method", "email")
    method_config = transport_config.get(method, {})

    cls = get_transport_class(method)
    return cls(method_config)


def create_transport_for_method(config: dict[str, Any], method: str) -> BaseTransport:
    """Instantiate a transport module for a specific method."""
    transport_config = config.get("transport", {})
    method_config = transport_config.get(method, {})
    cls = get_transport_class(method)
    return cls(method_config)


# Import built-in transport modules so they self-register.
logger = logging.getLogger(__name__)

for _module in (
    "email_transport",
    "http_transport",
    "ftp_transport",
    "telegram_transport",
):
    try:
        __import__(f"{__name__}.{_module}")
    except Exception as exc:  # pragma: no cover - optional deps/platforms
        logger.debug("Transport module '%s' not loaded: %s", _module, exc)
