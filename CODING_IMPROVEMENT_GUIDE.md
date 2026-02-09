# Coding Improvement Guide

Based on a full review of this codebase. Focuses on Python skills, architecture,
and professional engineering habits.

---

## 1. Concurrency & Async Patterns

These are the biggest gap areas. Concurrency bugs are hard to find in testing
but crash in production.

### 1a. Never iterate a dict that another coroutine/thread can mutate

```python
# BAD — RuntimeError if dict changes during loop
for agent_id, queue in self.command_queues.items():
    ...

# GOOD — snapshot the items first
for agent_id, queue in list(self.command_queues.items()):
    ...
```

**Rule:** Any time you loop over a shared dict/set/list that another thread or
coroutine can modify, wrap it in `list(...)` first.

**Practice project:** Write a small program with two threads — one adding keys
to a dict, one iterating it. Watch it crash. Then fix it with `list()`.

### 1b. Understand TOCTOU (Time-Of-Check vs Time-Of-Use)

```python
# BAD — queue can change between check and get
if not queue.empty():
    _, command = await queue.get()  # can block forever

# GOOD — atomic check-and-get
try:
    _, command = queue.get_nowait()
except asyncio.QueueEmpty:
    continue
```

**Rule:** If you check a condition then act on it, ask yourself: "Can another
coroutine/thread change this between my check and my action?" If yes, use an
atomic operation instead.

### 1c. Know the sync/async boundary

```python
# BAD — create_task needs a running event loop
def send_command(self, ...):  # sync method
    asyncio.create_task(queue.put(...))  # fails without running loop

# GOOD option A — make the method async
async def send_command(self, ...):
    await queue.put(...)

# GOOD option B — use sync-safe queue method
def send_command(self, ...):
    queue.put_nowait(...)
```

**Rule:** `asyncio.create_task()`, `await`, and any `async` call can only
happen inside a running event loop. If your method is sync (`def` not
`async def`), you cannot use them. Use `_nowait()` variants or
`run_coroutine_threadsafe()` from sync code.

