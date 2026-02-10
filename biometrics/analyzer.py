"""
BiometricsAnalyzer computes typing dynamics metrics and profiles.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

from biometrics.models import BiometricsProfile, DigraphStats
from biometrics.matcher import ProfileMatcher


class BiometricsAnalyzer:
    """Analyze keystroke timing events to produce a profile.

    Also supports profile matching for user authentication via the integrated
    ProfileMatcher. Register reference profiles with `register_reference_profile()`
    and authenticate users with `authenticate()`.
    """

    def __init__(
        self,
        profile_id_prefix: str = "usr",
        match_threshold: float = 50.0,
        authentication_enabled: bool = False,
    ) -> None:
        self._prefix = profile_id_prefix
        self._matcher = ProfileMatcher(threshold=match_threshold)
        self._authentication_enabled = authentication_enabled
        self._reference_profiles: dict[str, dict[str, Any]] = {}

    # -------------------------------------------------------------------------
    # Profile Matching / Authentication Methods
    # -------------------------------------------------------------------------

    def register_reference_profile(
        self, user_id: str, profile: BiometricsProfile | dict[str, Any]
    ) -> None:
        """Register a reference profile for a user.

        Args:
            user_id: Unique identifier for the user
            profile: BiometricsProfile or dict representation of the profile
        """
        if isinstance(profile, BiometricsProfile):
            profile_dict = profile.to_dict()
        else:
            profile_dict = profile
        self._reference_profiles[user_id] = profile_dict

    def unregister_profile(self, user_id: str) -> bool:
        """Remove a user's reference profile.

        Returns:
            True if profile was removed, False if user_id not found.
        """
        if user_id in self._reference_profiles:
            del self._reference_profiles[user_id]
            return True
        return False

    def authenticate(self, live_profile: BiometricsProfile | dict[str, Any]) -> Optional[str]:
        """Authenticate a user based on their typing profile.

        Compares the live profile against all registered reference profiles
        and returns the user_id of the best match (if within threshold).

        Args:
            live_profile: The profile generated from live typing data

        Returns:
            user_id of the matched user, or None if no match found.
        """
        if not self._authentication_enabled:
            return None

        if isinstance(live_profile, BiometricsProfile):
            live_dict = live_profile.to_dict()
        else:
            live_dict = live_profile

        best_match: Optional[str] = None
        best_distance = float("inf")

        for user_id, ref_profile in self._reference_profiles.items():
            distance = self._matcher.distance(ref_profile, live_dict)
            if distance < best_distance and self._matcher.is_match(ref_profile, live_dict):
                best_distance = distance
                best_match = user_id

        return best_match

    def get_similarity_score(
        self,
        profile_a: BiometricsProfile | dict[str, Any],
        profile_b: BiometricsProfile | dict[str, Any],
    ) -> float:
        """Calculate similarity score between two profiles.

        Args:
            profile_a: First profile
            profile_b: Second profile

        Returns:
            Similarity score from 0 to 100 (100 = identical)
        """
        dict_a = profile_a.to_dict() if isinstance(profile_a, BiometricsProfile) else profile_a
        dict_b = profile_b.to_dict() if isinstance(profile_b, BiometricsProfile) else profile_b

        distance = self._matcher.distance(dict_a, dict_b)
        # Convert distance to similarity (inverse relationship, capped at 100)
        return max(0.0, 100.0 - distance)

    def is_same_user(
        self,
        profile_a: BiometricsProfile | dict[str, Any],
        profile_b: BiometricsProfile | dict[str, Any],
    ) -> bool:
        """Check if two profiles likely belong to the same user.

        Args:
            profile_a: First profile
            profile_b: Second profile

        Returns:
            True if profiles match within threshold, False otherwise.
        """
        dict_a = profile_a.to_dict() if isinstance(profile_a, BiometricsProfile) else profile_a
        dict_b = profile_b.to_dict() if isinstance(profile_b, BiometricsProfile) else profile_b

        return self._matcher.is_match(dict_a, dict_b)

    @property
    def registered_users(self) -> list[str]:
        """Return list of registered user IDs."""
        return list(self._reference_profiles.keys())

    # -------------------------------------------------------------------------
    # Profile Generation Methods (existing)
    # -------------------------------------------------------------------------

    def generate_profile(self, events: list[dict[str, Any]]) -> BiometricsProfile:
        """Generate a biometrics profile from keystroke events."""
        if not events:
            raise ValueError("No events provided for biometrics analysis")

        events_sorted = sorted(events, key=lambda e: e.get("down_ts", e.get("timestamp", 0)))
        sample_size = len(events_sorted)

        dwell_times = [e["dwell_ms"] for e in events_sorted if e.get("dwell_ms") is not None]
        flight_times = [e["flight_ms"] for e in events_sorted if e.get("flight_ms") is not None]

        avg_dwell = _mean(dwell_times)
        avg_flight = _mean(flight_times)

        digraph_model = self._build_digraph_model(events_sorted)
        trigraph_model = self._build_trigraph_model(events_sorted)
        rhythm_signature = self._compute_rhythm_signature(flight_times)
        pressure_variance = _std(flight_times) if flight_times else 0.0
        fatigue_curve = self._compute_fatigue_curve(events_sorted)
        error_rate = self._compute_error_rate(events_sorted)
        wpm_bursts = self._compute_wpm_bursts(events_sorted)

        profile_id = f"{self._prefix}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        created_at = datetime.now(timezone.utc).isoformat()

        return BiometricsProfile(
            profile_id=profile_id,
            created_at=created_at,
            sample_size=sample_size,
            avg_dwell_ms=avg_dwell,
            avg_flight_ms=avg_flight,
            pressure_variance=pressure_variance,
            digraph_model=digraph_model,
            trigraph_model=trigraph_model,
            rhythm_signature=rhythm_signature,
            fatigue_curve=fatigue_curve,
            error_rate=error_rate,
            wpm_bursts=wpm_bursts,
        )

    def _build_digraph_model(self, events: list[dict[str, Any]]) -> dict[str, DigraphStats]:
        latencies: dict[str, list[float]] = defaultdict(list)
        for prev, curr in zip(events, events[1:]):
            k1 = _normalize_key(prev.get("key", ""))
            k2 = _normalize_key(curr.get("key", ""))
            if len(k1) != 1 or len(k2) != 1:
                continue
            digraph = f"{k1}{k2}"
            t1 = prev.get("down_ts")
            t2 = curr.get("down_ts")
            if t1 is None or t2 is None:
                continue
            latencies[digraph].append((t2 - t1) * 1000.0)

        model: dict[str, DigraphStats] = {}
        for digraph, values in latencies.items():
            model[digraph] = DigraphStats(
                mean=_mean(values),
                std=_std(values),
                count=len(values),
            )
        return model

    def _build_trigraph_model(self, events: list[dict[str, Any]]) -> dict[str, DigraphStats]:
        latencies: dict[str, list[float]] = defaultdict(list)
        for i in range(len(events) - 2):
            k1 = _normalize_key(events[i].get("key", ""))
            k2 = _normalize_key(events[i + 1].get("key", ""))
            k3 = _normalize_key(events[i + 2].get("key", ""))
            if len(k1) != 1 or len(k2) != 1 or len(k3) != 1:
                continue
            trigraph = f"{k1}{k2}{k3}"
            t1 = events[i].get("down_ts")
            t3 = events[i + 2].get("down_ts")
            if t1 is None or t3 is None:
                continue
            latencies[trigraph].append((t3 - t1) * 1000.0)

        model: dict[str, DigraphStats] = {}
        for trigraph, values in latencies.items():
            model[trigraph] = DigraphStats(
                mean=_mean(values),
                std=_std(values),
                count=len(values),
            )
        return model

    @staticmethod
    def _compute_rhythm_signature(flight_times: list[float]) -> list[float]:
        if not flight_times:
            return []
        percentiles = [10, 25, 50, 75, 90]
        sorted_times = sorted(flight_times)
        return [_percentile(sorted_times, p) for p in percentiles]

    @staticmethod
    def _compute_fatigue_curve(events: list[dict[str, Any]]) -> dict[str, float]:
        if not events:
            return {}
        start = events[0].get("down_ts", events[0].get("timestamp", 0.0))
        buckets = {
            "0-15min": (0, 15 * 60),
            "15-30min": (15 * 60, 30 * 60),
            "30-60min": (30 * 60, 60 * 60),
            "60min+": (60 * 60, float("inf")),
        }
        counts: dict[str, int] = {k: 0 for k in buckets}
        for e in events:
            t = e.get("down_ts", e.get("timestamp", 0.0))
            delta = t - start
            for key, (lo, hi) in buckets.items():
                if lo <= delta < hi:
                    counts[key] += 1
                    break
        curve = {}
        for key, count in counts.items():
            minutes = (buckets[key][1] - buckets[key][0]) / 60.0
            if minutes == float("inf"):
                minutes = max((events[-1].get("down_ts", start) - start) / 60.0, 1.0)
            curve[key] = _wpm_from_keystrokes(count, minutes)
        return curve

    @staticmethod
    def _compute_error_rate(events: list[dict[str, Any]]) -> float:
        if not events:
            return 0.0
        backspaces = sum(1 for e in events if _normalize_key(e.get("key", "")) == "[backspace]")
        total = len(events)
        if total == 0:
            return 0.0
        return (backspaces / total) * 100.0

    @staticmethod
    def _compute_wpm_bursts(events: list[dict[str, Any]]) -> list[float]:
        if not events:
            return []
        start = events[0].get("down_ts", events[0].get("timestamp", 0.0))
        window = 10.0
        counts: dict[int, int] = defaultdict(int)
        for e in events:
            t = e.get("down_ts", e.get("timestamp", 0.0))
            idx = int((t - start) // window)
            counts[idx] += 1
        bursts = []
        for idx in sorted(counts.keys()):
            bursts.append(_wpm_from_keystrokes(counts[idx], window / 60.0))
        return bursts


def _normalize_key(key: str) -> str:
    return key.lower().strip()


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


def _percentile(sorted_values: list[float], percentile: int) -> float:
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * (percentile / 100)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_values[int(k)]
    d0 = sorted_values[f] * (c - k)
    d1 = sorted_values[c] * (k - f)
    return d0 + d1


def _wpm_from_keystrokes(count: int, minutes: float) -> float:
    if minutes <= 0:
        return 0.0
    words = count / 5.0
    return words / minutes
