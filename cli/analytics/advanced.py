"""Advanced analytics functions: LTV, repurchase, anomaly, canvas, recommend, RFM."""

from typing import Optional

from rich.console import Console

from ..api.mcp_client import MCPClient, MCPConfig as MCPClientConfig, MCPError
from ..output.export import format_output
from .common import (
    _compute_date_range,
    _safe_date_filter,
)
from .campaigns import _sanitize_string_input

console = Console()

_ANOMALY_METRICS = {
    "gmv":        ("GMV (¥)",       "gmv",              True),   # (label, field, fen->cny)
    "orders":     ("Orders",        "order_cnt",        False),
    "aov":        ("AOV (¥)",       "aov",              True),
    "new_buyers": ("New Buyers",    "new_buyer_cnt",    False),
}


def _get_mcp_ltv(config, cohort_months: int, follow_months: int) -> list:
    """Compute cohort LTV: group customers by first-order month, show cumulative GMV.

    Args:
        cohort_months: how many past months of cohorts to show (3-24)
        follow_months: how many months to track each cohort (1-12)
    """
    from datetime import datetime, timedelta

    if not isinstance(cohort_months, int) or cohort_months < 1 or cohort_months > 24:
        cohort_months = 6
    if not isinstance(follow_months, int) or follow_months < 1 or follow_months > 12:
        follow_months = 3

    today = datetime.now().date()
    # Earliest cohort start
    earliest = (today.replace(day=1) - timedelta(days=cohort_months * 31)).replace(day=1)
    earliest_str = earliest.isoformat()

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    database = config.mcp.database

    with MCPClient(mcp_config) as client:
        client.initialize()

        # Step 1: first-order month per customer (cohort assignment)
        # Step 2: for each cohort-month × follow-month, sum GMV
        rows = client.query(f"""
            SELECT
                DATE_FORMAT(first_order.first_date, '%Y-%m') AS cohort_month,
                COUNT(DISTINCT first_order.customer_code)    AS cohort_size,
                FLOOR(DATEDIFF(o.order_date, first_order.first_date) / 30) AS month_offset,
                SUM(o.total_amount) / 100.0                  AS gmv_cny,
                COUNT(DISTINCT o.customer_code)              AS buyers
            FROM (
                SELECT customer_code, MIN(order_date) AS first_date
                FROM dwd_v_order
                WHERE order_date >= '{earliest_str}'
                GROUP BY customer_code
            ) first_order
            JOIN dwd_v_order o
              ON o.customer_code = first_order.customer_code
             AND FLOOR(DATEDIFF(o.order_date, first_order.first_date) / 30)
                 BETWEEN 0 AND {follow_months - 1}
            WHERE first_order.first_date >= '{earliest_str}'
            GROUP BY cohort_month, month_offset
            ORDER BY cohort_month, month_offset
        """, database=database)

    return rows if isinstance(rows, list) else []


def _print_ltv(rows: list, cohort_months: int, follow_months: int) -> None:
    from rich.table import Table
    from rich import box as rich_box

    if not rows:
        console.print("[yellow]No LTV data found[/yellow]")
        return

    # Pivot: cohort_month → {month_offset: gmv}
    from collections import defaultdict
    cohort_data: dict = defaultdict(lambda: {"size": 0, "gmv": {}})
    for r in rows:
        cm = str(r.get("cohort_month") or "—")
        offset = int(r.get("month_offset") or 0)
        gmv = float(r.get("gmv_cny") or 0)
        size = int(r.get("cohort_size") or 0)
        cohort_data[cm]["size"] = size
        cohort_data[cm]["gmv"][offset] = gmv

    tbl = Table(
        title=f"Cohort LTV  (last {cohort_months} cohorts, {follow_months}-month window)",
        box=rich_box.SIMPLE_HEAVY, header_style="bold cyan",
    )
    tbl.add_column("Cohort",       style="bold")
    tbl.add_column("Size",         justify="right", style="dim")
    # Month columns
    for m in range(follow_months):
        label = "M0 (首月)" if m == 0 else f"M{m}"
        tbl.add_column(label, justify="right")
    tbl.add_column("Cumul. LTV",   justify="right", style="green")

    for cohort, info in sorted(cohort_data.items()):
        size = info["size"]
        gmv_map = info["gmv"]
        cumul = sum(gmv_map.values())
        ltv_per = cumul / size if size else 0

        cols = [cohort, f"{size:,}"]
        for m in range(follow_months):
            g = gmv_map.get(m, 0)
            per = g / size if size else 0
            cols.append(f"¥{per:,.1f}" if g else "—")
        cols.append(f"[green]¥{ltv_per:,.1f}[/green]")
        tbl.add_row(*cols)

    console.print(tbl)
    console.print(
        f"[dim]LTV per customer = cumulative GMV within {follow_months} months ÷ cohort size. "
        f"M0 = first-order month.[/dim]"
    )


