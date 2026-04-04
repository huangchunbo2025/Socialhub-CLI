"""Funnel and diagnose analytics functions."""

from rich.console import Console

from ..api.mcp_client import MCPClient
from ..api.mcp_client import MCPConfig as MCPClientConfig
from .common import _compute_date_range
from .overview import _fmt_cny

console = Console()


def _get_mcp_funnel(config, period: str = "30d") -> dict:
    """Customer lifecycle funnel: New -> First Purchase -> Repeat -> Loyal -> At-Risk -> Churned.

    Stages:
      1. New customers in period            (ads_das_business_overview_d.add_custs_num)
      2. First purchase in period           (dwd_v_order, order_count=1 per customer)
      3. Repeat purchasers (2+ orders)      (dwd_v_order)
      4. Loyal (5+ orders ever)             (dwd_v_order, all-time)
      5. At-risk (no order in 60d but had orders 60-120d ago)
      6. Churned (no order in 180d but had orders before)
    """
    start_date, end_date = _compute_date_range(period)
    start_str = start_date.isoformat() if start_date else end_date.isoformat()
    end_str = end_date.isoformat()

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
        api_key=config.mcp.api_key,
    )
    database = config.mcp.database

    from datetime import datetime, timedelta, timezone
    today = datetime.now(timezone.utc).date()
    at_risk_cutoff = (today - timedelta(days=60)).isoformat()
    at_risk_active = (today - timedelta(days=120)).isoformat()
    churned_cutoff = (today - timedelta(days=180)).isoformat()

    with MCPClient(mcp_config) as client:
        client.initialize()

        summary_result = client.query(f"""
            SELECT
                COALESCE((
                    SELECT SUM(add_custs_num)
                    FROM ads_das_business_overview_d
                    WHERE biz_date BETWEEN '{start_str}' AND '{end_str}'
                ), 0) AS new_customers,
                COALESCE((
                    SELECT COUNT(*)
                    FROM dim_customer_info
                ), 0) AS total_customers
        """, database=database)
        new_customers = total_customers = 0
        if isinstance(summary_result, list) and summary_result:
            summary_row = summary_result[0]
            new_customers = summary_row.get("new_customers") or 0
            total_customers = summary_row.get("total_customers") or 0

        lifecycle_result = client.query(f"""
            SELECT
                COUNT(CASE WHEN in_period_orders = 1 THEN 1 END) AS first_time_buyers,
                COUNT(CASE WHEN in_period_orders >= 2 THEN 1 END) AS repeat_buyers,
                COUNT(CASE WHEN total_orders >= 5 THEN 1 END) AS loyal_customers,
                COUNT(CASE
                    WHEN last_order_date BETWEEN '{at_risk_active}' AND '{at_risk_cutoff}' THEN 1
                END) AS at_risk,
                COUNT(CASE WHEN last_order_date < '{churned_cutoff}' THEN 1 END) AS churned
            FROM (
                SELECT
                    customer_code,
                    COUNT(*) AS total_orders,
                    SUM(CASE
                        WHEN order_date BETWEEN '{start_str}' AND '{end_str}' THEN 1
                        ELSE 0
                    END) AS in_period_orders,
                    MAX(order_date) AS last_order_date
                FROM dwd_v_order
                GROUP BY customer_code
            ) t
        """, database=database)
        first_time_buyers = repeat_buyers = loyal_customers = at_risk = churned = 0
        if isinstance(lifecycle_result, list) and lifecycle_result:
            row = lifecycle_result[0]
            first_time_buyers = row.get("first_time_buyers") or 0
            repeat_buyers = row.get("repeat_buyers") or 0
            loyal_customers = row.get("loyal_customers") or 0
            at_risk = row.get("at_risk") or 0
            churned = row.get("churned") or 0

    return {
        "period": period,
        "total_customers": total_customers,
        "new_customers": int(new_customers),
        "first_time_buyers": int(first_time_buyers),
        "repeat_buyers": int(repeat_buyers),
        "loyal_customers": int(loyal_customers),
        "at_risk": int(at_risk),
        "churned": int(churned),
    }


