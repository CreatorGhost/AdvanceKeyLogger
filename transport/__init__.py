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
