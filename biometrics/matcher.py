"""
ProfileMatcher compares live typing profiles against stored profiles.
"""
from __future__ import annotations

import math
from typing import Any


class ProfileMatcher:
    """Compare two biometrics profiles using a simple distance metric."""

    def __init__(self, threshold: float = 50.0) -> None:
        self.threshold = threshold

    def distance(self, profile_a: dict[str, Any], profile_b: dict[str, Any]) -> float:
        keys = ["avg_dwell_ms", "avg_flight_ms", "error_rate"]
        vec_a = [float(profile_a.get(k, 0.0)) for k in keys]
        vec_b = [float(profile_b.get(k, 0.0)) for k in keys]
        dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(vec_a, vec_b)))

        # Add digraph distance for overlap
        digraph_a = profile_a.get("digraph_model", {})
        digraph_b = profile_b.get("digraph_model", {})
        overlap = set(digraph_a.keys()) & set(digraph_b.keys())
        if overlap:
            digraph_dist = 0.0
            for key in overlap:
                a_mean = float(digraph_a[key].get("mean", 0.0))
                b_mean = float(digraph_b[key].get("mean", 0.0))
                std = float(digraph_a[key].get("std", 0.0) or 0.0)
                if std > 0:
                    digraph_dist += abs(a_mean - b_mean) / std
                else:
                    digraph_dist += abs(a_mean - b_mean)
            dist += digraph_dist / max(len(overlap), 1)
        return dist

    def is_match(self, profile_a: dict[str, Any], profile_b: dict[str, Any]) -> bool:
        return self.distance(profile_a, profile_b) <= self.threshold
