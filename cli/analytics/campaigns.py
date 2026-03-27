"""Campaign analytics functions."""

import re

from rich.console import Console

from ..api.mcp_client import MCPClient, MCPConfig as MCPClientConfig, MCPError
from ..output.export import format_output
from .common import (
    _compute_date_range,
    _mcp_query_timeout,
    _safe_date_filter,
)

console = Console()


def _sanitize_string_input(value: str, max_length: int = 100) -> str:
    """Sanitize string input for SQL queries.

    Removes dangerous characters and limits length.
    """
    if not value:
        return ""
    # Remove any characters that could be used for SQL injection
    sanitized = re.sub(r"['\";\\%_\-\-]", "", str(value))
    return sanitized[:max_length]


def _get_mcp_campaigns(config, period: str, campaign_id: str = None, name: str = None) -> list:
    """Get campaign analytics from MCP database.

    Merges two sources:
    - ads_das_activity_channel_effect_d : funnel metrics (target/reach/click/convert)
    - ads_das_activity_analysis_d        : reward metrics (points/coupons/messages/participants)
    """
    # Validate and compute safe date range
    start_date, _ = _compute_date_range(period)

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    database = config.mcp.database

    with MCPClient(mcp_config) as client:
        client.initialize()

        # --- Query 1: funnel metrics ---
        conditions = []
        if start_date:
            date_str = start_date.isoformat()
            if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
                conditions.append(f"create_time >= '{date_str}'")

        if campaign_id:
            safe_id = _sanitize_string_input(campaign_id, 50)
            if safe_id:
                conditions.append(f"activity_id = '{safe_id}'")

        if name:
            safe_name = _sanitize_string_input(name, 100)
            if safe_name:
                conditions.append(f"activity_name LIKE '%{safe_name}%'")

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        funnel_rows = client.query(f"""
            SELECT
                activity_id,
                activity_name,
                activity_type,
                status,
                start_time,
                end_time,
                target_count,
                reach_count,
                click_count,
                convert_count
            FROM ads_das_activity_channel_effect_d
            {where_clause}
            ORDER BY create_time DESC
            LIMIT 50
        """, database=database)

        if not isinstance(funnel_rows, list):
            return []

        # --- Query 2: reward metrics from ads_das_activity_analysis_d ---
        reward_where = ""
        if start_date:
            date_str = start_date.isoformat()
            if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
                reward_where = f"WHERE biz_date >= '{date_str}'"

        reward_rows = client.query(f"""
            SELECT
                activity_code,
                BITMAP_COUNT(BITMAP_UNION(activity_custs_bitnum)) AS participants,
                SUM(activity_Points_Issued)      AS points_issued,
                SUM(activity_coupon_issue_qty)   AS coupons_issued,
                SUM(activity_msg_send_num)       AS messages_sent
            FROM ads_das_activity_analysis_d
            {reward_where}
            GROUP BY activity_code
        """, database=database)

        # Build lookup: activity_code -> reward metrics
        reward_map = {}
        if isinstance(reward_rows, list):
            for r in reward_rows:
                code = str(r.get("activity_code") or "")
                if code:
                    reward_map[code] = r

        # Merge: activity_id in funnel == activity_code in analysis
        for row in funnel_rows:
            aid = str(row.get("activity_id") or "")
            reward = reward_map.get(aid, {})
            row["participants"]   = reward.get("participants") or 0
            row["points_issued"]  = reward.get("points_issued") or 0
            row["coupons_issued"] = reward.get("coupons_issued") or 0
            row["messages_sent"]  = reward.get("messages_sent") or 0

        return funnel_rows


