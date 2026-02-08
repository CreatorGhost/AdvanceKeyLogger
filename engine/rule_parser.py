"""
Rule parser: YAML -> Rule objects.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Trigger:
    event: str
    condition: str = ""


@dataclass
class Action:
    type: str
    params: dict[str, Any]


@dataclass
class Rule:
    name: str
    trigger: Trigger
    action: Action
    cooldown_ms: int = 0
    priority: int = 100
    enabled: bool = True
    last_triggered: float = 0.0
