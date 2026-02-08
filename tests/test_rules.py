"""Tests for rule engine components."""
from __future__ import annotations

import textwrap

from engine.evaluator import SafeEvaluator
from engine.registry import RuleRegistry
from engine.rule_engine import RuleEngine


def test_evaluator_matches_syntax():
    evaluator = SafeEvaluator()
    ctx = {"window_title": "Google Chrome - Test"}
    assert evaluator.evaluate("window_title matches '.*Chrome.*'", ctx) is True
    assert evaluator.evaluate("window_title matches '.*Firefox.*'", ctx) is False


def test_rule_registry_loads(tmp_path):
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text(
        textwrap.dedent(
            """
            rules:
              - name: "test-rule"
                trigger:
                  event: keystroke
                  condition: "buffer_contains('abc')"
                action:
                  type: set_capture_interval
                  value: 5
                priority: 5
            """
        ).strip()
    )
    registry = RuleRegistry(str(rules_path))
    rules = registry.rules
    assert len(rules) == 1
    assert rules[0].name == "test-rule"
    assert rules[0].trigger.event == "keystroke"


def test_rule_engine_triggers_action(tmp_path):
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text(
        textwrap.dedent(
            """
            rules:
              - name: "interval-rule"
                trigger:
                  event: keystroke
                  condition: "buffer_contains('abc')"
                action:
                  type: set_capture_interval
                  value: 7
            """
        ).strip()
    )
    config = {
        "rules": {
            "enabled": True,
            "path": str(rules_path),
            "mode": "first",
            "keystroke_buffer_max": 16,
        },
        "transport": {"method": "email"},
    }
    values = []

    def set_interval(value: float) -> None:
        values.append(value)

    engine = RuleEngine(config, captures=[], set_interval=set_interval)
    engine.process_events(
        [
            {"type": "keystroke", "data": "a"},
            {"type": "keystroke", "data": "b"},
            {"type": "keystroke", "data": "c"},
        ]
    )
    assert values == [7.0]
