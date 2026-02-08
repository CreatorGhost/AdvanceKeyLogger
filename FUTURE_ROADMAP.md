# Future Roadmap: Next-Gen Advanced Features

Generated: 2026-02-08 | Updated: 2026-02-08
Scope: 20 deeply technical features beyond the existing 18-feature checklist.
Focus: Software engineering patterns, systems design, and research-grade capabilities.

> These features are independent of `ADVANCED_FEATURES_CHECKLIST.md` and represent the
> next evolution of the project after the core 18 are complete.

---

## Feature Assessment (Existing 10)

| # | Feature | Verdict | Star Impact | Notes |
|---|---------|---------|-------------|-------|
| 1 | Rule Engine + DSL | KEEP — flagship feature | HIGH | Demonstrates compiler fundamentals. Very few monitoring tools have this. Makes great README demo. |
| 2 | Keystroke Biometrics | KEEP — unique differentiator | VERY HIGH | Almost no open-source project does this well. Research papers cite this area. Will attract security researchers. |
| 3 | Middleware Pipeline | KEEP — architectural backbone | MEDIUM | Essential for extensibility but less visible to users. Implement early as other features depend on it. |
| 4 | Service Mode | KEEP — practical necessity | MEDIUM | Essential for real usage but won't drive stars on its own. Low-glamour, high-utility. |
| 5 | App Profiler | KEEP — viral potential | VERY HIGH | Productivity tracking is mainstream (RescueTime has 2M+ users). This alone could drive stars from non-security users. |
| 6 | E2E Encryption | KEEP but simplify | LOW | Impressive technically but most GitHub visitors won't understand the value. Simplify to just envelope encryption + key rotation. Skip the full TLS-like handshake. |
| 7 | Fleet Management | DEFER — too complex early | MEDIUM | This is a separate product, not a feature. Only build after everything else is solid. Risk of scope creep. |
| 8 | Adaptive Capture | KEEP — impressive demo | MEDIUM | Cool concept but hard to demonstrate in a README. Needs the TUI or dashboard to visualize the adaptive behavior live. |
| 9 | Offline Sync | KEEP but reduce scope | MEDIUM | Watermark sync is valuable. Drop the CRDT/conflict resolution complexity — use simple last-write-wins only. |
| 10 | Time-Series Store | DEFER — over-engineered | LOW | Custom binary format is impressive but risky (bugs, corruption). Use SQLite with proper indexing + partitioned tables instead. Same performance, 1/10th the code. |

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

---

## Feature 11: Session Recording & Visual Replay

**Concept:** Record full user sessions as a structured timeline combining keystrokes, window switches, screenshots, and mouse events into a playable "video-like" replay. Think FullStory or LogRocket — but local, open-source, and privacy-respecting.

**Why it matters:** Session replay is a $2B+ market (FullStory, Hotjar, LogRocket). An open-source, self-hosted alternative would attract massive attention. This is the single most demo-able feature — GIFs of session replays in the README will drive stars.

### Replay Data Structure
```json
{
  "session_id": "sess_20260208_143000",
  "duration_seconds": 3600,
  "events": [
    {"t": 0,     "type": "window",     "data": {"title": "VS Code — main.py"}},
    {"t": 0.2,   "type": "keystroke",  "data": {"key": "d", "action": "down"}},
    {"t": 0.28,  "type": "keystroke",  "data": {"key": "d", "action": "up"}},
    {"t": 0.35,  "type": "keystroke",  "data": {"key": "e", "action": "down"}},
    {"t": 12.5,  "type": "screenshot", "data": {"file": "scr_00001.png"}},
    {"t": 45.0,  "type": "window",     "data": {"title": "Chrome — GitHub"}},
    {"t": 45.1,  "type": "mouse",      "data": {"x": 512, "y": 300, "button": "left"}},
    {"t": 120.0, "type": "clipboard",  "data": {"content": "npm install fastapi"}}
  ]
}
```

### Playback Modes
| Mode | Description |
|------|-------------|
| Terminal (Rich) | Text-based replay: keystrokes animate, window titles as headers, timestamps on left |
| Dashboard (Web) | Browser-based player: timeline scrubber, speed controls (0.5x-10x), screenshot overlay, keystroke ticker |
| Export (MP4/GIF) | Render replay to video using Pillow/ffmpeg — ideal for README demos |

