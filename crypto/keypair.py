"""
Key pair management for E2E transport.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
from cryptography.hazmat.primitives import serialization

from crypto.key_store import KeyStore


@dataclass
class AgentKeyPair:
    exchange_private: x25519.X25519PrivateKey
    exchange_public: x25519.X25519PublicKey
    signing_private: ed25519.Ed25519PrivateKey
    signing_public: ed25519.Ed25519PublicKey


class KeyPairManager:
    """Load or generate key pairs for E2E encryption and signing."""

    def __init__(self, store: KeyStore, prefix: str = "agent") -> None:
        self._store = store
        self._prefix = prefix

    def load_or_create(self, rotation_hours: int | None = None) -> AgentKeyPair:
        exchange_private = self._load_x25519_private()
        signing_private = self._load_ed25519_private()
        meta = self._store.load_json(self._name("meta")) or {}

        if rotation_hours:
            created_at = float(meta.get("created_at", 0.0))
            age_seconds = time.time() - created_at if created_at else None
            if age_seconds is None or age_seconds >= rotation_hours * 3600:
                exchange_private = None
                signing_private = None

        if exchange_private is None:
            exchange_private = x25519.X25519PrivateKey.generate()
            self._store.save_bytes(
                self._name("x25519_private"),
                exchange_private.private_bytes(
                    serialization.Encoding.Raw,
                    serialization.PrivateFormat.Raw,
                    serialization.NoEncryption(),
                ),
            )

        if signing_private is None:
            signing_private = ed25519.Ed25519PrivateKey.generate()
            self._store.save_bytes(
                self._name("ed25519_private"),
                signing_private.private_bytes(
                    serialization.Encoding.Raw,
                    serialization.PrivateFormat.Raw,
                    serialization.NoEncryption(),
                ),
            )

        exchange_public = exchange_private.public_key()
        signing_public = signing_private.public_key()

        self._store.save_bytes(
            self._name("x25519_public"),
            exchange_public.public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            ),
        )
        self._store.save_bytes(
            self._name("ed25519_public"),
            signing_public.public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            ),
        )
        self._store.save_json(
            self._name("meta"),
            {"created_at": time.time()},
        )

        return AgentKeyPair(
            exchange_private=exchange_private,
            exchange_public=exchange_public,
            signing_private=signing_private,
            signing_public=signing_public,
        )

    def _load_x25519_private(self) -> x25519.X25519PrivateKey | None:
        raw = self._store.load_bytes(self._name("x25519_private"))
        if raw:
            return x25519.X25519PrivateKey.from_private_bytes(raw)
        return None

    def _load_ed25519_private(self) -> ed25519.Ed25519PrivateKey | None:
        raw = self._store.load_bytes(self._name("ed25519_private"))
        if raw:
            return ed25519.Ed25519PrivateKey.from_private_bytes(raw)
        return None

    def _name(self, key: str) -> str:
        return f"{self._prefix}_{key}"
