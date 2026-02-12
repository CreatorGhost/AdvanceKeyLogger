# Identified Security and Reliability Issues

Comprehensive issue tracker from manual review + automated deep audit (5 parallel agents).
(Previously split across AUDIT_FINDINGS.md and CODEX_ISSUES.md — both merged here and deleted.)
Status: `OPEN` = not yet fixed | `FIXED` = resolved | `WONTFIX` = accepted risk

**Total: 161 issues** (17 critical, 53 high, 63 medium, 28 low)
**ALL 161 RESOLVED** (151 FIXED + 10 WONTFIX) — **0 remaining** (100% resolution rate)

---

## CRITICAL (9)

FILE: dashboard/routes/fleet_dashboard_api.py
LINES: 63
CATEGORY: 2 (Async/Sync)
SEVERITY: low
STATUS: WONTFIX
BUG: `async def list_agents()` calls sync `controller.get_all_agents()` blocking the entire FastAPI event loop.
FIX: Wrap in `await asyncio.to_thread(controller.get_all_agents)`.
REASON: Downgraded: verified as in-memory dict ops (microsecond cost); no lock or I/O involved.

FILE: dashboard/routes/fleet_dashboard_api.py
LINES: 74
CATEGORY: 2 (Async/Sync)
SEVERITY: low
STATUS: WONTFIX
BUG: `async def get_agent()` calls sync `controller.get_agent()` blocking event loop.
FIX: Wrap in `await asyncio.to_thread()`.
REASON: Downgraded: verified as in-memory dict ops (microsecond cost); no lock or I/O involved.

FILE: dashboard/routes/fleet_dashboard_api.py
LINES: 108
CATEGORY: 2 (Async/Sync)
SEVERITY: low
STATUS: WONTFIX
BUG: `async def get_agent_commands()` calls sync controller method blocking event loop.
FIX: Wrap in `await asyncio.to_thread()`.
REASON: Downgraded: verified as in-memory dict ops (microsecond cost); no lock or I/O involved.

FILE: dashboard/routes/fleet_api.py
LINES: 95
CATEGORY: 2 (Async/Sync)
SEVERITY: critical
STATUS: FIXED
BUG: `async def verify_signature()` calls sync `storage.get_agent()` which acquires threading.Lock + SQLite query -- blocks event loop.
FIX: Wrapped in `await asyncio.to_thread(controller.storage.get_agent, agent_id)`.

FILE: dashboard/routes/fleet_api.py
LINES: 295
CATEGORY: 2 (Async/Sync)
SEVERITY: critical
STATUS: FIXED
BUG: `async def heartbeat()` calls sync storage method blocking event loop.
FIX: Wrapped in `await asyncio.to_thread(controller.storage.get_agent, agent_id)`.

FILE: dashboard/routes/fleet_api.py
LINES: 387
CATEGORY: 2 (Async/Sync)
SEVERITY: critical
STATUS: FIXED
BUG: `async def command_response()` calls sync storage method blocking event loop.
FIX: Wrapped in `await asyncio.to_thread(controller.storage.get_agent, agent_id)`.

FILE: rootkit/native/linux/hidemod.c
LINES: 489, 562-571
CATEGORY: 11 (Dangling Pointer)
SEVERITY: critical
STATUS: FIXED
BUG: `module_prev` saved at hide time can become dangling if adjacent module unloads. Consistency check dereferences potentially-freed pointer -- undefined behavior / kernel panic.
FIX: Walk live modules list at unhide time, or register a module notifier to track changes.

FILE: rootkit/native/macos/interpose.c
LINES: 170-185
CATEGORY: 17 (Logic)
SEVERITY: critical
STATUS: FIXED
BUG: DYLD interpose tuples are self-referential: both `replacement` and `replacee` slots point to the same local symbol. DYLD sees "replace readdir with readdir" -- **directory hiding is a complete no-op**.
FIX: Renamed to `my_readdir`/`my_readdir_r`; tuples now correctly map replacement→libc original via extern decls.

FILE: stealth/detection_awareness.py
LINES: 356-381
CATEGORY: 17 (Destructive Side Effect)
SEVERITY: critical
STATUS: FIXED
BUG: `_check_debugger_macos` uses `PT_DENY_ATTACH` which is destructive -- permanently prevents any debugger from attaching on first clean scan. Runs every scan cycle.
FIX: Replaced with non-destructive sysctl `KERN_PROC`/`KERN_PROC_PID` reading `P_TRACED` flag via `kinfo_proc`.

FILE: stealth/core.py
LINES: 170-229
CATEGORY: 5 (Resilience)
SEVERITY: critical
STATUS: FIXED
BUG: No try/except isolation between subsystems in `activate()`. If any single subsystem raises (e.g., fs_cloak permissions error), ALL subsequent subsystems are skipped.
FIX: Each subsystem wrapped in `_safe_activate()` with try/except + error logging; failures isolated and counted.

FILE: c2/protocol.py
LINES: 139-141, 153-154
CATEGORY: 6 (Security)
SEVERITY: critical
STATUS: FIXED
BUG: Encryption silently falls back to plaintext when `cryptography` package is missing. Zero warning logged. System continues operating completely unencrypted.
FIX: Now raises `ImportError` with critical log when key configured but package missing; refuses plaintext.

FILE: transport/failover.py, c2_dns_transport.py, c2_https_transport.py
LINES: 61, 39, 36
CATEGORY: 5 (Contract)
SEVERITY: critical
STATUS: FIXED
BUG: `connect()` returns `bool` violating `BaseTransport.connect() -> None` contract. DNS/HTTPS `send()` uses `if not self.connect()` which will ALWAYS return False if fixed to None.
FIX: All three changed to `-> None` with exceptions on failure; added `try_connect() -> bool` helper; `send()` uses try/except for auto-connect.

---

## HIGH (35)

FILE: server/data_bridge.py
LINES: 54-60
CATEGORY: 1 (Resource Leak)
SEVERITY: high
STATUS: FIXED
BUG: SQLite connection leaks if `_create_tables()` raises in `__init__` -- caller never gets instance, `close()` never called.
FIX: Added try/except in `__init__` that calls `self._conn.close()` before re-raising.

FILE: storage/sqlite_storage.py
LINES: 31-38
CATEGORY: 1 (Resource Leak)
SEVERITY: high
STATUS: FIXED
BUG: Same pattern -- `sqlite3.connect()` then `_create_tables()`, conn leaks on exception.
FIX: Added try/except in `__init__` that calls `self._conn.close()` before re-raising.

FILE: dashboard/routes/api.py
LINES: 83-91
CATEGORY: 2 (Async/Sync)
SEVERITY: high
STATUS: FIXED
BUG: `async def system_status()` creates new SQLiteStorage connection + queries synchronously on event loop.
FIX: Refactored to reuse `app.state.sqlite_storage` and offload all queries via `asyncio.to_thread()`.

FILE: dashboard/routes/api.py
LINES: 131-158
CATEGORY: 2 (Async/Sync)
SEVERITY: high
STATUS: FIXED
BUG: `async def list_captures()` sync SQLite queries on event loop.
FIX: Refactored to reuse `app.state.sqlite_storage` and offload via `asyncio.to_thread(_fetch_captures)`.

FILE: dashboard/routes/api.py
LINES: 244-259
CATEGORY: 2 (Async/Sync)
SEVERITY: high
STATUS: FIXED
BUG: `async def activity_data()` sync SQLite query with 10k row limit on event loop.
FIX: Refactored to reuse `app.state.sqlite_storage` and offload via `asyncio.to_thread(_build_heatmap)`.

FILE: dashboard/routes/api.py
LINES: 280-289
CATEGORY: 2 (Async/Sync)
SEVERITY: high
STATUS: FIXED
BUG: `async def analytics_summary()` sync SQLite queries on event loop.
FIX: Refactored to reuse `app.state.sqlite_storage` and offload via `asyncio.to_thread(_build_summary)`.

FILE: fleet/agent.py
LINES: 198-208
CATEGORY: 2 (Async/Sync)
SEVERITY: high
STATUS: FIXED
BUG: `_heartbeat_loop` calls blocking psutil disk/CPU directly on event loop.
FIX: Wrap `_get_system_metrics()` in `await loop.run_in_executor(None, ...)`.

