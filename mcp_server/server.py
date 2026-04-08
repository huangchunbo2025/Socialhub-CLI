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
import os
import time
from collections import OrderedDict
from functools import lru_cache
from typing import Any

from mcp.server import Server
from mcp.types import Tool, TextContent, CallToolResult


from cli.api.mcp_client import MCPError
from cli.config import load_config
import threading

_config_cache: Any = None
_config_lock = threading.Lock()
_thread_local = threading.local()


class _BoundedTTLCache:
    """Bounded TTL cache using OrderedDict for LRU eviction. No external dependencies.

    maxsize=200: MCP cache keys are {tenant_id}:{tool_name}:{params_hash}; even in
    multi-tenant deployments the realistic entry count is well below 200, so LRU
    eviction is a safety net rather than a hot path.
    """

    def __init__(self, maxsize: int = 200, ttl: float = 900):
        self._store: "OrderedDict[str, tuple[list, float]]" = OrderedDict()
        self._maxsize = maxsize
        self._ttl = ttl
        self._lock = threading.Lock()

    def get(self, key: str) -> list | None:
        with self._lock:
            if key not in self._store:
                return None
            value, ts = self._store[key]
            if time.time() - ts >= self._ttl:
                del self._store[key]
                return None
            self._store.move_to_end(key)  # LRU: mark as recently used
            return value

    def set(self, key: str, value: list) -> None:
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = (value, time.time())
            if len(self._store) > self._maxsize:
                self._store.popitem(last=False)  # evict least-recently-used entry


_CACHE_TTL = 900  # seconds (15 minutes)
_cache = _BoundedTTLCache(maxsize=200, ttl=_CACHE_TTL)


@lru_cache(maxsize=256)
def _resolve_tenant_db(env_var: str, tenant_id: str, prefix: str) -> str:
    """Resolve database name for a tenant from env var or default rule.

    Env var format: DAS_DATABASE=uat:das_test,dev:das_dev
    Default: {prefix}_{tenant_id}
    """
    raw = os.getenv(env_var, "")
    for entry in raw.split(","):
        entry = entry.strip()
        if ":" in entry:
            tid, db = entry.split(":", 1)
            if tid.strip() == tenant_id:
                return db.strip()
    return f"{prefix}_{tenant_id}"


def _get_config() -> Any:
    """Return config, patched with per-request tenant_id/database if set via thread-local.

    HTTP mode: each tool call sets _thread_local.tenant_id = tid (from API Key) before
    entering the executor thread, so every handler gets a config scoped to that tenant.
    stdio mode: thread-local is not set, falls back to global config as before.
    """
    global _config_cache
    if _config_cache is None:
        with _config_lock:
            if _config_cache is None:
                _config_cache = load_config()

    tid = getattr(_thread_local, "tenant_id", None)
    if not tid:
        return _config_cache

    import copy
    patched = copy.copy(_config_cache)
    mcp = copy.copy(_config_cache.mcp)
    mcp.tenant_id = tid
    mcp.database = ""  # 上游按 tenant_id 自动路由，不传数据库名
    patched.mcp = mcp
    return patched

_analytics_loaded = False
_analytics_ready = threading.Event()

# Results cache: key -> (result, timestamp)
_cache: dict[str, tuple[list, float]] = {}
_CACHE_TTL = 900  # seconds (15 minutes)
_inflight: dict[str, threading.Event] = {}
_inflight_lock = threading.Lock()


def _cache_key(name: str, args: dict, tenant_id: str = "") -> str:
    """
    生成缓存 key。
    tenant_id 必须纳入 key，防止不同租户共享同一缓存结果（跨租户数据泄露）。
    stdio 模式下 tenant_id 来自环境变量 MCP_TENANT_ID，
    HTTP 模式下 tenant_id 来自 auth 中间件注入的 ContextVar。
    """
    return f"{tenant_id}:{name}:{json.dumps(args, sort_keys=True)}"


def _get_cached_result(key: str) -> list | None:
    cached = _cache.get(key)
    if cached and time.time() - cached[1] < _CACHE_TTL:
        return cached[0]
    return None


