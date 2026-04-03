"""Schema Explorer — semantic navigation of the SocialHub.AI warehouse.

Lets analysts discover tables, understand grain and field meaning, and map
business questions to the right data source — without reading raw schema dumps.

Three databases:
  das_demoen     — analytics warehouse (ADS / DWS / DWD / DIM layers)
  dts_demoen     — source/ODS layer  (vdm_t_* views)
  datanow_demoen — real-time layer   (t_* tables)
"""


import typer
from rich import box as rich_box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(help="Warehouse schema explorer — discover tables and field meanings")
console = Console()

# =============================================================================
# Schema Registry — embedded metadata for the key warehouse assets
# Each entry:
#   domain   : business domain
#   db       : database
#   layer    : dim / dwd / dws / ads / src (source/ODS)
#   purpose  : one-line business description
#   grain    : what one row represents
#   date_col : primary date/partition column
#   key_dims : list of key dimension columns
#   key_metrics : list of key metric columns (with types)
#   bitmap_cols : bitmap columns (need BITMAP_COUNT / BITMAP_UNION)
#   caveats  : important warnings / gotchas
#   use_cases: list of typical analyst questions answered
#   cli_cmd  : corresponding CLI command(s)
# =============================================================================

SCHEMA: dict[str, dict] = {

    # ── Activity / Campaign ───────────────────────────────────────────────────

    "ads_das_activity_analysis_d": {
        "domain": "activity",
        "db": "das_demoen",
        "layer": "ads",
        "purpose": "Daily campaign performance summary — participants, rewards, and linked orders",
        "grain": "One row per (activity_code, biz_date)",
        "date_col": "biz_date",
        "key_dims": ["activity_code", "biz_date"],
        "key_metrics": [
            "activity_custs_bitnum BITMAP  — distinct participant bitmap",
            "activity_Points_Issued BIGINT — points issued in fen",
            "activity_coupon_issue_qty INT — coupons issued",
        ],
        "bitmap_cols": ["activity_custs_bitnum"],
        "caveats": [
            "Use BITMAP_COUNT(BITMAP_UNION(activity_custs_bitnum)) to get unique participant count across days",
            "Points values are in fen (÷100 for CNY)",
        ],
        "use_cases": [
            "Campaign ROI: participants → orders within N days",
            "Period-level participant counts",
            "Points/coupon distribution per campaign",
        ],
        "cli_cmd": "analytics campaigns --roi",
    },

    "ads_das_activity_canvas_analysis_d": {
        "domain": "activity",
        "db": "das_demoen",
        "layer": "ads",
        "purpose": "Journey canvas (multi-step campaign) summary metrics per canvas",
        "grain": "One row per (canvas_id, biz_date)",
        "date_col": "biz_date",
        "key_dims": ["canvas_id", "biz_date"],
        "key_metrics": [
            "enter_custs_bitnum BITMAP — customers who entered the canvas",
            "complete_custs_bitnum BITMAP — customers who completed all nodes",
        ],
        "bitmap_cols": ["enter_custs_bitnum", "complete_custs_bitnum"],
        "caveats": ["Companion to ads_das_activity_node_canvas_analysis_d for per-node breakdown"],
        "use_cases": ["Canvas funnel: entry → completion rate", "Journey drop-off analysis"],
        "cli_cmd": "analytics campaigns",
    },

    "ads_das_activity_node_canvas_analysis_d": {
        "domain": "activity",
        "db": "das_demoen",
        "layer": "ads",
        "purpose": "Per-node metrics within a journey canvas (touch / pass / reward counts)",
        "grain": "One row per (canvas_id, node_id, biz_date)",
        "date_col": "biz_date",
        "key_dims": ["canvas_id", "node_id", "biz_date"],
        "key_metrics": [
            "touch_cnt INT — customers who reached this node",
            "pass_cnt  INT — customers who passed / completed this node",
            "reward_cnt INT — customers who received a reward at this node",
        ],
        "bitmap_cols": [],
        "caveats": ["node_id ordering determines the funnel sequence"],
        "use_cases": ["Per-step drop-off in a multi-step journey"],
        "cli_cmd": "analytics campaigns",
    },

    # ── Customer ──────────────────────────────────────────────────────────────

    "ads_das_business_overview_d": {
        "domain": "customer",
        "db": "das_demoen",
        "layer": "ads",
        "purpose": "Daily business KPI snapshot — active, new, buying, churn, pre-churn bitmaps",
        "grain": "One row per biz_date (single-row daily snapshot)",
        "date_col": "biz_date",
        "key_dims": ["biz_date"],
        "key_metrics": [
            "active_custs_bitnum BITMAP  — customers active in the period",
            "new_custs_bitnum    BITMAP  — new customers registered today",
            "buying_custs_bitnum BITMAP  — customers who placed an order today",
            "churn_custs_bitnum  BITMAP  — churned customers",
            "pre_churn_bitnum    BITMAP  — pre-churn (at-risk) customers",
            "add_custs_num       INT     — new registrations count",
            "gmv                 BIGINT  — daily GMV in fen",
        ],
        "bitmap_cols": [
            "active_custs_bitnum", "new_custs_bitnum", "buying_custs_bitnum",
            "churn_custs_bitnum", "pre_churn_bitnum",
        ],
        "caveats": [
            "Use BITMAP_COUNT(BITMAP_UNION(...)) to aggregate across a date range",
            "GMV in fen — divide by 100 for CNY",
            "Single row per day; for period totals, aggregate with BITMAP_UNION",
        ],
        "use_cases": [
            "Daily overview dashboard",
            "Period-over-period active/churn comparison",
            "New customer growth trend",
        ],
        "cli_cmd": "analytics overview",
    },

    "ads_das_custs_tier_distribution_d": {
        "domain": "customer",
        "db": "das_demoen",
        "layer": "ads",
        "purpose": "Daily member tier distribution — headcount and risk bitmaps per tier",
        "grain": "One row per (tier_code, biz_date)",
        "date_col": "biz_date",
        "key_dims": ["tier_code", "tier_name", "biz_date"],
        "key_metrics": [
            "member_bitnum      BITMAP — members currently in this tier",
            "pre_churn_bitnum   BITMAP — pre-churn members in this tier",
            "churn_bitnum       BITMAP — churned members in this tier",
        ],
        "bitmap_cols": ["member_bitnum", "pre_churn_bitnum", "churn_bitnum"],
        "caveats": [
            "BITMAP_AND between two dates gives net tier-change membership",
            "Use BITMAP_COUNT(BITMAP_UNION(member_bitnum)) for total members per tier over a period",
        ],
        "use_cases": [
            "Tier distribution dashboard",
            "Churn risk per tier",
            "Tier upgrade / downgrade flow (compare snapshots)",
        ],
        "cli_cmd": "members tier-distribution  |  members tier-transitions",
    },

    "ads_v_rfm": {
        "domain": "customer",
        "db": "das_demoen",
        "layer": "ads",
        "purpose": "RFM customer value segmentation view — scored and labeled by R/F/M dimensions",
        "grain": "One row per customer_code (latest snapshot)",
        "date_col": None,
        "key_dims": ["customer_code", "rfm_segment", "rfm_label"],
        "key_metrics": [
            "recency_score  INT  — days since last order (lower = more recent)",
            "frequency      INT  — total order count",
            "monetary       BIGINT — total spend in fen",
            "rfm_score      FLOAT  — combined RFM score",
        ],
        "bitmap_cols": [],
        "caveats": ["View refreshed periodically — not real-time", "monetary in fen"],
        "use_cases": [
            "High-value customer identification",
            "Segment-specific marketing lists",
            "Churn prevention targeting",
        ],
        "cli_cmd": "analytics rfm  |  members rfm",
    },

    "ads_das_custs_source_analysis_d": {
        "domain": "customer",
        "db": "das_demoen",
        "layer": "ads",
        "purpose": "Customer acquisition source breakdown — how customers were acquired by channel",
        "grain": "One row per (source_channel, biz_date)",
        "date_col": "biz_date",
        "key_dims": ["source_channel", "biz_date"],
        "key_metrics": [
            "new_custs_cnt   INT — new customers from this source today",
            "custs_bitnum BITMAP — customer bitmap for this source",
        ],
        "bitmap_cols": ["custs_bitnum"],
        "caveats": ["Channel definitions vary by tenant configuration"],
        "use_cases": ["Acquisition channel effectiveness", "Source contribution trend"],
        "cli_cmd": "analytics customers --source",
    },

    "ads_das_custs_gender_distribution_d": {
        "domain": "customer",
        "db": "das_demoen",
        "layer": "ads",
        "purpose": "Customer gender distribution snapshot",
        "grain": "One row per (gender, biz_date)",
        "date_col": "biz_date",
        "key_dims": ["gender", "biz_date"],
        "key_metrics": ["custs_bitnum BITMAP — customer bitmap for this gender"],
        "bitmap_cols": ["custs_bitnum"],
        "caveats": ["Gender values: 1=Male, 2=Female, 0=Unknown"],
        "use_cases": ["Demographics breakdown"],
        "cli_cmd": "analytics customers --gender",
    },

    "dws_customer_base_metrics": {
        "domain": "customer",
        "db": "das_demoen",
        "layer": "dws",
        "purpose": "Pre-aggregated customer-level lifetime metrics — total orders, spend, recency",
        "grain": "One row per customer_code (latest snapshot)",
        "date_col": "last_order_date",
        "key_dims": ["customer_code", "identity_type"],
        "key_metrics": [
            "total_orders    INT    — lifetime order count",
            "total_amount    BIGINT — lifetime spend in fen",
            "last_order_date DATE   — date of most recent order",
            "first_order_date DATE  — date of first order",
        ],
        "bitmap_cols": [],
        "caveats": [
            "identity_type=1 for members; filter to avoid double-counting",
            "total_amount in fen",
        ],
        "use_cases": ["Top-customer ranking", "RFM input", "Customer lifetime metrics"],
        "cli_cmd": "members top",
    },

    # ── Transaction / Orders ─────────────────────────────────────────────────

    "dwd_v_order": {
        "domain": "transaction",
        "db": "das_demoen",
        "layer": "dwd",
        "purpose": "Atomic order fact view — one row per order with key financial fields",
        "grain": "One row per order (code)",
        "date_col": "order_date",
        "key_dims": ["code", "customer_code", "store_name", "channel", "order_date"],
        "key_metrics": [
            "total_amount  BIGINT — order amount in fen",
            "discount_amount BIGINT — discount applied in fen",
            "direction     INT    — 0=sale, 1=return",
            "delete_flag   INT    — 0=valid, filter to 0",
        ],
        "bitmap_cols": [],
        "caveats": [
            "Always filter: delete_flag=0 AND direction=0 for normal sales",
            "total_amount in fen — divide by 100 for CNY",
            "Cross-database JOIN with vdm_t_order_detail requires same DB or federated query",
        ],
        "use_cases": [
            "GMV / order count / AOV",
            "Repurchase rate (ROW_NUMBER per customer)",
            "Store-level performance",
            "Customer order history",
        ],
        "cli_cmd": "analytics orders  |  analytics stores  |  analytics repurchase",
    },

    "dws_order_base_metrics_d": {
        "domain": "transaction",
        "db": "das_demoen",
        "layer": "dws",
        "purpose": "Pre-aggregated daily order metrics — GMV, orders, AOV, new vs returning",
        "grain": "One row per biz_date (daily summary)",
        "date_col": "biz_date",
        "key_dims": ["biz_date"],
        "key_metrics": [
            "gmv             BIGINT — total GMV in fen",
            "order_cnt       INT    — total orders",
            "aov             BIGINT — average order value in fen",
            "new_buyer_cnt   INT    — buyers placing first ever order today",
            "return_buyer_cnt INT   — repeat buyers today",
        ],
        "bitmap_cols": [],
        "caveats": [
            "Use this instead of dwd_v_order for dashboard-speed queries",
            "All amounts in fen",
        ],
        "use_cases": [
            "Fast daily GMV dashboard",
            "New vs returning buyer trend",
            "Anomaly detection on transaction movement",
        ],
        "cli_cmd": "(analytics overview — currently uses dwd_v_order; migration planned)",
    },

    "ads_das_v_repurchase_analysis_d": {
        "domain": "transaction",
        "db": "das_demoen",
        "layer": "ads",
        "purpose": "Pre-aggregated repurchase rate and repeat-buyer metrics by date",
        "grain": "One row per biz_date",
        "date_col": "biz_date",
        "key_dims": ["biz_date"],
        "key_metrics": [
            "repurchase_cust_cnt BIGINT — customers with 2+ orders in the period",
            "repurchase_rate     DOUBLE — repurchase rate (0-1)",
            "repurchase_amount   BIGINT — GMV from repeat orders in fen",
        ],
        "bitmap_cols": [],
        "caveats": ["Definitions may differ from computed repurchase rate in dwd_v_order"],
        "use_cases": ["Quick repurchase rate lookup without self-join on order table"],
        "cli_cmd": "analytics repurchase (also tries this table as supplementary)",
    },

    # ── Coupon ────────────────────────────────────────────────────────────────

    "dwd_coupon_instance": {
        "domain": "coupon",
        "db": "das_demoen",
        "layer": "dwd",
        "purpose": "Individual coupon instance — one row per coupon issued to a customer",
        "grain": "One row per coupon instance (id)",
        "date_col": "create_time",
        "key_dims": ["id", "customer_code", "coupon_rule_code", "status"],
        "key_metrics": [
            "par_value   BIGINT — face value in fen",
            "status      INT    — 1=unused, 2=used, 3=expired",
        ],
        "bitmap_cols": [],
        "caveats": [
            "status=2 means redeemed",
            "par_value in fen",
            "JOIN dwd_v_order on customer_code to compute attributed GMV",
        ],
        "use_cases": ["Coupon issuance volume", "Redemption rate", "Per-rule ROI"],
        "cli_cmd": "analytics coupons --by-rule",
    },

    "ads_das_v_coupon_analysis_d": {
        "domain": "coupon",
        "db": "das_demoen",
        "layer": "ads",
        "purpose": "Pre-aggregated daily coupon issue / redeem / linked GMV summary",
        "grain": "One row per biz_date",
        "date_col": "biz_date",
        "key_dims": ["biz_date"],
        "key_metrics": [
            "issue_cnt    INT    — coupons issued today",
            "redeem_cnt   INT    — coupons redeemed today",
            "redeem_value BIGINT — total redemption value in fen",
            "linked_gmv   BIGINT — GMV from orders that used a coupon",
        ],
        "bitmap_cols": [],
        "caveats": ["Use for trend queries; dwd_coupon_instance for per-rule breakdown"],
        "use_cases": ["Daily coupon performance dashboard", "Redemption trend"],
        "cli_cmd": "analytics coupons",
    },

    # ── Points ────────────────────────────────────────────────────────────────

    "dwd_member_points_log": {
        "domain": "points",
        "db": "das_demoen",
        "layer": "dwd",
        "purpose": "Atomic points transaction log — every earn and redeem event per member",
        "grain": "One row per points transaction",
        "date_col": "create_time",
        "key_dims": ["member_id", "change_type", "create_time"],
        "key_metrics": [
            "points      INT    — points earned (earn) or spent (redeem)",
            "change_type STRING — 'earn' | 'redeem' | 'expire' | 'adjust'",
        ],
        "bitmap_cols": [],
        "caveats": [
            "Aggregate with SUM(CASE WHEN change_type='earn' THEN points END) for total earned",
            "Large table — always filter by create_time range",
        ],
        "use_cases": ["Daily points earn/redeem trend", "Per-member points history"],
        "cli_cmd": "analytics points --daily-trend",
    },

    "dws_points_base_metrics_d": {
        "domain": "points",
        "db": "das_demoen",
        "layer": "dws",
        "purpose": "Pre-aggregated daily points metrics — earn, consume, expire totals per day",
        "grain": "One row per biz_date",
        "date_col": "biz_date",
        "key_dims": ["biz_date"],
        "key_metrics": [
            "earn_points    BIGINT — points earned today",
            "consume_points BIGINT — points consumed today",
            "expire_points  BIGINT — points expired today",
            "earn_cnt       INT    — earn transaction count",
        ],
        "bitmap_cols": [],
        "caveats": [
            "Preferred over dwd_member_points_log for period summaries",
            "analytics points tries this table first (DWS-first pattern)",
        ],
        "use_cases": ["Points earn/consume trend", "Period summary dashboard"],
        "cli_cmd": "analytics points",
    },

    "ads_das_v_points_summary_analysis_d": {
        "domain": "points",
        "db": "das_demoen",
        "layer": "ads",
        "purpose": "Pre-aggregated daily points summary — issued, consumed, balance, liability",
        "grain": "One row per biz_date",
        "date_col": "biz_date",
        "key_dims": ["biz_date"],
        "key_metrics": [
            "points_issued   BIGINT — points issued today",
            "points_consumed BIGINT — points consumed today",
            "points_expired  BIGINT — points expired today",
            "points_balance  BIGINT — cumulative outstanding balance",
            "liability_cny   DOUBLE — estimated CNY liability of outstanding points",
        ],
        "bitmap_cols": [],
        "caveats": ["Preferred over dwd_member_points_log for dashboard queries"],
        "use_cases": ["Points health dashboard", "Liability tracking", "Burn rate analysis"],
        "cli_cmd": "analytics loyalty  |  analytics points",
    },

    # ── Messaging ─────────────────────────────────────────────────────────────

    "vdm_t_message_record": {
        "domain": "messaging",
        "db": "dts_demoen",
        "layer": "src",
        "purpose": "Raw message send records — every outbound message per customer",
        "grain": "One row per message send attempt",
        "date_col": "create_time",
        "key_dims": ["customer_code", "channel_type", "template_id", "status"],
        "key_metrics": [
            "status         INT — 1=pending, 3=delivered, 4=failed, 5=opened",
            "operate_status INT — 1=opened, 2=clicked, 4=unsubscribed",
            "channel_type   INT — 1=SMS-CN, 2=SMS-Intl, 4=Email, 8=WeChat, 16=WhatsApp, 17=Line",
        ],
        "bitmap_cols": [],
        "caveats": [
            "status IN (3,5) for delivered messages",
            "Large table — always filter by create_time",
            "Lives in dts_demoen (source layer), not das_demoen",
        ],
        "use_cases": [
            "Channel delivery health",
            "Template open/click rates",
            "Message-to-purchase attribution",
        ],
        "cli_cmd": "messages health  |  messages template-stats  |  messages attribution",
    },

    "ads_das_v_message_analysis_d": {
        "domain": "messaging",
        "db": "das_demoen",
        "layer": "ads",
        "purpose": "Pre-aggregated daily message performance by channel",
        "grain": "One row per (channel_type, biz_date)",
        "date_col": "biz_date",
        "key_dims": ["channel_type", "biz_date"],
        "key_metrics": [
            "send_cnt      INT — messages sent",
            "success_cnt   INT — messages delivered",
            "fail_cnt      INT — messages failed",
            "open_cnt      INT — messages opened",
            "click_cnt     INT — links clicked",
        ],
        "bitmap_cols": [],
        "caveats": [
            "Grain is channel × day — no template_id dimension; use vdm_t_message_record for template-level detail",
            "messages template-stats tries this view first and falls back to vdm_t_message_record",
        ],
        "use_cases": ["Cross-channel delivery trend", "Failure spike detection"],
        "cli_cmd": "messages health  |  messages template-stats (ADS-first fallback)",
    },

    # ── Recommendation ────────────────────────────────────────────────────────

    "dwd_rec_user_product_rating": {
        "domain": "recommendation",
        "db": "das_demoen",
        "layer": "dwd",
        "purpose": "User-product affinity scores used by the recommendation engine",
        "grain": "One row per (customer_code, product_code)",
        "date_col": "update_time",
        "key_dims": ["customer_code", "product_code"],
        "key_metrics": ["rating FLOAT — affinity score (higher = stronger preference)"],
        "bitmap_cols": [],
        "caveats": ["Refreshed periodically by the ML pipeline; not real-time"],
        "use_cases": ["Product affinity analysis", "Recommendation quality audit"],
        "cli_cmd": "(not yet implemented)",
    },

    "dws_rec_user_recs": {
        "domain": "recommendation",
        "db": "das_demoen",
        "layer": "dws",
        "purpose": "Pre-computed recommendation list per user — top N products per customer",
        "grain": "One row per (customer_code, rec_rank)",
        "date_col": "rec_date",
        "key_dims": ["customer_code", "product_code", "rec_rank", "rec_date"],
        "key_metrics": ["score FLOAT — recommendation confidence score"],
        "bitmap_cols": [],
        "caveats": ["rec_rank=1 is the top recommendation for the customer"],
        "use_cases": ["Recommendation output inspection", "Conversion correlation"],
        "cli_cmd": "(not yet implemented)",
    },

    # ── Segments / Tags ───────────────────────────────────────────────────────

    "t_customer_group_history": {
        "domain": "segment",
        "db": "datanow_demoen",
        "layer": "src",
        "purpose": "Daily segment membership snapshots — bitmap of customers per segment per day",
        "grain": "One row per (group_id, snapshot_date)",
        "date_col": "snapshot_date",
        "key_dims": ["group_id", "snapshot_date"],
        "key_metrics": ["member_bitmap BITMAP — bitmap of member IDs in segment on that day"],
        "bitmap_cols": ["member_bitmap"],
        "caveats": [
            "Column may be named biz_date in some tenants — query with fallback",
            "Use BITMAP_COUNT(BITMAP_UNION(member_bitmap)) for total unique members over period",
        ],
        "use_cases": ["Segment size trend", "Segment growth/shrink analysis"],
        "cli_cmd": "segments growth",
    },

    "t_customer_tag_result": {
        "domain": "segment",
        "db": "datanow_demoen",
        "layer": "src",
        "purpose": "Customer tag assignment results — current tag values per customer",
        "grain": "One row per (customer_code, tag_id)",
        "date_col": None,
        "key_dims": ["customer_code", "tag_id", "tag_value"],
        "key_metrics": ["COUNT(DISTINCT customer_code) — coverage count per tag"],
        "bitmap_cols": [],
        "caveats": [
            "No date column — always reflects the latest computed tag values",
            "Use QUALIFY ROW_NUMBER() OVER (PARTITION BY tag_id ORDER BY cnt DESC) for top values",
        ],
        "use_cases": ["Tag coverage audit", "Tag value distribution"],
        "cli_cmd": "tags coverage",
    },
}