def _print_campaigns_mcp(rows: list, export_path: str = None) -> None:
    """Rich table output for MCP campaign results (funnel + reward metrics)."""
    from rich.table import Table
    from rich import box as rich_box

    if not rows:
        console.print("[yellow]No campaign data found[/yellow]")
        return

    if export_path:
        format_output(rows, "json", export_path)
        return

    t = Table(box=rich_box.ROUNDED, header_style="bold cyan", show_lines=False)
    t.add_column("ID",         style="dim",  max_width=14)
    t.add_column("Name",                     max_width=24)
    t.add_column("Status",     style="dim",  max_width=10)
    t.add_column("Target",     justify="right")
    t.add_column("Reach",      justify="right")
    t.add_column("Click",      justify="right")
    t.add_column("Convert",    justify="right")
    t.add_column("Participants", justify="right", style="cyan")
    t.add_column("Pts Issued", justify="right", style="green")
    t.add_column("Coupons",    justify="right", style="green")
    t.add_column("Messages",   justify="right", style="green")

    def _n(v):
        try:
            return f"{int(v or 0):,}"
        except (TypeError, ValueError):
            return "-"

    def _rate(part, total):
        try:
            p, t_ = int(part or 0), int(total or 0)
            return f"{p/t_*100:.0f}%" if t_ else "-"
        except (TypeError, ValueError, ZeroDivisionError):
            return "-"

    for r in rows:
        reach   = r.get("reach_count")
        target  = r.get("target_count")
        convert = r.get("convert_count")
        t.add_row(
            str(r.get("activity_id") or "-"),
            str(r.get("activity_name") or "-"),
            str(r.get("status") or "-"),
            _n(target),
            f"{_n(reach)} ({_rate(reach, target)})",
            _n(r.get("click_count")),
            f"{_n(convert)} ({_rate(convert, reach)})",
            _n(r.get("participants")),
            _n(r.get("points_issued")),
            _n(r.get("coupons_issued")),
            _n(r.get("messages_sent")),
        )

    console.print()
    console.print(t)
    console.print(f"[dim]{len(rows)} campaign(s) | Reach% = reach/target | Convert% = convert/reach[/dim]")


def _get_mcp_campaign_detail(config, campaign_id: str) -> dict:
    """Get single campaign deep analysis: funnel + rewards + daily trend.

    Combines ads_das_activity_channel_effect_d (funnel) and
    ads_das_activity_analysis_d (rewards + daily).
    """
    safe_id = _sanitize_string_input(campaign_id, 50)
    if not safe_id:
        return {}

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    database = config.mcp.database

    with MCPClient(mcp_config) as client:
        client.initialize()

        # Funnel totals for this campaign
        funnel_rows = client.query(f"""
            SELECT
                activity_id,
                activity_name,
                activity_type,
                status,
                start_time,
                end_time,
                SUM(target_count)  AS target_count,
                SUM(reach_count)   AS reach_count,
                SUM(click_count)   AS click_count,
                SUM(convert_count) AS convert_count
            FROM ads_das_activity_channel_effect_d
            WHERE activity_id = '{safe_id}'
            GROUP BY activity_id, activity_name, activity_type, status, start_time, end_time
        """, database=database)

        # Reward totals
        reward_rows = client.query(f"""
            SELECT
                activity_code,
                BITMAP_COUNT(BITMAP_UNION(activity_custs_bitnum)) AS participants,
                SUM(activity_Points_Issued)    AS points_issued,
                SUM(activity_coupon_issue_qty) AS coupons_issued,
                SUM(activity_msg_send_num)     AS messages_sent
            FROM ads_das_activity_analysis_d
            WHERE activity_code = '{safe_id}'
            GROUP BY activity_code
        """, database=database)

        # Daily trend (last 30 days of this campaign's data)
        daily_rows = client.query(f"""
            SELECT
                biz_date,
                BITMAP_COUNT(BITMAP_UNION(activity_custs_bitnum)) AS participants,
                SUM(activity_Points_Issued)    AS points_issued,
                SUM(activity_coupon_issue_qty) AS coupons_issued
            FROM ads_das_activity_analysis_d
            WHERE activity_code = '{safe_id}'
            GROUP BY biz_date
            ORDER BY biz_date DESC
            LIMIT 30
        """, database=database)

    funnel = funnel_rows[0] if isinstance(funnel_rows, list) and funnel_rows else {}
    reward = reward_rows[0] if isinstance(reward_rows, list) and reward_rows else {}

    return {
        "campaign_id": campaign_id,
        "activity_name": funnel.get("activity_name") or campaign_id,
        "activity_type": funnel.get("activity_type") or "-",
        "status": funnel.get("status") or "-",
        "start_time": funnel.get("start_time") or "-",
        "end_time": funnel.get("end_time") or "-",
        # Funnel
        "target_count": int(funnel.get("target_count") or 0),
        "reach_count": int(funnel.get("reach_count") or 0),
        "click_count": int(funnel.get("click_count") or 0),
        "convert_count": int(funnel.get("convert_count") or 0),
        # Rewards
        "participants": int(reward.get("participants") or 0),
        "points_issued": int(reward.get("points_issued") or 0),
        "coupons_issued": int(reward.get("coupons_issued") or 0),
        "messages_sent": int(reward.get("messages_sent") or 0),
        # Daily
        "daily": daily_rows if isinstance(daily_rows, list) else [],
    }


