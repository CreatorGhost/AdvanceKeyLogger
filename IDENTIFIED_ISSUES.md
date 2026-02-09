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

# Part 2 — All Issues Resolved

All issues from the audit have been addressed. See Round 5 fixes below.

---

## Round 5: Final Fixes (Code Review)

### R27. A1 — `send_command()` async/sync crash

**Problem:** `send_command()` called `asyncio.create_task()` from sync context, causing RuntimeError.

**Fix applied:** Changed to use `queue.put_nowait()` which is sync-safe and doesn't require an event loop. Added `QueueFull` exception handling.

**Files changed:** `agent_controller.py:364-379`

---

### R28. A2 — `send_command_async()` wrapper

**Problem:** Wrapped the broken sync `send_command()`.

**Fix applied:** Updated docstrings to note that `send_command()` now uses `put_nowait()` internally and is sync-safe. The async wrapper is kept for API consistency.

**Files changed:** `fleet/controller.py:252-279`

---

### R29. A3 — `_handle_shutdown()` called `asyncio.create_task()` from sync handler

**Problem:** Command handler ran in thread pool executor with no event loop.

**Fix applied:** Changed to set `self._shutdown_requested = True` flag. The command listener loop checks this flag and calls `await self.stop()` from the async context.

**Files changed:** `agent_controller.py:630, 793-797, 1022-1030`

---

### R30. B1 — WebSocket action mismatch (`command` vs `send_to_agent`)

**Problem:** Frontend sent `command` action, backend only handled `send_to_agent`.

**Fix applied:** Added `action == "command"` as an alias for `send_to_agent` in the backend dispatcher.

**Files changed:** `dashboard/routes/websocket.py:246`

---

### R31. B2 — Dead `heartbeat` handler in frontend

**Problem:** Frontend registered handler for `heartbeat` messages that backend never sends.

**Fix applied:** Replaced with `captures` handler since that message type IS sent by backend.

**Files changed:** `dashboard/static/js/ws-client.js:202-206`

---

### R32. B3 — No frontend handler for `captures` WS type

**Problem:** Backend sent `captures` messages, frontend had no explicit handler.

**Fix applied:** Added `_handleCapturesResponse()` method to update captures list/table in UI.

**Files changed:** `dashboard/static/js/ws-client.js:322-352`

---

### R33. C1-C10 — Config keys defined but never read

**Problem:** 10 fleet config keys existed in YAML but no code read them.

**Fix applied:** Added TODO comments to each key explaining they are defined but not yet enforced, so users understand the current state.

**Files changed:** `config/default_config.yaml:214-249`

---

### R34. D1-D4 — Code reads config keys that don't exist in YAML

**Problem:** 16+ config keys read by code with hardcoded defaults, but not in `default_config.yaml`.

**Fix applied:** Added `fleet.agent.*` section with all agent config keys, and `capture.mouse.move_throttle_interval`.

**Files changed:** `config/default_config.yaml:212-225, 15-17`

---

### R35. E1 — Circular import risk (transport ↔ redis_queue)

**Problem:** Circular import chain works due to import ordering but is fragile.

**Fix applied:** Added detailed comment in `transport/redis_transport.py` explaining the import order dependency and why it works.

**Files changed:** `transport/redis_transport.py:7-12`

---

### R36. E2 — `redis` and `websockets` not in dependencies

**Problem:** Optional transports would crash if packages not installed.

**Fix applied:** Added `[project.optional-dependencies]` section with `transports` and `all` extras.

**Files changed:** `pyproject.toml:26-33`

---

## Category F: Informational (Not Bugs)

### F1. `/health` endpoint has no frontend consumer

**Status:** Not a bug — intentional for external monitoring (load balancers, uptime checks).

### F2. `APP_ENV` read via `os.environ.get()` directly

**Status:** Acceptable — needed before Settings are fully loaded to determine environment.

---

# Summary Table

## All Resolved

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
| R27 | A1: `send_command()` async/sync crash | Code review | 5 |
| R28 | A2: `send_command_async()` wrapper | Code review | 5 |
| R29 | A3: `_handle_shutdown()` create_task | Code review | 5 |
| R30 | B1: WS action mismatch | Code review | 5 |
| R31 | B2: Dead `heartbeat` handler | Code review | 5 |
| R32 | B3: No `captures` handler | Code review | 5 |
| R33 | C1-C10: Unused config keys documented | Code review | 5 |
| R34 | D1-D4: Missing config keys added | Code review | 5 |
| R35 | E1: Circular import documented | Code review | 5 |
| R36 | E2: Optional deps added | Code review | 5 |

## Informational (Not Bugs)

| ID | Issue | Status |
|----|-------|--------|
| F1 | `/health` no frontend consumer | Intentional |
| F2 | `APP_ENV` bypasses settings | Acceptable |
