"""
Plugin system for extending capture, transport, and pipeline capabilities.

Plugins are Python packages or single-file modules that register new components
using the existing ``@register_capture``, ``@register_transport``, or
``@register_middleware`` decorators.

Discovery modes:
1. **Directory-based** — drop a ``.py`` file or package into ``plugins/``
2. **Entry-point-based** — install a pip package with an ``advkl.plugins``
   entry point group
3. **Config-based** — list plugin module paths under ``plugins.load`` in the
   YAML config

Usage::

    from plugins import PluginManager

    pm = PluginManager(config)
    pm.discover()   # scan all sources
    pm.load_all()   # import and register
"""

from __future__ import annotations

import importlib
import importlib.metadata
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "advkl.plugins"
_PLUGINS_DIR = Path(__file__).parent


class PluginInfo:
    """Metadata for a discovered plugin."""

    __slots__ = ("name", "module_path", "source", "loaded", "error")

    def __init__(self, name: str, module_path: str, source: str) -> None:
        self.name = name
        self.module_path = module_path
        self.source = source  # "directory" | "entrypoint" | "config"
        self.loaded = False
        self.error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "module_path": self.module_path,
            "source": self.source,
            "loaded": self.loaded,
            "error": self.error,
        }


class PluginManager:
    """Discover, load, and manage plugins from multiple sources."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._plugins: dict[str, PluginInfo] = {}

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> list[PluginInfo]:
        """Run all discovery methods and return the combined list."""
        self._discover_directory()
        self._discover_entrypoints()
        self._discover_config()
        return list(self._plugins.values())

    def _discover_directory(self) -> None:
        """Scan the ``plugins/`` directory for .py files and packages."""
        if not _PLUGINS_DIR.is_dir():
            return
        for item in sorted(_PLUGINS_DIR.iterdir()):
            if item.name.startswith("_"):
                continue
            if item.is_file() and item.suffix == ".py":
                mod_name = f"plugins.{item.stem}"
                self._register(item.stem, mod_name, "directory")
            elif item.is_dir() and (item / "__init__.py").exists():
                mod_name = f"plugins.{item.name}"
                self._register(item.name, mod_name, "directory")

    def _discover_entrypoints(self) -> None:
        """Discover plugins registered via pip entry points."""
        try:
            eps = importlib.metadata.entry_points()
            # Python 3.12+ returns a SelectableGroups / dict
            group = eps.get(ENTRY_POINT_GROUP, []) if isinstance(eps, dict) else (
                eps.select(group=ENTRY_POINT_GROUP)
                if hasattr(eps, "select")
                else []
            )
            for ep in group:
                # ep.value may contain "module:Attr"; split to get the module
                # portion so import_module in _load_one doesn't choke.
                module_path = ep.value.split(":")[0] if ":" in ep.value else ep.value
                self._register(ep.name, module_path, "entrypoint")
        except Exception as exc:
            logger.debug("Entry-point discovery failed: %s", exc)

    def _discover_config(self) -> None:
        """Load plugin paths from ``plugins.load`` config list."""
        paths = self._config.get("plugins", {}).get("load", [])
        for path in paths:
            name = path.rsplit(".", 1)[-1]
            self._register(name, path, "config")

    def _register(self, name: str, module_path: str, source: str) -> None:
        if name not in self._plugins:
            self._plugins[name] = PluginInfo(name, module_path, source)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_all(self) -> int:
        """Import all discovered plugins.  Returns the number loaded."""
        loaded = 0
        for info in self._plugins.values():
            if info.loaded:
                loaded += 1
                continue
            if self._load_one(info):
                loaded += 1
        logger.info(
            "Plugins: %d/%d loaded successfully", loaded, len(self._plugins)
        )
        return loaded

    def load(self, name: str) -> bool:
        """Load a single plugin by name."""
        info = self._plugins.get(name)
        if info is None:
            logger.warning("Plugin '%s' not found", name)
            return False
        return self._load_one(info)

    def _load_one(self, info: PluginInfo) -> bool:
        try:
            importlib.import_module(info.module_path)
            info.loaded = True
            info.error = None
            logger.info("Loaded plugin '%s' from %s (%s)", info.name, info.module_path, info.source)
            return True
        except Exception as exc:
            info.error = str(exc)
            logger.error("Failed to load plugin '%s': %s", info.name, exc)
            return False

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def plugins(self) -> dict[str, PluginInfo]:
        return dict(self._plugins)

    def list_plugins(self) -> list[dict[str, Any]]:
        """Return serialisable list of all known plugins."""
        return [p.to_dict() for p in self._plugins.values()]

    def is_loaded(self, name: str) -> bool:
        info = self._plugins.get(name)
        return info.loaded if info else False