def _print_campaign_detail(data: dict) -> None:
    """Rich display for single campaign deep analysis."""
    from rich.table import Table
    from rich import box as rich_box
    from rich.panel import Panel
    from rich.columns import Columns

    if not data:
        console.print("[yellow]No data found for this campaign[/yellow]")
        return

    def _n(v):
        try:
            return f"{int(v or 0):,}"
        except (TypeError, ValueError):
            return "-"

    def _rate(part, total):
        try:
            p, t = int(part or 0), int(total or 0)
            return f"{p / t * 100:.1f}%" if t else "-"
        except (TypeError, ValueError, ZeroDivisionError):
            return "-"

    # Header panel
    header = (
        f"[bold]{data.get('activity_name')}[/bold]  "
        f"[dim]({data.get('campaign_id')})[/dim]\n"
        f"Type: {data.get('activity_type')}  |  Status: [cyan]{data.get('status')}[/cyan]\n"
        f"Period: {data.get('start_time')} → {data.get('end_time')}"
    )
    console.print(Panel(header, title="Campaign Detail", border_style="cyan"))

    # Funnel table
    target  = data.get("target_count", 0)
    reach   = data.get("reach_count", 0)
    click   = data.get("click_count", 0)
    convert = data.get("convert_count", 0)

    ft = Table(title="Funnel", box=rich_box.SIMPLE, header_style="bold")
    ft.add_column("Stage")
    ft.add_column("Count", justify="right")
    ft.add_column("Rate", justify="right")
    ft.add_row("Target",  _n(target),  "-")
    ft.add_row("Reach",   _n(reach),   _rate(reach, target))
    ft.add_row("Click",   _n(click),   _rate(click, reach))
    ft.add_row("Convert", _n(convert), _rate(convert, reach))
    console.print(ft)

    # Rewards table
    rt = Table(title="Rewards", box=rich_box.SIMPLE, header_style="bold")
    rt.add_column("Metric")
    rt.add_column("Value", justify="right")
    rt.add_row("[cyan]Unique Participants[/cyan]", _n(data.get("participants")))
    rt.add_row("[green]Points Issued[/green]",     _n(data.get("points_issued")))
    rt.add_row("[green]Coupons Issued[/green]",    _n(data.get("coupons_issued")))
    rt.add_row("[green]Messages Sent[/green]",     _n(data.get("messages_sent")))
    console.print(rt)

    # Daily trend
    daily = data.get("daily", [])
    if daily:
        dt = Table(title="Daily Trend (latest 30 days)", box=rich_box.SIMPLE, header_style="bold dim")
        dt.add_column("Date")
        dt.add_column("Participants", justify="right", style="cyan")
        dt.add_column("Points", justify="right", style="green")
        dt.add_column("Coupons", justify="right", style="green")
        for row in daily:
            dt.add_row(
                str(row.get("biz_date") or "-"),
                _n(row.get("participants")),
                _n(row.get("points_issued")),
                _n(row.get("coupons_issued")),
            )
        console.print(dt)


