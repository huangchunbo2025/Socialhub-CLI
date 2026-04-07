"""Unit tests for DTS and DataNow mapping functions."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from emarsys_sync.mapping.dts_mappings import apply_dts_mapping
from emarsys_sync.mapping.datanow_mappings import apply_datanow_mapping


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


# ── DTS tests ──────────────────────────────────────────────────────────────

def test_dts_email_unsubscribe_create_time_is_email_sent_at():
    row = {
        "contact_id": 1,
        "message_id": 2,
        "campaign_id": 10,
        "campaign_type": "batch",
        "domain": "example.com",
        "event_time": _ts("2026-01-01T10:00:00"),
        "email_sent_at": _ts("2026-01-01T09:00:00"),
        "loaded_at": _ts("2026-01-01T11:00:00"),
    }
    result = apply_dts_mapping("email_unsubscribes", row, tenant_id="t1")
    assert result is not None
    assert result["row"]["create_time"] == row["email_sent_at"]
    assert result["row"]["create_time"] != row["loaded_at"]


def test_dts_products_latest_state_uses_default_suffix():
    row = {
        "item_id": "sku-001",
        "title": {"default": "Product A", "en": "Product A"},
        "category": {"default": "Shoes"},
        "price": {"default": 99.9},
        "brand": {"default": "Nike"},
        "link": {"default": "https://example.com/sku-001"},
        "image": {"default": "https://cdn.example.com/img.jpg"},
        "description": {"default": "A great shoe"},
        "currency": {"default": "USD"},
        "availability": {"default": "in_stock"},
        "available_from": _ts("2026-01-01T00:00:00"),
        "event_time": _ts("2026-04-01T00:00:00"),
    }
    result = apply_dts_mapping("products_latest_state", row, tenant_id="t1")
    assert result is not None
    r = result["row"]
    assert r["name"] == "Product A"
    assert r["category"] == "Shoes"
    assert r["brand"] == "Nike"
    assert r["update_time"] == row["event_time"]


def test_dts_loyalty_points_direction_uses_type_field():
    row_earned = {
        "contact_id": 1,
        "event_time": _ts("2026-01-01T00:00:00"),
        "type": "earned",
        "amount": 100,
        "points": 100,
    }
    result = apply_dts_mapping("loyalty_points_earned_redeemed", row_earned, tenant_id="t1")
    assert result["row"]["direction"] == 1

    row_redeemed = {**row_earned, "type": "redeemed", "amount": -50, "points": -50}
    result2 = apply_dts_mapping("loyalty_points_earned_redeemed", row_redeemed, tenant_id="t1")
    assert result2["row"]["direction"] == 2


def test_dts_loyalty_points_direction_falls_back_to_points_sign():
    row = {
        "contact_id": 1,
        "event_time": _ts("2026-01-01T00:00:00"),
        "amount": 50,
        "points": 50,
    }
    result = apply_dts_mapping("loyalty_points_earned_redeemed", row, tenant_id="t1")
    assert result["row"]["direction"] == 1

    row_neg = {**row, "amount": -30, "points": -30}
    result2 = apply_dts_mapping("loyalty_points_earned_redeemed", row_neg, tenant_id="t1")
    assert result2["row"]["direction"] == 2


def test_dts_inapp_campaign_maps_to_vdm_t_activity():
    row = {
        "campaign_id": 42,
        "name": "InApp Campaign",
        "event_time": _ts("2026-01-01T00:00:00"),
    }
    result = apply_dts_mapping("inapp_campaigns", row, tenant_id="t1")
    assert result is not None
    assert result["target_table"] == "vdm_t_activity"
    assert result["row"]["code"] == "42"


def test_dts_returns_none_for_unmapped_table():
    row = {"contact_id": 1, "event_time": _ts("2026-01-01T00:00:00")}
    assert apply_dts_mapping("engagement_events", row, tenant_id="t1") is None


# ── DataNow tests ──────────────────────────────────────────────────────────


def test_datanow_email_sends_campaign_id_in_bigint1():
    row = {
        "contact_id": 1, "campaign_id": 999, "campaign_type": "batch",
        "domain": "x.com", "message_id": 2, "launch_id": 3,
        "event_time": _ts("2026-01-01T00:00:00"),
    }
    result = apply_datanow_mapping("email_sends", row, tenant_id="t1", customer_code="123")
    assert result is not None
    assert result["bigint1"] == "999"           # campaign_id → bigint1
    assert result.get("dimension1") == "batch"  # campaign_type → dimension1
    assert result.get("dimension6") is None     # customer_id slot removed


def test_datanow_email_sends_missing_field_is_skipped():
    row = {"contact_id": 1, "campaign_type": "batch", "event_time": _ts("2026-01-01T00:00:00")}
    result = apply_datanow_mapping("email_sends", row, tenant_id="t1", customer_code="123")
    assert result is not None
    assert "bigint1" not in result  # campaign_id absent → slot skipped


def test_datanow_loyalty_points_state_new_slots():
    row = {
        "contact_id": 1, "tier_name": "Gold", "currency_code": "USD",
        "total_points": 1000, "available_points": 800,
        "pending_points": 50, "spent_points": 150,
        "event_time": _ts("2026-01-01T00:00:00"),
    }
    result = apply_datanow_mapping("loyalty_contact_points_state_latest", row, tenant_id="t1", customer_code="123")
    assert result is not None
    assert result["dimension1"] == "Gold"
    assert result["bigint1"] == "1000"
    assert result["bigint2"] == "800"


def test_datanow_push_sends_mapped():
    row = {"contact_id": 1, "push_token": "tok123", "platform": "Android",
           "campaign_id": 42, "event_time": _ts("2026-01-01T00:00:00")}
    result = apply_datanow_mapping("push_sends", row, tenant_id="t1", customer_code="123")
    assert result is not None
    assert result["event_key"] == "$emarsys_push_send"
    assert result["text2"] == "tok123"


def test_datanow_sms_deliveries_has_no_mapping():
    row = {"contact_id": 1, "event_time": _ts("2026-01-01T00:00:00")}
    assert apply_datanow_mapping("sms_deliveries", row, tenant_id="t1", customer_code="123") is None


def test_datanow_loyalty_points_transaction_new_slots():
    row = {
        "contact_id": 1, "transaction_id": "txn-001", "type": "earned",
        "amount": 100, "balance": 500, "total_points": 500,
        "event_time": _ts("2026-01-01T00:00:00"),
    }
    result = apply_datanow_mapping("loyalty_points_earned_redeemed", row, tenant_id="t1", customer_code="123")
    assert result is not None
    assert result["text2"] == "txn-001"
    assert result["dimension1"] == "earned"
    assert result["bigint1"] == "100"


def test_datanow_no_event_time_returns_none():
    row = {"contact_id": 1}
    assert apply_datanow_mapping("email_sends", row, tenant_id="t1", customer_code="123") is None
