"""Tests for E2E server security helpers."""
from __future__ import annotations

from server.clients import ClientRegistry
from server.rate_limit import RateLimiter
from server.replay import ReplayCache


def test_client_registry_allowlist():
    registry = ClientRegistry(["abc"], None)
    assert registry.is_allowed("abc") is True
    assert registry.is_allowed("def") is False


def test_client_registry_open_when_empty():
    registry = ClientRegistry([], None)
    assert registry.is_allowed("anything") is True


def test_rate_limiter():
    limiter = RateLimiter(limit_per_minute=2)
    assert limiter.allow("ip") is True
    assert limiter.allow("ip") is True
    assert limiter.allow("ip") is False


def test_replay_cache():
    cache = ReplayCache(ttl_seconds=60, max_entries=10)
    assert cache.seen("id") is False
    assert cache.seen("id") is True