def _get_mcp_campaign_audience(config, campaign_id: str) -> list:
    """Compute campaign audience overlap with each tier using BITMAP_AND.

    Uses Doris CTE to:
    1. Aggregate campaign participant bitmap from ads_das_activity_analysis_d
    2. Aggregate tier member bitmaps from ads_das_custs_tier_distribution_d (latest date)
    3. BITMAP_AND each tier against campaign participants → count per tier

    Returns list of dicts: tier_code, tier_name, in_campaign, tier_total, coverage_pct
    """
    safe_id = _sanitize_string_input(campaign_id, 50)
    if not safe_id:
        return []

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    database = config.mcp.database

    with MCPClient(mcp_config) as client:
        client.initialize()

        rows = client.query(f"""
            WITH campaign_bitmap AS (
                SELECT BITMAP_UNION(activity_custs_bitnum) AS bits
                FROM ads_das_activity_analysis_d
                WHERE activity_code = '{safe_id}'
            ),
            latest_tier AS (
                SELECT MAX(biz_date) AS d
                FROM ads_das_custs_tier_distribution_d
            ),
            tier_bits AS (
                SELECT
                    t.tier_code,
                    t.tier_name,
                    BITMAP_UNION(t.custs_bitnum)               AS bits,
                    BITMAP_COUNT(BITMAP_UNION(t.custs_bitnum)) AS tier_total
                FROM ads_das_custs_tier_distribution_d t
                CROSS JOIN latest_tier lt
                WHERE t.biz_date = lt.d
                  AND t.identity_type = 1
                GROUP BY t.tier_code, t.tier_name
            )
            SELECT
                tb.tier_code,
                tb.tier_name,
                BITMAP_COUNT(BITMAP_AND(cb.bits, tb.bits)) AS in_campaign,
                tb.tier_total,
                BITMAP_COUNT(cb.bits) AS campaign_total
            FROM tier_bits tb
            CROSS JOIN campaign_bitmap cb
            ORDER BY in_campaign DESC
        """, database=database)

    result = []
    if isinstance(rows, list):
        for r in rows:
            in_camp = int(r.get("in_campaign") or 0)
            tier_total = int(r.get("tier_total") or 0)
            camp_total = int(r.get("campaign_total") or 0)
            result.append({
                "tier_code": r.get("tier_code") or "-",
                "tier_name": r.get("tier_name") or r.get("tier_code") or "-",
                "in_campaign": in_camp,
                "tier_total": tier_total,
                "campaign_total": camp_total,
                # % of this tier that's in the campaign
                "tier_coverage_pct": round(in_camp / tier_total * 100, 2) if tier_total else 0,
                # % this tier contributes to total campaign audience
                "audience_share_pct": round(in_camp / camp_total * 100, 2) if camp_total else 0,
            })
    return result