FILE: dashboard/routes/websocket.py
LINES: 399-403
CATEGORY: 2 (Async/Sync)
SEVERITY: high
STATUS: FIXED
BUG: `_process_dashboard_command` directly calls blocking psutil metrics functions; hangs entire WebSocket server.
FIX: Offload to `await asyncio.to_thread(...)`.

FILE: agent_controller.py
LINES: 483-515
CATEGORY: 2 (Async/Sync)
SEVERITY: high
STATUS: FIXED
BUG: `_process_commands` loop calls blocking `transport.send(...)` stalling controller event loop.
FIX: Offloaded to `await loop.run_in_executor(None, transport.send, message.to_bytes())`.

FILE: capture/macos_audio_backend.py
LINES: 104
CATEGORY: 2 (Async/Sync)
SEVERITY: high
STATUS: FIXED
BUG: `record` method uses `time.sleep(duration)` blocking entire thread for seconds/minutes.
FIX: Use `threading.Event().wait(timeout=duration)` or dedicated thread.

FILE: dashboard/routes/pages.py
LINES: 21+
CATEGORY: 3 (Uninitialized State)
SEVERITY: high
STATUS: FIXED
BUG: Direct `app.state.templates` access without `getattr` guard -- `AttributeError` if unset.
FIX: Use `getattr(..., None)` + HTTP 503.

FILE: dashboard/routes/fleet_ui.py
LINES: 14, 31
CATEGORY: 3 (Uninitialized State)
SEVERITY: high
STATUS: FIXED
BUG: Same direct `app.state.templates` access without fallback.
FIX: Same.

FILE: config/settings.py
LINES: 136
CATEGORY: 6 (Sensitive Data)
SEVERITY: high
STATUS: FIXED
BUG: Env overrides log secret values in plaintext (e.g., `SVC_FLEET__AUTH__JWT_SECRET=actual_secret`).
FIX: Redact values for keys containing "secret", "password", "key", "token".

FILE: fleet/auth.py
LINES: 108, 111
CATEGORY: 6 (Sensitive Data)
SEVERITY: high
STATUS: FIXED
BUG: JWT error messages may leak token content via `f"Invalid token: {e}"`.
FIX: Log generic message at warning; detail at DEBUG only.

FILE: sync/engine.py
LINES: 147-151
CATEGORY: 11 (Stale Reference)
SEVERITY: high
STATUS: FIXED
BUG: Caches private `sqlite_store._conn`; becomes stale if store closes its connection.
FIX: Use connection factory or public `get_connection()` method.

FILE: transport/failover.py
LINES: 99-114
CATEGORY: 13 (Failover)
SEVERITY: high
STATUS: FIXED
BUG: Fallback success doesn't reset `_primary_failed_at`; primary suppressed for full 5 minutes after transient 1-second failure.
FIX: Fallback success now resets `_primary_failed_at = now` so primary is retried sooner.

FILE: tests/test_stealth.py
LINES: 661-672
CATEGORY: 12 (Test Isolation)
SEVERITY: high
STATUS: FIXED
BUG: `test_rename_env_vars` renames ALL `KEYLOGGER_*` env vars but only restores the test one -- leaks renames to subsequent tests.
FIX: Save full `os.environ` snapshot or use `mock.patch.dict`.

FILE: c2/dns_tunnel.py
LINES: 117-128
CATEGORY: 14 (Parser Safety)
SEVERITY: high
STATUS: FIXED
BUG: QNAME-skipping loop: `offset += data[offset] + 1` can overshoot buffer on truncated/malicious data. No bounds check before advance.
FIX: Added `label_len` bounds check before every advance; early return on truncated packets.

FILE: c2/dns_tunnel.py
LINES: 136-141
CATEGORY: 14 (Parser Safety)
SEVERITY: high
STATUS: FIXED
BUG: Answer NAME label parsing: `offset += data[offset] + 1` in while loop can overshoot buffer. Post-loop `offset += 1` executes even when past buffer end.
FIX: Added `label_len` bounds check in answer NAME loop; guarded post-loop increment.

FILE: c2/dns_tunnel.py
LINES: 86-96
CATEGORY: 14 (Protocol)
SEVERITY: high
STATUS: FIXED
BUG: Labels exceeding 63 bytes are silently truncated with only a warning -- sends query to wrong domain, causes silent data loss.
FIX: Raise ValueError instead of truncating; validate `self._domain` at init time.

FILE: c2/dns_tunnel.py
LINES: 354-374
CATEGORY: 10 (Protocol)
SEVERITY: high
STATUS: FIXED
BUG: `_send_chunked()` hardcodes 120-byte chunk size ignoring domain length -- messages silently dropped for domains > ~38 chars.
FIX: Compute max chunk size dynamically from domain suffix length, matching `exfiltrate()`.

FILE: c2/dns_tunnel.py
LINES: 440-450
CATEGORY: 4 (Cross-Platform)
SEVERITY: high
STATUS: FIXED
BUG: `_get_system_nameserver` only reads `/etc/resolv.conf` (Unix); falls back to hardcoded `8.8.8.8` on Windows -- DNS silently leaks to Google.
FIX: Add Windows registry query; return None/empty on failure instead of `8.8.8.8`.

FILE: dashboard/static/js/session-replay.js
LINES: 199-215
CATEGORY: 15 (Frontend)
SEVERITY: high
STATUS: FIXED
BUG: `prevFrame()`/`nextFrame()` update frameIndex and currentTime but never update eventIndex -- overlays (cursor, keystrokes, window title) desync from displayed frame.
FIX: Call `this.eventIndex = this._findEventAt(this.currentTime)` and re-apply recent events.

FILE: harvest/browser_creds.py
LINES: 468-473
CATEGORY: 16 (Harvest)
SEVERITY: high
STATUS: FIXED
BUG: Safari `_harvest_safari` uses `-d` flag on `security dump-keychain` which triggers per-entry macOS authorization dialog -- makes bulk extraction impractical.
FIX: Remove `-d` flag; retrieve metadata only; always set password to `"[keychain-protected]"`.

FILE: harvest/browser_creds.py
LINES: 414-417
CATEGORY: 6 (Sensitive Data)
SEVERITY: high
STATUS: FIXED
BUG: Firefox: when `_firefox_decrypt` returns None, inserts `"[encrypted:{enc_username[:20]}...]"` leaking base64 ciphertext fragments.
FIX: Replace with fixed sentinel `"[encrypted]"` with no ciphertext content.

FILE: harvest/browser_creds.py
LINES: 257-455
CATEGORY: 5 (Unchecked Returns)
SEVERITY: high
STATUS: FIXED
BUG: Extensive use of broad `except Exception:` blocks masks critical permission or file-locking failures during browser credential harvesting.
FIX: Catch specific exceptions (`PermissionError`, `sqlite3.OperationalError`) and log detailed error context.

FILE: rootkit/native/linux/hidemod.c
LINES: 48-53, 365-451
CATEGORY: 17 (Missing Feature)
SEVERITY: high
STATUS: FIXED
BUG: Missing `UNHIDE_PREFIX` ioctl case -- once a prefix is hidden, it can never be un-hidden without unloading the module.
FIX: Add case `UNHIDE_PREFIX` (cmd 6) mirroring UNHIDE_PID/UNHIDE_PORT pattern.

FILE: rootkit/native/linux/hidemod.c
LINES: 88, 98, 111
CATEGORY: 8 (Memory Ordering)
SEVERITY: high
STATUS: FIXED
BUG: Reader functions use `READ_ONCE` on counts but writer uses `smp_store_release`. `READ_ONCE` lacks acquire semantics; broken on ARM64 where reader can observe incremented count before array write.
FIX: Replace `READ_ONCE(hidden_*_count)` with `smp_load_acquire(&hidden_*_count)`.