def _get_mcp_repurchase(config, period: str) -> dict:
    """Repurchase rate, days-to-rebuy distribution, GMV contribution.

    Single MCP session: all queries run against dwd_v_order (das_demoen).
    Also attempts ads_das_v_repurchase_analysis_d for pre-aggregated context.
    """
    start_date, end_date = _compute_date_range(period)
    start_str = start_date.isoformat() if start_date else "2000-01-01"
    end_str   = end_date.isoformat()

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    database = config.mcp.database

    with MCPClient(mcp_config) as client:
        client.initialize()

        # Core: repurchase rate + timing distribution in one CTE pass
        rate_rows = client.query(f"""
            WITH order_seq AS (
                SELECT customer_code, order_date, total_amount,
                       ROW_NUMBER() OVER (PARTITION BY customer_code ORDER BY order_date) AS rn
                FROM dwd_v_order
                WHERE delete_flag = 0 AND direction = 0
                  AND order_date BETWEEN '{start_str}' AND '{end_str}'
            ),
            first_second AS (
                SELECT
                    customer_code,
                    MIN(CASE WHEN rn = 1 THEN order_date END)    AS first_date,
                    MIN(CASE WHEN rn = 2 THEN order_date END)    AS second_date,
                    SUM(CASE WHEN rn >= 2 THEN total_amount ELSE 0 END) AS repeat_amount,
                    SUM(total_amount)                             AS total_amount_all
                FROM order_seq
                GROUP BY customer_code
            )
            SELECT
                COUNT(*)                                                          AS total_buyers,
                SUM(CASE WHEN second_date IS NOT NULL THEN 1 ELSE 0 END)         AS repeat_buyers,
                SUM(repeat_amount)                                                AS repeat_gmv_fen,
                SUM(total_amount_all)                                             AS total_gmv_fen,
                AVG(CASE WHEN second_date IS NOT NULL
                    THEN DATEDIFF(second_date, first_date) END)                   AS avg_days_to_rebuy,
                SUM(CASE WHEN second_date IS NOT NULL
                     AND DATEDIFF(second_date, first_date) <= 7   THEN 1 ELSE 0 END) AS bucket_7d,
                SUM(CASE WHEN second_date IS NOT NULL
                     AND DATEDIFF(second_date, first_date) BETWEEN 8  AND 30 THEN 1 ELSE 0 END) AS bucket_30d,
                SUM(CASE WHEN second_date IS NOT NULL
                     AND DATEDIFF(second_date, first_date) BETWEEN 31 AND 60 THEN 1 ELSE 0 END) AS bucket_60d,
                SUM(CASE WHEN second_date IS NOT NULL
                     AND DATEDIFF(second_date, first_date) BETWEEN 61 AND 90 THEN 1 ELSE 0 END) AS bucket_90d,
                SUM(CASE WHEN second_date IS NOT NULL
                     AND DATEDIFF(second_date, first_date) > 90   THEN 1 ELSE 0 END) AS bucket_90plus
            FROM first_second
        """, database=database)

        # Monthly repurchase trend
        trend_rows = client.query(f"""
            SELECT
                DATE_FORMAT(order_date, '%Y-%m')          AS month,
                COUNT(DISTINCT customer_code)             AS buyers,
                COUNT(DISTINCT CASE WHEN rn >= 2 THEN customer_code END) AS repeaters
            FROM (
                SELECT customer_code, order_date,
                       ROW_NUMBER() OVER (PARTITION BY customer_code ORDER BY order_date) AS rn
                FROM dwd_v_order
                WHERE delete_flag = 0 AND direction = 0
                  AND order_date BETWEEN '{start_str}' AND '{end_str}'
            ) t
            GROUP BY month
            ORDER BY month
        """, database=database)

        # Optional: ADS pre-aggregated table
        ads_row = None
        try:
            ads_rows = client.query(f"""
                SELECT *
                FROM ads_das_v_repurchase_analysis_d
                WHERE biz_date BETWEEN '{start_str}' AND '{end_str}'
                ORDER BY biz_date DESC
                LIMIT 1
            """, database=database)
            if isinstance(ads_rows, list) and ads_rows:
                ads_row = ads_rows[0]
        except Exception:
            pass

    # Parse core metrics
    r = rate_rows[0] if isinstance(rate_rows, list) and rate_rows else {}
    total   = int(r.get("total_buyers") or 0)
    repeats = int(r.get("repeat_buyers") or 0)
    rep_gmv = float(r.get("repeat_gmv_fen") or 0) / 100
    tot_gmv = float(r.get("total_gmv_fen") or 0) / 100
    avg_raw = r.get("avg_days_to_rebuy")
    avg_days = round(float(avg_raw), 1) if avg_raw else None

    b7   = int(r.get("bucket_7d") or 0)
    b30  = int(r.get("bucket_30d") or 0)
    b60  = int(r.get("bucket_60d") or 0)
    b90  = int(r.get("bucket_90d") or 0)
    b90p = int(r.get("bucket_90plus") or 0)

    timing = [
        {"bucket": "<=7天  (冲动复购)",   "count": b7,   "pct": f"{b7/repeats*100:.1f}%"   if repeats else "—"},
        {"bucket": "8-30天 (习惯触发)",   "count": b30,  "pct": f"{b30/repeats*100:.1f}%"  if repeats else "—"},
        {"bucket": "31-60天 (需求驱动)",  "count": b60,  "pct": f"{b60/repeats*100:.1f}%"  if repeats else "—"},
        {"bucket": "61-90天 (长周期)",    "count": b90,  "pct": f"{b90/repeats*100:.1f}%"  if repeats else "—"},
        {"bucket": ">90天  (低频/唤回)",  "count": b90p, "pct": f"{b90p/repeats*100:.1f}%" if repeats else "—"},
    ]

    trend = []
    if isinstance(trend_rows, list):
        for row in trend_rows:
            buyers = int(row.get("buyers") or 0)
            reps   = int(row.get("repeaters") or 0)
            trend.append({
                "month":     row.get("month", "—"),
                "buyers":    buyers,
                "repeaters": reps,
                "rate":      f"{reps/buyers*100:.1f}%" if buyers else "—",
            })

    return {
        "period":            period,
        "total_buyers":      total,
        "repeat_buyers":     repeats,
        "repurchase_rate":   f"{repeats/total*100:.1f}%" if total else "—",
        "repeat_gmv_cny":    rep_gmv,
        "total_gmv_cny":     tot_gmv,
        "repeat_gmv_share":  f"{rep_gmv/tot_gmv*100:.1f}%" if tot_gmv else "—",
        "avg_days_to_rebuy": avg_days,
        "timing_distribution": timing,
        "monthly_trend":     trend,
        "ads_snapshot":      ads_row,
    }


