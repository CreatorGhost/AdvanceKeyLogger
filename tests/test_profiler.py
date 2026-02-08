"""Tests for application usage profiler."""
from __future__ import annotations

from datetime import datetime

from profiler.categorizer import AppCategorizer
from profiler.models import AppSession
from profiler.scorer import ProductivityScorer
from profiler.tracker import AppUsageTracker


def test_categorizer_browser_entertainment_override():
    categories = {
        "work": ["Visual Studio Code"],
        "communication": ["Slack"],
        "browser": ["Google Chrome"],
        "entertainment": ["YouTube"],
        "uncategorized": ["*"],
    }
    categorizer = AppCategorizer(categories)
    title = "Cats on YouTube - Google Chrome"
    app_name = categorizer.extract_app_name(title)
    assert app_name == "Google Chrome"
    assert categorizer.categorize(app_name, title) == "entertainment"


def test_tracker_sessions_and_switches():
    categories = {
        "work": ["Visual Studio Code"],
        "communication": ["Slack"],
        "uncategorized": ["*"],
    }
    tracker = AppUsageTracker(AppCategorizer(categories), idle_gap_seconds=500)
    events = [
        {"type": "window", "data": "Doc - Visual Studio Code", "timestamp": 100.0},
        {"type": "window", "data": "Slack", "timestamp": 200.0},
        {"type": "window", "data": "Doc - Visual Studio Code", "timestamp": 260.0},
    ]
    tracker.process_batch(events)
    sessions, idle_gaps, switches = tracker.snapshot(now_ts=400.0)
    assert len(sessions) == 3
    assert len(idle_gaps) == 0
    assert len(switches) == 2
    assert sessions[0].duration_sec == 100.0
    assert sessions[1].duration_sec == 60.0
    assert sessions[2].duration_sec == 140.0


def test_scorer_basic_metrics():
    now = datetime.now()
    day_start = datetime(now.year, now.month, now.day).timestamp()
    sessions = [
        AppSession(
            app_name="Visual Studio Code",
            category="work",
            window_title="",
            start_ts=day_start,
            end_ts=day_start + 3600,
            duration_sec=3600,
        ),
        AppSession(
            app_name="Slack",
            category="communication",
            window_title="",
            start_ts=day_start + 3600,
            end_ts=day_start + 4200,
            duration_sec=600,
        ),
    ]
    context_switches = [day_start + 3600]
    scorer = ProductivityScorer(focus_min_seconds=600, productive_categories=["work"], top_n=2)
    profile = scorer.score_day(
        sessions,
        idle_gaps=[],
        context_switches=context_switches,
        day=datetime.fromtimestamp(day_start).date(),
    )
    assert profile is not None
    assert profile.total_active_seconds == 4200
    assert profile.productive_seconds == 3600
    assert profile.productivity_score >= 0
    assert profile.productivity_score <= 100
    assert len(profile.focus_sessions) == 2
    assert len(profile.top_apps) == 2
    assert profile.peak_productivity_window is not None