def _print_campaign_audience(rows: list, campaign_id: str) -> None:
    """Rich display for campaign × tier audience breakdown."""
    from rich.panel import Panel
    from rich.table import Table
    from rich import box as rich_box

    if not rows:
        console.print("[yellow]No audience data found (campaign may have no participants yet)[/yellow]")
        return

    camp_total = rows[0].get("campaign_total", 0) if rows else 0
    accounted = sum(r.get("in_campaign", 0) for r in rows)

    summary = (
        f"Campaign [bold cyan]{campaign_id}[/bold cyan]\n"
        f"Total unique participants: [bold]{camp_total:,}[/bold]  "
        f"(tier-accounted: {accounted:,})"
    )
    console.print(Panel(summary, title="Campaign Audience by Tier", border_style="cyan"))

    t = Table(box=rich_box.ROUNDED, header_style="bold cyan", show_lines=False)
    t.add_column("Tier Code",       style="dim")
    t.add_column("Tier Name")
    t.add_column("In Campaign",     justify="right", style="cyan")
    t.add_column("Tier Total",      justify="right", style="dim")
    t.add_column("Tier Coverage %", justify="right")  # % of tier reached by campaign
    t.add_column("Audience Share %", justify="right", style="green")  # % of campaign from this tier

    for r in rows:
        cov = r.get("tier_coverage_pct", 0)
        cov_style = "green" if cov >= 20 else ("yellow" if cov >= 5 else "red")
        t.add_row(
            str(r.get("tier_code") or "-"),
            str(r.get("tier_name") or "-"),
            f"{r.get('in_campaign', 0):,}",
            f"{r.get('tier_total', 0):,}",
            f"[{cov_style}]{cov:.1f}%[/{cov_style}]",
            f"{r.get('audience_share_pct', 0):.1f}%",
        )

    console.print(t)
    console.print(
        "[dim]Tier Coverage % = in_campaign / tier_total  |  "
        "Audience Share % = in_campaign / campaign_total[/dim]"
    )


def _get_mcp_campaign_roi(config, period: str, window_days: int) -> list:
    """Compare order behavior of campaign participants vs non-participants."""
    start_date, end_date = _compute_date_range(period)
    start_str = start_date.isoformat() if start_date else end_date.isoformat()
    end_str   = end_date.isoformat()
    if not isinstance(window_days, int) or window_days < 1 or window_days > 60:
        window_days = 30

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    database = config.mcp.database

    with MCPClient(mcp_config) as client:
        client.initialize()

        # Active campaigns in period
        campaigns = client.query(f"""
            SELECT DISTINCT activity_code,
                   BITMAP_COUNT(BITMAP_UNION(activity_custs_bitnum)) AS participants,
                   SUM(activity_Points_Issued)                       AS points_issued,
                   SUM(activity_coupon_issue_qty)                    AS coupons_issued
            FROM ads_das_activity_analysis_d
            WHERE biz_date BETWEEN '{start_str}' AND '{end_str}'
            GROUP BY activity_code
            ORDER BY participants DESC
            LIMIT 20
        """, database=database)

        if not isinstance(campaigns, list) or not campaigns:
            return []

        act_codes = [c.get("activity_code") for c in campaigns if c.get("activity_code")]
        in_clause = ", ".join(f"'{c}'" for c in act_codes)

        # Batch: all campaign orders in one query instead of N+1
        all_orders = client.query(f"""
            SELECT
                a.activity_code,
                COUNT(DISTINCT o.customer_code)  AS buyers,
                COUNT(DISTINCT o.code)           AS orders,
                SUM(o.total_amount) / 100.0      AS gmv_cny
            FROM ads_das_activity_analysis_d a
            JOIN dwd_v_order o
              ON o.customer_code = a.customer_code
             AND o.order_date BETWEEN a.biz_date
                 AND DATE_ADD(a.biz_date, INTERVAL {window_days} DAY)
            WHERE a.activity_code IN ({in_clause})
              AND a.biz_date BETWEEN '{start_str}' AND '{end_str}'
            GROUP BY a.activity_code
        """, database=database)

        orders_map = {}
        if isinstance(all_orders, list):
            for o in all_orders:
                orders_map[o.get("activity_code")] = o

        rows = []
        for camp in campaigns:
            act_code = camp.get("activity_code") or ""
            if not act_code:
                continue
            participants = int(camp.get("participants") or 0)
            po = orders_map.get(act_code, {})
            buyers = int(po.get("buyers") or 0)
            orders = int(po.get("orders") or 0)
            gmv    = float(po.get("gmv_cny") or 0)
            rows.append({
                "activity_code":  act_code,
                "participants":   participants,
                "converted_buyers": buyers,
                "conversion_rate": f"{buyers/participants*100:.1f}%" if participants else "—",
                "attributed_orders": orders,
                "attributed_gmv_cny": gmv,
                "gmv_per_participant": f"¥{gmv/participants:.1f}" if participants else "—",
                "points_issued":  int(camp.get("points_issued") or 0),
                "coupons_issued": int(camp.get("coupons_issued") or 0),
            })

    return sorted(rows, key=lambda x: x["attributed_gmv_cny"], reverse=True)


