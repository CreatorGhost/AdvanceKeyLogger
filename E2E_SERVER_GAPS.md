# E2E Server/Client Architecture — Review Round 2

**Status:** You fixed 16 of the original 20 gaps. This document covers the 13 NEW bugs
and issues found in the updated implementation, plus the 4 original gaps still open.

**Tests:** 143 passed, 72 skipped (macOS-only).

---

## What You Successfully Implemented (Original Gaps Fixed)

| Original Gap | Status |
|-------------|--------|
| 1. Client authentication (`server/auth.py`) | DONE |
| 2. Client public key allowlist (`server/clients.py`) | DONE |
| 3. Rate limiting (`server/rate_limit.py`) | DONE |
| 4. Payload size limit (`_read_body_limited`) | DONE |
| 5. Storage rotation/cleanup (`cleanup_storage`) | DONE |
| 6. Response no longer leaks full path | DONE (returns `filename` only) |
| 7. Audit logging (`server/audit.py`) | DONE |
| 9. Length-prefixed signature (`_signature_payload_v2`) | DONE |
| 10. Nonce/key length validation (`_validate_lengths`) | DONE |
| 11. Replay protection (`server/replay.py`) | DONE |
| 12. Key rotation (client + server) | DONE |
| 13. HKDF salt (`_HKDF_SALT`) | DONE |
| 14. Sender identity bound in AAD (`_payload_aad`, `_wrap_aad`) | DONE |
| 15. Export methods wired up (`export_client_keys`, `save_client_keys`) | DONE |
| 16. Envelope sequence numbering | DONE |
| 18. Client health check (`preflight()`) | DONE |

---

## Remaining Original Gaps (4 still open)

### Original #8: No TLS / HTTPS Configuration

- **File:** `server/run.py`
- **Problem:** Server still runs plain HTTP. Auth tokens (Bearer/API-Key) are sent in
  cleartext over the wire.
- **What to do:** Pass `ssl_certfile` and `ssl_keyfile` to `uvicorn.run()` when configured.

### Original #17: No Server Identity Verification on Client

- **File:** `transport/http_transport.py:28`
- **Problem:** `verify` defaults to `True` (good), but there is no config option for custom
  CA certificates. Self-signed server certs will fail unless `verify: false` is set, which
  disables all TLS verification.
- **What to do:** Add a `ca_cert` config option and pass it as `verify=ca_cert_path`.

### Original #19: Server Config Schema Documentation

- **File:** `config/server_config.example.yaml`, `server/config.example.yaml`
- **Problem:** Two duplicate example configs exist. Neither documents all options (missing:
  `replay_ttl_seconds`, `replay_cache_max`, `key_rotation_hours`, `max_storage_mb`,
  `retention_hours`).
- **What to do:** Merge into one file with all options documented.

### Original #20: Error Recovery Documentation

- **Problem:** Still no documented procedure for key loss, pin mismatch recovery, or
  client re-registration.
- **What to do:** Add a section to README or a dedicated OPERATIONS.md.

---

## NEW Bugs Found in Implementation (13 issues)

### NEW-1: Thread Safety — All Server Modules (CRITICAL)

FastAPI runs with async/await and can handle concurrent requests. All mutable shared
state across these modules lacks synchronization:

**`server/rate_limit.py:19-28`** — `_windows` dict:
- Two concurrent requests from same IP can both see `window is None`, both create new
  windows, resetting the counter. Rate limiting is bypassable under concurrency.

**`server/replay.py:13-21`** — `_seen` dict:
- Two concurrent requests with the same `envelope_id` can both reach line 16, both find
  it missing, both return `False`. Replay protection completely fails under concurrency.

**`server/app.py:39,122`** — `last_sequences` dict:
- Two concurrent requests from same sender can both read `last = None`, both pass the
  sequence check. Sequence validation fails under concurrency.

**`server/clients.py:21-24,41-49`** — `_allowed` set + file I/O:
- Concurrent registration calls can lose entries (read-modify-write on file without lock).

**What to do for all four:**
- Add `threading.Lock()` to each class
- Wrap all read-check-write operations in `with self._lock:`
- Example for `ReplayCache`:
  ```python
  import threading

  class ReplayCache:
      def __init__(self, ...):
          ...
          self._lock = threading.Lock()

      def seen(self, envelope_id: str) -> bool:
          now = time.time()
          with self._lock:
              self._purge(now)
              if envelope_id in self._seen:
                  return True
              if len(self._seen) >= self._max_entries:
                  self._purge(now, force=True)
              self._seen[envelope_id] = now
              return False
  ```
- Apply same pattern to `RateLimiter.allow()`, `ClientRegistry.register()`,
  and `last_sequences` access in `app.py`

---

### NEW-2: Thread Safety — Sequence Counter (CRITICAL)

- **File:** `crypto/protocol.py:82-86`
- **Problem:** `_next_sequence()` does a non-atomic read-increment-write cycle via
  `load_json` / `save_json`. If two threads or processes call it simultaneously, both
  can read the same value, both increment to the same number, producing duplicate sequences.
