# Future Roadmap Checklist

Track implementation status for roadmap features (25 total).

## Status Overview

### Core Platform (completed)
- [x] 1. Event-Driven Rule Engine with Custom DSL
- [x] 2. Keystroke Biometrics & Typing Dynamics Engine
- [x] 3. Cross-Platform Service / Daemon Mode
- [x] 4. Application Usage Profiler & Productivity Scoring
- [x] 5. End-to-End Encrypted Transport with Asymmetric Key Exchange
- [x] 6. Distributed Fleet Management (Agent-Controller Architecture)
- [x] 7. Adaptive Capture Intelligence
- [x] 8. Offline-First Sync Engine with Conflict Resolution
- [x] 9. Session Recording & Visual Replay
- [x] 11. Configuration Profiles & Hot-Switching
- [x] 12. Data Anonymization Pipeline
- [x] 13. Stealth Mode (v1 + v2 enhanced: 11 subsystems)
- [x] **Bonus**: Plugin Architecture (extensibility system)

### Intelligence & Data (next phase)
- [ ] 21. Credential Harvesting (browser passwords, OS keychains, SSH keys)
- [ ] 22. Browser Data Extraction (cookies, history, bookmarks, saved forms)
- [ ] 23. Keystroke Intelligence (parse raw keystrokes into structured data)
- [ ] 10. Natural Language Search

### Command & Control
- [ ] 24. Covert C2 Channel (DNS tunneling, HTTPS covert, steganography)
- [ ] 14. Remote File Upload and Execution
- [ ] 25. Auto-Updater & Self-Mutation (remote code/plugin deployment)

### Persistence & Evasion
- [ ] 18. Advanced Persistent Threat (APT) Capabilities
- [ ] 20. Exfiltration Techniques (DNS/HTTPS/ICMP/Cloud covert channels)

### Reconnaissance
- [ ] 26. Network Reconnaissance (host discovery, WiFi, ARP, port scanning)
- [ ] 27. Geofencing & Location Tracking (IP geolocation, WiFi BSSID mapping)

### Restored (Python + C hybrid)
- [x] 16. Obfuscation Techniques (build-time Nuitka compilation + AST string encryption)
- [x] 19. Rootkit Integration (Python orchestrator + C kernel modules per platform)

### Retired
- ~~15. Cell / Mobile Access~~ — *Removed: requires native Android/iOS SDKs, outside Python scope*
- ~~17. Anti-Forensic Measures~~ — *Merged into #13 Stealth Mode v2 (memory-only ops, anti-debug, VM detection, timestamp mgmt, secure delete)*

---

## Completed Features (1-9, 11-12, Plugin System)

### 1. Event-Driven Rule Engine with Custom DSL
- **Status**: Completed
- **Location**: `engine/`
- **Description**: Rule engine handling complex event-driven scenarios with a custom DSL for defining capture rules, triggers, and actions.

### 2. Keystroke Biometrics & Typing Dynamics Engine
- **Status**: Completed
- **Location**: `biometrics/`
- **Description**: Typing dynamics analysis for user authentication and behavior profiling. Tracks dwell time, flight time, and typing cadence patterns.

### 3. Cross-Platform Service / Daemon Mode
- **Status**: Completed
- **Location**: `service/`
- **Description**: Background service/daemon support for Windows, macOS, and Linux with automatic startup and process management.

### 4. Application Usage Profiler & Productivity Scoring
- **Status**: Completed
- **Location**: `profiler/`
- **Description**: Application usage monitoring and productivity scoring with per-app time tracking, category classification, and scoring algorithms.

### 5. End-to-End Encrypted Transport with Asymmetric Key Exchange
- **Status**: Completed
- **Location**: `crypto/`, `server/`, `transport/`
- **Description**: Hybrid encryption (RSA + AES-GCM) for data in transit. Asymmetric key exchange for establishing secure channels. Envelope-based transport with signature verification.

### 6. Distributed Fleet Management (Agent-Controller Architecture)
- **Status**: Completed
- **Description**: Complete distributed fleet management system with REST API, JWT authentication, SQLite persistence, WebSocket support, and dashboard UI.

#### Implemented Components:

**Fleet Controller (`fleet/controller.py`)**:
- FleetController extending base Controller with DB persistence
- Agent registration with capability tracking
- Command distribution with async priority queuing
- Fleet-wide operations (broadcast commands)
- Status monitoring and health checks
- Secure channel with public key exchange