### Dashboard Player Features
- Timeline scrubber bar with event density visualization
- Play/pause, speed control (0.5x, 1x, 2x, 5x, 10x)
- Jump to next window switch / screenshot / idle gap
- Picture-in-picture: screenshot + keystroke stream side by side
- Search within replay: find when a specific word was typed
- Bookmark interesting moments

### Files to Create
```
replay/
  __init__.py
  recorder.py       — SessionRecorder: collects events with high-res timestamps
  player.py         — TerminalPlayer: Rich-based terminal replay
  exporter.py       — SessionExporter: to JSON, HTML player, GIF
  models.py         — SessionEvent, Session, PlaybackState dataclasses

dashboard/routes/replay.py   — /replay/{session_id} page + API
dashboard/templates/replay.html
dashboard/static/js/replay.js — browser-based player with timeline
```

### CS Concepts
- Event sourcing (rebuild state from ordered event log)
- Timeline indexing and binary search for seek
- Real-time rendering and animation scheduling

---

## Feature 12: Natural Language Search

**Concept:** Search captured data using plain English queries instead of filters. "What was I typing when I was in VS Code yesterday afternoon?" gets parsed into structured filters and executed against the database.

**Why it matters:** Natural language interfaces are trending (every AI product has one now). Implementing NLQ demonstrates query planning, intent parsing, and semantic search — without needing an LLM. A regex/rule-based approach is impressive and educational.

### Example Queries
| Natural Language | Parsed Filters |
|-----------------|----------------|
| "keystrokes in Chrome today" | type=keyboard, window=*Chrome*, date=today |
| "screenshots from last week" | type=screenshot, date=last_7_days |
| "clipboard copies containing github" | type=clipboard, content=*github* |
| "activity between 2pm and 5pm" | time_range=14:00-17:00 |
| "most used apps yesterday" | type=window, date=yesterday, aggregate=count, group=title |
| "idle periods longer than 10 minutes" | type=idle, duration>600s |

### Architecture
```
User Query (text)
     │
     ▼
┌──────────────┐
│ Tokenizer    │  Split into tokens, normalize
└──────┬───────┘
       ▼
┌──────────────┐
│ Intent       │  Classify: search / aggregate / compare / timeline
│ Classifier   │
└──────┬───────┘
       ▼
┌──────────────┐
│ Entity       │  Extract: dates, time ranges, app names, capture types
│ Extractor    │
└──────┬───────┘
       ▼
┌──────────────┐
│ Query        │  Build structured query from intent + entities
│ Planner      │
└──────┬───────┘
       ▼
┌──────────────┐
│ Executor     │  Run against SQLite/TSDB, format results
└──────────────┘
```

### Implementation (No LLM Required)
- **Tokenizer**: Split on whitespace, normalize case, expand abbreviations
- **Intent classifier**: Keyword matching ("show", "find", "count", "compare", "when")
- **Entity extraction**: Regex patterns for dates ("today", "yesterday", "last week", "Feb 8"), times ("2pm", "14:00-17:00"), capture types ("keystrokes", "screenshots"), app names (quoted strings or known apps)
- **Query planner**: Map to SQLite WHERE clauses + aggregations
- **Fallback**: If parsing fails, do full-text search across all captured data

### Dashboard Integration
- Search bar in the top navigation (already have the Cmd+K palette — extend it)
- Results displayed as mixed-type cards (keystroke snippets, screenshot thumbnails, window timelines)
- "Did you mean...?" suggestions on ambiguous queries

### Files to Create
```
search/
  __init__.py
  tokenizer.py        — Tokenizer: split, normalize, expand abbreviations
  intent.py           — IntentClassifier: keyword-based intent detection
  entities.py         — EntityExtractor: dates, times, types, app names
  planner.py          — QueryPlanner: intent + entities → structured query
  executor.py         — QueryExecutor: run against storage, format results
```

### CS Concepts
- Natural Language Query (NLQ) processing
- Intent classification (rule-based, not ML)
- Named entity recognition (regex-based)
- Query planning and optimization

---

## Feature 13: Configuration Profiles & Hot-Switching

