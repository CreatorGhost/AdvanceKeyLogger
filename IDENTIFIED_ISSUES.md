# Identified Disconnections & Issues

Scope: Full codebase audit of component wiring, dead code, protocol mismatches, and stub implementations. Each issue includes the root cause, all affected files with line numbers, and what a fix would need to address.

Priority legend: **Critical** (will crash or 404), **High** (feature is dead/unreachable), **Medium** (incomplete/stub), **Low** (cleanup/dead code)

---

## Issue 1 — RedisTransport lives in the wrong directory (High)

**Root cause:** `transport/__init__.py` auto-imports all transport modules from `transport/` at startup. It expects a file at `transport/redis_transport.py` but the actual implementation is in `utils/redis_queue.py`. The import fails silently (caught by try/except), so RedisTransport never registers and is completely unavailable at runtime.

**Affected files:**

| File | Lines | What happens |
|------|-------|-------------|
| `transport/__init__.py` | 87-96 | The import loop lists `"redis_transport"` and runs `__import__(f"{__name__}.{_module}")`. Since `transport/redis_transport.py` doesn't exist, this import fails silently. |
| `utils/redis_queue.py` | 240-243 | `@register_transport("redis")` decorator sits on `class RedisTransport(BaseTransport)`. The decorator would register correctly if the module were ever imported, but nothing imports this file. |
| `config/default_config.yaml` | (fleet section) | Config keys `fleet.transport.redis_enabled` and `redis_url` exist but are never read because the transport never registers. |

**What a fix requires:**
- Either move `utils/redis_queue.py` to `transport/redis_transport.py` (adjusting internal imports), or add an explicit import of `utils.redis_queue` in `transport/__init__.py`.
- Ensure the `@register_transport("redis")` decorator fires so the factory `create_transport("redis")` works.

---

## Issue 2 — Base `Agent` class is never instantiated (High)

**Root cause:** `agent_controller.py` defines a full `Agent` class (registration, heartbeat, command handling, encryption) but no entry point or script ever creates an instance of it. A separate `FleetAgent` (in `fleet/agent.py`) extends it and overrides key methods for REST API communication, but `FleetAgent` itself is also never instantiated by any entry point.

**Affected files:**

| File | Lines | What's there |
|------|-------|-------------|
| `agent_controller.py` | 580-914 | `class Agent` — full implementation: `__init__`, `start()`, `stop()`, `_register()`, `_heartbeat_loop()`, `_command_listener()`, `handle_command()`, default handlers (ping, update_config, get_status, shutdown). |
| `agent_controller.py` | 591-659 | `Agent.__init__` — hardcodes `HttpTransport` at line 653-659: `self.transport = HttpTransport({"url": self.controller_url, "method": "POST", ...})`. Ignores config-driven transport selection used elsewhere in the codebase (`main.py`). |
| `fleet/agent.py` | 29-32 | `class FleetAgent(Agent)` — extends the base Agent with REST API registration, heartbeat, and command polling. |
| `fleet/agent.py` | 48, 64, 102, 155, 194 | Key overridden methods: `start()`, `stop()`, `_register()`, `_heartbeat_loop()`, `_command_listener()`. |

**What a fix requires:**
- An entry point or CLI command that instantiates `FleetAgent` with the appropriate config.
- Transport selection in base `Agent.__init__` should use the config-driven factory (`create_transport()`) instead of hardcoding `HttpTransport`.

---

## Issue 3 — Agent `_command_listener()` is a stub (High)

**Root cause:** The base `Agent._command_listener()` method is an infinite sleep loop that never polls for or receives commands. The comment in the code acknowledges this.

**Affected files:**

| File | Lines | What's there |
|------|-------|-------------|
| `agent_controller.py` | 751-764 | `async def _command_listener(self) -> None:` — body is `while self.running: await asyncio.sleep(1)` with a comment: *"Commands would be received here via transport.receive() or similar. For HTTP transport, we'd need to implement a polling mechanism or switch to a WebSocket transport for real-time communication."* |
| `fleet/agent.py` | 194 | `FleetAgent._command_listener()` — overrides the stub with a REST polling implementation that calls `GET /api/v1/fleet/commands`. This one actually works, but is itself never run (see Issue 2). |