def _print_funnel(data: dict) -> None:
    """Rich display of the customer lifecycle funnel."""
    from rich import box
    from rich.panel import Panel
    from rich.table import Table

    period = data["period"]
    total = data["total_customers"]

    def _pct(n, base):
        if not base:
            return "—"
        return f"{n / base * 100:.1f}%"

    stages = [
        ("New Customers",      data["new_customers"],     "🆕", "cyan"),
        ("First Purchase",     data["first_time_buyers"], "🛍", "green"),
        ("Repeat Buyers (2+)", data["repeat_buyers"],     "🔁", "green"),
        ("Loyal (5+ orders)",  data["loyal_customers"],   "⭐", "yellow"),
        ("At-Risk (60d)",      data["at_risk"],           "⚠ ", "orange3"),
        ("Churned (180d)",     data["churned"],           "❌", "red"),
    ]

    tbl = Table(
        title=f"Customer Lifecycle Funnel  ({period})",
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold cyan",
    )
    tbl.add_column("Stage", style="bold")
    tbl.add_column("Count", justify="right")
    tbl.add_column("% of Total", justify="right")
    tbl.add_column("Conv. from prev.", justify="right")

    prev_count = None
    for label, count, icon, color in stages:
        pct_total = _pct(count, total)
        conv = _pct(count, prev_count) if prev_count is not None else "—"
        tbl.add_row(
            f"[{color}]{icon} {label}[/{color}]",
            f"[{color}]{count:,}[/{color}]",
            pct_total,
            conv,
        )
        prev_count = count

    console.print(tbl)
    console.print(
        Panel(
            f"Total registered customers: [bold]{total:,}[/bold]\n"
            f"Repeat/Loyal: [green]{data['repeat_buyers']:,}[/green]  |  "
            f"At-Risk: [orange3]{data['at_risk']:,}[/orange3]  |  "
            f"Churned: [red]{data['churned']:,}[/red]",
            title="Summary",
            border_style="dim",
        )
    )


def _get_mcp_diagnose_context(config) -> dict:
    """Gather key metrics from multiple tables for AI diagnosis."""
    from datetime import datetime, timedelta, timezone

    today = datetime.now(timezone.utc).date()
    start_30d = (today - timedelta(days=30)).isoformat()
    end_str = today.isoformat()
    start_7d = (today - timedelta(days=7)).isoformat()

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
        api_key=config.mcp.api_key,
    )
    database = config.mcp.database

    result = {}

    with MCPClient(mcp_config) as client:
        client.initialize()

        # 1+2. Business overview: 30d and 7d in one pass with CASE WHEN
        ov_combined = client.query(f"""
            SELECT
                SUM(add_custs_num)                                         AS new_custs_30d,
                SUM(total_order_num)                                       AS orders_30d,
                SUM(total_transaction_amt)                                 AS revenue_30d,
                SUM(CASE WHEN biz_date >= '{start_7d}' THEN add_custs_num     ELSE 0 END) AS new_custs_7d,
                SUM(CASE WHEN biz_date >= '{start_7d}' THEN total_order_num   ELSE 0 END) AS orders_7d,
                SUM(CASE WHEN biz_date >= '{start_7d}' THEN total_transaction_amt ELSE 0 END) AS revenue_7d
            FROM ads_das_business_overview_d
            WHERE biz_date BETWEEN '{start_30d}' AND '{end_str}'
        """, database=database)
        row_ov = ov_combined[0] if isinstance(ov_combined, list) and ov_combined else {}
        result["overview_30d"] = {
            "new_custs": row_ov.get("new_custs_30d"),
            "orders": row_ov.get("orders_30d"),
            "revenue_fen": row_ov.get("revenue_30d"),
        }
        result["overview_7d"] = {
            "new_custs": row_ov.get("new_custs_7d"),
            "orders": row_ov.get("orders_7d"),
            "revenue_fen": row_ov.get("revenue_7d"),
        }

        # 3. At-risk customers (no order in 60 days)
        at_risk_cutoff = (today - timedelta(days=60)).isoformat()
        at_risk_active = (today - timedelta(days=120)).isoformat()
        ar = client.query(f"""
            SELECT COUNT(DISTINCT customer_code) AS at_risk
            FROM dwd_v_order
            WHERE order_date BETWEEN '{at_risk_active}' AND '{at_risk_cutoff}'
              AND customer_code NOT IN (
                  SELECT DISTINCT customer_code FROM dwd_v_order
                  WHERE order_date > '{at_risk_cutoff}'
              )
        """, database=database)
        result["at_risk_customers"] = ar[0].get("at_risk", 0) if isinstance(ar, list) and ar else 0

        # 4. Repeat purchase rate last 30d
        rpr = client.query(f"""
            SELECT
                COUNT(DISTINCT customer_code) AS active,
                COUNT(DISTINCT CASE WHEN order_cnt > 1 THEN customer_code END) AS repeat_custs
            FROM (
                SELECT customer_code, COUNT(*) AS order_cnt
                FROM dwd_v_order
                WHERE order_date BETWEEN '{start_30d}' AND '{end_str}'
                GROUP BY customer_code
            ) t
        """, database=database)
        result["repurchase_30d"] = rpr[0] if isinstance(rpr, list) and rpr else {}

        # 5. Top 3 channels by revenue last 30d
        ch = client.query(f"""
            SELECT
                COALESCE(source_name, 'unknown') AS channel,
                COUNT(*) AS orders,
                SUM(total_amount) AS revenue_fen
            FROM dwd_v_order
            WHERE order_date BETWEEN '{start_30d}' AND '{end_str}'
            GROUP BY source_name
            ORDER BY revenue_fen DESC
            LIMIT 3
        """, database=database)
        result["top_channels"] = ch if isinstance(ch, list) else []

        # 6. Active campaigns last 30d
        camp = client.query(f"""
            SELECT COUNT(*) AS active_campaigns,
                   SUM(target_custs_num) AS total_targeted
            FROM ads_das_activity_analysis_d
            WHERE biz_date BETWEEN '{start_30d}' AND '{end_str}'
        """, database=database)
        result["campaigns_30d"] = camp[0] if isinstance(camp, list) and camp else {}

        # 7. Points liability (approximate)
        pts = client.query("""
            SELECT SUM(available_points + in_transit_points) AS total_points
            FROM vdm_t_points_account
            WHERE delete_flag = 0
        """, database="dts_demoen")
        total_points = pts[0].get("total_points", 0) if isinstance(pts, list) and pts else 0
        result["points_liability_cny"] = round(float(total_points or 0) * 0.01, 0)

    return result


