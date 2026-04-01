"""Tests for BigQuery credentials validator."""
import json
from unittest.mock import MagicMock, patch

import pytest

# Minimal valid service account JSON structure
VALID_SA_JSON = {
    "type": "service_account",
    "project_id": "test-project",
    "private_key_id": "key-id",
    "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA\n-----END RSA PRIVATE KEY-----\n",
    "client_email": "test@test-project.iam.gserviceaccount.com",
    "client_id": "123456789",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
}


def _mock_table(table_id: str):
    t = MagicMock()
    t.table_id = table_id
    return t


def test_validate_success():
    """有效凭据且目标表存在时返回表列表。"""
    from mcp_server.services.bigquery_validator import validate_credentials, ValidationResult

    mock_tables = [
        _mock_table("email_sends_12345"),
        _mock_table("email_opens_12345"),
        _mock_table("email_clicks_12345"),
    ]

    with patch("mcp_server.services.bigquery_validator.service_account") as mock_sa:
        with patch("mcp_server.services.bigquery_validator.bigquery") as mock_bq:
            mock_sa.Credentials.from_service_account_info.return_value = MagicMock()
            mock_client = MagicMock()
            mock_bq.Client.return_value = mock_client
            mock_client.list_tables.return_value = mock_tables

            result = validate_credentials(
                sa_json=VALID_SA_JSON,
                gcp_project_id="test-project",
                dataset_id="emarsys_12345",
                customer_id="12345",
            )

    assert isinstance(result, ValidationResult)
    assert result.success is True
    assert "email_sends_12345" in result.tables_found
    assert "12345" in result.account_ids_found
    assert result.error is None


def test_validate_missing_core_table():
    """核心表 email_sends_{customer_id} 不存在时返回失败。"""
    from mcp_server.services.bigquery_validator import validate_credentials

    mock_tables = [_mock_table("some_other_table")]

    with patch("mcp_server.services.bigquery_validator.service_account") as mock_sa:
        with patch("mcp_server.services.bigquery_validator.bigquery") as mock_bq:
            mock_sa.Credentials.from_service_account_info.return_value = MagicMock()
            mock_client = MagicMock()
            mock_bq.Client.return_value = mock_client
            mock_client.list_tables.return_value = mock_tables

            result = validate_credentials(
                sa_json=VALID_SA_JSON,
                gcp_project_id="test-project",
                dataset_id="emarsys_12345",
                customer_id="12345",
            )

    assert result.success is False
    assert "email_sends_12345" in result.error


def test_validate_invalid_sa_json():
    """SA JSON 格式无效（缺少 type 字段）时返回失败。"""
    from mcp_server.services.bigquery_validator import validate_credentials

    bad_sa = {"project_id": "test"}  # missing 'type'

    result = validate_credentials(
        sa_json=bad_sa,
        gcp_project_id="test-project",
        dataset_id="emarsys_12345",
        customer_id="12345",
    )

    assert result.success is False
    assert result.error is not None


def test_validate_bq_api_error():
    """BigQuery API 抛出异常时返回失败。"""
    from mcp_server.services.bigquery_validator import validate_credentials

    with patch("mcp_server.services.bigquery_validator.service_account") as mock_sa:
        with patch("mcp_server.services.bigquery_validator.bigquery") as mock_bq:
            mock_sa.Credentials.from_service_account_info.return_value = MagicMock()
            mock_client = MagicMock()
            mock_bq.Client.return_value = mock_client
            mock_client.list_tables.side_effect = Exception("Permission denied")

            result = validate_credentials(
                sa_json=VALID_SA_JSON,
                gcp_project_id="test-project",
                dataset_id="emarsys_12345",
                customer_id="12345",
            )

    assert result.success is False
    assert "Permission denied" in result.error


def test_validate_no_customer_id_auto_detect():
    """未提供 customer_id 时自动从表名提取。"""
    from mcp_server.services.bigquery_validator import validate_credentials

    mock_tables = [
        _mock_table("email_sends_12345"),
        _mock_table("email_opens_12345"),
    ]

    with patch("mcp_server.services.bigquery_validator.service_account") as mock_sa:
        with patch("mcp_server.services.bigquery_validator.bigquery") as mock_bq:
            mock_sa.Credentials.from_service_account_info.return_value = MagicMock()
            mock_client = MagicMock()
            mock_bq.Client.return_value = mock_client
            mock_client.list_tables.return_value = mock_tables

            result = validate_credentials(
                sa_json=VALID_SA_JSON,
                gcp_project_id="test-project",
                dataset_id="emarsys_12345",
                # no customer_id
            )

    assert result.success is True
    assert "12345" in result.account_ids_found