FILE: transport/failover.py
LINES: 124-131
CATEGORY: 18 (Failover Cache)
SEVERITY: high
STATUS: FIXED
BUG: Primary transport not cached when lazily created in `_try_send` -- line 130 excludes primary from caching. New instance created and discarded every call.
FIX: Now caches to `self._primary` when `method == self._primary_method`; also added None check on transport creation.

FILE: harvest/browser_creds.py
LINES: 156
CATEGORY: 16 (Data Completeness)
SEVERITY: high
STATUS: FIXED
BUG: Chrome `Login Data` copied without WAL/SHM sidecar files -- recently saved passwords silently missing.
FIX: Now copies `-wal` and `-shm` sidecar files alongside main DB file.

FILE: harvest/browser_data.py
LINES: 46
CATEGORY: 16 (Data Completeness)
SEVERITY: high
STATUS: FIXED
BUG: Same for History, Cookies, WebData, places.sqlite, cookies.sqlite (6 databases affected).
FIX: Now copies `-wal` and `-shm` sidecar files alongside main DB file in `_safe_query_db()`.

FILE: harvest/keys.py
LINES: 344-348
CATEGORY: 16 (UX)
SEVERITY: high
STATUS: FIXED
BUG: WiFi macOS `security find-generic-password -w` for each WiFi SSID triggers macOS Keychain auth dialog per network -- same class as Safari bug.
FIX: Remove `-w` flag or skip password retrieval; note passwords require user authorization.

FILE: dashboard/static/js/captures.js
LINES: 50
CATEGORY: 6 (XSS)
SEVERITY: high
STATUS: FIXED
BUG: `item.capture_type` interpolated directly into innerHTML without `escapeHtml()`. Compromised agent can inject arbitrary HTML/JS into dashboard.
FIX: Applied `escapeHtml()` to `item.capture_type`, `item.status`, `item.id`, and `timestamp`.

FILE: dashboard/static/js/session-replay.js
LINES: 144-154
CATEGORY: 8 (Race Condition)
SEVERITY: high
STATUS: FIXED
BUG: `play()` has no guard against double-call. If called while already playing, creates second rAF loop running at double speed; the extra loop is uncancellable.
FIX: Add `if (this.playing) return;` guard at top of `play()`.

FILE: rootkit/native/linux/hidemod.c
LINES: 499, 543
CATEGORY: 17 (Module Lifecycle)
SEVERITY: high
STATUS: FIXED
BUG: `hide_module()` removes module from kernel list + deletes kobject, making `rmmod` impossible. The entire exit path (hook removal, device deregistration) is unreachable dead code.
FIX: Provide an alternative unhide mechanism (e.g., ioctl command, or magic signal) before supporting rmmod.

---

## MEDIUM (36)

FILE: rootkit/ioctl_bridge.py
LINES: 164-172
CATEGORY: 1 (Resource Leak)
SEVERITY: medium
STATUS: FIXED
BUG: `/dev/.null` fd opened via `os.open()` but `KernelBridge` has no `__enter__/__exit__` context manager.
FIX: Add context manager protocol or `__del__` safety net.

FILE: dashboard/routes/api.py
LINES: 83, 131, 247, 283
CATEGORY: 1 (Resource Leak)
SEVERITY: medium
STATUS: FIXED
BUG: Creates new `SQLiteStorage` connection per request instead of reusing `app.state.sqlite_storage`.
FIX: All 4 handlers refactored to reuse `app.state.sqlite_storage` with fallback to new instance only when not set.

FILE: dashboard/routes/api.py
LINES: 70-76
CATEGORY: 2 (Async/Sync)
SEVERITY: medium
STATUS: FIXED
BUG: Recursive `rglob("*")` filesystem scan in async handler blocks event loop.
FIX: Extracted to `_calc_storage()` helper and offloaded via `await asyncio.to_thread(_calc_storage)`.

FILE: c2/dns_tunnel.py
LINES: 273-372
CATEGORY: 2 (Async/Sync)
SEVERITY: medium
STATUS: FIXED
BUG: Uses synchronous `time.sleep()` for jitter delays within tunnel logic; blocks any event loop integrating this component.
FIX: Replace with `await asyncio.sleep()` or offload to background thread.

FILE: dashboard/routes/session_api.py
LINES: 150-152
CATEGORY: 3 (Uninitialized State)
SEVERITY: medium
STATUS: FIXED
BUG: `frames_dir` falls back to `Path.cwd()` allowing serving ANY file under working directory.
FIX: Raise HTTP 503 if `frames_dir` is None.

FILE: utils/system_info.py
LINES: 106
CATEGORY: 4 (Cross-Platform)
SEVERITY: medium
STATUS: FIXED
BUG: `psutil.disk_usage("/")` hardcodes Unix root path -- `ValueError` on Windows.
FIX: Use `os.path.splitdrive(os.getcwd())[0]` on Windows, `"/"` on Unix.

FILE: stealth/process_masking.py
LINES: 225
CATEGORY: 4 (Cross-Platform)
SEVERITY: medium
STATUS: WONTFIX
BUG: `ctypes.windll` in `_apply_console_title` -- no explicit platform guard in method body.
REASON: FALSE POSITIVE — call site is platform-gated (`if self._platform == "windows":`) and method body wraps in try/except.

FILE: stealth/fs_cloak.py
LINES: 207
CATEGORY: 4 (Cross-Platform)
SEVERITY: medium
STATUS: WONTFIX
BUG: `ctypes.windll` in `_hide_windows` -- no explicit platform guard in method body.
REASON: FALSE POSITIVE — `_hide_path` dispatches per-platform; `_hide_windows()` only called when `self._platform == "windows"`.

FILE: stealth/fs_cloak.py
LINES: 43-123
CATEGORY: 4 (Cross-Platform)
SEVERITY: medium
STATUS: WONTFIX
BUG: Hardcoded paths like `/tmp/.system.pid` are invalid on Windows; compromise cross-platform consistency.
REASON: FALSE POSITIVE — `_DEFAULT_PATHS` dict is keyed per-platform; Windows section uses `os.environ.get("LOCALAPPDATA",...)`.

FILE: harvest/keys.py
LINES: 370-375
CATEGORY: 5 (Unchecked Return)
SEVERITY: medium
STATUS: FIXED
BUG: `_wifi_windows` first `subprocess.run` returncode unchecked -- parses error output as profiles.
FIX: Add `if proc.returncode != 0: return results`.

FILE: pipeline/middleware/context_annotator.py
LINES: 44-51
CATEGORY: 5 (Unchecked Return)
SEVERITY: medium
STATUS: FIXED
BUG: Linux `xdotool` subprocess returncode unchecked -- returns empty string on failure.
FIX: Check returncode, return `"Unknown"` on failure.

FILE: pipeline/middleware/context_annotator.py
LINES: 65-72
CATEGORY: 5 (Unchecked Return)
SEVERITY: medium
STATUS: FIXED
BUG: macOS `osascript` subprocess returncode unchecked.
FIX: Same.

FILE: service/macos_launchd.py
LINES: 19
CATEGORY: 5 (Unchecked Return)
SEVERITY: medium
STATUS: FIXED
BUG: `launchctl load` return value completely ignored -- reports success even on failure.
FIX: Check returncode, return error message on failure.

FILE: stealth/detection_awareness.py
LINES: 331-507
CATEGORY: 5 (Silent Failure)
SEVERITY: medium
STATUS: FIXED
BUG: Broad exception swallowing in detection awareness prevents reporting of evasion failures, making subsystem brittle.
FIX: Log specific error details to internal audit system even when suppressing crash.

FILE: main.py
LINES: 548-549
CATEGORY: 6 (Sensitive Data)
SEVERITY: medium
STATUS: FIXED
BUG: E2E public keys logged at INFO level.
FIX: Log at DEBUG or log only truncated hash.

FILE: agent_controller.py
LINES: 494-515
CATEGORY: 8 (Thread Safety)
SEVERITY: medium
STATUS: FIXED
BUG: `send_command` modifies shared `self.commands` and `self.command_queues` without `self._lock`.
FIX: Added `threading.Lock` (`self._sync_lock`) for sync callers; entire `send_command` body wrapped in `with self._sync_lock:`.