# Domain grouping for the domain map
DOMAINS = {
    "activity":       "Campaign & journey analytics (ads_das_activity_*)",
    "customer":       "Member KPIs, tier, RFM, churn, source (ads_das_custs_*, ads_v_rfm, dws_customer_*)",
    "transaction":    "Orders, GMV, repurchase, AOV (dwd_v_order, dws_order_*, ads_das_v_repurchase_*)",
    "coupon":         "Coupon issuance, redemption, ROI (dwd_coupon_instance, ads_das_v_coupon_*)",
    "points":         "Points earn/burn/liability (dwd_member_points_log, ads_das_v_points_*)",
    "messaging":      "Message delivery, open/click, attribution (vdm_t_message_record, ads_das_v_message_*)",
    "recommendation": "Product affinity & rec engine output (dwd_rec_*, dws_rec_*)",
    "segment":        "Segment snapshots & tag assignments (t_customer_group_history, t_customer_tag_result)",
}

LAYER_COLORS = {
    "ads": "green",
    "dws": "cyan",
    "dwd": "yellow",
    "dim": "blue",
    "src": "dim",
}

LAYER_DESC = {
    "ads": "ADS — application-ready aggregates (fastest, use first)",
    "dws": "DWS — subject-level pre-aggregated metrics",
    "dwd": "DWD — detail/atomic warehouse layer",
    "dim": "DIM — dimension/reference tables",
    "src": "SRC — source/ODS layer (raw, large tables)",
}


