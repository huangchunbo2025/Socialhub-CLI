"""BigQuery → datanow_.t_retailevent slot mapping rules.

Reference: docs/emarsys-integration/sync-mapping-2.md
"""

from __future__ import annotations

from typing import Any

# Tables with DataNow mapping — maps table_name → event_key.
DATANOW_TABLES: dict[str, str] = {
    # Email
    "email_sends":                         "$emarsys_email_send",
    "email_opens":                         "$emarsys_email_open",
    "email_clicks":                        "$emarsys_email_click",
    "email_bounces":                       "$emarsys_email_bounce",
    "email_cancels":                       "$emarsys_email_cancel",
    "email_complaints":                    "$emarsys_email_complaint",
    "email_unsubscribes":                  "$emarsys_email_unsubscribe",
    # Web Push
    "web_push_sends":                      "$emarsys_web_push_send",
    "web_push_clicks":                     "$emarsys_web_push_click",
    "web_push_not_sends":                  "$emarsys_web_push_not_send",
    "web_push_custom_events":              "$emarsys_web_push_custom_event",
    # Mobile Push (new naming)
    "push_sends":                          "$emarsys_push_send",
    "push_not_sends":                      "$emarsys_push_not_send",
    "push_opens":                          "$emarsys_push_open",
    "push_custom_events":                  "$emarsys_push_custom_event",
    # In-App
    "inapp_views":                         "$emarsys_inapp_view",
    "inapp_clicks":                        "$emarsys_inapp_click",
    "inapp_audience_changes":              "$emarsys_inapp_audience_change",
    # Inbox
    "inbox_sends":                         "$emarsys_inbox_send",
    "inbox_not_sends":                     "$emarsys_inbox_not_send",
    "inbox_tag_changes":                   "$emarsys_inbox_tag_change",
    # Wallet
    "wallet_passes":                       "$emarsys_wallet_pass",
    # SMS
    "sms_sends":                           "$emarsys_sms_send",
    "sms_send_reports":                    "$emarsys_sms_send_report",
    "sms_clicks":                          "$emarsys_sms_click",
    "sms_unsubscribes":                    "$emarsys_sms_unsubscribe",
    # Web Channel
    "webchannel_events_enhanced":          "$emarsys_webchannel_event",
    # Sessions
    "sessions":                            "$emarsys_session",
    "session_categories":                  "$emarsys_session_category",
    "session_purchases":                   "$emarsys_session_purchase",
    "session_tags":                        "$emarsys_session_tag",
    "session_views":                       "$emarsys_session_view",
    # Events
    "external_events":                     "$emarsys_external_event",
    "custom_events":                       "$emarsys_custom_event",
    "engagement_events":                   "$emarsys_engagement_event",
    # Loyalty
    "loyalty_contact_points_state_latest": "$emarsys_loyalty_points_state",
    "loyalty_points_earned_redeemed":      "$emarsys_loyalty_points_transaction",
    "loyalty_vouchers":                    "$emarsys_loyalty_voucher",
    "loyalty_exclusive_access":            "$emarsys_loyalty_exclusive_access",
    "loyalty_actions":                     "$emarsys_loyalty_action",
    "loyalty_referral_codes":              "$emarsys_loyalty_referral_code",
    "loyalty_referral_purchases":          "$emarsys_loyalty_referral_purchase",
    # Analytics
    "revenue_attribution":                 "$emarsys_revenue_attribution",
    "si_contacts":                         "$emarsys_si_contact",
    # Conversation
    "conversation_opens":                  "$emarsys_conversation_open",
    "conversation_deliveries":             "$emarsys_conversation_delivery",
    "conversation_clicks":                 "$emarsys_conversation_click",
    "conversation_sends":                  "$emarsys_conversation_send",
}

