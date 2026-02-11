# Architecture

## Deployment Model

The system is deployed across **two machines** -- the victim (target) and the attacker (operator). They communicate over the internet via encrypted HTTP, with no direct database connection.

```mermaid
graph TD
    subgraph victim ["VICTIM MACHINE (target)"]
        Agent["main.py — Unified Agent"]
        Cap["Captures: Keyboard, Mouse\nScreenshot, Clipboard\nWindow, Audio"]
        VDB["Local SQLite\n(temporary buffer)"]
        Stealth["Stealth Module\n(hides everything)"]
        Fleet["Fleet Agent Thread\n(receives commands)"]
        
        Cap --> Agent
        Agent --> VDB
        Stealth -.-> Agent
        Fleet -.-> Agent
    end

    subgraph attacker ["ATTACKER MACHINE (operator)"]
        Server["Server :8000\n/ingest endpoint"]
        Bridge["DataBridge\nJSON → SQLite"]
        ADB["SQLite DB\n(permanent storage)"]
        Dashboard["Dashboard :8080\nWeb UI"]
        Browser["Browser"]
        
        Server --> Bridge
        Bridge --> ADB
        ADB --> Dashboard
        Dashboard --> Browser
    end

    Agent -->|"E2E Encrypted HTTP\n(or DNS/Email fallback)"| Server
    Fleet <-->|"Fleet REST API\n(JWT authenticated)"| Dashboard
```

**Key points:**
- The victim machine only makes **outbound** connections (no listening ports)
- Data is **E2E encrypted** (Curve25519 + AES-256-GCM) before leaving the victim
- The local SQLite on the victim is a **temporary buffer** -- data is deleted after successful sync
- The attacker's SQLite is the **permanent record** that the dashboard reads from
- The two databases are never directly connected -- only linked by encrypted HTTP packets

## What Runs Where

| Machine | Process | Command | Port | Role |
|---------|---------|---------|------|------|
| **Victim** | `main.py` | `python main.py` | None (outbound only) | Capture data + fleet agent (unified) |
| **Attacker** | `server/run.py` | `python -m server.run` | 8000 | E2E ingest server (receives encrypted payloads) |
| **Attacker** | `dashboard/run.py` | `python -m dashboard.run --enable-fleet` | 8080 | Web dashboard + fleet controller |

## Data Flow (Agent to Dashboard)

```mermaid
sequenceDiagram
    participant C as Captures
    participant DB as Victim SQLite
    participant S as SyncEngine
    participant T as Transport
    participant Srv as Server /ingest
    participant B as DataBridge
    participant ADB as Attacker SQLite
    participant D as Dashboard

    C->>DB: 1. Insert captured data
    S->>DB: 2. Query unsent records
    S->>S: 3. Compress + E2E encrypt
    S->>T: 4. Send payload
    T->>Srv: 5. HTTP POST (encrypted)
    Srv->>Srv: 6. Decrypt envelope
    Srv->>B: 7. Parse JSON records
    B->>ADB: 8. INSERT into captures
    Srv-->>T: 9. HTTP 200 OK
    S->>DB: 10. Mark records as sent
    D->>ADB: 11. SELECT for display
```

### Step-by-step:

1. **Capture** -- Agent captures keystrokes, screenshots, etc. and writes to local SQLite
2. **Queue** -- SyncEngine queries for unsent records every 10-30 seconds
3. **Encrypt** -- Records are bundled into JSON, compressed with zlib, encrypted with E2E (Curve25519 + AES-256-GCM)
4. **Transport** -- Encrypted payload sent via configured transport (HTTP primary, DNS/Email fallback)
5. **Receive** -- Server's `/ingest` endpoint receives the encrypted envelope
6. **Decrypt** -- Server decrypts using its private key, verifies signature and replay protection
7. **Parse** -- DataBridge parses the JSON payload into individual records
8. **Store** -- Records inserted into the attacker's SQLite database
9. **Confirm** -- Server responds with 200 OK
10. **Cleanup** -- Agent marks records as "sent", purges after 24h
11. **Display** -- Dashboard reads from the attacker's SQLite and shows in browser

## Component Overview

```mermaid
graph LR
    subgraph core [Core Agent]
        Main["main.py"]
        Caps["Capture Plugins"]
        Pipe["Pipeline Middleware"]
        Store["SQLite Storage"]
        Sync["Sync Engine"]
        Trans["Transport Layer"]
    end

    subgraph intel [Intelligence]
        Rules["Rule Engine"]
        Bio["Biometrics"]
        Prof["Profiler"]
        Harvest["Credential Harvester"]
    end

    subgraph stealth [Stealth System]
        SM["StealthManager"]
        Proc["Process Masking"]
        FS["FS Cloak"]
        Det["Detection Awareness"]
        Net["Network Normalizer"]
        Crash["Crash Guard"]
        Mem["Memory Cloak"]
    end

    subgraph c2sys [Command and Control]
        FleetA["Fleet Agent"]
        DNS["DNS Tunnel"]
        HTTPS["HTTPS Covert"]
        Failover["Failover Chain"]
    end

    subgraph server [Attacker Server]
        Ingest["/ingest API"]
        DBridge["DataBridge"]
        Dash["Dashboard"]
        FleetC["Fleet Controller"]
    end

    Caps --> Main
    Main --> Pipe
    Pipe --> Store
    Store --> Sync
    Sync --> Trans
    Trans --> Ingest
    Ingest --> DBridge
    DBridge --> Dash

    SM -.-> Main
    FleetA <--> FleetC
    Trans --> Failover
    Failover --> DNS
    Failover --> HTTPS
```

## Offline-First Sync

The system uses an **offline-first** design. Data is always captured and stored locally first, then synced when the network is available.

```mermaid
stateDiagram-v2
    [*] --> Captured: Agent captures data
    Captured --> Pending: Saved to local SQLite
    Pending --> Queued: SyncEngine picks up batch
    Queued --> InFlight: Encrypted and sent
    InFlight --> Synced: Server confirms receipt
    InFlight --> Failed: Network error
    Failed --> Pending: Retry with backoff
    Synced --> Purged: Cleanup after 24h
```

If the network is down, data accumulates locally (up to 100MB). When connectivity returns, the SyncEngine drains the backlog automatically with adaptive batch sizing and exponential backoff.

## Plugin Architecture

Capture and transport modules self-register via decorators:

```python
@register_capture("keyboard")
class KeyboardCapture(BaseCapture):
    ...

@register_transport("http")
class HttpTransport(BaseTransport):
    ...
```

Modules are auto-imported at startup. Missing optional dependencies are handled gracefully -- the module is simply skipped.

## Event System

The [`EventBus`](../engine/event_bus.py) provides decoupled pub/sub event routing. Components subscribe to event types and receive notifications without direct coupling:

- Rule engine subscribes to `*` (all events)
- Biometrics subscribes to `keystroke` events
- Profiler subscribes to `window` and `app_focus` events