# =============================================================================
# Commands
# =============================================================================

@app.command("domains")
def schema_domains() -> None:
    """Business domain map — shows all domains and their key tables.

    Use this to orient yourself before searching for a specific table.

    Examples:
        sh schema domains
    """
    tbl = Table(
        title="Warehouse Domain Map",
        box=rich_box.ROUNDED, header_style="bold cyan",
    )
    tbl.add_column("Domain",      style="bold", min_width=14)
    tbl.add_column("Key Tables / Description", max_width=60)
    tbl.add_column("CLI Command", style="dim", max_width=35)

    domain_cmds: dict[str, list] = {}
    for name, meta in SCHEMA.items():
        d = meta["domain"]
        if d not in domain_cmds:
            domain_cmds[d] = []
        cmd = meta.get("cli_cmd", "")
        if cmd and cmd not in domain_cmds[d]:
            domain_cmds[d].append(cmd)

    for domain, description in DOMAINS.items():
        cmds = "  |  ".join(domain_cmds.get(domain, []))[:60]
        tbl.add_row(domain, description, cmds or "—")

    console.print(tbl)

    # Layer legend
    console.print("\n[bold]Data Layers[/bold] (choose the highest applicable layer for performance):")
    for layer, desc in LAYER_DESC.items():
        color = LAYER_COLORS.get(layer, "white")
        console.print(f"  [{color}]{layer.upper():4s}[/{color}]  {desc}")

    console.print(
        "\n[dim]Tip: sh schema search <keyword>  to find tables by business term[/dim]"
    )


