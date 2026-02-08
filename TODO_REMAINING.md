# Remaining TODO Items — E2E Server/Client

5 items left. Everything else has been fixed across 4 rounds of review.
Ordered by recommended implementation sequence.

---

## 1. ClientRegistry: Deny-by-Default

**File:** `server/clients.py`
**Effort:** Low
**Why first:** One logic change, no dependencies.

Currently when `allowed_client_keys` is empty, the server allows ALL senders.
This is dangerous — a misconfigured server is wide open.

**Changes needed:**

`server/clients.py` — add `allow_open` parameter:
```python
class ClientRegistry:
    def __init__(self, allowed_keys, clients_file, allow_open=False):
        self._allow_open = allow_open
        # ... rest unchanged

    def is_allowed(self, key_b64: str) -> bool:
        if not self._allowed:
            return self._allow_open   # was: return True
        return key_b64 in self._allowed
```

`server/app.py` — pass the flag from config:
```python
registry = ClientRegistry(
    allowed_client_keys,
    clients_file,
    allow_open=bool(config.get("allow_open_registration", False)),
)
```

`config/server_config.example.yaml` — add the option:
```yaml
# Set to true to allow any sender when allowed_client_keys is empty.
# Default false = deny all unknown senders.
allow_open_registration: false
```

---

## 2. Client Key Rotation: Preserve Previous Signing Keypair

**File:** `crypto/keypair.py`
**Effort:** Medium
**Why second:** Prevents signature verification failures during key rotation windows.

Currently the server preserves old keys during rotation (`server/keys.py:80-81`),
but the client (`keypair.py`) overwrites its old signing keypair. If the client
rotates mid-flight, envelopes signed with the old key can't be verified.

**Changes needed:**

`crypto/keypair.py` — before overwriting, save current as `_prev`:
```python
# Inside load_or_create(), before generating new keys:
if rotation needed:
    # Preserve current keys
    current_signing = self._store.load_bytes(self._name("ed25519_signing_private"))
    current_signing_pub = self._store.load_bytes(self._name("ed25519_signing_public"))
    current_exchange = self._store.load_bytes(self._name("x25519_private"))
    current_exchange_pub = self._store.load_bytes(self._name("x25519_public"))

    if current_signing:
        self._store.save_bytes(self._name("ed25519_signing_private_prev"), current_signing)
    if current_signing_pub:
        self._store.save_bytes(self._name("ed25519_signing_public_prev"), current_signing_pub)
    if current_exchange:
        self._store.save_bytes(self._name("x25519_private_prev"), current_exchange)
    if current_exchange_pub:
        self._store.save_bytes(self._name("x25519_public_prev"), current_exchange_pub)

    # Then generate new keys as currently done...
```

The pattern is identical to what `server/keys.py:77-81` already does.

---

## 3. TLS via Reverse Proxy (Caddy)

**Effort:** Low (infrastructure, no code changes)
**Why third:** Protects auth tokens on the wire. Requires a domain name.

**Recommended approach:** Use Caddy as a reverse proxy in front of uvicorn.
Caddy auto-obtains and auto-renews Let's Encrypt certificates.

**Steps on your Digital Ocean / EC2 server:**

```bash
# 1. Install Caddy
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install caddy

# 2. Create Caddyfile (replace your-domain.com with your actual domain)
sudo tee /etc/caddy/Caddyfile << 'CADDYEOF'
your-domain.com {
    reverse_proxy 127.0.0.1:8000
}
CADDYEOF

# 3. Start Caddy (auto-obtains TLS cert from Let's Encrypt)
sudo systemctl enable caddy
sudo systemctl start caddy

# 4. Start your FastAPI server (binds to localhost only)
python -m server.run --host 127.0.0.1 --port 8000 --config config/server_config.example.yaml
```

