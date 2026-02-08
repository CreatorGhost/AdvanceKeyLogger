# E2E Server/Client Architecture — Gaps & Missing Features

Comprehensive list of gaps identified in the `server/`, `crypto/`, and related transport
modules. Each item includes the affected file(s), what's missing, and what the fix involves.

---

## Server-Side Gaps (`server/`)

### 1. No Client Authentication on `/ingest`

- **File:** `server/app.py:22-42`
- **Problem:** The `/ingest` endpoint is completely open. Anyone who knows (or guesses) the
  server URL can POST encrypted envelopes. There is no API key, bearer token, mTLS, or any
  other authentication mechanism.
- **What to implement:**
  - Add an `Authorization: Bearer <token>` header check, OR
  - Add API key validation via `X-API-Key` header, OR
  - Implement mTLS (mutual TLS) so only clients with valid certificates can connect
  - Store allowed tokens/keys in server config under e.g. `e2e_server.auth_tokens: [...]`
  - Return `401 Unauthorized` for missing/invalid credentials

### 2. No Client Public Key Registration / Allowlist

- **File:** `server/app.py:28-33`, `crypto/envelope.py:137`
- **Problem:** The server accepts envelopes from ANY `sender_public_key`. During decryption
  (`HybridEnvelope.decrypt`), it reconstructs the sender's Ed25519 public key from whatever
  is in the envelope and verifies the signature against *that same key*. This means any
  attacker who generates their own Ed25519 keypair can create valid-looking envelopes.
  Signature verification only proves the envelope wasn't tampered with — not that the sender
  is authorized.
- **What to implement:**
  - Add a `known_clients` registry (file or config) mapping client IDs to their Ed25519 public keys
  - On `/ingest`, after parsing the envelope, check that `envelope.sender_public_key` is in the allowlist
  - Add a `/register` endpoint (or manual config) for new clients to register their public key
  - Return `403 Forbidden` for unregistered sender keys

### 3. No Rate Limiting on `/ingest`

- **File:** `server/app.py:22`
- **Problem:** No rate limiting means a single client (or attacker) can flood the endpoint
  with requests, consuming disk space and CPU (decryption is not free).
- **What to implement:**
  - Add middleware or dependency that limits requests per IP per time window
  - Consider using `slowapi` or a simple in-memory token bucket
  - Return `429 Too Many Requests` when limit exceeded

### 4. No Payload Size Limit on `/ingest`

- **File:** `server/app.py:25`
- **Problem:** `await request.body()` reads the entire request body into memory with no
  upper bound. A malicious client could send a multi-GB body to exhaust server memory.
- **What to implement:**
  - Check `Content-Length` header before reading body
  - Set a max payload size (e.g. 10 MB) in config: `e2e_server.max_payload_bytes: 10485760`
  - Return `413 Payload Too Large` if exceeded
  - Also configure uvicorn's `--limit-max-request-size` flag

### 5. No Storage Rotation / Cleanup

- **File:** `server/storage.py:20-35`
- **Problem:** `store_payload()` writes files to `storage_dir` indefinitely. There is no
  mechanism to delete old payloads, rotate storage, or enforce a maximum directory size.
  The disk will eventually fill up.
- **What to implement:**
  - Add `max_storage_mb` config option
  - Add `retention_hours` config option (auto-delete payloads older than N hours)
  - Implement a cleanup function that runs periodically (background task or cron)
  - Consider using the existing `StorageManager` pattern from `storage/manager.py`

### 6. Response Leaks Internal File Path

- **File:** `server/app.py:38-39`
- **Problem:** The `/ingest` response includes `"path": str(path)`, which exposes the
  server's internal filesystem path to the client. This is an information disclosure issue.
- **What to implement:**
  - Remove `path` from the response, or replace it with just the filename (no directory)
  - Only return: `{"status": "stored", "bytes": len(payload)}`

### 7. No Logging / Audit Trail

- **File:** `server/app.py`
- **Problem:** Successful ingestions are not logged. Failed decryptions log nothing beyond
  the HTTP 400. There is no audit trail of who sent what, when, and whether it succeeded.
- **What to implement:**
  - Log on successful ingest: timestamp, sender_public_key (base64), payload size, stored filename
  - Log on failed ingest: timestamp, error reason, client IP
  - Consider a structured audit log file separate from application logs

### 8. No TLS / HTTPS Configuration