def _print_repurchase(data: dict) -> None:
    from rich.table import Table
    from rich import box as rich_box
    from rich.panel import Panel

    period    = data["period"]
    rate      = data["repurchase_rate"]
    repeats   = data["repeat_buyers"]
    total     = data["total_buyers"]
    rep_gmv   = data["repeat_gmv_cny"]
    tot_gmv   = data["total_gmv_cny"]
    gmv_share = data["repeat_gmv_share"]
    avg_days  = data["avg_days_to_rebuy"]

    try:
        rate_f = float(rate.rstrip("%"))
        rate_color = "green" if rate_f >= 40 else ("yellow" if rate_f >= 20 else "red")
    except Exception:
        rate_color = "white"

    avg_str = f"{avg_days} 天" if avg_days is not None else "—"
    console.print(Panel(
        f"复购买家:     [{rate_color}][bold]{repeats:,}[/bold][/{rate_color}]"
        f"  /  {total:,} 总买家\n"
        f"复购率:       [{rate_color}][bold]{rate}[/bold][/{rate_color}]\n"
        f"复购GMV:      [green]¥{rep_gmv:,.0f}[/green]"
        f"  占总GMV {gmv_share}  (总GMV ¥{tot_gmv:,.0f})\n"
        f"平均复购间隔: [cyan]{avg_str}[/cyan]",
        title=f"[bold cyan]复购分析  ({period})[/bold cyan]",
        border_style="cyan",
    ))

    # Timing distribution
    timing = data.get("timing_distribution", [])
    if timing:
        max_count = max(t["count"] for t in timing) or 1
        tbl = Table(title="复购时间分布（首单→复购）",
                    box=rich_box.SIMPLE_HEAVY, header_style="bold cyan")
        tbl.add_column("时间段",   min_width=20)
        tbl.add_column("买家数",   justify="right", style="green")
        tbl.add_column("占比",     justify="right")
        tbl.add_column("分布",     no_wrap=True)
        for t in timing:
            bar_len = int(t["count"] / max_count * 25) if max_count else 0
            tbl.add_row(
                t["bucket"],
                f"{t['count']:,}",
                t["pct"],
                "[green]" + "█" * bar_len + "[/green]",
            )
        console.print(tbl)

    # Monthly trend
    trend = data.get("monthly_trend", [])
    if trend:
        tbl2 = Table(title="月度复购趋势", box=rich_box.SIMPLE, header_style="bold cyan")
        tbl2.add_column("月份",     style="dim")
        tbl2.add_column("买家数",   justify="right")
        tbl2.add_column("复购买家", justify="right", style="green")
        tbl2.add_column("复购率",   justify="right")
        for row in trend:
            try:
                rf = float(row["rate"].rstrip("%"))
                col = "green" if rf >= 40 else ("yellow" if rf >= 20 else "red")
            except Exception:
                col = "white"
            tbl2.add_row(
                row["month"],
                f"{row['buyers']:,}",
                f"{row['repeaters']:,}",
                f"[{col}]{row['rate']}[/{col}]",
            )
        console.print(tbl2)

    # ADS snapshot if available
    ads = data.get("ads_snapshot")
    if ads:
        console.print("\n[dim]ADS 预聚合快照 (ads_das_v_repurchase_analysis_d):[/dim]")
        for k, v in ads.items():
            console.print(f"  [dim]{k}[/dim]: {v}")

    console.print(
        "[dim]数据来源: dwd_v_order. "
        "复购率 = 期内下≥2单买家 / 期内总买家.[/dim]"
    )


def _get_mcp_repurchase_path(config, period: str, limit: int) -> dict:
    """First-order to second-order product category transition analysis.

    Two queries in one MCP session (dts_demoen):
      1. Top category transition pairs (1st order cat -> 2nd order cat)
      2. Per first-category: repurchase rate + same-category loyalty rate
    """
    start_date, end_date = _compute_date_range(period)
    start_str = start_date.isoformat() if start_date else "2000-01-01"
    end_str   = end_date.isoformat()
    if not isinstance(limit, int) or limit < 1 or limit > 100:
        limit = 20

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )

    with MCPClient(mcp_config) as client:
        client.initialize()

        # Category transition pairs
        pairs = client.query(f"""
            WITH order_cat AS (
                SELECT
                    o.customer_code,
                    o.order_date,
                    ROW_NUMBER() OVER (PARTITION BY o.customer_code ORDER BY o.order_date) AS rn,
                    COALESCE(p.category_name, od.product_name, '未分类') AS category
                FROM vdm_t_order o
                JOIN vdm_t_order_detail od
                  ON od.order_code = o.code AND od.delete_flag = 0
                LEFT JOIN vdm_t_product p
                  ON p.code = od.product_code AND p.delete_flag = 0
                WHERE o.delete_flag = 0 AND o.direction = 0
                  AND o.order_date BETWEEN '{start_str}' AND '{end_str}'
            )
            SELECT
                o1.category                      AS first_category,
                o2.category                      AS second_category,
                COUNT(DISTINCT o1.customer_code) AS customers,
                ROUND(AVG(DATEDIFF(o2.order_date, o1.order_date)), 1) AS avg_days
            FROM order_cat o1
            JOIN order_cat o2
              ON o2.customer_code = o1.customer_code
             AND o1.rn = 1 AND o2.rn = 2
            GROUP BY first_category, second_category
            ORDER BY customers DESC
            LIMIT {limit}
        """, database="dts_demoen")

        # Per first-category repurchase + same-category loyalty
        by_cat = client.query(f"""
            WITH order_cat AS (
                SELECT
                    o.customer_code,
                    o.order_date,
                    ROW_NUMBER() OVER (PARTITION BY o.customer_code ORDER BY o.order_date) AS rn,
                    COALESCE(p.category_name, od.product_name, '未分类') AS category
                FROM vdm_t_order o
                JOIN vdm_t_order_detail od
                  ON od.order_code = o.code AND od.delete_flag = 0
                LEFT JOIN vdm_t_product p
                  ON p.code = od.product_code AND p.delete_flag = 0
                WHERE o.delete_flag = 0 AND o.direction = 0
                  AND o.order_date BETWEEN '{start_str}' AND '{end_str}'
            )
            SELECT
                o1.category                      AS category,
                COUNT(DISTINCT o1.customer_code) AS first_buyers,
                COUNT(DISTINCT CASE WHEN o2.customer_code IS NOT NULL
                      THEN o1.customer_code END) AS repeat_buyers,
                COUNT(DISTINCT CASE WHEN o2.category = o1.category
                      THEN o1.customer_code END) AS same_cat_repeat
            FROM order_cat o1
            LEFT JOIN order_cat o2
              ON o2.customer_code = o1.customer_code AND o1.rn = 1 AND o2.rn = 2
            WHERE o1.rn = 1
            GROUP BY o1.category
            ORDER BY first_buyers DESC
            LIMIT {limit}
        """, database="dts_demoen")

    return {
        "period": period,
        "pairs":             pairs  if isinstance(pairs, list)  else [],
        "by_first_category": by_cat if isinstance(by_cat, list) else [],
    }