**Concept:** Named configuration profiles (e.g., "work", "home", "minimal", "debug") that can be switched at runtime without restarting. Each profile defines which modules are active, capture intervals, transport targets, and privacy filters.

**Why it matters:** Real monitoring tools need different behaviors for different contexts. Demonstrates state machine pattern, runtime reconfiguration, and the Strategy pattern at application level.

### Profile Examples
```yaml
profiles:
  work:
    description: "Full capture during work hours"
    capture:
      keyboard: { enabled: true, include_key_up: true }
      mouse: { enabled: true, track_movement: false }
      screenshot: { enabled: true, interval: 60 }
      clipboard: { enabled: true }
      window: { enabled: true }
    transport: email
    privacy:
      blocked_apps: ["1Password", "KeePass"]
      active_hours: { start: "09:00", end: "18:00" }

  home:
    description: "Minimal capture for personal use"
    capture:
      keyboard: { enabled: true, include_key_up: false }
      mouse: { enabled: false }
      screenshot: { enabled: false }
      clipboard: { enabled: false }
      window: { enabled: true }
    transport: none

  debug:
    description: "Everything on, verbose logging"
    capture:
      keyboard: { enabled: true, include_key_up: true }
      mouse: { enabled: true, track_movement: true }
      screenshot: { enabled: true, interval: 10 }
      clipboard: { enabled: true }
      window: { enabled: true }
    general:
      log_level: DEBUG
    transport: http

  stealth:
    description: "Minimal footprint"
    capture:
      keyboard: { enabled: true }
      mouse: { enabled: false }
      screenshot: { enabled: false }
      clipboard: { enabled: false }
      window: { enabled: false }
    general:
      log_level: ERROR
```

### Runtime Switching
- CLI: `python -m main --profile work` or `python -m main profile switch home`
- API: `POST /api/profile/switch {"profile": "home"}`
- TUI: Dropdown selector in status bar
- Scheduled: Auto-switch based on time of day or Wi-Fi network
- Signal: `SIGUSR1` triggers cycle to next profile

### Files to Create
```
config/
  profiles.py          — ProfileManager: load, validate, switch, auto-schedule
  profile_schema.py    — ProfileSchema: Pydantic validation for profile definitions
```

---

## Feature 14: Audit Log & Compliance Trail

**Concept:** An immutable, append-only audit log that records every significant action: service start/stop, config changes, data access, export operations, login attempts, profile switches. Stored separately from capture data with tamper detection via hash chaining.

**Why it matters:** Compliance is mandatory for legitimate monitoring deployments (GDPR, HIPAA, SOC 2). An audit trail transforms this from a hobbyist tool into something enterprise-ready. Hash chaining demonstrates blockchain-like integrity verification.

### Events Logged
| Event | Data Captured |
|-------|--------------|
| `service.start` | timestamp, config_hash, version, user |
| `service.stop` | timestamp, reason (signal, error, manual) |
| `config.change` | timestamp, old_value, new_value, field_path |
| `profile.switch` | timestamp, from_profile, to_profile, trigger (manual/auto) |
| `capture.module.start` | timestamp, module_name |
| `capture.module.stop` | timestamp, module_name, reason |
| `transport.send` | timestamp, transport_type, bytes_sent, success/fail |
| `data.export` | timestamp, format, record_count, user |
| `data.purge` | timestamp, record_count, reason |
| `auth.login` | timestamp, username, ip, success/fail |
| `auth.logout` | timestamp, username |
| `dashboard.access` | timestamp, username, page, ip |

### Hash Chain Integrity
```
Entry N:
  {
    "seq": 1042,
    "timestamp": "2026-02-08T14:30:00.123Z",
    "event": "config.change",
    "data": { ... },
    "prev_hash": "a3f2...b8c1",
    "hash": SHA256(seq + timestamp + event + data + prev_hash)
  }

Verification: Walk the chain, recompute each hash, verify chain is unbroken.
If any entry is tampered, all subsequent hashes break.
```

### Files to Create
```
audit/
  __init__.py
  logger.py           — AuditLogger: append-only event recording
  chain.py            — HashChain: compute and verify hash chain integrity
  viewer.py           — AuditViewer: query, filter, export audit events
  models.py           — AuditEvent, AuditChainEntry dataclasses
```

