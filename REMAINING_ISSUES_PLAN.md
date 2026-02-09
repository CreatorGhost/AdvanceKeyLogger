# Comprehensive Plan for Remaining Issues

This document outlines the detailed implementation plan for the 4 remaining issues from `IDENTIFIED_ISSUES.md`.

---

## Issue 11: Fleet Controller Doesn't Persist Keys (Medium Priority)

### Problem
When the fleet controller starts, it generates a new RSA key pair via `SecureChannel.initialize()`. These keys are stored only in memory. On restart:
- The controller gets a new key pair
- Agents still have the old controller public key
- Encrypted communication fails until agents re-register

### Current Code Location
```
fleet/controller.py:75-80
    def _load_or_generate_keys(self) -> None:
        """Load controller keys from storage or generate new ones."""
        # For MVP, we'll just generate new ones.
        # TODO: Persist keys to file or DB to support key pinning.
        self.secure_channel.initialize()
```

### Implementation Plan

#### Step 1: Add Keys Table to FleetStorage
```sql
CREATE TABLE IF NOT EXISTS controller_keys (
    id TEXT PRIMARY KEY DEFAULT 'controller',
    public_key TEXT NOT NULL,
    private_key TEXT NOT NULL,  -- PEM format, encrypted at rest
    created_at REAL,
    rotated_at REAL
);
```

**File**: `storage/fleet_storage.py`
- Add `save_controller_keys(public_key: str, private_key: str)` method
- Add `get_controller_keys() -> Optional[Tuple[str, str]]` method
- Private key should be stored encrypted using a config-provided passphrase

#### Step 2: Update FleetController Key Loading
**File**: `fleet/controller.py`

```python
def _load_or_generate_keys(self) -> None:
    """Load controller keys from storage or generate new ones."""
    keys = self.storage.get_controller_keys()
    
    if keys:
        public_key_pem, private_key_pem = keys
        self.secure_channel.public_key = public_key_pem.encode()
        self.secure_channel.private_key = private_key_pem.encode()
        self.secure_channel._initialized = True
        logger.info("Controller keys loaded from storage")
    else:
        self.secure_channel.initialize()
        # Persist the new keys
        self.storage.save_controller_keys(
            self.secure_channel.public_key.decode(),
            self.secure_channel.private_key.decode()
        )
        logger.info("Controller keys generated and persisted")
```

#### Step 3: Add Key Rotation Support (Optional Enhancement)
**File**: `fleet/controller.py`

```python
async def rotate_keys(self) -> str:
    """Rotate controller keys and notify all agents."""
    old_public_key = self.secure_channel.public_key
    
    # Generate new keys
    self.secure_channel.initialize()
    self.storage.save_controller_keys(
        self.secure_channel.public_key.decode(),
        self.secure_channel.private_key.decode()
    )
    
    # Broadcast key rotation to all agents
    for agent_id in self.agents:
        await self.send_command_async(
            agent_id, 
            "update_controller_key",
            {"new_public_key": self.secure_channel.public_key.decode()}
        )
    
    return self.secure_channel.public_key.decode()
```

#### Step 4: Add Config for Key Encryption
**File**: `config/default_config.yaml`

```yaml
fleet:
  security:
    key_encryption_passphrase: ""  # If empty, keys stored in plaintext
    auto_rotate_keys_days: 0       # 0 = disabled
```

### Files to Modify
| File | Changes |
|------|---------|
| `storage/fleet_storage.py` | Add controller_keys table, save/get methods |
| `fleet/controller.py` | Update `_load_or_generate_keys()` |
| `config/default_config.yaml` | Add key_encryption_passphrase setting |

### Testing Plan
1. Start controller, verify keys are persisted to DB
2. Restart controller, verify same keys are loaded
3. Test key rotation command
4. Verify agent re-registration after key rotation

### Estimated Effort: 2-3 hours

---

## Issue 13: biometrics/matcher.py Unused (Low Priority)

### Problem
`ProfileMatcher` is exported in `biometrics/__init__.py` but never instantiated in production code. Only tests reference it.

### Current State
- `ProfileMatcher` provides `distance()`, `is_match()` methods
- `BiometricsAnalyzer` generates profiles but doesn't use matcher
- The matcher is designed for user authentication scenarios

### Implementation Options

#### Option A: Wire into BiometricsAnalyzer (Recommended)
Add profile matching capability to the existing biometrics flow.

**File**: `biometrics/analyzer.py`