**What a fix requires:**
- Base `Agent._command_listener()` needs a real polling or push-receive implementation.
- Or, the codebase should commit to using `FleetAgent` and wire it into an entry point.

---

## Issue 4 — WebSocket receive loop is a no-op (High)

**Root cause:** `WebSocketTransport._receive_loop()` receives messages and logs them, but the TODO to actually dispatch them was never implemented. Messages arrive and are silently dropped.

**Affected files:**

| File | Lines | What's there |
|------|-------|-------------|
| `transport/websocket_transport.py` | 196-221 | `async def _receive_loop(self) -> None:` — receives via `await self._websocket.recv()`, decompresses with gzip, parses JSON, logs `"Received message: {data}"`, then hits line 212: `# TODO: Process received messages (e.g., commands from controller)`. Nothing further happens. |

**What a fix requires:**
- After parsing, the receive loop should call a callback (e.g., `self.on_message(data)`) or dispatch to `Agent.handle_command()`.
- A callback/handler registration mechanism so the transport doesn't need to know about the Agent directly.

---

## Issue 5 — No WebSocket frontend client (High)

**Root cause:** The dashboard backend defines two WebSocket endpoints (`/ws/dashboard` and `/ws/agent/{agent_id}`) with full connection management, but no JavaScript code in any static file or template creates a WebSocket connection. The entire real-time infrastructure has no frontend consumer.

**Affected files:**

| File | Lines | What's there |
|------|-------|-------------|
| `dashboard/routes/websocket.py` | 160 | `@ws_router.websocket("/ws/dashboard")` — accepts dashboard client connections. |
| `dashboard/routes/websocket.py` | 191 | `@ws_router.websocket("/ws/agent/{agent_id}")` — accepts agent connections. |
| `dashboard/routes/websocket.py` | 27-130 | `ConnectionManager` class — full implementation: `connect_dashboard()`, `connect_agent()`, `broadcast_dashboard()`, `send_to_agent()`. |
| `dashboard/static/js/dashboard.js` | entire file | Uses only `fetch()` for REST API calls. Zero WebSocket code. |
| `dashboard/static/js/*.js` | all files | Searched all JS files — none create `new WebSocket(...)`. |

**What a fix requires:**
- JavaScript in `dashboard.js` (or a new `ws-client.js`) that opens a WebSocket to `ws://<host>/ws/dashboard`.
- Handlers for incoming message types: `agent_status`, `new_capture`, `command_result`, `status`.
- Live-updating UI elements that react to WebSocket events.

---

## Issue 6 — Signatures are created but never verified (High)

**Root cause:** `SecureChannel` has a `sign()` method and signatures are included in `ProtocolMessage`, but no code on either side (controller or agent) ever calls a verify function. Messages can be tampered with undetected.

**Affected files:**

| File | Lines | What's there |
|------|-------|-------------|
| `agent_controller.py` | 248-252 | `SecureChannel.sign(self, data: bytes) -> bytes` — signs using RSA-PSS via `sign_with_private_key()`. |
| `agent_controller.py` | 513 | `signature = channel.sign(command_data)` — controller signs commands before sending. |
| `agent_controller.py` | 165-212 | `ProtocolMessage` — has a `signature` field that is set during creation and serialized to JSON. |
| `agent_controller.py` | entire file | No call to any `verify()` or `verify_signature()` function exists. The signature is packed and sent but the receiver never checks it. |
| `utils/crypto.py` | (verify functions) | `verify_with_public_key()` exists in the crypto module but is never called by the agent/controller code. |

**What a fix requires:**
- On the controller side: verify the agent's signature on registration, heartbeat, and command_response messages using the agent's stored public key.
- On the agent side: verify the controller's signature on commands using the controller's public key (which first requires a key exchange — see Issue 7).

---

## Issue 7 — Three incompatible message protocols (High)

**Root cause:** Three different parts of the codebase define their own message formats. They cannot interoperate.

