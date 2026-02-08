# Future Roadmap: Next-Gen Advanced Features

Generated: 2026-02-08
Scope: 10 deeply technical features beyond the existing 18-feature checklist.
Focus: Software engineering patterns, systems design, and research-grade capabilities.

> These features are independent of `ADVANCED_FEATURES_CHECKLIST.md` and represent the
> next evolution of the project after the core 18 are complete.

---

## Feature 1: Event-Driven Rule Engine with Custom DSL

**Concept:** A configurable trigger-action system (think mini IFTTT) that reacts to
capture events in real time. Instead of capturing everything uniformly, rules let users
define **when** and **what** to do dynamically.

**Why it matters:** Transforms the project from a passive recorder into an intelligent,
reactive system. Demonstrates compiler/interpreter fundamentals (lexing, parsing, AST evaluation)
in a practical context.

### Example Rules (YAML DSL)
```yaml
rules:
  - name: "screenshot-on-keyword"
    trigger:
      event: keystroke
      condition: "buffer_contains('confidential')"
    action:
      type: take_screenshot
      delay_ms: 500

  - name: "boost-on-browser"
    trigger:
      event: window_change
      condition: "window_title matches '.*Chrome.*|.*Firefox.*'"
    action:
      type: set_capture_interval
      value: 5   # seconds (faster)

  - name: "pause-on-lock"
    trigger:
      event: window_change
      condition: "window_title matches '.*Lock Screen.*'"
    action:
      type: pause_capture
      modules: ["keyboard", "mouse"]

  - name: "alert-on-idle"
    trigger:
      event: idle_detected
      condition: "idle_seconds > 300"
    action:
      type: notify
      channel: telegram
      message: "User idle for {idle_seconds}s"
```

### Architecture
```
Capture Events ──> Event Bus (pub/sub) ──> Rule Engine
                                              │
                                    ┌─────────┴─────────┐
                                    │   For each rule:   │
                                    │  1. Parse trigger   │
                                    │  2. Eval condition  │
                                    │  3. Exec action     │
                                    └─────────────────────┘
```

### Core Components
| Component | File | Purpose |
|-----------|------|---------|
| Event Bus | `engine/event_bus.py` | Async pub/sub with topic routing |
| Rule Parser | `engine/rule_parser.py` | YAML → Rule AST (conditions + actions) |
| Condition Evaluator | `engine/evaluator.py` | Safe expression evaluator (no `eval()`) |
| Action Dispatcher | `engine/actions.py` | Maps action types to capture/transport/notify methods |
| Rule Registry | `engine/registry.py` | Load, validate, hot-reload rules |

### Key Design Decisions
- **Safe expression evaluation** using AST walking (never raw `eval`/`exec`)
- **Hot-reload**: Rules can be updated without restarting (file-watch + re-parse)
- **Debouncing**: Configurable cooldown per rule to prevent action floods
- **Priority ordering**: Rules evaluated in priority order, first-match or all-match modes
- **Audit trail**: Every rule trigger logged with timestamp + context

### CS Concepts Demonstrated
- Domain-Specific Language (DSL) design
- Abstract Syntax Tree (AST) construction and evaluation
- Publisher/Subscriber (pub/sub) event architecture
- Interpreter pattern

---

## Feature 2: Keystroke Biometrics & Typing Dynamics Engine

**Concept:** Capture the **timing** of keystrokes (not just which keys) to build a unique
behavioral fingerprint. Dwell time (how long a key is held) and flight time (gap between
consecutive keys) create a biometric profile as unique as a fingerprint.

**Why it matters:** This is active security research territory. Keystroke dynamics are
used in continuous authentication systems, insider threat detection, and fraud prevention.
Adds genuine research credibility to the project.

### Metrics Captured
| Metric | Definition | Unit |
|--------|-----------|------|
| Dwell Time | Duration key is held (key_down → key_up) | milliseconds |
| Flight Time | Gap between releasing key N and pressing key N+1 | milliseconds |
| Digraph Latency | Time between pressing two specific key pairs (e.g., "th", "he", "in") | milliseconds |
| Trigraph Latency | Same for three-character sequences | milliseconds |
| Pressure Variance | Rhythm consistency (stddev of flight times) | milliseconds |
| Error Rate | Backspace frequency per 100 characters | ratio |
| WPM Burst Profile | WPM measured in 10-second micro-windows | words/min |

