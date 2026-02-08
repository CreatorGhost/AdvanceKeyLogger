"""
Shared pipeline context passed to all middleware.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineContext:
    """Context shared across middleware in a pipeline run."""

    config: dict[str, Any]
    system_info: dict[str, Any]
    start_time: float = field(default_factory=time.time)
    metrics: dict[str, int] = field(default_factory=lambda: {"processed": 0, "dropped": 0})

    def inc(self, key: str, amount: int = 1) -> None:
        self.metrics[key] = self.metrics.get(key, 0) + amount