**Protocol A — Base Agent/Controller (`ProtocolMessage`):**
```
{
  "version": "1.0",
  "type": "register|heartbeat|command|command_response",
  "agent_id": "...",
  "timestamp": 1234567890.0,
  "payload": { ... },
  "signature": "base64..."
}
```
Defined in `agent_controller.py:165-212`. Used by `Agent._register()` (line 710) and `Controller._send_command_to_agent()` (line 513).

**Protocol B — FleetAgent (REST JSON):**
```
POST /api/v1/fleet/register  { hostname, platform, ... }
POST /api/v1/fleet/heartbeat { agent_id, status, ... }
GET  /api/v1/fleet/commands
POST /api/v1/fleet/commands/{id}/response
```
Defined in `fleet/agent.py:102-228`. Consumed by `dashboard/routes/fleet_api.py`.

**Protocol C — Dashboard WebSocket:**
```
{
  "type": "agent_status|command|get_status|broadcast|...",
  "data": { ... }
}
```
Defined in `dashboard/routes/websocket.py:228-333`. Expects flat `{type, data}` shape.

**Affected files:**

| File | Lines | Protocol |
|------|-------|----------|
| `agent_controller.py` | 165-212 | Protocol A (`ProtocolMessage`) |
| `agent_controller.py` | 710 | Agent sends Protocol A via `transport.send(message.to_bytes())` |
| `fleet/agent.py` | 102-228 | Protocol B (REST JSON) |
| `dashboard/routes/fleet_api.py` | 101-212 | Receives Protocol B |
| `dashboard/routes/websocket.py` | 228-333 | Expects Protocol C |
| `transport/http_transport.py` | 66 | Sends raw bytes (Protocol A) — no endpoint receives this format |

**What a fix requires:**
- Decide on a single canonical wire format.
- Either unify around `ProtocolMessage` (and update dashboard WS to parse it) or unify around the REST/JSON format (and retire `ProtocolMessage`).
- Ensure HTTP transport has a matching server endpoint if raw `ProtocolMessage` bytes are sent.

---

## Issue 8 — Dashboard WebSocket handlers are log-only stubs (Medium)

**Root cause:** When agent messages arrive via WebSocket, the handler functions only call `logger.info()` or `logger.debug()`. No data is persisted or forwarded.

**Affected files:**

| File | Lines | Function | What it does |
|------|-------|----------|-------------|
| `dashboard/routes/websocket.py` | 362-366 | `_update_agent_status()` | Logs agent_id and status keys. No DB write. |
| `dashboard/routes/websocket.py` | 368-377 | `_handle_capture_data()` | Logs agent_id, capture type, and size. No storage. |
| `dashboard/routes/websocket.py` | 379-386 | `_handle_command_response()` | Logs command_id and status. No forwarding to controller. |

**What a fix requires:**
- These functions should write to `FleetStorage` (or `SQLiteStorage`) to persist agent status, capture data, and command results.
- `_handle_command_response()` should also call `controller.handle_command_response()` to update command state.

---

## Issue 9 — `_get_recent_captures()` returns mock data (Medium)

**Root cause:** The WebSocket `get_captures` command handler returns hardcoded fake data instead of querying the database.

**Affected files:**

| File | Lines | What's there |
|------|-------|-------------|
| `dashboard/routes/websocket.py` | 346-359 | `async def _get_recent_captures()` — comment says *"In production, this would query the actual storage system. For now, return mock data"*. Returns a list of `{"id": f"capture_{i}", ...}` dicts. |
| `storage/sqlite_storage.py` | 117-134 | `get_pending()` method exists and could serve this purpose — returns real capture records from the `captures` table. |

**What a fix requires:**
- Replace the mock return with a call to `SQLiteStorage.get_pending()` or a similar query method.
- The WebSocket handler needs access to the storage instance (via `app.state` or dependency injection).

---

## Issue 10 — `/live` route is redundant (Low)

**Root cause:** The `/live` route renders the exact same `dashboard.html` template as `/dashboard`, just with `page: "live"`. Since no WebSocket frontend client exists (Issue 5), there is no live functionality.