### Biometric Profile Structure
```json
{
  "profile_id": "usr_20260208_a3f2",
  "created_at": "2026-02-08T14:30:00Z",
  "sample_size": 15000,
  "avg_dwell_ms": 89.3,
  "avg_flight_ms": 132.7,
  "digraph_model": {
    "th": {"mean": 98.2, "std": 12.4},
    "he": {"mean": 105.1, "std": 15.8},
    "in": {"mean": 112.6, "std": 18.2}
  },
  "rhythm_signature": [0.82, 0.91, 0.78, 0.85],
  "fatigue_curve": {
    "0-15min": 72.1,
    "15-30min": 68.4,
    "30-60min": 61.2,
    "60min+": 55.8
  }
}
```

### Analysis Capabilities
- **User verification**: Compare live typing against stored profile (Euclidean distance / Mahalanobis distance)
- **Fatigue detection**: Track WPM degradation and error rate increase over session duration
- **Imposter detection**: Flag when typing pattern deviates beyond threshold (different person at keyboard)
- **Emotional state inference**: Faster/erratic typing may correlate with stress (research context)

### Architecture
```
keyboard_capture.py
   │ (key_down timestamp, key_up timestamp)
   ▼
BiometricsCollector ──> raw timing pairs
   │
   ▼
BiometricsAnalyzer
   ├── compute_dwell_times()
   ├── compute_flight_times()
   ├── build_digraph_model()
   ├── compute_fatigue_curve()
   └── generate_profile()
           │
           ▼
     SQLite (profiles table)
```

### Files to Create
```
biometrics/
  __init__.py
  collector.py     — BiometricsCollector: captures key_down/key_up timing pairs
  analyzer.py      — BiometricsAnalyzer: statistical analysis and profile generation
  matcher.py       — ProfileMatcher: compare live input against stored profiles
  models.py        — Data classes for profiles, digraphs, metrics
```

### CS Concepts Demonstrated
- Statistical modeling (Gaussian distributions, z-scores, Mahalanobis distance)
- Behavioral biometrics (active research field)
- Time-series signal processing
- Pattern recognition without ML libraries (pure statistics)

---

## Feature 3: Composable Middleware Pipeline Architecture

**Concept:** A pluggable filter chain that sits between capture and storage. Every piece
of captured data passes through an ordered sequence of middleware functions that can
transform, enrich, filter, or route data — similar to Express.js middleware or Django middleware.

**Why it matters:** Decouples data transformation from capture logic. Makes the system
infinitely extensible without modifying core modules. Demonstrates a fundamental
enterprise integration pattern.

### Pipeline Flow
```
  Capture Module
       │
       ▼
┌──────────────┐
│  Middleware 1 │  Timestamp Enricher (adds high-res timestamps, timezone)
└──────┬───────┘
       ▼
┌──────────────┐
│  Middleware 2 │  Context Annotator (attaches active window, process info)
└──────┬───────┘
       ▼
┌──────────────┐
│  Middleware 3 │  Deduplicator (drops repeated clipboard entries)
└──────┬───────┘
       ▼
┌──────────────┐
│  Middleware 4 │  Rate Limiter (throttles high-frequency events)
└──────┬───────┘
       ▼
┌──────────────┐
│  Middleware 5 │  Router (sends screenshots to S3, keystrokes to SQLite)
└──────┬───────┘
       ▼
    Storage
```

### Middleware Interface
```python
class BaseMiddleware(ABC):
    """All middleware must implement this interface."""

    @abstractmethod
    def process(self, event: CaptureEvent, context: PipelineContext) -> Optional[CaptureEvent]:
        """
        Process a capture event.

        Return the event (possibly modified) to pass it downstream.
        Return None to drop the event (filter it out).
        Raise MiddlewareError to halt the pipeline.
        """
        ...

    @property
    def name(self) -> str: ...

    @property
    def order(self) -> int: ...  # Lower = earlier in pipeline
```

### Built-in Middleware
| Name | Order | Purpose |
|------|-------|---------|
| `TimestampEnricher` | 10 | Adds microsecond-precision timestamps + timezone info |
| `ContextAnnotator` | 20 | Attaches active window title, PID, process name |
| `Deduplicator` | 30 | Drops duplicate clipboard/window events within configurable window |
| `ContentTruncator` | 40 | Enforces max content length per event type |
| `RateLimiter` | 50 | Throttles events exceeding configured events/second |
| `ConditionalRouter` | 60 | Routes events to different storage backends by type/content |
| `MetricsEmitter` | 99 | Emits pipeline throughput metrics (events/sec, drop rate) |

### Configuration
```yaml
pipeline:
  enabled: true
  middleware:
    - name: timestamp_enricher
      enabled: true
    - name: context_annotator
      enabled: true
    - name: deduplicator
      enabled: true
      config:
        window_seconds: 5
    - name: rate_limiter
      enabled: true
      config:
        max_events_per_second: 50
    - name: conditional_router
      enabled: false
      config:
        routes:
          screenshot: "s3"
          keystroke: "sqlite"
```

