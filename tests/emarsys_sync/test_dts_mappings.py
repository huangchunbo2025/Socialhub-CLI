"""Tests for BigQuery → dts_ field mapping rules."""
from __future__ import annotations

from emarsys_sync.mapping.dts_mappings import (
    DTS_TABLES,
    apply_dts_mapping,
)


def test_email_sends_maps_to_message_record():
    row = {
        "customer_id": "12345",
        "contact_id": 99,
        "event_time": "2026-01-01T00:00:00Z",
        "loaded_at": "2026-01-01T01:00:00Z",
        "message_id": 777,
        "campaign_id": 42,
        "launch_id": 11,
        "domain": "example.com",
        "campaign_type": "batch",
    }
    result = apply_dts_mapping("email_sends", row, tenant_id="uat")

    assert result["target_table"] == "vdm_t_message_record"
    assert result["row"]["tenant_id"] == "uat"
    assert result["row"]["consumer_code"] == "99"
    assert result["row"]["send_time"] == "2026-01-01T00:00:00Z"
    assert result["row"]["template_type"] == 2
    assert result["row"]["status"] == 5
    assert result["row"]["business_type"] == 1   # batch → 1
    assert result["row"]["receiver"] == "example.com"
    assert "id" in result["row"]


def test_email_sends_transactional_maps_business_type_0():
    row = {
        "customer_id": "12345", "contact_id": 1, "event_time": "2026-01-01T00:00:00Z",
        "loaded_at": "2026-01-01T01:00:00Z", "message_id": 1, "campaign_id": 1,
        "launch_id": 1, "domain": "x.com", "campaign_type": "transactional",
    }
    result = apply_dts_mapping("email_sends", row, tenant_id="uat")
    assert result["row"]["business_type"] == 0


def test_unmapped_table_returns_none():
    result = apply_dts_mapping("engagement_events", {}, tenant_id="uat")
    assert result is None


def test_dts_tables_contains_expected_keys():
    assert "email_sends" in DTS_TABLES
    assert "email_opens" in DTS_TABLES
    assert "email_clicks" in DTS_TABLES
    assert "email_bounces" in DTS_TABLES
    assert "email_unsubscribes" in DTS_TABLES
    assert "email_campaigns_v2" in DTS_TABLES
    assert "loyalty_contact_points_state_latest" in DTS_TABLES
    assert "loyalty_points_earned_redeemed" in DTS_TABLES
    assert "products_latest_state" in DTS_TABLES


def test_email_opens_maps_to_message_record_status_6():
    row = {
        "contact_id": 1, "event_time": "2026-01-02T00:00:00Z",
        "loaded_at": "2026-01-02T01:00:00Z", "message_id": 2, "campaign_id": 3,
        "launch_id": 4, "domain": "a.com", "campaign_type": "batch",
    }
    result = apply_dts_mapping("email_opens", row, tenant_id="uat")
    assert result["target_table"] == "vdm_t_message_record"
    assert result["row"]["status"] == 6


def test_email_clicks_maps_to_message_record_status_7():
    row = {
        "contact_id": 1, "event_time": "2026-01-03T00:00:00Z",
        "loaded_at": "2026-01-03T01:00:00Z", "message_id": 2, "campaign_id": 3,
        "launch_id": 4, "domain": "a.com", "campaign_type": "batch",
    }
    result = apply_dts_mapping("email_clicks", row, tenant_id="uat")
    assert result["target_table"] == "vdm_t_message_record"
    assert result["row"]["status"] == 7


def test_email_bounces_maps_to_message_record_status_8():
    row = {
        "contact_id": 1, "event_time": "2026-01-04T00:00:00Z",
        "loaded_at": "2026-01-04T01:00:00Z", "message_id": 2, "campaign_id": 3,
        "launch_id": 4, "domain": "a.com", "campaign_type": "batch",
    }
    result = apply_dts_mapping("email_bounces", row, tenant_id="uat")
    assert result["target_table"] == "vdm_t_message_record"
    assert result["row"]["status"] == 8


def test_email_unsubscribes_maps_to_message_record_status_9():
    row = {
        "contact_id": 1, "event_time": "2026-01-05T00:00:00Z",
        "loaded_at": "2026-01-05T01:00:00Z", "message_id": 2, "campaign_id": 3,
        "launch_id": 4, "domain": "a.com", "campaign_type": "batch",
    }
    result = apply_dts_mapping("email_unsubscribes", row, tenant_id="uat")
    assert result["target_table"] == "vdm_t_message_record"
    assert result["row"]["status"] == 9


def test_email_campaigns_v2_maps_to_activity():
    row = {"campaign_id": 10, "name": "Summer Sale", "event_time": "2026-02-01T00:00:00Z"}
    result = apply_dts_mapping("email_campaigns_v2", row, tenant_id="uat")
    assert result["target_table"] == "vdm_t_activity"
    assert result["row"]["code"] == "10"
    assert result["row"]["name"] == "Summer Sale"
    assert result["row"]["tenant_id"] == "uat"


def test_loyalty_points_state_maps_to_points_account():
    row = {"contact_id": 5, "plan_id": 99, "balance": 1000.0, "event_time": "2026-02-01T00:00:00Z"}
    result = apply_dts_mapping("loyalty_contact_points_state_latest", row, tenant_id="uat")
    assert result["target_table"] == "vdm_t_points_account"
    assert result["row"]["consumer_code"] == "5"
    assert result["row"]["plan_code"] == "99"
    assert result["row"]["balance"] == 1000.0


def test_loyalty_points_earned_redeemed_maps_to_points_record():
    row = {"contact_id": 5, "points": 50.0, "event_time": "2026-02-01T00:00:00Z"}
    result = apply_dts_mapping("loyalty_points_earned_redeemed", row, tenant_id="uat")
    assert result["target_table"] == "vdm_t_points_record"
    assert result["row"]["direction"] == 1  # positive points
    assert result["row"]["points"] == 50.0
    assert "5_2026-02-01T00:00:00Z" in result["row"]["code"]


def test_loyalty_points_negative_direction():
    row = {"contact_id": 5, "points": -20.0, "event_time": "2026-02-01T00:00:00Z"}
    result = apply_dts_mapping("loyalty_points_earned_redeemed", row, tenant_id="uat")
    assert result["row"]["direction"] == 2  # negative points


def test_products_latest_state_maps_to_product():
    row = {
        "item_id": "SKU-001", "title": "Widget", "category": "Electronics",
        "price": 29.99, "available_from": "2026-01-01", "available_to": "2026-12-31",
        "event_time": "2026-01-01T00:00:00Z",
    }
    result = apply_dts_mapping("products_latest_state", row, tenant_id="uat")
    assert result["target_table"] == "vdm_t_product"
    assert result["row"]["code"] == "SKU-001"
    assert result["row"]["name"] == "Widget"
    assert result["row"]["price"] == 29.99