def _run_with_cache(name: str, args: dict, tenant_id: str, compute_fn) -> list:
    """Reuse cached or in-flight work for identical tool requests."""
    key = _cache_key(name, args, tenant_id)
    cached = _get_cached_result(key)
    if cached is not None:
        logger.info("MCP tool cache hit: %s", name)
        return cached

    with _inflight_lock:
        event = _inflight.get(key)
        if event is None:
            event = threading.Event()
            _inflight[key] = event
            is_owner = True
        else:
            is_owner = False

    if not is_owner:
        logger.info("MCP tool waiting on in-flight result: %s", name)
        if event.wait(timeout=180):
            cached = _get_cached_result(key)
            if cached is not None:
                logger.info("MCP tool cache hit after wait: %s", name)
                return cached
        logger.warning("MCP tool in-flight wait expired or cache missing: %s", name)

    try:
        result = compute_fn()
        _cache[key] = (result, time.time())
        return result
    finally:
        if is_owner:
            with _inflight_lock:
                current = _inflight.pop(key, None)
                if current is not None:
                    current.set()


def _warm_cache() -> None:
    """Pre-execute the most common analytics queries in parallel after analytics loads."""
    _analytics_ready.wait()
    if not _analytics_loaded:
        return  # analytics failed to load
    try:
        from concurrent.futures import ThreadPoolExecutor
        warmup = [
            ("analytics_overview", {"period": "30d"}),
            ("analytics_overview", {"period": "30d", "compare": True}),
            ("analytics_overview", {"period": "365d", "compare": True}),
            ("analytics_orders",   {"period": "30d"}),
            ("analytics_orders",   {"period": "365d", "include_returns": True}),
            ("analytics_orders",   {"period": "365d", "group_by": "channel"}),
            ("analytics_orders",   {"period": "365d", "group_by": "province"}),
            ("analytics_customers", {"period": "30d"}),
            ("analytics_funnel", {"period": "365d"}),
            # Heavy queries — pre-warm so Claude Desktop tool calls return from cache
            ("analytics_rfm",      {}),
            ("analytics_retention", {"days": [7, 30, 90]}),
            ("analytics_repurchase", {"period": "90d"}),
        ]
        def _run_one(item: tuple) -> None:
            # _warm_cache 仅供 stdio 模式调用（__main__.py _run_stdio），HTTP 模式的 lifespan 不调用此函数
            warm_tid = os.getenv("MCP_TENANT_ID", "")
            if not warm_tid:
                logging.getLogger(__name__).debug("Cache warm skipped: MCP_TENANT_ID not set")
                return
            name, args = item
            handler = _HANDLERS.get(name)
            if not handler:
                return
            try:
                logging.getLogger(__name__).info("Cache warm started: %s args=%s", name, json.dumps(args, ensure_ascii=False, sort_keys=True))
                result = _run_with_cache(name, args, warm_tid, lambda: handler(args))
                logging.getLogger(__name__).info("Cache warm finished: %s", name)
            except Exception as e:
                logging.getLogger(__name__).warning("Cache warm failed for %s: %s", name, e)
        with ThreadPoolExecutor(max_workers=3) as ex:
            list(ex.map(_run_one, warmup))
    except Exception as e:
        logging.getLogger(__name__).warning("Cache warming failed: %s", e)


