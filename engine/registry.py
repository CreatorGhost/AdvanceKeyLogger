"""
Rule registry with hot-reload support.
"""
from __future__ import annotations

import os
import time
from typing import Any

import yaml

from engine.rule_parser import Rule, Trigger, Action


class RuleRegistry:
    """Loads and stores rules from a YAML file."""

    def __init__(self, rules_path: str, reload_interval: float = 2.0, mode: str = "all") -> None:
        self.rules_path = rules_path
        self.reload_interval = reload_interval
        self.mode = mode  # "all" or "first"
        self._rules: list[Rule] = []
        self._last_mtime: float = 0.0
        self._last_check: float = 0.0
        self.load()

    def load(self) -> None:
        if not self.rules_path or not os.path.exists(self.rules_path):
            self._rules = []
            return
        with open(self.rules_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        rules = []
        for entry in data.get("rules", []):
            if not isinstance(entry, dict):
                continue
            name = entry.get("name", "unnamed-rule")
            trigger_cfg = entry.get("trigger", {})
            action_cfg = entry.get("action", {})
            if not trigger_cfg or not action_cfg:
                continue

            trigger = Trigger(
                event=str(trigger_cfg.get("event", "")).strip(),
                condition=str(trigger_cfg.get("condition", "")).strip(),
            )
            action = Action(
                type=str(action_cfg.get("type", "")).strip(),
                params={k: v for k, v in action_cfg.items() if k != "type"},
            )
            rule = Rule(
                name=name,
                trigger=trigger,
                action=action,
                cooldown_ms=int(entry.get("cooldown_ms", 0)),
                priority=int(entry.get("priority", 100)),
                enabled=bool(entry.get("enabled", True)),
            )
            rules.append(rule)

        self._rules = sorted(rules, key=lambda r: r.priority)
        self._last_mtime = os.path.getmtime(self.rules_path)
        self._last_check = time.time()

    def maybe_reload(self) -> None:
        now = time.time()
        if now - self._last_check < self.reload_interval:
            return
        self._last_check = now
        if not self.rules_path or not os.path.exists(self.rules_path):
            return
        try:
            mtime = os.path.getmtime(self.rules_path)
        except OSError:
            return
        if mtime > self._last_mtime:
            self.load()

    def get_rules_for_event(self, event_type: str) -> list[Rule]:
        if not event_type:
            return []
        return [
            rule
            for rule in self._rules
            if rule.enabled and (rule.trigger.event == event_type or rule.trigger.event == "*")
        ]

    @property
    def rules(self) -> list[Rule]:
        return list(self._rules)
