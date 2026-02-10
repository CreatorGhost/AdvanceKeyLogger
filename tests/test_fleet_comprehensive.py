"""
Comprehensive fleet management tests.
"""

import sys
import os
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import Settings
from dashboard.app import create_app
from dashboard.routes.fleet_dashboard_api import get_current_user_api

DB_PATH = "./data/test_comprehensive_fleet.db"


@pytest.fixture
def client():
    """Set up test client with fleet enabled."""
    # Reset settings singleton
    Settings.reset()

    settings = Settings()
    settings.set("fleet.enabled", True)
    settings.set("fleet.database_path", DB_PATH)
    settings.set("fleet.auth.jwt_secret", "test-secret-key-32chars-minimum")

    # Clean previous run
    for f in [DB_PATH, DB_PATH + "-shm", DB_PATH + "-wal"]:
        if os.path.exists(f):
            os.remove(f)

    app = create_app()
    app.dependency_overrides[get_current_user_api] = lambda: "test-admin"

    with TestClient(app) as c:
        yield c

    # Cleanup
    for f in [DB_PATH, DB_PATH + "-shm", DB_PATH + "-wal"]:
        if os.path.exists(f):
            os.remove(f)

    Settings.reset()


class TestFleetRegistration:
    """Test agent registration flow."""

    def test_register_new_agent(self, client):
        """Test successful agent registration."""
        payload = {
            "agent_id": "agent-001",
            "hostname": "test-host",
            "platform": "linux",
            "version": "1.0.0",
            "public_key": "-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----",
            "capabilities": {"keylogging": True, "screenshots": False},
            "metadata": {"mac_address": "00:11:22:33:44:55"},
        }

        res = client.post("/api/v1/fleet/register", json=payload)
        assert res.status_code == 200

        data = res.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "Bearer"
        assert data["expires_in"] > 0
        # Verify controller public key is returned
        assert "controller_public_key" in data

    def test_register_duplicate_agent(self, client):
        """Test re-registration of existing agent (should update)."""
        payload = {
            "agent_id": "agent-002",
            "hostname": "test-host",
            "platform": "linux",
            "version": "1.0.0",
            "public_key": "test-key",
            "capabilities": {},
            "metadata": {},
        }

        # First registration
        res1 = client.post("/api/v1/fleet/register", json=payload)
        assert res1.status_code == 200

        # Second registration (update)
        payload["hostname"] = "updated-host"
        res2 = client.post("/api/v1/fleet/register", json=payload)
        assert res2.status_code == 200

        # Both should succeed (re-registration is allowed)


