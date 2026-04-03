"""BigQuery → datanow_.t_retailevent slot mapping rules.

Each entry maps a BQ table name to a list of (slot_name, source_field) pairs.
Slots follow t_retailevent schema: text1-30, dimension1-25, bigint1-15,
decimal1-5, datetime1-5, date1-5, context (JSON).

Reference: docs/emarsys-integration/sync-mapping.md  §  t_retailevent mappings
"""

from __future__ import annotations

from typing import Any

# All 21 tables with contact_id — maps table_name → event_key
DATANOW_TABLES: dict[str, str] = {
    "email_sends": "$emarsys_email_send",
    "email_opens": "$emarsys_email_open",
    "email_clicks": "$emarsys_email_click",
    "email_bounces": "$emarsys_email_bounce",
    "email_unsubscribes": "$emarsys_email_unsubscribe",
    "email_cancels": "$emarsys_email_cancel",
    "email_complaints": "$emarsys_email_complaint",
    "web_push_sends": "$emarsys_web_push_send",
    "web_push_clicks": "$emarsys_web_push_click",
    "web_push_not_sends": "$emarsys_web_push_not_send",
    "sms_sends": "$emarsys_sms_send",
    "sms_deliveries": "$emarsys_sms_delivery",
    "sms_clicks": "$emarsys_sms_click",
    "sms_bounces": "$emarsys_sms_bounce",
    "mobile_push_sends": "$emarsys_mobile_push_send",
    "mobile_push_deliveries": "$emarsys_mobile_push_delivery",
    "mobile_push_opens": "$emarsys_mobile_push_open",
    "engagement_events": "$emarsys_engagement_event",
    "loyalty_contact_points_state_latest": "$emarsys_loyalty_points_state",
    "loyalty_points_earned_redeemed": "$emarsys_loyalty_points_transaction",
    "predict_clicks": "$emarsys_predict_click",
}

# Per-event-key slot → view column alias mapping.
# Keys are slot names in t_retailevent; values are the semantic column names used in CREATE OR REPLACE VIEW DDL.
# NOTE: These are NOT BigQuery source field names — see _TABLE_SLOT_SOURCE for the BQ→slot mapping.
SLOT_MAPS: dict[str, dict[str, str]] = {
    "$emarsys_email_send": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "campaign_type",
        "dimension3": "domain",
        "dimension4": "message_id",
        "dimension5": "launch_id",
        "dimension6": "customer_id",
    },
    "$emarsys_email_open": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "campaign_type",
        "dimension3": "domain",
        "dimension4": "message_id",
        "dimension5": "launch_id",
        "dimension6": "customer_id",
        "dimension7": "device_type",
        "dimension8": "country",
    },
    "$emarsys_email_click": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "campaign_type",
        "dimension3": "domain",
        "dimension4": "message_id",
        "dimension5": "launch_id",
        "dimension6": "customer_id",
        "text2": "url",
    },
    "$emarsys_email_bounce": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "campaign_type",
        "dimension3": "domain",
        "dimension4": "message_id",
        "dimension5": "bounce_type",
        "dimension6": "customer_id",
    },
    "$emarsys_email_unsubscribe": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "campaign_type",
        "dimension3": "domain",
        "dimension4": "message_id",
        "dimension5": "customer_id",
    },
    "$emarsys_email_cancel": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "campaign_type",
        "dimension3": "customer_id",
    },
    "$emarsys_email_complaint": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "campaign_type",
        "dimension3": "domain",
        "dimension4": "message_id",
        "dimension5": "customer_id",
    },
    "$emarsys_web_push_send": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "customer_id",
    },
    "$emarsys_web_push_click": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "customer_id",
    },
    "$emarsys_web_push_not_send": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "reason",
        "dimension3": "customer_id",
    },
    "$emarsys_sms_send": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "customer_id",
    },
    "$emarsys_sms_delivery": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "status",
        "dimension3": "customer_id",
    },
    "$emarsys_sms_click": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "customer_id",
        "text2": "url",
    },
    "$emarsys_sms_bounce": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "bounce_type",
        "dimension3": "customer_id",
    },
    "$emarsys_mobile_push_send": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "customer_id",
    },
    "$emarsys_mobile_push_delivery": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "customer_id",
    },
    "$emarsys_mobile_push_open": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "customer_id",
    },
    "$emarsys_engagement_event": {
        "text1": "contact_id",
        "dimension1": "event_name",
        "dimension2": "customer_id",
        "context": "event_data",
    },
    "$emarsys_loyalty_points_state": {
        "text1": "contact_id",
        "dimension1": "plan_id",
        "decimal1": "balance",
        "dimension2": "customer_id",
    },
    "$emarsys_loyalty_points_transaction": {
        "text1": "contact_id",
        "dimension1": "plan_id",
        "dimension2": "transaction_type",
        "decimal1": "points",
        "bigint1": "direction",
        "dimension3": "customer_id",
    },
    "$emarsys_predict_click": {
        "text1": "contact_id",
        "dimension1": "item_id",
        "dimension2": "customer_id",
    },
}

