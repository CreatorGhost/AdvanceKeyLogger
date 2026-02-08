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
  - [Resilience Patterns](#14-resilience-patterns)
  - [Process Management](#15-process-management)
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
| **Transport** | Email (SMTP), HTTP (POST/PUT), FTP/FTPS, Telegram Bot API |
| **Storage** | Local filesystem with rotation, SQLite with batch tracking |
| **Security** | AES-256-CBC encryption, PBKDF2 key derivation, ZIP/GZIP compression |
| **Resilience** | Retry with exponential backoff, circuit breaker, transport queue |
| **Pipeline** | Configurable middleware chain (dedup, rate-limit, enrich, route, truncate) |
| **Rule Engine** | YAML-based conditional rules with pattern matching and actions |
| **Biometrics** | Keystroke timing analysis, user profiling, profile matching |
| **Profiler** | App usage tracking, categorization, productivity scoring |
| **Service** | Cross-platform daemon mode (systemd, launchd, Windows Service) |
| **Anti-Forensics** | Self-destruct with secure wipe, trace removal, service cleanup |
| **Auto-Install** | Automatic dependency detection and installation at startup |
| **Dashboard** | FastAPI web UI with auth, analytics, screenshot viewer |
| **Operations** | PID lock, graceful shutdown, rotating logs, dry-run mode |
| **Architecture** | Plugin system with auto-discovery, YAML config with env var overrides |
| **Cross-platform** | Windows, Linux, macOS support |
| **Testing** | 145 passing tests across unit and integration suites |

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
- **Source:** [`capture/mouse_capture.py`](capture/mouse_capture.py)
- **Concepts:** OS-level mouse hooks via `pynput`, click vs movement tracking, callback integration with screenshot capture
- **Config:** `capture.mouse.enabled`, `track_movement`
- **Output:** `{"type": "mouse_click", "data": {"x": 500, "y": 300, "button": "left", "pressed": true}, ...}`

#### Screenshot Capture
- **Source:** [`capture/screenshot_capture.py`](capture/screenshot_capture.py)
- **Concepts:** On-demand screen capture with Pillow, file-based output with metadata, max-count enforcement
- **Config:** `capture.screenshot.enabled`, `quality`, `format`, `max_count`, `capture_region`
- **Output:** `{"type": "screenshot", "path": "./data/screenshots/screenshot_0001.png", "size": 45230, ...}`

#### Clipboard Capture
- **Source:** [`capture/clipboard_capture.py`](capture/clipboard_capture.py)
- **Concepts:** Polling-based change detection, content truncation, daemon thread with stop event
- **Config:** `capture.clipboard.enabled`, `poll_interval`, `max_length`
- **Output:** `{"type": "clipboard", "data": "copied text", ...}`

#### Window Capture
- **Source:** [`capture/window_capture.py`](capture/window_capture.py)
- **Concepts:** Platform-native APIs (ctypes on Windows, osascript on macOS, xdotool on Linux), change detection
- **Config:** `capture.window.enabled`, `poll_interval`
- **Output:** `{"type": "window", "data": "Visual Studio Code", ...}`

---

### 2. Audio Recording

Records audio clips at a configurable interval using `sounddevice` and saves WAV files to disk.

- **Source:** [`capture/audio_capture.py`](capture/audio_capture.py)
- **Test:** [`tests/test_audio_capture.py`](tests/test_audio_capture.py)
- **Concepts:** Daemon thread for periodic recording, `sounddevice.rec()` + `wave` stdlib for WAV output, graceful import with `SOUNDDEVICE_AVAILABLE` flag, thread-safe buffer, max-count enforcement
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

---

### 4. Storage Backends

#### Local Filesystem
- **Source:** [`storage/manager.py`](storage/manager.py)
- **Concepts:** File-based storage with capacity tracking, auto-rotation at 80% capacity, cleanup after transport

#### SQLite
- **Source:** [`storage/sqlite_storage.py`](storage/sqlite_storage.py)
- **Concepts:** Structured storage with WAL mode, batch retrieval of unsent records, mark-as-sent tracking, purge old data
- **Test:** [`tests/test_storage.py`](tests/test_storage.py)

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

Analyzes typing patterns to build user profiles based on keystroke timing.

- **Source:** [`biometrics/`](biometrics/)
  - [`biometrics/collector.py`](biometrics/collector.py) — Timing data collection (dwell time, flight time)
  - [`biometrics/analyzer.py`](biometrics/analyzer.py) — Statistical profile generation
  - [`biometrics/matcher.py`](biometrics/matcher.py) — Profile distance/similarity comparison
  - [`biometrics/models.py`](biometrics/models.py) — Data models
- **Test:** [`tests/test_biometrics.py`](tests/test_biometrics.py)
- **Concepts:** Dwell time (key hold duration), flight time (inter-key interval), statistical profiling, distance metrics

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

A FastAPI-based web dashboard for monitoring captures, viewing screenshots, and analytics.

- **Source:** [`dashboard/`](dashboard/)
  - [`dashboard/app.py`](dashboard/app.py) — FastAPI routes and API endpoints
  - [`dashboard/auth.py`](dashboard/auth.py) — Session-based authentication
  - [`dashboard/run.py`](dashboard/run.py) — Dashboard server launcher
- **Test:** [`tests/test_dashboard.py`](tests/test_dashboard.py)
- **Concepts:** FastAPI, Jinja2 templates, session auth, REST API endpoints, path traversal protection
- **Endpoints:** `/api/status`, `/api/captures`, `/api/screenshots`, `/api/analytics/activity`, `/api/analytics/summary`, `/api/config`, `/api/modules`

---

### 14. Resilience Patterns

- **Source:** [`utils/resilience.py`](utils/resilience.py)
- **Test:** [`tests/test_utils.py`](tests/test_utils.py) (TestRetry, TestCircuitBreaker, TestTransportQueue classes)
- **Concepts:**
  - **Retry with exponential backoff:** `@retry` decorator, configurable max attempts, specific exception types, `retry_on_false` mode
  - **Circuit breaker:** CLOSED -> OPEN -> HALF_OPEN state machine, configurable failure threshold and cooldown
  - **Transport queue:** Thread-safe deque with batch drain, requeue on failure, max-size enforcement

---

### 15. Process Management

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
| screenshot      | +-----------------+ | FTP/FTPS        |
| clipboard       |                     | Telegram        |
| window          | +-----------------+ +-----------------+
| audio           | |   Pipeline      |
+-----------------+ |   Middleware     | +-----------------+
                    +-----------------+ |   Dashboard     |
+-----------------+ | deduplicator    | |   (FastAPI)     |
|   Rule Engine   | | rate_limiter    | +-----------------+
|   (YAML rules)  | | router          |
+-----------------+ | truncator       | +-----------------+
                    | enricher        | |  Self-Destruct  |
+-----------------+ +-----------------+ |  (anti-forensic)|
|  Biometrics     |                     +-----------------+
|  (typing)       | +-----------------+
+-----------------+ |  App Profiler   | +-----------------+
                    |  (productivity) | |  Auto-Install   |
+-----------------+ +-----------------+ |  (dep checker)  |
|   Service       |                     +-----------------+
| systemd/launchd |
| Windows Service | +-----------------+
+-----------------+ |   Utilities     |
                    | crypto | zip    |
                    | retry  | PID    |
                    | logger | sysinfo|
                    +-----------------+
```

**Plugin System:** Capture and transport modules self-register via decorators (`@register_capture`, `@register_transport`). Modules are auto-imported at startup, and missing optional dependencies are handled gracefully.

---

## Project Structure

```
AdvanceKeyLogger/
├── main.py                          # Entry point & orchestration loop
├── config/
│   ├── settings.py                  # Settings singleton (YAML + env vars)
│   └── default_config.yaml          # Default configuration
├── capture/
│   ├── __init__.py                  # Plugin registry & auto-discovery
│   ├── base.py                      # BaseCapture abstract class
│   ├── keyboard_capture.py          # Keystroke monitoring (backend selection)
│   ├── macos_keyboard_backend.py    # Native macOS CGEventTap backend
│   ├── mouse_capture.py             # Mouse click/movement (pynput)
│   ├── screenshot_capture.py        # Screen capture (Pillow)
│   ├── clipboard_capture.py         # Clipboard polling (pyperclip)
│   ├── window_capture.py            # Active window tracking (platform-native)
│   └── audio_capture.py             # Audio recording (sounddevice)
├── transport/
│   ├── __init__.py                  # Plugin registry & auto-discovery
│   ├── base.py                      # BaseTransport abstract class
│   ├── email_transport.py           # SMTP with SSL/TLS
│   ├── http_transport.py            # HTTP POST/PUT
│   ├── ftp_transport.py             # FTP/FTPS upload
│   └── telegram_transport.py        # Telegram Bot API
├── storage/
│   ├── __init__.py
│   ├── manager.py                   # Local filesystem with rotation
│   └── sqlite_storage.py            # SQLite with batch tracking
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
│   ├── app.py                       # FastAPI web dashboard
│   ├── auth.py                      # Session-based auth
│   └── run.py                       # Dashboard launcher
├── utils/
│   ├── __init__.py
│   ├── crypto.py                    # AES-256-CBC encryption
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
│   └── test_macos_keyboard_backend.py  # macOS keyboard backend tests
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

**Optional dependencies:**

| Package | Version | Purpose |
|---------|---------|---------|
| `cryptography` | >= 41.0.0 | AES-256 encryption |
| `pyperclip` | >= 1.8.2 | Clipboard monitoring |
| `requests` | >= 2.31.0 | HTTP and Telegram transports |
| `sounddevice` | >= 0.4.6 | Audio recording |
| `numpy` | >= 1.24.0 | Audio data handling |
| `psutil` | >= 5.9.0 | System metrics |
| `pyobjc-framework-Quartz` | >= 10.0 | Native macOS keyboard capture (macOS only) |
| `fastapi` | >= 0.104.0 | Dashboard web UI |

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

# Install dependencies
pip install -r requirements.txt
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

**Transport** (choose one method):
```yaml
transport:
  method: "email"
  batch_size: 50
  queue_size: 1000
  failure_threshold: 5
  cooldown: 60
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
| macOS Keyboard Backend | [`tests/test_macos_keyboard_backend.py`](tests/test_macos_keyboard_backend.py) | 13 |

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