- **What to do:**
  - Add a `threading.Lock()` around the sequence read-increment-write
  - For multi-process safety, use file locking (`fcntl.flock` on Linux/macOS)

---

### NEW-3: Timing Attack on Token Comparison (HIGH)

- **File:** `server/auth.py:23`
- **Code:** `return token in set(tokens)`
- **Problem:** Python's `in` operator on a set does not use constant-time comparison.
  An attacker can measure response time differences to determine if a token's hash
  prefix matches, potentially brute-forcing the token.
- **What to do:**
  ```python
  import hmac

  def is_authorized(request, tokens):
      token = extract_token(request)
      if not token:
          return False
      return any(hmac.compare_digest(token, t) for t in tokens)
  ```
  `hmac.compare_digest()` uses constant-time comparison, preventing timing attacks.

---

### NEW-4: Rate Limiter Unbounded Memory (HIGH)

- **File:** `server/rate_limit.py:17`
- **Problem:** `_windows` dictionary grows without bound. Every unique client IP creates
  an entry that is never deleted (expired windows are replaced, not removed). An attacker
  using many IPs causes unbounded memory growth.
- **What to do:**
  - Periodically purge expired entries. Add a purge method:
    ```python
    def _purge_expired(self, now: float) -> None:
        expired = [k for k, w in self._windows.items() if now - w.start_ts >= 60]
        for k in expired:
            del self._windows[k]
    ```
  - Call it inside `allow()` every N requests or every M seconds
  - Or cap the dict size with a max-entries limit

---

### NEW-5: ClientRegistry Open-by-Default (MEDIUM)

- **File:** `server/clients.py:16-18`
- **Code:**
  ```python
  def is_allowed(self, key_b64: str) -> bool:
      if not self._allowed:
          return True  # Allows ALL senders!
      return key_b64 in self._allowed
  ```
- **Problem:** If the admin forgets to configure `allowed_client_keys` and no clients
  register, the server allows envelopes from any sender. This is a dangerous default.
- **What to do:**
  - Add a config flag like `allow_open_registration: true/false` (default `false`)
  - When `false` and no keys configured, reject all senders instead of allowing all
  - Log a warning at startup if running in open mode

---

### NEW-6: Malformed clients.json Iteration Bug (MEDIUM)

- **File:** `server/clients.py:36`
- **Code:** `keys = data.get("allowed_keys", []) if isinstance(data, dict) else data`
- **Problem:** If the JSON value for `allowed_keys` is a string instead of a list
  (e.g. `{"allowed_keys": "abc123"}`), `for key in "abc123"` iterates over individual
  characters `'a'`, `'b'`, `'c'`, etc. Each character passes `isinstance(key, str)`,
  loading garbage into the allowlist.
- **What to do:**
  ```python
  raw_keys = data.get("allowed_keys", []) if isinstance(data, dict) else data
  if not isinstance(raw_keys, list):
      return  # or log warning
  for key in raw_keys:
      if isinstance(key, str) and key.strip():
          self._allowed.add(key.strip())
  ```

---

### NEW-7: Storage Cleanup Runs Synchronously Per Request (MEDIUM)

- **File:** `server/storage.py:35`
- **Code:** `cleanup_storage(base_dir, config)` is called on every `/ingest` request.
- **Problem:** `cleanup_storage()` calls `base_dir.glob("payload_*")` twice (once for
  retention, once for size limit), performing O(n) filesystem I/O where n is the number
  of stored payloads. On a busy server with thousands of files, this adds significant
  latency to every request.
- **What to do:**
  - Run cleanup in a background task (FastAPI `BackgroundTasks`) instead of inline
  - Or throttle cleanup to once per N requests / once per M minutes
  - Example:
    ```python
    @app.post("/ingest")
    async def ingest(request: Request, background_tasks: BackgroundTasks):
        ...
        path = store_payload(payload, config)
        background_tasks.add_task(cleanup_storage, base_dir, config)
        return {...}
    ```

---

### NEW-8: Health Check TTL Only Updates on Success (LOW-MEDIUM)

- **File:** `transport/http_transport.py:60-61`
- **Code:**
  ```python
  if self._healthy:
      self._last_health_ts = now
  ```
- **Problem:** When the server is unhealthy, `_last_health_ts` is never updated. This
  means the TTL check (`now - self._last_health_ts < self._health_ttl`) always evaluates
  `False`, causing a health check HTTP request on EVERY `send()` call. If the server is
  down, the client hammers the health endpoint.
- **What to do:** Always update `_last_health_ts`:
  ```python
  self._last_health_ts = now  # Always update, regardless of result
  self._healthy = 200 <= response.status_code < 300
  ```

---

### NEW-9: Broad Exception Handling in Decryption Fallback (LOW)

