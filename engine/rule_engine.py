"""
Rule engine: evaluates triggers and dispatches actions.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from engine.actions import ActionDispatcher
from engine.evaluator import SafeEvaluator
from engine.event_bus import EventBus
from engine.registry import RuleRegistry

logger = logging.getLogger(__name__)


class RuleEngine:
    """Evaluates rules against capture events and dispatches actions."""

    def __init__(
        self,
        config: dict[str, Any],
        captures: list[Any],
        set_interval,
    ) -> None:
        self._config = config
        rules_cfg = config.get("rules", {})
        rules_path = rules_cfg.get("path", "./config/rules.yaml")
        reload_interval = float(rules_cfg.get("reload_interval_seconds", 2))
        self._mode = str(rules_cfg.get("mode", "all")).lower()
        self._buffer_max = int(rules_cfg.get("keystroke_buffer_max", 1024))

        self._registry = RuleRegistry(
            rules_path=rules_path,
            reload_interval=reload_interval,
            mode=self._mode,
        )
        self._evaluator = SafeEvaluator()
        self._dispatcher = ActionDispatcher(captures, config, set_interval=set_interval)
        self._bus = EventBus()
        self._bus.subscribe("*", self._on_event)

        self._keystroke_buffer: str = ""

    def process_events(self, events: list[dict[str, Any]]) -> None:
        for event in events:
            event_type = event.get("type", "")
            self._bus.publish(event_type, event)

    def _on_event(self, event: dict[str, Any]) -> None:
        self._registry.maybe_reload()
        event_type = event.get("type", "")
        rules = self._registry.get_rules_for_event(event_type)
        if not rules:
            return

        if event_type == "keystroke":
            key = str(event.get("data", ""))
            if key:
                self._keystroke_buffer = (self._keystroke_buffer + key)[-self._buffer_max :]

        for rule in rules:
            if not rule.enabled:
                continue
            if rule.cooldown_ms > 0:
                if (time.time() - rule.last_triggered) * 1000 < rule.cooldown_ms:
                    continue

            if not self._evaluate_rule(rule, event):
                continue

            try:
                self._dispatcher.dispatch(rule.action, event)
                rule.last_triggered = time.time()
                logger.info("Rule triggered: %s", rule.name)
            except Exception as exc:
                logger.error("Rule action failed (%s): %s", rule.name, exc)

            if self._mode == "first":
                break

    def _evaluate_rule(self, rule, event: dict[str, Any]) -> bool:
        condition = rule.trigger.condition
        if not condition:
            return True

        window_title = None
        if event.get("type") == "window":
            window_title = event.get("data")
        else:
            window_title = (event.get("context") or {}).get("window_title")

        context = {
            "event": event,
            "data": event.get("data"),
            "buffer": self._keystroke_buffer,
            "window_title": window_title,
            "idle_seconds": event.get("idle_seconds", 0),
        }
        try:
            return self._evaluator.evaluate(condition, context)
        except Exception as exc:
            logger.error("Rule condition error (%s): %s", rule.name, exc)
            return False
