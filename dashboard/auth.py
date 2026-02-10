"""Authentication for the dashboard."""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import threading
import time
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse

logger = logging.getLogger(__name__)

auth_router = APIRouter(tags=["auth"])

# In-memory session store (simple, no external deps)
_sessions: dict[str, dict[str, Any]] = {}
_sessions_lock = threading.Lock()

# Rate limiting for login attempts (IP -> list of timestamps)
_login_attempts: dict[str, list[float]] = defaultdict(list)
_login_attempts_lock = threading.Lock()
_LOGIN_RATE_LIMIT = 5  # max attempts per window
_LOGIN_RATE_WINDOW = 300  # 5 minute window

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


def _cleanup_expired_sessions() -> None:
    """Remove expired sessions to prevent unbounded memory growth.

    Must be called while holding ``_sessions_lock``.
    """
    now = time.time()
    expired = [tok for tok, s in _sessions.items() if now - s["created"] > _SESSION_TTL]
    for tok in expired:
        _sessions.pop(tok, None)


def create_session(username: str) -> str:
    """Create a new session and return token."""
    token = secrets.token_urlsafe(32)
    with _sessions_lock:
        # Periodically purge expired sessions
        _cleanup_expired_sessions()
        _sessions[token] = {
            "username": username,
            "created": time.time(),
        }
    return token


def get_current_user(request: Request) -> str | None:
    """Get the current user from session cookie."""
    token = request.cookies.get("session_token")
    if not token:
        return None
    with _sessions_lock:
        session = _sessions.get(token)
        if not session:
            return None
        if time.time() - session["created"] > _SESSION_TTL:
            _sessions.pop(token, None)
            return None
        return session["username"]


def require_auth(request: Request) -> RedirectResponse | None:
    """Redirect to login if not authenticated. Returns None if authenticated."""
    if get_current_user(request) is None:
        return RedirectResponse(url="/login", status_code=302)
    return None


def _is_rate_limited(ip: str) -> bool:
    """Check if an IP is rate-limited for login attempts."""
    now = time.time()
    with _login_attempts_lock:
        attempts = _login_attempts[ip]
        # Remove attempts outside the window
        _login_attempts[ip] = [t for t in attempts if now - t < _LOGIN_RATE_WINDOW]
        return len(_login_attempts[ip]) >= _LOGIN_RATE_LIMIT


def _upgrade_password_hash(plaintext: str) -> None:
    """Re-hash a password from legacy SHA-256 to PBKDF2 in-place."""
    global _ADMIN_PASSWORD_HASH
    new_hash = hash_password(plaintext)
    _ADMIN_PASSWORD_HASH = new_hash
    logger.info("Upgraded admin password hash from legacy SHA-256 to PBKDF2")


@auth_router.post("/auth/login")
async def login(request: Request) -> Response:
    """Handle login form submission."""
    client_ip = request.client.host if request.client else "unknown"

    # Rate limit check
    if _is_rate_limited(client_ip):
        logger.warning("Rate limited login attempt from %s", client_ip)
        templates = request.app.state.templates
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Too many login attempts. Please try again later."},
            status_code=429,
        )

    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")

    if username == _ADMIN_USERNAME and verify_password(password, _ADMIN_PASSWORD_HASH):
        # Migrate legacy SHA-256 hashes to PBKDF2 on successful login
        if "$" not in _ADMIN_PASSWORD_HASH:
            _upgrade_password_hash(password)

        # Clear failed attempts on success
        with _login_attempts_lock:
            _login_attempts.pop(client_ip, None)
        token = create_session(username)
        response = RedirectResponse(url="/dashboard", status_code=302)
        is_secure = request.url.scheme == "https"
        response.set_cookie(
            key="session_token",
            value=token,
            httponly=True,
            secure=is_secure,
            samesite="strict",
            max_age=_SESSION_TTL,
        )
        logger.info("User '%s' logged in", username)
        return response

    # Record failed attempt
    with _login_attempts_lock:
        _login_attempts[client_ip].append(time.time())

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
        with _sessions_lock:
            _sessions.pop(token, None)
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("session_token")
    return response
