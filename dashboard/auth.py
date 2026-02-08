"""Authentication for the dashboard."""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

auth_router = APIRouter(tags=["auth"])

# In-memory session store (simple, no external deps)
_sessions: dict[str, dict[str, Any]] = {}

# PBKDF2 parameters
_PBKDF2_ITERATIONS = 480_000
_PBKDF2_HASH = "sha256"
_SALT_LENGTH = 32

# Default credentials — should be changed via config
_ADMIN_USERNAME = "admin"
_ADMIN_PASSWORD_HASH = ""  # set by configure_auth or first hash_password call
_SESSION_TTL = 3600  # 1 hour


def configure_auth(username: str, password_hash: str, session_ttl: int = 3600) -> None:
    """Configure auth settings from application config."""
    global _ADMIN_USERNAME, _ADMIN_PASSWORD_HASH, _SESSION_TTL
    _ADMIN_USERNAME = username
    _ADMIN_PASSWORD_HASH = password_hash
    _SESSION_TTL = session_ttl


def hash_password(password: str) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256 and a random salt.

    Returns a string in the format: ``iterations$salt_hex$derived_hex``.
    """
    salt = os.urandom(_SALT_LENGTH)
    derived = hashlib.pbkdf2_hmac(
        _PBKDF2_HASH,
        password.encode(),
        salt,
        _PBKDF2_ITERATIONS,
    )
    return f"{_PBKDF2_ITERATIONS}${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Constant-time password verification against a PBKDF2 hash string.

    Also accepts legacy SHA-256 hex digests for backwards compatibility.
    """
    if "$" in stored_hash:
        # PBKDF2 format: iterations$salt_hex$derived_hex
        parts = stored_hash.split("$", 2)
        if len(parts) != 3:
            return False
        iterations_str, salt_hex, expected_hex = parts
        try:
            iterations = int(iterations_str)
            salt = bytes.fromhex(salt_hex)
        except (ValueError, TypeError):
            return False
        derived = hashlib.pbkdf2_hmac(
            _PBKDF2_HASH,
            password.encode(),
            salt,
            iterations,
        )
        return hmac.compare_digest(derived.hex(), expected_hex)

    # Legacy SHA-256 (no salt) — kept for migration only
    return hmac.compare_digest(
        hashlib.sha256(password.encode()).hexdigest(),
        stored_hash,
    )


def create_session(username: str) -> str:
    """Create a new session and return token."""
    token = secrets.token_urlsafe(32)
    _sessions[token] = {
        "username": username,
        "created": time.time(),
    }
    return token


def get_current_user(request: Request) -> str | None:
    """Get the current user from session cookie."""
    token = request.cookies.get("session_token")
    if not token or token not in _sessions:
        return None
    session = _sessions[token]
    if time.time() - session["created"] > _SESSION_TTL:
        _sessions.pop(token, None)
        return None
    return session["username"]


def require_auth(request: Request) -> RedirectResponse | None:
    """Redirect to login if not authenticated. Returns None if authenticated."""
    if get_current_user(request) is None:
        return RedirectResponse(url="/login", status_code=302)
    return None


class LoginForm(BaseModel):
    username: str
    password: str


@auth_router.post("/auth/login")
async def login(request: Request) -> Response:
    """Handle login form submission."""
    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")

    if username == _ADMIN_USERNAME and verify_password(password, _ADMIN_PASSWORD_HASH):
        token = create_session(username)
        response = RedirectResponse(url="/dashboard", status_code=302)
        response.set_cookie(
            key="session_token",
            value=token,
            httponly=True,
            samesite="strict",
            max_age=_SESSION_TTL,
        )
        logger.info("User '%s' logged in", username)
        return response

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": "Invalid username or password"},
        status_code=401,
    )


@auth_router.post("/auth/logout")
async def logout(request: Request) -> RedirectResponse:
    """Handle logout (POST only to prevent CSRF via GET)."""
    token = request.cookies.get("session_token")
    if token:
        _sessions.pop(token, None)
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("session_token")
    return response
