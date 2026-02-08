# Operations Guide — E2E Server/Client

This document describes how to deploy, operate, and recover the E2E server/client setup.

## 1. Server setup

1) Generate server keys and capture the public key:

```bash
python -m server.run --generate-keys --config config/server_config.example.yaml
```

2) Configure server options in `config/server_config.example.yaml`:

- `auth_tokens` for `/ingest`
- `registration_tokens` for `/register`
- `allowed_client_keys` or `clients_file`
- `storage_dir`, `retention_hours`, `max_storage_mb`
- `ssl_certfile` / `ssl_keyfile` (TLS)

3) Run the server:

```bash
python -m server.run --config config/server_config.example.yaml --host 0.0.0.0 --port 8000
```

## 2. Client setup

1) Set the server public key in the client config:

```yaml
encryption:
  enabled: true
  mode: "e2e"
  e2e:
    server_public_key: "<paste server public key>"
    emit_client_keys: true
    client_keys_path: "~/.advancekeylogger/keys/client_keys.json"
```

2) Configure HTTP transport:

```yaml
transport:
  method: "http"
  http:
    url: "https://your-domain.com/ingest"
    healthcheck_url: "https://your-domain.com/health"
```

3) Register the client (if registration is enabled):

```bash
curl -X POST https://your-domain.com/register \
  -H "Authorization: Bearer <registration-token>" \
  -H "Content-Type: application/json" \
  -d '{"sender_public_key":"<client signing public key>"}'
```

## 3. Key rotation

- **Server:** set `key_rotation_hours` in server config. The server will rotate keys and
  keep the previous key to allow a transition period.
- **Client:** set `encryption.e2e.key_rotation_hours` in client config. The client will
  rotate keys and preserve the previous keypair for recovery/rollbacks.

## 4. Recovery from key loss

- **Server key lost:**
  1) Regenerate keys with `--generate-keys`.
  2) Update all clients with the new `server_public_key`.
  3) Clients must delete their pinned key file:
     `~/.advancekeylogger/keys/server_public_key.key`

- **Client key lost:**
  1) Delete the client key store directory.
  2) Restart client to generate new keys.
  3) Re-register the new signing key with the server.

## 5. Monitoring

- Check audit logs at `audit_log_path` for ingest activity.
- Use `/health` for server health checks.
- Watch for `sequence_gap` events in audit logs (indicates missing envelopes).

## 6. TLS with Caddy (recommended)

If you have a domain name, run the server behind Caddy for automatic HTTPS:

```bash
# Install Caddy
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install caddy

# Create Caddyfile
sudo tee /etc/caddy/Caddyfile << 'CADDYEOF'
your-domain.com {
    reverse_proxy 127.0.0.1:8000
}
CADDYEOF

# Start Caddy
sudo systemctl enable caddy
sudo systemctl start caddy

# Run server locally
python -m server.run --host 127.0.0.1 --port 8000 --config config/server_config.example.yaml
```

If you do **not** have a domain name, use `ssl_certfile`/`ssl_keyfile` in server config
with a self-signed certificate and set `transport.http.ca_cert` on clients.