FILE: stealth/image_scrubber.py
LINES: 42, 126
CATEGORY: 8 (Thread Safety)
SEVERITY: medium
STATUS: FIXED
BUG: `self._counter += 1` not thread-safe -- concurrent threads could get same counter.
FIX: Use `threading.Lock` or `itertools.count()`.

FILE: rootkit/native/macos/interpose.c
LINES: 241-245
CATEGORY: 8 (Thread Safety)
SEVERITY: medium
STATUS: FIXED
BUG: `interpose_hidden_count()` reads shared counters without lock or atomics.
FIX: Use `__atomic_load_n()` or lock `hide_mutex`.

FILE: stealth/network_normalizer.py
LINES: 118, 199
CATEGORY: 8 (Thread Safety)
SEVERITY: medium
STATUS: FIXED
BUG: `_dns_cache` check-then-set pattern without lock; concurrent threads can cause redundant DNS lookups.
FIX: Add `threading.Lock` around cache access.

FILE: stealth/network_normalizer.py
LINES: 72-88
CATEGORY: 8 (Thread Safety)
SEVERITY: medium
STATUS: FIXED
BUG: `TokenBucket.consume()` is not thread-safe; concurrent senders can both think they have enough tokens.
FIX: Add `threading.Lock` around token computation.

FILE: harvest/browser_data.py
LINES: 128-246
CATEGORY: 9 (Performance)
SEVERITY: medium
STATUS: FIXED
BUG: `_find_chrome_dbs()` scans same directories 5 times in one `harvest_all()`.
FIX: Scan once, cache the mapping.

FILE: harvest/browser_creds.py
LINES: 102-145, 528
CATEGORY: 9 (Performance)
SEVERITY: medium
STATUS: FIXED
BUG: `_get_chrome_profiles()` called twice per harvest+detect cycle.
FIX: Cache result at instance level.

FILE: c2/dns_tunnel.py
LINES: 337-352
CATEGORY: 10 (Protocol)
SEVERITY: medium
STATUS: FIXED
BUG: `_send_message` doesn't share `exfiltrate`'s dynamic size computation for chunk sizing.
FIX: Extract overhead calculation into shared helper.

FILE: c2/dns_tunnel.py
LINES: 283
CATEGORY: 10 (Protocol)
SEVERITY: medium
STATUS: FIXED
BUG: `poll_commands()` never validates total domain length against 253-byte limit.
FIX: Validate domain length before sending; reject if too long.

FILE: transport/failover.py
LINES: 107-118
CATEGORY: 13 (Failover)
SEVERITY: medium
STATUS: FIXED
BUG: No backoff when entire chain (primary + all fallbacks) fails -- enables retry storms.
FIX: Track consecutive total failures, apply exponential backoff.

FILE: tests/test_stealth.py
LINES: 243-263
CATEGORY: 12 (Test Isolation)
SEVERITY: medium
STATUS: FIXED
BUG: `test_apply_silent_mode` restores handlers but not root logger level/filters.
FIX: Save and restore `root.level` and `root.filters`.

FILE: transport/http_transport.py
LINES: 28
CATEGORY: 6 (TLS)
SEVERITY: medium
STATUS: FIXED
BUG: `verify: false` disables TLS certificate verification with no warning logged.
FIX: Log a warning when verification is disabled.

FILE: transport/websocket_transport.py
LINES: 62-69
CATEGORY: 6 (TLS)
SEVERITY: medium
STATUS: FIXED
BUG: SSL disabled by default; `verify_ssl: false` sets CERT_NONE with no warning.
FIX: Log warning when SSL disabled or CERT_NONE set.

FILE: transport/websocket_transport.py
LINES: 146-200
CATEGORY: 1 (Resource Leak)
SEVERITY: medium
STATUS: FIXED
BUG: WebSocketTransport thread loop lacks robust guaranteed cleanup on failure; can leak background threads and sockets on reload.
FIX: Ensure background thread is always joined in `finally` block or context manager.

FILE: harvest/browser_creds.py
LINES: 152; harvest/browser_data.py: 42
CATEGORY: 6 (Permissions)
SEVERITY: medium
STATUS: WONTFIX
BUG: Temp files for DB copies created with `NamedTemporaryFile(delete=False)` lack `0o600` permissions; may be world-readable.
REASON: FALSE POSITIVE — Python's `NamedTemporaryFile` uses `_mkstemp_inner()` which creates files with mode 0o600 by default.

FILE: harvest/browser_creds.py
LINES: 368-369; harvest/browser_data.py: 277-278
CATEGORY: 4 (Platform Path)
SEVERITY: medium
STATUS: FIXED
BUG: Missing Snap/Flatpak Firefox profile paths on Ubuntu 22.04+ (default snap install).
FIX: Add `~/snap/firefox/common/.mozilla/firefox` and `~/.var/app/org.mozilla.firefox/.mozilla/firefox`.

FILE: harvest/keys.py
LINES: 155-157
CATEGORY: 4 (Platform Path)
SEVERITY: medium
STATUS: FIXED
BUG: GCP credentials path `~/.config/gcloud/` doesn't exist on Windows (`%APPDATA%\gcloud\` is correct).
FIX: Add `os.environ.get("APPDATA", "") / "gcloud"` for Windows.

FILE: harvest/scheduler.py
LINES: 63-100
CATEGORY: 5 (Logic)
SEVERITY: medium
STATUS: FIXED
BUG: Change detection runs AFTER full harvest -- all temp file creation, DB copies, subprocess calls, and auth dialogs triggered every cycle even when data hasn't changed.
FIX: Check file modification times BEFORE calling `harvest_all()`.

FILE: rootkit/native/linux/hidemod.c
LINES: 499, 543
CATEGORY: 17 (Module Lifecycle)
SEVERITY: medium
STATUS: FIXED
BUG: Self-hide makes `rmmod` impossible; exit cleanup (hook removal, device deregistration) is unreachable dead code.
FIX: Provide alternative unhide mechanism (ioctl command or magic signal).

FILE: transport/failover.py
LINES: 61-72
CATEGORY: 5 (Contract)
SEVERITY: medium
STATUS: FIXED
BUG: `connect()` returns `bool` violating `BaseTransport.connect() -> None` contract; redundant `hasattr` check.
FIX: Changed to `-> None` with exceptions; added `try_connect() -> bool` helper. (Same as critical C12 fix.)

FILE: rootkit/manager.py
LINES: 157-170
CATEGORY: 17 (Logic)
SEVERITY: medium
STATUS: FIXED
BUG: `hide_self` doesn't check `hide_file_prefix` return values or track successful hides. Default prefixes never added to `_hidden_prefixes`. `uninstall()` never unhides prefixes.
FIX: Check return, log success/failure, append to `_hidden_prefixes` only on success.

---

## LOW (20)

FILE: harvest/keys.py
LINES: 380-383
CATEGORY: 5 (Unchecked Return)
SEVERITY: low
STATUS: FIXED
BUG: Per-profile `netsh` returncode unchecked.
FIX: Add `if pw_proc.returncode != 0: continue`.

FILE: rootkit/ioctl_bridge.py
LINES: 326-330
CATEGORY: 5 (Unchecked Return)
SEVERITY: low
STATUS: FIXED
BUG: `subprocess.run(["fltmc", ...])` returncode not checked for driver loaded status.
FIX: Check `result.returncode == 0`.

FILE: rootkit/ioctl_bridge.py
LINES: 349
CATEGORY: 4 (Cross-Platform)
SEVERITY: low
STATUS: WONTFIX
BUG: `_windows_hide_prefix` accesses `ctypes.windll` without platform check -- `AttributeError` on Linux/macOS.
REASON: FALSE POSITIVE — line 349 doesn't exist (file is 281 lines); actual code at L248 is platform-gated at call site + wrapped in try/except.

FILE: dashboard/routes/api.py
LINES: 298
CATEGORY: 6 (Sensitive Data)
SEVERITY: low
STATUS: WONTFIX
BUG: `_SENSITIVE_CONFIG_KEYS` set incomplete -- missing `jwt_secret`, `dsn`, `credentials`.
REASON: FALSE POSITIVE — `jwt_secret` is already in the set; `dsn`/`credentials` keys don't exist in config schema; substring matching covers derivatives.

