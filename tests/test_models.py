"""Tests for ORM models."""
import pytest
from sqlalchemy import inspect


def test_model_table_name():
    """TenantBigQueryCredential 映射到正确的表名。"""
    from mcp_server.models import TenantBigQueryCredential
    assert TenantBigQueryCredential.__tablename__ == "tenant_bigquery_credentials"


def test_model_columns():
    """TenantBigQueryCredential 包含所有必要字段。"""
    from mcp_server.models import TenantBigQueryCredential
    mapper = inspect(TenantBigQueryCredential)
    col_names = {col.key for col in mapper.columns}
    required = {
        "id", "tenant_id", "customer_id", "gcp_project_id",
        "dataset_id", "service_account_json", "tables_found",
        "validated_at", "created_at", "updated_at",
    }
    assert required.issubset(col_names), f"Missing columns: {required - col_names}"


def test_model_tenant_id_unique():
    """tenant_id 字段有唯一约束。"""
    from mcp_server.models import TenantBigQueryCredential
    mapper = inspect(TenantBigQueryCredential)
    tenant_col = next(c for c in mapper.columns if c.key == "tenant_id")
    assert tenant_col.unique is True