def _load_analytics() -> None:
    """Lazily import heavy analytics deps (pandas/matplotlib) and inject into globals.

    Must be called from a regular Python thread (NOT from anyio's thread pool),
    because importing pandas from within the ProactorEventLoop's executor deadlocks.
    Always sets _analytics_ready even on failure so tool calls never hang forever.
    """
    global _analytics_loaded
    if _analytics_loaded:
        return
    try:
        from cli.analytics.mcp_adapter import (
            _get_mcp_overview,
            _get_mcp_customers,
            _get_mcp_customer_source,
            _get_mcp_customer_gender,
            _get_mcp_orders,
            _get_mcp_order_returns,
            _get_mcp_orders_tool_payload,
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
        from cli.analytics.mcp_adapter import _mcp_segment_analyze
        g = globals()
        for fn in [
            _get_mcp_overview, _get_mcp_customers, _get_mcp_customer_source,
            _get_mcp_customer_gender, _get_mcp_orders, _get_mcp_order_returns,
            _get_mcp_orders_tool_payload,
            _get_mcp_retention, _get_mcp_funnel, _get_mcp_rfm, _get_mcp_ltv,
            _get_mcp_campaigns, _get_mcp_campaign_detail, _get_mcp_campaign_roi,
            _get_mcp_canvas, _get_mcp_points, _get_mcp_points_at_risk,
            _get_mcp_coupons, _get_mcp_coupon_lift, _get_mcp_coupon_anomaly,
            _get_mcp_products, _get_mcp_stores, _get_mcp_anomaly,
            _get_mcp_loyalty, _get_mcp_repurchase, _get_mcp_repurchase_path,
        ]:
            g[fn.__name__] = fn
        g['_mcp_segment_analyze'] = _mcp_segment_analyze
        _analytics_loaded = True
    except Exception as e:
        logging.getLogger(__name__).error(f"Analytics load failed: {e}", exc_info=True)
    finally:
        _analytics_ready.set()  # Always unblock waiting tool calls

logger = logging.getLogger(__name__)


def probe_upstream_mcp(timeout: int = 15) -> tuple[bool, str]:
    """Check whether the configured upstream MCP analytics service is reachable.

    This intentionally performs a lightweight real connection so server startup can
    fail fast in logs instead of surfacing only as Claude tool timeouts later.
    """
    try:
        from cli.api.mcp_client import MCPClient, MCPConfig

        config = _get_config()
        client = MCPClient(MCPConfig(
            sse_url=config.mcp.sse_url,
            post_url=config.mcp.post_url,
            tenant_id=config.mcp.tenant_id,
            timeout=timeout,
        ))
        client.connect(show_status=False)
        client.initialize()
        tools = client.list_tools()
        client.disconnect()
        return True, f"upstream reachable, tools={len(tools)}"
    except Exception as e:
        return False, str(e)

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS: list[Tool] = [
    Tool(
        name="analytics_overview",
        description=(
            "Top-level business KPI dashboard — call this tool for daily/weekly/monthly business reviews, "
            "operational summaries, or when the user asks 'how is the business doing', 'show me today's numbers', "
            "'give me a business overview', or any request for a high-level performance snapshot. "
            "Returns GMV (gross merchandise value), total orders, AOV (average order value), active customers, "
            "new customers, coupon redemption rate, loyalty points issued and consumed, and message delivery rate. "
            "Set compare=true to include prior-period delta so you can show growth/decline trends."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["today", "7d", "30d", "90d", "365d", "ytd"],
                    "default": "30d",
                    "description": "Analysis window: today, 7d (last 7 days), 30d, 90d, 365d, or ytd (year-to-date)",
                },
                "compare": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, also returns the same metrics for the prior equal-length period so growth rates can be computed",
                },
            },
        },
    ),
    Tool(
        name="analytics_customers",
        description=(
            "Customer base and growth metrics — call this tool when the user asks about customer counts, "
            "member growth, new vs returning customers, how many registered users or buyers there are, "
            "or where customers come from. "
            "Returns total registered customers, total buyers (customers who have ordered at least once), "
            "active buyers in period, member vs non-member split, and new customer acquisitions. "
            "Set include_source=true to add acquisition channel breakdown (which channels bring the most customers). "
            "Set include_gender=true to add gender distribution of the customer base."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["today", "7d", "30d", "90d", "365d", "ytd"],
                    "default": "30d",
                    "description": "Analysis window for active buyers and new customer counts",
                },
                "include_source": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, include acquisition channel breakdown (e.g. WeChat, app, offline, etc.)",
                },
                "include_gender": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, include gender distribution of the registered customer base",
                },
            },
        },
    ),
    Tool(
        name="analytics_orders",
        description=(
            "Order and sales analytics — call this tool when the user asks about sales performance, "
            "revenue trends, order volume, channel breakdown, regional/province analysis, product rankings, "
            "repurchase rate, or return/refund rates. "
            "Returns GMV, order count, AOV, unique customers, new vs returning buyer split, and daily order trend. "
            "Set group_by='channel' for sales by sales channel (Tmall, JD, WeChat Mini Program, offline, etc.). "
            "Set group_by='province' for regional/geographic sales breakdown. "
            "Set group_by='product' for top products by revenue. "
            "Set include_returns=true to add return and refund order breakdown by channel."
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
                "group_by": {
                    "type": "string",
                    "enum": ["channel", "province", "product"],
                    "description": "Dimension to group by: 'channel' for sales channel, 'province' for region, 'product' for SKU/item ranking. Omit for overall totals only.",
                },
                "include_returns": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, include return order count and refund GMV breakdown by channel",
                },
            },
        },
    ),
    Tool(
        name="analytics_retention",
        description=(
            "Cohort-based customer retention rates — call this tool when the user asks about retention, "
            "how many customers come back, buyer loyalty over time, or whether customers are returning to purchase again. "
            "For each specified day window (e.g. 7, 30, 90 days), shows: total customers who bought in that window, "
            "how many made a second purchase within that window, and the retention rate percentage. "
            "Use multiple windows (e.g. [7, 30, 90]) to see short-term vs long-term retention patterns."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "days": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 1, "maximum": 365},
                    "default": [7, 14, 30],
                    "description": "List of retention window sizes in days (e.g. [7, 30, 90]). Each window measures how many buyers repurchased within that many days.",
                },
            },
        },
    ),
    Tool(
        name="analytics_funnel",
        description=(
            "Customer lifecycle funnel — call this tool when the user asks about the customer lifecycle, "
            "how many loyal or churned customers there are, customer health distribution, "
            "conversion from new customer to repeat buyer, or where customers are dropping off. "
            "Returns headcount and conversion rates across six lifecycle stages: "
            "New (registered, never ordered) → First Purchase → Repeat Buyer (2+ orders) → "
            "Loyal (frequent, high-value) → At-Risk (lapsed, may churn) → Churned (long inactive). "
            "Use to understand the overall health of the customer base and identify the biggest drop-off stage."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["today", "7d", "30d", "90d", "365d", "ytd"],
                    "default": "30d",
                    "description": "Analysis window for determining active vs at-risk vs churned status",
                },
            },
        },
    ),
    Tool(
        name="analytics_rfm",
        description=(
            "RFM (Recency, Frequency, Monetary) customer segmentation — call this tool when the user asks "
            "about RFM analysis, customer segmentation, customer tiers, high-value customers, loyal customers, "
            "at-risk customers, or customer loyalty scoring. "
            "Returns live segment distribution (Champions, Loyal Customers, Potential Loyalists, New Customers, "
            "Cant Lose Them, Need Attention, About to Sleep, Hibernating) with headcount, average spend, "
            "order frequency, and recency per segment. "
            "Use segment_filter to drill into one segment; use top_limit to list the top-N customers."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "segment_filter": {
                    "type": "string",
                    "description": "Filter to a specific segment name (e.g. 'Champions', 'Loyal Customers', 'Hibernating'). Omit for all segments.",
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
            "Cohort Lifetime Value (LTV) analysis — call this tool when the user asks about customer lifetime value, "
            "cohort analysis, whether newer customers are more or less valuable than older ones, "
            "or how much revenue each acquisition cohort generates over time. "
            "Groups customers by their first-order month (acquisition cohort) and tracks cumulative GMV per customer "
            "in each subsequent month. Useful for identifying which cohorts have the highest long-term value "
            "and whether the business is acquiring increasingly valuable customers over time."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "cohort_months": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 24,
                    "default": 6,
                    "description": "How many past acquisition months to include as cohorts (e.g. 6 = last 6 months of new customers)",
                },
                "follow_months": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 12,
                    "default": 3,
                    "description": "How many months to track each cohort's revenue after their first order",
                },
            },
        },
    ),
    Tool(
        name="analytics_campaigns",
        description=(
            "Marketing campaign performance analytics — call this tool when the user asks about campaign results, "
            "marketing ROI, which campaigns are performing well, campaign reach/click/conversion rates, "
            "or the effectiveness of a specific campaign or customer journey. "
            "Returns campaign list with funnel metrics (targeted audience → reached → clicked → converted) "
            "and reward distribution (points awarded, coupons sent, messages delivered). "
            "Set campaign_id to drill into a single campaign's details. "
            "Set canvas_id to get per-node conversion funnel for a multi-step journey campaign. "
            "Set include_roi=true to add GMV attribution (revenue generated by customers who participated in the campaign)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["today", "7d", "30d", "90d", "365d", "ytd"],
                    "default": "30d",
                    "description": "Time window for filtering campaigns by start date",
                },
                "campaign_id": {
                    "type": "string",
                    "description": "If provided, return detailed metrics for this specific campaign ID only",
                },
                "name_filter": {
                    "type": "string",
                    "description": "Filter campaigns by name keyword (case-insensitive partial match)",
                },
                "canvas_id": {
                    "type": "string",
                    "description": "If provided, return per-node journey funnel for this canvas/automation campaign ID",
                },
                "include_roi": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, include GMV revenue attributed to each campaign's converted customers",
                },
                "attribution_window_days": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 90,
                    "default": 30,
                    "description": "Number of days after campaign conversion event to count attributed purchases (used when include_roi=true)",
                },
            },
        },
    ),
    Tool(
        name="analytics_points",
        description=(
            "Loyalty points program analytics — call this tool when the user asks about the points program, "
            "how many points were earned or redeemed, points redemption rate, points liability, "
            "which members are at risk of losing expiring points, or points program engagement. "
            "Returns total points earned, redeemed, expired, redemption rate percentage, and count of active members. "
            "Set include_breakdown=true to add breakdown by operation type (purchase earn, promotion bonus, gift redemption, expiry). "
            "Set expiring_within_days to identify members with points expiring soon (useful for win-back campaigns)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["today", "7d", "30d", "90d", "365d", "ytd"],
                    "default": "30d",
                    "description": "Analysis window for points activity",
                },
                "include_breakdown": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, break down earned and redeemed points by operation type",
                },
                "expiring_within_days": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 365,
                    "default": 0,
                    "description": "If > 0, also return list of members whose points will expire within this many days",
                },
                "at_risk_limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 500,
                    "default": 100,
                    "description": "Maximum number of expiring-points members to return (requires expiring_within_days > 0)",
                },
            },
        },
    ),
    Tool(
        name="analytics_coupons",
        description=(
            "Coupon and discount program analytics — call this tool when the user asks about coupon performance, "
            "discount usage, redemption rates, which coupon rules are most effective, "
            "whether coupons are actually driving incremental revenue, or coupon fraud/anomaly detection. "
            "Returns total coupons issued, redeemed, expired, redemption rate, and total face value redeemed (CNY). "
            "Set include_roi_breakdown=true to see GMV and ROI per coupon rule (which coupons generate the most revenue). "
            "Set include_lift=true to compare coupon users vs non-users on AOV and repurchase rate "
            "(measures whether coupons actually change customer behavior). "
            "Set detect_anomalies=true to flag days with unusually high or low redemption volume."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["today", "7d", "30d", "90d", "365d", "ytd"],
                    "default": "30d",
                    "description": "Analysis window for coupon activity",
                },
                "include_roi_breakdown": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, include per-coupon-rule GMV attribution and ROI",
                },
                "include_lift": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, compare AOV and repurchase rate between coupon users and non-users",
                },
                "detect_anomalies": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, run mean ± 2σ anomaly detection on daily redemption volume",
                },
            },
        },
    ),
    Tool(
        name="analytics_loyalty",
        description=(
            "Loyalty program tier and enrollment analytics — call this tool when the user asks about "
            "the loyalty membership program, tier distribution (how many Bronze/Silver/Gold/Platinum members), "
            "member enrollment rate, points liability (total unredeemed points value in CNY), "
            "or which tiers have the highest churn risk. "
            "Returns member count and percentage per tier, overall enrollment rate vs total customer base, "
            "total outstanding points liability, and churn risk score per tier."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    Tool(
        name="analytics_products",
        description=(
            "Product performance ranking — call this tool when the user asks about best-selling products, "
            "top SKUs by revenue, product category performance, which products drive the most orders, "
            "or product-level sales analysis. "
            "Returns top products ranked by revenue with order count, units sold, unique buyers, "
            "total revenue (CNY), and average selling price. "
            "Set by_category=true to aggregate by product category instead of individual SKUs."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["today", "7d", "30d", "90d", "365d", "ytd"],
                    "default": "30d",
                    "description": "Analysis window for order data",
                },
                "by_category": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, aggregate revenue and orders by product category instead of individual products",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 20,
                    "description": "Number of top products (or categories) to return",
                },
            },
        },
    ),
    Tool(
        name="analytics_stores",
        description=(
            "Store-level sales performance — call this tool when the user asks about which stores are performing best, "
            "offline store rankings, store GMV comparison, or store-level customer metrics. "
            "Returns each store's GMV, order count, unique customer count, and repeat purchase rate, "
            "ranked by GMV descending. Covers both offline retail stores and online flagship stores. "
            "Use to identify top performers, underperforming locations, or compare channel-specific store results."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["today", "7d", "30d", "90d", "365d", "ytd"],
                    "default": "30d",
                    "description": "Analysis window for store sales data",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 20,
                    "description": "Number of top stores to return",
                },
            },
        },
    ),
    Tool(
        name="analytics_repurchase",
        description=(
            "Repurchase behavior and customer repeat-buy analysis — call this tool when the user asks about "
            "repurchase rate, how quickly customers make their second order, what percentage of revenue comes "
            "from returning vs new buyers, or how long the typical repurchase cycle is. "
            "Returns: repurchase rate (% of buyers who ordered more than once), GMV split between new and returning buyers, "
            "median days from first to second order, and a histogram of first-to-second order timing intervals. "
            "Longer periods (90d+) give more statistically reliable repurchase rate estimates."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["today", "7d", "30d", "90d", "365d", "ytd"],
                    "default": "90d",
                    "description": "Analysis window — use 90d or longer for reliable repurchase rate calculation",
                },
            },
        },
    ),
    Tool(
        name="analytics_anomaly",
        description=(
            "Statistical anomaly detection on daily business metrics — call this tool when the user asks "
            "whether there were any unusual or abnormal days, if GMV/orders suddenly spiked or dropped, "
            "or to proactively flag data quality issues or business incidents in recent days. "
            "Uses a rolling mean ± 2σ baseline computed from historical data to identify days where "
            "the metric was significantly higher or lower than expected. "
            "Available metrics: gmv (gross revenue), orders (order count), aov (average order value), new_buyers. "
            "Returns flagged anomaly days with actual vs expected values and severity."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "metric": {
                    "type": "string",
                    "enum": ["gmv", "orders", "aov", "new_buyers"],
                    "description": "The KPI to check: 'gmv' for gross revenue, 'orders' for order volume, 'aov' for average order value, 'new_buyers' for daily new customer acquisitions",
                },
                "lookback_days": {
                    "type": "integer",
                    "minimum": 7,
                    "maximum": 180,
                    "default": 30,
                    "description": "Number of historical days to use for computing the baseline mean and standard deviation",
                },
                "detect_days": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 30,
                    "default": 7,
                    "description": "Number of most recent days to evaluate against the baseline",
                },
            },
            "required": ["metric"],
        },
    ),
    Tool(
        name="analytics_segment",
        description=(
            "Purchase behavior analysis for a specific customer segment or group — call this tool when the user "
            "provides a segment ID or customer group ID and wants to know how that group is performing, "
            "how active they are, what their AOV is, or who the top buyers in the segment are. "
            "Queries purchase history for members of the specified segment and returns: buy rate (% who ordered), "
            "total GMV, AOV, average orders per buyer, and a ranked list of top buyers by spend. "
            "For large segments, results are automatically sampled (up to max_members) and labeled as such."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "group_id": {
                    "type": "string",
                    "description": "The segment or customer group ID to analyze (required)",
                },
                "period": {
                    "type": "string",
                    "enum": ["7d", "30d", "90d", "365d"],
                    "default": "30d",
                    "description": "Analysis window for purchase activity within the segment",
                },
                "max_members": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 2000,
                    "default": 500,
                    "description": "Maximum number of segment members to sample when the group is large",
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
    config = _get_config()
    period = args.get("period", "30d")
    data = _get_mcp_overview(config, period)
    return _ok({"period": period, **data})


def _handle_analytics_customers(args: dict) -> list[TextContent]:
    config = _get_config()
    period = args.get("period", "30d")
    result: dict[str, Any] = {}
    result["customers"] = _get_mcp_customers(config, period, "all")
    if args.get("include_source"):
        result["source"] = _get_mcp_customer_source(config, period)
    if args.get("include_gender"):
        result["gender"] = _get_mcp_customer_gender(config)
    return _ok(result)


def _handle_analytics_orders(args: dict) -> list[TextContent]:
    config = _get_config()
    period = args.get("period", "30d")
    group_by = args.get("group_by")
    result = _get_mcp_orders_tool_payload(
        config,
        period,
        group_by=group_by,
        include_returns=args.get("include_returns", False),
    )
    return _ok(result)


def _handle_analytics_retention(args: dict) -> list[TextContent]:
    config = _get_config()
    days = args.get("days", [7, 14, 30])
    data = _get_mcp_retention(config, days)
    return _ok(data)


def _handle_analytics_funnel(args: dict) -> list[TextContent]:
    config = _get_config()
    period = args.get("period", "30d")
    data = _get_mcp_funnel(config, period)
    return _ok(data)


def _handle_analytics_rfm(args: dict) -> list[TextContent]:
    config = _get_config()
    segment_filter = args.get("segment_filter", "")
    top_limit = args.get("top_limit", 0)
    data = _get_mcp_rfm(config, limit=top_limit, segment_filter=segment_filter)
    return _ok(data)


def _handle_analytics_ltv(args: dict) -> list[TextContent]:
    config = _get_config()
    cohort_months = args.get("cohort_months", 6)
    follow_months = args.get("follow_months", 3)
    data = _get_mcp_ltv(config, cohort_months, follow_months)
    return _ok(data)


def _handle_analytics_campaigns(args: dict) -> list[TextContent]:
    config = _get_config()
    period = args.get("period", "30d")
    campaign_id = args.get("campaign_id")
    canvas_id = args.get("canvas_id")
    result: dict[str, Any] = {}

    if canvas_id:
        result["canvas_funnel"] = _get_mcp_canvas(config, canvas_id)
    elif campaign_id:
        result["detail"] = _get_mcp_campaign_detail(config, campaign_id)
    else:
        result["campaigns"] = _get_mcp_campaigns(
            config, period,
            campaign_id=campaign_id,
            name=args.get("name_filter"),
        )

    if args.get("include_roi"):
        window = args.get("attribution_window_days", 30)
        result["roi"] = _get_mcp_campaign_roi(config, period, window)

    return _ok(result)


def _handle_analytics_points(args: dict) -> list[TextContent]:
    config = _get_config()
    period = args.get("period", "30d")
    expiring_days = args.get("expiring_within_days", 0)
    breakdown = args.get("include_breakdown", False)
    at_risk_limit = args.get("at_risk_limit", 100)

    result: dict[str, Any] = {}
    result["points"] = _get_mcp_points(config, period, expiring_days=expiring_days, breakdown=breakdown)
    if expiring_days > 0:
        result["at_risk_members"] = _get_mcp_points_at_risk(config, expiring_days, limit=at_risk_limit)
    return _ok(result)


def _handle_analytics_coupons(args: dict) -> list[TextContent]:
    config = _get_config()
    period = args.get("period", "30d")
    roi = args.get("include_roi_breakdown", False)

    result: dict[str, Any] = {}
    result["coupons"] = _get_mcp_coupons(config, period, roi=roi)
    if args.get("include_lift"):
        result["lift"] = _get_mcp_coupon_lift(config, period)
    if args.get("detect_anomalies"):
        result["anomaly"] = _get_mcp_coupon_anomaly(config)
    return _ok(result)


def _handle_analytics_loyalty(args: dict) -> list[TextContent]:
    config = _get_config()
    data = _get_mcp_loyalty(config)
    return _ok(data)


def _handle_analytics_products(args: dict) -> list[TextContent]:
    config = _get_config()
    period = args.get("period", "30d")
    by_category = args.get("by_category", False)
    limit = args.get("limit", 20)
    data = _get_mcp_products(config, period, by_category, limit)
    return _ok(data)


def _handle_analytics_stores(args: dict) -> list[TextContent]:
    config = _get_config()
    period = args.get("period", "30d")
    limit = args.get("limit", 20)
    data = _get_mcp_stores(config, period, limit)
    return _ok(data)


def _handle_analytics_repurchase(args: dict) -> list[TextContent]:
    config = _get_config()
    period = args.get("period", "90d")
    data = _get_mcp_repurchase(config, period)
    return _ok(data)


def _handle_analytics_anomaly(args: dict) -> list[TextContent]:
    config = _get_config()
    metric = args["metric"]
    lookback = args.get("lookback_days", 30)
    detect = args.get("detect_days", 7)
    data = _get_mcp_anomaly(config, metric, lookback, detect)
    return _ok(data)


def _handle_analytics_segment(args: dict) -> list[TextContent]:
    config = _get_config()
    group_id = str(args["group_id"])
    period = args.get("period", "30d")
    max_members = args.get("max_members", 500)
    data = _mcp_segment_analyze(config, group_id, period, max_members)
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
        import asyncio
        handler = _HANDLERS.get(name)
        if handler is None:
            return _err(f"Unknown tool: {name}")
        try:
            args = arguments or {}
            loop = asyncio.get_running_loop()
            started = time.time()
            from mcp_server.auth import _get_tenant_id, _get_request_id
            req_id = _get_request_id()
            logger.info("MCP tool call started: %s req_id=%s args=%s", name, req_id or "-", json.dumps(args, ensure_ascii=False, sort_keys=True))

            # 在 async 上下文中读取 tenant_id（ContextVar 在此处可用）
            # 必须在 run_in_executor 之前读取，线程池中 ContextVar 可能因 MCP SDK
            # 创建新 async context 而丢失
            tid = _get_tenant_id() or os.getenv("MCP_TENANT_ID", "")

            if not tid:
                logger.warning("tenant_id 未设置，tool=%s", name)
                return _err("Tenant not configured. Contact IT administrator.")

            # 在 async 上下文中获取凭证（DB 查询是异步的），供 _run() 同步使用
            from mcp_server.token_manager import get_cred, get_cached_token_sync
            cred = await get_cred(tid)

            # 在 async 上下文中读取 tenant_id（ContextVar 在此处可用）
            # 必须在 run_in_executor 之前读取，线程池中 ContextVar 可能因 MCP SDK
            # 创建新 async context 而丢失
            from mcp_server.auth import _get_tenant_id
            tid = _get_tenant_id() or os.getenv("MCP_TENANT_ID", "")

            if not tid:
                logger.warning("tenant_id 未设置，tool=%s", name)
                return _err("Tenant not configured. Contact IT administrator.")

            # 在 async 上下文中获取凭证（DB 查询是异步的），供 _run() 同步使用
            from mcp_server.token_manager import get_cred, get_cached_token_sync
            cred = await get_cred(tid)

            def _run():
                import threading as _threading
                if not _analytics_ready.wait(timeout=120):
                    return _err("Analytics failed to load within 120s")

                # 将 API Key 映射的 tenant_id 注入 thread-local，
                # 使 _get_config() 在本线程返回该租户的 mcp 配置
                _thread_local.tenant_id = tid
                try:
                    # 注入 SocialHub token 到当前线程 dict，供 MCPClient 读取
                    if cred:
                        try:
                            token = get_cached_token_sync(tid, cred)
                            _threading.current_thread().__dict__["_sh_mcp_token"] = token
                        except Exception as _e:
                            logger.warning("SocialHub token 获取失败 tenant=%s: %s", tid, _e)
                            _threading.current_thread().__dict__["_sh_mcp_token"] = ""
                    else:
                        logger.warning("tenant=%s 未配置 SocialHub 凭证，upstream 请求将无 token", tid)
                        _threading.current_thread().__dict__["_sh_mcp_token"] = ""

                    # 注入数据库名（env var 优先，否则按默认规则 {prefix}_{tenant_id}）
                    _tl = _threading.current_thread().__dict__
                    _tl["_sh_das_database"]     = _resolve_tenant_db("DAS_DATABASE", tid, "das")
                    _tl["_sh_dts_database"]     = _resolve_tenant_db("DTS_DATABASE", tid, "dts")
                    _tl["_sh_datanow_database"] = _resolve_tenant_db("DATANOW_DATABASE", tid, "datanow")

                    safe_args = {k: v for k, v in args.items() if k != "tenant_id"}
                    return _run_with_cache(name, safe_args, tid, lambda: handler(safe_args))
                finally:
                    _thread_local.tenant_id = None
                    _tl = _threading.current_thread().__dict__
                    _tl.pop("_sh_mcp_token", None)
                    _tl.pop("_sh_das_database", None)
                    _tl.pop("_sh_dts_database", None)
                    _tl.pop("_sh_datanow_database", None)

            result = await loop.run_in_executor(None, _run)
            logger.info("MCP tool call finished: %s elapsed_ms=%s", name, int((time.time() - started) * 1000))
            return result
        except MCPError as e:
            logger.error("MCP database error in %s: %s", name, e)
            return _err(f"Database error: {e}")
        except ValueError as e:
            return _err(f"Invalid input: {e}")
        except Exception as e:
            logger.exception("Unexpected error in tool %s", name)
            return _err(f"Unexpected error: {e}")

    return server
