"""Tests for biometrics modules."""
from __future__ import annotations

import time

from biometrics.collector import BiometricsCollector
from biometrics.analyzer import BiometricsAnalyzer
from biometrics.matcher import ProfileMatcher


def test_collector_dwell_and_flight():
    collector = BiometricsCollector()
    t0 = time.time()
    collector.on_key_down("a", t0)
    collector.on_key_up("a", t0 + 0.1)
    collector.on_key_down("b", t0 + 0.2)
    collector.on_key_up("b", t0 + 0.3)

    events = collector.collect()
    assert len(events) == 2
    assert events[0]["key"] == "a"
    assert events[0]["dwell_ms"] > 0
    assert events[1]["flight_ms"] is not None


def test_analyzer_generates_profile():
    analyzer = BiometricsAnalyzer(profile_id_prefix="test")
    base = time.time()
    events = [
        {"key": "t", "down_ts": base, "up_ts": base + 0.05, "dwell_ms": 50, "flight_ms": None},
        {"key": "h", "down_ts": base + 0.1, "up_ts": base + 0.15, "dwell_ms": 50, "flight_ms": 50},
        {"key": "e", "down_ts": base + 0.2, "up_ts": base + 0.25, "dwell_ms": 50, "flight_ms": 50},
    ]
    profile = analyzer.generate_profile(events)
    assert profile.sample_size == 3
    assert profile.avg_dwell_ms > 0
    assert profile.avg_flight_ms >= 0
    assert "th" in profile.digraph_model


def test_matcher_distance():
    matcher = ProfileMatcher(threshold=10.0)
    a = {"avg_dwell_ms": 100, "avg_flight_ms": 120, "error_rate": 1.0, "digraph_model": {}}
    b = {"avg_dwell_ms": 101, "avg_flight_ms": 119, "error_rate": 1.0, "digraph_model": {}}
    assert matcher.is_match(a, b) is True