**Study:** Read the Python docs page on
[asyncio — Concurrency and Multithreading](https://docs.python.org/3/library/asyncio-dev.html#concurrency-and-multithreading).

### 1d. PriorityQueue needs fully comparable items

```python
# BAD — if two commands have the same priority, Python compares Command objects
queue.put((priority.value, command))  # TypeError: '<' not supported

# GOOD — add a tiebreaker that's always unique
self._seq = 0
...
self._seq += 1
queue.put((priority.value, self._seq, command))
```

**Rule:** `PriorityQueue` compares tuples element-by-element. If the first
element ties, it compares the second. Make sure every element in the tuple
is comparable, or add a monotonic sequence number as a tiebreaker.

---

## 2. Python Best Practices

### 2a. Lazy logging format strings

```python
# BAD — f-string is always evaluated, even if log level is off
logger.info(f"Agent registered: {agent_id}")

# GOOD — only formatted if the message is actually logged
logger.info("Agent registered: %s", agent_id)
```

This matters in hot loops (per-request, per-message paths). For one-time
startup logs it doesn't matter much, but building the habit is valuable.

### 2b. Log tracebacks, not just messages

```python
# BAD — you lose the stack trace
except Exception as e:
    logger.error(f"Failed: {e}")

# GOOD — full traceback is preserved
except Exception:
    logger.exception("Failed")

# ALSO GOOD — if you don't want ERROR level
except Exception:
    logger.warning("Failed", exc_info=True)
```

**Rule:** When catching unexpected exceptions, always log with `exc_info=True`
or use `logger.exception()`. Without the traceback you'll spend hours guessing
where the error came from.

### 2c. Clean up unused imports

Your `agent_controller.py` imports `struct`, `hashlib`, `Union`, `Coroutine`
but never uses them.

**Action:** Set up a linter. Add to your workflow:

```bash
pip install ruff
ruff check --select F401 .   # find unused imports
ruff check --fix .            # auto-fix what it can
```

Make this a habit before every commit.

### 2d. Pick one type annotation style

You mix `Dict[str, Any]` (from `typing`) and `dict[str, Any]` (built-in).

**Rule:** Since you already use `from __future__ import annotations`, just use
the built-in lowercase forms everywhere: `dict`, `list`, `set`, `tuple`,
`str | None` instead of `Optional[str]`.

The `typing` module imports (`Dict`, `List`, `Optional`, etc.) are the older
style. Modern Python (3.10+) doesn't need them.

### 2e. Use `__all__` in modules with public APIs

When a module has a mix of public classes and internal helpers, define `__all__`
at the top:

```python
__all__ = ["Controller", "Agent", "AgentStatus", "Command"]
```

This tells other developers (and tools like IDEs) what the intended public
interface is.

---

## 3. Architecture & Design

### 3a. Separate protocol from transport

Your `agent_controller.py` is 839 lines and contains: data models, enums,
protocol serialization, crypto channel, controller logic, and agent logic.

**Better structure:**

```
fleet/
    models.py          # AgentMetadata, Command, AgentCapabilities (dataclasses)
    enums.py           # AgentStatus, CommandStatus, CommandPriority
    protocol.py        # ProtocolMessage, SecureChannel
    controller.py      # Controller class only
    agent.py           # Agent class only
```

**Rule of thumb:** If a file is over 300 lines, look for natural split points.
Each file should have one reason to change.

### 3b. Don't hardcode transport choice inside Agent

```python
# Current — Agent is welded to HttpTransport
self.transport = HttpTransport({...})

# Better — inject the transport
class Agent:
    def __init__(self, config, transport: BaseTransport):
        self.transport = transport
```

This is **Dependency Injection**. It lets you:
- Swap transports (HTTP, WebSocket, Redis) without changing Agent code
- Pass a mock transport in tests

**Study:** Look up "Dependency Injection" and "Strategy Pattern".

### 3c. Use an interface/protocol for command handlers

```python
# Current — handlers are bare callables in a dict
self.command_handlers: Dict[str, Callable] = {}

# Better — define a Protocol (structural typing)
from typing import Protocol

class CommandHandler(Protocol):
    def __call__(self, params: dict[str, Any]) -> dict[str, Any]: ...
```

This gives you type checking on handler signatures.

### 3d. Config validation at startup

Your config is a raw `dict[str, Any]` everywhere. If a key is missing or the
wrong type, you find out at runtime in some random code path.

**Better:** Validate config once at startup using `dataclasses` or `pydantic`:

```python
@dataclass
class ControllerConfig:
    heartbeat_timeout: float = 120.0
    max_command_history: int = 1000
    cleanup_interval: float = 300.0

# Fails immediately with a clear error if config is wrong
config = ControllerConfig(**raw_config)
```

---

## 4. Testing Habits

### 4a. Test concurrency bugs explicitly

Write tests that exercise race conditions:

```python
import asyncio

async def test_concurrent_dict_iteration():
    """Ensure iteration survives concurrent modification."""
    d = {"a": 1, "b": 2, "c": 3}

    async def mutator():
        await asyncio.sleep(0)
        d["d"] = 4

    asyncio.create_task(mutator())
    # This should not crash
    for k in list(d):
        await asyncio.sleep(0)
```

### 4b. Test edge cases in your queue

- What happens when PriorityQueue has two items with the same priority?
- What happens when you `get_nowait()` on an empty queue?
- What happens when an agent disconnects while a command is being sent?

### 4c. Use `pytest-asyncio` for async tests

```python
import pytest

@pytest.mark.asyncio
async def test_controller_start_stop():
    controller = Controller({"heartbeat_timeout": 5})
    await controller.start()
    assert controller.running
    await controller.stop()
    assert not controller.running
```

---

## 5. Tooling Checklist

Set these up once, benefit forever:

| Tool | Purpose | Command |
|------|---------|---------|
| `ruff` | Linting + auto-fix (replaces flake8/isort/pyflakes) | `ruff check --fix .` |
| `ruff format` | Code formatting (replaces black) | `ruff format .` |
| `mypy` | Static type checking | `mypy --strict src/` |
| `pytest-cov` | Test coverage | `pytest --cov=. --cov-report=term-missing` |
| `pre-commit` | Run checks before every commit | `pre-commit run --all-files` |

**Goal:** Set up a `pre-commit` config that runs `ruff` and `mypy` on every
commit. This catches unused imports, type errors, and style issues before
they enter the codebase.

---

## 6. Learning Path (ordered by priority)

1. **Concurrency fundamentals** — Read "Python Concurrency with asyncio"
   by Matthew Fowler. Focus on chapters about task groups and sync/async
   boundaries.

2. **SOLID principles** — Especially Single Responsibility and Dependency
   Inversion. Your code already shows good instincts here (BaseTransport
   abstraction, plugin registry). Formalize the knowledge.

3. **Design Patterns** — Strategy (transport swapping), Observer (pub/sub),
   Command pattern (you're already using it). Read "Head First Design
   Patterns" or the Python-specific examples at refactoring.guru.

4. **Testing** — Focus on testing async code and edge cases. Your test suite
   has good coverage for sync code (143 tests). Add async and concurrency
   tests.

5. **Type system mastery** — Run `mypy --strict` on your codebase. Fix every
   error. This will teach you generics, protocols, type narrowing, and
   overloads faster than any tutorial.

---

## Summary of Bugs Found (for learning)

| # | File | Line | Bug | Root Cause |
|---|------|------|-----|------------|
| 1 | agent_controller.py | 447 | Dict iteration during mutation | Missing `list()` snapshot |
| 2 | agent_controller.py | 451 | `queue.get()` can block forever | TOCTOU race on `empty()` check |
| 3 | agent_controller.py | 360 | `create_task` in sync method | Sync/async boundary confusion |
| 4 | agent_controller.py | ~360 | PriorityQueue `TypeError` on tie | Missing `__lt__` or tiebreaker |
| 5 | websocket_transport.py | 210 | `self.logger` vs module `logger` | Copy-paste inconsistency |
| 6 | transport/__init__.py | 93 | `redis_transport` module not found | File is `utils/redis_queue.py` |

All six are concurrency or wiring bugs — the kind that pass unit tests but
fail in production. Learning to spot these is the single biggest skill jump
from intermediate to senior.
