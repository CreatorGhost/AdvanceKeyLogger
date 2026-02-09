# Fleet Management

This module adds centralized fleet management capabilities to AdvanceKeyLogger.

## Features

- **Agent Registry**: Track all agents, their status, platform, and capabilities.
- **Secure Communication**: 
  - JWT-based authentication for agents.
  - RSA-signed commands (capability).
  - HTTPS-ready REST API.
- **Command & Control**:
  - Send commands (ping, config update, shutdown, etc.) to agents.
  - Real-time status updates via polling.
  - Persistent command history.
- **Dashboard Integration**:
  - View all agents in the dashboard.
  - Drill down into agent details.
  - Send commands directly from the UI.
- **Persistence**: SQLite-backed storage for all fleet state (`data/fleet.db`).

## Configuration

To enable fleet management, update `config/default_config.yaml` or set environment variables:

```yaml
fleet:
  enabled: true
  database_path: "./data/fleet.db"
  auth:
    jwt_secret: "CHANGE_ME_IN_PRODUCTION"  # Critical for security
  controller:
    heartbeat_timeout_seconds: 300
```

CLI arguments are also supported:
```bash
python dashboard/run.py --enable-fleet --fleet-db ./data/my_fleet.db
```

## Architecture

### Components
1. **FleetController** (`fleet/controller.py`): Manages business logic, state, and persistence.
2. **FleetStorage** (`storage/fleet_storage.py`): Handles SQLite operations for fleet tables.
3. **FleetAgent** (`fleet/agent.py`): Agent implementation that speaks the REST protocol.
4. **Fleet API** (`dashboard/routes/fleet_api.py`): Endpoints for agents (`/api/v1/fleet`).
5. **Dashboard API** (`dashboard/routes/fleet_dashboard_api.py`): Endpoints for UI (`/api/dashboard/fleet`).

### Security
- **Authentication**: Agents exchange a public key for a JWT pair (access/refresh) upon registration.
- **Integrity**: Messages can be signed using the RSA keys established during the handshake.
- **Isolation**: Agent traffic uses a dedicated API prefix separate from the dashboard user API.

## Usage

1. Start the dashboard with fleet enabled.
2. Configure agents to point to the dashboard URL:
   ```python
   config = {
       "controller_url": "http://localhost:8080/api/v1/fleet",
       ...
   }
   agent = FleetAgent(config)
   await agent.start()
   ```
3. Access the dashboard at `http://localhost:8080/dashboard` and navigate to "Fleet" in the sidebar.

## API Endpoints

### Agent API
- `POST /api/v1/fleet/register`: Register and get tokens.
- `POST /api/v1/fleet/heartbeat`: Send heartbeat (requires Bearer token).
- `GET /api/v1/fleet/commands`: Poll for commands.
- `POST /api/v1/fleet/commands/{id}/response`: Submit command result.

### Dashboard API
- `GET /api/dashboard/fleet/agents`: List agents.
- `POST /api/dashboard/fleet/agents/{id}/command`: Send command.
