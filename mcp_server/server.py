"""SocialHub.AI MCP Server.

Exposes SocialHub analytics capabilities as MCP tools for external AI agents.
Runs over stdio (Claude Desktop compatible) or SSE (HTTP agents).

Usage:
    python -m mcp_server                        # stdio (default)
    python -m mcp_server --transport sse --port 8090
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server import Server
from mcp.types import Tool, TextContent, CallToolResult

from cli.api.mcp_client import MCPError
from cli.config import load_config
from cli.commands.analytics import (
    _get_mcp_overview,
    _get_mcp_customers,
    _get_mcp_customer_source,
    _get_mcp_customer_gender,
    _get_mcp_orders,
    _get_mcp_order_returns,
    _get_mcp_retention,
    _get_mcp_funnel,
    _get_mcp_rfm,
    _get_mcp_ltv,
    _get_mcp_campaigns,
    _get_mcp_campaign_detail,
    _get_mcp_campaign_roi,
    _get_mcp_canvas,
    _get_mcp_points,
    _get_mcp_points_at_risk,
    _get_mcp_coupons,
    _get_mcp_coupon_lift,
    _get_mcp_coupon_anomaly,
    _get_mcp_products,
    _get_mcp_stores,
    _get_mcp_anomaly,
    _get_mcp_loyalty,
    _get_mcp_repurchase,
    _get_mcp_repurchase_path,
)
from cli.commands.segments import _mcp_segment_analyze

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS: list[Tool] = [
    Tool(
        name="analytics_overview",
        description=(
            "Business analytics overview: GMV, order count, AOV, active customers, "
            "new customers, coupon redemption rate, points issued/consumed, message delivery rate. "
            "Optionally compares current period vs prior same-length period."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["today", "7d", "30d", "90d", "365d", "ytd"],
                    "default": "30d",
                    "description": "Analysis window",
                },
                "compare": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include prior-period comparison",
                },
            },
        },
    ),
    Tool(
        name="analytics_customers",
        description=(
            "Customer base metrics: total registered, total buyers, active buyers, "
            "member vs non-member split. Optionally includes acquisition channel source "
            "breakdown and gender distribution."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["today", "7d", "30d", "90d", "365d", "ytd"],
                    "default": "30d",
                },
                "include_source": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include acquisition channel breakdown",
                },
                "include_gender": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include gender distribution",
                },
            },
        },
    ),
    Tool(
        name="analytics_orders",
        description=(
            "Order metrics: GMV, order count, AOV, unique customers, new vs returning buyer split. "
            "Optionally group by channel, province, or product. Optionally include return/refund analysis."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["today", "7d", "30d", "90d", "365d", "ytd"],
                    "default": "30d",
                },
                "group_by": {
                    "type": "string",
                    "enum": ["channel", "province", "product"],
                    "description": "Group results by this dimension. Omit for overall totals.",
                },
                "include_returns": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include return/refund breakdown by channel",
                },
            },
        },
    ),
    Tool(
        name="analytics_retention",
        description=(
            "Cohort-based customer retention. For each day window, shows what percentage of "
            "customers who bought N days ago made another purchase. "
            "Use to measure how well the business retains buyers over time."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "days": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 1, "maximum": 365},
                    "default": [7, 14, 30],
                    "description": "Retention window sizes in days",
                },
            },
        },
    ),
    Tool(
        name="analytics_funnel",
        description=(
            "Customer lifecycle funnel: New → First Purchase → Repeat → Loyal → At-Risk → Churned. "
            "Shows headcount at each stage and conversion rate between stages. "
            "Use to identify where customers drop off."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["today", "7d", "30d", "90d", "365d", "ytd"],
                    "default": "30d",
                },
            },
        },
    ),
    Tool(
        name="analytics_rfm",
        description=(
            "RFM (Recency, Frequency, Monetary) customer segmentation. "
            "Returns segment distribution with average spend, frequency, and recency per bucket. "
            "Use segment_filter to drill into one segment. Use top_limit to list highest-scoring customers."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "segment_filter": {
                    "type": "string",
                    "description": "Filter to a specific RFM segment code (e.g. 'high_value', 'at_risk'). Omit for all segments.",
                },
                "top_limit": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 500,
                    "default": 0,
                    "description": "Return top N customers by RFM score. 0 = distribution only.",
                },
            },
        },
    ),
    Tool(
        name="analytics_ltv",
        description=(
            "Cohort Lifetime Value. Groups customers by first-order month and tracks GMV "
            "per customer in subsequent months. Use to compare whether newer cohorts are "
            "more or less valuable than older ones."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "cohort_months": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 24,
                    "default": 6,
                    "description": "How many past months of cohorts to include",
                },
                "follow_months": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 12,
                    "default": 3,
                    "description": "How many months to track each cohort after acquisition",
                },
            },
        },
    ),
    Tool(
        name="analytics_campaigns",
        description=(
            "Marketing campaign analytics. Lists campaigns with funnel metrics "
            "(target/reach/click/convert) and reward metrics (points, coupons, messages). "
            "Set campaign_id for a single campaign. Set canvas_id for per-node journey funnel."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["today", "7d", "30d", "90d", "365d", "ytd"],
                    "default": "30d",
                },
                "campaign_id": {
                    "type": "string",
                    "description": "Filter to this specific campaign ID",
                },
                "name_filter": {
                    "type": "string",
                    "description": "Filter campaigns by name (partial match)",
                },
                "canvas_id": {
                    "type": "string",
                    "description": "If set, return per-node journey funnel for this canvas campaign",
                },
                "include_roi": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include revenue attribution (GMV generated by campaign participants)",
                },
                "attribution_window_days": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 90,
                    "default": 30,
                    "description": "Days after campaign conversion to attribute revenue (used when include_roi=true)",
                },
            },
        },
    ),
    Tool(
        name="analytics_points",
        description=(
            "Points program analytics: earned, redeemed, expired, redemption rate, active members. "
            "Optionally includes operation-type breakdown (purchase earn, promotion, redeem gift, expired). "
            "Optionally lists at-risk members whose points are expiring soon."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["today", "7d", "30d", "90d", "365d", "ytd"],
                    "default": "30d",
                },
                "include_breakdown": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include per-operation-type earn/redeem breakdown",
                },
                "expiring_within_days": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 365,
                    "default": 0,
                    "description": "If > 0, include members whose points expire within N days",
                },
                "at_risk_limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 500,
                    "default": 100,
                    "description": "Max at-risk members to return (requires expiring_within_days > 0)",
                },
            },
        },
    ),
    Tool(
        name="analytics_coupons",
        description=(
            "Coupon analytics: issued, redeemed, expired, redemption rate, total face value redeemed. "
            "Optionally includes per-rule ROI breakdown and lift analysis comparing "
            "coupon users vs non-users (AOV and repurchase rate lift)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["today", "7d", "30d", "90d", "365d", "ytd"],
                    "default": "30d",
                },
                "include_roi_breakdown": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include per-coupon-rule GMV and ROI breakdown",
                },
                "include_lift": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include lift analysis: coupon users vs non-users comparison",
                },
                "detect_anomalies": {
                    "type": "boolean",
                    "default": False,
                    "description": "Run anomaly detection on daily redemption volume (mean ± 2σ)",
                },
            },
        },
    ),
    Tool(
        name="analytics_loyalty",
        description=(
            "Loyalty program overview: member enrollment rate, tier distribution (headcount per tier), "
            "points liability in CNY equivalent, and churn risk per tier."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    Tool(
        name="analytics_products",
        description=(
            "Top products by revenue: order count, quantity, unique buyers, revenue. "
            "Optionally group by product category. Use for product performance ranking and category analysis."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["today", "7d", "30d", "90d", "365d", "ytd"],
                    "default": "30d",
                },
                "by_category": {
                    "type": "boolean",
                    "default": False,
                    "description": "Aggregate by product category instead of individual products",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 20,
                },
            },
        },
    ),
    Tool(
        name="analytics_stores",
        description=(
            "Store-level performance: GMV, order count, unique customers, repeat purchase rate per store. "
            "Ranked by GMV. Use to identify top-performing stores and laggards."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["today", "7d", "30d", "90d", "365d", "ytd"],
                    "default": "30d",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 20,
                },
            },
        },
    ),
    Tool(
        name="analytics_repurchase",
        description=(
            "Repurchase behavior: repurchase rate %, GMV contribution by new vs returning buyers, "
            "median days from first to second order, distribution of first-to-second order timing."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["today", "7d", "30d", "90d", "365d", "ytd"],
                    "default": "90d",
                },
            },
        },
    ),
    Tool(
        name="analytics_anomaly",
        description=(
            "Statistical anomaly detection on daily business metrics. "
            "Uses mean ± 2σ baseline to flag abnormal days in the detection window. "
            "Metrics: gmv (gross revenue), orders (order count), aov (average order value), new_buyers."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "metric": {
                    "type": "string",
                    "enum": ["gmv", "orders", "aov", "new_buyers"],
                    "description": "The KPI metric to monitor",
                },
                "lookback_days": {
                    "type": "integer",
                    "minimum": 7,
                    "maximum": 180,
                    "default": 30,
                    "description": "Days of history to compute baseline mean and σ",
                },
                "detect_days": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 30,
                    "default": 7,
                    "description": "How many recent days to check for anomalies",
                },
            },
            "required": ["metric"],
        },
    ),
    Tool(
        name="analytics_segment",
        description=(
            "Purchase behavior analysis for customers in a segment. "
            "Computes buy rate, GMV, AOV, and orders per buyer for segment members. "
            "Also returns top buyers list. Results are labeled 'sampled' if segment is large."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "group_id": {
                    "type": "string",
                    "description": "Segment / customer group ID",
                },
                "period": {
                    "type": "string",
                    "enum": ["7d", "30d", "90d", "365d"],
                    "default": "30d",
                },
                "max_members": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 2000,
                    "default": 500,
                    "description": "Max members to sample for analysis",
                },
            },
            "required": ["group_id"],
        },
    ),
]


# ---------------------------------------------------------------------------
# Tool name → handler mapping
# ---------------------------------------------------------------------------

def _ok(data: Any) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, default=str, ensure_ascii=False))]


def _err(msg: str) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({"error": msg}))]


def _handle_analytics_overview(args: dict) -> list[TextContent]:
    config = load_config()
    mcp_cfg = _mcp_config(config)
    period = args.get("period", "30d")
    data = _get_mcp_overview(mcp_cfg, period)
    return _ok({"period": period, **data})


def _handle_analytics_customers(args: dict) -> list[TextContent]:
    config = load_config()
    mcp_cfg = _mcp_config(config)
    period = args.get("period", "30d")
    result: dict[str, Any] = {}
    result["customers"] = _get_mcp_customers(mcp_cfg, period, "all")
    if args.get("include_source"):
        result["source"] = _get_mcp_customer_source(mcp_cfg, period)
    if args.get("include_gender"):
        result["gender"] = _get_mcp_customer_gender(mcp_cfg)
    return _ok(result)


def _handle_analytics_orders(args: dict) -> list[TextContent]:
    config = load_config()
    mcp_cfg = _mcp_config(config)
    period = args.get("period", "30d")
    group_by = args.get("group_by")
    result: dict[str, Any] = {}
    result["orders"] = _get_mcp_orders(mcp_cfg, period, "sales", group_by)
    if args.get("include_returns"):
        result["returns"] = _get_mcp_order_returns(mcp_cfg, period)
    return _ok(result)


def _handle_analytics_retention(args: dict) -> list[TextContent]:
    config = load_config()
    mcp_cfg = _mcp_config(config)
    days = args.get("days", [7, 14, 30])
    data = _get_mcp_retention(mcp_cfg, days)
    return _ok(data)


def _handle_analytics_funnel(args: dict) -> list[TextContent]:
    config = load_config()
    mcp_cfg = _mcp_config(config)
    period = args.get("period", "30d")
    data = _get_mcp_funnel(mcp_cfg, period)
    return _ok(data)


def _handle_analytics_rfm(args: dict) -> list[TextContent]:
    config = load_config()
    mcp_cfg = _mcp_config(config)
    segment_filter = args.get("segment_filter", "")
    top_limit = args.get("top_limit", 0)
    data = _get_mcp_rfm(mcp_cfg, limit=top_limit, segment_filter=segment_filter)
    return _ok(data)


def _handle_analytics_ltv(args: dict) -> list[TextContent]:
    config = load_config()
    mcp_cfg = _mcp_config(config)
    cohort_months = args.get("cohort_months", 6)
    follow_months = args.get("follow_months", 3)
    data = _get_mcp_ltv(mcp_cfg, cohort_months, follow_months)
    return _ok(data)


def _handle_analytics_campaigns(args: dict) -> list[TextContent]:
    config = load_config()
    mcp_cfg = _mcp_config(config)
    period = args.get("period", "30d")
    campaign_id = args.get("campaign_id")
    canvas_id = args.get("canvas_id")
    result: dict[str, Any] = {}

    if canvas_id:
        result["canvas_funnel"] = _get_mcp_canvas(mcp_cfg, canvas_id)
    elif campaign_id:
        result["detail"] = _get_mcp_campaign_detail(mcp_cfg, campaign_id)
    else:
        result["campaigns"] = _get_mcp_campaigns(
            mcp_cfg, period,
            campaign_id=args.get("campaign_id"),
            name=args.get("name_filter"),
        )

    if args.get("include_roi"):
        window = args.get("attribution_window_days", 30)
        result["roi"] = _get_mcp_campaign_roi(mcp_cfg, period, window)

    return _ok(result)


def _handle_analytics_points(args: dict) -> list[TextContent]:
    config = load_config()
    mcp_cfg = _mcp_config(config)
    period = args.get("period", "30d")
    expiring_days = args.get("expiring_within_days", 0)
    breakdown = args.get("include_breakdown", False)
    at_risk_limit = args.get("at_risk_limit", 100)

    result: dict[str, Any] = {}
    result["points"] = _get_mcp_points(mcp_cfg, period, expiring_days=expiring_days, breakdown=breakdown)
    if expiring_days > 0:
        result["at_risk_members"] = _get_mcp_points_at_risk(mcp_cfg, expiring_days, limit=at_risk_limit)
    return _ok(result)


def _handle_analytics_coupons(args: dict) -> list[TextContent]:
    config = load_config()
    mcp_cfg = _mcp_config(config)
    period = args.get("period", "30d")
    roi = args.get("include_roi_breakdown", False)

    result: dict[str, Any] = {}
    result["coupons"] = _get_mcp_coupons(mcp_cfg, period, roi=roi)
    if args.get("include_lift"):
        result["lift"] = _get_mcp_coupon_lift(mcp_cfg, period)
    if args.get("detect_anomalies"):
        result["anomaly"] = _get_mcp_coupon_anomaly(mcp_cfg)
    return _ok(result)


def _handle_analytics_loyalty(args: dict) -> list[TextContent]:
    config = load_config()
    mcp_cfg = _mcp_config(config)
    data = _get_mcp_loyalty(mcp_cfg)
    return _ok(data)


def _handle_analytics_products(args: dict) -> list[TextContent]:
    config = load_config()
    mcp_cfg = _mcp_config(config)
    period = args.get("period", "30d")
    by_category = args.get("by_category", False)
    limit = args.get("limit", 20)
    data = _get_mcp_products(mcp_cfg, period, by_category, limit)
    return _ok(data)


def _handle_analytics_stores(args: dict) -> list[TextContent]:
    config = load_config()
    mcp_cfg = _mcp_config(config)
    period = args.get("period", "30d")
    limit = args.get("limit", 20)
    data = _get_mcp_stores(mcp_cfg, period, limit)
    return _ok(data)


def _handle_analytics_repurchase(args: dict) -> list[TextContent]:
    config = load_config()
    mcp_cfg = _mcp_config(config)
    period = args.get("period", "90d")
    data = _get_mcp_repurchase(mcp_cfg, period)
    return _ok(data)


def _handle_analytics_anomaly(args: dict) -> list[TextContent]:
    config = load_config()
    mcp_cfg = _mcp_config(config)
    metric = args["metric"]
    lookback = args.get("lookback_days", 30)
    detect = args.get("detect_days", 7)
    data = _get_mcp_anomaly(mcp_cfg, metric, lookback, detect)
    return _ok(data)


def _handle_analytics_segment(args: dict) -> list[TextContent]:
    config = load_config()
    mcp_cfg = _mcp_config(config)
    group_id = str(args["group_id"])
    period = args.get("period", "30d")
    max_members = args.get("max_members", 500)
    data = _mcp_segment_analyze(mcp_cfg, group_id, period, max_members)
    return _ok(data)


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_HANDLERS = {
    "analytics_overview": _handle_analytics_overview,
    "analytics_customers": _handle_analytics_customers,
    "analytics_orders": _handle_analytics_orders,
    "analytics_retention": _handle_analytics_retention,
    "analytics_funnel": _handle_analytics_funnel,
    "analytics_rfm": _handle_analytics_rfm,
    "analytics_ltv": _handle_analytics_ltv,
    "analytics_campaigns": _handle_analytics_campaigns,
    "analytics_points": _handle_analytics_points,
    "analytics_coupons": _handle_analytics_coupons,
    "analytics_loyalty": _handle_analytics_loyalty,
    "analytics_products": _handle_analytics_products,
    "analytics_stores": _handle_analytics_stores,
    "analytics_repurchase": _handle_analytics_repurchase,
    "analytics_anomaly": _handle_analytics_anomaly,
    "analytics_segment": _handle_analytics_segment,
}


# ---------------------------------------------------------------------------
# Config helper
# ---------------------------------------------------------------------------

def _mcp_config(config: Any) -> Any:
    """Extract MCPConfig from app config."""
    from cli.api.mcp_client import MCPConfig as ClientMCPConfig
    return ClientMCPConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )


# ---------------------------------------------------------------------------
# Server factory
# ---------------------------------------------------------------------------

def create_server() -> Server:
    server = Server("socialhub-analytics")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        handler = _HANDLERS.get(name)
        if handler is None:
            return _err(f"Unknown tool: {name}")
        try:
            return handler(arguments or {})
        except MCPError as e:
            logger.error("MCP database error in %s: %s", name, e)
            return _err(f"Database error: {e}")
        except ValueError as e:
            return _err(f"Invalid input: {e}")
        except Exception as e:
            logger.exception("Unexpected error in tool %s", name)
            return _err(f"Unexpected error: {e}")

    return server