FILE: tests/test_stealth.py
LINES: 60-67
CATEGORY: 12 (Test Isolation)
SEVERITY: low
STATUS: FIXED
BUG: `test_overwrite_argv` only saves `sys.argv[0]`, not full list.
FIX: Save `list(sys.argv)`.

FILE: tests/test_stealth.py
LINES: 484-488
CATEGORY: 12 (Test Platform)
SEVERITY: low
STATUS: FIXED
BUG: `test_get_pid_path_default` hardcodes `"/tmp/.system-helper.pid"` -- fails on Windows.
FIX: Use `tempfile.gettempdir()` to derive expected path.

FILE: transport/failover.py
LINES: 59, 94-102
CATEGORY: 13 (Failover)
SEVERITY: low
STATUS: FIXED
BUG: `_primary_failed_at` set even when failover disabled; latent state can misfire if enabled later.
FIX: Only set when `has_fallbacks` is True.

FILE: transport/failover.py
LINES: 87
CATEGORY: 5 (Contract)
SEVERITY: low
STATUS: FIXED
BUG: `send()` narrows metadata to `dict[str,str]` vs base `dict[str,Any]` violating Liskov substitution.
FIX: Changed `send()` and `_try_send()` signatures to `dict[str, Any] | None`.

FILE: c2_dns_transport.py, c2_https_transport.py
LINES: 55, 50
CATEGORY: 5 (Contract)
SEVERITY: low
STATUS: FIXED
BUG: Same metadata type narrowing in DNS and HTTPS covert transports.
FIX: Changed `send()` signatures to `dict[str, Any] | None`.

FILE: dashboard/static/js/session-replay.js
LINES: 463-472
CATEGORY: 15 (Frontend)
SEVERITY: low
STATUS: FIXED
BUG: `player.init()` returns Promise (async) but DOMContentLoaded handler doesn't handle rejection -- unhandled promise rejection on error.
FIX: Add `.catch(err => console.error('Replay init failed:', err))`.

FILE: dashboard/static/js (multiple files)
LINES: sessions.js:6-7, dashboard.js:6-7, captures.js:6, analytics.js:8, settings.js:12
CATEGORY: 15 (Frontend)
SEVERITY: low
STATUS: FIXED
BUG: ~20 async function calls in DOMContentLoaded handlers without `.catch()` -- unhandled promise rejections.
FIX: Add `.catch()` to all async calls from non-async contexts.

FILE: dashboard/static/js/ws-client.js
LINES: 182-186
CATEGORY: 15 (Memory Leak)
SEVERITY: low
STATUS: FIXED
BUG: `_statusInterval` set in `init()` but never cleared; no `destroy()` method on `LiveDashboard`.
FIX: Store interval ID and add `destroy()` with `clearInterval`.

FILE: dashboard/static/js/dashboard.js
LINES: 7
CATEGORY: 15 (Memory Leak)
SEVERITY: low
STATUS: FIXED
BUG: `setInterval(loadDashboardData, 30000)` interval ID discarded; can never be cancelled.
FIX: Store ID for cleanup.

FILE: rootkit/native/linux/hidemod.c
LINES: 411
CATEGORY: 17 (Kernel API)
SEVERITY: low
STATUS: FIXED
BUG: `strncpy` deprecated in Linux kernel; use `strscpy`.
FIX: Replace `strncpy` with `strscpy`.

FILE: rootkit/native/linux/hidemod.c
LINES: 186
CATEGORY: 17 (Kernel API)
SEVERITY: low
STATUS: FIXED
BUG: `FTRACE_OPS_FL_RECURSION` flag semantics differ pre/post Linux 5.11.
FIX: Add `#if` version check for 5.7-5.10 compatibility.

FILE: harvest/scheduler.py
LINES: 155-161
CATEGORY: 13 (Logic)
SEVERITY: low
STATUS: FIXED
BUG: No backoff on repeated periodic harvest failures; short interval causes log flooding.
FIX: Track consecutive failures and increase interval.

FILE: stealth/process_masking.py
LINES: 117, 158, 238
CATEGORY: 8 (Thread Safety)
SEVERITY: low
STATUS: FIXED
BUG: `_original_thread_names` dict mutated from multiple threads without lock.
FIX: Add `threading.Lock` around mutations.

---

---

## ADDITIONAL FINDINGS FROM AUDIT_FINDINGS.md (36 new, deduplicated)

### Additional Critical (5)

FILE: service/manager.py
LINES: 13-15
CATEGORY: 4 (Cross-Platform)
SEVERITY: critical
STATUS: FIXED
BUG: All three platform service managers imported unconditionally at module level -- crashes with `ImportError` on non-matching OS (e.g., `winreg` on Linux).
FIX: Use lazy imports inside platform-gated branches or `importlib.import_module()`.

FILE: harvest/browser_creds.py
LINES: 164-193
CATEGORY: 6 (Sensitive Data)
SEVERITY: critical
STATUS: FIXED
BUG: Decrypted browser passwords stored in plaintext `Credential` dataclass and returned via `to_dict()` -- any serialization/logging exposes cleartext passwords.
FIX: Encrypt password field immediately after decryption; never return plaintext in `to_dict()`.

FILE: harvest/keys.py
LINES: 96-357
CATEGORY: 6 (Sensitive Data)
SEVERITY: critical
STATUS: FIXED
BUG: SSH private keys, AWS credentials, GCP service account keys, Azure tokens, Git credentials, WiFi passwords -- all stored as plaintext strings in `HarvestedKey.content`.
FIX: Encrypt all harvested credential content immediately using E2E envelope encryption.

FILE: storage/fleet_storage.py
LINES: 576-577
CATEGORY: 6 (Sensitive Data)
SEVERITY: critical
STATUS: FIXED
BUG: When `cryptography` package unavailable, private keys stored in plaintext SQLite -- silent degradation to zero security.
FIX: Now raises `ImportError` refusing plaintext storage; decrypt path raises `ValueError` instead of returning raw key.

FILE: server/app.py
LINES: 81-173
CATEGORY: 2 (Async/Sync)
SEVERITY: critical
STATUS: FIXED
BUG: `ingest()` performs blocking file I/O, SQLite operations, `replay_cache.seen`, and `DataBridge` all on the async event loop.
FIX: `store_payload` offloaded via `asyncio.to_thread()`; DataBridge wrapped in `try/finally` and offloaded to thread.

### Additional High (16)

FILE: transport/ftp_transport.py
LINES: 31-44
CATEGORY: 1 (Resource Leak)
SEVERITY: high
STATUS: FIXED
BUG: FTP/FTP_TLS object created, then `connect()`/`login()`/`prot_p()`/`cwd()` can each throw -- socket leaked since no `try/finally`.
FIX: Wrapped in try/except that calls `ftp.close()` on partial connect failure before re-raising.

FILE: dashboard/auth.py
LINES: 180
CATEGORY: 2 (Async/Sync)
SEVERITY: high
STATUS: FIXED
BUG: `login()` performs CPU-intensive PBKDF2 with 480K iterations directly on event loop -- blocks ALL async handlers for hundreds of ms.
FIX: Offloaded `verify_password()` to `await asyncio.to_thread(verify_password, ...)`.

FILE: dashboard/app.py
LINES: 136-151
CATEGORY: 3 (Uninitialized State)
SEVERITY: high
STATUS: FIXED
BUG: When fleet init fails or is disabled, `fleet_controller`/`fleet_auth`/`fleet_storage` never set on `app.state`.
FIX: Explicitly set all three to `None` at top of lifespan before conditional block.

FILE: server/app.py
LINES: 60-77
CATEGORY: 2 (Async/Sync)
SEVERITY: high
STATUS: FIXED
BUG: `register_client()` calls `registry.register()` which takes `threading.Lock` and does file I/O in async handler.
FIX: Offloaded to `await asyncio.to_thread(registry.register, key_b64)`.