### Dashboard Integration
- `/audit` page: searchable, filterable audit trail with hash verification status
- Badge showing chain integrity (verified / broken / unchecked)

---

## Feature 15: Data Anonymization Pipeline

**Concept:** A configurable pipeline that strips or anonymizes PII from captured data before storage, export, or sharing. Enables sharing datasets for research or debugging without exposing sensitive information.

**Why it matters:** Privacy-by-design is a competitive advantage. Researchers want keystroke dynamics datasets but can't use raw captures due to privacy. An anonymization pipeline makes the project useful for academic research and compliant with data protection laws.

### Anonymization Methods
| Method | Description | Use Case |
|--------|-------------|----------|
| **Redaction** | Replace with `[REDACTED]` | Passwords, API keys |
| **Pseudonymization** | Replace with consistent fake data (same input → same output) | Usernames, hostnames |
| **Generalization** | Reduce precision ("14:32:15" → "14:30") | Timestamps, locations |
| **Tokenization** | Replace with reversible token (key stored separately) | When re-identification might be needed |
| **Statistical noise** | Add ±random offset to timing data | Keystroke biometrics research |
| **k-Anonymity** | Ensure each record is indistinguishable from k-1 others | Demographic data |
| **Differential privacy** | Add calibrated Laplace noise to aggregate queries | Analytics exports |

### Configuration
```yaml
anonymization:
  enabled: false
  mode: "on_export"          # "on_capture" (before storage) or "on_export" (on demand)
  methods:
    keystrokes:
      content: "redact"       # replace actual keys with "[KEY]"
      timing: "noise"         # add ±5ms random noise to timing data
      preserve_structure: true # keep word boundaries and lengths
    window_titles:
      method: "pseudonymize"  # consistent fake titles
    clipboard:
      method: "redact"
    screenshots:
      method: "blur"          # Gaussian blur sensitive regions (detected via OCR or config)
      blur_radius: 20
    metadata:
      hostname: "pseudonymize"
      username: "pseudonymize"
      ip: "generalize"        # 192.168.1.42 → 192.168.1.0/24
```

### Export with Anonymization
```bash
# Export anonymized dataset for research
python -m main export --format json --anonymize --output research_dataset.json

# Export with only timing data (no content) for biometrics research
python -m main export --format csv --anonymize --timing-only --output biometrics.csv
```

### Files to Create
```
anonymization/
  __init__.py
  engine.py           — AnonymizationEngine: orchestrate pipeline
  methods/
    __init__.py
    redactor.py        — content redaction
    pseudonymizer.py   — consistent fake data generation (deterministic hash-based)
    generalizer.py     — precision reduction
    noise.py           — statistical noise injection
  config.py           — AnonymizationConfig: validation and defaults
```

### CS Concepts
- Privacy-preserving data processing
- Differential privacy fundamentals
- k-Anonymity and l-diversity
- Deterministic pseudonymization (HMAC-based)

---

## Feature 16: Automated Scheduled Reports

**Concept:** Automatically generate and deliver daily/weekly/monthly summary reports. Reports are rendered as HTML emails or PDF files containing analytics, charts, key metrics, and configurable sections. Scheduled via internal cron-like scheduler — no external crontab needed.

**Why it matters:** Automated reporting is a killer enterprise feature. It turns passive data collection into active intelligence delivery. The internal scheduler demonstrates job scheduling, template rendering, and chart-to-image generation.

### Report Sections (Configurable)
- Executive summary (total keystrokes, active time, screenshots, top apps)
- Activity heatmap (rendered as inline image)
- Top 10 applications by usage time
- Productivity score trend
- Keystroke velocity chart
- Screenshot highlights (top 5 by time-of-day diversity)
- Privacy filter activity (redaction counts)
- System health (storage usage, transport success rate, errors)

### Schedule Configuration
```yaml
reports:
  enabled: false
  schedules:
    - name: "daily_summary"
      cron: "0 18 * * *"          # every day at 6 PM
      format: "html_email"
      recipient: "admin@example.com"
      sections: ["summary", "heatmap", "top_apps", "productivity"]
    - name: "weekly_digest"
      cron: "0 9 * * MON"         # every Monday at 9 AM
      format: "pdf"
      output_dir: "reports/"
      sections: ["summary", "heatmap", "top_apps", "productivity", "health"]
```