def _print_campaign_roi(rows: list, period: str, window_days: int) -> None:
    from rich.table import Table
    from rich import box as rich_box

    if not rows:
        console.print("[yellow]No campaign ROI data found[/yellow]")
        return

    tbl = Table(title=f"Campaign Attributed GMV  ({period}, {window_days}d window)",
                box=rich_box.SIMPLE_HEAVY, header_style="bold cyan")
    tbl.add_column("Campaign",       style="dim", max_width=18)
    tbl.add_column("Participants",   justify="right")
    tbl.add_column("Buyers",         justify="right", style="green")
    tbl.add_column("Conv. Rate",     justify="right")
    tbl.add_column("GMV (¥)",        justify="right", style="green")
    tbl.add_column("GMV/Person",     justify="right")
    tbl.add_column("Points Out",     justify="right", style="yellow")
    tbl.add_column("Coupons Out",    justify="right", style="yellow")

    for r in rows:
        tbl.add_row(
            r["activity_code"],
            f"{r['participants']:,}",
            f"{r['converted_buyers']:,}",
            r["conversion_rate"],
            f"{r['attributed_gmv_cny']:,.0f}",
            r["gmv_per_participant"],
            f"{r['points_issued']:,}",
            f"{r['coupons_issued']:,}",
        )
    console.print(tbl)
    total_gmv = sum(r["attributed_gmv_cny"] for r in rows)
    console.print(
        f"[dim]Total attributed GMV: ¥{total_gmv:,.0f}  |  "
        f"Attribution: participant orders within {window_days}d of first activity contact[/dim]"
    )


