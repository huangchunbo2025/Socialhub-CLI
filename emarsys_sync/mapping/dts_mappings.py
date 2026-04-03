"""BigQuery → StarRocks dts_ field mapping rules.

Each entry in DTS_TABLES maps a BQ table name (without customer suffix) to its
target StarRocks table and the transformation logic.

Reference: docs/emarsys-integration/sync-mapping.md
"""

from __future__ import annotations

import hashlib
from typing import Any

# Tables that have a dts_ mapping.  Tables NOT in this dict are skipped for dts_.
DTS_TABLES: frozenset[str] = frozenset(
    [
        "email_sends",
        "email_opens",
        "email_clicks",
        "email_bounces",
        "email_unsubscribes",
        "email_campaigns_v2",
        "loyalty_contact_points_state_latest",
        "loyalty_points_earned_redeemed",
        "products_latest_state",
    ]
)

_CAMPAIGN_TYPE_TO_BUSINESS_TYPE: dict[str, int] = {
    "batch": 1,
    "transactional": 0,
}

_TEMPLATE_TYPE_EMAIL = 2


def _hash_id(*parts: Any) -> int:
    """Generate a positive bigint sort-key from concatenated string parts."""
    raw = "||".join(str(p) for p in parts)
    digest = hashlib.md5(raw.encode()).hexdigest()  # noqa: S324 — not crypto, just ID gen
    return int(digest, 16) % (2**63 - 1)


def apply_dts_mapping(
    table_name: str, row: dict[str, Any], *, tenant_id: str
) -> dict[str, Any] | None:
    """Transform a BigQuery row into a StarRocks dts_ row.

    Args:
        table_name: BQ table name without customer_id suffix (e.g. ``email_sends``).
        row: Raw BigQuery row as dict.
        tenant_id: Target tenant identifier.

    Returns:
        Dict with keys ``target_table`` (str) and ``row`` (dict), or ``None``
        if this table has no dts_ mapping.
    """
    if table_name not in DTS_TABLES:
        return None

    handler = _HANDLERS.get(table_name)
    if handler is None:
        return None
    return handler(row, tenant_id)


# ---------------------------------------------------------------------------
# Per-table handlers
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
            "create_time": row.get("loaded_at"),
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


def _email_campaign_v2(row: dict[str, Any], tenant_id: str) -> dict[str, Any]:
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


def _loyalty_points_state(row: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    return {
        "target_table": "vdm_t_points_account",
        "row": {
            "id": _hash_id(row.get("contact_id"), row.get("plan_id")),
            "consumer_code": str(row.get("contact_id", "")),
            "plan_code": str(row.get("plan_id", "")),
            "balance": row.get("balance"),
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
    points = row.get("points", 0) or 0
    direction = 1 if float(points) >= 0 else 2
    return {
        "target_table": "vdm_t_points_record",
        "row": {
            # vdm_t_points_record uses code (string composite key) as primary key, not a bigint id
            "code": f"{contact_id}_{event_time}",
            "consumer_code": str(row.get("contact_id", "")),
            "points": abs(float(points)),
            "direction": direction,
            "create_time": row.get("event_time"),
            "tenant_id": tenant_id,
        },
    }


def _products_latest_state(row: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    return {
        "target_table": "vdm_t_product",
        "row": {
            "id": _hash_id(row.get("item_id")),
            "code": str(row.get("item_id", "")),
            "name": row.get("title"),
            "category": row.get("category"),
            "price": row.get("price"),
            "create_time": row.get("available_from"),
            "update_time": row.get("available_to"),
            "tenant_id": tenant_id,
        },
    }


_HANDLERS = {
    "email_sends": _email_send_event,
    "email_opens": _email_open_event,
    "email_clicks": _email_click_event,
    "email_bounces": _email_bounce_event,
    "email_unsubscribes": _email_unsubscribe_event,
    "email_campaigns_v2": _email_campaign_v2,
    "loyalty_contact_points_state_latest": _loyalty_points_state,
    "loyalty_points_earned_redeemed": _loyalty_points_earned_redeemed,
    "products_latest_state": _products_latest_state,
}
