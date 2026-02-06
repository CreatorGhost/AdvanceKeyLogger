"""
Capture module plugin registry.

Register new capture modules with the @register_capture decorator:

    from capture import register_capture
    from capture.base import BaseCapture

    @register_capture("my_capture")
    class MyCapture(BaseCapture):
        ...

Then load enabled captures from config:

    from capture import create_enabled_captures
    captures = create_enabled_captures(config_dict)
"""
from __future__ import annotations

from typing import Any

from capture.base import BaseCapture

_CAPTURE_REGISTRY: dict[str, type[BaseCapture]] = {}


def register_capture(name: str):
    """Decorator to register a capture plugin by name."""
    def decorator(cls: type[BaseCapture]) -> type[BaseCapture]:
        if not issubclass(cls, BaseCapture):
            raise TypeError(f"{cls.__name__} must inherit from BaseCapture")
        _CAPTURE_REGISTRY[name] = cls
        return cls
    return decorator


def get_capture_class(name: str) -> type[BaseCapture]:
    """Look up a registered capture class by name."""
    if name not in _CAPTURE_REGISTRY:
        available = ", ".join(sorted(_CAPTURE_REGISTRY.keys()))
        raise ValueError(f"Unknown capture: '{name}'. Available: {available}")
    return _CAPTURE_REGISTRY[name]


def list_captures() -> list[str]:
    """Return names of all registered capture modules."""
    return sorted(_CAPTURE_REGISTRY.keys())


def create_enabled_captures(config: dict[str, Any]) -> list[BaseCapture]:
    """
    Instantiate all capture modules that are enabled in the config.

    Args:
        config: The full config dict (expects a "capture" key with sub-keys
                for each module, each having an "enabled" boolean).

    Returns:
        List of instantiated capture modules.

    Example config:
        capture:
          keyboard:
            enabled: true
          screenshot:
            enabled: true
            quality: 80
    """
    captures: list[BaseCapture] = []
    capture_config = config.get("capture", {})

    for name, settings in capture_config.items():
        if isinstance(settings, dict) and settings.get("enabled", False):
            try:
                cls = get_capture_class(name)
                captures.append(cls(settings))
            except ValueError:
                pass

    return captures
