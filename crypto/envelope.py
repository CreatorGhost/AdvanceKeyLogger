"""
Hybrid envelope encryption using X25519 + AES-256-GCM.
"""
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from crypto.signer import sign_message, verify_message

_HKDF_SALT = b"x25519-e2e-hkdf-v1"


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
    envelope_id: str | None = None
    sequence: int | None = None
    sent_at: float | None = None

    def to_bytes(self) -> bytes:
        payload: dict[str, Any] = {
            "version": self.version,
            "sender_public_key": _b64(self.sender_public_key),
            "ephemeral_public_key": _b64(self.ephemeral_public_key),
            "wrap_nonce": _b64(self.wrap_nonce),
            "wrapped_key": _b64(self.wrapped_key),
            "payload_nonce": _b64(self.payload_nonce),
            "ciphertext": _b64(self.ciphertext),
            "signature": _b64(self.signature),
        }
        if self.envelope_id:
            payload["envelope_id"] = self.envelope_id
        if self.sequence is not None:
            payload["sequence"] = self.sequence
        if self.sent_at is not None:
            payload["sent_at"] = self.sent_at
        return json.dumps(payload, ensure_ascii=True).encode("utf-8")

    @staticmethod
    def from_bytes(data: bytes) -> Envelope:
        try:
            raw = json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError(f"Invalid envelope data: {exc}") from exc

        required = [
            "sender_public_key",
            "ephemeral_public_key",
            "wrap_nonce",
            "wrapped_key",
            "payload_nonce",
            "ciphertext",
            "signature",
        ]
        missing = [k for k in required if not raw.get(k)]
        if missing:
            raise ValueError(f"Envelope missing required fields: {missing}")

        try:
            envelope = Envelope(
                version=int(raw.get("version", 1)),
                sender_public_key=_b64_decode(raw["sender_public_key"]),
                ephemeral_public_key=_b64_decode(raw["ephemeral_public_key"]),
                wrap_nonce=_b64_decode(raw["wrap_nonce"]),
                wrapped_key=_b64_decode(raw["wrapped_key"]),
                payload_nonce=_b64_decode(raw["payload_nonce"]),
                ciphertext=_b64_decode(raw["ciphertext"]),
                signature=_b64_decode(raw["signature"]),
                envelope_id=raw.get("envelope_id"),
                sequence=_safe_int(raw.get("sequence")),
                sent_at=_safe_float(raw.get("sent_at")),
            )
        except Exception as exc:
            raise ValueError(f"Invalid envelope field encoding: {exc}") from exc

        _validate_lengths(envelope)
        return envelope


class HybridEnvelope:
    """Encrypt/decrypt payloads using X25519 key agreement + AES-GCM."""

    def __init__(self, server_public_key: x25519.X25519PublicKey) -> None:
        self._server_public_key = server_public_key

    def encrypt(
        self,
        payload: bytes,
        sender_signing_key: ed25519.Ed25519PrivateKey,
        sender_public_key: ed25519.Ed25519PublicKey,
        sequence: int | None = None,
        sent_at: float | None = None,
    ) -> Envelope:
        data_key = AESGCM.generate_key(bit_length=256)
        payload_nonce = os.urandom(12)

        ephemeral_private = x25519.X25519PrivateKey.generate()
        ephemeral_public = ephemeral_private.public_key()
        shared_secret = ephemeral_private.exchange(self._server_public_key)

        sender_pub_bytes = sender_public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        payload_aad = _payload_aad(sender_pub_bytes)
        aesgcm_payload = AESGCM(data_key)
        ciphertext = aesgcm_payload.encrypt(payload_nonce, payload, payload_aad)

        wrap_key = _derive_wrap_key(shared_secret, legacy=False)
        wrap_nonce = os.urandom(12)
        aesgcm_wrap = AESGCM(wrap_key)
        wrapped_key = aesgcm_wrap.encrypt(
            wrap_nonce,
            data_key,
            _wrap_aad(sender_pub_bytes),
        )

        ephemeral_pub_bytes = ephemeral_public.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

        signature_payload = _signature_payload_v2(
            1,
            sender_pub_bytes,
            ephemeral_pub_bytes,
            wrap_nonce,
            wrapped_key,
            payload_nonce,
            ciphertext,
        )
        signature = sign_message(sender_signing_key, signature_payload)

        envelope = Envelope(
            version=1,
            sender_public_key=sender_pub_bytes,
            ephemeral_public_key=ephemeral_pub_bytes,
            wrap_nonce=wrap_nonce,
            wrapped_key=wrapped_key,
            payload_nonce=payload_nonce,
            ciphertext=ciphertext,
            signature=signature,
            sequence=sequence,
            sent_at=sent_at,
        )
        envelope.envelope_id = compute_envelope_id(envelope)
        return envelope

    @staticmethod
    def decrypt(
        envelope: Envelope,
        server_private_key: x25519.X25519PrivateKey,
        verify_signature: bool = True,
    ) -> bytes:
        if envelope.version != 1:
            raise ValueError(f"Unsupported envelope version: {envelope.version}")
        sender_public = ed25519.Ed25519PublicKey.from_public_bytes(
            envelope.sender_public_key
        )
        if verify_signature and not _verify_signature(envelope, sender_public):
            raise ValueError("Invalid envelope signature")

        ephemeral_public = x25519.X25519PublicKey.from_public_bytes(
            envelope.ephemeral_public_key
        )
        shared_secret = server_private_key.exchange(ephemeral_public)

        wrap_key = _derive_wrap_key(shared_secret, legacy=False)
        data_key = _decrypt_wrapped_key(envelope, wrap_key)
        if data_key is None:
            wrap_key = _derive_wrap_key(shared_secret, legacy=True)
            data_key = _decrypt_wrapped_key(envelope, wrap_key)
            if data_key is None:
                raise ValueError("Failed to unwrap data key")

        payload = _decrypt_payload(envelope, data_key)
        if payload is None:
            raise ValueError("Failed to decrypt payload")
        return payload


