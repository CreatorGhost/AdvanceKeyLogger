"""Tests for E2E crypto envelope."""
from __future__ import annotations

import base64
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519

from crypto.envelope import Envelope, HybridEnvelope
from crypto.protocol import E2EProtocol


def _b64_public(key) -> str:
    raw = key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("utf-8")


def test_envelope_roundtrip():
    server_private = x25519.X25519PrivateKey.generate()
    server_public = server_private.public_key()

    sender_private = ed25519.Ed25519PrivateKey.generate()
    sender_public = sender_private.public_key()

    envelope = HybridEnvelope(server_public).encrypt(
        b"hello", sender_private, sender_public
    )
    encoded = envelope.to_bytes()
    parsed = Envelope.from_bytes(encoded)

    plaintext = HybridEnvelope.decrypt(parsed, server_private)
    assert plaintext == b"hello"


def test_protocol_encrypt_and_decrypt(tmp_path: Path):
    server_private = x25519.X25519PrivateKey.generate()
    server_public = server_private.public_key()

    config = {
        "server_public_key": _b64_public(server_public),
        "key_store_path": str(tmp_path),
        "pin_server_key": True,
    }

    protocol = E2EProtocol(config)
    encrypted = protocol.encrypt(b"payload")
    envelope = Envelope.from_bytes(encrypted)
    plaintext = HybridEnvelope.decrypt(envelope, server_private)
    assert plaintext == b"payload"
