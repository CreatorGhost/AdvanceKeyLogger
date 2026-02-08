"""
Native macOS active-window backend using Quartz and AppKit.

Replaces the ``osascript`` subprocess approach with direct API calls:
  - ``NSWorkspace.sharedWorkspace().frontmostApplication()`` for the app name
  - ``CGWindowListCopyWindowInfo`` for the actual window title

Falls back gracefully when pyobjc is not installed (see APPKIT_AVAILABLE).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

APPKIT_AVAILABLE = False
try:
    from AppKit import NSWorkspace

    APPKIT_AVAILABLE = True
except ImportError:
    pass

_QUARTZ_WINDOW_AVAILABLE = False
try:
    from Quartz import (
        CGWindowListCopyWindowInfo,
        kCGNullWindowID,
        kCGWindowListOptionOnScreenOnly,
        kCGWindowListExcludeDesktopElements,
    )

    _QUARTZ_WINDOW_AVAILABLE = True
except ImportError:
    pass


def get_active_window_title_native() -> str:
    """Return the active window title using native macOS APIs.

    Tries to get the actual *window* title via CGWindowListCopyWindowInfo.
    Falls back to just the application name via NSWorkspace if the
    window-level query fails.

    Returns ``"Unknown"`` on any failure.
    """
    try:
        app_name = _get_frontmost_app_name()
        if not app_name:
            return "Unknown"

        # Try to find the window title for the frontmost app
        if _QUARTZ_WINDOW_AVAILABLE:
            title = _get_window_title_for_app(app_name)
            if title:
                return title

        # Fall back to just the app name (same as old osascript behaviour)
        return app_name

    except Exception:
        return "Unknown"


def _get_frontmost_app_name() -> str | None:
    """Return the localized name of the frontmost application."""
    try:
        ws = NSWorkspace.sharedWorkspace()
        app = ws.frontmostApplication()
        if app is None:
            return None
        name = app.localizedName()
        return str(name) if name else None
    except Exception:
        return None


def _get_window_title_for_app(app_name: str) -> str | None:
    """Return the title of the frontmost window owned by *app_name*.

    Iterates through on-screen windows (front-to-back order) and
    returns the first window whose owner matches.
    """
    try:
        options = kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements
        window_list = CGWindowListCopyWindowInfo(options, kCGNullWindowID)
        if window_list is None:
            return None

        for win in window_list:
            owner = win.get("kCGWindowOwnerName", "")
            if owner == app_name:
                title = win.get("kCGWindowName", "")
                if title:
                    return f"{app_name} — {title}"
                return app_name

        return None
    except Exception:
        return None