class TestFleetAuthentication:
    """Test JWT authentication."""

    def test_heartbeat_without_token(self, client):
        """Test heartbeat fails without auth token."""
        res = client.post("/api/v1/fleet/heartbeat", json={"status": "ONLINE"})
        assert res.status_code == 401

    def test_heartbeat_with_invalid_token(self, client):
        """Test heartbeat fails with invalid token."""
        res = client.post(
            "/api/v1/fleet/heartbeat",
            json={"status": "ONLINE"},
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert res.status_code == 401

    def test_heartbeat_with_valid_token(self, client):
        """Test heartbeat succeeds with valid token."""
        # Register first
        reg_res = client.post(
            "/api/v1/fleet/register",
            json={
                "agent_id": "agent-auth-test",
                "hostname": "test",
                "platform": "test",
                "version": "1.0",
                "public_key": "key",
                "capabilities": {},
                "metadata": {},
            },
        )
        token = reg_res.json()["access_token"]

        # Heartbeat with token
        res = client.post(
            "/api/v1/fleet/heartbeat",
            json={"status": "ONLINE", "uptime": 100.0, "metrics": {"cpu": 10}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200


class TestCommandFlow:
    """Test command delivery and response flow."""

    def test_full_command_lifecycle(self, client):
        """Test complete command flow: send -> poll -> respond."""
        # 1. Register agent
        reg_res = client.post(
            "/api/v1/fleet/register",
            json={
                "agent_id": "agent-cmd-test",
                "hostname": "cmd-host",
                "platform": "linux",
                "version": "1.0",
                "public_key": "key",
                "capabilities": {},
                "metadata": {},
            },
        )
        token = reg_res.json()["access_token"]

        # 2. Send command via dashboard API
        cmd_res = client.post(
            "/api/dashboard/fleet/agents/agent-cmd-test/command",
            json={"action": "ping", "parameters": {"echo": "hello"}, "priority": "HIGH"},
        )
        assert cmd_res.status_code == 200
        cmd_id = cmd_res.json()["command_id"]
        assert cmd_id is not None

        # 3. Poll for commands
        poll_res = client.get(
            "/api/v1/fleet/commands", headers={"Authorization": f"Bearer {token}"}
        )
        assert poll_res.status_code == 200
        commands = poll_res.json()["commands"]
        assert len(commands) == 1
        assert commands[0]["command_id"] == cmd_id
        assert commands[0]["action"] == "ping"

        # 4. Submit response
        resp_res = client.post(
            f"/api/v1/fleet/commands/{cmd_id}/response",
            json={"success": True, "result": {"pong": True}, "error": None},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp_res.status_code == 200

        # 5. Verify command status via dashboard
        history_res = client.get("/api/dashboard/fleet/agents/agent-cmd-test/commands")
        assert history_res.status_code == 200
        # Command should be in history
        cmds = history_res.json()["commands"]
        assert any(c["command_id"] == cmd_id for c in cmds)


class TestDashboardAPI:
    """Test dashboard-facing fleet API."""

    def test_list_agents_empty(self, client):
        """Test listing agents when none registered."""
        res = client.get("/api/dashboard/fleet/agents")
        assert res.status_code == 200
        assert res.json()["agents"] == []

    def test_list_agents_with_data(self, client):
        """Test listing agents after registration."""
        # Register an agent
        client.post(
            "/api/v1/fleet/register",
            json={
                "agent_id": "dash-list-test",
                "hostname": "dash-host",
                "platform": "darwin",
                "version": "2.0",
                "public_key": "key",
                "capabilities": {"keylogging": True},
                "metadata": {},
            },
        )

        res = client.get("/api/dashboard/fleet/agents")
        assert res.status_code == 200
        agents = res.json()["agents"]
        assert len(agents) >= 1
        agent = next((a for a in agents if a["agent_id"] == "dash-list-test"), None)
        assert agent is not None
        assert agent["hostname"] == "dash-host"
        assert agent["platform"] == "darwin"

    def test_get_agent_not_found(self, client):
        """Test getting non-existent agent."""
        res = client.get("/api/dashboard/fleet/agents/nonexistent-agent")
        assert res.status_code == 404

    def test_send_command_to_nonexistent_agent(self, client):
        """Test sending command to non-existent agent fails."""
        res = client.post(
            "/api/dashboard/fleet/agents/nonexistent/command",
            json={"action": "ping", "parameters": {}},
        )
        assert res.status_code == 400


class TestPersistence:
    """Test data persistence."""

    def test_agent_persisted_to_db(self, client):
        """Test that agent data is saved to database."""
        client.post(
            "/api/v1/fleet/register",
            json={
                "agent_id": "persist-test",
                "hostname": "persist-host",
                "platform": "windows",
                "version": "3.0",
                "public_key": "key",
                "capabilities": {},
                "metadata": {},
            },
        )

        # Verify via storage directly
        storage = client.app.state.fleet_storage
        agent = storage.get_agent("persist-test")
        assert agent is not None
        assert agent["hostname"] == "persist-host"
        assert agent["platform"] == "windows"

    def test_heartbeat_persisted(self, client):
        """Test that heartbeats are recorded."""
        # Register
        reg_res = client.post(
            "/api/v1/fleet/register",
            json={
                "agent_id": "hb-persist-test",
                "hostname": "hb-host",
                "platform": "linux",
                "version": "1.0",
                "public_key": "key",
                "capabilities": {},
                "metadata": {},
            },
        )
        token = reg_res.json()["access_token"]

        # Send heartbeat
        client.post(
            "/api/v1/fleet/heartbeat",
            json={"status": "ONLINE", "uptime": 500.0, "metrics": {"memory": 80}},
            headers={"Authorization": f"Bearer {token}"},
        )

        # Verify
        storage = client.app.state.fleet_storage
        hb = storage.get_latest_heartbeat("hb-persist-test")
        assert hb is not None
        # The heartbeat stores the full payload as metrics
        # Check that metrics contains the sent data
        assert "metrics" in hb
        # The metrics field stores the full heartbeat payload
        assert (
            hb["metrics"].get("metrics", {}).get("memory") == 80
            or hb["metrics"].get("memory") == 80
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