def _derive_wrap_key(shared_secret: bytes, legacy: bool) -> bytes:
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None if legacy else _HKDF_SALT,
        info=b"E2E-WRAP-V1",
    )
    return hkdf.derive(shared_secret)


def _signature_payload_v2(
    version: int,
    sender_pub: bytes,
    ephemeral_pub: bytes,
    wrap_nonce: bytes,
    wrapped_key: bytes,
    payload_nonce: bytes,
    ciphertext: bytes,
) -> bytes:
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


def _signature_payload_legacy(
    version: int,
    sender_pub: bytes,
    ephemeral_pub: bytes,
    wrap_nonce: bytes,
    wrapped_key: bytes,
    payload_nonce: bytes,
    ciphertext: bytes,
) -> bytes:
    return b"|".join(
        [
            version.to_bytes(4, "big"),
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


def _payload_aad(sender_pub: bytes, legacy: bool = False) -> bytes:
    if legacy:
        return b"AKL-PAYLOAD"  # original AAD required for legacy decryption
    return b"PAYLOAD-V1|" + sender_pub


def _wrap_aad(sender_pub: bytes, legacy: bool = False) -> bytes:
    if legacy:
        return b"AKL-WRAP"  # original AAD required for legacy decryption
    return b"WRAP-V1|" + sender_pub


def _decrypt_wrapped_key(envelope: Envelope, wrap_key: bytes) -> bytes | None:
    aesgcm_wrap = AESGCM(wrap_key)
    try:
        return aesgcm_wrap.decrypt(
            envelope.wrap_nonce,
            envelope.wrapped_key,
            _wrap_aad(envelope.sender_public_key),
        )
    except InvalidTag:
        try:
            return aesgcm_wrap.decrypt(
                envelope.wrap_nonce,
                envelope.wrapped_key,
                _wrap_aad(envelope.sender_public_key, legacy=True),
            )
        except InvalidTag:
            return None


def _decrypt_payload(envelope: Envelope, data_key: bytes) -> bytes | None:
    aesgcm_payload = AESGCM(data_key)
    try:
        return aesgcm_payload.decrypt(
            envelope.payload_nonce,
            envelope.ciphertext,
            _payload_aad(envelope.sender_public_key),
        )
    except InvalidTag:
        try:
            return aesgcm_payload.decrypt(
                envelope.payload_nonce,
                envelope.ciphertext,
                _payload_aad(envelope.sender_public_key, legacy=True),
            )
        except InvalidTag:
            return None


def _verify_signature(envelope: Envelope, sender_public: ed25519.Ed25519PublicKey) -> bool:
    payload = _signature_payload_v2(
        envelope.version,
        envelope.sender_public_key,
        envelope.ephemeral_public_key,
        envelope.wrap_nonce,
        envelope.wrapped_key,
        envelope.payload_nonce,
        envelope.ciphertext,
    )
    if verify_message(sender_public, payload, envelope.signature):
        return True
    legacy = _signature_payload_legacy(
        envelope.version,
        envelope.sender_public_key,
        envelope.ephemeral_public_key,
        envelope.wrap_nonce,
        envelope.wrapped_key,
        envelope.payload_nonce,
        envelope.ciphertext,
    )
    return verify_message(sender_public, legacy, envelope.signature)


def compute_envelope_id(envelope: Envelope) -> str:
    digest = hashes.Hash(hashes.SHA256())
    digest.update(envelope.sender_public_key)
    digest.update(envelope.ephemeral_public_key)
    digest.update(envelope.wrap_nonce)
    digest.update(envelope.wrapped_key)
    digest.update(envelope.payload_nonce)
    digest.update(envelope.ciphertext)
    digest.update(envelope.signature)
    return digest.finalize().hex()


def _validate_lengths(envelope: Envelope) -> None:
    if len(envelope.sender_public_key) != 32:
        raise ValueError("sender_public_key must be 32 bytes")
    if len(envelope.ephemeral_public_key) != 32:
        raise ValueError("ephemeral_public_key must be 32 bytes")
    if len(envelope.wrap_nonce) != 12:
        raise ValueError("wrap_nonce must be 12 bytes")
    if len(envelope.payload_nonce) != 12:
        raise ValueError("payload_nonce must be 12 bytes")
    if len(envelope.signature) != 64:
        raise ValueError("signature must be 64 bytes")
    if len(envelope.wrapped_key) < 16:
        raise ValueError("wrapped_key too short (min 16 bytes for GCM tag)")
    if len(envelope.ciphertext) < 16:
        raise ValueError("ciphertext too short (min 16 bytes for GCM tag)")


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
