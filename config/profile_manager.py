"""
Configuration Profiles — named, inheritable config presets.

Profiles are YAML files stored in ``config/profiles/`` or defined inline
in the main config under ``profiles``.  Each profile is a partial config
dict that is deep-merged onto the base config when activated.

Features:
  * Named profiles (``low_power``, ``stealth``, ``full_capture``, …)
  * Inheritance — a profile can declare ``extends: "parent_name"``
  * Validation against the running config keys
  * Import/export as standalone YAML files
  * Fleet integration — profiles can be pushed to agents via fleet commands

Example config::

    profiles:
      low_power:
        description: "Reduced capture for battery savings"
        capture:
          screenshot:
            enabled: false
          audio:
            enabled: false
        adaptive:
          base_interval: 5.0

      stealth:
        extends: low_power
        description: "Minimal footprint"
        capture:
          clipboard:
            enabled: false
        resources:
          cpu_limit: 10
"""

from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Recursively merge *overlay* into *base* (non-destructive)."""
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


class Profile:
    """A named configuration overlay."""

    __slots__ = ("name", "description", "extends", "overrides")

    def __init__(
        self,
        name: str,
        overrides: dict[str, Any],
        description: str = "",
        extends: str | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.extends = extends
        self.overrides = overrides

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"name": self.name, "description": self.description}
        if self.extends:
            d["extends"] = self.extends
        d["overrides"] = self.overrides
        return d


class ProfileManager:
    """Manage named configuration profiles with inheritance.

    Parameters
    ----------
    base_config:
        The full default configuration dict (before any profile overlay).
    profiles_config:
        The ``profiles`` section from the config file (dict of profile dicts).
    profiles_dir:
        Optional directory containing ``<name>.yaml`` profile files.
    """

    def __init__(
        self,
        base_config: dict[str, Any],
        profiles_config: dict[str, Any] | None = None,
        profiles_dir: str | Path | None = None,
    ) -> None:
        self._base = copy.deepcopy(base_config)
        self._profiles: dict[str, Profile] = {}
        self._active: str | None = None

        # Load inline profiles
        for name, pcfg in (profiles_config or {}).items():
            self._load_profile(name, pcfg)

        # Load file-based profiles
        if profiles_dir:
            self._load_directory(Path(profiles_dir))

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_profile(self, name: str, raw: dict[str, Any]) -> Profile:
        data = dict(raw)  # shallow copy to avoid mutating the caller's dict
        extends = data.pop("extends", None)
        description = data.pop("description", "")
        profile = Profile(
            name=name,
            overrides=data,
            description=description,
            extends=extends,
        )
        self._profiles[name] = profile
        logger.debug("Loaded profile '%s' (extends=%s)", name, extends)
        return profile

    def _load_directory(self, path: Path) -> None:
        if not path.is_dir():
            return
        try:
            import yaml
        except ImportError:
            logger.warning("PyYAML not installed — cannot load profile files")
            return

        for fp in sorted(path.glob("*.yaml")):
            try:
                with open(fp, encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                name = fp.stem
                self._load_profile(name, data)
            except Exception as exc:
                logger.error("Failed to load profile '%s': %s", fp, exc)

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def resolve(self, name: str) -> dict[str, Any]:
        """Resolve a profile to a full config dict (with inheritance).

        Raises ``KeyError`` if the profile doesn't exist.
        """
        profile = self._profiles.get(name)
        if profile is None:
            raise KeyError(f"Unknown profile: '{name}'")

        # Build inheritance chain (depth-limited to prevent cycles)
        chain: list[Profile] = []
        seen: set[str] = set()
        current: Profile | None = profile
        while current is not None:
            if current.name in seen:
                raise ValueError(
                    f"Circular profile inheritance detected: {current.name}"
                )
            seen.add(current.name)
            chain.append(current)
            if current.extends:
                current = self._profiles.get(current.extends)
                if current is None:
                    raise KeyError(
                        f"Profile '{profile.name}' extends unknown profile "
                        f"'{chain[-1].extends}'"
                    )
            else:
                current = None

        # Apply chain in reverse (ancestor first)
        result = copy.deepcopy(self._base)
        for p in reversed(chain):
            result = _deep_merge(result, p.overrides)

        return result

    def apply(self, name: str) -> dict[str, Any]:
        """Resolve and set *name* as the active profile.  Returns the
        merged config dict."""
        config = self.resolve(name)
        self._active = name
        logger.info("Activated profile '%s'", name)
        return config

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def active(self) -> str | None:
        return self._active

    def list_profiles(self) -> list[dict[str, Any]]:
        return [
            {
                "name": p.name,
                "description": p.description,
                "extends": p.extends,
                "active": p.name == self._active,
            }
            for p in self._profiles.values()
        ]

    def get_profile(self, name: str) -> Profile | None:
        return self._profiles.get(name)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_profile(self, name: str, path: str | Path) -> None:
        """Write a profile to a standalone YAML file."""
        profile = self._profiles.get(name)
        if profile is None:
            raise KeyError(f"Unknown profile: '{name}'")
        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError("PyYAML required for export") from exc

        data = copy.deepcopy(profile.overrides)
        if profile.extends:
            data["extends"] = profile.extends
        if profile.description:
            data["description"] = profile.description

        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        logger.info("Exported profile '%s' to %s", name, p)