def _print_repurchase_path(data: dict) -> None:
    from rich.table import Table
    from rich import box as rich_box

    period = data["period"]
    pairs  = data.get("pairs", [])
    by_cat = data.get("by_first_category", [])

    # Category pairs matrix
    if pairs:
        tbl = Table(
            title=f"首单->复购品类转化矩阵  ({period})",
            box=rich_box.ROUNDED, header_style="bold cyan",
        )
        tbl.add_column("#",           style="dim", width=4)
        tbl.add_column("首单品类",    max_width=20)
        tbl.add_column("复购品类",    max_width=20, style="green")
        tbl.add_column("客户数",      justify="right", style="cyan")
        tbl.add_column("均间隔(天)",  justify="right")
        tbl.add_column("路径",        style="dim")
        for i, r in enumerate(pairs, 1):
            first  = str(r.get("first_category")  or "—")
            second = str(r.get("second_category") or "—")
            path_type = "[green]♻ 同品类[/green]" if first == second else "→ 跨品类"
            tbl.add_row(
                str(i), first, second,
                f"{int(r.get('customers') or 0):,}",
                str(r.get("avg_days") or "—"),
                path_type,
            )
        console.print(tbl)
        console.print(
            "[dim]同品类路径说明客户对该品类有强需求；"
            "跨品类路径是拓品机会。[/dim]\n"
        )

    # Per first-category repurchase stats
    if by_cat:
        tbl2 = Table(
            title=f"首单品类复购率  ({period})",
            box=rich_box.SIMPLE_HEAVY, header_style="bold cyan",
        )
        tbl2.add_column("首单品类",   max_width=22)
        tbl2.add_column("首购买家",   justify="right")
        tbl2.add_column("复购买家",   justify="right", style="green")
        tbl2.add_column("复购率",     justify="right")
        tbl2.add_column("同品类复购", justify="right")
        tbl2.add_column("品类留存率", justify="right", style="cyan")
        for r in by_cat:
            fb  = int(r.get("first_buyers") or 0)
            rb  = int(r.get("repeat_buyers") or 0)
            sb  = int(r.get("same_cat_repeat") or 0)
            rr  = f"{rb/fb*100:.1f}%" if fb else "—"
            sr  = f"{sb/rb*100:.1f}%" if rb else "—"
            try:
                rc = "green" if float(rr.rstrip("%")) >= 40 else (
                     "yellow" if float(rr.rstrip("%")) >= 20 else "red")
            except Exception:
                rc = "white"
            tbl2.add_row(
                str(r.get("category") or "—"),
                f"{fb:,}", f"{rb:,}",
                f"[{rc}]{rr}[/{rc}]",
                f"{sb:,}", sr,
            )
        console.print(tbl2)

    console.print(
        "[dim]品类留存率 = 复购时仍购同品类 / 总复购买家. "
        "数据来源: vdm_t_order + vdm_t_order_detail + vdm_t_product (dts_demoen).[/dim]"
    )


def _get_mcp_anomaly(config, metric: str, lookback: int, detect_days: int) -> dict:
    """Fetch daily metric history and run mean±2σ anomaly detection.

    Primary: dws_order_base_metrics_d (DWS, pre-aggregated, fast).
    Fallback: dwd_v_order (DWD, computed on the fly).

    Args:
        metric:       one of gmv / orders / aov / new_buyers
        lookback:     days of history used to compute baseline (default 30)
        detect_days:  how many recent days to flag as anomalies (default 7)
    """
    from datetime import datetime, timedelta

    metric_info = _ANOMALY_METRICS.get(metric)
    if metric_info is None:
        raise ValueError(
            f"Unknown metric '{metric}'. "
            f"Valid: {', '.join(_ANOMALY_METRICS.keys())}"
        )
    label, field, is_fen = metric_info

    today      = datetime.now().date()
    start_base = (today - timedelta(days=lookback + detect_days)).isoformat()
    end_base   = (today - timedelta(days=detect_days + 1)).isoformat()
    start_det  = (today - timedelta(days=detect_days)).isoformat()
    end_det    = today.isoformat()

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    database = config.mcp.database

    with MCPClient(mcp_config) as client:
        client.initialize()

        # Try DWS layer first
        dws_ok = False
        history_rows = []
        try:
            rows = client.query(f"""
                SELECT biz_date AS day, {field} AS value
                FROM dws_order_base_metrics_d
                WHERE biz_date BETWEEN '{start_base}' AND '{end_det}'
                ORDER BY day
            """, database=database)
            if isinstance(rows, list) and rows:
                history_rows = rows
                dws_ok = True
        except Exception:
            pass

        # Fallback: compute from dwd_v_order
        if not dws_ok:
            if metric == "gmv":
                expr = "SUM(total_amount)"
            elif metric == "orders":
                expr = "COUNT(*)"
            elif metric == "aov":
                expr = "AVG(total_amount)"
            elif metric == "new_buyers":
                # Approximate: first-ever order per customer on that day
                expr = "COUNT(DISTINCT customer_code)"

            rows = client.query(f"""
                SELECT order_date AS day, {expr} AS value
                FROM dwd_v_order
                WHERE delete_flag = 0 AND direction = 0
                  AND order_date BETWEEN '{start_base}' AND '{end_det}'
                GROUP BY order_date
                ORDER BY day
            """, database=database)
            if isinstance(rows, list):
                history_rows = rows

    if not history_rows:
        return {"metric": metric, "label": label, "error": "No data returned"}

    # Split into baseline vs detection window
    baseline = [r for r in history_rows if str(r.get("day", "")) <= end_base]
    detection = [r for r in history_rows if str(r.get("day", "")) >= start_det]

    def _v(r):
        raw = r.get("value") or 0
        return float(raw) / 100 if is_fen else float(raw)

    base_vals = [_v(r) for r in baseline]
    if not base_vals:
        return {"metric": metric, "label": label, "error": "Insufficient baseline data"}

    mean = sum(base_vals) / len(base_vals)
    variance = sum((x - mean) ** 2 for x in base_vals) / len(base_vals)
    std = variance ** 0.5
    upper = mean + 2 * std
    lower = max(0.0, mean - 2 * std)

    flagged = []
    for r in detection:
        v = _v(r)
        day = str(r.get("day", ""))
        delta_pct = (v - mean) / mean * 100 if mean else 0
        status = "normal"
        if v > upper:
            status = "high"
        elif v < lower:
            status = "low"
        flagged.append({
            "day": day,
            "value": v,
            "delta_pct": delta_pct,
            "status": status,
        })

    return {
        "metric":      metric,
        "label":       label,
        "is_fen":      is_fen,
        "dws_used":    dws_ok,
        "baseline_days": len(base_vals),
        "mean":        mean,
        "std":         std,
        "upper_2sigma": upper,
        "lower_2sigma": lower,
        "detection":   flagged,
        "anomaly_count": sum(1 for f in flagged if f["status"] != "normal"),
    }