@app.command("search")
def schema_search(
    keyword: str = typer.Argument(..., help="Business keyword (e.g. churn, coupon, rfm, repurchase)"),
) -> None:
    """Search tables and fields by business keyword.

    Matches against table names, purpose descriptions, field names,
    and use-case descriptions.

    Examples:
        sh schema search churn
        sh schema search repurchase
        sh schema search coupon redeem
        sh schema search rfm
    """
    kw = keyword.lower()

    results = []
    for table, meta in SCHEMA.items():
        score = 0
        matched_fields = []

        # Score: table name match (highest weight)
        if kw in table.lower():
            score += 10

        # Score: domain match
        if kw in meta.get("domain", "").lower():
            score += 8

        # Score: purpose description
        if kw in meta.get("purpose", "").lower():
            score += 5

        # Score: use cases
        for uc in meta.get("use_cases", []):
            if kw in uc.lower():
                score += 3
                break

        # Score: field names / metrics
        for f in meta.get("key_metrics", []):
            if kw in f.lower():
                score += 2
                matched_fields.append(f.split()[0])

        for f in meta.get("key_dims", []):
            if kw in f.lower():
                score += 2
                matched_fields.append(f)

        if score > 0:
            results.append((score, table, meta, matched_fields))

    results.sort(key=lambda x: -x[0])

    if not results:
        console.print(f"[yellow]No tables found matching '{keyword}'[/yellow]")
        console.print("[dim]Try: sh schema domains  to browse all domains[/dim]")
        return

    tbl = Table(
        title=f"Schema Search: '{keyword}'  ({len(results)} results)",
        box=rich_box.SIMPLE_HEAVY, header_style="bold cyan",
    )
    tbl.add_column("Table",    max_width=38)
    tbl.add_column("Layer",    width=5)
    tbl.add_column("DB",       style="dim", width=14)
    tbl.add_column("Purpose",  max_width=45)
    tbl.add_column("CLI",      style="dim", max_width=30)

    for score, table, meta, mf in results:
        layer = meta.get("layer", "—")
        color = LAYER_COLORS.get(layer, "white")
        tbl.add_row(
            table,
            f"[{color}]{layer.upper()}[/{color}]",
            meta.get("db", "—"),
            meta.get("purpose", "—"),
            meta.get("cli_cmd", "—"),
        )

    console.print(tbl)
    console.print(
        "[dim]Tip: sh schema show <table_name>  for grain, fields, and caveats[/dim]"
    )