### Files to Create
```
pipeline/
  __init__.py
  core.py              — Pipeline executor, middleware chain runner
  context.py           — PipelineContext (shared state across middleware)
  base_middleware.py    — BaseMiddleware ABC
  registry.py          — @register_middleware decorator + auto-discovery
  middleware/
    __init__.py
    timestamp_enricher.py
    context_annotator.py
    deduplicator.py
    content_truncator.py
    rate_limiter.py
    conditional_router.py
    metrics_emitter.py
```

### CS Concepts Demonstrated
- Chain of Responsibility pattern
- Middleware / pipeline architecture (used in web frameworks, ETL, message brokers)
- Decorator-based plugin registration (extends existing project pattern)
- Event-driven data transformation

---

## Feature 4: Cross-Platform Service / Daemon Mode

**Concept:** Run the application as a proper OS-level service that starts on boot,
restarts on crash, and integrates with the platform's service manager (systemd on Linux,
launchd on macOS, Windows Service on Windows).

**Why it matters:** Demonstrates deep OS integration and production deployment patterns.
Most monitoring tools need to survive reboots and user logouts — this is what separates
a script from a real system service.

### Platform Support Matrix
| Platform | Service Manager | Integration Method |
|----------|----------------|-------------------|
| Linux | systemd | `.service` unit file + `sd_notify` protocol |
| macOS | launchd | `.plist` file in `~/Library/LaunchAgents/` |
| Windows | Windows Service (SCM) | `pywin32` / `win32serviceutil` |

### Features
- **Auto-install**: `python -m main service install` — generates and installs service config
- **Auto-uninstall**: `python -m main service uninstall` — cleanly removes service
- **Status check**: `python -m main service status` — running / stopped / failed
- **Crash recovery**: Automatic restart with configurable delay (3 restarts max, then stop)
- **Boot persistence**: Survives reboots without manual intervention
- **Privilege management**: Runs as current user (not root) — captures user-level input
- **Logging integration**: Service logs visible via `journalctl` / `Console.app` / Event Viewer

### systemd Unit File (Generated)
```ini
[Unit]
Description=AdvanceKeyLogger Monitoring Service
After=network.target graphical-session.target
Wants=graphical-session.target

[Service]
Type=notify
ExecStart=/usr/bin/python3 -m main --config %h/.config/advancekeylogger/config.yaml
Restart=on-failure
RestartSec=10
StartLimitBurst=3
StartLimitIntervalSec=60
Environment=DISPLAY=:0

[Install]
WantedBy=default.target
```

### launchd plist (Generated)
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.advancekeylogger.agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>-m</string>
        <string>main</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
</dict>
</plist>
```

### Files to Create
```
service/
  __init__.py
  manager.py          — ServiceManager: install/uninstall/status (cross-platform)
  linux_systemd.py    — systemd unit generation, systemctl wrappers
  macos_launchd.py    — plist generation, launchctl wrappers
  windows_service.py  — pywin32 Service class, SCM registration
  templates/
    systemd.service.j2
    launchd.plist.j2
```

### CS Concepts Demonstrated
- OS service lifecycle management
- Platform abstraction layer (Strategy pattern)
- Process supervision and crash recovery
- IPC notification protocols (sd_notify)

---

## Feature 5: Application Usage Profiler & Productivity Scoring

**Concept:** A new capture module that goes beyond window titles to build a comprehensive
profile of application usage. Tracks foreground time per app, categorizes apps (work vs
personal vs communication), computes focus scores, and detects context-switching patterns.

**Why it matters:** Transforms raw window-switch data into actionable productivity intelligence.
This is what tools like RescueTime and ActivityWatch do. Demonstrates data aggregation,
time-series bucketing, and scoring algorithms.

### Metrics
| Metric | Description |
|--------|-------------|
| App Foreground Time | Total seconds each application was in focus, per day |
| Category Breakdown | Time split across Work / Communication / Entertainment / Other |
| Focus Sessions | Uninterrupted periods (>10 min) in a single app |
| Context Switches/Hour | How often the user changes the active application |
| Productive Time Ratio | (Work category time) / (Total active time) |
| Deep Work Score | Longest focus session * frequency of long sessions |
| Top 10 Apps | Ranked by total foreground time |
| Idle Gaps | Periods with no input between active sessions |
| Peak Productivity Window | Hour(s) of day with highest productive time ratio |

### Application Categorization
```yaml
app_categories:
  work:
    - "Visual Studio Code"
    - "IntelliJ"
    - "Terminal"
    - "Xcode"
    - "Figma"
  communication:
    - "Slack"
    - "Discord"
    - "Microsoft Teams"
    - "Zoom"
    - "Mail"
  browser:
    - "Google Chrome"
    - "Firefox"
    - "Safari"
  entertainment:
    - "Spotify"
    - "YouTube"    # detected via browser title
    - "Netflix"
  uncategorized: "*"   # everything else