def _get_mcp_campaign_postmortem(config, campaign_id: str) -> dict:
    """Fetch post-mortem data for a single campaign."""
    safe_id = _sanitize_string_input(campaign_id, 50)
    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    database = config.mcp.database

    with MCPClient(mcp_config) as client:
        client.initialize()

        # Campaign meta + funnel
        meta_rows = client.query(f"""
            SELECT activity_name, start_date, end_date, status,
                   target_count, join_count, finish_count, reward_count
            FROM ads_das_activity_analysis_d
            WHERE activity_code = '{safe_id}'
            ORDER BY start_date DESC
            LIMIT 1
        """, database=database)

        # ROI: participants who ordered within 30d
        roi_rows = client.query(f"""
            SELECT
                COUNT(DISTINCT o.customer_code) AS buyers,
                SUM(o.total_amount)             AS attributed_gmv,
                COUNT(*)                         AS orders
            FROM dwd_v_order o
            WHERE o.delete_flag = 0 AND o.direction = 0
              AND o.customer_code IN (
                  SELECT member_code FROM ads_das_activity_analysis_d
                  WHERE activity_code = '{safe_id}'
              )
        """, database=database)

        # Audience tier breakdown via member lookup
        tier_rows = client.query(f"""
            WITH campaign_members AS (
                SELECT BITMAP_UNION(activity_custs_bitnum) AS bits
                FROM ads_das_activity_analysis_d
                WHERE activity_code = '{safe_id}'
            )
            SELECT t.tier_name,
                   BITMAP_COUNT(BITMAP_AND(c.bits, t.tier_bitmap)) AS members
            FROM dim_member_tier t
            CROSS JOIN campaign_members c
            ORDER BY members DESC
        """, database=database)

        # Daily participation trend
        trend_rows = client.query(f"""
            SELECT biz_date AS day, join_cnt, finish_cnt, reward_cnt
            FROM ads_das_activity_analysis_d
            WHERE activity_code = '{safe_id}'
            ORDER BY biz_date
        """, database=database)

    meta   = meta_rows[0] if isinstance(meta_rows, list) and meta_rows else {}
    roi    = roi_rows[0] if isinstance(roi_rows, list) and roi_rows else {}
    tiers  = tier_rows if isinstance(tier_rows, list) else []
    trend  = trend_rows if isinstance(trend_rows, list) else []

    return {
        "campaign_id": campaign_id,
        "meta":        meta,
        "roi":         roi,
        "tiers":       tiers,
        "trend":       trend,
        "generated":   __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def _build_postmortem_markdown(data: dict) -> str:
    cid   = data["campaign_id"]
    m     = data["meta"]
    roi   = data["roi"]
    tiers = data["tiers"]
    trend = data["trend"]
    gen   = data["generated"]

    name      = m.get("activity_name", cid)
    start     = m.get("start_date", "-")
    end       = m.get("end_date", "-")
    target    = int(m.get("target_count") or 0)
    joined    = int(m.get("join_count") or 0)
    finished  = int(m.get("finish_count") or 0)
    rewarded  = int(m.get("reward_count") or 0)
    join_rate = joined / target * 100 if target else 0
    fin_rate  = finished / joined * 100 if joined else 0

    buyers  = int(roi.get("buyers") or 0)
    gmv_raw = float(roi.get("attributed_gmv") or 0) / 100
    orders  = int(roi.get("orders") or 0)

    lines = [
        f"# Campaign Post-Mortem: {name}",
        f"",
        f"_ID: {cid}_  |  _Period: {start} ~ {end}_  |  _Generated: {gen}_",
        f"",
        f"---",
        f"",
        f"## Participation Funnel",
        f"",
        f"| Stage | Count | Rate |",
        f"| --- | --- | --- |",
        f"| Target Audience | {target:,} | 100% |",
        f"| Joined | {joined:,} | {join_rate:.1f}% |",
        f"| Finished | {finished:,} | {fin_rate:.1f}% of joined |",
        f"| Rewarded | {rewarded:,} | {rewarded/joined*100:.1f}% of joined |" if joined else f"| Rewarded | {rewarded:,} | - |",
        f"",
        f"## Purchase Attribution (30-day window)",
        f"",
        f"| Metric | Value |",
        f"| --- | --- |",
        f"| Attributed Buyers | {buyers:,} |",
        f"| Attributed Orders | {orders:,} |",
        f"| Attributed GMV (¥) | {gmv_raw:,.0f} |",
        f"| Conv Rate (buyers/joined) | {buyers/joined*100:.1f}% |" if joined else f"| Conv Rate | - |",
        f"",
    ]

    if tiers:
        lines += [
            f"## Audience Tier Breakdown",
            f"",
            f"| Tier | Members |",
            f"| --- | --- |",
        ]
        for t in tiers:
            lines.append(f"| {t.get('tier_name', '-')} | {int(t.get('members') or 0):,} |")
        lines.append("")

    if trend:
        lines += [
            f"## Daily Participation Trend",
            f"",
            f"| Date | Joined | Finished | Rewarded |",
            f"| --- | --- | --- | --- |",
        ]
        for r in trend:
            lines.append(
                f"| {r.get('day','-')} | {int(r.get('join_cnt') or 0):,} "
                f"| {int(r.get('finish_cnt') or 0):,} | {int(r.get('reward_cnt') or 0):,} |"
            )
        lines.append("")

    lines += [
        f"---",
        f"",
        f"_Source: SocialHub.AI CLI — Campaign Post-Mortem Report_",
    ]
    return "\n".join(lines)