def _print_anomaly(data: dict) -> None:
    from rich.table import Table
    from rich import box as rich_box
    from rich.panel import Panel

    if "error" in data:
        console.print(f"[red]Error: {data['error']}[/red]")
        return

    label    = data["label"]
    mean     = data["mean"]
    std      = data["std"]
    upper    = data["upper_2sigma"]
    lower    = data["lower_2sigma"]
    flagged  = data["detection"]
    is_fen   = data.get("is_fen", False)
    n_anom   = data["anomaly_count"]

    fmt = lambda v: f"¥{v:,.0f}" if is_fen else f"{v:,.1f}"

    status_color = "green" if n_anom == 0 else ("yellow" if n_anom <= 2 else "red")
    summary = (
        f"Metric:   [bold]{label}[/bold]\n"
        f"Baseline: mean={fmt(mean)}  std={fmt(std)}\n"
        f"Band:     [{fmt(lower)}, {fmt(upper)}]  (mean +/- 2sigma)\n"
        f"Anomalies: [{status_color}]{n_anom} day(s) flagged[/{status_color}]  "
        f"({'[green]All normal[/green]' if n_anom == 0 else '[red]Action may be needed[/red]'})"
    )
    console.print(Panel(summary, title="[bold cyan]Anomaly Detection[/bold cyan]", border_style="cyan"))

    if not flagged:
        return

    tbl = Table(
        title=f"Detection Window  ({len(flagged)} days)",
        box=rich_box.SIMPLE_HEAVY, header_style="bold cyan",
    )
    tbl.add_column("Date",    style="dim")
    tbl.add_column("Value",   justify="right")
    tbl.add_column("vs Mean", justify="right")
    tbl.add_column("Status",  justify="center")
    tbl.add_column("Bar",     no_wrap=True)

    max_val = max((f["value"] for f in flagged), default=1) or 1
    for f in flagged:
        v         = f["value"]
        delta     = f["delta_pct"]
        status    = f["status"]
        delta_str = f"[green]+{delta:.1f}%[/green]" if delta >= 0 else f"[red]{delta:.1f}%[/red]"
        if status == "high":
            scol, sym = "red",    "[red]HIGH [/red]"
        elif status == "low":
            scol, sym = "yellow", "[yellow]LOW  [/yellow]"
        else:
            scol, sym = "green",  "[green]ok   [/green]"
        bar_len = int(v / max_val * 20) if max_val else 0
        bar     = f"[{scol}]" + "█" * bar_len + f"[/{scol}]"
        tbl.add_row(f["day"], fmt(v), delta_str, sym, bar)

    console.print(tbl)

    # Interpretation hint
    if n_anom > 0:
        highs = [f for f in flagged if f["status"] == "high"]
        lows  = [f for f in flagged if f["status"] == "low"]
        if highs:
            console.print(
                f"[red]HIGH anomaly on {', '.join(f['day'] for f in highs)}[/red] — "
                "check: flash sales, data pipeline spike, duplicate records"
            )
        if lows:
            console.print(
                f"[yellow]LOW anomaly on {', '.join(f['day'] for f in lows)}[/yellow] — "
                "check: store closures, holiday, payment gateway issue"
            )
    console.print(
        f"\n[dim]Baseline: {data['baseline_days']} days history. "
        f"Source: {'dws_order_base_metrics_d (DWS)' if data['dws_used'] else 'dwd_v_order (fallback)'}.[/dim]"
    )


def _get_mcp_canvas(config, canvas_id: str) -> dict:
    """Fetch canvas journey funnel data for a given canvas/activity ID."""
    safe_id = _sanitize_string_input(canvas_id, 50)
    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    database = config.mcp.database

    with MCPClient(mcp_config) as client:
        client.initialize()

        # Canvas-level summary
        canvas_rows = client.query(f"""
            SELECT
                activity_code,
                activity_name,
                start_date,
                end_date,
                total_enter_cnt,
                total_finish_cnt,
                total_convert_cnt,
                total_convert_gmv
            FROM ads_das_activity_canvas_analysis_d
            WHERE activity_code = '{safe_id}'
            ORDER BY start_date DESC
            LIMIT 1
        """, database=database)

        # Node-level funnel
        node_rows = client.query(f"""
            SELECT
                node_id,
                node_name,
                node_type,
                node_order,
                enter_cnt,
                action_cnt,
                exit_cnt,
                convert_cnt,
                convert_gmv
            FROM ads_das_activity_node_canvas_analysis_d
            WHERE activity_code = '{safe_id}'
            ORDER BY node_order
        """, database=database)

    canvas = canvas_rows[0] if isinstance(canvas_rows, list) and canvas_rows else {}
    nodes = node_rows if isinstance(node_rows, list) else []

    return {
        "canvas_id": canvas_id,
        "canvas": canvas,
        "nodes": nodes,
    }