```

### Scoring Algorithm
```
Deep Work Score = sum(
    session_duration_minutes * weight
    for session in focus_sessions
    where session_duration > 10 minutes
)

Weights:
  10-30 min  → 1.0x
  30-60 min  → 1.5x
  60-120 min → 2.0x
  120+ min   → 3.0x  (rare, highly valuable)

Productivity Score (0-100) = (
    (productive_minutes / total_active_minutes) * 50  +
    (deep_work_score / max_possible_score) * 30       +
    (1 - context_switches_per_hour / 60) * 20
)
```

### Dashboard Integration
- Daily/weekly productivity score trend chart
- App usage breakdown pie chart
- Focus sessions timeline (Gantt-style visualization)
- "Your most productive hours" insight card

### Files to Create
```
profiler/
  __init__.py
  tracker.py          — AppUsageTracker: foreground monitoring, session detection
  categorizer.py      — AppCategorizer: rule-based app classification
  scorer.py           — ProductivityScorer: compute focus sessions, scores
  models.py           — AppSession, FocusSession, DailyProfile dataclasses
```

### CS Concepts Demonstrated
- Time-series data bucketing and aggregation
- Rule-based classification systems
- Scoring and ranking algorithms
- Session detection (gap-based segmentation)

---

## Feature 6: End-to-End Encrypted Transport with Asymmetric Key Exchange

**Concept:** Replace the current symmetric-key-only encryption with a full cryptographic
protocol that uses asymmetric keys for initial handshake and symmetric keys for bulk data.
Implements a simplified TLS-like protocol for data transport.

**Why it matters:** The current AES-256-CBC with a shared key requires the key to be
in the config file (a security weakness). Asymmetric crypto eliminates shared secrets.
Demonstrates real-world cryptographic protocol design.

### Protocol Design
```
PHASE 1: Key Exchange (one-time setup)
─────────────────────────────────────
  Agent                          Collector Server
    │                                  │
    │  ──── Agent Public Key ────────> │
    │                                  │
    │  <── Server Public Key ───────── │
    │      + Signed Challenge          │
    │                                  │
    │  ──── Signed Response ─────────> │
    │                                  │
    │      (Both derive shared         │
    │       session key via ECDH)      │
    │                                  │

PHASE 2: Data Transport (every send)
─────────────────────────────────────
  Agent                          Collector Server
    │                                  │
    │  1. Generate ephemeral AES key   │
    │  2. Encrypt payload with AES key │
    │  3. Encrypt AES key with server  │
    │     public key (RSA/ECDH)        │
    │  4. Sign the bundle with agent   │
    │     private key                  │
    │                                  │
    │  ──── Encrypted Bundle ────────> │
    │       + Encrypted AES Key        │
    │       + Signature                │
    │                                  │
    │  <── ACK + Sequence Number ───── │
    │                                  │
```

### Crypto Primitives
| Component | Algorithm | Purpose |
|-----------|-----------|---------|
| Key Exchange | ECDH (Curve25519) | Derive shared secret without transmitting it |
| Bulk Encryption | AES-256-GCM | Authenticated encryption (confidentiality + integrity) |
| Signing | Ed25519 | Verify agent identity, prevent tampering |
| Key Derivation | HKDF-SHA256 | Derive session keys from ECDH shared secret |
| Envelope | Hybrid encryption | RSA/ECDH wraps AES key, AES encrypts payload |

### Key Management
- **Agent keypair**: Generated on first run, stored in `~/.advancekeylogger/keys/`
- **Server keypair**: Generated on server setup, public key distributed to agents
- **Key rotation**: New session keys every N hours or N megabytes (configurable)
- **Key pinning**: Agent remembers server's public key, warns on change (TOFU model)
- **Revocation**: Server maintains list of revoked agent keys

### Configuration
```yaml
encryption:
  mode: "e2e"              # "symmetric" (current) or "e2e" (new)
  e2e:
    curve: "curve25519"
    signing: "ed25519"
    bulk_cipher: "aes-256-gcm"
    key_rotation_hours: 24
    key_store_path: "~/.advancekeylogger/keys/"
    server_public_key: ""  # base64-encoded, set during enrollment
    pin_server_key: true
