"""Tests for /api-keys endpoints."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from starlette.testclient import TestClient

from mcp_server.http_app import app

VALID_JWT = "valid.jwt.token"
TENANT_ID = "democn"


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def mock_jwt_verification():
    """All tests use a valid JWT by default."""
    with patch(
        "mcp_server.routers.api_keys.verify_token",
        return_value=TENANT_ID,
    ):
        yield


def test_create_api_key_success(client):
    """POST /api-keys creates a new key and returns the full key once."""
    with patch("mcp_server.routers.api_keys.get_session") as mock_get:
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_get.return_value = mock_db

        resp = client.post(
            "/api-keys",
            json={"name": "My MCP Key"},
            headers={"X-Portal-Token": VALID_JWT},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["key"].startswith("sh_")
    assert len(data["key"]) == 35  # sh_ + 32 hex chars
    assert data["name"] == "My MCP Key"
    assert "id" in data
    assert "key_prefix" in data


def test_create_api_key_without_token(client):
    """POST /api-keys without JWT returns 401."""
    with patch("mcp_server.routers.api_keys.verify_token", return_value=None):
        resp = client.post("/api-keys", json={"name": "test"})
    assert resp.status_code == 401


def test_create_api_key_missing_name(client):
    """POST /api-keys with empty name returns 422."""
    resp = client.post(
        "/api-keys",
        json={"name": ""},
        headers={"X-Portal-Token": VALID_JWT},
    )
    assert resp.status_code == 422


def test_list_api_keys(client):
    """GET /api-keys returns list of active keys for the tenant."""
    from mcp_server.models import TenantApiKey
    from datetime import datetime, timezone

    fake_key = MagicMock(spec=TenantApiKey)
    fake_key.id = 1
    fake_key.name = "My MCP Key"
    fake_key.key_prefix = "sh_abc123"
    fake_key.created_at = datetime(2026, 4, 1, tzinfo=timezone.utc)
    fake_key.last_used_at = None
    fake_key.revoked_at = None

    with patch("mcp_server.routers.api_keys.get_session") as mock_get:
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [fake_key]
        mock_db.execute = AsyncMock(return_value=result_mock)
        mock_get.return_value = mock_db

        resp = client.get("/api-keys", headers={"X-Portal-Token": VALID_JWT})

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["keys"]) == 1
    assert data["keys"][0]["name"] == "My MCP Key"
    assert "key_hash" not in data["keys"][0]  # never expose hash
    assert "key" not in data["keys"][0]        # never expose full key in list


def test_revoke_api_key(client):
    """DELETE /api-keys/{key_id} sets revoked_at."""
    from mcp_server.models import TenantApiKey

    fake_key = MagicMock(spec=TenantApiKey)
    fake_key.tenant_id = TENANT_ID
    fake_key.revoked_at = None

    with patch("mcp_server.routers.api_keys.get_session") as mock_get:
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = fake_key
        mock_db.execute = AsyncMock(return_value=result_mock)
        mock_get.return_value = mock_db

        resp = client.delete("/api-keys/1", headers={"X-Portal-Token": VALID_JWT})

    assert resp.status_code == 200
    assert fake_key.revoked_at is not None


def test_revoke_api_key_not_found(client):
    """DELETE /api-keys/{key_id} returns 404 if key not found."""
    with patch("mcp_server.routers.api_keys.get_session") as mock_get:
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=result_mock)
        mock_get.return_value = mock_db

        resp = client.delete("/api-keys/999", headers={"X-Portal-Token": VALID_JWT})

    assert resp.status_code == 404