def _print_canvas(data: dict) -> None:
    from rich.table import Table
    from rich import box as rich_box
    from rich.panel import Panel

    canvas_id = data["canvas_id"]
    canvas    = data["canvas"]
    nodes     = data["nodes"]

    if not canvas and not nodes:
        console.print(f"[red]No canvas data found for activity: {canvas_id}[/red]")
        return

    # Canvas summary panel
    name        = canvas.get("activity_name", canvas_id)
    start       = canvas.get("start_date", "-")
    end         = canvas.get("end_date", "-")
    enter       = int(canvas.get("total_enter_cnt") or 0)
    finish      = int(canvas.get("total_finish_cnt") or 0)
    converts    = int(canvas.get("total_convert_cnt") or 0)
    gmv_raw     = float(canvas.get("total_convert_gmv") or 0)
    finish_rate = finish / enter * 100 if enter else 0
    conv_rate   = converts / enter * 100 if enter else 0

    summary = (
        f"Canvas:  [bold]{name}[/bold]  ([dim]{canvas_id}[/dim])\n"
        f"Period:  {start} ~ {end}\n"
        f"Entered: [cyan]{enter:,}[/cyan]   "
        f"Finished: [green]{finish:,}[/green] ({finish_rate:.1f}%)   "
        f"Converted: [yellow]{converts:,}[/yellow] ({conv_rate:.1f}%)\n"
        f"Conv GMV: [bold yellow]¥{gmv_raw/100:,.0f}[/bold yellow]"
    )
    console.print(Panel(summary, title="[bold cyan]Canvas Journey Summary[/bold cyan]", border_style="cyan"))

    if not nodes:
        return

    # Node funnel table
    tbl = Table(
        title="Node Funnel",
        box=rich_box.SIMPLE_HEAVY,
        header_style="bold cyan",
    )
    tbl.add_column("#",          style="dim",    width=3)
    tbl.add_column("Node",       style="bold",   min_width=18)
    tbl.add_column("Type",       style="dim",    width=10)
    tbl.add_column("Enter",      justify="right")
    tbl.add_column("Action",     justify="right")
    tbl.add_column("Exit",       justify="right")
    tbl.add_column("Conv",       justify="right")
    tbl.add_column("Conv GMV",   justify="right")
    tbl.add_column("Drop%",      justify="right")
    tbl.add_column("Bar",        no_wrap=True)

    first_enter = int(nodes[0].get("enter_cnt") or 1) if nodes else 1

    for node in nodes:
        order      = str(node.get("node_order", "-"))
        nname      = str(node.get("node_name", "-"))
        ntype      = str(node.get("node_type", "-"))
        n_enter    = int(node.get("enter_cnt") or 0)
        n_action   = int(node.get("action_cnt") or 0)
        n_exit     = int(node.get("exit_cnt") or 0)
        n_conv     = int(node.get("convert_cnt") or 0)
        n_gmv      = float(node.get("convert_gmv") or 0)
        drop_pct   = n_exit / n_enter * 100 if n_enter else 0
        bar_len    = int(n_enter / first_enter * 20) if first_enter else 0
        bar_col    = "green" if drop_pct < 30 else ("yellow" if drop_pct < 60 else "red")
        bar        = f"[{bar_col}]" + "█" * bar_len + f"[/{bar_col}]"
        drop_str   = f"[red]{drop_pct:.1f}%[/red]" if drop_pct >= 50 else f"{drop_pct:.1f}%"

        tbl.add_row(
            order, nname, ntype,
            f"{n_enter:,}", f"{n_action:,}", f"{n_exit:,}", f"{n_conv:,}",
            f"¥{n_gmv/100:,.0f}",
            drop_str,
            bar,
        )

    console.print(tbl)

    # Drop-off insight
    worst = max(nodes, key=lambda n: int(n.get("exit_cnt") or 0), default=None)
    if worst:
        wname = worst.get("node_name", "-")
        wexit = int(worst.get("exit_cnt") or 0)
        wenter = int(worst.get("enter_cnt") or 1)
        console.print(
            f"\n[yellow]Highest drop-off node:[/yellow] [bold]{wname}[/bold] "
            f"— {wexit:,} exits ({wexit/wenter*100:.1f}% drop rate)"
        )


def _get_mcp_recommend(config, user_id: Optional[str] = None,
                        product_id: Optional[str] = None, limit: int = 20) -> dict:
    """Fetch recommendation analytics data.

    Modes:
      default:        top recommended products + co-purchase affinity
      --user <id>:    recommendations for a specific user
      --product <id>: products most associated with a given product
    """
    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    database = config.mcp.database

    safe_user    = _sanitize_string_input(user_id, 50) if user_id else None
    safe_product = _sanitize_string_input(product_id, 50) if product_id else None

    with MCPClient(mcp_config) as client:
        client.initialize()

        # Top-rated products across all users
        top_rows = client.query(f"""
            SELECT product_id,
                   COUNT(DISTINCT user_id)  AS rated_users,
                   AVG(rating)              AS avg_rating,
                   SUM(rating)              AS total_score
            FROM dwd_rec_user_product_rating
            GROUP BY product_id
            ORDER BY avg_rating DESC, rated_users DESC
            LIMIT {limit}
        """, database=database)

        # User-specific recs
        user_rows = []
        if safe_user:
            user_rows = client.query(f"""
                SELECT product_id, score, rank
                FROM dws_rec_user_recs
                WHERE user_id = '{safe_user}'
                ORDER BY rank
                LIMIT {limit}
            """, database=database)

        # Product-to-product affinity
        p2p_rows = []
        if safe_product:
            p2p_rows = client.query(f"""
                SELECT product_b_id AS related_product,
                       rating       AS affinity_score
                FROM dws_rec_product_to_prdocut_rating
                WHERE product_a_id = '{safe_product}'
                ORDER BY affinity_score DESC
                LIMIT {limit}
            """, database=database)
        else:
            # Top globally strong product pairs
            p2p_rows = client.query(f"""
                SELECT product_a_id, product_b_id, rating AS affinity_score
                FROM dws_rec_product_to_prdocut_rating
                ORDER BY affinity_score DESC
                LIMIT {limit}
            """, database=database)

        # Quality check: avg rating distribution
        quality_rows = client.query("""
            SELECT
                ROUND(rating, 0)       AS rating_bucket,
                COUNT(*)               AS cnt
            FROM dwd_rec_user_product_rating
            GROUP BY rating_bucket
            ORDER BY rating_bucket DESC
        """, database=database)

    return {
        "mode":        "user" if safe_user else ("product" if safe_product else "overview"),
        "user_id":     user_id,
        "product_id":  product_id,
        "top_products": top_rows if isinstance(top_rows, list) else [],
        "user_recs":   user_rows if isinstance(user_rows, list) else [],
        "p2p":         p2p_rows if isinstance(p2p_rows, list) else [],
        "quality":     quality_rows if isinstance(quality_rows, list) else [],
    }