@app.command("show")
def schema_show(
    table: str = typer.Argument(..., help="Table or view name"),
) -> None:
    """Show full table metadata: purpose, grain, key fields, caveats, CLI commands.

    Examples:
        sh schema show dwd_v_order
        sh schema show ads_v_rfm
        sh schema show ads_das_activity_analysis_d
    """
    meta = SCHEMA.get(table)
    if meta is None:
        # Fuzzy fallback
        matches = [t for t in SCHEMA if table.lower() in t.lower()]
        if matches:
            console.print(f"[yellow]'{table}' not found. Did you mean:[/yellow]")
            for m in matches[:5]:
                console.print(f"  sh schema show {m}")
        else:
            console.print(f"[red]Table '{table}' not found in schema registry.[/red]")
            console.print("[dim]Try: sh schema search <keyword>[/dim]")
        return

    layer = meta.get("layer", "—")
    lcolor = LAYER_COLORS.get(layer, "white")

    console.print(Panel(
        f"[bold]{table}[/bold]\n"
        f"Domain: [cyan]{meta.get('domain', '—')}[/cyan]  "
        f"Layer: [{lcolor}]{layer.upper()}[/{lcolor}]  "
        f"DB: [dim]{meta.get('db', '—')}[/dim]\n\n"
        f"[bold]Purpose:[/bold] {meta.get('purpose', '—')}\n"
        f"[bold]Grain:[/bold]   {meta.get('grain', '—')}\n"
        f"[bold]Date column:[/bold] {meta.get('date_col') or '— (no date column)'}",
        title="[bold cyan]Table Detail[/bold cyan]",
        border_style="cyan",
    ))

    # Key dimensions
    dims = meta.get("key_dims", [])
    if dims:
        console.print("[bold]Key Dimensions:[/bold]")
        for d in dims:
            console.print(f"  [dim]-[/dim] {d}")

    # Key metrics
    metrics = meta.get("key_metrics", [])
    if metrics:
        console.print("\n[bold]Key Metrics:[/bold]")
        for m in metrics:
            console.print(f"  [green]+[/green] {m}")

    # Bitmap columns
    bitmaps = meta.get("bitmap_cols", [])
    if bitmaps:
        console.print("\n[bold]Bitmap Columns[/bold] [dim](use BITMAP_COUNT(BITMAP_UNION(...)))[/dim]:")
        for b in bitmaps:
            console.print(f"  [magenta]*[/magenta] {b}")

    # Caveats
    caveats = meta.get("caveats", [])
    if caveats:
        console.print("\n[bold]Caveats:[/bold]")
        for c in caveats:
            console.print(f"  [yellow]![/yellow] {c}")

    # Use cases
    use_cases = meta.get("use_cases", [])
    if use_cases:
        console.print("\n[bold]Use Cases:[/bold]")
        for u in use_cases:
            console.print(f"  [cyan]>[/cyan] {u}")

    # CLI command
    cli_cmd = meta.get("cli_cmd")
    if cli_cmd:
        console.print(f"\n[bold]CLI Command:[/bold] [green]{cli_cmd}[/green]")

    console.print(
        "\n[dim]Tip: sh schema fields <table>  for field-level dictionary[/dim]"
    )


