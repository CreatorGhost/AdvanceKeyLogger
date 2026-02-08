"""
Track foreground application usage and context switches.
"""
from __future__ import annotations

import time
from typing import Any

from profiler.categorizer import AppCategorizer
from profiler.models import AppSession


class AppUsageTracker:
    """Track foreground app sessions and idle gaps from capture events."""

    def __init__(
        self,
        categorizer: AppCategorizer,
        idle_gap_seconds: int = 300,
        activity_event_types: set[str] | None = None,
    ) -> None:
        self.categorizer = categorizer
        self.idle_gap_seconds = idle_gap_seconds
        self.activity_event_types = activity_event_types or {
            "keystroke",
            "clipboard",
            "window",
            "mouse_move",
            "mouse_click",
        }
        self._sessions: list[AppSession] = []
        self._idle_gaps: list[dict[str, Any]] = []
        self._context_switches: list[float] = []
        self._current_app: str | None = None
        self._current_category: str | None = None
        self._current_title: str | None = None
        self._current_start_ts: float | None = None
        self._last_activity_ts: float | None = None
        self._last_event_ts: float | None = None

    def process_batch(self, events: list[dict[str, Any]]) -> None:
        if not events:
            return
        stamped = []
        for event in events:
            ts = event.get("timestamp")
            if ts is None:
                ts = time.time()
            stamped.append((ts, event))
        for _, event in sorted(stamped, key=lambda item: item[0]):
            self.process_event(event)

    def process_event(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("type", ""))
        ts = event.get("timestamp")
        if ts is None:
            ts = time.time()

        if event_type == "window":
            title = str(event.get("data") or "")
            app_name = self.categorizer.extract_app_name(title)
            category = self.categorizer.categorize(app_name, title)
            self._maybe_record_idle_gap(ts)

            if self._current_app is None:
                self._start_session(app_name, category, title, ts)
            else:
                if app_name != self._current_app or category != self._current_category:
                    self._close_session(ts)
                    self._context_switches.append(ts)
                    self._start_session(app_name, category, title, ts)
                else:
                    self._current_title = title
                    self._last_event_ts = ts
            self._last_activity_ts = ts
            return

        if event_type.startswith("mouse_") or event_type in self.activity_event_types:
            self._last_activity_ts = ts

    def snapshot(
        self, now_ts: float | None = None
    ) -> tuple[list[AppSession], list[dict[str, Any]], list[float]]:
        sessions = list(self._sessions)
        if now_ts is None:
            now_ts = time.time()
        if self._current_app is not None and self._current_start_ts is not None:
            duration = max(0.0, now_ts - self._current_start_ts)
            sessions.append(
                AppSession(
                    app_name=self._current_app,
                    category=self._current_category or "uncategorized",
                    window_title=self._current_title or "",
                    start_ts=self._current_start_ts,
                    end_ts=now_ts,
                    duration_sec=duration,
                )
            )
        return sessions, list(self._idle_gaps), list(self._context_switches)

    def _start_session(self, app_name: str, category: str, title: str, ts: float) -> None:
        self._current_app = app_name
        self._current_category = category
        self._current_title = title
        self._current_start_ts = ts
        self._last_event_ts = ts

    def _close_session(self, end_ts: float) -> None:
        if self._current_app is None or self._current_start_ts is None:
            return
        duration = max(0.0, end_ts - self._current_start_ts)
        self._sessions.append(
            AppSession(
                app_name=self._current_app,
                category=self._current_category or "uncategorized",
                window_title=self._current_title or "",
                start_ts=self._current_start_ts,
                end_ts=end_ts,
                duration_sec=duration,
            )
        )
        self._current_app = None
        self._current_category = None
        self._current_title = None
        self._current_start_ts = None
        self._last_event_ts = end_ts

    def _maybe_record_idle_gap(self, ts: float) -> None:
        if self._last_activity_ts is None:
            return
        gap = ts - self._last_activity_ts
        if gap >= self.idle_gap_seconds:
            self._idle_gaps.append(
                {
                    "start_ts": self._last_activity_ts,
                    "end_ts": ts,
                    "duration_sec": gap,
                }
            )