def _print_recommend(data: dict) -> None:
    from rich.table import Table
    from rich import box as rich_box
    from rich.panel import Panel

    mode = data["mode"]

    if mode == "user":
        recs = data["user_recs"]
        console.print(Panel(
            f"User: [bold]{data['user_id']}[/bold]  |  {len(recs)} recommendations",
            title="[bold cyan]User Recommendations[/bold cyan]", border_style="cyan"
        ))
        tbl = Table(box=rich_box.SIMPLE_HEAVY, header_style="bold cyan")
        tbl.add_column("Rank", style="dim", width=5)
        tbl.add_column("Product ID", style="bold")
        tbl.add_column("Score", justify="right")
        for r in recs:
            tbl.add_row(str(r.get("rank","-")), str(r.get("product_id","-")),
                        f"{float(r.get('score') or 0):.3f}")
        console.print(tbl)

    elif mode == "product":
        p2p = data["p2p"]
        console.print(Panel(
            f"Product: [bold]{data['product_id']}[/bold]  |  {len(p2p)} related products",
            title="[bold cyan]Product Association[/bold cyan]", border_style="cyan"
        ))
        tbl = Table(box=rich_box.SIMPLE_HEAVY, header_style="bold cyan")
        tbl.add_column("Related Product", style="bold")
        tbl.add_column("Affinity Score", justify="right")
        for r in p2p:
            tbl.add_row(str(r.get("related_product","-")),
                        f"{float(r.get('affinity_score') or 0):.4f}")
        console.print(tbl)

    else:
        # Overview
        top = data["top_products"]
        p2p = data["p2p"]
        quality = data["quality"]

        # Rating quality distribution panel
        total_ratings = sum(int(q.get("cnt") or 0) for q in quality)
        q_str = "  ".join(
            f"[dim]{int(q.get('rating_bucket',0))}★:[/dim]{int(q.get('cnt') or 0):,}"
            for q in quality
        )
        console.print(Panel(
            f"Total ratings indexed: [bold]{total_ratings:,}[/bold]\n{q_str}",
            title="[bold cyan]Recommendation Engine Overview[/bold cyan]", border_style="cyan"
        ))

        # Top products
        if top:
            tbl = Table(title="Top Recommended Products", box=rich_box.SIMPLE_HEAVY,
                        header_style="bold cyan")
            tbl.add_column("Product ID",   style="bold", min_width=20)
            tbl.add_column("Rated Users",  justify="right")
            tbl.add_column("Avg Rating",   justify="right")
            tbl.add_column("Total Score",  justify="right")
            tbl.add_column("Bar",          no_wrap=True)
            max_score = max((float(r.get("total_score") or 0) for r in top), default=1) or 1
            for r in top:
                score = float(r.get("total_score") or 0)
                bar_len = int(score / max_score * 20)
                bar = "[cyan]" + "█" * bar_len + "[/cyan]"
                tbl.add_row(
                    str(r.get("product_id","-")),
                    f"{int(r.get('rated_users') or 0):,}",
                    f"{float(r.get('avg_rating') or 0):.2f}",
                    f"{score:,.0f}",
                    bar,
                )
            console.print(tbl)

        # Top product pairs
        if p2p:
            tbl2 = Table(title="Top Product Affinities (co-purchase)", box=rich_box.SIMPLE_HEAVY,
                         header_style="bold cyan")
            tbl2.add_column("Product A",    style="bold")
            tbl2.add_column("Product B",    style="bold")
            tbl2.add_column("Affinity",     justify="right")
            for r in p2p:
                tbl2.add_row(
                    str(r.get("product_a_id","-")),
                    str(r.get("product_b_id","-")),
                    f"{float(r.get('affinity_score') or 0):.4f}",
                )
            console.print(tbl2)