def _build_diagnose_prompt(ctx: dict) -> str:
    """Format gathered metrics into a structured AI prompt."""
    def _n(v) -> str:
        """Safely format an integer value with comma separators."""
        try:
            return f"{int(v or 0):,}"
        except (TypeError, ValueError):
            return "N/A"

    ov30 = ctx.get("overview_30d", {})
    ov7 = ctx.get("overview_7d", {})
    rpr = ctx.get("repurchase_30d", {})
    channels = ctx.get("top_channels", [])
    camp = ctx.get("campaigns_30d", {})

    repeat_rate = "N/A"
    active = rpr.get("active", 0) or 0
    repeat_c = rpr.get("repeat_custs", 0) or 0
    if active > 0:
        repeat_rate = f"{repeat_c / active * 100:.1f}%"

    channel_txt = "\n".join(
        f"  - {r.get('channel')}: {_n(r.get('orders'))} orders, "
        f"{_fmt_cny(r.get('revenue_fen'))} revenue"
        for r in channels
    ) or "  N/A"

    prompt = f"""You are a CDP business analyst for SocialHub.AI. Analyze the following 30-day metrics and provide a concise health diagnosis (3-5 bullets) with actionable recommendations.

## Key Metrics (Last 30 Days)
- New customers: {_n(ov30.get("new_custs"))}
- Total orders: {_n(ov30.get("orders"))}
- Revenue: {_fmt_cny(ov30.get("revenue_fen"))}
- Repeat purchase rate: {repeat_rate}
- At-risk customers (60d inactive): {_n(ctx.get("at_risk_customers"))}
- Points liability: {_fmt_cny(ctx.get("points_liability_cny", 0) * 100)}

## Last 7 Days Trend
- New customers: {_n(ov7.get("new_custs"))}
- Orders: {_n(ov7.get("orders"))}
- Revenue: {_fmt_cny(ov7.get("revenue_fen"))}

## Channels (Top 3 by Revenue)
{channel_txt}

## Marketing
- Active campaigns: {_n(camp.get("active_campaigns"))}
- Total targeted customers: {_n(camp.get("total_targeted"))}

Based on these metrics, provide:
1. Overall business health assessment (Healthy / Warning / Critical)
2. Top 3 issues or opportunities
3. Specific recommended actions for the data/marketing team
Keep the response concise and actionable."""
    return prompt