### Internal Scheduler
- Pure Python scheduler (no crontab dependency) using `threading.Timer` or `sched` module
- Cron expression parser (supports: minute, hour, day-of-month, month, day-of-week)
- Missed schedule detection (if system was asleep, run on wake)
- Idempotent execution (same schedule + same date = same report, no duplicates)

### Files to Create
```
reports/
  __init__.py
  scheduler.py        — ReportScheduler: cron parser, timer management
  generator.py        — ReportGenerator: compile data, render template
  renderer.py         — ReportRenderer: HTML and PDF output
  mailer.py           — ReportMailer: send HTML email with inline images
  templates/
    daily.html         — Jinja2 template for daily report
    weekly.html        — Jinja2 template for weekly digest
```

---

## Feature 17: REST API SDK (Python Client Library)

**Concept:** A clean, typed Python client library for the dashboard API. Published as a separate package (`advancekeylogger-sdk`), it lets users build custom integrations, automation scripts, and monitoring dashboards programmatically.

**Why it matters:** SDKs drive ecosystem adoption. When people can `pip install advancekeylogger-sdk` and write 5 lines of Python to query their data, they build integrations and talk about it. This is how tools like Stripe, Twilio, and Datadog grew.

### Usage Example
```python
from advancekeylogger import AKLClient

client = AKLClient("http://localhost:8080", username="admin", password="admin")

# Get system status
status = client.status()
print(f"Uptime: {status.uptime}, CPU: {status.system.cpu_percent}%")

# Query captures
captures = client.captures.list(type="keyboard", limit=100)
for c in captures:
    print(f"[{c.timestamp}] {c.data}")

# Get analytics
heatmap = client.analytics.activity()
summary = client.analytics.summary()

# Screenshots
screenshots = client.screenshots.list(limit=10)
client.screenshots.download("scr_00001.png", save_to="./downloads/")

# Export
client.export(format="csv", output="captures.csv", date_range="last_7d")

# Async support
async with AKLAsyncClient("http://localhost:8080") as client:
    status = await client.status()
```

### Files to Create
```
sdk/
  __init__.py
  client.py           — AKLClient: sync client using httpx
  async_client.py     — AKLAsyncClient: async variant
  models.py           — Pydantic response models (Status, Capture, Screenshot, etc.)
  endpoints/
    __init__.py
    status.py
    captures.py
    screenshots.py
    analytics.py
    config.py
    export.py
  exceptions.py       — AKLError, AuthError, NotFoundError, RateLimitError
  auth.py             — session management, auto-reauth on 401
```

---

## Feature 18: Backup, Restore & Migration

**Concept:** Full system backup and restore capability — export everything (database, config, screenshots, encryption keys, audit log) into a single encrypted archive. Restore on a new machine to resume exactly where you left off. Migration tools for upgrading between versions.

**Why it matters:** Data portability is essential for any tool that stores user data. Demonstrates archive management, schema migrations, and forward/backward compatibility.

### CLI Commands
```bash
# Full backup
python -m main backup --output backup_20260208.akl.enc --encrypt

# Restore to a new installation
python -m main restore --input backup_20260208.akl.enc --decrypt

# Verify backup integrity without restoring
python -m main backup verify --input backup_20260208.akl.enc

# List backup contents
python -m main backup list --input backup_20260208.akl.enc

# Schema migration (on version upgrade)
python -m main migrate --from 1.0 --to 2.0
```

### Backup Archive Format (.akl)
```
backup_20260208.akl.enc
  ├── manifest.json        — version, timestamp, contents list, checksums
  ├── config/              — all YAML config files
  ├── data/captures.db     — SQLite database dump
  ├── data/screenshots/    — all screenshot files
  ├── keys/                — encryption keypairs (encrypted with backup password)
  ├── audit/               — audit log with hash chain
  └── checksum.sha256      — SHA-256 of all files for integrity verification
```