def _get_mcp_rfm(config, limit: int = 0, segment_filter: str = "") -> dict:
    """Compute RFM segments from ads_v_rfm using avg benchmarks in the view.

    ads_v_rfm columns: customer_code, Recency, Frequency, Monetary_1,
    avgRecency, avgFrequency, avgMonetary_1 (no pre-computed segment labels).

    Segmentation: compare each customer's R/F/M against the avg columns.
    CTE syntax is blocked by the gateway, so subqueries are used instead.
    """
    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    database = config.mcp.database
    safe_limit = max(1, min(int(limit), 500)) if limit > 0 else 0
    safe_seg   = _sanitize_string_input(segment_filter, 50) if segment_filter else ""

    seg_filter = f"WHERE segment = '{safe_seg}'" if safe_seg else ""

    # Inline CASE expression reused in both the distribution and top-customer queries
    _segment_expr = """
        CASE
            WHEN Recency <= avgRecency   AND Frequency >= avgFrequency AND Monetary_1 >= avgMonetary_1 THEN 'Champions'
            WHEN Recency <= avgRecency   AND Frequency >= avgFrequency AND Monetary_1 <  avgMonetary_1 THEN 'Loyal Customers'
            WHEN Recency <= avgRecency   AND Frequency <  avgFrequency AND Monetary_1 >= avgMonetary_1 THEN 'Potential Loyalists'
            WHEN Recency <= avgRecency   AND Frequency <  avgFrequency AND Monetary_1 <  avgMonetary_1 THEN 'New Customers'
            WHEN Recency >  avgRecency   AND Frequency >= avgFrequency AND Monetary_1 >= avgMonetary_1 THEN 'Cant Lose Them'
            WHEN Recency >  avgRecency   AND Frequency >= avgFrequency AND Monetary_1 <  avgMonetary_1 THEN 'Need Attention'
            WHEN Recency >  avgRecency   AND Frequency <  avgFrequency AND Monetary_1 >= avgMonetary_1 THEN 'About to Sleep'
            ELSE 'Hibernating'
        END
    """

    with MCPClient(mcp_config) as client:
        client.initialize()

        # Segment distribution
        dist_rows = client.query(f"""
            SELECT segment,
                   COUNT(*)                    AS customer_count,
                   ROUND(AVG(Monetary_1), 0)   AS avg_monetary_cny,
                   ROUND(AVG(Frequency), 2)    AS avg_frequency,
                   ROUND(AVG(Recency), 0)      AS avg_recency_days
            FROM (
                SELECT customer_code, Recency, Frequency, Monetary_1,
                       {_segment_expr} AS segment
                FROM ads_v_rfm
            ) t
            {seg_filter}
            GROUP BY segment
            ORDER BY customer_count DESC
        """, database=database)

        total_rows = client.query(f"""
            SELECT COUNT(*) AS total
            FROM (
                SELECT {_segment_expr} AS segment FROM ads_v_rfm
            ) t
            {seg_filter}
        """, database=database)

        total = int((total_rows[0].get("total") or 0) if isinstance(total_rows, list) and total_rows else 0)

        distribution = []
        if isinstance(dist_rows, list):
            for r in dist_rows:
                cnt = int(r.get("customer_count") or 0)
                distribution.append({
                    "rfm_segment":      str(r.get("segment") or "-"),
                    "customer_count":   cnt,
                    "share_pct":        round(cnt / total * 100, 1) if total else 0,
                    "avg_monetary_cny": round(float(r.get("avg_monetary_cny") or 0), 0),
                    "avg_frequency":    round(float(r.get("avg_frequency") or 0), 1),
                    "avg_recency_days": round(float(r.get("avg_recency_days") or 0), 0),
                })

        # Top customers (optional)
        top_customers = []
        if safe_limit > 0:
            top_rows = client.query(f"""
                SELECT customer_code, segment,
                       Recency AS recency_days,
                       Frequency AS frequency,
                       Monetary_1 AS monetary_cny
                FROM (
                    SELECT customer_code, Recency, Frequency, Monetary_1,
                           {_segment_expr} AS segment
                    FROM ads_v_rfm
                ) t
                {seg_filter}
                ORDER BY Monetary_1 DESC
                LIMIT {safe_limit}
            """, database=database)
            if isinstance(top_rows, list):
                top_customers = [
                    {
                        "customer_code": r.get("customer_code") or "-",
                        "rfm_segment":   r.get("segment") or "-",
                        "recency_days":  int(r.get("recency_days") or 0),
                        "frequency":     int(r.get("frequency") or 0),
                        "monetary_cny":  round(float(r.get("monetary_cny") or 0), 0),
                    }
                    for r in top_rows
                ]

    return {
        "total_customers": total,
        "segment_filter": segment_filter or "all",
        "distribution": distribution,
        "top_customers": top_customers,
    }


def _print_rfm(data: dict, show_top: bool = False) -> None:
    """Rich display for RFM analysis."""
    from rich.table import Table
    from rich import box as rich_box
    from rich.panel import Panel

    total = data.get("total_customers", 0)
    seg_f = data.get("segment_filter", "all")
    console.print(Panel(
        f"Total customers in RFM view: [bold]{total:,}[/bold]  |  "
        f"Filter: [cyan]{seg_f}[/cyan]",
        title="[bold cyan]RFM Customer Segmentation[/bold cyan]",
        border_style="cyan",
    ))

    dist = data.get("distribution", [])
    if dist:
        t = Table(title="Segment Distribution", box=rich_box.ROUNDED, header_style="bold cyan")
        t.add_column("Segment",      style="bold")
        t.add_column("Label",        style="dim")
        t.add_column("Customers",    justify="right", style="cyan")
        t.add_column("Share %",      justify="right")
        t.add_column("Avg Spend ¥",  justify="right", style="green")
        t.add_column("Avg Orders",   justify="right")
        t.add_column("Avg Recency",  justify="right", style="dim")
        t.add_column("Bar", no_wrap=True)

        max_cnt = max((r.get("customer_count", 0) for r in dist), default=1) or 1
        for r in dist:
            cnt  = r.get("customer_count", 0)
            pct  = r.get("share_pct", 0)
            bar  = "█" * int(cnt / max_cnt * 18)
            pc   = "green" if pct >= 20 else ("yellow" if pct >= 5 else "dim")
            t.add_row(
                str(r.get("rfm_segment") or "-"),
                str(r.get("rfm_label") or "-"),
                f"{cnt:,}",
                f"[{pc}]{pct:.1f}%[/{pc}]",
                f"{r.get('avg_monetary_cny', 0):,.0f}",
                f"{r.get('avg_frequency', 0):.1f}",
                f"{r.get('avg_recency_days', 0):.0f}d",
                f"[cyan]{bar}[/cyan]",
            )
        console.print(t)

    top = data.get("top_customers", [])
    if show_top and top:
        tt = Table(title=f"Top {len(top)} Customers by RFM Score",
                   box=rich_box.SIMPLE, header_style="bold dim")
        tt.add_column("Customer",     style="dim",   max_width=20)
        tt.add_column("Segment",      style="bold")
        tt.add_column("Label",        style="dim")
        tt.add_column("Recency (d)",  justify="right")
        tt.add_column("Orders",       justify="right", style="cyan")
        tt.add_column("Spend ¥",      justify="right", style="green")
        tt.add_column("RFM Score",    justify="right")
        for r in top:
            tt.add_row(
                str(r.get("customer_code") or "-"),
                str(r.get("rfm_segment") or "-"),
                str(r.get("rfm_label") or "-"),
                str(r.get("recency_days") or "-"),
                f"{int(r.get('frequency') or 0):,}",
                f"{float(r.get('monetary_cny') or 0):,.0f}",
                f"{float(r.get('rfm_score') or 0):.3f}",
            )
        console.print(tt)

    console.print("[dim]Source: ads_v_rfm (das_demoen)  |  monetary in CNY (÷100 from fen)[/dim]")