```

### Files to Create
```
crypto/
  __init__.py
  keypair.py           — KeyPairManager: generate, store, load ECDH + Ed25519 keys
  handshake.py         — HandshakeProtocol: ECDH key exchange, challenge-response
  envelope.py          — HybridEnvelope: encrypt/decrypt with hybrid scheme
  signer.py            — MessageSigner: Ed25519 sign/verify
  key_store.py         — Persistent key storage with file permissions
  protocol.py          — E2EProtocol: orchestrates handshake + envelope + signing
```

### CS Concepts Demonstrated
- Public-key cryptography (ECDH, RSA)
- Hybrid encryption (asymmetric + symmetric)
- Digital signatures and authentication
- Key exchange protocols (Diffie-Hellman)
- Forward secrecy
- Trust-On-First-Use (TOFU) model

---

## Feature 7: Distributed Fleet Management (Agent-Controller Architecture)

**Concept:** A central controller server that manages multiple keylogger agent instances
across different machines. Agents enroll with the controller, receive configuration
updates, and report captured data back. The controller provides a unified dashboard
for all agents.

**Why it matters:** Moves from single-machine tool to distributed system. Demonstrates
agent enrollment, heartbeat protocols, remote configuration management, and multi-tenant
data aggregation — patterns used in every enterprise monitoring system (Datadog, Splunk, etc.).

### Architecture
```
┌─────────────────────────────────────────────────┐
│              Controller Server                   │
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌───────────────┐ │
│  │ Agent    │  │ Config   │  │ Unified       │ │
│  │ Registry │  │ Manager  │  │ Dashboard     │ │
│  └────┬─────┘  └────┬─────┘  └───────────────┘ │
│       │              │                           │
│  ┌────┴──────────────┴────┐                     │
│  │   REST + WebSocket API  │                     │
│  └────────────┬────────────┘                     │
└───────────────┼──────────────────────────────────┘
                │
       ┌────────┼────────┐
       │        │        │
  ┌────▼──┐ ┌──▼────┐ ┌─▼─────┐
  │Agent 1│ │Agent 2│ │Agent 3│
  │ (Mac) │ │(Linux)│ │ (Win) │
  └───────┘ └───────┘ └───────┘
```

### Agent Enrollment Flow
```
1. Agent starts with controller URL in config
2. Agent generates keypair (Feature 6)
3. Agent sends enrollment request:
   POST /api/agents/enroll
   { hostname, os, platform, public_key, agent_version }
4. Controller returns:
   { agent_id, config, server_public_key, enrollment_token }
5. Agent stores credentials, begins normal operation
6. Agent sends heartbeat every 30s:
   POST /api/agents/{id}/heartbeat
   { status, uptime, capture_counts, storage_usage }
```

### Controller API
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/agents/enroll` | POST | New agent enrollment |
| `/api/agents` | GET | List all agents with status |
| `/api/agents/{id}` | GET | Agent detail (status, config, last seen) |
| `/api/agents/{id}/heartbeat` | POST | Agent heartbeat update |
| `/api/agents/{id}/config` | GET/PUT | Get or push config to specific agent |
| `/api/agents/{id}/data` | POST | Agent uploads captured data bundle |
| `/api/agents/{id}/command` | POST | Send command to agent (start/stop/restart) |
| `/api/fleet/status` | GET | Aggregated fleet status |
| `/api/fleet/broadcast` | POST | Push config/command to all agents |

### Agent States
```
ENROLLED ──> ONLINE ──> CAPTURING
                │            │
                ▼            ▼
             IDLE      PAUSED
                │            │
                ▼            ▼
            OFFLINE    ERROR
                │
                ▼
           DECOMMISSIONED
```

### Files to Create
```
fleet/
  __init__.py
  controller/
    __init__.py
    app.py             — FastAPI controller server
    agent_registry.py  — Agent enrollment, tracking, decommission
    config_manager.py  — Per-agent config storage and push
    data_receiver.py   — Receive and store data from agents
    command_queue.py   — Pending commands per agent
  agent/
    __init__.py
    enrollment.py      — Enrollment handshake
    heartbeat.py       — Periodic heartbeat sender
    config_sync.py     — Pull and apply config changes from controller
    data_uploader.py   — Bundle and upload captures to controller
    command_handler.py — Receive and execute commands from controller
```

### CS Concepts Demonstrated
- Distributed systems design (agent-controller topology)
- Service enrollment and discovery
- Heartbeat / health-check protocols
- Remote configuration management
- Multi-tenant data aggregation
- Command and control (C2) architecture (educational context)

---

## Feature 8: Adaptive Capture Intelligence

