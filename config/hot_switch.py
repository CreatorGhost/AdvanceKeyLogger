"""
Hot-Switch Engine — apply configuration changes at runtime without restart.

Works with :class:`~config.profile_manager.ProfileManager` and the
:class:`~config.settings.Settings` singleton to:

1. Validate a proposed config change before applying
2. Atomically swap the active config
3. Notify registered listeners so subsystems can react
4. Roll back if any listener reports a failure

Usage::

    from config.hot_switch import HotSwitch

    hs = HotSwitch(settings)
    hs.on_change("capture.*", capture_reload_handler)
    hs.on_change("pipeline.*", pipeline_reload_handler)

    # Later — e.g. from a fleet command or dashboard action:
    ok = hs.apply_profile("stealth")
    ok = hs.apply_patch({"capture": {"screenshot": {"enabled": False}}})
"""

from __future__ import annotations

import copy
import fnmatch
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Listener signature: fn(old_config, new_config) -> bool  (True = success)
ChangeListener = Callable[[dict[str, Any], dict[str, Any]], bool]


class HotSwitch:
    """Runtime configuration switching with rollback."""

    def __init__(self, settings: Any) -> None:
        """
        Parameters
        ----------
        settings:
            The :class:`~config.settings.Settings` singleton.  Must support
            ``.as_dict()``, ``.set(key_path, value)``, and optionally
            ``._config`` for direct replacement.
        """
        self._settings = settings
        self._listeners: list[tuple[str, ChangeListener]] = []
        self._profile_manager: Any | None = None  # set via set_profile_manager()
        self._history: list[dict[str, Any]] = []  # snapshots for rollback
        self._max_history = 10

    # ------------------------------------------------------------------
    # Listener registration
    # ------------------------------------------------------------------

    def on_change(self, pattern: str, listener: ChangeListener) -> None:
        """Register a listener for config keys matching *pattern*.

        *pattern* supports ``fnmatch`` wildcards:
        ``"capture.*"``, ``"pipeline.middleware.*"``, ``"*"`` (all changes).
        """
        self._listeners.append((pattern, listener))
        logger.debug("Registered config change listener for '%s'", pattern)

    # ------------------------------------------------------------------
    # Profile integration
    # ------------------------------------------------------------------

    def set_profile_manager(self, pm: Any) -> None:
        """Attach a :class:`~config.profile_manager.ProfileManager`."""
        self._profile_manager = pm

    def apply_profile(self, name: str) -> bool:
        """Resolve a named profile and apply it as a config patch.

        Returns True on success, False on rollback.
        """
        if self._profile_manager is None:
            logger.error("No ProfileManager attached — cannot apply profile")
            return False

        try:
            new_config = self._profile_manager.resolve(name)
        except (KeyError, ValueError) as exc:
            logger.error("Profile resolution failed: %s", exc)
            return False

        return self._apply(new_config, reason=f"profile:{name}")

    # ------------------------------------------------------------------
    # Patch application
    # ------------------------------------------------------------------

    def apply_patch(self, patch: dict[str, Any]) -> bool:
        """Deep-merge *patch* onto the current config and apply.

        Returns True on success, False on rollback.
        """
        from config.profile_manager import _deep_merge

        old = self._settings.as_dict() if hasattr(self._settings, "as_dict") else {}
        new_config = _deep_merge(old, patch)
        return self._apply(new_config, reason="patch")

    # ------------------------------------------------------------------
    # Core apply + rollback
    # ------------------------------------------------------------------

    def _apply(self, new_config: dict[str, Any], reason: str = "") -> bool:
        old_config = (
            self._settings.as_dict()
            if hasattr(self._settings, "as_dict")
            else {}
        )

        # Determine which top-level keys changed — skip no-op applies
        changed_keys = _diff_keys(old_config, new_config)
        if not changed_keys:
            logger.info("Hot-switch: no effective changes (%s)", reason)
            return True

        # Save snapshot for rollback only when there are real changes
        self._history.append(copy.deepcopy(old_config))
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        logger.info(
            "Hot-switch applying %s — changed keys: %s",
            reason, ", ".join(sorted(changed_keys)),
        )

        # Replace config in settings
        self._replace_config(new_config)

        # Notify matching listeners
        failed: list[str] = []
        succeeded: list[tuple[str, ChangeListener]] = []
        for pattern, listener in self._listeners:
            if any(fnmatch.fnmatch(k, pattern) for k in changed_keys):
                try:
                    ok = listener(old_config, new_config)
                    if not ok:
                        failed.append(pattern)
                    else:
                        succeeded.append((pattern, listener))
                except Exception as exc:
                    logger.error("Listener '%s' raised: %s", pattern, exc)
                    failed.append(pattern)

        if failed:
            logger.warning(
                "Hot-switch rollback: %d listener(s) failed: %s",
                len(failed), failed,
            )
            # Re-notify already-succeeded listeners with swapped args to revert
            for pattern, listener in succeeded:
                try:
                    listener(new_config, old_config)
                except Exception as exc:
                    logger.error(
                        "Listener '%s' raised during rollback re-notify: %s",
                        pattern, exc,
                    )
            self._replace_config(old_config)
            return False

        logger.info("Hot-switch applied successfully (%s)", reason)
        return True

    def rollback(self) -> bool:
        """Revert to the previous config snapshot."""
        if not self._history:
            logger.warning("No config history to rollback to")
            return False
        previous = self._history.pop()
        self._replace_config(previous)
        logger.info("Rolled back to previous config")
        return True

    def _replace_config(self, config: dict[str, Any]) -> None:
        """Write *config* into the Settings singleton."""
        if hasattr(self._settings, "_config"):
            self._settings._config = copy.deepcopy(config)
        else:
            # Fallback: set keys one by one (flat)
            for key, value in _flatten(config):
                self._settings.set(key, value)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_history_count(self) -> int:
        return len(self._history)

    def get_changed_keys(self) -> list[str]:
        """Return the keys that changed in the most recent apply."""
        if len(self._history) < 1:
            return []
        old = self._history[-1]
        current = (
            self._settings.as_dict()
            if hasattr(self._settings, "as_dict")
            else {}
        )
        return _diff_keys(old, current)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _diff_keys(
    old: dict[str, Any], new: dict[str, Any], prefix: str = ""
) -> list[str]:
    """Return dot-separated key paths that differ between *old* and *new*."""
    keys: list[str] = []
    all_k = set(old.keys()) | set(new.keys())
    for k in all_k:
        full = f"{prefix}{k}" if not prefix else f"{prefix}.{k}"
        ov = old.get(k)
        nv = new.get(k)
        if isinstance(ov, dict) and isinstance(nv, dict):
            keys.extend(_diff_keys(ov, nv, full))
        elif ov != nv:
            keys.append(full)
    return keys


def _flatten(
    d: dict[str, Any], prefix: str = ""
) -> list[tuple[str, Any]]:
    """Flatten a nested dict to dot-separated key-value pairs."""
    items: list[tuple[str, Any]] = []
    for k, v in d.items():
        full = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            items.extend(_flatten(v, full))
        else:
            items.append((full, v))
    return items
