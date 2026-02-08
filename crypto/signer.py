"""
Ed25519 signing helpers.
"""
from __future__ import annotations

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519


def sign_message(private_key: ed25519.Ed25519PrivateKey, message: bytes) -> bytes:
    return private_key.sign(message)


def verify_message(
    public_key: ed25519.Ed25519PublicKey, message: bytes, signature: bytes
) -> bool:
    try:
        public_key.verify(signature, message)
        return True
    except InvalidSignature:
        return False
