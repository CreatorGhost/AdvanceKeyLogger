# AdvanceKeyLogger

A modular Python input monitoring and screen capture tool built for **educational purposes** — learning about OS-level input APIs, networking, encryption, plugin architectures, and resilience patterns.

> **Disclaimer:** This project is for educational and authorized security research only. Do not use on systems you do not own or without explicit written permission. Unauthorized monitoring may violate local, state, and federal laws.

---

## Table of Contents

- [Features at a Glance](#features-at-a-glance)
- [Complete Feature Guide](#complete-feature-guide)
  - [Capture Plugins](#1-capture-plugins)
  - [Audio Recording](#2-audio-recording)
  - [Transport Modules](#3-transport-modules)
  - [Storage Backends](#4-storage-backends)
  - [Encryption and Compression](#5-encryption-and-compression)
  - [Pipeline and Middleware](#6-pipeline-and-middleware)
  - [Rule Engine](#7-rule-engine)
  - [Keystroke Biometrics](#8-keystroke-biometrics)
  - [App Usage Profiler](#9-app-usage-profiler)
  - [Service/Daemon Mode](#10-servicedaemon-mode)
  - [Self-Destruct / Anti-Forensics](#11-self-destruct--anti-forensics)
  - [Auto-Install Dependencies](#12-auto-install-dependencies)
  - [Dashboard (Web UI)](#13-dashboard-web-ui)
  - [Fleet Management](#14-fleet-management)
  - [Resilience Patterns](#15-resilience-patterns)
  - [Process Management](#16-process-management)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Testing](#testing)
- [Development](#development)
- [License](#license)

---

## Features at a Glance

| Category | Features |
|----------|----------|
| **Capture** | Keyboard, mouse, screenshot, clipboard, active window, audio recording |
| **Transport** | Email (SMTP), HTTP (POST/PUT), FTP/FTPS, Telegram Bot API, WebSocket |
| **Storage** | Local filesystem with rotation, SQLite with batch tracking, Fleet SQLite |
| **Security** | AES-256-CBC, E2E (X25519 + AES-256-GCM), PBKDF2, RSA signature verification |
| **Resilience** | Retry with exponential backoff, circuit breaker, transport queue |
| **Pipeline** | Configurable middleware chain (dedup, rate-limit, enrich, route, truncate) |
| **Rule Engine** | YAML-based conditional rules with pattern matching and actions |
| **Biometrics** | Keystroke timing analysis, user profiling, authentication via typing patterns |
| **Profiler** | App usage tracking, categorization, productivity scoring |
| **Service** | Cross-platform daemon mode (systemd, launchd, Windows Service) |
| **Fleet** | Distributed agent management, command dispatch, heartbeat monitoring |
| **Dashboard** | FastAPI web UI with 8+ pages, WebSocket real-time updates, command palette |
| **Anti-Forensics** | Self-destruct with secure wipe, trace removal, service cleanup |
| **Auto-Install** | Automatic dependency detection and installation at startup |
| **Operations** | PID lock, graceful shutdown, rotating logs, dry-run mode |
| **Architecture** | Plugin system with auto-discovery, EventBus pub/sub, YAML + env var config |
| **Cross-platform** | Windows, Linux, macOS support |

---

## Complete Feature Guide

Below is a detailed guide to every feature in the project. Each section links directly to the source code so you can study the implementation.

---

### 1. Capture Plugins

The capture system uses a **plugin architecture** with auto-discovery. All plugins inherit from [`BaseCapture`](capture/base.py) and self-register via the `@register_capture` decorator. The registry lives in [`capture/__init__.py`](capture/__init__.py).

**How to study this pattern:** Start with [`capture/base.py`](capture/base.py) to understand the abstract interface (`start()`, `stop()`, `collect()`), then look at how [`capture/__init__.py`](capture/__init__.py) manages the registry and auto-imports plugins.

#### Keyboard Capture
- **Source:** [`capture/keyboard_capture.py`](capture/keyboard_capture.py), [`capture/macos_keyboard_backend.py`](capture/macos_keyboard_backend.py)
- **Concepts:** OS-level keyboard hooks, thread-safe ring buffer, special key handling, backend selection pattern
- **Backends:**
  - **macOS native (CGEventTap):** Uses `pyobjc-framework-Quartz` for direct access to macOS Core Graphics event taps. Provides reliable Unicode character extraction via `CGEventKeyboardGetUnicodeString`. Automatically selected when running on macOS with pyobjc installed.
  - **pynput (cross-platform):** Default backend using `pynput.keyboard.Listener`. Used on Linux, Windows, and macOS when pyobjc is not available.
- **Config:** `capture.keyboard.enabled`, `include_key_up`, `max_buffer`, `biometrics_enabled`
- **Output:** `{"type": "keystroke", "data": "a", "timestamp": 1700000000.0}`

#### Mouse Capture
- **Source:** [`capture/mouse_capture.py`](capture/mouse_capture.py), [`capture/macos_mouse_backend.py`](capture/macos_mouse_backend.py)
- **Concepts:** OS-level mouse hooks, click vs movement tracking, callback integration with screenshot capture
- **Backends:**
  - **macOS native (CGEventTap):** Uses `pyobjc-framework-Quartz` for direct mouse event taps. More reliable permission handling and higher precision coordinates.
  - **pynput (cross-platform):** Default backend. Used on Linux, Windows, and macOS when pyobjc is not available.
- **Config:** `capture.mouse.enabled`, `track_movement`
- **Output:** `{"type": "mouse_click", "data": {"x": 500, "y": 300, "button": "left", "pressed": true}, ...}`

#### Screenshot Capture
- **Source:** [`capture/screenshot_capture.py`](capture/screenshot_capture.py), [`capture/macos_screenshot_backend.py`](capture/macos_screenshot_backend.py)
- **Concepts:** On-demand screen capture, file-based output with metadata, max-count enforcement
- **Backends:**
  - **macOS native (Quartz CoreGraphics):** Uses `CGWindowListCreateImage` for proper Retina/HiDPI display support and faster capture. Saves via AppKit `NSBitmapImageRep` or `CGImageDestination`.
  - **PIL ImageGrab (cross-platform):** Default backend. Used on Linux, Windows, and macOS when pyobjc is not available.
- **Config:** `capture.screenshot.enabled`, `quality`, `format`, `max_count`, `capture_region`
- **Output:** `{"type": "screenshot", "path": "./data/screenshots/screenshot_0001.png", "size": 45230, ...}`

#### Clipboard Capture
- **Source:** [`capture/clipboard_capture.py`](capture/clipboard_capture.py), [`capture/macos_clipboard_backend.py`](capture/macos_clipboard_backend.py)
- **Concepts:** Change detection, content truncation, daemon thread with stop event
- **Backends:**
  - **macOS native (NSPasteboard):** Uses `AppKit.NSPasteboard` with `changeCount` for efficient change detection without subprocess overhead.
  - **pyperclip (cross-platform):** Default backend using `pbpaste`/`xclip` subprocesses. Used on Linux, Windows, and macOS when pyobjc is not available.
- **Config:** `capture.clipboard.enabled`, `poll_interval`, `max_length`
- **Output:** `{"type": "clipboard", "data": "copied text", ...}`

#### Window Capture
- **Source:** [`capture/window_capture.py`](capture/window_capture.py), [`capture/macos_window_backend.py`](capture/macos_window_backend.py)
- **Concepts:** Platform-native APIs, change detection
- **Backends:**
  - **macOS native (NSWorkspace + CGWindowList):** Uses `NSWorkspace.frontmostApplication()` and `CGWindowListCopyWindowInfo` for app name + window title without subprocess overhead.
  - **osascript (macOS fallback):** AppleScript subprocess, used when pyobjc is not installed.
  - **xdotool (Linux):** Subprocess-based window title query.
  - **ctypes (Windows):** Direct Win32 API calls.
- **Config:** `capture.window.enabled`, `poll_interval`
- **Output:** `{"type": "window", "data": "Visual Studio Code", ...}`

---

### 2. Audio Recording

Records audio clips at a configurable interval and saves WAV files to disk.

- **Source:** [`capture/audio_capture.py`](capture/audio_capture.py), [`capture/macos_audio_backend.py`](capture/macos_audio_backend.py)
- **Test:** [`tests/test_audio_capture.py`](tests/test_audio_capture.py)
- **Concepts:** Daemon thread for periodic recording, WAV output, graceful import, thread-safe buffer, max-count enforcement
- **Backends:**
  - **macOS native (AVFoundation):** Uses `AVAudioEngine` via `pyobjc-framework-AVFoundation` for tighter Core Audio integration.
  - **sounddevice (cross-platform):** Default backend using PortAudio. Used on Linux, Windows, and macOS when pyobjc is not available.
- **Config:**
  ```yaml
  capture:
    audio:
      enabled: false
      duration: 10          # seconds per clip
      sample_rate: 44100    # Hz
      channels: 1           # mono
      max_count: 50         # max clips before stopping
      interval: 300         # seconds between recordings
  ```
- **Output:** `{"type": "audio", "path": "./data/audio/audio_0001.wav", "size": 88244, ...}`
- **Dependencies:** `sounddevice>=0.4.6`, `numpy>=1.24.0` (optional — gracefully skipped if not installed)

---

### 3. Transport Modules

All transport modules inherit from [`BaseTransport`](transport/base.py) and self-register. The registry lives in [`transport/__init__.py`](transport/__init__.py).

#### Email (SMTP)
- **Source:** [`transport/email_transport.py`](transport/email_transport.py)
- **Concepts:** SMTP with SSL/TLS, `email.message.EmailMessage`, auto-reconnect, retry with backoff

#### HTTP
- **Source:** [`transport/http_transport.py`](transport/http_transport.py)
- **Concepts:** `requests.Session` connection pooling, configurable method/headers/timeout

#### FTP/FTPS
- **Source:** [`transport/ftp_transport.py`](transport/ftp_transport.py)
- **Concepts:** `ftplib.FTP_TLS` with `prot_p()`, remote directory auto-creation

#### Telegram Bot API
- **Source:** [`transport/telegram_transport.py`](transport/telegram_transport.py)
- **Concepts:** REST API integration, message vs document upload based on size, bot validation

#### WebSocket
- **Source:** [`transport/websocket_transport.py`](transport/websocket_transport.py)
- **Concepts:** Persistent bidirectional connection, auto-reconnect with backoff, heartbeat keep-alive, optional SSL/TLS, message compression
- **Config:** `transport.websocket.url`, `reconnect_interval`, `heartbeat_interval`, `ssl`, `verify_ssl`
- **Dependencies:** `websockets>=11.0` (optional — install with `pip install .[transports]`)

---

### 4. Storage Backends

#### Local Filesystem
- **Source:** [`storage/manager.py`](storage/manager.py)
- **Concepts:** File-based storage with capacity tracking, auto-rotation at 80% capacity, cleanup after transport

#### SQLite
- **Source:** [`storage/sqlite_storage.py`](storage/sqlite_storage.py)
- **Concepts:** Structured storage with WAL mode, batch retrieval of unsent records, mark-as-sent tracking, purge old data
- **Test:** [`tests/test_storage.py`](tests/test_storage.py)

#### Fleet Storage
- **Source:** [`storage/fleet_storage.py`](storage/fleet_storage.py)
- **Concepts:** Dedicated SQLite database for fleet management — agent registry, command history, heartbeat logs, controller key persistence, enrollment key tracking

---

### 5. Encryption and Compression

- **Encryption Source:** [`utils/crypto.py`](utils/crypto.py)
- **Compression Source:** [`utils/compression.py`](utils/compression.py)
- **Test:** [`tests/test_utils.py`](tests/test_utils.py) (TestCrypto, TestCompression classes)
- **Concepts:**
  - AES-256-CBC with random IV per encryption
  - PBKDF2-HMAC-SHA256 key derivation (480,000 iterations)
  - ZIP bundling (multiple files into one archive)
  - GZIP compression with ratio logging

---

### 6. Pipeline and Middleware

A configurable middleware chain that processes events before storage/transport.

- **Source:** [`pipeline/`](pipeline/)
  - [`pipeline/core.py`](pipeline/core.py) — Pipeline orchestrator
  - [`pipeline/base_middleware.py`](pipeline/base_middleware.py) — Middleware base class
  - [`pipeline/registry.py`](pipeline/registry.py) — Built-in middleware registry
  - [`pipeline/context.py`](pipeline/context.py) — Pipeline context
- **Test:** [`tests/test_pipeline.py`](tests/test_pipeline.py)
- **Concepts:** Chain-of-responsibility pattern, configurable ordering, drop/pass/modify semantics
- **Built-in middleware:**
  - `timestamp_enricher` — adds/normalizes timestamps
  - `context_annotator` — adds system context
  - `deduplicator` — suppresses duplicate events within a time window
  - `content_truncator` — truncates large payloads
  - `rate_limiter` — caps events per second
  - `conditional_router` — routes events to different backends by type
  - `metrics_emitter` — logs pipeline throughput metrics

---

### 7. Rule Engine

YAML-based conditional rules with pattern matching and triggered actions.

- **Source:** [`engine/`](engine/)
  - [`engine/rule_engine.py`](engine/rule_engine.py) — Engine orchestrator
  - [`engine/rule_parser.py`](engine/rule_parser.py) — YAML rule parser
  - [`engine/evaluator.py`](engine/evaluator.py) — Condition evaluator
  - [`engine/actions.py`](engine/actions.py) — Action definitions
  - [`engine/event_bus.py`](engine/event_bus.py) — Event pub/sub bus
  - [`engine/registry.py`](engine/registry.py) — Rule registry
- **Test:** [`tests/test_rules.py`](tests/test_rules.py)
- **Concepts:** Expression evaluator, pattern matching syntax, event-driven architecture

---

### 8. Keystroke Biometrics

Analyzes typing patterns to build user profiles based on keystroke timing. Optionally authenticates users by matching live typing against stored profiles.

- **Source:** [`biometrics/`](biometrics/)
  - [`biometrics/collector.py`](biometrics/collector.py) — Timing data collection (dwell time, flight time)
  - [`biometrics/analyzer.py`](biometrics/analyzer.py) — Statistical profile generation
  - [`biometrics/matcher.py`](biometrics/matcher.py) — Profile distance/similarity comparison
  - [`biometrics/models.py`](biometrics/models.py) — Data models
- **Test:** [`tests/test_biometrics.py`](tests/test_biometrics.py)
- **Concepts:** Dwell time (key hold duration), flight time (inter-key interval), statistical profiling, distance metrics, user authentication via typing patterns
- **Authentication config:**
  ```yaml
  biometrics:
    authentication:
      enabled: false
      match_threshold: 50.0    # Distance threshold (lower = stricter)
      min_samples: 100         # Min keystrokes for reliable matching
  ```

---

### 9. App Usage Profiler

Tracks which applications are used, for how long, and scores productivity.

- **Source:** [`profiler/`](profiler/)
  - [`profiler/tracker.py`](profiler/tracker.py) — Usage session tracking
  - [`profiler/categorizer.py`](profiler/categorizer.py) — App-to-category mapping
  - [`profiler/scorer.py`](profiler/scorer.py) — Productivity scoring
  - [`profiler/models.py`](profiler/models.py) — Data models
- **Test:** [`tests/test_profiler.py`](tests/test_profiler.py)
- **Concepts:** Session tracking with idle detection, configurable categories, focus time calculation, top-N reporting

---

### 10. Service/Daemon Mode

Cross-platform background service support — install, start, stop, restart, uninstall.

- **Source:** [`service/`](service/)
  - [`service/manager.py`](service/manager.py) — Cross-platform service manager (dispatches by OS)
  - [`service/linux_systemd.py`](service/linux_systemd.py) — Linux systemd unit file generation
  - [`service/macos_launchd.py`](service/macos_launchd.py) — macOS LaunchAgent plist generation
  - [`service/windows_service.py`](service/windows_service.py) — Windows service management
- **Test:** [`tests/test_service.py`](tests/test_service.py)
- **Concepts:** systemd unit files, launchd plists, platform detection, service lifecycle management
- **Usage:**
  ```bash
  python main.py service install
  python main.py service start
  python main.py service stop
  python main.py service restart
  python main.py service status
  python main.py service uninstall
  ```

---

### 11. Self-Destruct / Anti-Forensics

Removes all data, logs, databases, PID files, and optionally the service and program directory.

- **Source:** [`utils/self_destruct.py`](utils/self_destruct.py)
- **Test:** [`tests/test_self_destruct.py`](tests/test_self_destruct.py)
- **Concepts:** Secure file deletion (overwrite with zeros before unlinking), recursive directory wipe, SQLite WAL/SHM cleanup, platform-specific scheduled self-removal scripts
- **Key functions:**
  - `secure_delete_file()` — overwrites file with zeros then deletes
  - `remove_data_directory()` — recursively wipes `data/`
  - `remove_log_files()` — removes logs and parent directory
  - `remove_sqlite_database()` — removes .db, -wal, -shm files
  - `remove_pid_file()` — removes PID lock file
  - `uninstall_service()` — uninstalls the system service
  - `remove_program_directory()` — schedules delayed program directory removal
  - `execute_self_destruct()` — orchestrates all cleanup steps
- **Config:**
  ```yaml
  self_destruct:
    secure_wipe: false       # overwrite files with zeros before deleting
    remove_program: false    # remove the entire program directory
    remove_service: true     # uninstall the system service
  ```
- **Usage:**
  ```bash
  python main.py --self-destruct
  # Prompts: "WARNING: This will permanently delete ALL data, logs, and traces."
  # Type 'YES' to confirm.
  ```

---

### 12. Auto-Install Dependencies

Checks for missing Python packages at startup and optionally installs them via pip.

- **Source:** [`utils/dependency_check.py`](utils/dependency_check.py)
- **Test:** [`tests/test_dependency_check.py`](tests/test_dependency_check.py)
- **Concepts:** `importlib.import_module()` for detection, `subprocess.run()` with pip for installation, configurable package map, timeout handling
- **Key functions:**
  - `check_package()` — tests if a module is importable
  - `install_package()` — runs `pip install` with timeout
  - `check_and_install_dependencies()` — iterates the package map, installs missing packages
- **Package map** (`PACKAGE_MAP`): maps import names to pip names (e.g., `"PIL"` -> `"Pillow"`)
- **Config:**
  ```yaml
  general:
    auto_install_deps: false   # set to true to auto-install at startup
  ```

---

### 13. Dashboard (Web UI)

A FastAPI-based web dashboard with 8+ pages, real-time WebSocket updates, command palette, and fleet management views.

- **Source:** [`dashboard/`](dashboard/)
  - [`dashboard/app.py`](dashboard/app.py) — FastAPI application factory with lifespan management
  - [`dashboard/auth.py`](dashboard/auth.py) — Session-based authentication with JWT support
  - [`dashboard/run.py`](dashboard/run.py) — Dashboard server launcher
  - **Routes:**
    - [`dashboard/routes/pages.py`](dashboard/routes/pages.py) — HTML page routes (dashboard, analytics, captures, screenshots, settings, live, fleet)
    - [`dashboard/routes/api.py`](dashboard/routes/api.py) — REST API endpoints for captures, screenshots, analytics
    - [`dashboard/routes/fleet_api.py`](dashboard/routes/fleet_api.py) — Fleet management REST API (agent registration, heartbeat, commands)
    - [`dashboard/routes/fleet_ui.py`](dashboard/routes/fleet_ui.py) — Fleet UI page routes
    - [`dashboard/routes/fleet_dashboard_api.py`](dashboard/routes/fleet_dashboard_api.py) — Fleet dashboard data API
    - [`dashboard/routes/websocket.py`](dashboard/routes/websocket.py) — WebSocket endpoint for real-time updates
  - **Templates:** `base.html`, `dashboard.html`, `analytics.html`, `captures.html`, `screenshots.html`, `settings.html`, `live.html`, `login.html`, `landing.html`, `fleet/index.html`, `fleet/agent_details.html`
  - **Frontend JS:**
    - [`dashboard/static/js/ws-client.js`](dashboard/static/js/ws-client.js) — WebSocket client with auto-reconnect, LiveDashboard class for real-time event feed
    - [`dashboard/static/js/cmd-palette.js`](dashboard/static/js/cmd-palette.js) — Command palette (Ctrl+K) for quick navigation
    - [`dashboard/static/js/app.js`](dashboard/static/js/app.js), `dashboard.js`, `analytics.js`, `captures.js`, `screenshots.js`, `settings.js`
- **Test:** [`tests/test_dashboard.py`](tests/test_dashboard.py)
- **Concepts:** FastAPI, Jinja2 templates, session auth, WebSocket real-time updates, path traversal protection, command palette UX
- **Pages:**
  | Page | URL | Description |
  |------|-----|-------------|
  | Dashboard | `/` | Overview with status cards and activity feed |
  | Analytics | `/analytics` | Capture metrics, activity charts |
  | Captures | `/captures` | Keystroke log viewer |
  | Screenshots | `/screenshots` | Screenshot gallery with viewer |
  | Settings | `/settings` | Configuration management |
  | Live | `/live` | Real-time activity feed via WebSocket |
  | Fleet | `/fleet` | Agent management, command dispatch |
  | Agent Details | `/fleet/agents/{id}` | Individual agent status and command history |
- **API Endpoints:**
  | Endpoint | Description |
  |----------|-------------|
  | `GET /api/status` | System status |
  | `GET /api/captures` | Recent captures |
  | `GET /api/screenshots` | Screenshot list |
  | `GET /api/analytics/activity` | Activity data |
  | `GET /api/analytics/summary` | Analytics summary |
  | `GET /api/config` | Current configuration |
  | `GET /api/modules` | Module status |
  | `POST /api/fleet/agents/register` | Agent registration |
  | `POST /api/fleet/agents/{id}/heartbeat` | Agent heartbeat |
  | `GET /api/fleet/agents/{id}/commands` | Poll pending commands |
  | `POST /api/fleet/commands/{id}/response` | Command result |
  | `WS /ws` | WebSocket for real-time dashboard updates |

---

### 14. Fleet Management

A distributed agent management system for controlling multiple instances from a central dashboard.

- **Source:**
  - [`agent_controller.py`](agent_controller.py) — Core Controller/Agent architecture with command dispatch, heartbeat monitoring, SecureChannel (RSA key pairs, signature verification)
  - [`fleet/controller.py`](fleet/controller.py) — FleetController with SQLite persistence, key management
  - [`fleet/agent.py`](fleet/agent.py) — FleetAgent with HTTP/WebSocket transport, auto-reconnect
  - [`fleet/run_agent.py`](fleet/run_agent.py) — Agent entry point script
  - [`fleet/auth.py`](fleet/auth.py) — JWT-based authentication for fleet communication
  - [`storage/fleet_storage.py`](storage/fleet_storage.py) — Persistent storage for agents, commands, keys
- **Concepts:** Distributed architecture, command-and-control pattern, RSA signature verification, JWT authentication, priority command queues, heartbeat-based health monitoring
- **Config:**
  ```yaml
  fleet:
    enabled: false
    database_path: "./data/fleet.db"
    agent:
      controller_url: ""
      heartbeat_interval: 60
      reconnect_interval: 30
      max_retries: 5
      command_poll_interval: 5
      sign_requests: false
      transport_method: "http"    # "http" or "websocket"
    controller:
      max_agents: 1000
      heartbeat_timeout: 120
      max_command_history: 1000
      cleanup_interval: 300
    security:
      require_signature_verification: true
  ```
- **Agent usage:**
  ```bash
  python -m fleet.run_agent --controller-url http://controller:8000
  ```

---

### 15. Resilience Patterns

- **Source:** [`utils/resilience.py`](utils/resilience.py)
- **Test:** [`tests/test_utils.py`](tests/test_utils.py) (TestRetry, TestCircuitBreaker, TestTransportQueue classes)
- **Concepts:**
  - **Retry with exponential backoff:** `@retry` decorator, configurable max attempts, specific exception types, `retry_on_false` mode
  - **Circuit breaker:** CLOSED -> OPEN -> HALF_OPEN state machine, configurable failure threshold and cooldown
  - **Transport queue:** Thread-safe deque with batch drain, requeue on failure, max-size enforcement

---

### 16. Process Management

- **Source:** [`utils/process.py`](utils/process.py)
- **Test:** [`tests/test_utils.py`](tests/test_utils.py) (TestPIDLock, TestGracefulShutdown classes)
- **Concepts:**
  - **PID lock:** Prevents multiple instances, stale PID detection, atexit cleanup
  - **Graceful shutdown:** SIGINT/SIGTERM signal handling, clean exit with resource cleanup

---

## Architecture

```
                    +------------------+
                    |     main.py      |
                    |  (orchestrator)  |
                    +--------+---------+
                             |
         +-------------------+-------------------+
         |                   |                   |
+--------v--------+ +--------v--------+ +--------v--------+
|    Capture       | |    Storage      | |   Transport     |
|    Plugins       | |    Backends     | |    Plugins      |
+-----------------+ +-----------------+ +-----------------+
| keyboard        | | local FS        | | email (SMTP)    |
| mouse           | | SQLite          | | HTTP            |
| screenshot      | | Fleet SQLite    | | FTP/FTPS        |
| clipboard       | +-----------------+ | Telegram        |
| window          |                     | WebSocket       |
| audio           | +-----------------+ +-----------------+
+-----------------+ |   Pipeline      |
                    |   Middleware     | +-----------------+
+-----------------+ +-----------------+ |   Dashboard     |
|   Rule Engine   | | deduplicator    | |   (FastAPI)     |
|   (YAML rules)  | | rate_limiter    | |   + WebSocket   |
+-----------------+ | router          | |   + Cmd Palette |
                    | truncator       | +-----------------+
+-----------------+ | enricher        |
|  Biometrics     | +-----------------+ +-----------------+
|  (typing +      |                     |   Fleet Mgmt    |
|   auth)         | +-----------------+ |  Controller +   |
+-----------------+ |  App Profiler   | |  Agent + Auth   |
                    |  (productivity) | +-----------------+
+-----------------+ +-----------------+
|   Service       |                     +-----------------+
| systemd/launchd | +-----------------+ |  Self-Destruct  |
| Windows Service | |   Utilities     | |  (anti-forensic)|
+-----------------+ | crypto | zip    | +-----------------+
                    | retry  | PID    |
+-----------------+ | logger | sysinfo| +-----------------+
|   EventBus      | | event_bus       | |  Auto-Install   |
|   (pub/sub)     | +-----------------+ |  (dep checker)  |
+-----------------+                     +-----------------+
```

**Plugin System:** Capture and transport modules self-register via decorators (`@register_capture`, `@register_transport`). Modules are auto-imported at startup, and missing optional dependencies are handled gracefully.

**Event System:** The [`EventBus`](engine/event_bus.py) provides decoupled pub/sub event routing between components (rule engine triggers, fleet events, pipeline notifications).

---

## Project Structure

```
AdvanceKeyLogger/
├── main.py                          # Entry point & orchestration loop
├── agent_controller.py              # Core Controller/Agent architecture (fleet)
├── pyproject.toml                   # Project metadata & dependencies
├── config/
│   ├── settings.py                  # Settings singleton (YAML + env vars)
│   └── default_config.yaml          # Default configuration
├── capture/
│   ├── __init__.py                  # Plugin registry & auto-discovery
│   ├── base.py                      # BaseCapture abstract class
│   ├── keyboard_capture.py          # Keystroke monitoring (backend selection)
│   ├── macos_keyboard_backend.py    # Native macOS CGEventTap keyboard backend
│   ├── mouse_capture.py             # Mouse click/movement (backend selection)
│   ├── macos_mouse_backend.py       # Native macOS CGEventTap mouse backend
│   ├── screenshot_capture.py        # Screen capture (backend selection)
│   ├── macos_screenshot_backend.py  # Native macOS Quartz screenshot backend
│   ├── clipboard_capture.py         # Clipboard monitoring (backend selection)
│   ├── macos_clipboard_backend.py   # Native macOS NSPasteboard backend
│   ├── window_capture.py            # Active window tracking (backend selection)
│   ├── macos_window_backend.py      # Native macOS NSWorkspace+CGWindowList backend
│   ├── audio_capture.py             # Audio recording (backend selection)
│   └── macos_audio_backend.py       # Native macOS AVFoundation audio backend
├── transport/
│   ├── __init__.py                  # Plugin registry & auto-discovery
│   ├── base.py                      # BaseTransport abstract class
│   ├── email_transport.py           # SMTP with SSL/TLS
│   ├── http_transport.py            # HTTP POST/PUT
│   ├── ftp_transport.py             # FTP/FTPS upload
│   ├── telegram_transport.py        # Telegram Bot API
│   └── websocket_transport.py       # WebSocket with auto-reconnect
├── storage/
│   ├── __init__.py
│   ├── manager.py                   # Local filesystem with rotation
│   ├── sqlite_storage.py            # SQLite with batch tracking
│   └── fleet_storage.py             # Fleet management SQLite storage
├── fleet/
│   ├── __init__.py
│   ├── controller.py                # FleetController with persistence
│   ├── agent.py                     # FleetAgent with HTTP/WS transport
│   ├── run_agent.py                 # Agent entry point
│   └── auth.py                      # JWT authentication for fleet
├── pipeline/
│   ├── __init__.py
│   ├── core.py                      # Pipeline orchestrator
│   ├── base_middleware.py           # Middleware base class
│   ├── registry.py                  # Built-in middleware
│   └── context.py                   # Pipeline context
├── engine/
│   ├── __init__.py
│   ├── rule_engine.py               # Rule engine orchestrator
│   ├── rule_parser.py               # YAML rule parser
│   ├── evaluator.py                 # Condition evaluator
│   ├── actions.py                   # Action definitions
│   ├── event_bus.py                 # Event pub/sub bus
│   └── registry.py                  # Rule registry
├── biometrics/
│   ├── __init__.py
│   ├── collector.py                 # Keystroke timing collection
│   ├── analyzer.py                  # Statistical profile generation
│   ├── matcher.py                   # Profile similarity comparison
│   └── models.py                    # Data models
├── profiler/
│   ├── __init__.py
│   ├── tracker.py                   # App usage session tracking
│   ├── categorizer.py               # App-to-category mapping
│   ├── scorer.py                    # Productivity scoring
│   └── models.py                    # Data models
├── service/
│   ├── __init__.py
│   ├── manager.py                   # Cross-platform service manager
│   ├── linux_systemd.py             # systemd unit generation
│   ├── macos_launchd.py             # launchd plist generation
│   └── windows_service.py           # Windows service management
├── dashboard/
│   ├── __init__.py
│   ├── app.py                       # FastAPI application factory
│   ├── auth.py                      # Session-based auth + JWT
│   ├── run.py                       # Dashboard launcher
│   ├── routes/
│   │   ├── pages.py                 # HTML page routes
│   │   ├── api.py                   # REST API endpoints
│   │   ├── fleet_api.py             # Fleet management API
│   │   ├── fleet_ui.py              # Fleet UI pages
│   │   ├── fleet_dashboard_api.py   # Fleet dashboard data API
│   │   └── websocket.py             # WebSocket endpoint
│   ├── templates/
│   │   ├── base.html                # Base layout template
│   │   ├── dashboard.html           # Main dashboard
│   │   ├── analytics.html           # Analytics page
│   │   ├── captures.html            # Capture log viewer
│   │   ├── screenshots.html         # Screenshot gallery
│   │   ├── settings.html            # Settings management
│   │   ├── live.html                # Real-time activity feed
│   │   ├── login.html               # Login page
│   │   ├── landing.html             # Landing page
│   │   └── fleet/
│   │       ├── index.html           # Fleet management page
│   │       └── agent_details.html   # Agent details page
│   └── static/
│       ├── css/style.css            # Dashboard styling
│       └── js/
│           ├── app.js               # Common application logic
│           ├── dashboard.js         # Dashboard page logic
│           ├── analytics.js         # Analytics charts
│           ├── captures.js          # Captures viewer
│           ├── screenshots.js       # Screenshot gallery
│           ├── settings.js          # Settings page
│           ├── ws-client.js         # WebSocket client (real-time)
│           └── cmd-palette.js       # Command palette (Ctrl+K)
├── server/
│   └── run.py                       # E2E collector server
├── utils/
│   ├── __init__.py
│   ├── crypto.py                    # AES-256-CBC / E2E encryption
│   ├── compression.py               # ZIP and GZIP compression
│   ├── resilience.py                # Retry, circuit breaker, queue
│   ├── process.py                   # PID lock & graceful shutdown
│   ├── system_info.py               # Platform detection & system metadata
│   ├── logger_setup.py              # Rotating file + console logging
│   ├── dependency_check.py          # Auto-install missing packages
│   └── self_destruct.py             # Self-destruct / anti-forensics
├── tests/
│   ├── conftest.py                  # Pytest fixtures
│   ├── test_config.py               # Configuration tests
│   ├── test_storage.py              # Storage backend tests
│   ├── test_utils.py                # Utility tests
│   ├── test_integration.py          # End-to-end pipeline tests
│   ├── test_pipeline.py             # Pipeline middleware tests
│   ├── test_rules.py                # Rule engine tests
│   ├── test_biometrics.py           # Biometrics tests
│   ├── test_profiler.py             # App profiler tests
│   ├── test_service.py              # Service management tests
│   ├── test_dashboard.py            # Dashboard/API tests
│   ├── test_audio_capture.py        # Audio capture tests
│   ├── test_dependency_check.py     # Dependency checker tests
│   ├── test_self_destruct.py        # Self-destruct tests
│   ├── test_macos_keyboard_backend.py  # macOS keyboard backend tests
│   ├── test_macos_mouse_backend.py     # macOS mouse backend tests
│   ├── test_macos_screenshot_backend.py # macOS screenshot backend tests
│   ├── test_macos_clipboard_backend.py # macOS clipboard backend tests
│   ├── test_macos_window_backend.py    # macOS window backend tests
│   └── test_macos_audio_backend.py     # macOS audio backend tests
├── requirements.txt
└── README.md
```

---

## Requirements

**Python:** 3.10+

**Core dependencies:**

| Package | Version | Purpose |
|---------|---------|---------|
| `pynput` | >= 1.7.6 | Keyboard and mouse input listeners |
| `Pillow` | >= 10.0.0 | Screenshot capture |
| `pyyaml` | >= 6.0 | YAML configuration parsing |
| `cryptography` | >= 41.0.0 | AES-256 encryption, RSA keys |
| `pyperclip` | >= 1.8.2 | Clipboard monitoring |
| `requests` | >= 2.31.0 | HTTP transport, fleet agent |
| `fastapi` | >= 0.104.0 | Dashboard web UI |
| `uvicorn[standard]` | >= 0.24.0 | ASGI server |
| `jinja2` | >= 3.1.0 | HTML templates |
| `python-multipart` | >= 0.0.6 | Form data parsing |
| `psutil` | >= 5.9.0 | System metrics |
| `PyJWT` | >= 2.8.0 | JWT authentication |

**Optional dependencies:**

| Package | Version | Purpose | Install with |
|---------|---------|---------|--------------|
| `redis` | >= 5.0.0 | Redis transport | `pip install .[transports]` |
| `websockets` | >= 11.0 | WebSocket transport | `pip install .[transports]` |
| `sounddevice` | >= 0.4.6 | Audio recording | manual |
| `numpy` | >= 1.24.0 | Audio data handling | manual |
| `pyobjc-framework-Quartz` | >= 10.0 | Native macOS capture (macOS only) | manual |
| `pyobjc-framework-Cocoa` | >= 10.0 | Native macOS clipboard/window (macOS only) | manual |
| `pyobjc-framework-AVFoundation` | >= 10.0 | Native macOS audio (macOS only) | manual |

**Platform-specific:**

| Platform | Requirement |
|----------|-------------|
| Linux | `xdotool` for active window tracking (`sudo apt install xdotool`) |
| macOS | Accessibility permissions for keyboard/mouse monitoring. Install `pyobjc-framework-Quartz` for native Unicode keyboard capture. |
| Windows | No additional requirements |

---

## Installation

```bash
# Clone
git clone https://github.com/CreatorGhost/AdvanceKeyLogger.git
cd AdvanceKeyLogger

# Create virtual environment
python -m venv venv
source venv/bin/activate        # Linux/macOS
# venv\Scripts\activate         # Windows

# Install core dependencies
pip install -e .

# Install with optional transports (Redis, WebSocket)
pip install -e ".[transports]"

# Install with dev tools (pytest, ruff, mypy)
pip install -e ".[dev]"

# Install everything
pip install -e ".[all,dev]"
```

---

## Configuration

Configuration is loaded from YAML with optional environment variable overrides.

### Config file

Default config lives at `config/default_config.yaml`. Pass a custom config with `-c`:

```bash
python main.py -c /path/to/my_config.yaml
```

### Key configuration sections

**General:**
```yaml
general:
  report_interval: 30        # Seconds between batch reports
  data_dir: "./data"         # Local data storage directory
  log_level: "INFO"          # DEBUG, INFO, WARNING, ERROR
  log_file: "./logs/app.log" # Rotating log file path
  auto_install_deps: false   # Auto-install missing packages at startup
```

**Capture modules** (enable/disable individually):
```yaml
capture:
  keyboard:
    enabled: false
    include_key_up: false
    max_buffer: 10000
  mouse:
    enabled: false
    track_movement: false
  screenshot:
    enabled: true
    quality: 80
    format: "png"
    max_count: 100
  clipboard:
    enabled: false
    poll_interval: 5
    max_length: 10000
  window:
    enabled: false
    poll_interval: 2
  audio:
    enabled: false
    duration: 10
    sample_rate: 44100
    channels: 1
    max_count: 50
    interval: 300
```

**Storage:**
```yaml
storage:
  backend: "local"
  max_size_mb: 500
  rotation: true
  sqlite_path: "./data/captures.db"
```

**Transport** (choose one method: `email`, `http`, `ftp`, `telegram`, `websocket`):
```yaml
transport:
  method: "email"
  batch_size: 50
  queue_size: 1000
  failure_threshold: 5
  cooldown: 60

  websocket:
    url: ""
    reconnect_interval: 5
    heartbeat_interval: 30
    ssl: false
    verify_ssl: true
```

**Encryption & compression:**
```yaml
encryption:
  enabled: false
  mode: "symmetric"         # "symmetric" (AES-256-CBC) or "e2e"
  algorithm: "AES-256-CBC"
  key: ""
  e2e:
    server_public_key: ""    # Base64 X25519 public key from collector server
    key_store_path: "~/.advancekeylogger/keys/"
    pin_server_key: true

Note: E2E mode wraps each payload with an ephemeral X25519 key exchange and AES-256-GCM.

compression:
  enabled: true
  format: "zip"
```

**Self-destruct:**
```yaml
self_destruct:
  secure_wipe: false
  remove_program: false
  remove_service: true
```

### Environment variable overrides

Override any config value using the `KEYLOGGER_` prefix with double-underscore path separators:

```bash
export KEYLOGGER_CAPTURE__SCREENSHOT__QUALITY=95
export KEYLOGGER_TRANSPORT__METHOD=telegram
export KEYLOGGER_ENCRYPTION__ENABLED=true
```

---

## Usage

### Basic run

```bash
# Run with default config
python main.py

# Run with custom config
python main.py -c my_config.yaml

# Run with debug logging
python main.py --log-level DEBUG
```

### CLI options

| Flag | Description |
|------|-------------|
| `-c`, `--config` | Path to YAML configuration file |
| `--log-level` | Override log level (DEBUG, INFO, WARNING, ERROR) |
| `--list-captures` | List all registered capture plugins and exit |
| `--list-transports` | List all registered transport plugins and exit |
| `--self-destruct` | Remove all data, logs, and traces then exit |
| `--dry-run` | Capture data but do not send via transport |
| `--no-pid-lock` | Allow multiple instances (skip PID lock) |
| `--version` | Show version and exit |
| `service <action>` | Manage daemon mode (install/uninstall/start/stop/restart/status) |
| `dashboard` | Launch the web dashboard (default port 8050) |

### List available plugins

```bash
$ python main.py --list-captures
Registered capture plugins:
  - audio
  - clipboard
  - keyboard
  - mouse
  - screenshot
  - window

$ python main.py --list-transports
Registered transport plugins:
  - email
  - ftp
  - http
  - telegram
  - websocket
```

### Dry-run mode

```bash
python main.py --dry-run --log-level DEBUG
```

### Self-destruct

```bash
python main.py --self-destruct
# WARNING: This will permanently delete ALL data, logs, and traces.
# Type 'YES' to confirm: YES
# Self-destruct complete.
```

---

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=. --cov-report=term-missing

# Run specific test module
python -m pytest tests/test_audio_capture.py -v
python -m pytest tests/test_self_destruct.py -v
python -m pytest tests/test_dependency_check.py -v
```

**Test suite: 145 tests passing**

| Module | Test File | Tests |
|--------|-----------|-------|
| Configuration | [`tests/test_config.py`](tests/test_config.py) | 13 |
| Storage | [`tests/test_storage.py`](tests/test_storage.py) | 10 |
| Utilities (crypto, compression, PID, resilience) | [`tests/test_utils.py`](tests/test_utils.py) | 34 |
| Dashboard | [`tests/test_dashboard.py`](tests/test_dashboard.py) | 15 |
| Pipeline | [`tests/test_pipeline.py`](tests/test_pipeline.py) | 2 |
| Rule Engine | [`tests/test_rules.py`](tests/test_rules.py) | 3 |
| Biometrics | [`tests/test_biometrics.py`](tests/test_biometrics.py) | 3 |
| App Profiler | [`tests/test_profiler.py`](tests/test_profiler.py) | 3 |
| Service Management | [`tests/test_service.py`](tests/test_service.py) | 2 |
| Integration | [`tests/test_integration.py`](tests/test_integration.py) | 2 |
| Audio Capture | [`tests/test_audio_capture.py`](tests/test_audio_capture.py) | 7 |
| Dependency Checker | [`tests/test_dependency_check.py`](tests/test_dependency_check.py) | 9 |
| Self-Destruct | [`tests/test_self_destruct.py`](tests/test_self_destruct.py) | 14 |
| macOS Keyboard Backend | [`tests/test_macos_keyboard_backend.py`](tests/test_macos_keyboard_backend.py) | 18 |
| macOS Mouse Backend | [`tests/test_macos_mouse_backend.py`](tests/test_macos_mouse_backend.py) | 8 |
| macOS Screenshot Backend | [`tests/test_macos_screenshot_backend.py`](tests/test_macos_screenshot_backend.py) | 6 |
| macOS Clipboard Backend | [`tests/test_macos_clipboard_backend.py`](tests/test_macos_clipboard_backend.py) | 5 |
| macOS Window Backend | [`tests/test_macos_window_backend.py`](tests/test_macos_window_backend.py) | 8 |
| macOS Audio Backend | [`tests/test_macos_audio_backend.py`](tests/test_macos_audio_backend.py) | 4 |

---

## Development

```bash
# Lint
ruff check .

# Format
ruff format .

# Type check
mypy . --ignore-missing-imports

# Run tests
python -m pytest tests/ -v
```

### Adding a new capture module

1. Create `capture/your_capture.py`
2. Inherit from `BaseCapture` ([`capture/base.py`](capture/base.py))
3. Decorate with `@register_capture("your_name")`
4. Implement `start()`, `stop()`, `collect()`
5. Add config section under `capture.your_name` in YAML
6. Add module name to the auto-import list in [`capture/__init__.py`](capture/__init__.py)

### Adding a new transport module

1. Create `transport/your_transport.py`
2. Inherit from `BaseTransport` ([`transport/base.py`](transport/base.py))
3. Decorate with `@register_transport("your_name")`
4. Implement `connect()`, `send()`, `disconnect()`
5. Add config section under `transport.your_name` in YAML
6. Add module name to the auto-import list in [`transport/__init__.py`](transport/__init__.py)

---

## Disclaimer

This project is for **educational and authorized security research purposes only**. Do not use this software on systems you do not own or without explicit written permission from the system owner. Unauthorized monitoring of computer activity may violate local, state, and federal laws.

---

## E2E Collector Server

Client/Server separation is explicit:
- Client encrypts data with the server's public key and sends encrypted envelopes.
- Server holds the private key, receives envelopes, decrypts, and stores payloads.
- Crypto flow: X25519 key agreement → HKDF → AES-256-GCM.

Server config example lives in `config/server_config.example.yaml`.

### Generate server keys

```bash
python -m server.run --generate-keys --config config/server_config.example.yaml
```

This prints the base64 **server public key**. Put it in the client config:

```yaml
encryption:
  enabled: true
  mode: "e2e"
  e2e:
    server_public_key: "<paste key>"
    emit_client_keys: true
    client_keys_path: "~/.advancekeylogger/keys/client_keys.json"
```

### Run the server

```bash
python -m server.run --config config/server_config.example.yaml --host 0.0.0.0 --port 8000
```

The server exposes:
- `GET /health`
- `POST /ingest` (expects the envelope body from the client)
- `POST /register` (optional client registration when enabled)

### Auth & allowlist

Configure server authentication and allowed client keys:

```yaml
e2e_server:
  auth_tokens:
    - "change-me"
  registration_tokens:
    - "register-me"
  allowed_client_keys: []
  clients_file: "./server_data/clients.json"
```

### TLS

Provide `ssl_certfile` and `ssl_keyfile` in server config to enable HTTPS.
On the client, set `transport.http.verify` to `true` (default) or to a CA bundle path.

### HTTP health check

If you use HTTP transport, you can set `transport.http.healthcheck_url` to the server
`/health` endpoint. The client will skip sends while the server is unhealthy.

### Error recovery (pinned keys)

If the server key rotates or is lost, clients that pin the old key will reject it.
To recover:
1. Generate a new server keypair.
2. Update clients with the new `server_public_key`.
3. Remove the old pinned key file from the client key store:
   `~/.advancekeylogger/keys/server_public_key.key`
