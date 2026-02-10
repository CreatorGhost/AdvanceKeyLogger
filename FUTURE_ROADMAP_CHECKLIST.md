# Future Roadmap Checklist

Track implementation status for FUTURE_ROADMAP.md features (20 total).

## Status Overview

- [x] 1. Event-Driven Rule Engine with Custom DSL
- [x] 2. Keystroke Biometrics & Typing Dynamics Engine
- [x] 3. Cross-Platform Service / Daemon Mode
- [x] 4. Application Usage Profiler & Productivity Scoring
- [x] 5. End-to-End Encrypted Transport with Asymmetric Key Exchange
- [x] 6. Distributed Fleet Management (Agent-Controller Architecture)
- [x] 7. Adaptive Capture Intelligence
- [ ] 8. Offline-First Sync Engine with Conflict Resolution
- [ ] 9. Session Recording & Visual Replay
- [ ] 10. Natural Language Search
- [x] 11. Configuration Profiles & Hot-Switching
- [x] 12. Data Anonymization Pipeline
- [ ] 13. Stealth Mode
- [ ] 14. Remote File Upload and Execution
- [ ] 15. Cell / Mobile Access
- [ ] 16. Obfuscation Techniques
- [ ] 17. Anti-Forensic Measures
- [ ] 18. Advanced Persistent Threat (APT) Capabilities
- [ ] 19. Rootkit Integration
- [ ] 20. Exfiltration Techniques
- [x] **Bonus**: Plugin Architecture (extensibility system)

---

## Completed Features (1-7, 11-12, Plugin System)

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

## Planned Features (8-10, 13-20) — Not Yet Implemented

> **Note**: The following features are planned for future development. None of the
> listed files or directories exist yet. Each section describes the intended design
> and the files that will need to be created.

### 8. Offline-First Sync Engine with Conflict Resolution
- **Status**: Planned
- **Description**: Operate fully offline and sync captured data when connectivity is available.

#### Planned Components:
**Sync Engine (`sync/offline_sync.py`)** — to be created:
- [ ] Local-first data storage with SQLite WAL mode
- [ ] Delta-based change tracking and compression
- [ ] Priority-based sync queue (critical data first)
- [ ] Bandwidth-adaptive transfer protocols
- [ ] Resumable transfers with checkpointing

**Conflict Resolution (`sync/conflict_resolver.py`)** — to be created:
- [ ] Last-writer-wins with timestamp verification
- [ ] Merge strategy for overlapping capture windows
- [ ] Duplicate detection and deduplication
- [ ] Automatic conflict classification (safe vs. needs review)
- [ ] Rollback capability for failed sync operations

**Connectivity Monitor (`sync/connectivity.py`)** — to be created:
- [ ] Network availability detection
- [ ] Connection quality assessment (latency, bandwidth)
- [ ] Automatic sync triggering when connectivity restored
- [ ] Configurable sync schedules (e.g., only on WiFi)

### 9. Session Recording & Visual Replay
- **Status**: Planned
- **Description**: Record user sessions with screen capture and input events for later replay and analysis.

#### Planned Components:
**Recording Engine (`recording/session_capture.py`)** — to be created:
- [ ] Screen capture with configurable quality/frame rate
- [ ] Input event recording (keyboard, mouse) with timestamps
- [ ] Application-focused recording (only capture active window)
- [ ] Event-driven recording triggers (start/stop on conditions)
- [ ] Storage-aware compression and retention

**Replay System (`recording/replay.py`)** — to be created:
- [ ] Timeline-based playback with seeking
- [ ] Input event overlay on screen captures
- [ ] Annotation and bookmarking system
- [ ] Export to standard video formats
- [ ] Web-based replay viewer in dashboard

**Storage Backend (`recording/storage.py`)** — to be created:
- [ ] Chunked storage with per-session encryption
- [ ] Automatic cleanup based on retention policy
- [ ] Metadata indexing for fast session lookup
- [ ] Compression ratio monitoring and optimization

### 10. Natural Language Search
- **Status**: Planned
- **Description**: Search captured data using natural language queries.

#### Planned Components:
**Search Engine (`search/nlp_search.py`)** — to be created:
- [ ] Keyword extraction from captured text
- [ ] Fuzzy matching with typo tolerance
- [ ] Temporal query support ("last week", "yesterday at 3pm")
- [ ] Context-aware result ranking
- [ ] Regular expression support for power users

**Indexing System (`search/indexer.py`)** — to be created:
- [ ] Incremental full-text indexing with SQLite FTS5
- [ ] Cross-source indexing (keystrokes, clipboard, screenshots OCR)
- [ ] Automatic data classification and tagging
- [ ] Index optimization and compaction

**Search API (`search/api.py`)** — to be created:
- [ ] REST API endpoints for search queries
- [ ] Autocomplete with suggestion ranking
- [ ] Search history tracking
- [ ] Paginated results with highlighting
- [ ] Dashboard integration with search bar

### 13. Stealth Mode
- **Status**: Planned
- **Description**: Minimize the platform's observable footprint on the host system.

#### Planned Components:
**Stealth Core (`stealth/core.py`)** — to be created:
- [ ] Configurable process name (mimic legitimate software)
- [ ] Minimal file system footprint
- [ ] Low CPU/memory profile with adaptive throttling
- [ ] Startup integration mimicking system services
- [ ] Log suppression and cleanup

**Detection Avoidance (`stealth/detection.py`)** — to be created:
- [ ] Task manager / process list appearance management
- [ ] Network traffic pattern normalization
- [ ] File timestamp management
- [ ] Resource usage pattern randomization

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

## Additional Considerations

- **Payload Execution**: Develop a robust system for remote payload execution with audit logging and sandboxing.
- **Cross-Platform Coverage**: Ensure all new features work across Windows, macOS, and Linux where applicable.
- **Testing**: Each new feature should include comprehensive unit and integration tests.
- **Documentation**: Update API documentation and user guides with each feature release.
- **Security**: All new features must follow the existing security patterns (encryption, authentication, input validation).