- **File:** `crypto/envelope.py:225,232,244,251`
- **Code:** `except Exception:` catches everything during fallback decryption attempts
- **Problem:** This silently swallows non-crypto exceptions like `MemoryError`,
  `KeyboardInterrupt`, or programming errors (e.g. `AttributeError`). Only
  `cryptography.exceptions.InvalidTag` should trigger the fallback.
- **What to do:**
  ```python
  from cryptography.exceptions import InvalidTag
  # Replace: except Exception:
  # With:    except InvalidTag:
  ```

---

### NEW-10: No Validation of Registered Public Keys (LOW)

- **File:** `server/app.py:53-56`
- **Code:**
  ```python
  key_b64 = str(data.get("sender_public_key", "")).strip()
  if not key_b64:
      raise HTTPException(status_code=400, detail="missing sender_public_key")
  registry.register(key_b64)
  ```
- **Problem:** The `/register` endpoint accepts any non-empty string as a public key.
  No validation that it's valid base64 or that it decodes to exactly 32 bytes (Ed25519
  public key size). Garbage entries in the allowlist.
- **What to do:**
  ```python
  import base64
  try:
      raw = base64.b64decode(key_b64)
      if len(raw) != 32:
          raise ValueError("key must be 32 bytes")
  except Exception:
      raise HTTPException(status_code=400, detail="invalid public key format")
  ```

---

### NEW-11: Missing wrapped_key / ciphertext Length Validation (LOW)

- **File:** `crypto/envelope.py:291-301`
- **Problem:** `_validate_lengths()` validates nonces (12 bytes), public keys (32 bytes),
  and signature (64 bytes), but not `wrapped_key` or `ciphertext`. AES-GCM ciphertext
  includes a 16-byte authentication tag, so both should be at least 16 bytes.
- **What to do:**
  ```python
  if len(envelope.wrapped_key) < 16:
      raise ValueError("wrapped_key too short (min 16 bytes for GCM tag)")
  if len(envelope.ciphertext) < 16:
      raise ValueError("ciphertext too short (min 16 bytes for GCM tag)")
  ```

---

### NEW-12: Duplicate Example Config Files (LOW)

- **Files:** `config/server_config.example.yaml` and `server/config.example.yaml`
- **Problem:** Two separate example configs exist with slightly different content. This
  will cause confusion about which one to use.
- **What to do:** Pick one location (recommend `config/server_config.example.yaml`),
  delete the other, and reference it from README.

---

### NEW-13: Key Rotation Asymmetry Between Client and Server (LOW)

- **File:** `crypto/keypair.py` vs `server/keys.py`
- **Problem:** The server preserves previous keys (`server_x25519_private_prev`) during
  rotation and tries both during decryption. The client (`keypair.py`) overwrites old
  keys without preserving them. This means if the client rotates its signing key, the
  server has no way to verify envelopes signed with the old key during the transition.
- **What to do:** Have the client also preserve its previous signing keypair, and include
  a mechanism for the server to accept either current or previous sender keys.

---

## Priority Table (New Issues)

| Priority | Issue | Description | Effort |
|----------|-------|-------------|--------|
| **Critical** | NEW-1 | Thread safety in server modules | Medium |
| **Critical** | NEW-2 | Thread safety in sequence counter | Low |
| **High** | NEW-3 | Timing attack on auth token comparison | Low |
| **High** | NEW-4 | Rate limiter unbounded memory | Low |
| **Medium** | NEW-5 | ClientRegistry open-by-default | Low |
| **Medium** | NEW-6 | Malformed clients.json iteration | Low |
| **Medium** | NEW-7 | Synchronous storage cleanup | Low |
| **Low** | NEW-8 | Health check TTL on failure | Low |
| **Low** | NEW-9 | Broad exception in decryption fallback | Low |
| **Low** | NEW-10 | No validation of registered keys | Low |
| **Low** | NEW-11 | Missing wrapped_key/ciphertext validation | Low |
| **Low** | NEW-12 | Duplicate example configs | Low |
| **Low** | NEW-13 | Key rotation asymmetry | Medium |

---

## Test Coverage Gaps

The existing tests don't cover several new features:

- **Authentication:** No tests for Bearer token / X-API-Key extraction and validation
- **Rate limiting boundary:** Tests don't verify the 60-second window reset
- **Replay cache TTL:** Tests don't verify entries expire after `ttl_seconds`
- **Replay cache max entries:** Tests don't verify behavior when cache is full
- **Client registration:** No tests for `/register` endpoint
- **Sequence gaps/replay:** No HTTP-level tests for sequence validation
- **Concurrent requests:** No tests for thread safety issues (NEW-1, NEW-2)
- **Payload size limits:** No HTTP-level test for 413 response
- **Full E2E auth flow:** No test that combines auth + encryption + decryption

---

*17 items total: 4 original gaps remaining + 13 new implementation bugs.*
*Critical items (NEW-1, NEW-2) should be fixed first — they break replay/rate-limit under load.*