**Concept:** The system dynamically adjusts capture frequency and module activity based
on real-time context — user activity level, time of day, resource usage, and content
sensitivity. Busy periods get more capture; idle periods get less. Resource pressure
triggers automatic throttling.

**Why it matters:** Static capture intervals waste resources during idle time and miss
detail during active periods. Adaptive capture demonstrates control theory, feedback
loops, and resource-aware computing — patterns used in auto-scaling systems, network
congestion control, and adaptive bitrate streaming.

### Adaptive Signals
| Signal | Source | Effect |
|--------|--------|--------|
| Keystroke velocity | Keyboard capture | High KPM → decrease interval (capture more) |
| Idle detection | All input modules | No input >5min → increase interval, disable screenshots |
| Active window category | Window capture | "Work" app → normal; "Browser" → increase frequency |
| CPU usage | psutil | >70% → throttle all captures to prevent detection |
| Memory pressure | psutil | >80% → flush buffers, reduce ring buffer sizes |
| Disk space | Storage manager | <500MB → pause screenshots, compress aggressively |
| Time of day | System clock | Outside work hours → reduce to minimal capture |
| Error rate | Transport module | High failure rate → increase local buffer, reduce send attempts |

### Control Algorithm
```
                    ┌──────────────┐
  Signals ────────> │  Controller  │ ────────> Module Parameters
  (metrics)         │              │           (intervals, buffer sizes,
                    │  PID-like    │            enabled/disabled states)
                    │  feedback    │
                    │  loop        │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  Constraint  │
                    │  Checker     │
                    │  (min/max    │
                    │   bounds)    │
                    └──────────────┘

Capture Interval = BASE_INTERVAL * activity_factor * resource_factor * time_factor

Where:
  activity_factor ∈ [0.2, 3.0]   (busy = lower = more frequent)
  resource_factor ∈ [1.0, 10.0]  (pressure = higher = less frequent)
  time_factor     ∈ [0.5, 5.0]   (off-hours = higher = less frequent)
```

### Configuration
```yaml
adaptive:
  enabled: false
  mode: "balanced"         # "aggressive", "balanced", "conservative"
  base_interval_seconds: 30
  constraints:
    min_interval_seconds: 5
    max_interval_seconds: 300
    max_cpu_percent: 70
    max_memory_percent: 80
    min_free_disk_mb: 500
  time_policy:
    work_hours:
      start: "09:00"
      end: "18:00"
    off_hours_factor: 3.0  # 3x longer intervals outside work hours
  activity_thresholds:
    high_kpm: 200          # keystrokes/min → boost capture
    idle_seconds: 300      # 5 min no input → reduce capture
```

### Files to Create
```
adaptive/
  __init__.py
  controller.py        — AdaptiveController: main feedback loop
  signals.py           — Signal collectors (activity, resource, time)
  policy.py            — Policy engine: compute factors from signals
  constraints.py       — Constraint checker: enforce min/max bounds
```

### CS Concepts Demonstrated
- Control theory and feedback loops (PID-like control)
- Adaptive systems and auto-scaling patterns
- Resource-aware computing
- Multi-signal decision fusion

---

## Feature 9: Offline-First Sync Engine with Conflict Resolution

**Concept:** A robust sync engine that allows the agent to operate fully offline,
queuing all captured data locally with guaranteed ordering. When connectivity returns,
data is synchronized with the remote server using incremental sync with deduplication
and conflict resolution.

**Why it matters:** Real-world monitoring targets (laptops) frequently go offline.
Demonstrates distributed data consistency patterns used in CRDTs, mobile sync engines
(like CouchDB/PouchDB), and event sourcing systems.

### Sync Protocol
```
OFFLINE MODE:
  Capture → Local SQLite (with monotonic sequence numbers)
  Each record gets: (seq_id, timestamp, capture_type, data, sync_status)

SYNC TRIGGER:
  1. Connectivity check succeeds (periodic ping to server)
  2. Manual trigger via API/CLI

SYNC PROCESS:
  ┌─────────────────────────────────────────────┐
  │  1. Agent sends last_synced_seq to server    │
  │  2. Server responds with its last_received   │
  │  3. Agent computes delta (local - synced)    │
  │  4. Agent sends delta batch (ordered by seq) │
  │  5. Server acknowledges with new watermark   │
  │  6. Agent marks synced records               │
  │  7. Repeat until delta = 0                   │
  └─────────────────────────────────────────────┘
```