@app.command("fields")
def schema_fields(
    table: str = typer.Argument(..., help="Table or view name"),
) -> None:
    """Field dictionary for a table — dimensions, metrics, bitmaps, control fields.

    Examples:
        sh schema fields dwd_v_order
        sh schema fields ads_das_activity_analysis_d
    """
    meta = SCHEMA.get(table)
    if meta is None:
        matches = [t for t in SCHEMA if table.lower() in t.lower()]
        if matches:
            console.print(f"[yellow]'{table}' not found. Did you mean:[/yellow]")
            for m in matches[:5]:
                console.print(f"  sh schema fields {m}")
        else:
            console.print(f"[red]Table '{table}' not found.[/red]")
        return

    tbl = Table(
        title=f"Field Dictionary — {table}",
        box=rich_box.SIMPLE_HEAVY, header_style="bold cyan",
    )
    tbl.add_column("Field",       max_width=32)
    tbl.add_column("Category",    width=10)
    tbl.add_column("Type / Description", max_width=55)

    date_col = meta.get("date_col")
    bitmap_set = set(meta.get("bitmap_cols", []))

    for d in meta.get("key_dims", []):
        category = "DATE" if d == date_col else "DIM"
        color = "blue" if category == "DATE" else "cyan"
        tbl.add_row(d, f"[{color}]{category}[/{color}]", "Dimension / filter key")

    for m in meta.get("key_metrics", []):
        parts = m.split("—", 1)
        name_type = parts[0].strip()
        desc = parts[1].strip() if len(parts) > 1 else ""
        name = name_type.split()[0]
        col_type = " ".join(name_type.split()[1:]) if len(name_type.split()) > 1 else ""
        category = "BITMAP" if name in bitmap_set else "METRIC"
        color = "magenta" if category == "BITMAP" else "green"
        tbl.add_row(
            name,
            f"[{color}]{category}[/{color}]",
            f"{col_type}  {desc}".strip(),
        )

    console.print(tbl)

    if bitmap_set:
        console.print(
            "[dim]BITMAP fields require BITMAP_COUNT(BITMAP_UNION(col)) "
            "to aggregate across rows.[/dim]"
        )


# =============================================================================
# Metric Registry — standardized business metric definitions (F2)
# =============================================================================

