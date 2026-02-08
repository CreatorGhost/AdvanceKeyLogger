"""
Data models for keystroke biometrics.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DigraphStats:
    mean: float
    std: float
    count: int

    def to_dict(self) -> dict[str, Any]:
        return {"mean": self.mean, "std": self.std, "count": self.count}


@dataclass
class BiometricsProfile:
    profile_id: str
    created_at: str
    sample_size: int
    avg_dwell_ms: float
    avg_flight_ms: float
    pressure_variance: float = 0.0
    digraph_model: dict[str, DigraphStats] = field(default_factory=dict)
    trigraph_model: dict[str, DigraphStats] = field(default_factory=dict)
    rhythm_signature: list[float] = field(default_factory=list)
    fatigue_curve: dict[str, float] = field(default_factory=dict)
    error_rate: float = 0.0
    wpm_bursts: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "created_at": self.created_at,
            "sample_size": self.sample_size,
            "avg_dwell_ms": self.avg_dwell_ms,
            "avg_flight_ms": self.avg_flight_ms,
            "pressure_variance": self.pressure_variance,
            "digraph_model": {
                key: stats.to_dict() for key, stats in self.digraph_model.items()
            },
            "trigraph_model": {
                key: stats.to_dict() for key, stats in self.trigraph_model.items()
            },
            "rhythm_signature": self.rhythm_signature,
            "fatigue_curve": self.fatigue_curve,
            "error_rate": self.error_rate,
            "wpm_bursts": self.wpm_bursts,
        }