```python
class BiometricsAnalyzer:
    def __init__(self, config: Dict[str, Any] = None):
        # ... existing code ...
        self.matcher = ProfileMatcher(
            threshold=config.get("match_threshold", 50.0)
        )
        self.reference_profiles: Dict[str, dict] = {}
    
    def register_profile(self, user_id: str, profile: dict) -> None:
        """Register a reference profile for a user."""
        self.reference_profiles[user_id] = profile
    
    def authenticate(self, live_profile: dict) -> Optional[str]:
        """Match live profile against registered profiles."""
        for user_id, ref_profile in self.reference_profiles.items():
            if self.matcher.is_match(live_profile, ref_profile):
                return user_id
        return None
    
    def get_similarity(self, profile_a: dict, profile_b: dict) -> float:
        """Get similarity score between two profiles (0-100)."""
        distance = self.matcher.distance(profile_a, profile_b)
        # Convert distance to similarity (inverse relationship)
        return max(0, 100 - distance)
```

#### Option B: Document as Extension Point
If authentication isn't needed now, document how to use it.

**File**: `biometrics/README.md`

```markdown
## Profile Matching

The `ProfileMatcher` class enables user authentication based on typing patterns.

### Usage Example

```python
from biometrics import BiometricsAnalyzer, ProfileMatcher

# Collect reference profile during enrollment
analyzer = BiometricsAnalyzer()
# ... collect keystrokes ...
reference_profile = analyzer.get_profile()

# Later, authenticate user
matcher = ProfileMatcher(threshold=50.0)
live_profile = analyzer.get_profile()

if matcher.is_match(reference_profile, live_profile):
    print("User authenticated!")
else:
    print("Authentication failed")
```
```

### Recommended Approach
**Option A** - Wire into BiometricsAnalyzer with a config flag to enable/disable.

### Files to Modify
| File | Changes |
|------|---------|
| `biometrics/analyzer.py` | Add matcher integration, `authenticate()` method |
| `config/default_config.yaml` | Add `biometrics.authentication_enabled` setting |
| `main.py` | Optionally use authentication in biometrics flow |

### Testing Plan
1. Unit test `authenticate()` with matching profiles
2. Unit test with non-matching profiles
3. Test threshold sensitivity

### Estimated Effort: 1-2 hours

---

## Issue 14: EventBus and RuleRegistry Unused (Low Priority)

### Problem
`EventBus` and `RuleRegistry` are exported from `engine/__init__.py` but never instantiated in production. `RuleEngine` works independently without them.

### Current State
- `EventBus`: Simple pub/sub for routing events to handlers
- `RuleRegistry`: Loads rules from YAML, supports hot-reload
- `RuleEngine`: Self-contained, loads rules directly, has its own buffer

### Analysis
Looking at the code:
- `RuleEngine` already handles rule loading internally via `_load_rules()`
- `RuleEngine` processes events in `process_event()` without EventBus
- `RuleRegistry` duplicates functionality in `RuleEngine`

### Implementation Options

#### Option A: Integrate EventBus into Main Pipeline (Recommended)
Use EventBus as the central event router, allowing multiple subscribers.

**File**: `main.py`

```python
# In AdvancedMonitor class
def __init__(self, config):
    # ... existing code ...
    self.event_bus = EventBus()
    
    # Subscribe rule engine to all events
    if self.rule_engine:
        self.event_bus.subscribe("*", self.rule_engine.process_event)
    
    # Subscribe storage to capture events
    self.event_bus.subscribe("capture", self._store_capture)
    
    # Subscribe biometrics to keystroke events
    if self.biometrics_collector:
        self.event_bus.subscribe("keystroke", self.biometrics_collector.on_keystroke)

def _on_capture(self, capture_type: str, data: Any) -> None:
    """Called by capture modules."""
    event = {
        "type": capture_type,
        "data": data,
        "timestamp": time.time()
    }
    self.event_bus.publish(capture_type, event)
    self.event_bus.publish("capture", event)  # Generic capture topic
```

**Benefits**:
- Decouples components (rule engine, storage, biometrics)
- Allows adding new subscribers without modifying core code
- Supports multiple handlers for same event type

#### Option B: Remove Unused Code
If the EventBus pattern isn't needed, remove dead code.

**Files to delete or modify**:
- Remove `EventBus` from `engine/__init__.py` exports
- Keep `RuleRegistry` as it has hot-reload logic `RuleEngine` lacks

#### Option C: Document as Extension Points
Similar to Issue 13, document how to use these for custom extensions.

### Recommended Approach
**Option A** - Integrate EventBus for cleaner architecture.

### Files to Modify
| File | Changes |
|------|---------|
| `main.py` | Instantiate EventBus, use for event routing |
| `capture/*.py` | Optionally publish to EventBus instead of callbacks |
| `engine/rule_engine.py` | Accept events from EventBus subscription |

### Implementation Steps

1. **Initialize EventBus in main.py**
```python
from engine import EventBus

class AdvancedMonitor:
    def __init__(self, config):
        self.event_bus = EventBus()
```

