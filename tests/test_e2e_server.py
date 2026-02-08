"""Tests for E2E server helpers."""
from __future__ import annotations

from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
from fastapi.testclient import TestClient

from crypto.envelope import Envelope, HybridEnvelope
from crypto.protocol import E2EProtocol
from server.app import create_app
from server.keys import generate_server_keypair, load_server_private_key
from server.storage import detect_extension, store_payload


def test_generate_and_load_server_keys(tmp_path: Path):
    public_key_b64 = generate_server_keypair(str(tmp_path))
    assert public_key_b64

    config = {"key_store_path": str(tmp_path)}
    private_key = load_server_private_key(config)
    assert isinstance(private_key, x25519.X25519PrivateKey)


def test_auto_generate_keys_when_missing(tmp_path: Path):
    config = {"key_store_path": str(tmp_path / "auto")}
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

    signing_private = ed25519.Ed25519PrivateKey.generate()
    signing_public = signing_private.public_key()

    envelope = HybridEnvelope(server_public).encrypt(
        b"payload", signing_private, signing_public
    )
    data = envelope.to_bytes()
    parsed = Envelope.from_bytes(data)
    plaintext = HybridEnvelope.decrypt(parsed, server_private)
    assert plaintext == b"payload"


def test_ingest_endpoint_e2e(tmp_path: Path):
    """Full HTTP round-trip: client encrypts -> POST /ingest -> server decrypts."""
    # Generate server keys
    public_key_b64 = generate_server_keypair(str(tmp_path / "server_keys"))

    server_config = {
        "key_store_path": str(tmp_path / "server_keys"),
        "storage_dir": str(tmp_path / "storage"),
    }
    app = create_app(server_config)
    client = TestClient(app)

    # Client encrypts using E2EProtocol
    client_config = {
        "server_public_key": public_key_b64,
        "key_store_path": str(tmp_path / "client_keys"),
        "pin_server_key": True,
    }
    protocol = E2EProtocol(client_config)
    encrypted = protocol.encrypt(b'{"events": [1, 2, 3]}')

    # POST to /ingest
    response = client.post("/ingest", content=encrypted)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "stored"
    assert body["bytes"] > 0


def test_ingest_endpoint_rejects_empty(tmp_path: Path):
    public_key_b64 = generate_server_keypair(str(tmp_path / "keys"))
    config = {"key_store_path": str(tmp_path / "keys"), "storage_dir": str(tmp_path)}
    app = create_app(config)
    client = TestClient(app)

    response = client.post("/ingest", content=b"")
    assert response.status_code == 400


def test_ingest_endpoint_rejects_malformed(tmp_path: Path):
    public_key_b64 = generate_server_keypair(str(tmp_path / "keys"))
    config = {"key_store_path": str(tmp_path / "keys"), "storage_dir": str(tmp_path)}
    app = create_app(config)
    client = TestClient(app)

    response = client.post("/ingest", content=b"not valid json")
    assert response.status_code == 400
    assert "invalid envelope" in response.json()["detail"]


def test_health_endpoint(tmp_path: Path):
    public_key_b64 = generate_server_keypair(str(tmp_path / "keys"))
    config = {"key_store_path": str(tmp_path / "keys"), "storage_dir": str(tmp_path)}
    app = create_app(config)
    client = TestClient(app)

    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