# BQ source field name for each slot.
_TABLE_SLOT_SOURCE: dict[str, dict[str, str]] = {
    "email_sends": {
        "text1": "contact_id", "dimension1": "campaign_type", "dimension2": "domain",
        "bigint1": "campaign_id", "bigint2": "message_id", "bigint3": "launch_id",
        "datetime1": "loaded_at",
    },
    "email_opens": {
        "text1": "contact_id", "text2": "ip", "text3": "md5", "text4": "uid",
        "text5": "user_agent", "dimension1": "campaign_type", "dimension2": "domain",
        "dimension3": "generated_from", "dimension4": "geo_country_iso_code",
        "dimension5": "platform", "dimension6": "is_mobile",
        "bigint1": "campaign_id", "bigint2": "message_id", "bigint3": "launch_id",
        "datetime1": "email_sent_at", "datetime2": "loaded_at", "context": "geo",
    },
    "email_clicks": {
        "text1": "contact_id", "text2": "url", "text3": "md5", "text4": "ip",
        "text5": "user_agent", "dimension1": "campaign_type", "dimension2": "is_img",
        "dimension3": "link_name", "dimension4": "geo_country_iso_code", "dimension5": "platform",
        "bigint1": "campaign_id", "bigint2": "message_id", "bigint3": "launch_id",
        "bigint4": "link_id", "bigint5": "category_id",
        "datetime1": "email_sent_at", "datetime2": "loaded_at", "context": "geo",
    },
    "email_bounces": {
        "text1": "contact_id", "text2": "dsn_reason",
        "dimension1": "campaign_type", "dimension2": "domain", "dimension3": "bounce_type",
        "bigint1": "campaign_id", "bigint2": "message_id", "bigint3": "launch_id",
        "datetime1": "email_sent_at", "datetime2": "loaded_at",
    },
    "email_cancels": {
        "text1": "contact_id", "dimension1": "campaign_type", "dimension2": "domain",
        "bigint1": "campaign_id", "bigint2": "message_id",
    },
    "email_complaints": {
        "text1": "contact_id", "dimension1": "campaign_type", "dimension2": "domain",
        "bigint1": "campaign_id", "bigint2": "message_id", "bigint3": "launch_id",
    },
    "email_unsubscribes": {
        "text1": "contact_id", "dimension1": "campaign_type", "dimension2": "domain",
        "dimension3": "source", "bigint1": "campaign_id", "bigint2": "message_id",
        "bigint3": "launch_id", "datetime1": "email_sent_at", "datetime2": "loaded_at",
    },
    "web_push_sends": {
        "text1": "contact_id", "text2": "push_token", "text3": "client_id",
        "dimension1": "platform", "dimension2": "domain", "dimension3": "domain_code",
        "context": "treatments",
    },
    "web_push_clicks": {
        "text1": "contact_id", "text2": "user_agent",
        "dimension1": "platform", "dimension2": "domain",
    },
    "web_push_not_sends": {
        "text1": "contact_id", "text2": "push_token", "text3": "client_id",
        "dimension1": "platform", "dimension2": "reason", "dimension3": "domain_code",
    },
    "web_push_custom_events": {
        "text1": "contact_id", "text2": "event_name",
        "dimension1": "platform", "context": "event_data",
    },
    "push_sends": {
        "text1": "contact_id", "text2": "push_token", "text3": "hardware_id",
        "text4": "application_code", "dimension1": "platform", "dimension2": "target",
        "dimension3": "source.type", "bigint1": "campaign_id",
        "bigint2": "application_id", "bigint3": "program_id", "context": "treatments",
    },
    "push_not_sends": {
        "text1": "contact_id", "text2": "push_token", "text3": "hardware_id",
        "text4": "application_code", "dimension1": "platform", "dimension2": "reason",
        "dimension3": "source.type", "bigint1": "campaign_id", "bigint2": "application_id",
    },
    "push_opens": {
        "text1": "contact_id", "text2": "push_token",
        "dimension1": "platform", "dimension2": "target",
        "bigint1": "campaign_id", "bigint2": "application_id",
    },
    "push_custom_events": {
        "text1": "contact_id", "text2": "event_name",
        "dimension1": "platform", "bigint1": "application_id", "context": "event_data",
    },
    "inapp_views": {
        "text1": "contact_id", "text2": "user_agent",
        "dimension1": "campaign_type", "dimension2": "platform", "dimension3": "is_mobile",
        "bigint1": "campaign_id", "context": "geo",
    },
    "inapp_clicks": {
        "text1": "contact_id", "text2": "url", "text3": "user_agent",
        "dimension1": "campaign_type", "dimension2": "button_id", "dimension3": "is_mobile",
        "bigint1": "campaign_id",
    },
    "inapp_audience_changes": {
        "text1": "contact_id", "dimension1": "action", "bigint1": "campaign_id",
    },
    "inbox_sends": {
        "text1": "contact_id", "text2": "inbox_id",
        "dimension1": "campaign_type", "dimension2": "channel",
        "bigint1": "campaign_id", "bigint2": "message_id",
    },
    "inbox_not_sends": {
        "text1": "contact_id", "text2": "inbox_id",
        "dimension1": "campaign_type", "dimension2": "reason", "bigint1": "campaign_id",
    },
    "inbox_tag_changes": {
        "text1": "contact_id", "text2": "tag", "text3": "inbox_id",
        "dimension1": "action", "bigint1": "message_id",
    },
    "wallet_passes": {
        "text1": "contact_id", "text2": "pass_id", "text3": "campaign_id",
        "dimension1": "status", "dimension2": "pass_type",
        "date1": "valid_from", "date2": "valid_to", "context": "field_updates",
    },
    "sms_sends": {
        "text1": "contact_id", "text2": "message_id",
        "bigint1": "campaign_id", "bigint2": "launch_id", "bigint3": "program_id",
        "context": "treatments",
    },
    "sms_send_reports": {
        "text1": "contact_id", "dimension1": "status", "dimension2": "reject_reason",
        "bigint1": "campaign_id", "bigint2": "launch_id",
    },
    "sms_clicks": {
        "text1": "contact_id", "text2": "user_agent",
        "dimension1": "is_dry_run", "bigint1": "campaign_id",
        "bigint2": "launch_id", "bigint3": "link_id",
    },
    "sms_unsubscribes": {
        "text1": "contact_id", "dimension1": "source",
        "bigint1": "campaign_id", "bigint2": "launch_id",
    },
    "webchannel_events_enhanced": {
        "text1": "contact_id", "text2": "user_agent", "text3": "md5",
        "text4": "campaign_id", "text5": "ad_id",
        "dimension1": "event_type", "dimension2": "platform", "dimension3": "is_mobile",
        "context": "tracking_data",
    },
    "sessions": {
        "text1": "contact_id", "text2": "user_id",
        "dimension1": "user_id_type", "dimension2": "currency",
        "datetime1": "start_time", "datetime2": "end_time", "context": "purchases",
    },
    "session_categories": {
        "text1": "contact_id", "text2": "user_id",
        "dimension1": "category", "dimension2": "user_id_type",
    },
    "session_purchases": {
        "text1": "contact_id", "text2": "user_id", "text3": "order_id",
        "dimension1": "user_id_type", "context": "items",
    },
    "session_tags": {
        "text1": "contact_id", "text2": "user_id",
        "dimension1": "tag", "dimension2": "user_id_type", "context": "attributes",
    },
    "session_views": {
        "text1": "contact_id", "text2": "user_id", "text3": "item_id",
        "dimension1": "user_id_type",
    },
    "external_events": {
        "text1": "contact_id", "text2": "event_id", "bigint1": "event_type_id",
    },
    "custom_events": {
        "text1": "contact_id", "text2": "event_id",
        "dimension1": "event_type", "context": "related_data",
    },
    "engagement_events": {
        "text1": "contact_id", "text2": "event_id", "text3": "event_type",
        "bigint1": "customer_id", "context": "event_data",
    },
    "loyalty_contact_points_state_latest": {
        "text1": "contact_id", "dimension1": "tier_name", "dimension2": "currency_code",
        "bigint1": "total_points", "bigint2": "available_points",
        "bigint3": "pending_points", "bigint4": "spent_points",
    },
    "loyalty_points_earned_redeemed": {
        "text1": "contact_id", "text2": "transaction_id", "text3": "source.type_name",
        "dimension1": "type", "dimension2": "source.type",
        "dimension3": "source.expiration_date", "dimension4": "external_source.code",
        "dimension5": "source.category_name",
        "bigint1": "amount", "bigint2": "balance", "bigint3": "total_points",
        "context": "labels",
    },
    "loyalty_vouchers": {
        "text1": "contact_id", "text2": "voucher_code", "text3": "voucher_id",
        "dimension1": "type", "dimension2": "status",
        "bigint1": "amount", "bigint2": "redeemable_points",
        "date1": "valid_from", "date2": "valid_to", "datetime1": "used_at",
    },
    "loyalty_exclusive_access": {
        "text1": "contact_id", "text2": "item_id",
        "dimension1": "status", "date1": "valid_from", "date2": "valid_to",
    },
    "loyalty_actions": {
        "text1": "contact_id", "text2": "action_id",
        "dimension1": "status", "dimension2": "type", "bigint1": "points",
    },
    "loyalty_referral_codes": {
        "text1": "contact_id", "text2": "referral_code", "dimension1": "status",
    },
    "loyalty_referral_purchases": {
        "text1": "contact_id", "text2": "referral_code",
        "dimension1": "status", "bigint1": "purchase_value", "bigint2": "reward_points",
    },
    "revenue_attribution": {
        "text1": "contact_id", "text2": "order_id",
        "bigint1": "items.item_id", "decimal1": "items.price", "decimal2": "items.quantity",
        "context": "treatments",
    },
    "si_contacts": {
        "text1": "contact_id", "text2": "si_contact_id", "text3": "contact_external_id",
        "dimension1": "contact_source", "dimension2": "customer_lifecycle_status",
        "dimension3": "buyer_status", "dimension4": "lead_lifecycle_status",
        "dimension5": "is_generated", "bigint1": "number_of_purchases",
        "decimal1": "turnover", "decimal2": "average_order_value",
        "decimal3": "average_future_spend",
        "date1": "registered_on", "date2": "last_order_date",
        "date3": "last_engagement_date", "date4": "last_response_date",
    },
    "conversation_opens": {
        "text1": "contact_id", "text2": "message_id", "text3": "conversation_id",
        "dimension1": "program_type", "bigint1": "program_id",
    },
    "conversation_deliveries": {
        "text1": "contact_id", "text2": "message_id", "text3": "conversation_id",
        "text4": "error_message", "dimension1": "status", "dimension2": "error_type",
        "dimension3": "program_type", "bigint1": "program_id",
    },
    "conversation_clicks": {
        "text1": "contact_id", "text2": "message_id", "text3": "conversation_id",
        "text4": "user_agent", "dimension1": "program_type", "bigint1": "program_id",
    },
    "conversation_sends": {
        "text1": "contact_id", "text2": "message_id", "text3": "conversation_id",
        "dimension1": "program_type", "bigint1": "program_id",
    },
}

