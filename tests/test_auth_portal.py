"""Tests for POST /auth/login endpoint."""
import pytest
from unittest.mock import MagicMock, patch
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient


@pytest.fixture
def client():
    from mcp_server.routers.auth_portal import login
    app = Starlette(
        routes=[
            Route("/auth/login", login, methods=["POST"]),
        ]
    )
    return TestClient(app, raise_server_exceptions=False)


def test_login_missing_fields(client):
    """Login with missing fields returns 422."""
    resp = client.post("/auth/login", json={"tenantId": "democn"})
    assert resp.status_code == 422


def test_login_socialhub_error(client):
    """Login with wrong credentials returns 401."""
    with patch("mcp_server.routers.auth_portal._SOCIALHUB_AUTH_URL", "https://auth.example.com"):
        with patch("mcp_server.routers.auth_portal.OAuthClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.fetch_token.side_effect = Exception("invalid credentials")
            mock_cls.return_value = mock_client
            resp = client.post("/auth/login", json={
                "tenantId": "democn", "account": "bad", "pwd": "wrong"
            })
    assert resp.status_code == 401
    assert "error" in resp.json()


def test_login_success_returns_jwt(client):
    """Successful login returns a JWT token."""
    with patch("mcp_server.routers.auth_portal._SOCIALHUB_AUTH_URL", "https://auth.example.com"):
        with patch("mcp_server.routers.auth_portal.OAuthClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.fetch_token.return_value = {
                "token": "sh-token", "refreshToken": "r", "expiresTime": 9999
            }
            mock_cls.return_value = mock_client
            resp = client.post("/auth/login", json={
                "tenantId": "democn", "account": "admin", "pwd": "pass"
            })
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data
    assert data["token"].count(".") == 2  # valid JWT format
    assert data["tenant_id"] == "democn"


def test_login_no_auth_url(client):
    """Login returns 503 when SOCIALHUB_AUTH_URL is not configured."""
    with patch("mcp_server.routers.auth_portal._SOCIALHUB_AUTH_URL", ""):
        resp = client.post("/auth/login", json={
            "tenantId": "democn", "account": "admin", "pwd": "pass"
        })
    assert resp.status_code == 503
