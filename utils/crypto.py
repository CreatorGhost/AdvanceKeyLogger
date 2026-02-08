"""
Encryption and decryption utilities using AES-256-CBC.

Provides symmetric encryption with proper key derivation,
random initialization vectors, and PKCS7 padding.

Dependencies:
    pip install cryptography

Usage:
    from utils.crypto import generate_key, encrypt, decrypt, derive_key_from_password

    # With a random key
    key = generate_key()
    ciphertext = encrypt(b"secret data", key)
    plaintext = decrypt(ciphertext, key)

    # With a password-derived key
    key, salt = derive_key_from_password("my-password")
    ciphertext = encrypt(b"secret data", key)
    # Save the salt! You need it to derive the same key for decryption.
    key2, _ = derive_key_from_password("my-password", salt=salt)
    plaintext = decrypt(ciphertext, key2)
"""
from __future__ import annotations

import base64
import logging
import os

from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


def generate_key() -> bytes:
    """
    Generate a random 256-bit AES key.

    Returns:
        32 bytes of cryptographically secure random data.
    """
    key = os.urandom(32)
    logger.debug("Generated new AES-256 key")
    return key


def key_to_base64(key: bytes) -> str:
    """Encode a key as a base64 string (for safe storage in config files)."""
    return base64.b64encode(key).decode("utf-8")


def key_from_base64(encoded: str) -> bytes:
    """Decode a base64-encoded key back to bytes."""
    return base64.b64decode(encoded.encode("utf-8"))


def derive_key_from_password(
    password: str, salt: bytes | None = None
) -> tuple[bytes, bytes]:
    """
    Derive an encryption key from a password using PBKDF2-HMAC-SHA256.

    PBKDF2 makes brute-force attacks expensive by running many iterations
    of the hash function.

    Args:
        password: Human-memorable password string.
        salt: Random salt bytes. Generated if None. MUST be stored for
              later decryption — without the same salt, you can't derive
              the same key.

    Returns:
        Tuple of (derived_key, salt).
    """
    if salt is None:
        salt = os.urandom(16)

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480_000,
    )
    key = kdf.derive(password.encode("utf-8"))
    logger.debug("Derived key from password (salt=%s)", base64.b64encode(salt).decode())
    return key, salt


def encrypt(data: bytes, key: bytes) -> bytes:
    """
    Encrypt data using AES-256-CBC.

    Output format: [16-byte IV][ciphertext]

    The IV (Initialization Vector) is randomly generated each time,
    so encrypting the same data twice produces different output.

    Args:
        data: Plaintext bytes to encrypt.
        key: 32-byte AES key.

    Returns:
        IV + ciphertext as bytes.
    """
    iv = os.urandom(16)

    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(data) + padder.finalize()

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()

    result = iv + ciphertext
    logger.debug("Encrypted %d bytes -> %d bytes", len(data), len(result))
    return result


def decrypt(data: bytes, key: bytes) -> bytes:
    """
    Decrypt data that was encrypted with encrypt().

    Reads the 16-byte IV from the beginning, then decrypts the rest.

    Args:
        data: IV + ciphertext bytes (output of encrypt()).
        key: Same 32-byte AES key used for encryption.

    Returns:
        Original plaintext bytes.

    Raises:
        ValueError: If data is too short or padding is invalid (wrong key).
    """
    if len(data) < 17:
        raise ValueError("Encrypted data too short (must be at least 17 bytes)")

    iv = data[:16]
    ciphertext = data[16:]

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded_data = decryptor.update(ciphertext) + decryptor.finalize()

    unpadder = padding.PKCS7(128).unpadder()
    plaintext = unpadder.update(padded_data) + unpadder.finalize()

    logger.debug("Decrypted %d bytes -> %d bytes", len(data), len(plaintext))
    return plaintext
