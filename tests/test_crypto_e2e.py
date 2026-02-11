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

    envelope = HybridEnvelope(server_public).encrypt(b"hello", sender_private, sender_public)
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


def test_intermediate_salt_decrypt_fallback():
    """Verify data encrypted with intermediate salt can be recovered.

    This test simulates an envelope created using the intermediate HKDF salt
    (_HKDF_SALT_INTERMEDIATE = b"AdvanceKeyLogger-E2E-v1") and verifies that
    the decrypt path correctly falls back to this salt when the primary and
    legacy salts fail.
    """
    import os
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    from crypto.envelope import (
        _HKDF_SALT_INTERMEDIATE,
        _wrap_aad,
        _payload_aad,
        compute_envelope_id,
    )
    from crypto.signer import sign_message

    # Generate server key pair
    server_private = x25519.X25519PrivateKey.generate()
    server_public = server_private.public_key()

    # Generate sender signing key pair
    sender_signing_private = ed25519.Ed25519PrivateKey.generate()
    sender_signing_public = sender_signing_private.public_key()
    sender_pub_bytes = sender_signing_public.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    # Generate ephemeral key pair for X25519 key exchange
    ephemeral_private = x25519.X25519PrivateKey.generate()
    ephemeral_public = ephemeral_private.public_key()
    ephemeral_pub_bytes = ephemeral_public.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    # Compute shared secret
    shared_secret = ephemeral_private.exchange(server_public)

    # Derive wrap key using INTERMEDIATE salt (the key derivation we're testing)
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_HKDF_SALT_INTERMEDIATE,
        info=b"E2E-WRAP-V1",
    )
    wrap_key = hkdf.derive(shared_secret)

    # Generate a random data key and encrypt payload
    data_key = AESGCM.generate_key(bit_length=256)
    payload_nonce = os.urandom(12)
    original_payload = b"test payload with intermediate salt"

    aesgcm_payload = AESGCM(data_key)
    payload_aad = _payload_aad(sender_pub_bytes)
    ciphertext = aesgcm_payload.encrypt(payload_nonce, original_payload, payload_aad)

    # Wrap the data key using the intermediate-salt-derived wrap key
    wrap_nonce = os.urandom(12)
    aesgcm_wrap = AESGCM(wrap_key)
    wrapped_key = aesgcm_wrap.encrypt(wrap_nonce, data_key, _wrap_aad(sender_pub_bytes))

    # Build signature payload (v2 format)
    def _signature_payload_v2(
        version, sender_pub, ephemeral_pub, wrap_nonce, wrapped_key, payload_nonce, ciphertext
    ):
        fields = [
            version.to_bytes(4, "big"),
            sender_pub,
            ephemeral_pub,
            wrap_nonce,
            wrapped_key,
            payload_nonce,
            ciphertext,
        ]
        out = bytearray()
        for field in fields:
            out.extend(len(field).to_bytes(4, "big"))
            out.extend(field)
        return bytes(out)

    sig_payload = _signature_payload_v2(
        1, sender_pub_bytes, ephemeral_pub_bytes, wrap_nonce, wrapped_key, payload_nonce, ciphertext
    )
    signature = sign_message(sender_signing_private, sig_payload)

    # Construct the envelope manually
    envelope = Envelope(
        version=1,
        sender_public_key=sender_pub_bytes,
        ephemeral_public_key=ephemeral_pub_bytes,
        wrap_nonce=wrap_nonce,
        wrapped_key=wrapped_key,
        payload_nonce=payload_nonce,
        ciphertext=ciphertext,
        signature=signature,
    )
    envelope.envelope_id = compute_envelope_id(envelope)

    # Now decrypt using the standard HybridEnvelope.decrypt method
    # This should:
    # 1. Try primary salt (_HKDF_SALT) -> FAIL
    # 2. Try legacy (salt=None) -> FAIL
    # 3. Try intermediate salt (_HKDF_SALT_INTERMEDIATE) -> SUCCESS
    decrypted = HybridEnvelope.decrypt(envelope, server_private)

    assert decrypted == original_payload, (
        f"Decryption with intermediate salt fallback failed: "
        f"expected {original_payload!r}, got {decrypted!r}"
    )