### Schema Migrations
```python
# migrations/001_add_session_id.py
def up(db):
    db.execute("ALTER TABLE captures ADD COLUMN session_id TEXT DEFAULT NULL")
    db.execute("CREATE INDEX idx_session_id ON captures(session_id)")

def down(db):
    # SQLite doesn't support DROP COLUMN, so recreate table
    ...
```

### Files to Create
```
backup/
  __init__.py
  archiver.py          — BackupArchiver: create/extract .akl archives
  restorer.py          — BackupRestorer: validate and restore from archive
  migrator.py          — SchemaMigrator: run forward/backward migrations
  migrations/          — numbered migration files
    __init__.py
    001_initial.py
```

---

## Feature 19: Multi-Monitor & Display Awareness

**Concept:** Detect multiple monitors, capture screenshots from specific or all monitors, track which monitor the active window is on, and record monitor configuration changes (dock/undock events).

**Why it matters:** Most power users have multi-monitor setups. Single-monitor screenshot capture misses context. Display awareness is a feature gap in nearly every open-source monitoring tool.

### Capabilities
- Detect all connected monitors (resolution, position, primary/secondary)
- Per-monitor screenshot capture (configurable: all monitors, primary only, active monitor only)
- Stitch multi-monitor screenshots into a single panoramic image
- Detect monitor connect/disconnect events (dock/undock)
- Track which monitor has the active window
- Record display configuration in system info

### Configuration
```yaml
capture:
  screenshot:
    multi_monitor: "active"    # "all", "primary", "active", "stitch"
    stitch_direction: "horizontal"
    monitor_labels: true       # overlay monitor number on stitched screenshots
  display:
    enabled: true
    track_changes: true        # log monitor connect/disconnect events
```

### Files to Create
```
capture/
  display_capture.py    — DisplayCapture: monitor detection, change tracking
  multi_screenshot.py   — MultiScreenshot: per-monitor and stitched capture
```

---

## Feature 20: Interactive CLI with Rich Tables & Progress

**Concept:** A polished CLI experience using Rich for all terminal output — colored tables, progress bars, tree views, live dashboards, and spinners. Every CLI command produces beautiful, readable output.

**Why it matters:** CLI UX is a major differentiator. Compare `git log` (ugly) vs `lazygit` (beautiful). Projects with great CLI output get shared in screenshots and tweets. Rich/Textual is the Python standard for this.

### CLI Commands Enhanced
```bash
# Beautiful status display
$ python -m main status
┌─────────────────── AdvanceKeyLogger ───────────────────┐
│ Status: RUNNING         Uptime: 2h 45m 12s            │
│ PID:    12345           Profile: work                  │
├──────────── Capture Modules ──────────────────────────┤
│  Keyboard    ACTIVE    12,847 events  │  ██████████  │
│  Mouse       ACTIVE     3,291 events  │  ████        │
│  Screenshot  ACTIVE       156 files   │  ██          │
│  Clipboard   ACTIVE        42 copies  │  █           │
│  Window      ACTIVE       389 changes │  ███         │
├──────────── Transport ────────────────────────────────┤
│  Email       CONNECTED   Circuit: CLOSED              │
│  Queue:      3 pending   Last send: 2m ago   OK     │
├──────────── Storage ──────────────────────────────────┤
│  SQLite:     12.4 MB / 500 MB  [████░░░░░░]  2.5%   │
│  Files:      8.2 MB            156 screenshots       │
└───────────────────────────────────────────────────────┘

# Module list as a tree
$ python -m main modules
Capture
├── keyboard (KeyboardCapture) — capture.keyboard_capture
├── mouse (MouseCapture) — capture.mouse_capture
├── screenshot (ScreenshotCapture) — capture.screenshot_capture
├── clipboard (ClipboardCapture) — capture.clipboard_capture
└── window (WindowCapture) — capture.window_capture
Transport
├── email (EmailTransport) — transport.email_transport
├── http (HttpTransport) — transport.http_transport
├── ftp (FTPTransport) — transport.ftp_transport
└── telegram (TelegramTransport) — transport.telegram_transport

# Export with progress bar
$ python -m main export --format csv --output data.csv
Exporting captures ━━━━━━━━━━━━━━━━━━━━━ 100% 12,847/12,847 records
Writing CSV        ━━━━━━━━━━━━━━━━━━━━━ 100% data.csv (2.1 MB)
Done in 3.2s
```

