"""Tests for E2E server helpers."""
from __future__ import annotations

import base64
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519

from crypto.envelope import Envelope, HybridEnvelope
from server.keys import generate_server_keypair, load_server_private_key
from server.storage import detect_extension, store_payload


def test_generate_and_load_server_keys(tmp_path: Path):
    public_key_b64 = generate_server_keypair(str(tmp_path))
    assert public_key_b64

    config = {"key_store_path": str(tmp_path)}
    private_key = load_server_private_key(config)
    assert isinstance(private_key, x25519.X25519PrivateKey)


def test_store_payload_extension(tmp_path: Path):
    config = {"storage_dir": str(tmp_path)}
    payload = b"{\"ok\": true}"
    path = store_payload(payload, config)
    assert path.exists()
    assert path.suffix == ".json"

    assert detect_extension(b"PK\x03\x04...") == ".zip"
    assert detect_extension(b"\x1f\x8b...") == ".gz"


def test_server_decrypt_flow(tmp_path: Path):
    server_private = x25519.X25519PrivateKey.generate()
    server_public = server_private.public_key()

    sender_private = x25519.X25519PrivateKey.generate()
    sender_public = sender_private.public_key()

    # For the envelope, we only need an Ed25519 key pair to sign
    from cryptography.hazmat.primitives.asymmetric import ed25519

    signing_private = ed25519.Ed25519PrivateKey.generate()
    signing_public = signing_private.public_key()

    envelope = HybridEnvelope(server_public).encrypt(
        b"payload", signing_private, signing_public
    )
    data = envelope.to_bytes()
    parsed = Envelope.from_bytes(data)
    plaintext = HybridEnvelope.decrypt(parsed, server_private)
    assert plaintext == b"payload"
