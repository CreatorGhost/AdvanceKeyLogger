"""
Safe expression evaluator for rule conditions.
"""
from __future__ import annotations

import ast
import re
from typing import Any, Callable


class SafeEvaluator:
    """Evaluates a restricted subset of Python expressions."""

    def __init__(self) -> None:
        self._functions: dict[str, Callable[..., Any]] = {
            "buffer_contains": self._buffer_contains,
            "matches": self._matches,
            "contains": self._contains,
            "startswith": self._startswith,
            "endswith": self._endswith,
        }

    def evaluate(self, expression: str, context: dict[str, Any]) -> bool:
        if not expression:
            return True
        normalized = _normalize_condition(expression)
        node = ast.parse(normalized, mode="eval")
        return bool(self._eval(node.body, context))

    def _eval(self, node: ast.AST, context: dict[str, Any]) -> Any:
        if isinstance(node, ast.BoolOp):
            values = [self._eval(v, context) for v in node.values]
            if isinstance(node.op, ast.And):
                return all(values)
            if isinstance(node.op, ast.Or):
                return any(values)
            raise ValueError("Unsupported boolean operator")

        if isinstance(node, ast.UnaryOp):
            operand = self._eval(node.operand, context)
            if isinstance(node.op, ast.Not):
                return not operand
            raise ValueError("Unsupported unary operator")

        if isinstance(node, ast.Compare):
            left = self._eval(node.left, context)
            for op, comparator in zip(node.ops, node.comparators, strict=True):
                right = self._eval(comparator, context)
                if isinstance(op, ast.Eq) and not (left == right):
                    return False
                if isinstance(op, ast.NotEq) and not (left != right):
                    return False
                if isinstance(op, ast.Lt) and not (left < right):
                    return False
                if isinstance(op, ast.LtE) and not (left <= right):
                    return False
                if isinstance(op, ast.Gt) and not (left > right):
                    return False
                if isinstance(op, ast.GtE) and not (left >= right):
                    return False
                if isinstance(op, ast.In) and not (left in right):
                    return False
                if isinstance(op, ast.NotIn) and not (left not in right):
                    return False
                left = right
            return True

        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
                func = self._functions.get(func_name)
                if not func:
                    raise ValueError(f"Function '{func_name}' not allowed")
                args = [self._eval(arg, context) for arg in node.args]
                return func(context, *args)
            raise ValueError("Unsupported function call")

        if isinstance(node, ast.Name):
            return context.get(node.id)

        if isinstance(node, ast.Attribute):
            value = self._eval(node.value, context)
            if isinstance(value, dict):
                return value.get(node.attr)
            raise ValueError(
                f"Attribute access only allowed on dict objects, got {type(value).__name__}"
            )

        if isinstance(node, ast.Constant):
            return node.value

        raise ValueError(f"Unsupported expression: {type(node).__name__}")

    @staticmethod
    def _buffer_contains(context: dict[str, Any], needle: str) -> bool:
        buffer_value = str(context.get("buffer", "") or "")
        return needle in buffer_value

    @staticmethod
    def _matches(context: dict[str, Any], value: str, pattern: str) -> bool:
        return re.search(pattern, str(value or "")) is not None

    @staticmethod
    def _contains(context: dict[str, Any], haystack: str, needle: str) -> bool:
        return str(needle) in str(haystack or "")

    @staticmethod
    def _startswith(context: dict[str, Any], value: str, prefix: str) -> bool:
        return str(value or "").startswith(str(prefix))

    @staticmethod
    def _endswith(context: dict[str, Any], value: str, suffix: str) -> bool:
        return str(value or "").endswith(str(suffix))


def _normalize_condition(expression: str) -> str:
    """
    Convert DSL infix syntax to function call syntax.

    Supported operators:
        window_title matches ".*Chrome.*"  -> matches(window_title, ".*Chrome.*")
        window_title contains "Chrome"     -> contains(window_title, "Chrome")
        window_title startswith "Google"   -> startswith(window_title, "Google")
        data endswith ".exe"               -> endswith(data, ".exe")
    """
    operators = ["matches", "contains", "startswith", "endswith"]
    result = expression
    for op in operators:
        pattern = re.compile(
            rf"([A-Za-z0-9_\\.]+)\s+{op}\s+([\"'].*?[\"'])"
        )
        result = pattern.sub(rf"{op}(\1, \2)", result)
    return result