METRICS: dict[str, dict] = {
    "active_customer": {
        "label": "Active Customer (活跃客户)",
        "definition": "A customer who performed any qualifying action (order, login, points event) within the lookback window.",
        "numerator": "BITMAP_COUNT(BITMAP_UNION(active_custs_bitnum))",
        "denominator": "N/A — absolute headcount",
        "source_table": "ads_das_business_overview_d",
        "source_field": "active_custs_bitnum",
        "window": "Configurable per tenant (typically 30 or 90 days)",
        "caveats": ["Definition varies by tenant; check system settings for exact qualifying events"],
        "cli_cmd": "analytics overview",
    },
    "buyer": {
        "label": "Buyer (购买客户)",
        "definition": "A customer who completed at least one valid order (delete_flag=0, direction=0) in the period.",
        "numerator": "COUNT(DISTINCT customer_code) WHERE direction=0 AND delete_flag=0",
        "denominator": "N/A — absolute headcount",
        "source_table": "dwd_v_order  /  ads_das_business_overview_d.buying_custs_bitnum",
        "source_field": "buying_custs_bitnum",
        "window": "The analysis period",
        "caveats": ["Excludes returns (direction=1) and deleted records"],
        "cli_cmd": "analytics overview  |  analytics orders",
    },
    "repurchase_rate": {
        "label": "Repurchase Rate (复购率)",
        "definition": "Proportion of buyers who placed 2 or more orders within the analysis period.",
        "numerator": "COUNT(DISTINCT customer_code WHERE order_count >= 2)",
        "denominator": "COUNT(DISTINCT customer_code WHERE order_count >= 1)",
        "source_table": "dwd_v_order  (computed via ROW_NUMBER window function)",
        "source_field": "Derived — no pre-built column",
        "window": "The analysis period (30d / 90d / 365d)",
        "caveats": [
            "Both orders must fall within the same period window",
            "Differs from 'ever repurchased' (lifetime) — this is period-scoped",
            "ads_das_v_repurchase_analysis_d may use a different definition",
        ],
        "cli_cmd": "analytics repurchase",
    },
    "churn": {
        "label": "Churned Customer (已流失客户)",
        "definition": "A previously active customer who has not made any qualifying action beyond the churn threshold window.",
        "numerator": "BITMAP_COUNT(BITMAP_UNION(churn_custs_bitnum))",
        "denominator": "N/A — absolute headcount",
        "source_table": "ads_das_business_overview_d",
        "source_field": "churn_custs_bitnum",
        "window": "Threshold configured per tenant (typically 90 or 180 days of inactivity)",
        "caveats": [
            "Churn threshold is tenant-configurable — verify before comparing across tenants",
            "Distinct from pre-churn: churn = already lost, pre-churn = at risk",
        ],
        "cli_cmd": "members churn  |  members overview",
    },
    "pre_churn": {
        "label": "Pre-Churn / At-Risk Customer (预流失客户)",
        "definition": "An active customer showing behavioral signals (declining frequency, recency gap) that predict future churn.",
        "numerator": "BITMAP_COUNT(BITMAP_UNION(pre_churn_bitnum))",
        "denominator": "N/A — absolute headcount",
        "source_table": "ads_das_business_overview_d  /  ads_das_custs_tier_distribution_d",
        "source_field": "pre_churn_bitnum",
        "window": "Rolling lookback; threshold configured per tenant",
        "caveats": ["Prediction model sensitivity varies by tenant configuration"],
        "cli_cmd": "members at-risk  |  members churn",
    },
    "aov": {
        "label": "Average Order Value — AOV (客单价)",
        "definition": "Average revenue per completed order in the period.",
        "numerator": "SUM(total_amount)  [in fen]",
        "denominator": "COUNT(DISTINCT code)  [valid orders]",
        "source_table": "dwd_v_order",
        "source_field": "total_amount (fen) / code",
        "window": "The analysis period",
        "caveats": [
            "total_amount is in fen — divide by 100 for CNY",
            "Filter delete_flag=0 AND direction=0 for valid sales only",
        ],
        "cli_cmd": "analytics orders",
    },
    "gmv": {
        "label": "GMV — Gross Merchandise Value (商品交易总额)",
        "definition": "Total revenue from all completed sales orders before deducting returns.",
        "numerator": "SUM(total_amount WHERE direction=0 AND delete_flag=0)  [in fen]",
        "denominator": "N/A — sum metric",
        "source_table": "dwd_v_order  /  dws_order_base_metrics_d.gmv",
        "source_field": "total_amount",
        "window": "The analysis period",
        "caveats": [
            "Gross — does not net out returns",
            "All values in fen; divide by 100 for CNY",
            "Use dws_order_base_metrics_d for pre-aggregated daily GMV (faster)",
        ],
        "cli_cmd": "analytics overview  |  analytics orders",
    },
    "roi": {
        "label": "Campaign / Coupon ROI",
        "definition": "Attributed GMV generated per unit of cost (discount or points value) for a campaign or coupon rule.",
        "numerator": "SUM(attributed order total_amount)  [fen]",
        "denominator": "SUM(discount / points value issued)  [fen]",
        "source_table": "dwd_coupon_instance  JOIN  dwd_v_order  (coupon ROI)\nads_das_activity_analysis_d  JOIN  dwd_v_order  (campaign ROI)",
        "source_field": "par_value (coupon)  /  activity_Points_Issued (campaign)",
        "window": "Same period as issuance; attribution window configurable",
        "caveats": [
            "Attribution model: last-touch — orders within the attribution window after coupon/campaign participation",
            "ROI < 1x means discount cost exceeded attributed revenue",
            "Does not account for counterfactual (would the purchase have happened anyway?)",
        ],
        "cli_cmd": "analytics coupons --by-rule  |  analytics campaigns --roi",
    },
    "redeem_rate": {
        "label": "Coupon Redeem Rate (优惠券核销率)",
        "definition": "Proportion of issued coupons that were successfully redeemed.",
        "numerator": "COUNT(id WHERE status=2)  [redeemed]",
        "denominator": "COUNT(id)  [total issued]",
        "source_table": "dwd_coupon_instance",
        "source_field": "status  (2=redeemed)",
        "window": "Based on create_time of issuance",
        "caveats": [
            "status=1 unused, status=2 used/redeemed, status=3 expired",
            "Expired coupons are in the denominator — adjust if comparing only valid period",
        ],
        "cli_cmd": "analytics coupons",
    },
    "message_success_rate": {
        "label": "Message Delivery Success Rate (消息投递成功率)",
        "definition": "Proportion of sent messages that were successfully delivered to the recipient.",
        "numerator": "COUNT(id WHERE status IN (3,5))  [delivered or opened]",
        "denominator": "COUNT(id)  [all sent attempts]",
        "source_table": "vdm_t_message_record",
        "source_field": "status  (3=delivered, 4=failed, 5=opened)",
        "window": "Based on create_time",
        "caveats": [
            "status=3 is delivered (no open), status=5 includes open event",
            "channel_type: 1=SMS-CN 2=SMS-Intl 4=Email 8=WeChat 16=WhatsApp 17=Line",
            "Delivery semantics differ by channel (e.g. WhatsApp delivery vs SMS delivery)",
        ],
        "cli_cmd": "messages health",
    },
    "ltv": {
        "label": "Customer Lifetime Value — LTV (客户生命周期价值)",
        "definition": "Cumulative GMV per customer within a cohort, tracked month-by-month from first order.",
        "numerator": "SUM(total_amount per customer in cohort up to month M)  [fen / 100]",
        "denominator": "COUNT(DISTINCT customer_code in cohort)",
        "source_table": "dwd_v_order  (self-aggregated by first-order month cohort)",
        "source_field": "total_amount, order_date",
        "window": "M0 = first-order month; M1/M2/... = subsequent months",
        "caveats": [
            "LTV here is realized historical GMV, not predicted future value",
            "Cohort size shrinks at higher M values (customers who joined recently have fewer follow-up months)",
        ],
        "cli_cmd": "analytics ltv",
    },
    "points_liability": {
        "label": "Points Liability (积分负债)",
        "definition": "Estimated monetary value of all unredeemed outstanding points — represents a financial liability on the books.",
        "numerator": "SUM(outstanding points balance)",
        "denominator": "N/A — converted at the configured points-to-CNY exchange rate",
        "source_table": "ads_das_v_points_summary_analysis_d",
        "source_field": "points_balance  *  exchange_rate",
        "window": "Latest snapshot",
        "caveats": [
            "Exchange rate is configured per loyalty program",
            "Liability decreases when points are redeemed or expire",
        ],
        "cli_cmd": "analytics loyalty  |  analytics points",
    },
    "coverage_rate": {
        "label": "Tag Coverage Rate (标签覆盖率)",
        "definition": "Proportion of total customers who have been assigned a value for a given tag.",
        "numerator": "COUNT(DISTINCT customer_code WHERE tag_id = X)",
        "denominator": "COUNT(DISTINCT customer_code)  [in dim_customer_info]",
        "source_table": "t_customer_tag_result  /  dim_customer_info",
        "source_field": "customer_code, tag_id",
        "window": "Latest computed tag snapshot (no date column)",
        "caveats": ["Low coverage (< 40%) typically indicates incomplete tag rule execution or missing source data"],
        "cli_cmd": "tags coverage",
    },
}


