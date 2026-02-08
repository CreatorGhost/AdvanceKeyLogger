"""
Hybrid envelope encryption using X25519 + AES-256-GCM.
"""
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from crypto.signer import sign_message, verify_message


@dataclass
class Envelope:
    version: int
    sender_public_key: bytes
    ephemeral_public_key: bytes
    wrap_nonce: bytes
    wrapped_key: bytes
    payload_nonce: bytes
    ciphertext: bytes
    signature: bytes

    def to_bytes(self) -> bytes:
        payload = {
            "version": self.version,
            "sender_public_key": _b64(self.sender_public_key),
            "ephemeral_public_key": _b64(self.ephemeral_public_key),
            "wrap_nonce": _b64(self.wrap_nonce),
            "wrapped_key": _b64(self.wrapped_key),
            "payload_nonce": _b64(self.payload_nonce),
            "ciphertext": _b64(self.ciphertext),
            "signature": _b64(self.signature),
        }
        return json.dumps(payload, ensure_ascii=True).encode("utf-8")

    @staticmethod
    def from_bytes(data: bytes) -> Envelope:
        try:
            raw = json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError(f"Invalid envelope data: {exc}") from exc
        required = [
            "sender_public_key", "ephemeral_public_key", "wrap_nonce",
            "wrapped_key", "payload_nonce", "ciphertext", "signature",
        ]
        missing = [k for k in required if not raw.get(k)]
        if missing:
            raise ValueError(f"Envelope missing required fields: {missing}")
        try:
            return Envelope(
                version=int(raw.get("version", 1)),
                sender_public_key=_b64_decode(raw["sender_public_key"]),
                ephemeral_public_key=_b64_decode(raw["ephemeral_public_key"]),
                wrap_nonce=_b64_decode(raw["wrap_nonce"]),
                wrapped_key=_b64_decode(raw["wrapped_key"]),
                payload_nonce=_b64_decode(raw["payload_nonce"]),
                ciphertext=_b64_decode(raw["ciphertext"]),
                signature=_b64_decode(raw["signature"]),
            )
        except Exception as exc:
            raise ValueError(f"Invalid envelope field encoding: {exc}") from exc


class HybridEnvelope:
    """Encrypt/decrypt payloads using X25519 key agreement + AES-GCM."""

    def __init__(self, server_public_key: x25519.X25519PublicKey) -> None:
        self._server_public_key = server_public_key

    def encrypt(
        self,
        payload: bytes,
        sender_signing_key: ed25519.Ed25519PrivateKey,
        sender_public_key: ed25519.Ed25519PublicKey,
    ) -> Envelope:
        data_key = AESGCM.generate_key(bit_length=256)
        payload_nonce = os.urandom(12)
        aesgcm_payload = AESGCM(data_key)
        ciphertext = aesgcm_payload.encrypt(payload_nonce, payload, b"AKL-PAYLOAD")

        ephemeral_private = x25519.X25519PrivateKey.generate()
        ephemeral_public = ephemeral_private.public_key()
        shared_secret = ephemeral_private.exchange(self._server_public_key)

        wrap_key = _derive_wrap_key(shared_secret)
        wrap_nonce = os.urandom(12)
        aesgcm_wrap = AESGCM(wrap_key)
        wrapped_key = aesgcm_wrap.encrypt(wrap_nonce, data_key, b"AKL-WRAP")

        sender_pub_bytes = sender_public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        ephemeral_pub_bytes = ephemeral_public.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

        signature_payload = _signature_payload(
            sender_pub_bytes,
            ephemeral_pub_bytes,
            wrap_nonce,
            wrapped_key,
            payload_nonce,
            ciphertext,
        )
        signature = sign_message(sender_signing_key, signature_payload)

        return Envelope(
            version=1,
            sender_public_key=sender_pub_bytes,
            ephemeral_public_key=ephemeral_pub_bytes,
            wrap_nonce=wrap_nonce,
            wrapped_key=wrapped_key,
            payload_nonce=payload_nonce,
            ciphertext=ciphertext,
            signature=signature,
        )

    @staticmethod
    def decrypt(
        envelope: Envelope,
        server_private_key: x25519.X25519PrivateKey,
        verify_signature: bool = True,
    ) -> bytes:
        sender_public = ed25519.Ed25519PublicKey.from_public_bytes(envelope.sender_public_key)
        if verify_signature:
            signature_payload = _signature_payload(
                envelope.sender_public_key,
                envelope.ephemeral_public_key,
                envelope.wrap_nonce,
                envelope.wrapped_key,
                envelope.payload_nonce,
                envelope.ciphertext,
            )
            if not verify_message(sender_public, signature_payload, envelope.signature):
                raise ValueError("Invalid envelope signature")

        ephemeral_public = x25519.X25519PublicKey.from_public_bytes(
            envelope.ephemeral_public_key
        )
        shared_secret = server_private_key.exchange(ephemeral_public)
        wrap_key = _derive_wrap_key(shared_secret)
        aesgcm_wrap = AESGCM(wrap_key)
        data_key = aesgcm_wrap.decrypt(envelope.wrap_nonce, envelope.wrapped_key, b"AKL-WRAP")

        aesgcm_payload = AESGCM(data_key)
        return aesgcm_payload.decrypt(envelope.payload_nonce, envelope.ciphertext, b"AKL-PAYLOAD")


def _derive_wrap_key(shared_secret: bytes) -> bytes:
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"AKL-E2E-WRAP",
    )
    return hkdf.derive(shared_secret)


def _signature_payload(
    sender_pub: bytes,
    ephemeral_pub: bytes,
    wrap_nonce: bytes,
    wrapped_key: bytes,
    payload_nonce: bytes,
    ciphertext: bytes,
) -> bytes:
    return b"|".join(
        [
            sender_pub,
            ephemeral_pub,
            wrap_nonce,
            wrapped_key,
            payload_nonce,
            ciphertext,
        ]
    )


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")


def _b64_decode(value: str) -> bytes:
    if not value:
        return b""
    return base64.b64decode(value.encode("utf-8"))

