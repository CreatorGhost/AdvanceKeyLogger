# Identified Issues — Full Audit Trail

Scope: Complete codebase audit covering component wiring, protocol mismatches, dead code, frontend-backend alignment, configuration gaps, import chains, async/sync safety, and runtime error risks. This document tracks all issues found across multiple audit passes, what was fixed, by whom, and what remains.

**Audit date:** 2026-02-10
**Branch:** `codex/fleet-management`

---

# Part 1 — Resolved Issues

## Round 1: Initial bugs (fixed by code review)

### R1. Missing `/analytics` page route (was Critical — 404)

**Problem:** Sidebar in `base.html:49` linked to `/analytics`. The template `analytics.html` and JS `analytics.js` both existed, and the API endpoints `/api/analytics/activity` and `/api/analytics/summary` worked. But no page route handler existed, so clicking Analytics gave a 404.

**Fix applied:** Added route in `dashboard/routes/pages.py:101-115`:
```python
@pages_router.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request) -> Response:
```
Follows the same auth-check + template-render pattern as all other page routes.

**Files changed:** `dashboard/routes/pages.py`

---

### R2. `url_for('login')` Flask syntax in FastAPI template (was Critical — template crash)

**Problem:** `dashboard/templates/login.html:30` used `{{ url_for('login') }}` which is Flask/Jinja2 URL generation. FastAPI does not provide this function by default, causing a template render crash.

**Fix applied:** Replaced with the hardcoded path `/auth/login` which matches the POST endpoint in `dashboard/auth.py`.

**Files changed:** `dashboard/templates/login.html:30`

---

## Round 2: Original 17 issues (Issues 1-17, fixed by user)

### R3. Issue 1 — RedisTransport in wrong directory (was High)

**Problem:** `transport/__init__.py:87-96` tried to auto-import `transport.redis_transport` but the file was at `utils/redis_queue.py`. Import failed silently.

**Fix applied:** Created `transport/redis_transport.py` as a bridge module that re-exports `RedisTransport`, `RedisQueue`, `Message`, `MessagePriority` from `utils/redis_queue.py`. The `@register_transport("redis")` decorator now fires during import.

**Files changed:** `transport/redis_transport.py` (new)

---

### R4. Issue 2 — Base Agent never instantiated (was High)

**Problem:** `agent_controller.py:580-914` defined a full `Agent` class. `fleet/agent.py:29` defined `FleetAgent(Agent)`. Neither was instantiated by any entry point.

**Fix applied:** Created `fleet/run_agent.py` CLI entry point with argparse. Updated base `Agent.start()` to use config-driven transport factory via `create_transport_for_method()` instead of hardcoding `HttpTransport`.

**Files changed:** `fleet/run_agent.py` (new), `agent_controller.py`

---

### R5. Issue 3 — Agent `_command_listener()` was a stub (was High)

**Problem:** `agent_controller.py:751-764` — infinite `asyncio.sleep(1)` loop, never polled or received commands.