- **File:** `server/run.py:50`
- **Problem:** The server runs plain HTTP (`uvicorn.run(app, host, port)`). While the E2E
  encryption protects payload confidentiality, running without TLS means:
  - API keys/tokens (if added) would be sent in cleartext
  - No server identity verification for the client
  - Susceptible to connection hijacking
- **What to implement:**
  - Add `ssl_certfile` and `ssl_keyfile` config options
  - Pass them to `uvicorn.run(app, host, port, ssl_certfile=..., ssl_keyfile=...)`
  - Document how to generate self-signed certs or use Let's Encrypt

---

## Crypto / Envelope Gaps (`crypto/`)

### 9. Signature Delimiter Ambiguity

- **File:** `crypto/envelope.py:182-192`
- **Problem:** `_signature_payload()` joins binary fields with `b"|"`. Since the fields are
  arbitrary binary data, a `0x7C` byte (the `|` character) could theoretically appear within
  a field, making the encoding ambiguous. While extremely unlikely with random crypto bytes,
  it's not cryptographically rigorous.
- **What to implement:**
  - Use length-prefixed encoding instead of delimiter-based:
    ```
    for each field: [4-byte big-endian length][field bytes]
    ```
  - This makes parsing unambiguous regardless of field contents
  - NOTE: This is a breaking change to the envelope format — requires a version bump to `2`

### 10. No Nonce Length Validation

- **File:** `crypto/envelope.py:44-68` (in `from_bytes`)
- **Problem:** AES-GCM requires 12-byte nonces. The `from_bytes()` method decodes
  `wrap_nonce` and `payload_nonce` from base64 but never validates they are exactly 12 bytes.
  A malformed envelope with wrong-length nonces would fail deep inside the cryptography
  library with an opaque error.
- **What to implement:**
  - After decoding, check: `len(wrap_nonce) == 12` and `len(payload_nonce) == 12`
  - Also validate: `len(sender_public_key) == 32` and `len(ephemeral_public_key) == 32`
  - Raise a clear `ValueError` with the field name and expected vs actual length

### 11. No Replay Protection

- **File:** `server/app.py:22-42`, `crypto/envelope.py`
- **Problem:** The same valid envelope can be POSTed to `/ingest` multiple times and will
  be accepted and stored each time. There is no nonce/ID tracking to detect replays.
- **What to implement:**
  - Add a unique `envelope_id` field (e.g. UUID or hash of the envelope) to the Envelope dataclass
  - Server-side: maintain a seen-IDs set (in-memory with TTL, or persistent)
  - Reject envelopes with previously-seen IDs
  - Alternative: use a timestamp field and reject envelopes older than N minutes

### 12. Key Rotation Not Implemented

- **File:** `config/default_config.yaml:91`, `crypto/protocol.py`
- **Problem:** The config has `key_rotation_hours: 24` but this value is never read or acted
  upon anywhere. Client keys (`AgentKeyPair`) are generated once and used forever. Server
  keys are also static.
- **What to implement:**
  - In `E2EProtocol.__init__()`: check key age against `key_rotation_hours`
  - If keys are older than the configured period, generate new ones
  - Store key creation timestamp alongside the key material
  - For server keys: implement a graceful rotation where both old and new keys are accepted
    during a transition period

### 13. HKDF Salt is None

- **File:** `crypto/envelope.py:163-170`
- **Problem:** `_derive_wrap_key()` uses `salt=None` in HKDF. While HKDF with no salt is
  still secure (it uses a zero-filled salt internally), using a random or fixed application-
  specific salt improves domain separation.
- **What to implement:**
  - Use a fixed application-specific salt, e.g.:
    ```python
    salt=b"AdvanceKeyLogger-E2E-v1"
    ```
  - Or derive a per-envelope salt from the ephemeral public key
  - NOTE: This is a breaking change — requires version bump

### 14. No Associated Data Binding Sender Identity

- **File:** `crypto/envelope.py:86,95`
- **Problem:** The AES-GCM additional authenticated data (AAD) uses static strings
  (`b"AKL-PAYLOAD"`, `b"AKL-WRAP"`). The sender's identity is not bound to the AAD, so if
  two different senders happen to produce the same shared secret (impossible in practice but
  a theoretical concern), their ciphertexts would be interchangeable.
- **What to implement:**
  - Include sender public key in AAD:
    ```python
    aad = b"AKL-PAYLOAD|" + sender_pub_bytes
    ```
  - This cryptographically binds the ciphertext to the sender's identity

---

## Client-Side Gaps (`crypto/protocol.py`, `transport/`)