FILE: main.py
LINES: 329-333
CATEGORY: 5 (Unchecked Return)
SEVERITY: high
STATUS: WONTFIX
BUG: `transport.send()` may return `None` (no explicit return); treated as failure -- some transports don't return bool.
REASON: FALSE POSITIVE — all `send()` implementations return `bool`; `if success:` correctly treats both `False` and hypothetical `None` as failure.

FILE: fleet/agent.py
LINES: 158-168
CATEGORY: 5 (Unchecked Return)
SEVERITY: high
STATUS: FIXED
BUG: `_register()` doesn't validate `refresh_token` from response -- if `None`, subsequent token refresh silently fails.
FIX: Validate JSON response; warn if `refresh_token` missing.

FILE: harvest/browser_data.py
LINES: 317-331
CATEGORY: 6 (Sensitive Data)
SEVERITY: high
STATUS: FIXED
BUG: Cookie values (session tokens, auth cookies) returnable unredacted when `_include_cookie_values=True`.
FIX: Remove blanket flag; encrypt before returning; audit-log when enabled.

FILE: config/default_config.yaml
LINES: 294
CATEGORY: 6 (Security)
SEVERITY: high
STATUS: FIXED
BUG: Default JWT secret is known static string `"CHANGE_ME_IN_PRODUCTION"` with `allow_default_secret` bypass.
FIX: `FleetAuth.__init__` now validates against `_KNOWN_INSECURE_SECRETS` frozenset and raises `ValueError` unless `allow_default_secret=True` explicitly passed.

FILE: storage/fleet_storage.py
LINES: 615
CATEGORY: 6 (Sensitive Data)
SEVERITY: high
STATUS: FIXED
BUG: Failed decryption returns raw (potentially plaintext) key value; warning log includes exception with key fragments.
FIX: Now raises `ValueError` on decrypt failure; sanitized log message omits key details.

FILE: rootkit/native/linux/hidemod.c
LINES: 381-398
CATEGORY: 8 (Thread Safety)
SEVERITY: high
STATUS: FIXED
BUG: `UNHIDE_PID` swap-with-last: concurrent lock-free reader may observe stale/torn value. Comment claims "count only grows" but UNHIDE shrinks it.
FIX: Use sentinel values or switch to RCU.

FILE: rootkit/native/windows/minifilter.c
LINES: 261-274
CATEGORY: 8 (Thread Safety)
SEVERITY: high
STATUS: FIXED
BUG: `g_Data.ClientPort` written in `CommConnect`/`CommDisconnect` without synchronization -- torn pointer could crash `FltCloseClientPort`.
FIX: Use `InterlockedExchangePointer` or protect with `ExAcquireFastMutex`.

FILE: fleet/agent.py
LINES: 42-127
CATEGORY: 8 (Thread Safety)
SEVERITY: high
STATUS: FIXED
BUG: `requests.Session` shared between executor thread and main coroutine calling `session.close()` -- `Session` is not thread-safe.
FIX: Add `threading.Lock` or create new session per executor call.

FILE: rootkit/native/linux/hidemod.c
LINES: 131-141
CATEGORY: 11 (Dangling Pointer)
SEVERITY: high
STATUS: FIXED
BUG: `ksym_lookup` cached function pointer -- no NULL check at point of use; if address invalid, kernel oops.
FIX: Add NULL check in `lookup_name()` before dereference.

FILE: rootkit/native/windows/minifilter.c
LINES: 361-372
CATEGORY: 11 (Dangling Pointer)
SEVERITY: high
STATUS: FIXED
BUG: `FilterUnload()` doesn't NULL out handles after closing -- racing callbacks may use stale handles.
FIX: Set `ServerPort = NULL` and `FilterHandle = NULL` after closing; add unload-in-progress flag.

FILE: tests/test_stealth.py
LINES: 532-540
CATEGORY: 12 (Test Isolation)
SEVERITY: high
STATUS: FIXED
BUG: `test_install_uninstall` replaces `sys.excepthook` but doesn't verify restoration -- may remain mutated for subsequent tests.
FIX: Assert `sys.excepthook is original` after uninstall; force-restore in `finally`.

FILE: tests/test_fleet_comprehensive.py
LINES: 17
CATEGORY: 12 (Test Isolation)
SEVERITY: high
STATUS: FIXED
BUG: `DB_PATH = "./data/test_comprehensive_fleet.db"` fixed path -- parallel test runs collide; data corruption.
FIX: Use `tmp_path` fixture for unique temp DB per run.

FILE: transport/failover.py
LINES: 61-72
CATEGORY: 13 (Failover)
SEVERITY: high
STATUS: FIXED
BUG: `connect()` only attempts primary -- returns `False` without trying any fallback transports.
FIX: `connect()` now raises on failure (matching contract); added `try_connect() -> bool` helper. (Same as critical C12 fix.)

FILE: fleet/auth.py
LINES: 20-21
CATEGORY: 6 (Sensitive Data)
SEVERITY: high
STATUS: FIXED
BUG: JWT `secret_key` stored as plain public instance attribute -- accessible via `request.app.state.fleet_auth.secret_key`.
FIX: Name-mangled to `self.__secret_key`; exposed only via `_signing_key` property; `__repr__`/`__str__` redacted.

### Additional Medium (12)

FILE: main.py
LINES: 640-983
CATEGORY: 1 (Resource Leak)
SEVERITY: medium
STATUS: FIXED
BUG: `SQLiteStorage` + `transport` created in setup; if exception before main loop, neither `.close()` nor `.disconnect()` called.
FIX: Wrap in `try/finally` guaranteeing cleanup.

FILE: fleet/agent.py
LINES: 52-84
CATEGORY: 1 (Resource Leak)
SEVERITY: medium
STATUS: FIXED
BUG: `requests.Session()` in `__init__` but `session.close()` not in `finally` -- leaks if task cancellation raises.
FIX: Wrap `stop()` in `try/finally`.

FILE: crypto/keypair.py
LINES: 30-111
CATEGORY: 1 (Resource Leak)
SEVERITY: medium
STATUS: FIXED
BUG: Non-atomic multi-step key rotation: crash mid-write leaves files inconsistent.
FIX: Atomic write pattern (temp, fsync, rename).

FILE: transport/failover.py
LINES: 129-136
CATEGORY: 5 (Unchecked Return)
SEVERITY: medium
STATUS: FIXED
BUG: `create_transport_for_method()` may return `None`; code calls `.connect()`/`.send()` on it without check.
FIX: Added `if transport is None: return False` with warning log in `_try_send()`.

FILE: server/data_bridge.py
LINES: 145-177
CATEGORY: 5 (Silent Failure)
SEVERITY: medium
STATUS: FIXED
BUG: Silent data loss on commit failure -- `except Exception` swallows errors.
FIX: Log at warning; return failure indicator.

FILE: main.py
LINES: 908-913
CATEGORY: 5 (Unchecked Return)
SEVERITY: medium
STATUS: FIXED
BUG: `sqlite_store.insert()` unchecked -- data silently lost on DB error.
FIX: Wrap in try/except; queue items for transport on failure.

FILE: engine/actions.py
LINES: 97-103
CATEGORY: 5 (Unchecked Return)
SEVERITY: medium
STATUS: FIXED
BUG: `create_transport_for_method()` return used without None check.
FIX: Check `if transport is None` before `.connect()`/`.send()`.

FILE: rootkit/native/linux/hidemod.c
LINES: 490-504
CATEGORY: 8 (Thread Safety)
SEVERITY: medium
STATUS: FIXED
BUG: `module_hidden` plain `bool` written/read without barriers.
FIX: Use `WRITE_ONCE`/`READ_ONCE` or `atomic_t`.

FILE: rootkit/native/windows/minifilter.c
LINES: 324-330
CATEGORY: 8 (Thread Safety)
SEVERITY: medium
STATUS: FIXED
BUG: `CMD_GET_STATUS` reads `HiddenPrefixCount` outside mutex.
FIX: Wrap in `ExAcquireFastMutex`/`ExReleaseFastMutex`.

FILE: rootkit/native/windows/minifilter.c
LINES: 307-314
CATEGORY: 8 (Thread Safety)
SEVERITY: medium
STATUS: FIXED
BUG: Mixed mutex + `InterlockedIncrement` on same variable -- fragile correctness.
FIX: Use consistent strategy: plain increment under mutex.

