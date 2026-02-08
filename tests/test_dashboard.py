"""Tests for the web dashboard."""
from __future__ import annotations

import pytest

try:
    from fastapi.testclient import TestClient
    from dashboard.app import create_app
    _DASHBOARD_AVAILABLE = True
except ImportError:
    _DASHBOARD_AVAILABLE = False

needs_dashboard = pytest.mark.skipif(
    not _DASHBOARD_AVAILABLE, reason="Dashboard dependencies not installed"
)


@needs_dashboard
class TestDashboardAuth:
    """Test authentication flow."""

    def setup_method(self):
        self.app = create_app(secret_key="test-secret")
        self.client = TestClient(self.app)

    def test_login_page_renders(self):
        response = self.client.get("/login")
        assert response.status_code == 200
        assert "AdvanceKeyLogger" in response.text
        assert "Sign in" in response.text

    def test_unauthenticated_redirect(self):
        response = self.client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.headers["location"]

    def test_login_success(self):
        response = self.client.post(
            "/auth/login",
            data={"username": "admin", "password": "admin"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "session_token" in response.cookies

    def test_login_failure(self):
        response = self.client.post(
            "/auth/login",
            data={"username": "admin", "password": "wrong"},
        )
        assert response.status_code == 401
        assert "Invalid" in response.text

    def test_logout(self):
        # Login first
        self.client.post(
            "/auth/login",
            data={"username": "admin", "password": "admin"},
        )
        # Logout
        response = self.client.get("/auth/logout", follow_redirects=False)
        assert response.status_code == 302


@needs_dashboard
class TestDashboardAPI:
    """Test API endpoints."""

    def setup_method(self):
        self.app = create_app(secret_key="test-secret")
        self.client = TestClient(self.app)
        # Login
        self.client.post(
            "/auth/login",
            data={"username": "admin", "password": "admin"},
        )

    def test_health_no_auth_needed(self):
        # Health endpoint should work without auth
        client = TestClient(self.app)
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "timestamp" in data

    def test_api_requires_auth(self):
        # Unauthenticated client
        client = TestClient(self.app)
        response = client.get("/api/status")
        assert response.status_code == 401

    def test_status_endpoint(self):
        response = self.client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        assert "uptime" in data
        assert "system" in data
        assert "storage" in data
        assert "captures" in data

    def test_captures_endpoint(self):
        response = self.client.get("/api/captures")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    def test_screenshots_endpoint(self):
        response = self.client.get("/api/screenshots")
        assert response.status_code == 200
        data = response.json()
        assert "screenshots" in data
        assert "total" in data

    def test_analytics_activity(self):
        response = self.client.get("/api/analytics/activity")
        assert response.status_code == 200
        data = response.json()
        assert "heatmap" in data
        assert len(data["heatmap"]) == 7
        assert len(data["heatmap"][0]) == 24

    def test_analytics_summary(self):
        response = self.client.get("/api/analytics/summary")
        assert response.status_code == 200
        data = response.json()
        assert "total_captures" in data
        assert "pending" in data

    def test_config_endpoint(self):
        response = self.client.get("/api/config")
        assert response.status_code == 200
        data = response.json()
        assert "config" in data

    def test_modules_endpoint(self):
        response = self.client.get("/api/modules")
        assert response.status_code == 200
        data = response.json()
        assert "capture_modules" in data
        assert "transport_modules" in data

    def test_screenshot_path_traversal(self):
        response = self.client.get("/api/screenshots/..%2F..%2Fetc%2Fpasswd")
        assert response.status_code in (400, 404)


@needs_dashboard
class TestDashboardPages:
    """Test page rendering for authenticated users."""

    def setup_method(self):
        self.app = create_app(secret_key="test-secret")
        self.client = TestClient(self.app)
        self.client.post(
            "/auth/login",
            data={"username": "admin", "password": "admin"},
        )

    def test_dashboard_page(self):
        response = self.client.get("/")
        assert response.status_code == 200
        assert "Dashboard" in response.text

    def test_analytics_page(self):
        response = self.client.get("/analytics")
        assert response.status_code == 200
        assert "Analytics" in response.text

    def test_captures_page(self):
        response = self.client.get("/captures")
        assert response.status_code == 200
        assert "Captures" in response.text

    def test_screenshots_page(self):
        response = self.client.get("/screenshots")
        assert response.status_code == 200
        assert "Screenshots" in response.text

    def test_settings_page(self):
        response = self.client.get("/settings")
        assert response.status_code == 200
        assert "Settings" in response.text

    def test_login_redirect_if_authenticated(self):
        response = self.client.get("/login", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/"