### Key Properties
| Property | Implementation |
|----------|---------------|
| **Exactly-once delivery** | Sequence numbers + server-side dedup by (agent_id, seq_id) |
| **Ordering guarantee** | Monotonic sequence IDs assigned at capture time |
| **Resumable sync** | Watermark-based — resume from last acknowledged seq |
| **Bandwidth efficiency** | Delta sync (only unsent records), GZIP compression |
| **Conflict resolution** | Last-write-wins with agent_id tiebreaker (configurable) |
| **Batch control** | Configurable batch size (default 500 records per request) |
| **Backpressure** | Server returns 429 if overwhelmed, agent backs off |

### Sync States Per Record
```
PENDING ──> QUEUED ──> SENDING ──> SYNCED
                          │
                          ▼
                       FAILED ──> QUEUED (retry)
                          │
                          ▼ (after max retries)
                      DEAD_LETTER
```

### Configuration
```yaml
sync:
  enabled: true
  mode: "auto"                  # "auto" (on connectivity) or "manual"
  connectivity_check_url: "https://example.com/health"
  connectivity_check_interval_seconds: 60
  batch_size: 500
  max_retries_per_record: 5
  compression: true
  conflict_resolution: "last-write-wins"   # or "agent-priority"
  dead_letter_retention_days: 30
```

### Files to Create
```
sync/
  __init__.py
  engine.py            — SyncEngine: orchestrates the sync protocol
  sequencer.py         — SequenceGenerator: monotonic, gap-free sequence IDs
  delta.py             — DeltaComputer: compute unsent records efficiently
  connectivity.py      — ConnectivityChecker: periodic ping, state tracking
  conflict.py          — ConflictResolver: configurable resolution strategies
  dead_letter.py       — DeadLetterQueue: store permanently failed records
```

### CS Concepts Demonstrated
- Offline-first / local-first architecture
- Watermark-based incremental synchronization
- Exactly-once delivery semantics
- Conflict resolution strategies (LWW, vector clocks)
- Dead letter queue pattern
- Backpressure and flow control

---

## Feature 10: Embedded Time-Series Store with Query Engine

**Concept:** Replace raw SQLite tables with a purpose-built embedded time-series storage
layer optimized for append-heavy, time-ordered capture data. Includes a lightweight
query DSL for filtering, aggregating, and downsampling data without pulling everything
into memory.

**Why it matters:** SQLite is a general-purpose database — it works but isn't optimized
for time-series access patterns (append-only writes, time-range reads, downsampling).
Building a specialized store demonstrates database internals, storage engine design,
and query optimization — concepts at the core of systems like InfluxDB, TimescaleDB,
and Prometheus.

### Storage Design
```
data/
  timeseries/
    2026/
      02/
        08/
          keystrokes.tsdb     ← binary segment file (one per day per type)
          mouse.tsdb
          window.tsdb
          clipboard.tsdb
          screenshots.tsdb
    manifest.json             ← segment index: date ranges, record counts, byte offsets
    wal.log                   ← write-ahead log for crash recovery
```

### Segment File Format
```
┌─────────────────────────────────────────────┐
│  Magic: "TSDB" (4 bytes)                    │
│  Version: 1 (2 bytes)                       │
│  Capture Type: "keystroke" (variable)       │
│  Start Timestamp: epoch_ns (8 bytes)        │
│  End Timestamp: epoch_ns (8 bytes)          │
│  Record Count: uint32 (4 bytes)             │
│  Compression: enum (1 byte)                 │
├─────────────────────────────────────────────┤
│  Record 1: [timestamp | length | data]      │
│  Record 2: [timestamp | length | data]      │
│  ...                                        │
│  Record N: [timestamp | length | data]      │
├─────────────────────────────────────────────┤
│  Offset Index: [every 100th record offset]  │
│  Footer checksum: CRC32 (4 bytes)           │
└─────────────────────────────────────────────┘
```

### Query DSL
```python
# Fluent query API
results = tsdb.query("keystroke") \
    .time_range("2026-02-08T09:00", "2026-02-08T17:00") \
    .where(window_title__contains="VSCode") \
    .downsample("5m", agg="count") \
    .limit(1000) \
    .execute()

# Returns: [(timestamp_bucket, count), ...]

# Aggregation queries
summary = tsdb.query("keystroke") \
    .time_range("2026-02-01", "2026-02-08") \
    .group_by("hour_of_day") \
    .aggregate("count") \
    .execute()

# Returns: {0: 120, 1: 45, ..., 23: 89}
```