FILE: capture/mouse_capture.py
LINES: 108-112
CATEGORY: 8 (Thread Safety)
SEVERITY: medium
STATUS: FIXED
BUG: `_last_move_ts` read/written in callback without lock.
FIX: Protect with `self._lock`.

FILE: capture/clipboard_capture.py
LINES: 109-110
CATEGORY: 8 (Thread Safety)
SEVERITY: medium
STATUS: FIXED
BUG: `_last_value` read/written outside `self._lock` -- fragile thread-confinement.
FIX: Move access inside existing `self._lock` block.

FILE: main.py
LINES: 688-695, 953-957
CATEGORY: 8 (Thread Safety)
SEVERITY: medium
STATUS: FIXED
BUG: `fleet_agent.running = False` from main thread while coroutines read it in background thread.
FIX: Use `threading.Event` for shutdown signal.

FILE: recording/session_recorder.py
LINES: 296-308
CATEGORY: 5 (Logic)
SEVERITY: medium
STATUS: FIXED
BUG: `_flush_events()` catches all exceptions; persistent DB errors retry forever.
FIX: Add retry counter; after N failures, stop session or escalate.

FILE: transport/failover.py
LINES: 140-142
CATEGORY: 13 (Failover)
SEVERITY: medium
STATUS: FIXED
BUG: Transport instantiation errors silently swallowed at `debug` level -- misconfigured fallbacks invisible.
FIX: Log at `warning`; cache failures to avoid re-creating broken transports.

FILE: utils/resilience.py
LINES: 235-252
CATEGORY: 13 (Failover)
SEVERITY: medium
STATUS: FIXED
BUG: `CircuitBreaker.record_success()` transitions `HALF_OPEN -> CLOSED` but not `OPEN -> CLOSED` -- breaker stuck in OPEN.
FIX: Unconditionally set `state = CLOSED` on success; reset `_last_failure_time`.

FILE: tests/test_fleet_comprehensive.py
LINES: 36-37
CATEGORY: 12 (Test Isolation)
SEVERITY: medium
STATUS: FIXED
BUG: `app.dependency_overrides` set but never cleared -- persists if app reused.
STATUS: WONTFIX
REASON: FALSE POSITIVE — `app` object is local to the test fixture and gets garbage-collected; no cross-test leakage.

FILE: tests/test_fleet_comprehensive.py
LINES: 11
CATEGORY: 12 (Test Isolation)
SEVERITY: medium
STATUS: FIXED
BUG: `sys.path.insert(0, ...)` at module level permanently modifies import resolution.
FIX: Configure project via `pyproject.toml` / `conftest.py` instead.

### Additional Low (3)

FILE: dashboard/routes/session_api.py
LINES: 136-140
CATEGORY: 9 (Performance)
SEVERITY: low
STATUS: FIXED
BUG: O(n) linear search through frames list per request.
FIX: Dict keyed by frame ID, or `get_frame_by_id()` in store.

FILE: rootkit/native/linux/hidemod.c
LINES: 220-221
CATEGORY: 11 (Dangling Pointer)
SEVERITY: low
STATUS: FIXED
BUG: `orig_getdents64`/`orig_tcp4_seq_show` called without NULL guard (mitigated by install_hook check).
FIX: Add NULL check as defense-in-depth.

FILE: .gitignore
LINES: 1-9
CATEGORY: 6 (Sensitive Data)
SEVERITY: low
STATUS: FIXED
BUG: Missing `*.p12`, `*.pfx`, `*.jks`, `id_rsa*`, `secrets.yaml`, `credentials.*` patterns.
FIX: Add these patterns.

FILE: dashboard/routes/api.py
LINES: 169-190
CATEGORY: 2 (Async/Sync)
SEVERITY: low
STATUS: FIXED
BUG: `list_screenshots()` does filesystem glob/stat in async handler.
FIX: Offload to `asyncio.to_thread()`.

### Additional Medium (missed in initial pass, now included)

FILE: rootkit/native/macos/interpose.c
LINES: 106-107
CATEGORY: 11 (Stale Pointer)
SEVERITY: medium
STATUS: FIXED
BUG: `orig_readdir`/`orig_readdir_r` cached from `dlsym` -- could dangle if library unloaded.
FIX: Document assumption that libc symbols remain valid for process lifetime; add `__attribute__((destructor))` NULL guard.

FILE: c2/dns_tunnel.py
LINES: 236-254
CATEGORY: 10 (Protocol)
SEVERITY: medium
STATUS: FIXED
BUG: Suffix overhead assumes max 4-digit chunk counts; 10000+ chunks cause mid-sequence domain overflow (label > 63 bytes).
FIX: Use `len(str(len(chunks)))` instead of hardcoded 4.

---

## ADDITIONAL FINDINGS FROM CODEX_ISSUES.md (13 new, 2 duplicates excluded)

### Codex Medium (7)

FILE: server/app.py
LINES: 167-173
CATEGORY: 1 (Resource Leak)
SEVERITY: medium
STATUS: FIXED
BUG: `DataBridge` is closed only on the success path; an exception during ingest leaves the SQLite connection open.
FIX: Bridge usage wrapped in `try/finally` that always calls `bridge.close()`, offloaded to thread pool.

FILE: stealth/image_scrubber.py
LINES: 137-155
CATEGORY: 1 (Resource Leak)
SEVERITY: medium
STATUS: FIXED
BUG: `Image.open()` handle is never closed -- leaks file descriptors over time.
FIX: Use `with Image.open(path) as img:` or ensure `img.close()` in `finally`.

FILE: utils/process.py
LINES: 40-43
CATEGORY: 4 (Cross-Platform)
SEVERITY: medium
STATUS: FIXED
BUG: Default PID file path hardcoded to `/tmp/...` which fails on Windows.
FIX: Use `tempfile.gettempdir()` or `Path.home()` for cross-platform temp.

FILE: utils/self_destruct.py
LINES: 78-83
CATEGORY: 4 (Cross-Platform)
SEVERITY: medium
STATUS: FIXED
BUG: `remove_pid_file()` hardcodes `/tmp/...` and fails on Windows.
FIX: Use `tempfile.gettempdir()` or mirror PIDLock default.

FILE: service/linux_systemd.py
LINES: 27-44
CATEGORY: 5 (Unchecked Return)
SEVERITY: medium
STATUS: FIXED
BUG: Start/stop/restart/uninstall paths call `systemctl` with `check=False` and ignore return codes.
FIX: Check `returncode` and surface failures to caller.

FILE: service/macos_launchd.py
LINES: 15-43
CATEGORY: 5 (Unchecked Return)
SEVERITY: medium
STATUS: FIXED
BUG: install/start/stop/restart/uninstall paths all ignore `launchctl` failures (broader than existing line 19-only finding).
FIX: Check `returncode` and return an error message when non-zero.

FILE: utils/redis_queue.py
LINES: 274-326
CATEGORY: 8 (Thread Safety)
SEVERITY: medium
STATUS: FIXED
BUG: `_connected`/`_loop` shared between main thread and background loop without synchronization.
FIX: Guard state with a lock or use thread-safe events to coordinate.

### Codex Low (6)

FILE: dashboard/routes/api.py
LINES: 197-229
CATEGORY: 2 (Async/Sync)
SEVERITY: low
STATUS: FIXED
BUG: `get_screenshot()` does synchronous filesystem resolution/existence checks inside an async handler.
FIX: Offload filesystem work to `asyncio.to_thread()` or make the endpoint synchronous.

FILE: dashboard/routes/session_api.py
LINES: 122-166
CATEGORY: 2 (Async/Sync)
SEVERITY: low
STATUS: FIXED
BUG: `get_frame()` performs synchronous filesystem checks in an async handler.
FIX: Offload to `asyncio.to_thread()` or make the endpoint synchronous.

FILE: dashboard/routes/api.py
LINES: 291-294
CATEGORY: 2 (Async/Sync)
SEVERITY: low
STATUS: FIXED
BUG: `analytics_summary()` uses synchronous `glob()`/`len(list(...))` in an async handler (filesystem scan, distinct from existing SQLite finding).
FIX: Offload filesystem scan to `asyncio.to_thread()`.