### 15. Unused Export Methods

- **File:** `crypto/protocol.py:54-66`
- **Problem:** `export_sender_public_key()` and `export_exchange_public_key()` exist but are
  never called anywhere in the codebase. If they're intended for client registration with the
  server (gap #2), they need to be wired up.
- **What to implement:**
  - Wire these into the client startup flow to print/save the public keys
  - Use them during client registration with the server
  - Or remove them if not needed

### 16. No Envelope Sequence Numbering

- **File:** `crypto/envelope.py`
- **Problem:** Envelopes have no sequence number or timestamp. This means:
  - Server cannot detect missing/dropped envelopes
  - Server cannot enforce ordering
  - Duplicates are indistinguishable from separate events
- **What to implement:**
  - Add `sequence: int` field to the Envelope dataclass
  - Client increments sequence on each send (persist across restarts)
  - Server tracks last-seen sequence per sender and alerts on gaps

### 17. No Server Identity Verification on Client

- **File:** `crypto/protocol.py:37-52`, `transport/http_transport.py`
- **Problem:** The client pins the server's X25519 public key (for envelope encryption) but
  has no way to verify the HTTP server it connects to is actually the intended server. Without
  TLS certificate verification, a network attacker could intercept the connection.
- **What to implement:**
  - Enable TLS certificate verification in `HttpTransport` (don't set `verify=False`)
  - Add a `ca_cert` or `server_cert` config option for custom CA bundles
  - Optionally implement certificate pinning

### 18. Client Has No Connection Health Check

- **File:** `transport/http_transport.py`
- **Problem:** The HTTP transport has no way to verify the server is reachable and healthy
  before sending a large encrypted payload. If the server is down, the client wastes CPU
  encrypting data that can't be delivered.
- **What to implement:**
  - Before first send (or periodically), call `GET /health` on the server
  - Cache the health status with a TTL
  - Skip encryption if server is known to be unreachable (queue plaintext for later)

---

## Config / Documentation Gaps

### 19. No Server-Side Config Schema Documentation

- **File:** `config/default_config.yaml`, `server/run.py`
- **Problem:** The `default_config.yaml` documents client-side E2E config but there is no
  equivalent for server-side config. The server config structure (`e2e_server` key in YAML)
  is undocumented.
- **What to implement:**
  - Create `config/server_config.example.yaml` with all server options:
    ```yaml
    e2e_server:
      key_store_path: "~/.advancekeylogger/server_keys/"
      storage_dir: "./server_data"
      max_payload_bytes: 10485760
      max_storage_mb: 1000
      retention_hours: 168
      auth_tokens:
        - "token-1-here"
      ssl_certfile: ""
      ssl_keyfile: ""
      rate_limit_per_minute: 60
    ```

### 20. No Error Recovery Documentation

- **Problem:** If the server key is lost, all pinned clients will refuse to connect (pin
  mismatch). There is no documented recovery procedure.
- **What to document:**
  - How to regenerate server keys
  - How to clear pinned keys on clients (`server_public_key.key` in the client key store)
  - How to migrate to new keys gracefully

---

## Priority Order for Implementation

| Priority | Gap # | Description | Effort |
|----------|-------|-------------|--------|
| **Critical** | 4 | Payload size limit | Low |
| **Critical** | 6 | Remove path from response | Low |
| **High** | 1 | Client authentication (API key) | Medium |
| **High** | 2 | Client public key allowlist | Medium |
| **High** | 3 | Rate limiting | Low |
| **High** | 5 | Storage rotation/cleanup | Medium |
| **High** | 10 | Nonce/key length validation | Low |
| **Medium** | 7 | Audit logging | Low |
| **Medium** | 8 | TLS/HTTPS support | Medium |
| **Medium** | 11 | Replay protection | Medium |
| **Medium** | 12 | Key rotation | High |
| **Medium** | 17 | Server identity verification | Medium |
| **Medium** | 18 | Client health check | Low |
| **Low** | 9 | Signature delimiter fix | Low (but breaking) |
| **Low** | 13 | HKDF salt improvement | Low (but breaking) |
| **Low** | 14 | Sender identity in AAD | Low (but breaking) |
| **Low** | 15 | Wire up export methods | Low |
| **Low** | 16 | Envelope sequence numbers | Medium |
| **Low** | 19 | Server config docs | Low |
| **Low** | 20 | Error recovery docs | Low |

---

*20 gaps identified. Items marked "breaking" require an envelope version bump to `2`.*
