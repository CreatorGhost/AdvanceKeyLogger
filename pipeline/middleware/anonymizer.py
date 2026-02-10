"""
Data Anonymization Middleware — detects and redacts PII from capture events
before they reach storage or transport.

Integrates as a standard pipeline middleware using the ``@register_middleware``
decorator.  Runs early in the chain (order=15, after timestamp enrichment)
so downstream middleware and storage never see raw PII.

Supported PII patterns:
  * Email addresses
  * Credit card numbers (Luhn-validated)
  * US Social Security Numbers
  * Phone numbers (international format)
  * IPv4 addresses
  * Custom patterns via config

Redaction strategies:
  * ``mask`` (default) — replace with ``***`` preserving length hints
  * ``hash`` — replace with a SHA-256 prefix (irreversible but deterministic)
  * ``remove`` — delete the matched text entirely
  * ``tag`` — wrap in ``<REDACTED:type>`` tags (useful for debugging)

Configuration (in ``pipeline.middleware`` list)::

    - name: anonymizer
      enabled: true
      config:
        strategy: mask          # mask | hash | remove | tag
        patterns:               # additional regex patterns
          - name: employee_id
            regex: "EMP-\\d{6}"
        allowlist:              # never redact these (e.g. internal domains)
          - "@example.com"
        fields:                 # which event fields to scan (default: [data])
          - data
          - metadata.window_title
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, Optional

from pipeline.base_middleware import BaseMiddleware, CaptureEvent
from pipeline.context import PipelineContext
from pipeline.registry import register_middleware

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Built-in PII patterns
# ---------------------------------------------------------------------------

_BUILTIN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(
        r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
    )),
    ("credit_card", re.compile(
        r"\b(?:\d[ \-]*?){13,19}\b"
    )),
    ("ssn", re.compile(
        r"\b\d{3}[\- ]?\d{2}[\- ]?\d{4}\b"
    )),
    ("phone", re.compile(
        r"(?:\+\d{1,3}[\s\-]?|\b)\(?(?:\d{2,4})\)[\s\-]?\d{3,4}[\s\-]?\d{3,4}\b"
        r"|"
        r"\+\d{1,3}[\s\-]?\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{3,4}\b"
    )),
    ("ipv4", re.compile(
        r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
    )),
]


def _luhn_check(digits: str) -> bool:
    """Validate a numeric string with the Luhn algorithm."""
    clean = digits.replace(" ", "").replace("-", "")
    if not clean.isdigit() or len(clean) < 13:
        return False
    total = 0
    for i, ch in enumerate(reversed(clean)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


# ---------------------------------------------------------------------------
# Redaction strategies
# ---------------------------------------------------------------------------

def _mask(match_text: str, _pii_type: str) -> str:
    """Replace with asterisks, preserving first/last char if long enough."""
    if len(match_text) <= 4:
        return "***"
    return match_text[0] + "*" * (len(match_text) - 2) + match_text[-1]


def _hash_redact(match_text: str, pii_type: str) -> str:
    """Replace with a truncated SHA-256 hash."""
    h = hashlib.sha256(match_text.encode()).hexdigest()[:12]
    return f"[{pii_type}:{h}]"


def _remove(_match_text: str, _pii_type: str) -> str:
    return ""


def _tag(_match_text: str, pii_type: str) -> str:
    return f"<REDACTED:{pii_type}>"


_STRATEGIES = {
    "mask": _mask,
    "hash": _hash_redact,
    "remove": _remove,
    "tag": _tag,
}


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

@register_middleware("anonymizer")
class AnonymizerMiddleware(BaseMiddleware):
    """Pipeline middleware that detects and redacts PII from capture events."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        cfg = self.config

        strategy_name = cfg.get("strategy", "mask")
        self._strategy = _STRATEGIES.get(strategy_name, _mask)

        # Merge built-in + custom patterns
        self._patterns: list[tuple[str, re.Pattern[str]]] = list(_BUILTIN_PATTERNS)
        for custom in cfg.get("patterns", []):
            try:
                name = custom["name"]
                regex = re.compile(custom["regex"])
                self._patterns.append((name, regex))
            except (KeyError, re.error) as exc:
                logger.warning("Invalid custom pattern: %s", exc)

        # Allowlist: substrings that should never be redacted
        self._allowlist: list[str] = cfg.get("allowlist", [])

        # Fields to scan
        self._fields: list[str] = cfg.get("fields", ["data"])

    @property
    def name(self) -> str:
        return "anonymizer"

    @property
    def order(self) -> int:
        return 15  # after timestamp enricher (10), before most others

    def process(
        self,
        event: CaptureEvent,
        context: PipelineContext,
    ) -> Optional[CaptureEvent]:
        redacted_count = 0

        for field_path in self._fields:
            value = _get_nested(event, field_path)
            if not isinstance(value, str):
                continue

            new_value, count = self._redact(value)
            if count > 0:
                _set_nested(event, field_path, new_value)
                redacted_count += count

        if redacted_count > 0:
            event.setdefault("_anonymized", True)
            event.setdefault("_redaction_count", 0)
            event["_redaction_count"] += redacted_count
            context.inc("pii_redacted", redacted_count)

        return event

    def _redact(self, text: str) -> tuple[str, int]:
        """Apply all PII patterns to *text*.  Returns (new_text, redaction_count)."""
        count = 0

        for pii_type, pattern in self._patterns:
            def _replace(m: re.Match[str], _type: str = pii_type) -> str:
                nonlocal count
                matched = m.group(0)

                # Skip allowlisted substrings
                for allowed in self._allowlist:
                    if allowed in matched:
                        return matched

                # Extra validation for credit cards (Luhn check)
                if _type == "credit_card" and not _luhn_check(matched):
                    return matched

                count += 1
                return self._strategy(matched, _type)

            text = pattern.sub(_replace, text)

        return text, count


# ---------------------------------------------------------------------------
# Nested field access helpers
# ---------------------------------------------------------------------------

def _get_nested(d: dict[str, Any], path: str) -> Any:
    """Get a value from a nested dict using dot notation."""
    parts = path.split(".")
    current: Any = d
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _set_nested(d: dict[str, Any], path: str, value: Any) -> None:
    """Set a value in a nested dict using dot notation."""
    parts = path.split(".")
    current = d
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value