**Affected files:**

| File | Lines | What's there |
|------|-------|-------------|
| `dashboard/routes/pages.py` | 46-60 | `live_dashboard_page()` — renders `dashboard.html` with `{"page": "live"}`. |
| `dashboard/routes/pages.py` | 29-43 | `dashboard_page()` — renders `dashboard.html` with `{"page": "dashboard"}`. |
| `dashboard/templates/dashboard.html` | entire file | No conditional logic for `page == "live"` — both routes render identically. |

**What a fix requires:**
- Either add WebSocket-powered live functionality differentiated by `page == "live"`, or remove the `/live` route to avoid confusion.

---

## Issue 11 — `fleet/controller.py` doesn't persist keys (Medium)

**Root cause:** When an agent registers, the controller generates a `SecureChannel` with RSA keys, but these keys are stored only in memory. A restart loses all key material, breaking any encrypted communication.

**Affected files:**

| File | Lines | What's there |
|------|-------|-------------|
| `fleet/controller.py` | 78 | `# TODO: Persist keys to file or DB to support key pinning.` |
| `agent_controller.py` | 214-253 | `SecureChannel` — generates RSA keys in `initialize()`, stores them as instance attributes. No serialization. |
| `storage/fleet_storage.py` | (schema) | Fleet storage has tables for agents and commands but no column for key material. |

**What a fix requires:**
- Serialize RSA key pairs (PEM format) and store in the agents table or a dedicated keys table.
- On restart, reload keys for known agents so encrypted sessions resume.

---

## Issue 12 — `fleet_api.py` command endpoint skips encryption (Medium)

**Root cause:** The fleet REST API returns commands as plain JSON over HTTPS, bypassing the `SecureChannel` encryption that the base controller uses. A comment in the code acknowledges this gap.

**Affected files:**

| File | Lines | What's there |
|------|-------|-------------|
| `dashboard/routes/fleet_api.py` | 155 | `@router.get("/commands")` — fetches pending commands for an agent. |
| `dashboard/routes/fleet_api.py` | 177-193 | Comment block: *"Encrypt command for agent. Since we are using REST, we might skip full encryption if TLS is used. But Gap 4 says 'Secure Channel'. So we should return the encrypted blob that _send_command_to_agent would produce."* |

**What a fix requires:**
- If transport-level encryption is desired (beyond TLS), the endpoint should encrypt command payloads using the agent's stored public key before returning them.
- If TLS is considered sufficient, remove the TODO and document the decision.

---

## Issue 13 — `biometrics/matcher.py` is exported but never used (Low)

**Root cause:** `ProfileMatcher` is exported in `biometrics/__init__.py` but no production code ever imports or instantiates it. Only test files reference it.

**Affected files:**

| File | Lines | What's there |
|------|-------|-------------|
| `biometrics/__init__.py` | 8 | `from biometrics.matcher import ProfileMatcher` |
| `biometrics/__init__.py` | 14 | Listed in `__all__` |
| `biometrics/matcher.py` | entire file | `ProfileMatcher` class with `compare_profiles()`, `authenticate()`, `get_similarity_score()`. |
| `main.py` | 479-643 | Uses `BiometricsAnalyzer` and `BiometricsCollector` but never `ProfileMatcher`. |

---

## Issue 14 — `engine/event_bus.py` and `engine/registry.py` exported but never used (Low)

**Root cause:** Both `EventBus` and `RuleRegistry` are exported from `engine/__init__.py` but never instantiated anywhere in production code. `RuleEngine` (the class that IS used) doesn't depend on either of them.

**Affected files:**

| File | Lines | What's there |
|------|-------|-------------|
| `engine/__init__.py` | 6 | `from engine.event_bus import EventBus` |
| `engine/__init__.py` | 8 | `from engine.registry import RuleRegistry` |
| `engine/__init__.py` | 13-14 | Both listed in `__all__` |
| `engine/event_bus.py` | entire file (~37 lines) | `EventBus` class — publish/subscribe pattern. Never instantiated. |
| `engine/registry.py` | entire file (~84 lines) | `RuleRegistry` class — rule storage/lookup. Never instantiated in production. |
| `main.py` | 527-593 | Uses `RuleEngine` directly. Does not use `EventBus` or `RuleRegistry`. |