### Key Features
| Feature | Purpose |
|---------|---------|
| **Append-only segments** | Optimized for write-heavy workload (no random updates) |
| **Time-partitioned files** | One file per day per type — fast range scans, easy cleanup |
| **Write-Ahead Log (WAL)** | Crash recovery — replay uncommitted writes on startup |
| **Sparse offset index** | Binary search within segments for fast time-range lookups |
| **Built-in downsampling** | Reduce resolution for older data (raw → 1min → 1hour → 1day) |
| **Automatic compaction** | Merge small segments, apply retention policy |
| **Fluent query API** | Chainable Python API (no SQL dependency) |
| **CRC checksums** | Detect corruption in segment files |

### Retention Policy
```yaml
timeseries:
  enabled: true
  data_dir: "data/timeseries/"
  retention:
    raw: 7d           # full resolution: 7 days
    downsampled_1m: 30d   # 1-minute buckets: 30 days
    downsampled_1h: 365d  # 1-hour buckets: 1 year
  compaction:
    enabled: true
    schedule: "daily"      # run compaction once per day
    min_segment_size_kb: 100
  wal:
    enabled: true
    max_size_mb: 10
    sync_interval_ms: 1000
```

### Files to Create
```
tsdb/
  __init__.py
  store.py             — TimeSeriesStore: top-level API (open, query, close)
  segment.py           — SegmentFile: read/write binary segment files
  wal.py               — WriteAheadLog: append, replay, truncate
  index.py             — SegmentIndex: sparse offset index + manifest
  query.py             — QueryBuilder: fluent API, filter/aggregate/downsample
  compactor.py         — Compactor: merge segments, apply retention
  models.py            — TimeSeriesRecord, SegmentHeader, QueryResult
```

### CS Concepts Demonstrated
- Database storage engine design (LSM-tree inspired)
- Write-Ahead Logging (WAL) for durability
- Binary file format design with headers and checksums
- Time-series data modeling and downsampling
- Query engine with predicate pushdown
- Fluent API / builder pattern for queries
- Data retention and compaction strategies

---

## Implementation Priority Matrix

| # | Feature | Complexity | Impact | Depends On |
|---|---------|-----------|--------|------------|
| 1 | Event-Driven Rule Engine | HIGH | HIGH | Core pipeline |
| 2 | Keystroke Biometrics | MEDIUM | HIGH | Keyboard capture timing |
| 3 | Middleware Pipeline | MEDIUM | HIGH | None (enhances existing) |
| 4 | Cross-Platform Service Mode | MEDIUM | MEDIUM | None |
| 5 | App Usage Profiler | MEDIUM | HIGH | Window capture |
| 6 | E2E Encrypted Transport | HIGH | MEDIUM | Existing crypto module |
| 7 | Fleet Management | VERY HIGH | VERY HIGH | Feature 6, Dashboard |
| 8 | Adaptive Capture | HIGH | MEDIUM | Feature 5 signals |
| 9 | Offline-First Sync | HIGH | MEDIUM | Feature 7 (controller) |
| 10 | Time-Series Store | VERY HIGH | HIGH | None (replaces SQLite) |

### Recommended Implementation Order
```
Phase A (Foundation):     3 (Pipeline) → 2 (Biometrics) → 5 (Profiler)
Phase B (Intelligence):   1 (Rule Engine) → 8 (Adaptive Capture)
Phase C (Infrastructure): 4 (Service Mode) → 6 (E2E Crypto)
Phase D (Scale):          7 (Fleet Mgmt) → 9 (Sync Engine)
Phase E (Storage):        10 (Time-Series Store)
```

---

## Summary Table

| # | Feature | One-Line Description | Key CS Concept |
|---|---------|---------------------|----------------|
| 1 | Rule Engine | Configurable trigger-action system with custom DSL | Interpreter pattern, Event-driven architecture |
| 2 | Keystroke Biometrics | Typing dynamics analysis for user fingerprinting | Behavioral biometrics, Statistical modeling |
| 3 | Middleware Pipeline | Composable filter chain between capture and storage | Chain of Responsibility, Middleware pattern |
| 4 | Service Mode | OS-native service integration (systemd/launchd/SCM) | OS service lifecycle, Platform abstraction |
| 5 | App Profiler | Application usage tracking with productivity scoring | Time-series aggregation, Scoring algorithms |
| 6 | E2E Encryption | Asymmetric key exchange + hybrid encryption protocol | Public-key crypto, Forward secrecy |
| 7 | Fleet Management | Multi-agent controller with enrollment and remote config | Distributed systems, Agent-controller topology |
| 8 | Adaptive Capture | Dynamic capture frequency based on context signals | Control theory, Feedback loops |
| 9 | Offline Sync | Offline-first with watermark-based incremental sync | Distributed consistency, Exactly-once delivery |
| 10 | Time-Series Store | Embedded time-series database with query DSL | Storage engine design, WAL, Query optimization |