# Per-table BQ source field → slot mapping used at runtime.
# Keys are slot names; values are the BigQuery source field names to read from each row.
# NOTE: These are NOT view column aliases — see SLOT_MAPS for aliases used in DDL generation.
_TABLE_SLOT_SOURCE: dict[str, dict[str, str]] = {
    "email_sends": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "campaign_type",
        "dimension3": "domain",
        "dimension4": "message_id",
        "dimension5": "launch_id",
        "dimension6": "customer_id",
    },
    "email_opens": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "campaign_type",
        "dimension3": "domain",
        "dimension4": "message_id",
        "dimension5": "launch_id",
        "dimension6": "customer_id",
        "dimension7": "device_type",
        "dimension8": "geo_country_iso_code",
    },
    "email_clicks": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "campaign_type",
        "dimension3": "domain",
        "dimension4": "message_id",
        "dimension5": "launch_id",
        "dimension6": "customer_id",
        "text2": "url",
    },
    "email_bounces": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "campaign_type",
        "dimension3": "domain",
        "dimension4": "message_id",
        "dimension5": "bounce_type",
        "dimension6": "customer_id",
    },
    "email_unsubscribes": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "campaign_type",
        "dimension3": "domain",
        "dimension4": "message_id",
        "dimension5": "customer_id",
    },
    "email_cancels": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "campaign_type",
        "dimension3": "customer_id",
    },
    "email_complaints": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "campaign_type",
        "dimension3": "domain",
        "dimension4": "message_id",
        "dimension5": "customer_id",
    },
    "web_push_sends": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "customer_id",
    },
    "web_push_clicks": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "customer_id",
    },
    "web_push_not_sends": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "reason",
        "dimension3": "customer_id",
    },
    "sms_sends": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "customer_id",
    },
    "sms_deliveries": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "status",
        "dimension3": "customer_id",
    },
    "sms_clicks": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "customer_id",
        "text2": "url",
    },
    "sms_bounces": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "bounce_type",
        "dimension3": "customer_id",
    },
    "mobile_push_sends": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "customer_id",
    },
    "mobile_push_deliveries": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "customer_id",
    },
    "mobile_push_opens": {
        "text1": "contact_id",
        "dimension1": "campaign_id",
        "dimension2": "customer_id",
    },
    "engagement_events": {
        "text1": "contact_id",
        "dimension1": "event_name",
        "dimension2": "customer_id",
        "context": "event_data",
    },
    "loyalty_contact_points_state_latest": {
        "text1": "contact_id",
        "dimension1": "plan_id",
        "decimal1": "balance",
        "dimension2": "customer_id",
    },
    "loyalty_points_earned_redeemed": {
        "text1": "contact_id",
        "dimension1": "plan_id",
        "dimension2": "transaction_type",
        "decimal1": "points",
        "bigint1": "direction",
        "dimension3": "customer_id",
    },
    "predict_clicks": {
        "text1": "contact_id",
        "dimension1": "item_id",
        "dimension2": "customer_id",
    },
}


def apply_datanow_mapping(
    table_name: str,
    row: dict[str, Any],
    *,
    tenant_id: str,
    customer_code: str,
) -> dict[str, Any] | None:
    """Transform a BigQuery row into a t_retailevent row dict.

    Args:
        table_name: BQ table name without customer_id suffix.
        row: Raw BigQuery row.
        tenant_id: Target tenant identifier.
        customer_code: Customer code for ``customer_code`` field.

    Returns:
        Dict with t_retailevent fields, or None if table has no datanow mapping.
    """
    event_key = DATANOW_TABLES.get(table_name)
    if event_key is None:
        return None

    slot_source = _TABLE_SLOT_SOURCE.get(table_name, {})
    event_time = row.get("event_time")
    if event_time is None:
        return None  # can't write a row without event_time
    result: dict[str, Any] = {
        "event_key": event_key,
        "event_type": "trace",
        "event_time": str(event_time),  # ensure string for Stream Load
        "customer_code": customer_code,
        "tenant_id": tenant_id,
    }
    for slot, source_field in slot_source.items():
        value = row.get(source_field)
        if value is not None:
            result[slot] = str(value)

    return result


def build_view_ddl(event_key: str, slot_map: dict[str, str]) -> str:
    """Generate CREATE OR REPLACE VIEW DDL for a given event_key.

    Args:
        event_key: Event key (e.g. ``$emarsys_email_send``).
        slot_map: Dict mapping slot names to semantic column names.

    Returns:
        SQL DDL string.
    """
    view_name = event_key.lstrip("$").replace("-", "_")
    columns = ", ".join(f"{slot} AS {name}" for slot, name in slot_map.items())
    return (
        f"CREATE OR REPLACE VIEW t_retailevent_{view_name} AS\n"
        f"SELECT event_time, customer_code, tenant_id, {columns}\n"
        f"FROM t_retailevent WHERE event_key = '{event_key}'"
    )


def get_all_event_keys() -> list[str]:
    """Return all distinct event_keys (one per datanow table).

    Returns:
        List of event key strings.
    """
    return list(DATANOW_TABLES.values())
