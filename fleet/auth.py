"""
Authentication utilities for fleet agents using JWT.
"""

from __future__ import annotations

import time
import jwt
import logging
import secrets
from typing import Dict, Any, Optional
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


_KNOWN_INSECURE_SECRETS = frozenset({
    "CHANGE_ME_IN_PRODUCTION",
    "changeme",
    "secret",
    "development",
    "test",
})


class FleetAuth:
    """JWT-based authentication for fleet agents."""

    def __init__(
        self,
        secret_key: str,
        access_ttl_minutes: int = 15,
        refresh_ttl_days: int = 7,
        storage=None,
        allow_default_secret: bool = False,
    ):
        # Guard against known insecure defaults in production
        if secret_key in _KNOWN_INSECURE_SECRETS and not allow_default_secret:
            raise ValueError(
                "SECURITY: JWT secret is a known insecure default. "
                "Set a strong random secret (32+ chars) in fleet.auth.jwt_secret "
                "or explicitly set fleet.auth.allow_default_secret: true for "
                "development/testing."
            )
        if secret_key in _KNOWN_INSECURE_SECRETS:
            logger.warning(
                "SECURITY WARNING: Using a known insecure JWT secret. "
                "This is only acceptable in development/testing."
            )
        # Use name-mangled attribute to prevent accidental exposure
        self.__secret_key = secret_key
        self.access_ttl = timedelta(minutes=access_ttl_minutes)
        self.refresh_ttl = timedelta(days=refresh_ttl_days)
        self.algorithm = "HS256"
        self._storage = storage  # FleetStorage instance for token revocation checks

    @property
    def _signing_key(self) -> str:
        """Access the JWT signing key (internal use only)."""
        return self.__secret_key

    def __repr__(self) -> str:
        return f"<FleetAuth algorithm={self.algorithm}>"

    def __str__(self) -> str:
        return "FleetAuth(secret=***)"

    def create_tokens(self, agent_id: str) -> Dict[str, Any]:
        """Generate access and refresh tokens for an agent.

        The returned dict includes ``access_jti``, ``refresh_jti``,
        ``access_expires_at`` and ``refresh_expires_at`` so callers can
        persist the JTIs in storage (required for revocation to work).
        """
        now = datetime.now(timezone.utc)

        access_jti = secrets.token_hex(16)
        refresh_jti = secrets.token_hex(16)
        access_exp = now + self.access_ttl
        refresh_exp = now + self.refresh_ttl

        access_payload = {
            "sub": agent_id,
            "type": "access",
            "iat": now,
            "exp": access_exp,
            "jti": access_jti,
        }

        refresh_payload = {
            "sub": agent_id,
            "type": "refresh",
            "iat": now,
            "exp": refresh_exp,
            "jti": refresh_jti,
        }

        access_token = jwt.encode(access_payload, self._signing_key, algorithm=self.algorithm)
        refresh_token = jwt.encode(refresh_payload, self._signing_key, algorithm=self.algorithm)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": int(self.access_ttl.total_seconds()),
            "token_type": "Bearer",
            # Metadata for JTI persistence — not included in API response models
            "access_jti": access_jti,
            "refresh_jti": refresh_jti,
            "access_expires_at": access_exp.timestamp(),
            "refresh_expires_at": refresh_exp.timestamp(),
        }

    def verify_token(self, token: str, expected_type: str = "access") -> Optional[str]:
        """
        Verify a token and return the agent_id (sub) if valid.
        Returns None if invalid, revoked, or if the revocation check fails
        (fail-closed: tokens are rejected when storage is unavailable).
        """
        try:
            payload = jwt.decode(token, self._signing_key, algorithms=[self.algorithm])

            if payload.get("type") != expected_type:
                logger.warning(
                    f"Token type mismatch: expected {expected_type}, got {payload.get('type')}"
                )
                return None

            # Check token revocation if storage is available.
            # Fail closed: if self._storage.is_token_revoked raises,
            # reject the token rather than allowing it through.
            jti = payload.get("jti")
            if jti and self._storage is not None:
                try:
                    if self._storage.is_token_revoked(jti):
                        logger.warning("Token revoked (jti=%s)", jti)
                        return None
                except Exception as exc:
                    logger.error(
                        "Token revocation check failed (jti=%s): %s", jti, exc
                    )
                    return None

            return payload.get("sub")

        except jwt.ExpiredSignatureError:
            logger.debug("Token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning("Invalid token")
            logger.debug("Invalid token detail: %s", e)
            return None
        except Exception as e:
            logger.error(f"Token verification error: {e}")
            return None
