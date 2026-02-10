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


class FleetAuth:
    """JWT-based authentication for fleet agents."""

    def __init__(self, secret_key: str, access_ttl_minutes: int = 15, refresh_ttl_days: int = 7, storage=None):
        self.secret_key = secret_key
        self.access_ttl = timedelta(minutes=access_ttl_minutes)
        self.refresh_ttl = timedelta(days=refresh_ttl_days)
        self.algorithm = "HS256"
        self._storage = storage  # FleetStorage instance for token revocation checks

    def create_tokens(self, agent_id: str) -> Dict[str, str]:
        """Generate access and refresh tokens for an agent."""
        now = datetime.now(timezone.utc)

        access_payload = {
            "sub": agent_id,
            "type": "access",
            "iat": now,
            "exp": now + self.access_ttl,
            "jti": secrets.token_hex(16),
        }

        refresh_payload = {
            "sub": agent_id,
            "type": "refresh",
            "iat": now,
            "exp": now + self.refresh_ttl,
            "jti": secrets.token_hex(16),
        }

        access_token = jwt.encode(access_payload, self.secret_key, algorithm=self.algorithm)
        refresh_token = jwt.encode(refresh_payload, self.secret_key, algorithm=self.algorithm)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": int(self.access_ttl.total_seconds()),
            "token_type": "Bearer",
        }

    def verify_token(self, token: str, expected_type: str = "access") -> Optional[str]:
        """
        Verify a token and return the agent_id (sub) if valid.
        Returns None if invalid or revoked.
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])

            if payload.get("type") != expected_type:
                logger.warning(
                    f"Token type mismatch: expected {expected_type}, got {payload.get('type')}"
                )
                return None

            # Check token revocation if storage is available
            jti = payload.get("jti")
            if jti and self._storage is not None:
                try:
                    if self._storage.is_token_revoked(jti):
                        logger.warning("Token revoked (jti=%s)", jti)
                        return None
                except Exception as exc:
                    logger.warning("Token revocation check failed: %s", exc)

            return payload.get("sub")

        except jwt.ExpiredSignatureError:
            logger.debug("Token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None
        except Exception as e:
            logger.error(f"Token verification error: {e}")
            return None