# Semantic view column aliases — used by view_manager.py for CREATE OR REPLACE VIEW DDL.
SLOT_MAPS: dict[str, dict[str, str]] = {
    "$emarsys_email_send": {
        "text1": "contact_id", "dimension1": "campaign_type", "dimension2": "domain",
        "bigint1": "campaign_id", "bigint2": "message_id", "bigint3": "launch_id",
        "datetime1": "loaded_at",
    },
    "$emarsys_email_open": {
        "text1": "contact_id", "text2": "ip", "text3": "md5", "text4": "uid",
        "text5": "user_agent", "dimension1": "campaign_type", "dimension2": "domain",
        "dimension3": "generated_from", "dimension4": "geo_country_iso_code",
        "dimension5": "platform", "dimension6": "is_mobile",
        "bigint1": "campaign_id", "bigint2": "message_id", "bigint3": "launch_id",
        "datetime1": "email_sent_at", "datetime2": "loaded_at", "context": "geo",
    },
    "$emarsys_email_click": {
        "text1": "contact_id", "text2": "url", "text3": "md5", "text4": "ip",
        "text5": "user_agent", "dimension1": "campaign_type", "dimension2": "is_img",
        "dimension3": "link_name", "dimension4": "geo_country_iso_code", "dimension5": "platform",
        "bigint1": "campaign_id", "bigint2": "message_id", "bigint3": "launch_id",
        "bigint4": "link_id", "bigint5": "category_id",
        "datetime1": "email_sent_at", "datetime2": "loaded_at", "context": "geo",
    },
    "$emarsys_email_bounce": {
        "text1": "contact_id", "text2": "dsn_reason",
        "dimension1": "campaign_type", "dimension2": "domain", "dimension3": "bounce_type",
        "bigint1": "campaign_id", "bigint2": "message_id", "bigint3": "launch_id",
        "datetime1": "email_sent_at", "datetime2": "loaded_at",
    },
    "$emarsys_email_cancel": {
        "text1": "contact_id", "dimension1": "campaign_type", "dimension2": "domain",
        "bigint1": "campaign_id", "bigint2": "message_id",
    },
    "$emarsys_email_complaint": {
        "text1": "contact_id", "dimension1": "campaign_type", "dimension2": "domain",
        "bigint1": "campaign_id", "bigint2": "message_id", "bigint3": "launch_id",
    },
    "$emarsys_email_unsubscribe": {
        "text1": "contact_id", "dimension1": "campaign_type", "dimension2": "domain",
        "dimension3": "source", "bigint1": "campaign_id", "bigint2": "message_id",
        "bigint3": "launch_id", "datetime1": "email_sent_at", "datetime2": "loaded_at",
    },
    "$emarsys_web_push_send": {
        "text1": "contact_id", "text2": "push_token", "text3": "client_id",
        "dimension1": "platform", "dimension2": "domain", "dimension3": "domain_code",
        "context": "treatments",
    },
    "$emarsys_web_push_click": {
        "text1": "contact_id", "text2": "user_agent",
        "dimension1": "platform", "dimension2": "domain",
    },
    "$emarsys_web_push_not_send": {
        "text1": "contact_id", "text2": "push_token", "text3": "client_id",
        "dimension1": "platform", "dimension2": "reason", "dimension3": "domain_code",
    },
    "$emarsys_web_push_custom_event": {
        "text1": "contact_id", "text2": "event_name",
        "dimension1": "platform", "context": "event_data",
    },
    "$emarsys_push_send": {
        "text1": "contact_id", "text2": "push_token", "text3": "hardware_id",
        "text4": "application_code", "dimension1": "platform", "dimension2": "target",
        "dimension3": "source_type", "bigint1": "campaign_id",
        "bigint2": "application_id", "bigint3": "program_id", "context": "treatments",
    },
    "$emarsys_push_not_send": {
        "text1": "contact_id", "text2": "push_token", "text3": "hardware_id",
        "text4": "application_code", "dimension1": "platform", "dimension2": "reason",
        "dimension3": "source_type", "bigint1": "campaign_id", "bigint2": "application_id",
    },
    "$emarsys_push_open": {
        "text1": "contact_id", "text2": "push_token",
        "dimension1": "platform", "dimension2": "target",
        "bigint1": "campaign_id", "bigint2": "application_id",
    },
    "$emarsys_push_custom_event": {
        "text1": "contact_id", "text2": "event_name",
        "dimension1": "platform", "bigint1": "application_id", "context": "event_data",
    },
    "$emarsys_inapp_view": {
        "text1": "contact_id", "text2": "user_agent",
        "dimension1": "campaign_type", "dimension2": "platform", "dimension3": "is_mobile",
        "bigint1": "campaign_id", "context": "geo",
    },
    "$emarsys_inapp_click": {
        "text1": "contact_id", "text2": "url", "text3": "user_agent",
        "dimension1": "campaign_type", "dimension2": "button_id", "dimension3": "is_mobile",
        "bigint1": "campaign_id",
    },
    "$emarsys_inapp_audience_change": {
        "text1": "contact_id", "dimension1": "action", "bigint1": "campaign_id",
    },
    "$emarsys_inbox_send": {
        "text1": "contact_id", "text2": "inbox_id",
        "dimension1": "campaign_type", "dimension2": "channel",
        "bigint1": "campaign_id", "bigint2": "message_id",
    },
    "$emarsys_inbox_not_send": {
        "text1": "contact_id", "text2": "inbox_id",
        "dimension1": "campaign_type", "dimension2": "reason", "bigint1": "campaign_id",
    },
    "$emarsys_inbox_tag_change": {
        "text1": "contact_id", "text2": "tag", "text3": "inbox_id",
        "dimension1": "action", "bigint1": "message_id",
    },
    "$emarsys_wallet_pass": {
        "text1": "contact_id", "text2": "pass_id", "text3": "campaign_id",
        "dimension1": "status", "dimension2": "pass_type",
        "date1": "valid_from", "date2": "valid_to", "context": "field_updates",
    },
    "$emarsys_sms_send": {
        "text1": "contact_id", "text2": "message_id",
        "bigint1": "campaign_id", "bigint2": "launch_id", "bigint3": "program_id",
        "context": "treatments",
    },
    "$emarsys_sms_send_report": {
        "text1": "contact_id", "dimension1": "status", "dimension2": "reject_reason",
        "bigint1": "campaign_id", "bigint2": "launch_id",
    },
    "$emarsys_sms_click": {
        "text1": "contact_id", "text2": "user_agent",
        "dimension1": "is_dry_run", "bigint1": "campaign_id",
        "bigint2": "launch_id", "bigint3": "link_id",
    },
    "$emarsys_sms_unsubscribe": {
        "text1": "contact_id", "dimension1": "source",
        "bigint1": "campaign_id", "bigint2": "launch_id",
    },
    "$emarsys_webchannel_event": {
        "text1": "contact_id", "text2": "user_agent", "text3": "md5",
        "text4": "campaign_id", "text5": "ad_id",
        "dimension1": "event_type", "dimension2": "platform", "dimension3": "is_mobile",
        "context": "tracking_data",
    },
    "$emarsys_session": {
        "text1": "contact_id", "text2": "user_id",
        "dimension1": "user_id_type", "dimension2": "currency",
        "datetime1": "start_time", "datetime2": "end_time", "context": "purchases",
    },
    "$emarsys_session_category": {
        "text1": "contact_id", "text2": "user_id",
        "dimension1": "category", "dimension2": "user_id_type",
    },
    "$emarsys_session_purchase": {
        "text1": "contact_id", "text2": "user_id", "text3": "order_id",
        "dimension1": "user_id_type", "context": "items",
    },
    "$emarsys_session_tag": {
        "text1": "contact_id", "text2": "user_id",
        "dimension1": "tag", "dimension2": "user_id_type", "context": "attributes",
    },
    "$emarsys_session_view": {
        "text1": "contact_id", "text2": "user_id", "text3": "item_id",
        "dimension1": "user_id_type",
    },
    "$emarsys_external_event": {
        "text1": "contact_id", "text2": "event_id", "bigint1": "event_type_id",
    },
    "$emarsys_custom_event": {
        "text1": "contact_id", "text2": "event_id",
        "dimension1": "event_type", "context": "related_data",
    },
    "$emarsys_engagement_event": {
        "text1": "contact_id", "text2": "event_id", "text3": "event_type",
        "bigint1": "customer_id", "context": "event_data",
    },
    "$emarsys_loyalty_points_state": {
        "text1": "contact_id", "dimension1": "tier_name", "dimension2": "currency_code",
        "bigint1": "total_points", "bigint2": "available_points",
        "bigint3": "pending_points", "bigint4": "spent_points",
    },
    "$emarsys_loyalty_points_transaction": {
        "text1": "contact_id", "text2": "transaction_id", "text3": "source_type_name",
        "dimension1": "type", "dimension2": "source_type",
        "dimension3": "source_expiration_date", "dimension4": "external_source_code",
        "dimension5": "source_category_name",
        "bigint1": "amount", "bigint2": "balance", "bigint3": "total_points",
        "context": "labels",
    },
    "$emarsys_loyalty_voucher": {
        "text1": "contact_id", "text2": "voucher_code", "text3": "voucher_id",
        "dimension1": "type", "dimension2": "status",
        "bigint1": "amount", "bigint2": "redeemable_points",
        "date1": "valid_from", "date2": "valid_to", "datetime1": "used_at",
    },
    "$emarsys_loyalty_exclusive_access": {
        "text1": "contact_id", "text2": "item_id",
        "dimension1": "status", "date1": "valid_from", "date2": "valid_to",
    },
    "$emarsys_loyalty_action": {
        "text1": "contact_id", "text2": "action_id",
        "dimension1": "status", "dimension2": "type", "bigint1": "points",
    },
    "$emarsys_loyalty_referral_code": {
        "text1": "contact_id", "text2": "referral_code", "dimension1": "status",
    },
    "$emarsys_loyalty_referral_purchase": {
        "text1": "contact_id", "text2": "referral_code",
        "dimension1": "status", "bigint1": "purchase_value", "bigint2": "reward_points",
    },
    "$emarsys_revenue_attribution": {
        "text1": "contact_id", "text2": "order_id",
        "bigint1": "item_id", "decimal1": "item_price", "decimal2": "item_quantity",
        "context": "treatments",
    },
    "$emarsys_si_contact": {
        "text1": "contact_id", "text2": "si_contact_id", "text3": "contact_external_id",
        "dimension1": "contact_source", "dimension2": "customer_lifecycle_status",
        "dimension3": "buyer_status", "dimension4": "lead_lifecycle_status",
        "dimension5": "is_generated", "bigint1": "number_of_purchases",
        "decimal1": "turnover", "decimal2": "average_order_value",
        "decimal3": "average_future_spend",
        "date1": "registered_on", "date2": "last_order_date",
        "date3": "last_engagement_date", "date4": "last_response_date",
    },
    "$emarsys_conversation_open": {
        "text1": "contact_id", "text2": "message_id", "text3": "conversation_id",
        "dimension1": "program_type", "bigint1": "program_id",
    },
    "$emarsys_conversation_delivery": {
        "text1": "contact_id", "text2": "message_id", "text3": "conversation_id",
        "text4": "error_message", "dimension1": "status", "dimension2": "error_type",
        "dimension3": "program_type", "bigint1": "program_id",
    },
    "$emarsys_conversation_click": {
        "text1": "contact_id", "text2": "message_id", "text3": "conversation_id",
        "text4": "user_agent", "dimension1": "program_type", "bigint1": "program_id",
    },
    "$emarsys_conversation_send": {
        "text1": "contact_id", "text2": "message_id", "text3": "conversation_id",
        "dimension1": "program_type", "bigint1": "program_id",
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
        customer_code: Customer code for the ``customer_code`` field.

    Returns:
        Dict with t_retailevent fields, or None if no mapping or no event_time.
    """
    event_key = DATANOW_TABLES.get(table_name)
    if event_key is None:
        return None

    event_time = row.get("event_time")
    if event_time is None:
        return None

    slot_source = _TABLE_SLOT_SOURCE.get(table_name, {})
    result: dict[str, Any] = {
        "event_key": event_key,
        "event_type": "trace",
        "event_time": str(event_time),
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
    """Return all distinct event_keys (one per datanow table)."""
    return list(DATANOW_TABLES.values())
