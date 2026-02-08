# Codebase Issue Scan Results

## 1. Missing `strict=True` on `zip()` (B905)

| File | Line | Code | Status |
|------|------|------|--------|
| `engine/evaluator.py` | 47 | `for op, comparator in zip(node.ops, node.comparators):` | FIXED |
| `storage/sqlite_storage.py` | 134 | `return [dict(zip(columns, row)) for row in cursor.fetchall()]` | FIXED |

## 2. Falsy-vs-None Checks (0 treated as falsy)

| File | Line | Code | Status |
|------|------|------|--------|
| `crypto/keypair.py` | 35 | `if rotation_hours:` → `if rotation_hours is not None:` | FIXED |
| `main.py` | 650 | `if profiler_emit_interval and ...` → `if profiler_emit_interval is not None and ...` | FIXED |

## 3. O(n^2) `list.pop(0)` and Redundant `stat()` Calls

| File | Line(s) | Issue | Status |
|------|---------|-------|--------|
| `storage/manager.py` | 68-79 | Cached stat results upfront, index-based iteration, OSError handling on `unlink()` | FIXED |
| `biometrics/collector.py` | 48 | Converted `_events` to `deque(maxlen=...)` — O(1) eviction | FIXED |
| `capture/keyboard_capture.py` | 152 | Converted `_buffer` to `deque(maxlen=...)` — O(1) eviction | FIXED |

## 4. Unhandled `response.json()` JSONDecodeError

| File | Line(s) | Issue | Status |
|------|---------|-------|--------|
| `transport/telegram_transport.py` | 55, 109, 112, 135, 138 | Wrapped all `response.json()` calls in try/except for `json.JSONDecodeError` | FIXED |

## 5. Premature State/Timestamp Updates

| File | Line | Issue | Status |
|------|------|-------|--------|
| `engine/registry.py` | 70 | Moved `_last_check = now` to after file existence check | FIXED |

## 6. Unused Code

| File | Line(s) | Item | Status |
|------|---------|------|--------|
| `dashboard/auth.py` | 117-119 | Removed unused `LoginForm` class and orphaned `BaseModel` import | FIXED |
