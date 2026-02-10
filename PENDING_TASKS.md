# Pending Tasks

**Updated:** 2026-02-10
**Branch:** `codex/fleet-management`

---

## What Was Completed

### Round 1 — Bug Fixes (17 issues)
All 17 disconnection bugs fixed: missing routes (analytics 404), Flask syntax in FastAPI templates (`url_for`), broken WebSocket auth, storage class mismatches, import errors, config key typos, dead code removal, async/sync safety, and more.

### Round 2 — Follow-up Fixes (4 issues)
Fleet controller key persistence, fleet storage schema alignment, command queue async safety, settings public API.

### Round 3 — Comprehensive Audit (30 issues)
Crash prevention, config cleanup, dependency sync, frontend-backend protocol alignment, dead config key annotation.

### Round 4 — Frontend Integration Gaps (5 fixes)
- WebSocket `send()` protocol mismatch fixed (`{action, ...data}` format)
- `sendCommand` / `broadcastCommand` message format aligned
- Agent list rendering + connected-agents count wired to live DOM
- Status polling interval (30s) added
- System resource metrics (CPU/memory/disk via psutil) added to `get_status`

### Round 5 — Final Verification & Fixes (10 issues)
| ID | Description | File(s) |
|----|-------------|---------|
| C1 | `new_capture` broadcast flattened for frontend | `websocket.py` |
| H1 | Signature verification default aligned with `sign_requests` | `default_config.yaml` |
| H2 | Safe `.get()` for access/refresh tokens | `fleet/agent.py` |
| H3 | JSON parse error handling in command polling | `fleet/agent.py` |
| M1 | JWT fallback in WebSocket session validation | `websocket.py` |
| M2 | Priority enum `KeyError` guard | `fleet/controller.py` |
| M3 | Null check on `public_key.decode()` | `fleet/agent.py` |
| M4 | Command palette missing `/fleet` and `/live` links | `base.html` |
| L1 | Module-level import for `system_info` (was dynamic in loop) | `fleet/agent.py` |
| L2 | `settings.as_dict()` instead of private `_config` | `dashboard/app.py` |

### README
Fully rewritten to reflect all current features: fleet management, dashboard (8 pages), WebSocket real-time, transport/capture plugin systems, biometrics, E2E encryption, architecture diagram, project structure, config reference, and CLI options.

### Stale Docs Cleaned
Deleted: `ADVANCED_FEATURES_CHECKLIST.md`, `OPERATIONS.md`, `README_FLEET.md`, `FLEET_GAPS.md`, `REMAINING_ISSUES_PLAN.md`, `IDENTIFIED_ISSUES.md` — all superseded by README and this file.

---

## Pending Tasks

### P1. Test Suite (High)
No test suite has been run to verify the changes end-to-end. Need to:
- Run existing tests (`pytest`) and fix any failures
- Add unit tests for `FleetController`, `FleetAgent`, `FleetStorage`
- Add integration tests for REST API endpoints (`/api/v1/fleet/*`)
- Add WebSocket connection tests (dashboard + agent endpoints)
- Add frontend smoke tests (pages load without JS errors)

### P2. Dead Config Keys Cleanup (Low)
12 config keys in `default_config.yaml` are annotated with `# TODO: dead key` but still present. They should be removed once confirmed no external tooling depends on them:
- `transport.websocket.server_url`
- `transport.websocket.auth_token`
- `transport.websocket.reconnect_interval`
- `transport.websocket.max_retries`
- `transport.websocket.signing_key`
- `server.host`, `server.port`, `server.auth_token`, `server.use_ssl`, `server.ssl_cert`, `server.ssl_key`
- `encryption.key`

### P3. Production Hardening (High)
- Change default JWT secret from `"change-me-in-production"` to require explicit config
- Change default session secret key similarly
- Enable HTTPS/TLS configuration in dashboard
- Add rate limiting to REST API endpoints
- Add CORS configuration for dashboard

### P4. Agent WebSocket Transport (Medium)
Agents currently use REST polling (`fleet/agent.py` polls `GET /commands` every 5s). The WebSocket endpoint `/ws/agent/{agent_id}` exists and works, but `FleetAgent` doesn't use it. Wiring agents to use WebSocket would reduce latency and server load.

### P5. Settings Page Functionality (Medium)
The `/settings` page exists in the sidebar but the actual settings management UI (viewing/editing config, managing users, etc.) needs implementation.

### P6. Role-Based Access Control (Low)
Currently all authenticated users have full access. Add roles:
- `admin` — full control (commands, config changes)
- `viewer` — read-only (dashboard, captures, analytics)

### P7. Screenshots Page Data Integration (Low)
The `/screenshots` page template exists but needs real data integration with the capture storage system for screenshot-type captures.

### P8. Dashboard Analytics Real Data (Low)
The `/analytics` page uses the API endpoints (`/api/analytics/activity`, `/api/analytics/summary`) but these may return mock/minimal data. Wire to real capture statistics from SQLite storage.

### P9. Fleet Agent Groups & Tags (Low)
The `agent_controller.py` base supports tags but the dashboard UI doesn't expose agent grouping, filtering by tags, or bulk operations on agent groups.

### P10. Command History UI (Low)
Commands are persisted in `fleet.db` but the dashboard doesn't have a dedicated view to browse command history, filter by agent/status, or see response details.
