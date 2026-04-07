"""BigQuery → StarRocks dts_ field mapping rules.

Reference: docs/emarsys-integration/sync-mapping-2.md
"""

from __future__ import annotations

import hashlib
from typing import Any

DTS_TABLES: frozenset[str] = frozenset([
    "email_sends",
    "email_opens",
    "email_clicks",
    "email_bounces",
    "email_unsubscribes",
    "email_campaigns_v2",
    "inapp_campaigns",
    "inbox_campaigns",
    "push_campaigns",
    "sms_campaigns",
    "wallet_campaigns",
    "loyalty_contact_points_state_latest",
    "loyalty_points_earned_redeemed",
    "products_latest_state",
])

_CAMPAIGN_TYPE_TO_BUSINESS_TYPE: dict[str, int] = {
    "batch": 1,
    "transactional": 0,
}

_TEMPLATE_TYPE_EMAIL = 2


def _hash_id(*parts: Any) -> int:
    raw = "||".join(str(p) for p in parts)
    digest = hashlib.md5(raw.encode()).hexdigest()  # noqa: S324
    return int(digest, 16) % (2**63 - 1)


def _default_field(row: dict[str, Any], field: str) -> Any:
    """Extract .default sub-field from a BQ STRUCT, or return scalar value."""
    val = row.get(field)
    if isinstance(val, dict):
        return val.get("default")
    return val


def apply_dts_mapping(
    table_name: str, row: dict[str, Any], *, tenant_id: str
) -> dict[str, Any] | None:
    """Transform a BQ row into a StarRocks dts_ row.

    Args:
        table_name: BQ table name without customer_id suffix.
        row: Raw BigQuery row as dict.
        tenant_id: Target tenant identifier.

    Returns:
        Dict with keys ``target_table`` and ``row``, or ``None`` if no mapping.
    """
    if table_name not in DTS_TABLES:
        return None
    handler = _HANDLERS.get(table_name)
    if handler is None:
        return None
    return handler(row, tenant_id)


# ---------------------------------------------------------------------------
# Email event handlers
# ---------------------------------------------------------------------------