2. **Subscribe components**
```python
# Rule engine handles all events
self.event_bus.subscribe("*", self._on_event_for_rules)

# Biometrics only cares about keystrokes
self.event_bus.subscribe("keystroke", self._on_keystroke_for_biometrics)
```

3. **Publish from capture modules**
```python
def _keyboard_callback(self, event):
    capture = {"key": event.name, "timestamp": time.time()}
    self.event_bus.publish("keystroke", capture)
```

### Testing Plan
1. Verify events flow through EventBus to all subscribers
2. Test wildcard (*) subscription
3. Test handler errors don't crash other handlers
4. Performance test with high event volume

### Estimated Effort: 2-3 hours

---

## Issue 15: Legacy Root Scripts Orphaned (Low Priority)

### Problem
Two files at the repository root predate the modular architecture:
- `createfile.py` - Standalone screenshot capture with email
- `mailLogger.py` - SMTP email sending utility

These are superseded by:
- `capture/screenshot_capture.py`
- `transport/email_transport.py`

### Current State
- `createfile.py` imports `mailLogger.py`
- Neither is imported by any other production code
- Both have `if __name__ == "__main__"` blocks for standalone use
- `mailLogger.py` uses hardcoded Gmail SMTP settings

### Implementation Plan

#### Step 1: Verify No Dependencies
```bash
# Search for imports
grep -r "from createfile" .
grep -r "import createfile" .
grep -r "from mailLogger" .
grep -r "import mailLogger" .
```

Expected: Only `createfile.py` imports `mailLogger.py`

#### Step 2: Archive or Remove

**Option A: Archive to `legacy/` directory**
```bash
mkdir -p legacy
mv createfile.py legacy/
mv mailLogger.py legacy/
```

Create `legacy/README.md`:
```markdown
# Legacy Scripts

These scripts predate the modular architecture and are kept for reference.

## createfile.py
Original screenshot capture with mouse click trigger and email reporting.
Superseded by: `capture/screenshot_capture.py` + `transport/email_transport.py`

## mailLogger.py  
Original SMTP email utility.
Superseded by: `transport/email_transport.py`

To use the modern equivalents, see `main.py` and configure `transport.method: email`.
```

**Option B: Delete entirely**
```bash
git rm createfile.py mailLogger.py
```

### Recommended Approach
**Option A** - Archive to `legacy/` for historical reference.

### Files to Modify
| Action | File |
|--------|------|
| Move | `createfile.py` → `legacy/createfile.py` |
| Move | `mailLogger.py` → `legacy/mailLogger.py` |
| Create | `legacy/README.md` |
| Update | `.gitignore` (optional: ignore legacy/) |

### Testing Plan
1. Run full test suite after removal
2. Verify no import errors
3. Confirm `main.py` still works without these files

### Estimated Effort: 30 minutes

---

## Implementation Priority & Schedule

| Issue | Priority | Effort | Recommended Order |
|-------|----------|--------|-------------------|
| 15. Legacy scripts | Low | 30 min | 1st (quick win) |
| 13. biometrics/matcher | Low | 1-2 hrs | 2nd |
| 14. EventBus/Registry | Low | 2-3 hrs | 3rd |
| 11. Key persistence | Medium | 2-3 hrs | 4th |

**Total Estimated Effort**: 6-9 hours

### Quick Wins First
1. **Issue 15** - Remove/archive legacy scripts (30 min)
2. **Issue 13** - Add ProfileMatcher integration or docs (1-2 hrs)

### Architecture Improvements
3. **Issue 14** - Integrate EventBus for cleaner event routing (2-3 hrs)
4. **Issue 11** - Persist controller keys for production use (2-3 hrs)

---

## Validation Checklist

After implementing all fixes:

- [ ] All tests pass (`pytest tests/`)
- [ ] Dashboard starts without errors
- [ ] Fleet controller persists keys across restarts
- [ ] EventBus routes events to all subscribers
- [ ] BiometricsAnalyzer can authenticate users
- [ ] No import errors from removed legacy scripts
- [ ] Documentation updated in `IDENTIFIED_ISSUES.md`

---

## Notes

### Issue 12: Fleet API Command Encryption
**Status**: Documented as intentional design decision.

The fleet REST API uses HTTPS/TLS for transport encryption, which is standard practice. Application-level encryption would add complexity without significant security benefit when TLS is already in use.

If end-to-end encryption is required (e.g., for untrusted proxy scenarios):
1. Agent encrypts command responses with controller's public key
2. Controller encrypts commands with agent's public key
3. Both sides decrypt with their private keys

This is already partially implemented in `SecureChannel` but is optional.