@app.command("metrics")
def schema_metrics(
    name: str | None = typer.Argument(None, help="Metric name (omit to list all)"),
) -> None:
    """Standardized metric definitions — governance layer (F2).

    Shows the authoritative definition, data source, numerator/denominator,
    and caveats for each key business metric.

    Examples:
        sh schema metrics                  # list all metrics
        sh schema metrics repurchase_rate  # detail for one metric
        sh schema metrics churn
    """
    if name is None:
        # List all metrics
        tbl = Table(
            title="Standardized Metric Definitions",
            box=rich_box.SIMPLE_HEAVY, header_style="bold cyan",
        )
        tbl.add_column("Metric Key",  style="bold", min_width=20)
        tbl.add_column("Label",       max_width=32)
        tbl.add_column("Source Table",style="dim", max_width=35)
        tbl.add_column("CLI",         style="dim", max_width=30)

        for key, m in METRICS.items():
            tbl.add_row(
                key,
                m["label"],
                m["source_table"].split("\n")[0],
                m.get("cli_cmd", "—"),
            )

        console.print(tbl)
        console.print(
            "[dim]Tip: sh schema metrics <name>  for full definition with numerator/denominator[/dim]"
        )
        return

    # Fuzzy match
    key = name.lower().replace("-", "_")
    meta = METRICS.get(key)
    if meta is None:
        matches = [k for k in METRICS if key in k or k in key]
        if matches:
            console.print(f"[yellow]'{name}' not found. Did you mean:[/yellow]")
            for m in matches[:5]:
                console.print(f"  sh schema metrics {m}")
        else:
            console.print(f"[red]Metric '{name}' not found.[/red]")
            console.print("[dim]Run: sh schema metrics  to see all available metrics[/dim]")
        return

    console.print(Panel(
        f"[bold]{meta['label']}[/bold]\n\n"
        f"{meta['definition']}",
        title=f"[bold cyan]Metric: {key}[/bold cyan]",
        border_style="cyan",
    ))

    console.print(f"[bold]Numerator:[/bold]   [green]{meta['numerator']}[/green]")
    console.print(f"[bold]Denominator:[/bold] [green]{meta['denominator']}[/green]")
    console.print(f"\n[bold]Source Table:[/bold]  [dim]{meta['source_table']}[/dim]")
    console.print(f"[bold]Source Field:[/bold]  [dim]{meta['source_field']}[/dim]")
    console.print(f"[bold]Window:[/bold]        {meta['window']}")

    caveats = meta.get("caveats", [])
    if caveats:
        console.print("\n[bold]Caveats:[/bold]")
        for c in caveats:
            console.print(f"  [yellow]![/yellow] {c}")

    console.print(f"\n[bold]CLI Command:[/bold] [green]{meta.get('cli_cmd', '—')}[/green]")
