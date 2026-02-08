"""
Data models for application usage profiling.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AppSession:
    app_name: str
    category: str
    window_title: str
    start_ts: float
    end_ts: float
    duration_sec: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_name": self.app_name,
            "category": self.category,
            "window_title": self.window_title,
            "start_ts": self.start_ts,
            "end_ts": self.end_ts,
            "duration_sec": self.duration_sec,
        }


@dataclass
class FocusSession:
    app_name: str
    category: str
    start_ts: float
    end_ts: float
    duration_sec: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_name": self.app_name,
            "category": self.category,
            "start_ts": self.start_ts,
            "end_ts": self.end_ts,
            "duration_sec": self.duration_sec,
        }


@dataclass
class DailyProfile:
    date: str
    generated_at: str
    total_active_seconds: float
    productive_seconds: float
    productive_ratio: float
    deep_work_score: float
    productivity_score: float
    context_switches: int
    context_switches_per_hour: float
    app_totals: dict[str, float] = field(default_factory=dict)
    category_totals: dict[str, float] = field(default_factory=dict)
    focus_sessions: list[FocusSession] = field(default_factory=list)
    top_apps: list[dict[str, Any]] = field(default_factory=list)
    idle_gaps: list[dict[str, Any]] = field(default_factory=list)
    peak_productivity_window: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "generated_at": self.generated_at,
            "total_active_seconds": self.total_active_seconds,
            "productive_seconds": self.productive_seconds,
            "productive_ratio": self.productive_ratio,
            "deep_work_score": self.deep_work_score,
            "productivity_score": self.productivity_score,
            "context_switches": self.context_switches,
            "context_switches_per_hour": self.context_switches_per_hour,
            "app_totals": self.app_totals,
            "category_totals": self.category_totals,
            "focus_sessions": [session.to_dict() for session in self.focus_sessions],
            "top_apps": self.top_apps,
            "idle_gaps": self.idle_gaps,
            "peak_productivity_window": self.peak_productivity_window,
        }