def _email_send_event(row: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    return {
        "target_table": "vdm_t_message_record",
        "row": {
            "id": _hash_id(row.get("contact_id"), row.get("message_id"), row.get("event_time")),
            "tenant_id": tenant_id,
            "consumer_code": str(row.get("contact_id", "")),
            "send_time": row.get("event_time"),
            "create_time": row.get("loaded_at"),
            "message_id": str(row.get("message_id", "")),
            "activity_code": str(row.get("campaign_id", "")),
            "receiver": row.get("domain"),
            "business_type": _CAMPAIGN_TYPE_TO_BUSINESS_TYPE.get(
                str(row.get("campaign_type", "")), 1
            ),
            "template_type": _TEMPLATE_TYPE_EMAIL,
            "status": 5,  # sent
        },
    }


def _email_open_event(row: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    return {
        "target_table": "vdm_t_message_record",
        "row": {
            "id": _hash_id(row.get("contact_id"), row.get("message_id"), row.get("event_time")),
            "tenant_id": tenant_id,
            "consumer_code": str(row.get("contact_id", "")),
            "send_time": row.get("event_time"),
            "create_time": row.get("loaded_at"),
            "message_id": str(row.get("message_id", "")),
            "activity_code": str(row.get("campaign_id", "")),
            "receiver": row.get("domain"),
            "business_type": _CAMPAIGN_TYPE_TO_BUSINESS_TYPE.get(
                str(row.get("campaign_type", "")), 1
            ),
            "template_type": _TEMPLATE_TYPE_EMAIL,
            "status": 6,  # opened
        },
    }


def _email_click_event(row: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    return {
        "target_table": "vdm_t_message_record",
        "row": {
            "id": _hash_id(row.get("contact_id"), row.get("message_id"), row.get("event_time")),
            "tenant_id": tenant_id,
            "consumer_code": str(row.get("contact_id", "")),
            "send_time": row.get("event_time"),
            "create_time": row.get("loaded_at"),
            "message_id": str(row.get("message_id", "")),
            "activity_code": str(row.get("campaign_id", "")),
            "receiver": row.get("domain"),
            "business_type": _CAMPAIGN_TYPE_TO_BUSINESS_TYPE.get(
                str(row.get("campaign_type", "")), 1
            ),
            "template_type": _TEMPLATE_TYPE_EMAIL,
            "status": 7,  # clicked
        },
    }


def _email_bounce_event(row: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    return {
        "target_table": "vdm_t_message_record",
        "row": {
            "id": _hash_id(row.get("contact_id"), row.get("message_id"), row.get("event_time")),
            "tenant_id": tenant_id,
            "consumer_code": str(row.get("contact_id", "")),
            "send_time": row.get("event_time"),
            "create_time": row.get("loaded_at"),
            "message_id": str(row.get("message_id", "")),
            "activity_code": str(row.get("campaign_id", "")),
            "receiver": row.get("domain"),
            "business_type": _CAMPAIGN_TYPE_TO_BUSINESS_TYPE.get(
                str(row.get("campaign_type", "")), 1
            ),
            "template_type": _TEMPLATE_TYPE_EMAIL,
            "status": 8,  # bounced
        },
    }


def _email_unsubscribe_event(row: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    return {
        "target_table": "vdm_t_message_record",
        "row": {
            "id": _hash_id(row.get("contact_id"), row.get("message_id"), row.get("event_time")),
            "tenant_id": tenant_id,
            "consumer_code": str(row.get("contact_id", "")),
            "send_time": row.get("event_time"),
            "create_time": row.get("email_sent_at"),  # changed from loaded_at
            "message_id": str(row.get("message_id", "")),
            "activity_code": str(row.get("campaign_id", "")),
            "receiver": row.get("domain"),
            "business_type": _CAMPAIGN_TYPE_TO_BUSINESS_TYPE.get(
                str(row.get("campaign_type", "")), 1
            ),
            "template_type": _TEMPLATE_TYPE_EMAIL,
            "status": 9,  # unsubscribed
        },
    }


# ---------------------------------------------------------------------------
# Campaign handlers (all → vdm_t_activity)
# ---------------------------------------------------------------------------

def _campaign_to_activity(row: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    """Generic campaign → vdm_t_activity handler shared by all channel campaigns."""
    return {
        "target_table": "vdm_t_activity",
        "row": {
            "id": _hash_id(row.get("campaign_id"), row.get("event_time")),
            "code": str(row.get("campaign_id", "")),
            "name": row.get("name"),
            "create_time": row.get("event_time"),
            "tenant_id": tenant_id,
        },
    }


# ---------------------------------------------------------------------------
# Loyalty handlers
# ---------------------------------------------------------------------------

def _loyalty_points_state(row: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    return {
        "target_table": "vdm_t_points_account",
        "row": {
            "id": _hash_id(row.get("contact_id"), row.get("plan_id")),
            "consumer_code": str(row.get("contact_id", "")),
            "plan_code": str(row.get("plan_id", "")),
            # Use available_points as spendable balance; fall back to balance field
            "balance": row.get("available_points") or row.get("balance"),
            "tenant_id": tenant_id,
        },
    }


def _loyalty_points_earned_redeemed(row: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    contact_id = row.get("contact_id")
    event_time = row.get("event_time")
    if contact_id is None or event_time is None:
        raise ValueError(
            f"loyalty_points_earned_redeemed row missing required fields: "
            f"contact_id={contact_id!r}, event_time={event_time!r}"
        )

    # Use explicit type field when available; fall back to points sign for older BQ tables
    tx_type = row.get("type")
    if tx_type == "earned":
        direction = 1
    elif tx_type == "redeemed":
        direction = 2
    else:
        amount_fallback = row.get("amount") or row.get("points", 0) or 0
        direction = 1 if float(amount_fallback) >= 0 else 2

    amount = row.get("amount") or row.get("points", 0) or 0

    return {
        "target_table": "vdm_t_points_record",
        "row": {
            "code": f"{contact_id}_{event_time}",
            "consumer_code": str(contact_id),
            "points": abs(float(amount)),
            "direction": direction,
            "create_time": event_time,
            "tenant_id": tenant_id,
        },
    }


# ---------------------------------------------------------------------------
# Product handler
# ---------------------------------------------------------------------------

def _products_latest_state(row: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    return {
        "target_table": "vdm_t_product",
        "row": {
            "id": _hash_id(row.get("item_id")),
            "code": str(row.get("item_id", "")),
            "name": _default_field(row, "title"),
            "category": _default_field(row, "category"),
            "price": _default_field(row, "price"),
            "brand": _default_field(row, "brand"),
            "url": _default_field(row, "link"),
            "image_url": _default_field(row, "image"),
            "description": _default_field(row, "description"),
            "currency": _default_field(row, "currency"),
            "status": _default_field(row, "availability"),
            "create_time": row.get("available_from"),
            "update_time": row.get("event_time"),  # changed from available_to
            "tenant_id": tenant_id,
        },
    }


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

_HANDLERS: dict[str, Any] = {
    "email_sends": _email_send_event,
    "email_opens": _email_open_event,
    "email_clicks": _email_click_event,
    "email_bounces": _email_bounce_event,
    "email_unsubscribes": _email_unsubscribe_event,
    "email_campaigns_v2": _campaign_to_activity,
    "inapp_campaigns": _campaign_to_activity,
    "inbox_campaigns": _campaign_to_activity,
    "push_campaigns": _campaign_to_activity,
    "sms_campaigns": _campaign_to_activity,
    "wallet_campaigns": _campaign_to_activity,
    "loyalty_contact_points_state_latest": _loyalty_points_state,
    "loyalty_points_earned_redeemed": _loyalty_points_earned_redeemed,
    "products_latest_state": _products_latest_state,
}
