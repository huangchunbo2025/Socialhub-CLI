"""Tests for BigQuery → t_retailevent slot mappings and view DDL generation."""
from __future__ import annotations

from emarsys_sync.mapping.datanow_mappings import (
    DATANOW_TABLES,
    apply_datanow_mapping,
    build_view_ddl,
    get_all_event_keys,
)


def test_email_sends_produces_retailevent_row():
    row = {
        "contact_id": 99,
        "event_time": "2026-01-01T00:00:00Z",
        "message_id": 777,
        "campaign_id": 42,
        "launch_id": 11,
        "domain": "example.com",
        "campaign_type": "batch",
        "loaded_at": "2026-01-01T01:00:00Z",
    }
    result = apply_datanow_mapping("email_sends", row, tenant_id="uat", customer_code="uat")
    assert result is not None
    assert result["event_key"] == "$emarsys_email_send"
    assert result["event_type"] == "trace"
    assert result["customer_code"] == "uat"
    assert result["tenant_id"] == "uat"
    assert result["event_time"] == "2026-01-01T00:00:00Z"
    # contact_id → text1
    assert result["text1"] == "99"
    # campaign_id → bigint1 (v2 slot realignment)
    assert result["bigint1"] == "42"
    # campaign_type → dimension1 (v2)
    assert result["dimension1"] == "batch"


def test_unmapped_table_returns_none():
    # sms_deliveries was removed from DATANOW_TABLES in v2
    result = apply_datanow_mapping("sms_deliveries", {}, tenant_id="uat", customer_code="uat")
    assert result is None


def test_build_view_ddl_generates_correct_sql():
    ddl = build_view_ddl(
        "$emarsys_email_send",
        {"text1": "contact_id", "bigint1": "campaign_id"},
    )
    assert "CREATE OR REPLACE VIEW t_retailevent_emarsys_email_send" in ddl
    assert "text1 AS contact_id" in ddl
    assert "bigint1 AS campaign_id" in ddl
    assert "WHERE event_key = '$emarsys_email_send'" in ddl


def test_get_all_event_keys_returns_48_entries():
    keys = get_all_event_keys()
    assert len(keys) == 48
    assert "$emarsys_email_send" in keys


def test_datanow_tables_has_48_entries():
    assert len(DATANOW_TABLES) == 48


def test_apply_datanow_mapping_returns_none_when_event_time_missing():
    row = {"contact_id": 99}  # no event_time
    result = apply_datanow_mapping("email_sends", row, tenant_id="uat", customer_code="uat")
    assert result is None
