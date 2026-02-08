"""Authentication helpers for E2E server."""
from __future__ import annotations

import hmac
from typing import Iterable

from fastapi import Request


def extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return api_key.strip()
    return None


def is_authorized(request: Request, tokens: Iterable[str]) -> bool:
    token = extract_token(request)
    if not token:
        return False
    return any(hmac.compare_digest(token, t) for t in tokens)
