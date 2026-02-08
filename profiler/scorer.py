"""
Compute productivity metrics from application sessions.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, date
from typing import Any

from profiler.models import AppSession, DailyProfile, FocusSession
from profiler.tracker import AppUsageTracker


class ProductivityScorer:
    """Compute focus sessions and productivity scores."""

    def __init__(
        self,
        focus_min_seconds: int = 600,
        productive_categories: list[str] | None = None,
        top_n: int = 10,
    ) -> None:
        self.focus_min_seconds = focus_min_seconds
        self.productive_categories = {c.lower() for c in (productive_categories or ["work"])}
        self.top_n = top_n

    def build_daily_profile(
        self, tracker: AppUsageTracker, now_ts: float | None = None
    ) -> DailyProfile | None:
        if now_ts is None:
            now_ts = datetime.now().timestamp()
        sessions, idle_gaps, context_switches = tracker.snapshot(now_ts)
        day = datetime.fromtimestamp(now_ts).date()
        return self.score_day(sessions, idle_gaps, context_switches, day)

    def score_day(
        self,
        sessions: list[AppSession],
        idle_gaps: list[dict[str, Any]],
        context_switches: list[float],
        day: date,
    ) -> DailyProfile | None:
        daily_sessions = _sessions_for_day(sessions, day)
        if not daily_sessions:
            return None

        total_active_seconds = sum(s.duration_sec for s in daily_sessions)
        app_totals: dict[str, float] = {}
        category_totals: dict[str, float] = {}

        for session in daily_sessions:
            app_totals[session.app_name] = app_totals.get(session.app_name, 0.0) + session.duration_sec
            category_totals[session.category] = (
                category_totals.get(session.category, 0.0) + session.duration_sec
            )

        productive_seconds = sum(
            seconds
            for category, seconds in category_totals.items()
            if category.lower() in self.productive_categories
        )
        productive_ratio = _safe_ratio(productive_seconds, total_active_seconds)

        focus_sessions = [
            FocusSession(
                app_name=s.app_name,
                category=s.category,
                start_ts=s.start_ts,
                end_ts=s.end_ts,
                duration_sec=s.duration_sec,
            )
            for s in daily_sessions
            if s.duration_sec >= self.focus_min_seconds
        ]

        deep_work_score = sum(
            (session.duration_sec / 60.0) * _deep_work_weight(session.duration_sec)
            for session in focus_sessions
        )
        max_possible_score = (total_active_seconds / 60.0) * 3.0 if total_active_seconds else 0.0

        context_switch_count = sum(
            1
            for ts in context_switches
            if _same_day(datetime.fromtimestamp(ts), day)
        )
        active_hours = total_active_seconds / 3600.0 if total_active_seconds else 0.0
        context_switches_per_hour = _safe_ratio(context_switch_count, active_hours)

        productivity_score = _productivity_score(
            productive_ratio,
            deep_work_score,
            max_possible_score,
            context_switches_per_hour,
        )

        top_apps = [
            {"app_name": name, "seconds": seconds}
            for name, seconds in sorted(app_totals.items(), key=lambda item: item[1], reverse=True)
        ][: self.top_n]

        peak_window = _peak_productivity_window(
            daily_sessions, day, self.productive_categories
        )

        daily_idle_gaps = _idle_gaps_for_day(idle_gaps, day)

        generated_at = datetime.now().isoformat()
        return DailyProfile(
            date=day.isoformat(),
            generated_at=generated_at,
            total_active_seconds=total_active_seconds,
            productive_seconds=productive_seconds,
            productive_ratio=productive_ratio,
            deep_work_score=deep_work_score,
            productivity_score=productivity_score,
            context_switches=context_switch_count,
            context_switches_per_hour=context_switches_per_hour,
            app_totals=app_totals,
            category_totals=category_totals,
            focus_sessions=focus_sessions,
            top_apps=top_apps,
            idle_gaps=daily_idle_gaps,
            peak_productivity_window=peak_window,
        )


def _sessions_for_day(sessions: list[AppSession], day: date) -> list[AppSession]:
    day_start = datetime.combine(day, datetime.min.time())
    day_end = day_start + timedelta(days=1)
    day_start_ts = day_start.timestamp()
    day_end_ts = day_end.timestamp()

    filtered: list[AppSession] = []
    for session in sessions:
        if session.end_ts <= day_start_ts or session.start_ts >= day_end_ts:
            continue
        start_ts = max(session.start_ts, day_start_ts)
        end_ts = min(session.end_ts, day_end_ts)
        duration = max(0.0, end_ts - start_ts)
        if duration <= 0:
            continue
        filtered.append(
            AppSession(
                app_name=session.app_name,
                category=session.category,
                window_title=session.window_title,
                start_ts=start_ts,
                end_ts=end_ts,
                duration_sec=duration,
            )
        )
    return filtered


def _idle_gaps_for_day(idle_gaps: list[dict[str, Any]], day: date) -> list[dict[str, Any]]:
    if not idle_gaps:
        return []
    day_start = datetime.combine(day, datetime.min.time()).timestamp()
    day_end = (datetime.combine(day, datetime.min.time()) + timedelta(days=1)).timestamp()
    results: list[dict[str, Any]] = []
    for gap in idle_gaps:
        start_ts = float(gap.get("start_ts", 0.0))
        end_ts = float(gap.get("end_ts", 0.0))
        if end_ts <= day_start or start_ts >= day_end:
            continue
        clipped_start = max(start_ts, day_start)
        clipped_end = min(end_ts, day_end)
        results.append(
            {
                "start_ts": clipped_start,
                "end_ts": clipped_end,
                "duration_sec": max(0.0, clipped_end - clipped_start),
            }
        )
    return results


def _peak_productivity_window(
    sessions: list[AppSession], day: date, productive_categories: set[str]
) -> dict[str, Any] | None:
    if not sessions:
        return None
    day_start = datetime.combine(day, datetime.min.time()).timestamp()
    buckets_total = [0.0 for _ in range(24)]
    buckets_productive = [0.0 for _ in range(24)]

    for session in sessions:
        remaining_start = session.start_ts
        remaining_end = session.end_ts
        while remaining_start < remaining_end:
            hour_idx = int((remaining_start - day_start) // 3600)
            if hour_idx < 0 or hour_idx >= 24:
                break
            hour_start = day_start + hour_idx * 3600
            hour_end = hour_start + 3600
            segment_end = min(remaining_end, hour_end)
            duration = max(0.0, segment_end - remaining_start)
            buckets_total[hour_idx] += duration
            if session.category.lower() in productive_categories:
                buckets_productive[hour_idx] += duration
            remaining_start = segment_end

    best_hour = None
    best_ratio = -1.0
    for hour_idx in range(24):
        total = buckets_total[hour_idx]
        if total <= 0:
            continue
        ratio = buckets_productive[hour_idx] / total if total else 0.0
        if ratio > best_ratio:
            best_ratio = ratio
            best_hour = hour_idx

    if best_hour is None:
        return None
    return {
        "hour": best_hour,
        "productive_ratio": best_ratio,
        "productive_seconds": buckets_productive[best_hour],
        "total_seconds": buckets_total[best_hour],
    }


def _productivity_score(
    productive_ratio: float,
    deep_work_score: float,
    max_possible_score: float,
    context_switches_per_hour: float,
) -> float:
    productive_component = productive_ratio * 50.0
    deep_work_component = (
        (deep_work_score / max_possible_score) * 30.0 if max_possible_score > 0 else 0.0
    )
    switch_rate = min(context_switches_per_hour, 60.0)
    switch_component = (1.0 - switch_rate / 60.0) * 20.0
    score = productive_component + deep_work_component + switch_component
    return max(0.0, min(100.0, score))


def _deep_work_weight(duration_sec: float) -> float:
    minutes = duration_sec / 60.0
    if minutes >= 120:
        return 3.0
    if minutes >= 60:
        return 2.0
    if minutes >= 30:
        return 1.5
    if minutes >= 10:
        return 1.0
    return 0.0


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _same_day(dt: datetime, day: date) -> bool:
    return dt.date() == day