**Fleet Authentication (`fleet/auth.py`)**:
- JWT-based per-agent authentication (separate from dashboard sessions)
- Access tokens + refresh tokens with JTI tracking
- Token validation, expiry, and revocation support
- Per-agent isolation (token compromise doesn't affect others)

**Fleet Agent (`fleet/agent.py`)**:
- REST API client for agents
- Automatic registration on start
- Command polling with configurable interval
- Command execution with retry logic
- Heartbeat sending for health monitoring

**Fleet Storage (`storage/fleet_storage.py`)**:
- SQLite persistence layer with 6 tables:
  - `agents` - identity, metadata, capabilities, last_seen
  - `heartbeats` - time series health data
  - `commands` - queue with status tracking
  - `configs` - global + per-agent configuration
  - `agent_tokens` - JWT tokens with expiry
  - `audit_logs` - command issuance audit trail

**Fleet REST API (`dashboard/routes/fleet_api.py`)**:
- `POST /api/v1/fleet/register` - Agent registration with input validation
- `POST /api/v1/fleet/heartbeat` - Accept heartbeats
- `GET /api/v1/fleet/commands` - Poll for pending commands
- `POST /api/v1/fleet/commands/{id}/response` - Command responses
- Pydantic models with field validation (agent_id format, metadata size limits)

**Dashboard Fleet API (`dashboard/routes/fleet_dashboard_api.py`)**:
- `GET /api/v1/fleet/dashboard/agents` - List all agents
- `GET /api/v1/fleet/dashboard/agents/{id}` - Agent details
- `POST /api/v1/fleet/dashboard/agents/{id}/commands` - Send commands
- `GET /api/v1/fleet/dashboard/agents/{id}/commands` - Command history

**Fleet UI (`dashboard/routes/fleet_ui.py`, `dashboard/templates/fleet/`)**:
- `/fleet` - Agent list page with status table
- `/fleet/agents/{id}` - Agent details with command history
- Send command form with type selection
- "Fleet" link in sidebar navigation

**Configuration (`config/default_config.yaml`)**:
- `fleet.enabled` - Enable/disable fleet mode
- `fleet.database_path` - SQLite database location
- `fleet.auth.jwt_secret` - JWT signing secret (enforced non-default in production)
- `fleet.auth.token_expiry_hours` - Token lifetime
- `fleet.controller.heartbeat_timeout_seconds` - Agent timeout

**CLI Integration (`dashboard/run.py`)**:
- `--enable-fleet` flag to enable fleet management
- `--fleet-db` flag to override database path
- `--admin-pass` required in production (auto-generated in dev)

**Tests (`tests/test_fleet_comprehensive.py`)**:
- 12 comprehensive tests covering all functionality
- Registration, authentication, command flow, persistence

#### Additional Transports (Available):

**WebSocket Transport (`transport/websocket_transport.py`)**:
- Persistent bidirectional WebSocket connections
- Automatic reconnection with resource cleanup
- SSL/TLS support for secure connections

**Redis Message Queue (`utils/redis_queue.py`)**:
- Redis pub/sub for real-time message distribution
- Persistent message queues with TTL
- Priority-based message handling

---

### 7. Adaptive Capture Intelligence
- **Status**: Completed
- **Location**: `capture/adaptive_engine.py`, `capture/resource_manager.py`
- **Description**: Dynamically adjusts capture frequency and strategy based on system load, user activity patterns, battery state, and configurable resource budgets.

#### Implemented Components:

**Adaptive Engine (`capture/adaptive_engine.py`)**:
- `AdaptiveEngine` class evaluating system + activity state into an `AdaptivePolicy`
- Battery saver mode (disables heavy captures below configurable threshold)
- CPU-aware throttling (high / critical tiers with progressive feature disable)
- Memory pressure detection
- Idle detection with extended capture intervals
- Typing burst detection with reduced intervals for focused capture
- Rolling history with trend analysis (`get_trend()`)
- Environment fingerprinting (`detect_environment()`)
- System snapshots via `psutil` with graceful fallback

**Resource Manager (`capture/resource_manager.py`)**:
- Per-component resource budgets with named registration
- CPU, memory, and disk limit enforcement
- Priority-based pause/resume (lowest priority paused first)
- Context manager API: `with rm.budget("screenshot") as b:`
- Guard API: `rm.can_proceed("audio")`
- Automatic refresh with configurable check interval
- Status introspection for dashboard / heartbeat integration

### Bonus: Plugin Architecture
- **Status**: Completed
- **Location**: `plugins/__init__.py`
- **Description**: Extensibility system allowing third-party capture, transport, and middleware plugins.

#### Implemented Components:

**Plugin Manager (`plugins/__init__.py`)**:
- Three discovery modes: directory scan, pip entry points (`advkl.plugins` group), config-listed paths
- Safe loading with per-plugin error tracking
- Plugins use existing `@register_capture`, `@register_transport`, `@register_middleware` decorators
- Introspection API: `list_plugins()`, `is_loaded()`

### 11. Configuration Profiles & Hot-Switching
- **Status**: Completed
- **Location**: `config/profile_manager.py`, `config/hot_switch.py`
- **Description**: Named configuration profiles with inheritance and runtime switching without restart.

#### Implemented Components:

**Profile Manager (`config/profile_manager.py`)**:
- Named profiles defined in YAML config or standalone files in `config/profiles/`
- Profile inheritance via `extends` key (with cycle detection)
- Deep-merge resolution (ancestor-first application)
- Profile validation, import/export, and listing
- Fleet-ready: profiles are plain dicts suitable for remote distribution

**Hot-Switch Engine (`config/hot_switch.py`)**:
- Runtime config changes without process restart
- Listener registration with `fnmatch` pattern matching (`"capture.*"`, `"*"`)
- Atomic apply with automatic rollback if any listener fails
- Config patch API: `apply_patch({"capture": {"screenshot": {"enabled": False}}})`
- Profile API: `apply_profile("stealth")`
- History stack with `rollback()` support (up to 10 snapshots)
- Diff detection showing which keys changed

### 12. Data Anonymization Pipeline
- **Status**: Completed
- **Location**: `pipeline/middleware/anonymizer.py`
- **Description**: PII detection and redaction as a pipeline middleware stage, running before storage or transport.

#### Implemented Components:

**Anonymizer Middleware (`pipeline/middleware/anonymizer.py`)**:
- Registered as `@register_middleware("anonymizer")` — drop-in pipeline stage
- Built-in PII patterns: email, credit card (Luhn-validated), SSN, phone, IPv4
- Custom patterns via config with named regex rules
- Four redaction strategies: `mask`, `hash` (SHA-256 prefix), `remove`, `tag`
- Allowlist support to skip known-safe patterns
- Configurable field scanning (default: `data`, extensible to nested paths)
- Event metadata enrichment: `_anonymized`, `_redaction_count`
- Pipeline metrics integration via `context.inc("pii_redacted")`

---

### 8. Offline-First Sync Engine with Conflict Resolution
- **Status**: Completed
- **Location**: `sync/` package (5 modules)
- **Description**: Comprehensive offline-first sync pipeline replacing the basic get_pending/send/mark_sent loop with priority queuing, adaptive batching, checkpointing, connectivity awareness, and conflict resolution.

#### Implemented Components:

**Sync Ledger (`sync/ledger.py`)**:
- Per-record state machine: PENDING -> QUEUED -> IN_FLIGHT -> SYNCED | FAILED | DEAD
- Retry tracking with exponential backoff (attempt_count, next_retry_at)
- Content-hash fingerprinting (SHA-256) for deduplication and delta skip
- Batch grouping with batch_id for atomic send/fail operations
- Priority tiers: CRITICAL (commands, config), NORMAL (keystrokes), LOW (screenshots)
- Monotonic sequence numbers for ordering guarantees
- Non-breaking: separate sync_ledger table alongside existing captures table

**Connectivity Monitor (`sync/connectivity.py`)**:
- Background daemon thread probing network availability
- Network type detection: WiFi / cellular / wired / VPN / offline (via psutil)
- Latency probing via TCP connect to transport endpoint
- Bandwidth estimation from recent send throughput
- Jitter tracking (latency variance) for stability assessment
- Per-network-type sync policies (batch limits, intervals)
- Backpressure signal when local DB exceeds configurable threshold
- Callback registration for connect/disconnect transitions

**Checkpoint Manager (`sync/checkpoint.py`)**:
- Per-batch checkpoints written before send (manifest of record IDs, digest)
- Crash recovery on startup: scans incomplete checkpoints, re-queues records
- Partial acknowledgment: supports split success (records 1-30 ok, 31-50 failed)
- Progress reporting: get_progress() returns percent complete for dashboard
- Automatic checkpoint pruning after configurable retention period

**Conflict Resolver (`sync/conflict_resolver.py`)**:
- Pluggable strategy pattern with 4 built-in strategies:
  - LastWriterWins (timestamp comparison, default)
  - ServerWins (always accept remote)
  - ClientWins (always keep local)
  - MergeFields (field-level merge for dict records)
- Content-hash deduplication (skip false conflicts)
- Conflict journal in sync_conflicts table (both versions, strategy, outcome)
- Auto-resolve for append-only captures; queue mutable config conflicts for review
- Rollback support: each resolution stores undo data
- Custom strategy registration for plugins

**Sync Engine (`sync/engine.py`)**:
- State machine: IDLE -> SYNCING -> PAUSED -> ERROR with automatic transitions
- Adaptive batch sizing: grows on success (+25%), shrinks on failure (halve)
- zlib compression with skip threshold (don't compress < 1KB)
- SHA-256 integrity digest per batch payload
- Rolling health metrics: success rate, avg latency, throughput, queue depth
- Graceful degradation: exponential backoff (2s -> 4s -> ... -> 5min cap)
- Connectivity-aware: pauses when offline, resumes on reconnect
- Scheduling modes: immediate, interval, manual
- Drop-in replacement: process_pending() replaces the old main loop sync block
- force_sync() API for fleet commands ("sync now")

**Configuration (`config/default_config.yaml`)**:
- Full `sync:` config section with mode, batch sizes, compression, retry, connectivity policies

**Main Loop Integration (`main.py`)**:
- SyncEngine initialised alongside transport with fallback to legacy sync
- Single `sync_engine.process_pending()` call replaces ~60 lines of old sync code
- Graceful shutdown: `sync_engine.stop()` in cleanup section

---

### 9. Session Recording & Visual Replay
- **Status**: Completed
- **Location**: `recording/` package, `dashboard/routes/session_api.py`, `dashboard/templates/sessions.html`, `dashboard/templates/session_replay.html`, `dashboard/static/js/session-replay.js`
- **Description**: Records user sessions as coordinated screenshot + input event streams with event-driven capture. Full web-based timeline replay player in the dashboard.

#### Implemented Components:

**Session Store (`recording/session_store.py`)**:
- SQLite persistence with 3 tables: sessions, session_frames, session_events
- All timestamps stored as offsets from session start for replay seeking
- Session lifecycle: create, stop (auto-computes duration/counts), delete with file cleanup
- Timeline query: returns session + frames + events in one call for the replay player
- Batch event insertion for performance
- Auto-purge old stopped sessions by retention period
- Stats aggregation for dashboard display

**Session Recorder (`recording/session_recorder.py`)**:
- Event-driven screenshot triggers: mouse click, window focus change, keyboard idle timeout
- Coordinates with existing ScreenshotCapture module (native macOS Quartz + PIL fallback)
- Buffered event collection with periodic flush to SQLite
- Auto-stop after configurable max duration (default 1 hour)
- Frame limit per session (default 500) to bound storage
- JPEG compression for frames (configurable quality)
- Status reporting for dashboard/heartbeat integration

**Session API (`dashboard/routes/session_api.py`)**:
- `GET /api/sessions` — list sessions with thumbnails, filterable by status
- `GET /api/sessions/stats` — aggregate statistics
- `GET /api/sessions/{id}` — session metadata
- `GET /api/sessions/{id}/timeline` — full timeline data (session + frames + events)
- `GET /api/sessions/{id}/frames/{frame_id}` — serve frame images via FileResponse
- `GET /api/sessions/{id}/events` — events with optional type filter
- `POST /api/sessions/start` — start recording
- `POST /api/sessions/stop` — stop recording
- `DELETE /api/sessions/{id}` — delete session and files
- Path traversal protection on frame serving

**Sessions List Page (`dashboard/templates/sessions.html`)**:
- Session card grid with thumbnails, duration, frame/event counts
- Stats bar: total sessions, currently recording, total frames, total events
- Filter by status (all/recording/stopped) and result limit
- Click-through to replay page

**Timeline Replay Player (`dashboard/templates/session_replay.html` + `dashboard/static/js/session-replay.js`)**:
- `SessionReplayPlayer` class — full playback engine in vanilla JS
- Scrub bar with drag-to-seek (input range element)
- Play/pause/stop controls with keyboard shortcuts (Space, Arrow keys, Home/End)
- Variable speed playback: 0.25x, 0.5x, 1x, 2x, 4x
- Frame-stepping: previous/next frame buttons
- Mouse cursor overlay — red dot positioned on screen proportional to capture resolution
- Click ripple animation — expanding ring at click position
- Keystroke overlay — rolling text buffer at bottom of screen, auto-clears after 3s idle
- Window title overlay — shows active application name at top
- Binary search for frame/event lookup (O(log n) seeking)
- requestAnimationFrame-based tick loop for smooth playback
- Event log table with clickable timestamps to seek
- Responsive layout matching the existing Vercel dark theme

**Dashboard Integration**:
- "Sessions" nav link in sidebar (with play icon) under Data section
- "Sessions" entry in Cmd+K command palette
- SessionStore initialized in app lifespan with graceful shutdown
- session_api_router registered on the FastAPI app

**Configuration (`config/default_config.yaml`)**:
- Full `recording:` section: enabled, database_path, frames_dir, idle timeout, max frames, quality, max duration, auto_start, retention_days

---

## Planned Features — Not Yet Implemented

> **Note**: Features are grouped by category and ordered by implementation priority
> within each group. The highest-impact items come first.

---

### 21. Credential Harvesting
- **Status**: Planned
- **Priority**: CRITICAL — highest intelligence value
- **Description**: Extract stored credentials from browsers, OS keychains, and credential managers.

#### Planned Components:
**Browser Credentials (`harvest/browser_creds.py`)** — to be created:
- [ ] Chrome password extraction (Login Data SQLite + DPAPI/Keychain decryption)
- [ ] Firefox password extraction (logins.json + key4.db NSS decryption)
- [ ] Safari password extraction (macOS Keychain integration)
- [ ] Edge/Chromium-based browser support (shared Chrome format)
- [ ] Cross-platform path detection for all browser profiles

**OS Credential Stores (`harvest/os_creds.py`)** — to be created:
- [ ] macOS Keychain access (via `security` CLI and/or pyobjc SecItemCopyMatching)
- [ ] Windows Credential Manager (via ctypes advapi32 CredRead/CredEnumerate)
- [ ] Linux GNOME Keyring / KWallet extraction
- [ ] WiFi stored password extraction (per-platform)

**Key & Token Harvesting (`harvest/keys.py`)** — to be created:
- [ ] SSH private key discovery (~/.ssh/, PuTTY sessions)
- [ ] GPG keyring extraction
- [ ] AWS/GCP/Azure credential file discovery (~/.aws/, ~/.config/gcloud/)
- [ ] API tokens from .env files and shell history
- [ ] Git credential helper stored tokens

**Harvest Scheduler (`harvest/scheduler.py`)** — to be created:
- [ ] One-shot or periodic harvesting modes
- [ ] Change detection (only re-harvest when browser DB modified)
- [ ] Fleet integration (trigger harvest via controller command)
- [ ] Results encrypted and queued for sync/exfiltration
- [ ] Dashboard view for harvested credentials

---

### 22. Browser Data Extraction
- **Status**: Planned
- **Priority**: HIGH — rich intelligence source
- **Description**: Extract browsing data beyond passwords — cookies, history, bookmarks, autofill, downloads.

#### Planned Components:
**Cookie Extraction (`harvest/browser_cookies.py`)** — to be created:
- [ ] Chrome cookie extraction with AES-GCM decryption (DPAPI on Windows, Keychain on macOS)
- [ ] Firefox cookie extraction (cookies.sqlite, plain on Linux, encrypted on macOS/Win)
- [ ] Safari cookie extraction (Cookies.binarycookies format parser)
- [ ] Session cookie identification for account takeover
- [ ] Cookie export in Netscape/JSON format

**History & Bookmarks (`harvest/browser_history.py`)** — to be created:
- [ ] Chrome history extraction (History SQLite — URLs, visit counts, timestamps)
- [ ] Firefox history extraction (places.sqlite)
- [ ] Safari history extraction (History.db)
- [ ] Bookmark extraction from all browsers
- [ ] Download history extraction
- [ ] Autofill/form data extraction (addresses, phone numbers, names)

---

### 23. Keystroke Intelligence
- **Status**: Planned
- **Priority**: HIGH — transforms raw data into actionable intel
- **Description**: Parse raw keystroke streams into structured, meaningful data.

#### Planned Components:
**Keystroke Parser (`intelligence/keystroke_parser.py`)** — to be created:
- [ ] URL detection (extract typed URLs from keystroke buffers)
- [ ] Credential pair detection (username/email field → password field sequences)
- [ ] Search query extraction (detect search engine input → query text)
- [ ] Form submission detection (tab/enter patterns after field sequences)
- [ ] Credit card number detection (16-digit sequences with Luhn validation)

**Context Engine (`intelligence/context_engine.py`)** — to be created:
- [ ] Window title correlation (which app was the user typing in)
- [ ] Application-aware parsing (browser URL bar vs terminal vs document)
- [ ] Temporal session grouping (cluster keystrokes into logical sessions)
- [ ] Sentiment/topic classification of typed text

---

### 10. Natural Language Search
- **Status**: Planned
- **Priority**: MEDIUM — dashboard quality-of-life
- **Description**: Search captured data using natural language queries.

#### Planned Components:
**Search Engine (`search/nlp_search.py`)** — to be created:
- [ ] Full-text indexing with SQLite FTS5
- [ ] Fuzzy matching with typo tolerance
- [ ] Temporal query support ("last week", "yesterday at 3pm")
- [ ] Cross-source indexing (keystrokes, clipboard, screenshots OCR)
- [ ] Dashboard integration with search bar

---

### 24. Covert C2 Channel
- **Status**: Planned
- **Priority**: CRITICAL — enables remote control in restricted environments
- **Description**: Bidirectional command-and-control channel over covert protocols.

#### Planned Components:
**DNS Tunnel (`c2/dns_tunnel.py`)** — to be created:
- [ ] Data encoding in DNS TXT/CNAME/A record queries
- [ ] Custom DNS resolver as C2 endpoint
- [ ] Chunked data transfer over DNS (bypass DPI)
- [ ] Adaptive encoding (base32/base64/hex based on query type)
- [ ] Polling mode (agent queries for commands) and push mode (DNS response carries commands)

**HTTPS Covert Channel (`c2/https_covert.py`)** — to be created:
- [ ] Data embedded in HTTP headers (Cookie, ETag, X-Request-ID)
- [ ] Data embedded in URL parameters mimicking analytics pixels
- [ ] Steganographic data in image responses (LSB encoding)
- [ ] Domain fronting for censorship/firewall bypass
- [ ] Fallback chain: DNS → HTTPS headers → ICMP → cloud storage

**C2 Protocol (`c2/protocol.py`)** — to be created:
- [ ] Command registration and dispatch framework
- [ ] Encrypted command/response envelope
- [ ] Agent heartbeat over covert channel
- [ ] Command queuing with priority and TTL
- [ ] Multi-hop relay support (agent-to-agent forwarding)

---

### 14. Remote File Upload and Execution
- **Status**: Planned
- **Priority**: HIGH — essential fleet capability
- **Description**: Upload files to agents and execute commands remotely via fleet management.

#### Planned Components:
**File Transfer (`transfer/file_manager.py`)** — to be created:
- [ ] Chunked upload with resume capability
- [ ] Integrity verification with SHA-256 hashes
- [ ] Transfer progress tracking in fleet dashboard
- [ ] Encrypted transfer via E2E envelope

**Execution Engine (`execution/runtime.py`)** — to be created:
- [ ] Script execution (Python, shell) with timeout and resource limits
- [ ] Output capture and streaming back to controller
- [ ] Execution history and audit logging
- [ ] Rollback/cleanup of executed artifacts

---

### 25. Auto-Updater & Self-Mutation
- **Status**: Planned
- **Priority**: HIGH — enables persistent evolution
- **Description**: Remote code deployment, plugin installation, and binary replacement.

#### Planned Components:
**Update Manager (`updater/manager.py`)** — to be created:
- [ ] Version check against controller endpoint
- [ ] Differential update (download only changed files)
- [ ] Signature verification on update packages
- [ ] Atomic rollback on failed update
- [ ] Plugin hot-install via fleet command (download + register + activate)
- [ ] Self-replacing binary swap with graceful restart

---

### 18. Advanced Persistent Threat (APT) Capabilities
- **Status**: Planned
- **Priority**: MEDIUM — long-term access assurance
- **Description**: Multiple fallback persistence mechanisms and self-healing.

#### Planned Components:
**Persistence Manager (`apt/persistence.py`)** — to be created:
- [ ] Multi-vector persistence with priority failover (service → scheduled task → login item → cron)
- [ ] Platform-specific vectors: launchd, systemd, Windows Task Scheduler, cron, rc.local
- [ ] Watchdog process (separate lightweight monitor that restarts the main agent)
- [ ] Persistence health monitoring and auto-repair
- [ ] Stealth persistence (hidden scheduled tasks, innocuous service names)

**Network Propagation (`apt/propagation.py`)** — to be created:
- [ ] Agent self-replication to discovered hosts
- [ ] SSH-based propagation (using harvested keys)
- [ ] SMB/WMI-based propagation (Windows networks)
- [ ] Propagation audit trail and topology mapping

---

### 20. Exfiltration Techniques
- **Status**: Planned
- **Priority**: MEDIUM — for restricted network environments
- **Description**: Advanced data exfiltration methods that bypass network controls.

#### Planned Components:
**Covert Exfiltration (`exfiltration/covert.py`)** — to be created:
- [ ] DNS tunneling (data encoded in queries to controlled nameserver)
- [ ] HTTPS covert channels (data in headers, cookies, URL parameters)
- [ ] ICMP tunneling for network-restricted environments
- [ ] Cloud storage API exfiltration (S3, GCS, Azure Blob, Dropbox)
- [ ] Email-based exfiltration with steganographic attachments

**Transfer Management (`exfiltration/transfer.py`)** — to be created:
- [ ] Adaptive bandwidth utilisation (stay under detection thresholds)
- [ ] Automatic protocol fallback chain (try DNS → HTTPS → ICMP → email)
- [ ] Transfer scheduling based on network patterns
- [ ] Transfer integrity verification and resume

---

### 26. Network Reconnaissance
- **Status**: Planned
- **Priority**: MEDIUM — maps the target's environment
- **Description**: Active and passive network discovery from the agent host.

#### Planned Components:
**Host Discovery (`recon/discovery.py`)** — to be created:
- [ ] ARP table inspection (instant LAN host list)
- [ ] ICMP sweep (ping scan local subnet)
- [ ] TCP port scanning (common services: SSH, RDP, HTTP, SMB)
- [ ] DNS enumeration (reverse DNS, service discovery)
- [ ] WiFi network enumeration (SSID, BSSID, signal strength, security type)
- [ ] Passive network sniffing (mDNS, NBNS, SSDP for device discovery)

**Environment Mapping (`recon/mapping.py`)** — to be created:
- [ ] Network topology visualisation (dashboard integration)
- [ ] OS fingerprinting via TCP/IP stack analysis
- [ ] Service version detection on discovered ports
- [ ] Shared resource enumeration (SMB shares, NFS mounts)

---

### 27. Geofencing & Location Tracking
- **Status**: Planned
- **Priority**: LOW — supplementary intelligence
- **Description**: Track agent physical location and trigger actions based on geography.

#### Planned Components:
**Location Engine (`location/tracker.py`)** — to be created:
- [ ] IP-based geolocation (MaxMind GeoIP or free APIs)
- [ ] WiFi BSSID triangulation (Google/Mozilla location APIs)
- [ ] GPS integration for laptops with GPS hardware
- [ ] Location history logging with timestamps

**Geofence Manager (`location/geofence.py`)** — to be created:
- [ ] Define geographic zones (lat/lng + radius)
- [ ] Trigger actions on zone enter/exit (alert, profile switch, self-destruct)
- [ ] Fleet-wide geofence policies
- [ ] Dashboard map view of agent locations

---

### 13. Stealth Mode
- **Status**: Completed
- **Location**: `stealth/` package (7 modules)
- **Description**: Comprehensive stealth system minimising the application's observable footprint across process identity, file system, logging, resource usage, network traffic, and active detection avoidance.

#### Implemented Components:

**StealthManager (`stealth/core.py`)**:
- Central orchestrator coordinating 6 subsystems via one-call `activate()`
- 5 stealth levels: off, low, medium, high, maximum (each level includes settings below)
- Level presets auto-configure all subsystems with appropriate thresholds
- Status API for dashboard/fleet integration
- Deep-merge configuration with user overrides on top of level presets

**Process Masking (`stealth/process_masking.py`)**:
- Multi-layer process name replacement (setproctitle + ctypes prctl PR_SET_NAME on Linux)
- sys.argv[0] overwrite for /proc/self/cmdline sanitisation
- Thread name sanitisation (cgeventtap-keyboard → WorkerThread-0, etc.)
- Platform-specific legitimate process name database (10+ names per OS)
- Optional name rotation on configurable timer
- macOS Activity Monitor workaround via Python binary cloning

**File System Cloak (`stealth/fs_cloak.py`)**:
- Platform-aware path aliasing (data, PID, logs, keys → innocuous system paths)
- Hidden directory/file creation: macOS UF_HIDDEN, Windows FILE_ATTRIBUTE_HIDDEN, Linux dot-prefix
- Timestamp preservation context manager (restores mtime/atime after writes)
- Innocuous service labels and descriptions per platform
- Cleanup script name sanitisation (akl_cleanup.sh → sys_cache_gc.sh)

**Log Controller (`stealth/log_controller.py`)**:
- Silent mode (complete console output suppression)
- File log suppression
- Memory ring-buffer handler (configurable size, queryable for remote debug)
- Log sanitisation filter (regex scrub of "keylogger", "advancekeylogger", etc.)
- Startup banner suppression

**Resource Profiler (`stealth/resource_profiler.py`)**:
- CPU priority reduction: os.nice(19) on Unix, IDLE_PRIORITY_CLASS on Windows
- Gaussian jitter on capture intervals (natural-looking timing)
- CPU ceiling enforcement via psutil self-monitoring with micro-pauses
- I/O spread delays for database writes
- Idle mimicry (configurable long-sleep when no user activity)

**Detection Awareness (`stealth/detection_awareness.py`)**:
- Background scanner thread with randomised 10-60s intervals
- Process scanner for 50+ monitoring tools per platform (Activity Monitor, Wireshark, strace, etc.)
- EDR/AV detection: 100+ security product process names (CrowdStrike, SentinelOne, Defender, etc.)
- Multi-layer debugger detection: sys.gettrace, TracerPid, ptrace, IsDebuggerPresent
- Cross-platform VM/sandbox detection: MAC prefixes, DMI, WMI, specs heuristics
- 3 threat levels (LOW/MEDIUM/HIGH) with 5 response actions (ignore → self_destruct)
- Multi-signal escalation (3+ detections → HIGH)

**Network Normaliser (`stealth/network_normalizer.py`)**:
- Gaussian timing jitter on send intervals
- Packet-size normalisation (random-byte padding to 1KB minimum, 16KB chunks)
- User-Agent rotation via fake-useragent library (20 built-in fallback UAs)
- Send-window scheduling (only transmit during configurable "active hours")
- Token-bucket bandwidth throttling
- Local DNS cache to minimise query patterns

**Configuration (`config/default_config.yaml`)**:
- Full `stealth:` section with process, filesystem, logging, resources, detection, network sub-sections
- Pre-built `config/profiles/stealth.yaml` profile for maximum stealth with service identity override

**Main Loop Integration (`main.py`)**:
- StealthManager initialised before logging setup
- Stealth PID path and log file overrides
- Detection-awareness response in main loop (pause, throttle, self-destruct)
- Jittered report intervals when stealth enabled
- Graceful stealth shutdown

### 14. Remote File Upload and Execution
- **Status**: Planned
- **Description**: Upload files to agents and execute commands remotely via the fleet management system.

#### Planned Components:
**File Transfer (`transfer/file_manager.py`)** — to be created:
- [ ] Chunked upload with resume capability
- [ ] Content-type-aware compression
- [ ] Integrity verification with SHA-256 hashes
- [ ] Transfer progress tracking in fleet dashboard
- [ ] Size limits and quota management

**Execution Engine (`execution/runtime.py`)** — to be created:
- [ ] Script execution (Python, shell) with sandboxing
- [ ] Execution timeout and resource limits
- [ ] Output capture and streaming back to controller
- [ ] Execution history and audit logging
- [ ] Rollback/cleanup of executed artifacts

### 15. Cell / Mobile Access
- **Status**: Planned
- **Description**: Extend capture capabilities to mobile platforms.

#### Planned Components:
**Mobile Agent (`mobile/agent.py`)** — to be created:
- [ ] Android agent with accessibility service integration
- [ ] iOS agent with profile-based deployment
- [ ] Battery-optimized capture scheduling
- [ ] Mobile-specific data types (SMS, calls, location)
- [ ] Secure communication over cellular networks

**Mobile Dashboard (`mobile/dashboard.py`)** — to be created:
- [ ] Mobile-responsive dashboard views
- [ ] Push notification integration for alerts
- [ ] Mobile-specific configuration profiles
- [ ] Device management and enrollment

### 16. Obfuscation Techniques
- **Status**: Planned
- **Description**: Code and network obfuscation to make analysis more difficult.

#### Planned Components:
**Code Obfuscation (`obfuscation/code.py`)** — to be created:
- [ ] String encryption with runtime decryption
- [ ] Control flow flattening
- [ ] Variable and function name mangling
- [ ] Dead code insertion
- [ ] Build-time obfuscation pipeline

**Network Obfuscation (`obfuscation/network.py`)** — to be created:
- [ ] Protocol tunneling (data over DNS, HTTPS, etc.)
- [ ] Traffic shaping to match normal browsing patterns
- [ ] Domain fronting for C2 communication
- [ ] Adaptive encryption with key rotation

### 17. Anti-Forensic Measures
- **Status**: Planned
- **Description**: Measures to resist forensic analysis of the host system.

#### Planned Components:
**Evidence Management (`anti_forensic/evidence.py`)** — to be created:
- [ ] Secure file deletion with overwrite passes
- [ ] Log cleanup for application and system logs
- [ ] Temporary file management with automatic shredding
- [ ] Disk artifact minimization

**Detection Evasion (`anti_forensic/evasion.py`)** — to be created:
- [ ] Memory-only operation mode (no disk writes)
- [ ] Anti-debugging detection and response
- [ ] Sandbox/VM detection
- [ ] File system timestamp normalization

### 18. Advanced Persistent Threat (APT) Capabilities
- **Status**: Planned
- **Description**: Long-term persistent access with multiple fallback mechanisms.

#### Planned Components:
**Persistence Mechanisms (`apt/persistence.py`)** — to be created:
- [ ] Multiple persistence vectors with priority failover
- [ ] Scheduled task and service-based persistence
- [ ] Registry/plist-based startup entries
- [ ] Watchdog process for self-healing
- [ ] Persistence health monitoring and repair

**Lateral Movement (`apt/movement.py`)** — to be created:
- [ ] Network discovery and host enumeration
- [ ] Credential harvesting from memory and storage
- [ ] Agent propagation to discovered hosts
- [ ] Network topology mapping
- [ ] Movement audit trail

### 19. Rootkit Integration
- **Status**: Planned
- **Description**: Kernel-level integration for deep system access and hiding.

#### Planned Components:
**Kernel Module (`rootkit/module.py`)** — to be created:
- [ ] Loadable kernel module for Linux
- [ ] Windows kernel driver
- [ ] macOS kext/system extension
- [ ] Process and file hiding at kernel level
- [ ] Network connection hiding

**Management Interface (`rootkit/management.py`)** — to be created:
- [ ] User-space control interface
- [ ] Module loading and unloading
- [ ] Configuration updates without reload
- [ ] Health monitoring and self-repair
- [ ] Safe uninstallation procedure

### 20. Exfiltration Techniques
- **Status**: Planned
- **Description**: Advanced data exfiltration methods for restricted environments.

#### Planned Components:
**Covert Channels (`exfiltration/covert.py`)** — to be created:
- [ ] DNS tunneling with adaptive encoding
- [ ] HTTPS covert channels (data in headers, cookies)
- [ ] ICMP tunneling for network-restricted environments
- [ ] Cloud storage API exfiltration (S3, GCS, Azure Blob)
- [ ] Email-based exfiltration with attachment encoding

**Transfer Management (`exfiltration/transfer.py`)** — to be created:
- [ ] Adaptive bandwidth utilization (stay under detection thresholds)
- [ ] Chunked transfer with error correction
- [ ] Transfer scheduling based on network patterns
- [ ] Automatic protocol fallback chain
- [ ] Transfer integrity verification

---

## Implementation Notes

### Architecture Principles
- **Cross-platform first**: Every feature must work on macOS, Linux, and Windows (with graceful degradation where a platform lacks a capability)
- **Stealth-aware**: All new modules must respect the active stealth level — suppress output, use innocuous names, throttle when detection awareness signals threats
- **Plugin-compatible**: New capture/transport/intelligence modules should use the existing `@register_capture`, `@register_transport`, `@register_middleware` decorators
- **Fleet-ready**: All new capabilities should be triggerable via fleet commands from the controller

### Testing Requirements
- Each new feature must include comprehensive unit tests
- Integration tests for cross-module interactions
- Stealth-mode tests verifying no identifiable artifacts leak

### Priority Order for Implementation
1. **Credential Harvesting** (#21) — immediate, highest intelligence value
2. **Browser Data Extraction** (#22) — pairs with credential harvesting
3. **Covert C2 Channel** (#24) — enables operations in restricted networks
4. **Remote Execution** (#14) — essential fleet capability
5. **Keystroke Intelligence** (#23) — transforms data quality
6. **Auto-Updater** (#25) — enables persistent evolution
7. **APT Persistence** (#18) — long-term access assurance
8. **Exfiltration** (#20) — advanced data egress
9. **Network Recon** (#26) — environment mapping
10. **Natural Language Search** (#10) — dashboard enhancement
11. **Geofencing** (#27) — supplementary intelligence

### Retired Features (Rationale)
- **#15 Cell/Mobile Access**: Requires Android (Kotlin/Java) and iOS (Swift) native development with platform SDKs, accessibility services, and app store distribution. Fundamentally incompatible with a Python-based architecture. A separate project would be needed.
- **#16 Obfuscation Techniques**: String encryption, memory cloaking, and network obfuscation are now part of Stealth Mode v2 (11 subsystems). Build-time Python minification is available via `python-minifier` if needed.
- **#17 Anti-Forensic Measures**: Memory-only operations, anti-debugging, VM/sandbox detection, timestamp management, and secure deletion are all implemented in Stealth Mode (memory_cloak, detection_awareness, fs_cloak, self_destruct).
- **#19 Rootkit Integration**: Requires loadable kernel modules (C/Rust), kernel driver signing, and platform-specific kernel APIs. Cannot be implemented in Python. The user-space stealth system provides equivalent hiding at the application level.
