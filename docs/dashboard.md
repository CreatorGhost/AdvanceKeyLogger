# Dashboard (Web UI)

FastAPI-based web dashboard with real-time WebSocket updates, session replay, fleet management, and command palette.

- **Source:** [`dashboard/`](../dashboard/)

## Pages

| Page | URL | Description |
|------|-----|-------------|
| Dashboard | `/` | Overview with status cards and activity feed |
| Analytics | `/analytics` | Capture metrics, activity heatmap |
| Captures | `/captures` | Keystroke log viewer |
| Screenshots | `/screenshots` | Screenshot gallery with viewer |
| Sessions | `/sessions` | Session recording list |
| Session Replay | `/sessions/{id}/replay` | Visual timeline replay player |
| Settings | `/settings` | Configuration management |
| Live | `/live` | Real-time activity feed via WebSocket |
| Fleet | `/fleet` | Agent management, command dispatch |
| Agent Details | `/fleet/agents/{id}` | Individual agent status and history |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | System status |
| `/api/captures` | GET | Recent captures |
| `/api/screenshots` | GET | Screenshot list |
| `/api/analytics/activity` | GET | Activity heatmap data |
| `/api/analytics/summary` | GET | Analytics summary |
| `/api/sessions` | GET | Session recording list |
| `/api/sessions/{id}/timeline` | GET | Full timeline for replay |
| `/api/sessions/start` | POST | Start recording |
| `/api/sessions/stop` | POST | Stop recording |
| `/ws/dashboard` | WS | Real-time dashboard updates |

## Running

```bash
# Basic dashboard
python -m dashboard.run --port 8080

# With fleet management
python -m dashboard.run --port 8080 --enable-fleet --admin-pass your_password

# With custom config
python -m dashboard.run --config my_config.yaml
```

## Session Replay Player

The session replay system records user sessions as coordinated screenshot + input event streams and plays them back in a web-based timeline player.

**Features:**
- Scrub bar with drag-to-seek
- Play/pause/stop with keyboard shortcuts (Space, Arrow keys, Home/End)
- Variable speed playback (0.25x to 4x)
- Mouse cursor overlay with click ripple animation
- Keystroke overlay (rolling text buffer)
- Window title overlay
- Binary search for O(log n) seeking
- Event log table with clickable timestamps

**Source:** [`dashboard/static/js/session-replay.js`](../dashboard/static/js/session-replay.js)

## Frontend Stack

- **Server:** FastAPI + Jinja2 templates + uvicorn
- **JS:** Vanilla JavaScript (no framework)
- **CSS:** Custom dark theme (Vercel-inspired)
- **Real-time:** WebSocket with auto-reconnect
- **UX:** Command palette (Ctrl+K) for quick navigation