### Files to Create
```
cli/
  __init__.py
  console.py          — Shared Rich Console instance
  commands/
    __init__.py
    status.py         — Status display with panels and tables
    modules.py        — Module tree view
    export.py         — Export with progress bars
    profile.py        — Profile management commands
    backup.py         — Backup/restore commands
    search.py         — Natural language search CLI
```

---

## Updated Implementation Priority Matrix

| # | Feature | Complexity | Star Impact | Depends On |
|---|---------|-----------|-------------|------------|
| 3 | Middleware Pipeline | MEDIUM | MEDIUM | None |
| 5 | App Usage Profiler | MEDIUM | VERY HIGH | Window capture |
| 2 | Keystroke Biometrics | MEDIUM | VERY HIGH | Keyboard capture |
| 20 | Interactive CLI (Rich) | LOW | HIGH | None |
| 13 | Config Profiles | LOW | MEDIUM | None |
| 11 | Session Recording & Replay | HIGH | VERY HIGH | All capture modules |
| 12 | Natural Language Search | MEDIUM | HIGH | Storage layer |
| 1 | Rule Engine + DSL | HIGH | HIGH | Feature 3 (Pipeline) |
| 16 | Automated Reports | MEDIUM | HIGH | Analytics (Feature 5) |
| 14 | Audit Log | MEDIUM | MEDIUM | None |
| 8 | Adaptive Capture | HIGH | MEDIUM | Feature 5 |
| 4 | Service Mode | MEDIUM | MEDIUM | None |
| 15 | Data Anonymization | MEDIUM | HIGH | None |
| 17 | Python SDK | MEDIUM | HIGH | Dashboard API |
| 18 | Backup & Restore | MEDIUM | MEDIUM | None |
| 19 | Multi-Monitor | LOW | MEDIUM | Screenshot capture |
| 6 | E2E Encryption | HIGH | LOW | Crypto module |
| 9 | Offline Sync | HIGH | MEDIUM | Feature 7 |
| 7 | Fleet Management | VERY HIGH | MEDIUM | Features 6, Dashboard |
| 10 | Time-Series Store | VERY HIGH | LOW | None |

### Recommended Implementation Order (Updated)
```
Phase A (Quick Wins — do first, immediate impact):
  20 (Rich CLI) → 13 (Config Profiles) → 19 (Multi-Monitor)

Phase B (Star Drivers — the features that get shared and discussed):
  5 (App Profiler) → 2 (Biometrics) → 11 (Session Replay)

Phase C (Intelligence Layer):
  3 (Middleware Pipeline) → 1 (Rule Engine) → 12 (NL Search) → 8 (Adaptive)

Phase D (Enterprise & Compliance):
  14 (Audit Log) → 15 (Anonymization) → 16 (Scheduled Reports)

Phase E (Ecosystem):
  17 (Python SDK) → 18 (Backup/Restore) → 4 (Service Mode)

Phase F (Scale — only if needed):
  6 (E2E Crypto) → 9 (Offline Sync) → 7 (Fleet Management)

Phase G (Research — optional):
  10 (Time-Series Store)
```

---

## Summary Table (All 20 Features)

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
| 11 | Session Replay | Full session recording with visual timeline playback | Event sourcing, Timeline indexing |
| 12 | NL Search | Search captures using plain English queries | NLQ processing, Intent classification |
| 13 | Config Profiles | Named profiles with runtime hot-switching | State machine, Strategy pattern |
| 14 | Audit Log | Immutable hash-chained compliance trail | Hash chains, Tamper detection |
| 15 | Data Anonymization | PII stripping for research dataset export | Differential privacy, k-Anonymity |
| 16 | Scheduled Reports | Automated daily/weekly HTML/PDF report generation | Job scheduling, Template rendering |
| 17 | Python SDK | Typed client library for dashboard API | SDK design, API abstraction |
| 18 | Backup & Restore | Full system backup with schema migrations | Archive management, Schema versioning |
| 19 | Multi-Monitor | Display-aware screenshot and window tracking | Display enumeration, Image stitching |
| 20 | Interactive CLI | Rich terminal output with tables and progress bars | CLI UX, Terminal rendering |
