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
        keys = ["avg_dwell_ms", "avg_flight_ms", "error_rate", "pressure_variance"]
        vec_a = [float(profile_a.get(k, 0.0)) for k in keys]
        vec_b = [float(profile_b.get(k, 0.0)) for k in keys]
        dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(vec_a, vec_b)))

        # Add digraph distance for overlap
        dist += self._ngraph_distance(
            profile_a.get("digraph_model", {}),
            profile_b.get("digraph_model", {}),
        )

        # Add trigraph distance for overlap
        dist += self._ngraph_distance(
            profile_a.get("trigraph_model", {}),
            profile_b.get("trigraph_model", {}),
        )

        return dist

    @staticmethod
    def _ngraph_distance(model_a: dict[str, Any], model_b: dict[str, Any]) -> float:
        overlap = set(model_a.keys()) & set(model_b.keys())
        if not overlap:
            return 0.0
        total = 0.0
        for key in overlap:
            a_mean = float(model_a[key].get("mean", 0.0))
            b_mean = float(model_b[key].get("mean", 0.0))
            std = float(model_a[key].get("std", 0.0) or 0.0)
            if std > 0:
                total += abs(a_mean - b_mean) / std
            else:
                total += abs(a_mean - b_mean)
        return total / max(len(overlap), 1)

    def is_match(self, profile_a: dict[str, Any], profile_b: dict[str, Any]) -> bool:
        return self.distance(profile_a, profile_b) <= self.threshold