FILE: dashboard/routes/websocket.py
LINES: 187-215
CATEGORY: 2 (Async/Sync)
SEVERITY: low
STATUS: FIXED
BUG: `_validate_origin()` instantiates `Settings()` (file I/O) inside async WebSocket handlers.
FIX: Cache settings at startup or load via `asyncio.to_thread()`.

FILE: dashboard/routes/api.py
LINES: 301-313
CATEGORY: 2 (Async/Sync)
SEVERITY: low
STATUS: FIXED
BUG: `get_config()` loads `Settings()` (file I/O) in an async handler.
FIX: Use `app.state.config` or load via `asyncio.to_thread()`.

FILE: utils/redis_queue.py
LINES: 207-214
CATEGORY: 9 (Performance)
SEVERITY: low
STATUS: FIXED
BUG: `acknowledge()` scans the entire sorted set to find a message_id (O(n)).
FIX: Store message IDs separately or index them for O(1) deletion.

### Codex Low (continued)

FILE: rootkit/ioctl_bridge.py
LINES: 225-233
CATEGORY: 5 (Unchecked Return)
SEVERITY: low
STATUS: FIXED
BUG: `_check_windows_driver()` ignores `fltmc` returncode; failure vs empty output is indistinguishable.
FIX: Validate `returncode == 0` before parsing stdout.

---

## Summary

| Severity | Total | FIXED | WONTFIX | OPEN | Resolution Rate |
|----------|-------|-------|---------|------|-----------------|
| Critical | 17 | 14 | 3 | 0 | **100%** |
| High | 53 | 52 | 1 | 0 | **100%** |
| Medium | 63 | 56 | 4 | 0 | **100%** |
| Low | 28 | 26 | 2 | 0 | **100%** |
| **Total** | **161** | **151** | **10** | **0** | **100%** |

**All 161 issues resolved** (151 FIXED + 10 WONTFIX false positives). **0 remaining.**

## All Fixes Applied (Phases 1-9)

### Phase 1: False Positives Marked WONTFIX (10 issues)
- stealth/process_masking.py:225 — platform-gated at call site
- stealth/fs_cloak.py:207 — platform-gated at call site
- stealth/fs_cloak.py:43-123 — paths are per-platform in dict
- rootkit/ioctl_bridge.py:349 — Windows-only codepath
- harvest temp file permissions — NamedTemporaryFile uses 0o600 by default
- main.py:329-333 — transport.send() returns bool; falsy handling correct
- tests/test_fleet_comprehensive.py:36-37 — fixture-scoped app is GC'd
- dashboard/routes/api.py:298 — jwt_secret already in set; dsn/credentials not in schema
- fleet_dashboard_api.py C1-C3 — downgraded: in-memory dict ops, microsecond cost

### Phase 2: Critical Fixes (7 issues)
- C2 encryption silent plaintext fallback → raises ImportError with critical log
- Fleet storage plaintext key fallback → raises ImportError/ValueError
- Stealth activate() no subsystem isolation → _safe_activate() per subsystem
- PT_DENY_ATTACH destructive → sysctl KERN_PROC P_TRACED check
- macOS interpose tuples no-op → renamed my_readdir/my_readdir_r with correct tuple targets
- Transport connect() contract → all 3 transports -> None + try_connect()
- service/manager.py platform imports → lazy imports via importlib
- harvest/browser_creds.py + keys.py → SecureString wrapper (utils/secure_string.py)
- hidemod.c dangling module_prev → module notifier + safe list walk at unhide

### Phase 3: Kernel/Rootkit HIGH Fixes (8 issues)
- UNHIDE_PREFIX ioctl case added (cmd 6)
- smp_load_acquire on ARM64 readers (is_pid_hidden, is_port_hidden, is_prefix_hidden)
- UNHIDE_MODULE ioctl (cmd 7) for rmmod support
- smp_wmb() between swap and count decrement in UNHIDE_PID/PORT/PREFIX
- ksym_lookup NULL guard in lookup_name()
- minifilter: InterlockedExchangePointer for g_Data.ClientPort
- minifilter: NULL handles after FilterUnload close
- minifilter: CMD_GET_STATUS mutex + consistent increment strategy

### Phase 4: Dashboard/Frontend HIGH Fixes (7 issues)
- pages.py + fleet_ui.py: getattr guard + HTTP 503 fallback (12 handlers)
- dashboard/app.py: fleet_auth/fleet_storage set to None in error path
- session-replay.js: eventIndex updated in prevFrame/nextFrame
- session-replay.js: play() double-call guard
- config/settings.py: env override secret redaction with _SENSITIVE_PATTERNS

### Phase 5: DNS/Protocol HIGH Fixes (4 issues)
- Labels >63 bytes raise ValueError + domain validation at __init__
- _send_chunked() uses dynamic _compute_max_chunk_bytes() shared helper
- _get_system_nameserver() Windows registry query + warning on fallback
- poll_commands() 253-byte domain validation + dynamic suffix overhead

### Phase 6: Remaining HIGH Fixes (10 issues)
- fleet/agent.py psutil → run_in_executor
- websocket.py psutil → asyncio.to_thread
- fleet/auth.py JWT error → generic warning + DEBUG detail
- sync/engine.py → get_connection() public method
- test_rename_env_vars → full os.environ save/restore
- Firefox ciphertext leak → "[encrypted]" sentinel
- Safari/WiFi Keychain → removed -d/-w flags
- fleet/agent.py refresh_token validation + Session threading.Lock
- Test isolation: sys.excepthook restore + tempfile DB path

### Phase 7: Medium Fixes (53 issues)
- Thread safety: itertools.count(), TokenBucket lock, DNS cache lock, interpose atomics, mouse/clipboard locks, fleet_agent shutdown Event, redis_queue Event
- Resource leaks: KernelBridge context manager, main.py try/finally, session.close(), atomic key rotation, websocket thread join, Image.open context
- Unchecked returns: netsh, xdotool, osascript, launchctl, systemctl, sqlite_store.insert, transport None check
- Cross-platform: disk_usage Path.home().anchor, PID file tempfile.gettempdir()
- Failover: exponential backoff, warning-level logging, CircuitBreaker OPEN→CLOSED, TLS warnings
- Misc: session_api 503, detection_awareness logging, E2E key DEBUG level, Chrome profile caching, Firefox Snap/Flatpak paths, GCP Windows path, harvest scheduler mtime pre-check, rootkit manager return checks, data_bridge commit logging, session_recorder retry cap

### Phase 8: Low Fixes (24 issues)
- Frontend JS: .catch() on all async DOMContentLoaded calls, destroy() on LiveDashboard, stored interval IDs
- Kernel: strscpy, FTRACE_OPS_FL_RECURSION version check, orig_getdents64/orig_tcp4_seq_show NULL guards
- Async offload: list_screenshots, get_screenshot, get_config, get_frame, _validate_origin cached settings
- Tests: full sys.argv save/restore, tempfile-based pid path assertion
- Misc: .gitignore patterns, harvest failure backoff, Redis acknowledge O(1) index, fltmc returncode check
- failover.py _primary_failed_at guard, process_masking _original_thread_names lock

### Phase 9: Advanced Features (7 new capabilities)
- **Domain Fronting** (`c2/domain_fronting.py`): CDN-routed C2 with SNI masking + 3 provider presets
- **Process Hollowing** (`stealth/process_hollowing.py`): Windows payload injection into legitimate processes
- **ETW Evasion** (`stealth/etw_evasion.py`): EtwEventWrite in-memory patching on Windows
- **DNS-over-HTTPS** (DoH): Cloudflare/Google DoH in `c2/dns_tunnel.py`
- **Encrypted In-Memory Store** (`utils/secure_string.py`): SecureString wrapper for credentials
- **Anti-Hooking Detection**: API prologue comparison + LD_PRELOAD/DYLD checks
- **Beacon Jitter** (`c2/protocol.py`): Gaussian-distributed C2 intervals with time-of-day awareness