**Result:**
- Caddy listens on port 443 (HTTPS) with auto-renewed Let's Encrypt cert
- Your FastAPI app listens on 127.0.0.1:8000 (not exposed to internet)
- Auth tokens are encrypted in transit
- No code changes needed

**Client config:**
```yaml
transport:
  method: http
  http:
    url: "https://your-domain.com/ingest"
    # verify: true  (default, works with Let's Encrypt)
```

**Alternative (no domain name):** If you only have an IP address, Caddy can't
get a Let's Encrypt cert. In that case, add TLS directly to uvicorn:

`server/run.py` — pass SSL config to uvicorn:
```python
ssl_cert = config.get("ssl_certfile")
ssl_key = config.get("ssl_keyfile")
kwargs = {}
if ssl_cert and ssl_key:
    kwargs["ssl_certfile"] = ssl_cert
    kwargs["ssl_keyfile"] = ssl_key
uvicorn.run(app, host=host, port=port, **kwargs)
```

Then generate a self-signed cert:
```bash
openssl req -x509 -newkey rsa:4096 -keyout server.key -out server.crt \
    -days 365 -nodes -subj '/CN=your-server-ip'
```

And set `verify: false` on the client (disables cert validation — only for
development or when you control both ends).

---

## 4. Custom CA Certificate Support on Client

**File:** `transport/http_transport.py`
**Effort:** Low
**Why fourth:** Only needed if you use self-signed certs (item 3 alternative).
If you use Caddy + Let's Encrypt, skip this entirely.

**Changes needed:**

`transport/http_transport.py` — read `ca_cert` from config:
```python
def __init__(self, config):
    # ... existing init ...
    self._ca_cert = config.get("ca_cert")  # path to CA bundle file
    # Change _verify to use ca_cert path if provided:
    if self._ca_cert:
        self._verify = self._ca_cert
    # else _verify stays as config.get("verify", True)
```

`config/default_config.yaml` — add option under transport.http:
```yaml
transport:
  http:
    url: "https://your-server/ingest"
    # Path to custom CA certificate bundle (for self-signed server certs).
    # Leave empty to use system CA store (works with Let's Encrypt).
    ca_cert: ""
```

---

## 5. Operations Documentation

**File:** New file `OPERATIONS.md`
**Effort:** Low
**Why last:** No code impact, but important for maintainability.

Write a single document covering:

1. **Server setup**
   - Generate server keys: `python -m server.run --generate-keys`
   - Copy the printed public key (base64) for client config
   - Edit `config/server_config.example.yaml` with auth tokens
   - Start server: `python -m server.run --config ...`

2. **Client setup**
   - Set `encryption.e2e.server_public_key` to the server's base64 public key
   - Set `transport.method: http` and `transport.http.url: https://...`
   - Register client: send POST to `/register` with signing public key

3. **Key rotation**
   - Server: set `key_rotation_hours` in server config, server auto-rotates
   - Client: set `key_rotation_hours` in client config, client auto-rotates
   - During rotation, server accepts both current and previous keys

4. **Recovery from key loss**
   - Server key lost: regenerate with `--generate-keys`, update ALL clients'
     `server_public_key`, clients must delete pinned key file
     (`~/.advancekeylogger/keys/server_public_key.key`)
   - Client key lost: delete client key store, restart client (new keys generated),
     re-register with server

5. **Monitoring**
   - Check audit log at `audit_log_path` for ingest events
   - Check `/health` endpoint for server status
   - Watch for `sequence_gap` log entries (indicates dropped envelopes)

---

## Summary

| # | Item | File(s) | Effort |
|---|------|---------|--------|
| 1 | Deny-by-default registry | `server/clients.py`, `server/app.py` | Low |
| 2 | Client key preservation on rotation | `crypto/keypair.py` | Medium |
| 3 | TLS via Caddy reverse proxy | Infrastructure (no code) | Low |
| 4 | Custom CA cert on client | `transport/http_transport.py` | Low |
| 5 | Operations documentation | New `OPERATIONS.md` | Low |
