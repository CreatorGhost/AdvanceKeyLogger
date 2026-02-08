# AdvanceKeyLogger

A modular Python input monitoring and screen capture tool built for **educational purposes** — learning about OS-level input APIs, networking, encryption, plugin architectures, and resilience patterns.

> **Disclaimer:** This project is for educational and authorized security research only. Do not use on systems you do not own or without explicit written permission. Unauthorized monitoring may violate local, state, and federal laws.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Capture Modules](#capture-modules)
- [Transport Modules](#transport-modules)
- [Storage Backends](#storage-backends)
- [Security](#security)
- [Resilience Patterns](#resilience-patterns)
- [Testing](#testing)
- [Development](#development)
- [License](#license)

---

## Features

| Category | Features |
|----------|----------|
| **Capture** | Keyboard, mouse, screenshot, clipboard, active window |
| **Transport** | Email (SMTP), HTTP (POST/PUT), FTP/FTPS, Telegram Bot API |
| **Storage** | Local filesystem with rotation, SQLite with batch tracking |
| **Security** | AES-256-CBC encryption, PBKDF2 key derivation, ZIP/GZIP compression |
| **Resilience** | Retry with exponential backoff, circuit breaker, transport queue |
| **Operations** | PID lock, graceful shutdown, rotating logs, dry-run mode |
| **Architecture** | Plugin system with auto-discovery, YAML config with env var overrides |
| **Cross-platform** | Windows, Linux, macOS support |
| **Testing** | 79 passing tests across unit and integration suites |

---

## Architecture

```
                    +------------------+
                    |     main.py      |
                    |  (orchestrator)  |
                    +--------+---------+
                             |
              +--------------+--------------+
              |              |              |
      +-------v------+ +----v-----+ +------v-------+
      |   Capture    | |  Storage | |  Transport   |
      |   Plugins    | | Backends | |   Plugins    |
      +--------------+ +----------+ +--------------+
      | keyboard     | | local FS | | email (SMTP) |
      | mouse        | | SQLite   | | HTTP         |
      | screenshot   | +----------+ | FTP/FTPS     |
      | clipboard    |              | Telegram     |
      | window       |              +--------------+
      +--------------+
              |                             |
      +-------v-----------------------------v-------+
      |              Utilities                      |
      | crypto | compression | resilience | logging |
      +--------------------------------------------|
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
│   ├── keyboard_capture.py          # Keystroke monitoring (pynput)
│   ├── mouse_capture.py             # Mouse click/movement (pynput)
│   ├── screenshot_capture.py        # Screen capture (Pillow)
│   ├── clipboard_capture.py         # Clipboard polling (pyperclip)
│   └── window_capture.py            # Active window tracking (platform-native)
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
├── utils/
│   ├── __init__.py
│   ├── crypto.py                    # AES-256-CBC encryption
│   ├── compression.py               # ZIP and GZIP compression
│   ├── resilience.py                # Retry, circuit breaker, queue
│   ├── process.py                   # PID lock & graceful shutdown
│   ├── system_info.py               # Platform detection & system metadata
│   └── logger_setup.py              # Rotating file + console logging
├── tests/
│   ├── conftest.py                  # Pytest fixtures
│   ├── test_config.py               # Configuration tests (13 tests)
│   ├── test_storage.py              # Storage backend tests (10 tests)
│   ├── test_utils.py                # Utility tests (54 tests)
│   └── test_integration.py          # End-to-end pipeline tests (2 tests)
├── requirements.txt
├── credentials.json.example
├── REVIEW.md                        # Code review & roadmap
├── IMPLEMENTATION_CHECKLIST.md      # Implementation tracking
└── IMPLEMENTATION_STATUS.md         # Current status & issue log
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

**Platform-specific:**

| Platform | Requirement |
|----------|-------------|
| Linux | `xdotool` for active window tracking (`sudo apt install xdotool`) |
| macOS | Accessibility permissions for keyboard/mouse monitoring |
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
```

**Capture modules** (enable/disable individually):
```yaml
capture:
  keyboard:
    enabled: false
    include_key_up: false    # Also capture key release events
    max_buffer: 10000        # Ring buffer size (prevents unbounded memory)
  mouse:
    enabled: false
    track_movement: false    # Track movement or clicks only
  screenshot:
    enabled: true
    quality: 80              # JPEG quality (1-100)
    format: "png"            # "png" or "jpg"
    max_count: 100           # Maximum screenshots before stopping
  clipboard:
    enabled: false
    poll_interval: 5         # Poll every N seconds
    max_length: 10000        # Truncate content beyond this (bytes)
  window:
    enabled: false
    poll_interval: 2         # Check active window every N seconds
```

**Storage:**
```yaml
storage:
  backend: "local"           # "local" (filesystem) or "sqlite"
  max_size_mb: 500           # Maximum storage capacity
  rotation: true             # Auto-delete oldest files at 80% capacity
  sqlite_path: "./data/captures.db"
```

**Transport** (choose one method):
```yaml
transport:
  method: "email"            # "email", "http", "ftp", "telegram"
  batch_size: 50             # Items per send batch
  queue_size: 1000           # Max queued items in memory
  failure_threshold: 5       # Circuit breaker opens after N failures
  cooldown: 60               # Seconds before circuit breaker retries
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
  format: "zip"              # "zip" or "gzip"
```

### Environment variable overrides

Override any config value using the `KEYLOGGER_` prefix with double-underscore path separators:

```bash
# Override capture.screenshot.quality
export KEYLOGGER_CAPTURE__SCREENSHOT__QUALITY=95

# Override transport method
export KEYLOGGER_TRANSPORT__METHOD=telegram

# Override encryption
export KEYLOGGER_ENCRYPTION__ENABLED=true
```

Environment variables take highest precedence over YAML config.

---

## Usage

### Basic run

```bash
# Run with default config (config/default_config.yaml)
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
| `--dry-run` | Capture data but do not send via transport |
| `--no-pid-lock` | Allow multiple instances (skip PID lock) |
| `--version` | Show version and exit |

### List available plugins

```bash
$ python main.py --list-captures
Available capture modules:
  - clipboard
  - keyboard
  - mouse
  - screenshot
  - window

$ python main.py --list-transports
Available transport modules:
  - email
  - ftp
  - http
  - telegram
```

### Dry-run mode

Captures data and processes it (storage, compression, encryption) without sending via transport. Useful for testing:

```bash
python main.py --dry-run --log-level DEBUG
```

---

## Capture Modules

All capture modules inherit from `BaseCapture` and implement `start()`, `stop()`, and `collect()`.

### Keyboard (`keyboard`)

Monitors keyboard input using `pynput.keyboard.Listener`.

- Buffers keystrokes with timestamps in a thread-safe ring buffer
- Handles special keys (shift, ctrl, enter, backspace) as readable `[name]` strings
- Optional key-up event tracking via `include_key_up` config
- Prevents unbounded memory with configurable `max_buffer` size

**Output format:**
```json
{"type": "keystroke", "data": "a", "timestamp": 1700000000.0}
{"type": "keystroke", "data": "[enter]", "timestamp": 1700000001.0}
```

### Mouse (`mouse`)

Monitors mouse events using `pynput.mouse.Listener`.

- Tracks click events (button, coordinates, press/release) by default
- Optional movement tracking via `track_movement` config
- Provides a click callback hook for integration with screenshots

**Output format:**
```json
{"type": "mouse_click", "data": {"x": 500, "y": 300, "button": "left", "pressed": true}, "timestamp": 1700000000.0}
```

### Screenshot (`screenshot`)

On-demand screen capture using `PIL.ImageGrab`.

- Saves to disk with zero-padded filenames (`screenshot_0001.png`)
- Configurable format (PNG/JPG) and JPEG quality
- Enforces `max_count` limit
- Returns file path and size metadata

**Output format:**
```json
{"type": "screenshot", "path": "./data/screenshots/screenshot_0001.png", "timestamp": 1700000000.0, "size": 45230}
```

### Clipboard (`clipboard`)

Polls system clipboard using `pyperclip`.

- Change detection — only records when content actually changes
- Configurable poll interval (default: 5 seconds)
- Truncates large content to `max_length` (default: 10KB)
- Clean shutdown via `threading.Event`
- Handles `PyperclipException` for headless environments

**Output format:**
```json
{"type": "clipboard", "data": "copied text content", "timestamp": 1700000000.0}
```

### Window (`window`)

Tracks active/focused window title changes using platform-native APIs.

| Platform | Method |
|----------|--------|
| Windows | `ctypes` — `GetForegroundWindow` / `GetWindowTextW` |
| Linux | `xdotool getactivewindow getwindowname` (subprocess) |
| macOS | `osascript` AppleScript (subprocess) |

- Change detection — only records when the active window changes
- Configurable poll interval (default: 2 seconds)
- Falls back to `"Unknown"` on any platform-specific error

**Output format:**
```json
{"type": "window", "data": "Visual Studio Code", "timestamp": 1700000000.0}
```

---

## Transport Modules

All transport modules inherit from `BaseTransport` and implement `connect()`, `send()`, and `disconnect()`.

### Email (`email`)

Sends reports via SMTP with optional attachments.

- SSL/TLS support (defaults to SMTP_SSL on port 465)
- Uses modern `email.message.EmailMessage`
- Retry with exponential backoff on `send()`
- Auto-reconnect on SMTP disconnection

**Config:**
```yaml
transport:
  method: "email"
  email:
    smtp_server: "smtp.gmail.com"
    smtp_port: 465
    use_ssl: true
    sender: "you@gmail.com"
    password: "app-password"
    recipient: "dest@example.com"
```

### HTTP (`http`)

Sends reports via HTTP POST or PUT.

- Uses `requests.Session` for connection pooling
- Configurable method, headers, and timeout
- Retry with exponential backoff

**Config:**
```yaml
transport:
  method: "http"
  http:
    url: "https://your-server.com/api/reports"
    method: "POST"
    headers:
      Authorization: "Bearer your-token"
```

### FTP (`ftp`)

Uploads reports to an FTP/FTPS server.

- TLS support via `FTP_TLS` with `prot_p()` data protection
- Auto-creates remote directory if missing
- Retry with exponential backoff

**Config:**
```yaml
transport:
  method: "ftp"
  ftp:
    host: "ftp.example.com"
    port: 21
    username: "user"
    password: "pass"
    remote_dir: "/uploads"
    use_tls: false
```

### Telegram (`telegram`)

Sends reports via Telegram Bot API.

- Validates bot token on connect via `getMe`
- Small text data (< 3.5KB) sent as message; larger data as document upload
- Enforces 50MB file size limit
- Checks both HTTP status and Telegram API `"ok"` field
- Retry with exponential backoff

**Config:**
```yaml
transport:
  method: "telegram"
  telegram:
    bot_token: "123456:ABC-DEF..."
    chat_id: "987654321"
```

---

## Storage Backends

### Local Filesystem (`local`)

- Stores files in `data_dir` with subdirectory support
- Tracks total storage size
- Auto-rotation: deletes oldest files when reaching 80% of `max_size_mb`
- Cleans up files after successful transport

### SQLite (`sqlite`)

- Structured storage in `captures.db`
- Schema: `id`, `type`, `data`, `file_path`, `file_size`, `timestamp`, `sent`
- Batch retrieval of unsent records (`get_pending`)
- Mark-as-sent tracking for reliable delivery
- Purge old sent records to reclaim space
- WAL mode for concurrent access

---

## Security

### Encryption

- **Algorithm:** AES-256-CBC with random IV per encryption
- **Key derivation:** PBKDF2-HMAC-SHA256 with 480,000 iterations
- **Format:** `[16-byte IV][ciphertext]` with PKCS7 padding
- **Key storage:** Base64-encoded in config (or auto-generated)

### Compression

- **ZIP:** Bundle multiple files (screenshots + data) into a single archive
- **GZIP:** Compress raw data with configurable compression level
- Compression ratio logging for monitoring

---

## Resilience Patterns

### Retry with Exponential Backoff

Applied to all transport `send()` methods via `@retry` decorator:

- Default: 3 attempts with base-2 backoff (waits 2s, 4s between retries)
- Catches transport-specific exceptions
- Optional `retry_on_false` mode for methods returning bool

### Circuit Breaker

Prevents hammering a broken transport endpoint:

- **CLOSED** (normal) — requests flow through
- **OPEN** (failure threshold hit) — all requests blocked
- **HALF_OPEN** (after cooldown) — single test request allowed
- Configurable `failure_threshold` (default: 5) and `cooldown` (default: 60s)

### Transport Queue

In-memory deque-based buffer:

- Batch drain with configurable `batch_size`
- Requeue on send failure (no data loss)
- Configurable max queue size (default: 1000)

---

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=. --cov-report=term-missing

# Run specific test module
python -m pytest tests/test_utils.py -v
python -m pytest tests/test_config.py -v
python -m pytest tests/test_storage.py -v
```

**Test suite: 79 tests passing**

| Module | Tests | Coverage |
|--------|-------|----------|
| Configuration (settings, YAML, env vars) | 13 | Settings singleton, dot-notation, validation |
| Storage (filesystem, SQLite) | 10 | Rotation, cleanup, batch ops, size tracking |
| Crypto (AES, key derivation) | 15 | Encrypt/decrypt roundtrip, wrong key, edge cases |
| Compression (ZIP, GZIP) | 7 | Roundtrip, missing files, ratio verification |
| System utilities | 7 | Platform detection, system info, PID lock |
| Resilience (retry, circuit breaker, queue) | 18 | All state transitions, backoff, batch drain |
| Integration (end-to-end pipeline) | 2 | Bundle + encrypt + cleanup, SQLite roundtrip |
| Graceful shutdown | 1 | Signal handling, flag state |

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
2. Inherit from `BaseCapture`
3. Decorate with `@register_capture("your_name")`
4. Implement `start()`, `stop()`, `collect()`
5. Add config section under `capture.your_name` in YAML
6. Add module name to the auto-import list in `capture/__init__.py`

### Adding a new transport module

1. Create `transport/your_transport.py`
2. Inherit from `BaseTransport`
3. Decorate with `@register_transport("your_name")`
4. Implement `connect()`, `send()`, `disconnect()`
5. Add config section under `transport.your_name` in YAML
6. Add module name to the auto-import list in `transport/__init__.py`

---

## Disclaimer

This project is for **educational and authorized security research purposes only**. Do not use this software on systems you do not own or without explicit written permission from the system owner. Unauthorized monitoring of computer activity may violate local, state, and federal laws.