---

## Issue 15 — Legacy root-level scripts are orphaned (Low)

**Root cause:** Two files at the repository root predate the modular architecture and are fully superseded by newer modules. They are never imported or referenced.

**Affected files:**

| File | Lines | What's there | Superseded by |
|------|-------|-------------|---------------|
| `createfile.py` | ~103 lines | `ScreenshotReporter` — standalone screenshot capture and email. Has `if __name__ == "__main__"`. | `capture/screenshot_capture.py` + `transport/email_transport.py` |
| `mailLogger.py` | ~99 lines | `SendMail()` function — sends screenshots via SMTP. | `transport/email_transport.py` |

---

## Issue 16 — Base `Controller` never receives agent HTTP messages (High)

**Root cause:** The base `Agent` sends `ProtocolMessage` bytes via `HttpTransport` to `self.controller_url`, but there is no corresponding FastAPI/HTTP endpoint that parses `ProtocolMessage` payloads. The `fleet_api.py` endpoints accept REST JSON (Protocol B), not raw `ProtocolMessage` bytes (Protocol A).

**Affected files:**

| File | Lines | What's there |
|------|-------|-------------|
| `agent_controller.py` | 653-659 | Agent creates `HttpTransport` pointing at `controller_url`. |
| `agent_controller.py` | 710 | Agent sends: `self.transport.send(message.to_bytes())` — raw bytes. |
| `transport/http_transport.py` | 66-96 | `send()` does `requests.post(url, data=data)` — sends binary payload. |
| `dashboard/routes/fleet_api.py` | 101-212 | Endpoints expect JSON bodies with specific fields, NOT raw `ProtocolMessage` bytes. |
| `dashboard/routes/api.py` | entire file | No endpoint for agent registration, heartbeat, or command responses. |

**What a fix requires:**
- Either add an endpoint that accepts `ProtocolMessage` bytes (e.g., `POST /api/v1/agent/message`) and routes to the correct controller method based on `message.type`.
- Or retire the `ProtocolMessage` format and have the base `Agent` use the REST JSON format that `fleet_api.py` already handles.

---

## Issue 17 — `FleetAgent` has a metrics TODO (Low)

**Affected files:**

| File | Lines | What's there |
|------|-------|-------------|
| `fleet/agent.py` | 149 | `# TODO: Add real metrics` — heartbeat payload sends placeholder metrics instead of actual system stats. |
| `utils/system_info.py` | entire file | `get_system_info()` exists and collects real system metrics — but `FleetAgent` doesn't use it. |

---

## Summary table

| # | Issue | Priority | Status |
|---|-------|----------|--------|
| 1 | RedisTransport in wrong directory | High | Dead — import fails silently |
| 2 | Base Agent never instantiated | High | 334 lines of dead code |
| 3 | Agent _command_listener is a stub | High | Infinite sleep loop |
| 4 | WebSocket receive loop is a no-op | High | TODO never implemented |
| 5 | No WebSocket frontend client | High | Backend WS with no consumer |
| 6 | Signatures never verified | High | Created and discarded |
| 7 | Three incompatible protocols | High | Cannot interoperate |
| 8 | WS handlers are log-only stubs | Medium | No persistence |
| 9 | _get_recent_captures returns mock data | Medium | Hardcoded fake data |
| 10 | /live route is redundant | Low | Identical to /dashboard |
| 11 | Fleet controller doesn't persist keys | Medium | Lost on restart |
| 12 | Fleet API skips command encryption | Medium | Plain JSON over wire |
| 13 | biometrics/matcher.py unused | Low | Exported, never called |
| 14 | EventBus and RuleRegistry unused | Low | Exported, never called |
| 15 | Legacy root scripts orphaned | Low | Superseded by modules |
| 16 | No HTTP endpoint for ProtocolMessage | High | Agent sends, nothing receives |
| 17 | FleetAgent metrics placeholder | Low | TODO, util exists |