**Fix applied:** Implemented real polling/receive logic supporting both HTTP polling mode (requests to commands endpoint) and WebSocket receive mode (via transport's receive queue). `FleetAgent` has its own override at `fleet/agent.py:194` that polls `/api/v1/fleet/commands`.

**Files changed:** `agent_controller.py`

---

### R6. Issue 4 — WebSocket receive loop was a no-op (was High)

**Problem:** `transport/websocket_transport.py:196-221` received messages and logged them but had `# TODO: Process received messages`. Messages were silently dropped.

**Fix applied:** Added `register_handler()`, `set_default_handler()`, and `receive()` methods. `_receive_loop()` now dispatches messages to registered handlers and queues them for sync consumers.

**Files changed:** `transport/websocket_transport.py`

---

### R7. Issue 5 — No WebSocket frontend client (was High)

**Problem:** Backend WebSocket endpoints `/ws/dashboard` and `/ws/agent/{agent_id}` existed with full `ConnectionManager`, but zero JavaScript code created WebSocket connections.

**Fix applied:** Created `dashboard/static/js/ws-client.js` (536 lines) with `DashboardWebSocket` and `LiveDashboard` classes. Handles connection management, reconnection, and message routing. Included in `base.html:150`. Auto-initializes on pages with `data-enable-websocket="true"`.

**Files changed:** `dashboard/static/js/ws-client.js` (new), `dashboard/templates/base.html`

---

### R8. Issue 6 — Signatures created but never verified (was High)

**Problem:** `SecureChannel.sign()` at `agent_controller.py:248-252` created signatures. `ProtocolMessage` carried them. No code ever called verify.

**Fix applied:**
- Added `verify_with_public_key()` to `utils/crypto.py`
- Added `SecureChannel.verify()` method
- `fleet_api.py` verifies `X-Signature` header when `fleet.security.require_signature_verification` is `true` (now defaults to `true` in config)
- `FleetAgent` signs requests when `sign_requests` config is `true`

**Files changed:** `utils/crypto.py`, `agent_controller.py`, `dashboard/routes/fleet_api.py`, `fleet/agent.py`

---

### R9. Issues 7 & 16 — Three incompatible protocols / No HTTP endpoint for ProtocolMessage (was High)

**Problem:** Three message formats coexisted: Protocol A (`ProtocolMessage` — `agent_controller.py:165-212`), Protocol B (REST JSON — `fleet/agent.py:102-228`), Protocol C (Dashboard WS — `websocket.py:228-333`). None interoperated.

**Resolution:** REST JSON (Protocol B) is canonical. `FleetAgent` and `fleet_api.py` use it. `ProtocolMessage` (Protocol A) is retained as legacy for potential direct-transport use but is not the primary wire format.

**Files changed:** Documentation only

---

### R10. Issues 8 & 9 — WS handlers log-only / Mock captures data (was Medium)

**Problem:** `_update_agent_status()` (websocket.py:362), `_handle_capture_data()` (websocket.py:368), `_handle_command_response()` (websocket.py:379) only logged. `_get_recent_captures()` (websocket.py:346) returned hardcoded mock data.

**Fix applied:**
- Added `set_storage_references()` function to `websocket.py`
- Handlers now write to `FleetStorage` and `SQLiteStorage` when available
- `_get_recent_captures()` queries real storage with mock fallback
- `dashboard/app.py` calls `set_storage_references()` during lifespan startup, passing both `sqlite_storage` and `fleet_storage`

**Files changed:** `dashboard/routes/websocket.py`, `dashboard/app.py`

---

### R11. Issue 10 — `/live` route was redundant (was Low)

**Problem:** `/live` rendered the same `dashboard.html` as `/dashboard` with no differentiation.

**Fix applied:** Created dedicated `live.html` template with WebSocket integration. Updated `/live` route in `pages.py:49-64` to render `live.html` with `enable_websocket: True`. Added Live link to sidebar in `base.html`.

**Files changed:** `dashboard/templates/live.html` (new), `dashboard/routes/pages.py`, `dashboard/templates/base.html`

---

### R12. Issue 11 — Fleet controller didn't persist keys (was Medium)

**Problem:** `fleet/controller.py:78` had `# TODO: Persist keys`. RSA keys were memory-only and lost on restart.

**Fix applied:**
- Added `controller_keys` table to `storage/fleet_storage.py`
- Added `save_controller_keys()`, `get_controller_keys()`, `delete_controller_keys()` methods
- `FleetController._load_or_generate_keys()` loads from DB or generates + persists
- Added `rotate_keys()` for key rotation

**Files changed:** `storage/fleet_storage.py`, `fleet/controller.py`

---

### R13. Issue 12 — Fleet API skips command encryption (was Medium)

**Resolution:** Documented as intentional. HTTPS/TLS provides transport encryption. Application-level encryption is optional. Signatures provide authentication/integrity. Commands are plain JSON over TLS, which is standard REST practice.

**Files changed:** Documentation only

---

### R14. Issue 13 — `biometrics/matcher.py` unused (was Low)

**Fix applied:** Integrated `ProfileMatcher` into `BiometricsAnalyzer` with `register_reference_profile()`, `unregister_profile()`, `authenticate()`, `get_similarity_score()`, `is_same_user()`. Added `biometrics.authentication` config section in `default_config.yaml:114-117`.

**Files changed:** `biometrics/analyzer.py`, `config/default_config.yaml`

---

### R15. Issue 14 — EventBus and RuleRegistry unused (was Low)

**Fix applied:** Initialized `EventBus` in `main.py:524`. Subscribed `rule_engine` (all events), biometrics (keystroke events), profiler (window events). Events published via `event_bus.publish()` for decoupled routing.

**Files changed:** `main.py`

---

### R16. Issue 15 — Legacy root scripts orphaned (was Low)

**Fix applied:** Moved `createfile.py` and `mailLogger.py` to `legacy/` directory. Added `legacy/README.md` documenting the archived scripts and their modern replacements.

**Files changed:** `legacy/createfile.py` (moved), `legacy/mailLogger.py` (moved), `legacy/README.md` (new)

---

### R17. Issue 17 — FleetAgent metrics placeholder (was Low)

**Fix applied:** Added `get_system_metrics()` to `utils/system_info.py:78-135`. Uses psutil if available, falls back to OS-level stats. FleetAgent heartbeats at `fleet/agent.py:177-194` now include real CPU, memory, and disk metrics.

**Files changed:** `utils/system_info.py`, `fleet/agent.py`

---

## Round 3: Post-fix verification issues (fixed by user)

### R18. `set_storage_references()` missing SQLiteStorage parameter (was Medium)

**Problem:** `dashboard/app.py` called `set_storage_references()` but didn't pass SQLiteStorage. WebSocket handlers had `if _storage is not None:` guards but `_storage` was always `None`, so `_handle_capture_data()` and `_get_recent_captures()` never persisted data.

**Fix applied:** `dashboard/app.py:39-49` now initializes SQLiteStorage from `storage.sqlite_path` config. Lines 77-81 pass it as `storage=sqlite_storage` to `set_storage_references()`. Lines 89-95 wire it even if fleet is disabled. Lines 106-109 close it on shutdown.

**Files changed:** `dashboard/app.py`

---

### R19. Signature verification disabled by default (was Low)

**Problem:** `fleet.security.require_signature_verification` defaulted to `false`, meaning agents could send unsigned requests.

**Fix applied:** Changed to `true` in `config/default_config.yaml:227`. Added documentation comment explaining the security implications (lines 222-226).

**Files changed:** `config/default_config.yaml`

---

### R20. Path traversal in screenshot endpoint (was High)

**Problem:** `dashboard/routes/api.py:200` passed user input (`filename`) to `FileResponse` without validating the resolved path stayed within the screenshots directory. Attackers could use `../../etc/passwd` style paths.

**Fix applied:** `api.py:189-216` now:
1. Resolves `screenshots_dir` to absolute path (line 190)
2. Resolves requested path to canonical form (line 195)
3. Calls `requested_path.relative_to(screenshots_dir)` to reject traversal (lines 201-205)
4. Checks file existence and type (lines 208-212)

**Files changed:** `dashboard/routes/api.py`

---

### R21. TODO in `fleet/controller.py` for enrollment key (was Low)

**Problem:** `fleet/controller.py:188` had a TODO about preserving enrollment keys from metadata tags.

**Fix applied:** Enrollment key extraction implemented at `fleet/controller.py:189-195`, using convention of `enrollment_key:` prefix in `metadata.tags`.

**Files changed:** `fleet/controller.py`

---

## Round 4: Safe fixes (fixed by code review)

### R22. Unsafe dict access `self.agents[agent_id]` — KeyError risk (was Medium)

**Problem:** `agent_controller.py:443-451` accessed `self.agents[agent_id]` directly on both the success and failure branches of `handle_command_response()`. If an agent was unregistered between command send and response, this would raise `KeyError`.

**Fix applied:** Changed to `self.agents.get(agent_id)` with guard on both branches:
```python
agent = self.agents.get(agent_id)
if agent:
    agent.total_commands_executed += 1
```

**Files changed:** `agent_controller.py:443-451`

---

### R23. `pyproject.toml` missing dashboard dependencies (was Medium)

**Problem:** `requirements.txt` listed `fastapi`, `uvicorn[standard]`, `jinja2`, `python-multipart`, `psutil`, `PyJWT` but `pyproject.toml` only had core deps. Installing via `pip install .` would miss dashboard dependencies.

**Fix applied:** Added all 6 packages to `pyproject.toml` `[project].dependencies` to match `requirements.txt`.

**Files changed:** `pyproject.toml`

---

### R24. Missing `transport.websocket` config section (was Medium)

**Problem:** `transport/websocket_transport.py:40-63` reads `transport.websocket.reconnect_interval`, `transport.websocket.heartbeat_interval`, `transport.websocket.ssl`, `transport.websocket.verify_ssl` via `.get()` with hardcoded defaults. No matching section existed in `default_config.yaml`, making the defaults invisible to users.

**Fix applied:** Added `transport.websocket` section to `config/default_config.yaml` after the `telegram` section:
```yaml
websocket:
  url: ""
  reconnect_interval: 5
  heartbeat_interval: 30
  ssl: false
  verify_ssl: true
```

**Files changed:** `config/default_config.yaml`

---

### R25. Dead config key `profiler.store_profiles` (was Low)

**Problem:** `config/default_config.yaml:158` had `store_profiles: true` under `profiler` but no code reads this key (the `biometrics.store_profiles` key at line 120 IS used, this one is not).

**Fix applied:** Commented out with note: `# Unused — profiler.store_profiles is never read by code`.

**Files changed:** `config/default_config.yaml`

---

### R26. Dead config key `service.display` (was Low)

**Problem:** `config/default_config.yaml:198` had `display: ":0"` but no service manager code reads it.

**Fix applied:** Commented out with note: `# Unused — not read by any service manager code`.

**Files changed:** `config/default_config.yaml`

---

# Part 2 — Remaining Issues

Issues below are still open. Grouped by category with full file references and line numbers.

---

## Category A: Async/Sync Safety (Critical — runtime crashes)

### A1. `send_command()` calls `asyncio.create_task()` from sync context

**Priority:** Critical
**Impact:** `RuntimeError: no running event loop` when called from sync FastAPI route handlers or non-async code paths.

**Root cause:** `Controller.send_command()` is a sync method that internally calls `asyncio.create_task(queue.put(...))` to enqueue commands. This only works if called from within a running async event loop.

**Affected files:**

| File | Lines | What happens |
|------|-------|-------------|
| `agent_controller.py` | 362-393 | `send_command()` is `def` (sync). Lines 370-390 attempt `asyncio.create_task()` with fallbacks to `run_coroutine_threadsafe()` and `asyncio.run()`. The fallback chain is fragile — `asyncio.run()` creates a new loop which conflicts if one already exists. |
| `fleet/controller.py` | 225-238 | `FleetController.send_command()` calls `super().send_command()`, inheriting the problem. |
| `dashboard/routes/fleet_dashboard_api.py` | 93 | Calls `controller.send_command()` from a FastAPI route handler (which runs in an async context, so `create_task` works here — but the fallback paths are still problematic). |

**What a fix requires:**
- Make `send_command()` async (`async def`) and await the queue put.
- Or use `queue.put_nowait()` (sync, non-blocking) since `asyncio.PriorityQueue` supports it.
- Update all callers to match the new signature.

---

### A2. `send_command_async()` wraps the broken sync `send_command()`

**Priority:** Critical
**Impact:** Same `RuntimeError` propagates through the async wrapper.

**Affected files:**

| File | Lines | What happens |
|------|-------|-------------|
| `fleet/controller.py` | 260-265 | `async def send_command_async()` simply calls `self.send_command()` (sync), which internally tries `asyncio.create_task()`. The async wrapper doesn't help because the underlying sync method still has the event loop detection issues. |

**What a fix requires:**
- If `send_command()` becomes async (see A1), this wrapper becomes unnecessary.
- Or rewrite to directly `await queue.put()`.

---

### A3. `_handle_shutdown()` calls `asyncio.create_task()` from sync handler

**Priority:** Critical
**Impact:** `RuntimeError` when the shutdown command is received and dispatched.

**Affected files:**

| File | Lines | What happens |
|------|-------|-------------|
| `agent_controller.py` | ~1000 | `def _handle_shutdown(self, params)` is a sync function registered as a command handler via `register_command_handler()`. It calls `asyncio.create_task(self.stop())`. Since command handlers are called from `run_in_executor()` (a thread pool), there is no running event loop in that thread. |

**What a fix requires:**
- Use `asyncio.run_coroutine_threadsafe(self.stop(), self._loop)` where `self._loop` is the main event loop stored during `start()`.
- Or set a `self._shutdown_requested` flag and let the main loop handle it.

---

## Category B: Frontend ↔ Backend Mismatches (High — silent failures)

### B1. WebSocket action name mismatch: `command` vs `send_to_agent`

**Priority:** High
**Impact:** Commands sent from the dashboard Live page via WebSocket will be silently ignored — the backend doesn't recognize the action type.

**Affected files:**

| File | Lines | What happens |
|------|-------|-------------|
| `dashboard/static/js/ws-client.js` | 364 | Frontend sends: `this.send('command', {agent_id, action, parameters})` |
| `dashboard/routes/websocket.py` | 246 | Backend handles: `elif action == "send_to_agent":` |
| `dashboard/routes/websocket.py` | 232-272 | Full action dispatch: `get_status`, `broadcast`, `send_to_agent`, `get_captures`. No `command` case. |

**What a fix requires:**
Either:
- Change `ws-client.js:364` from `'command'` to `'send_to_agent'`
- Or add `elif action == "command":` as an alias in `websocket.py:246`

---

### B2. Frontend expects `heartbeat` WS messages, backend never sends them

**Priority:** Medium
**Impact:** Dead handler code. Frontend `ws-client.js:204` registers a handler for `heartbeat` messages. The backend only sends `agent_status` (when an agent heartbeats). Not a crash, but misleading.

**Affected files:**

| File | Lines | What happens |
|------|-------|-------------|
| `dashboard/static/js/ws-client.js` | 203-205 | `this.handlers.set('heartbeat', ...)` — handler registered but never triggered |
| `dashboard/routes/websocket.py` | 289-300 | Agent heartbeats are received and rebroadcast as `{"type": "agent_status", ...}`, NOT as `{"type": "heartbeat", ...}` |

**What a fix requires:**
Either:
- Backend sends a `heartbeat` message type alongside `agent_status`
- Or frontend handles `agent_status` instead (it already does at line 183, so just remove the dead `heartbeat` handler)

---

### B3. Backend sends `captures` WS message, no specific frontend handler

**Priority:** Low
**Impact:** Message is caught by generic handler, works but not type-safe.

**Affected files:**

| File | Lines | What happens |
|------|-------|-------------|
| `dashboard/routes/websocket.py` | 272 | Backend sends `{"type": "captures", "data": [...]}` in response to `get_captures` action |
| `dashboard/static/js/ws-client.js` | — | No `this.handlers.set('captures', ...)` call. Falls through to default handler. |

**What a fix requires:**
- Add `this.handlers.set('captures', (data) => { ... })` in `ws-client.js` for explicit handling.

---

## Category C: Config Keys Defined But Never Read (Medium — dead config)

These config keys exist in `config/default_config.yaml` but no code reads them via `settings.get()` or `config.get()`. They give users the false impression that these features are configurable.

| # | Config key | YAML line | Expected consumer | Status |
|---|-----------|-----------|-------------------|--------|
| C1 | `fleet.transport.http_enabled` | 215 | Should gate HTTP transport for agents | Never checked |
| C2 | `fleet.transport.websocket_enabled` | 216 | Should gate WebSocket transport for agents | Never checked |
| C3 | `fleet.transport.redis_enabled` | 217 | Should gate Redis transport | Never checked |
| C4 | `fleet.transport.redis_url` | 218 | Should configure Redis connection | Never read |
| C5 | `fleet.security.max_payload_size_mb` | 220 | Should limit incoming payload size | Never enforced |
| C6 | `fleet.security.rate_limit_requests_per_minute` | 221 | Should throttle agent requests | Never enforced |
| C7 | `fleet.auth.max_failed_attempts` | 207 | Should lock out after N failed logins | Never checked |
| C8 | `fleet.auth.lockout_minutes` | 208 | Should define lockout duration | Never enforced |
| C9 | `fleet.controller.command_timeout_seconds` | 212 | Should timeout pending commands | Never applied |
| C10 | `fleet.controller.max_queue_depth` | 213 | Should limit command queue size | Never enforced |

**What a fix requires for each:**
- Either implement the feature that reads the key, or remove the key from config with a comment explaining it's not yet supported.

---

## Category D: Code Reads Config Keys That Don't Exist (Medium — invisible defaults)

These config keys are read by code via `.get("key", default)` but don't appear in `default_config.yaml`. The code works via hardcoded fallbacks, but users can't discover or override these settings.

### D1. Agent-level config keys (agent_controller.py)

| Config key read | File | Line | Hardcoded default |
|----------------|------|------|------------------|
| `agent_id` | `agent_controller.py` | 591 | `str(uuid4())` |
| `controller_url` | `agent_controller.py` | 592 | `""` |
| `hostname` | `agent_controller.py` | 593 | `socket.gethostname()` |
| `platform` | `agent_controller.py` | 594 | `sys.platform` |
| `version` | `agent_controller.py` | 595 | `"1.0.0"` |
| `heartbeat_interval` | `agent_controller.py` | 627 | `60` |
| `reconnect_interval` | `agent_controller.py` | 628 | `30` |
| `max_retries` | `agent_controller.py` | 629 | `3` |
| `transport_method` | `agent_controller.py` | 651 | `"http"` |
| `command_poll_interval` | `agent_controller.py` | 774 | `5` |
| `commands_endpoint` | `agent_controller.py` | 775 | `""` |

### D2. Controller-level config keys (agent_controller.py)

| Config key read | File | Line | Hardcoded default |
|----------------|------|------|------------------|
| `heartbeat_timeout` | `agent_controller.py` | 276 | `120` |
| `max_command_history` | `agent_controller.py` | 277 | `1000` |
| `cleanup_interval` | `agent_controller.py` | 278 | `300` |

### D3. Fleet agent config (fleet/agent.py)

| Config key read | File | Line | Hardcoded default |
|----------------|------|------|------------------|
| `sign_requests` | `fleet/agent.py` | 92 | `false` |

### D4. Mouse capture config (capture/mouse_capture.py)

| Config key read | File | Line | Hardcoded default |
|----------------|------|------|------------------|
| `capture.mouse.move_throttle_interval` | `capture/mouse_capture.py` | 47 | `0.1` |

**What a fix requires:**
- Add these keys to `default_config.yaml` under appropriate sections (e.g., `fleet.agent.*`, `fleet.controller.*`, `capture.mouse.*`) so they're discoverable and overridable.

---

## Category E: Import Chain Issues (Medium — fragile)

### E1. Circular import risk: `transport` ↔ `utils.redis_queue`

**Priority:** Medium
**Impact:** Works currently due to import ordering, but fragile. Could break if imports are reordered.

**Import chain:**
1. `transport/__init__.py:96` → `__import__("transport.redis_transport")`
2. `transport/redis_transport.py:9` → `from utils.redis_queue import RedisTransport`
3. `utils/redis_queue.py:23` → `from transport import register_transport`
4. Back to `transport/__init__.py`

**Why it works today:** `register_transport` is defined at `transport/__init__.py:29-38` before the auto-import loop at line 87. By the time step 3 runs, `register_transport` is already in `transport`'s namespace.

**What a fix requires:**
- Move `register_transport` to a separate `transport._registry` module to break the cycle cleanly.
- Or document the import order dependency with a comment.

---

### E2. Missing `redis` and `websockets` in dependencies

**Priority:** Medium
**Impact:** `import redis` in `utils/redis_queue.py:21` and `import websockets` in `transport/websocket_transport.py:20` will crash if packages aren't installed. They're optional transports, so this is acceptable if documented but currently isn't.

**Affected files:**

| Package | Required by | In requirements.txt? | In pyproject.toml? |
|---------|------------|---------------------|-------------------|
| `redis>=5.0.0` | `utils/redis_queue.py:21` | No | No |
| `websockets>=11.0` | `transport/websocket_transport.py:20` | No | No |

**What a fix requires:**
- Add to `[project.optional-dependencies]` in `pyproject.toml` under a `fleet` or `transports` extra:
  ```toml
  [project.optional-dependencies]
  transports = ["redis>=5.0.0", "websockets>=11.0"]
  ```
- Or add to main dependencies if they're always needed.

---

## Category F: Miscellaneous (Low)

### F1. `/health` endpoint has no frontend consumer

**File:** `dashboard/routes/api.py:36-39`
**Impact:** None — likely intentional for external monitoring (load balancers, uptime checks). Not a bug.

---

### F2. `APP_ENV` read via `os.environ.get()` directly

**File:** `dashboard/app.py:114`
**Impact:** Minor inconsistency. Uses `os.environ.get("APP_ENV", "development")` directly instead of going through the `Settings` system (`KEYLOGGER_` prefix pattern). Acceptable since it's needed before settings are fully loaded.

---

# Summary Table

## Resolved

| ID | Issue | Fixed by | Round |
|----|-------|----------|-------|
| R1 | Missing `/analytics` route (404) | Code review | 1 |
| R2 | `url_for('login')` Flask syntax | Code review | 1 |
| R3 | RedisTransport wrong directory | User | 2 |
| R4 | Base Agent never instantiated | User | 2 |
| R5 | Agent command listener stub | User | 2 |
| R6 | WebSocket receive loop no-op | User | 2 |
| R7 | No WebSocket frontend client | User | 2 |
| R8 | Signatures never verified | User | 2 |
| R9 | Three incompatible protocols | User | 2 |
| R10 | WS handlers log-only / mock data | User | 2 |
| R11 | `/live` route redundant | User | 2 |
| R12 | Controller keys not persisted | User | 2 |
| R13 | Fleet API encryption documented | User | 2 |
| R14 | ProfileMatcher integrated | User | 2 |
| R15 | EventBus integrated | User | 2 |
| R16 | Legacy scripts archived | User | 2 |
| R17 | FleetAgent real metrics | User | 2 |
| R18 | `set_storage_references()` missing SQLiteStorage | User | 3 |
| R19 | Signature verification default off | User | 3 |
| R20 | Path traversal in screenshots | User | 3 |
| R21 | TODO enrollment key extraction | User | 3 |
| R22 | Unsafe dict access `self.agents[agent_id]` | Code review | 4 |
| R23 | `pyproject.toml` missing deps | Code review | 4 |
| R24 | Missing `transport.websocket` config | Code review | 4 |
| R25 | Dead config `profiler.store_profiles` | Code review | 4 |
| R26 | Dead config `service.display` | Code review | 4 |

## Remaining

| ID | Issue | Priority | Category |
|----|-------|----------|----------|
| A1 | `send_command()` async/sync crash | Critical | Async safety |
| A2 | `send_command_async()` wraps broken sync | Critical | Async safety |
| A3 | `_handle_shutdown()` create_task from sync | Critical | Async safety |
| B1 | WS action `command` vs `send_to_agent` | High | Frontend-backend |
| B2 | Frontend expects `heartbeat` WS, never sent | Medium | Frontend-backend |
| B3 | No frontend handler for `captures` WS type | Low | Frontend-backend |
| C1-C10 | 10 config keys defined but never read | Medium | Config wiring |
| D1-D4 | 16+ config keys read but not in YAML | Medium | Config wiring |
| E1 | Circular import risk (transport ↔ redis) | Medium | Import chain |
| E2 | `redis` and `websockets` not in deps | Medium | Dependencies |
| F1 | `/health` no frontend consumer | Low | Informational |
| F2 | `APP_ENV` bypasses settings | Low | Consistency |
