"""Tests for /credentials/bigquery endpoints."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.middleware import Middleware

_TEST_KEY_MAP = {"test-token-001": "democn"}

VALID_SA_JSON = {
    "type": "service_account",
    "project_id": "test-project",
    "private_key": "-----BEGIN RSA PRIVATE KEY-----\ntest\n-----END RSA PRIVATE KEY-----\n",
    "client_email": "test@test.iam.gserviceaccount.com",
    "client_id": "123",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "private_key_id": "key1",
}


@pytest.fixture
def client():
    with patch("mcp_server.auth._API_KEY_MAP", _TEST_KEY_MAP):
        from mcp_server.routers.credentials import (
            upload_credentials, get_credentials, delete_credentials
        )
        from mcp_server.auth import APIKeyMiddleware

        app = Starlette(
            routes=[
                Route("/credentials/bigquery", upload_credentials, methods=["POST"]),
                Route("/credentials/bigquery", get_credentials, methods=["GET"]),
                Route("/credentials/bigquery", delete_credentials, methods=["DELETE"]),
            ],
            middleware=[Middleware(APIKeyMiddleware)],
        )
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


def test_upload_no_token(client):
    resp = client.post("/credentials/bigquery", json={})
    assert resp.status_code == 401


def test_upload_missing_fields(client):
    resp = client.post(
        "/credentials/bigquery",
        json={"customer_id": "123"},
        headers={"Authorization": "Bearer test-token-001"},
    )
    assert resp.status_code == 422


def test_upload_success(client):
    from mcp_server.services.bigquery_validator import ValidationResult

    mock_result = ValidationResult(
        success=True,
        tables_found=["email_sends_12345", "email_opens_12345"],
    )

    mock_credential = MagicMock()
    mock_credential.customer_id = "12345"
    mock_credential.tables_found = '["email_sends_12345","email_opens_12345"]'
    mock_credential.validated_at = datetime(2026, 3, 31, 10, 0, 0, tzinfo=timezone.utc)

    with patch("mcp_server.routers.credentials.validate_credentials", return_value=mock_result):
        with patch("mcp_server.routers.credentials.encrypt", return_value="encrypted-blob"):
            with patch("mcp_server.routers.credentials.get_session") as mock_session_fn:
                mock_session = AsyncMock()
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=False)
                mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
                mock_session.add = MagicMock()
                mock_session.commit = AsyncMock()
                mock_session.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, 'validated_at', mock_credential.validated_at) or setattr(obj, 'tables_found', mock_credential.tables_found))
                mock_session_fn.return_value = mock_session

                resp = client.post(
                    "/credentials/bigquery",
                    json={
                        "customer_id": "12345",
                        "gcp_project_id": "test-project",
                        "dataset_id": "emarsys_12345",
                        "service_account_json": VALID_SA_JSON,
                    },
                    headers={"Authorization": "Bearer test-token-001"},
                )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["tenant_id"] == "democn"


def test_upload_validation_failure(client):
    from mcp_server.services.bigquery_validator import ValidationResult

    mock_result = ValidationResult(success=False, error="Permission denied")

    with patch("mcp_server.routers.credentials.validate_credentials", return_value=mock_result):
        resp = client.post(
            "/credentials/bigquery",
            json={
                "customer_id": "12345",
                "gcp_project_id": "test-project",
                "dataset_id": "emarsys_12345",
                "service_account_json": VALID_SA_JSON,
            },
            headers={"Authorization": "Bearer test-token-001"},
        )

    assert resp.status_code == 422
    assert "Permission denied" in resp.json()["message"]


def test_get_not_configured(client):
    with patch("mcp_server.routers.credentials.get_session") as mock_session_fn:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        mock_session_fn.return_value = mock_session

        resp = client.get(
            "/credentials/bigquery",
            headers={"Authorization": "Bearer test-token-001"},
        )

    assert resp.status_code == 200
    assert resp.json()["configured"] is False


def test_delete_not_found(client):
    with patch("mcp_server.routers.credentials.get_session") as mock_session_fn:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        mock_session_fn.return_value = mock_session

        resp = client.delete(
            "/credentials/bigquery",
            headers={"Authorization": "Bearer test-token-001"},
        )

    assert resp.status_code == 404
