"""Coupon analytics functions."""

from rich.console import Console

from ..api.mcp_client import MCPClient, MCPConfig as MCPClientConfig, MCPError
from ..output.export import format_output
from .common import (
    _compute_date_range,
    _safe_date_filter,
)

console = Console()


def _get_mcp_coupons(config, period: str, roi: bool = False) -> dict:
    """Get coupon analytics from MCP database.

    When roi=True, also computes:
    - Total face value issued / redeemed (par_value / 100 = CNY)
    - Breakdown by coupon_rule_code
    """
    # Validate and compute safe date range
    start_date, _ = _compute_date_range(period)
    date_filter = _safe_date_filter("create_time", start_date)

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
        api_key=config.mcp.api_key,
    )
    database = config.mcp.database

    with MCPClient(mcp_config) as client:
        client.initialize()

        # --- Base summary: try ads_das_v_coupon_analysis_d (ADS) first ---
        data = {
            "period": period,
            "total_issued": 0,
            "total_used": 0,
            "total_expired": 0,
            "unique_customers": 0,
            "usage_rate": 0.0,
            "total_face_value_cny": 0.0,
            "redeemed_face_value_cny": 0.0,
            "ads_used": False,
        }

        ads_ok = False
        try:
            ads_result = client.query(f"""
                SELECT
                    SUM(issue_cnt)    AS total_issued,
                    SUM(redeem_cnt)   AS total_used,
                    SUM(redeem_value) / 100.0 AS redeemed_face_value_cny
                FROM ads_das_v_coupon_analysis_d
                WHERE biz_date >= '{start_date}'
            """, database=database)
            if isinstance(ads_result, list) and ads_result and ads_result[0].get("total_issued") is not None:
                row = ads_result[0]
                data["total_issued"]          = int(row.get("total_issued") or 0)
                data["total_used"]            = int(row.get("total_used") or 0)
                data["redeemed_face_value_cny"] = float(row.get("redeemed_face_value_cny") or 0)
                if data["total_issued"] > 0:
                    data["usage_rate"] = round(data["total_used"] / data["total_issued"] * 100, 2)
                data["ads_used"] = True
                ads_ok = True
        except Exception:
            pass

        if not ads_ok:
            result = client.query(f"""
                SELECT
                    COUNT(*)                                                     AS total_issued,
                    SUM(CASE WHEN status = 'used'    THEN 1 ELSE 0 END)         AS total_used,
                    SUM(CASE WHEN status = 'expired' THEN 1 ELSE 0 END)         AS total_expired,
                    COUNT(DISTINCT customer_code)                                AS unique_customers,
                    SUM(par_value) / 100.0                                       AS total_face_value_cny,
                    SUM(CASE WHEN status = 'used' THEN par_value ELSE 0 END) / 100.0 AS redeemed_face_value_cny
                FROM dwd_coupon_instance
                {date_filter}
            """, database=database)

            if isinstance(result, list) and result:
                row = result[0]
                data["total_issued"]          = row.get("total_issued") or 0
                data["total_used"]            = row.get("total_used") or 0
                data["total_expired"]         = row.get("total_expired") or 0
                data["unique_customers"]      = row.get("unique_customers") or 0
                data["total_face_value_cny"]  = float(row.get("total_face_value_cny") or 0)
                data["redeemed_face_value_cny"] = float(row.get("redeemed_face_value_cny") or 0)
                if data["total_issued"] > 0:
                    data["usage_rate"] = round(data["total_used"] / data["total_issued"] * 100, 2)

        # --- Per-rule breakdown (when --roi) ---
        if roi:
            rule_result = client.query(f"""
                SELECT
                    coupon_rule_code,
                    COUNT(*)                                                     AS issued,
                    SUM(CASE WHEN status = 'used'    THEN 1 ELSE 0 END)         AS used,
                    SUM(CASE WHEN status = 'expired' THEN 1 ELSE 0 END)         AS expired,
                    SUM(par_value) / 100.0                                       AS face_value_cny,
                    SUM(CASE WHEN status = 'used' THEN par_value ELSE 0 END) / 100.0 AS redeemed_cny
                FROM dwd_coupon_instance
                {date_filter}
                GROUP BY coupon_rule_code
                ORDER BY issued DESC
                LIMIT 30
            """, database=database)

            rule_rows = []
            if isinstance(rule_result, list):
                for r in rule_result:
                    issued = int(r.get("issued") or 0)
                    used   = int(r.get("used") or 0)
                    rule_rows.append({
                        "coupon_rule_code": str(r.get("coupon_rule_code") or "-"),
                        "issued":           issued,
                        "used":             used,
                        "expired":          int(r.get("expired") or 0),
                        "usage_rate":       round(used / issued * 100, 1) if issued else 0.0,
                        "face_value_cny":   float(r.get("face_value_cny") or 0),
                        "redeemed_cny":     float(r.get("redeemed_cny") or 0),
                    })
            data["rule_breakdown"] = rule_rows

        return data


def _print_coupons_mcp(data: dict, show_roi: bool = False) -> None:
    """Rich output for MCP coupon analytics."""
    from rich.panel import Panel
    from rich.table import Table
    from rich import box as rich_box

    issued   = int(data.get("total_issued") or 0)
    used     = int(data.get("total_used") or 0)
    expired  = int(data.get("total_expired") or 0)
    pending  = issued - used - expired
    usage    = data.get("usage_rate") or 0.0
    face_cny = float(data.get("total_face_value_cny") or 0)
    red_cny  = float(data.get("redeemed_face_value_cny") or 0)
    value_rate = f"{red_cny/face_cny*100:.1f}%" if face_cny else "-"

    t = Table(show_header=False, box=rich_box.SIMPLE, padding=(0, 2))
    t.add_column("Metric", style="dim", min_width=24)
    t.add_column("Value", style="bold", justify="right", min_width=14)
    t.add_column("Note", style="dim")

    t.add_row("Total Issued",      f"{issued:,}",   f"Period: {data.get('period')}")
    t.add_row("Used",              f"{used:,}",     f"Usage rate: {usage:.1f}%")
    t.add_row("Expired",           f"{expired:,}",  "")
    t.add_row("Pending",           f"{pending:,}",  "Still active")
    t.add_row("Unique Customers",  f"{int(data.get('unique_customers') or 0):,}", "")
    t.add_row("", "", "")
    t.add_row("Total Face Value",  f"CNY {face_cny:,.2f}", "All issued coupons")
    t.add_row("Redeemed Value",    f"CNY {red_cny:,.2f}",  f"Value redemption rate: {value_rate}")

    console.print()
    console.print(Panel(t, title="[bold cyan]Coupon Analytics[/bold cyan]", border_style="cyan"))

    # Per-rule breakdown
    if show_roi and "rule_breakdown" in data and data["rule_breakdown"]:
        rt = Table(title="Breakdown by Coupon Rule", box=rich_box.ROUNDED, header_style="bold cyan")
        rt.add_column("Rule Code", style="dim")
        rt.add_column("Issued",    justify="right")
        rt.add_column("Used",      justify="right")
        rt.add_column("Usage %",   justify="right")
        rt.add_column("Expired",   justify="right", style="dim")
        rt.add_column("Face Value (CNY)", justify="right")
        rt.add_column("Redeemed (CNY)",   justify="right", style="bold")

        for r in data["rule_breakdown"]:
            rt.add_row(
                str(r.get("coupon_rule_code") or "-"),
                f"{int(r.get('issued') or 0):,}",
                f"{int(r.get('used') or 0):,}",
                f"{r.get('usage_rate') or 0:.1f}%",
                f"{int(r.get('expired') or 0):,}",
                f"{float(r.get('face_value_cny') or 0):,.2f}",
                f"{float(r.get('redeemed_cny') or 0):,.2f}",
            )
        console.print(rt)


def _get_mcp_coupon_lift(config, period: str) -> dict:
    """Compare order behaviour of coupon users vs non-users (dwd tables, das_demoen).

    Three queries inside one MCP session:
    1. Set of distinct customer_codes that used a coupon in period
    2. Order stats for that cohort
    3. Order stats for everyone else in the same period
    """
    start_date, _ = _compute_date_range(period)
    date_filter_coupon = _safe_date_filter("create_time", start_date)
    date_filter_order  = _safe_date_filter("order_date", start_date)

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
        api_key=config.mcp.api_key,
    )
    database = config.mcp.database

    with MCPClient(mcp_config) as client:
        client.initialize()

        # ── 1. Coupon-user cohort (who used a coupon this period) ─────────────
        used_rows = client.query(f"""
            SELECT COUNT(DISTINCT customer_code) AS coupon_user_count
            FROM dwd_coupon_instance
            {date_filter_coupon}
              AND status IN ('used', '2')
        """, database=database)

        coupon_user_count = int(
            (used_rows[0].get("coupon_user_count") or 0)
            if isinstance(used_rows, list) and used_rows else 0
        )

        # ── 2. Order stats — coupon users ─────────────────────────────────────
        with_rows = client.query(f"""
            SELECT
                COUNT(*)                            AS order_count,
                COUNT(DISTINCT o.customer_code)     AS customer_count,
                SUM(o.total_amount) / 100.0         AS total_revenue_cny,
                AVG(o.total_amount) / 100.0         AS avg_order_value_cny
            FROM dwd_v_order o
            WHERE o.customer_code IN (
                SELECT DISTINCT customer_code
                FROM dwd_coupon_instance
                {date_filter_coupon}
                  AND status IN ('used', '2')
            )
              AND o.direction = 0
              {date_filter_order.replace('WHERE', 'AND')}
        """, database=database)

        # ── 3. Order stats — non-coupon users ─────────────────────────────────
        without_rows = client.query(f"""
            SELECT
                COUNT(*)                            AS order_count,
                COUNT(DISTINCT o.customer_code)     AS customer_count,
                SUM(o.total_amount) / 100.0         AS total_revenue_cny,
                AVG(o.total_amount) / 100.0         AS avg_order_value_cny
            FROM dwd_v_order o
            WHERE o.customer_code NOT IN (
                SELECT DISTINCT customer_code
                FROM dwd_coupon_instance
                {date_filter_coupon}
                  AND status IN ('used', '2')
            )
              AND o.direction = 0
              {date_filter_order.replace('WHERE', 'AND')}
        """, database=database)

        # ── 4. Repeat-purchase rate per cohort ───────────────────────────────
        repeat_with = client.query(f"""
            SELECT COUNT(*) AS repeat_customers
            FROM (
                SELECT o.customer_code
                FROM dwd_v_order o
                WHERE o.customer_code IN (
                    SELECT DISTINCT customer_code
                    FROM dwd_coupon_instance
                    {date_filter_coupon}
                      AND status IN ('used', '2')
                )
                  AND o.direction = 0
                  {date_filter_order.replace('WHERE', 'AND')}
                GROUP BY o.customer_code
                HAVING COUNT(*) > 1
            ) t
        """, database=database)

        repeat_without = client.query(f"""
            SELECT COUNT(*) AS repeat_customers
            FROM (
                SELECT o.customer_code
                FROM dwd_v_order o
                WHERE o.customer_code NOT IN (
                    SELECT DISTINCT customer_code
                    FROM dwd_coupon_instance
                    {date_filter_coupon}
                      AND status IN ('used', '2')
                )
                  AND o.direction = 0
                  {date_filter_order.replace('WHERE', 'AND')}
                GROUP BY o.customer_code
                HAVING COUNT(*) > 1
            ) t
        """, database=database)

    def _row0(rows, key, default=0):
        return (rows[0].get(key) or default) if isinstance(rows, list) and rows else default

    def _cohort(order_rows, repeat_rows):
        orders   = int(_row0(order_rows, "order_count"))
        custs    = int(_row0(order_rows, "customer_count"))
        revenue  = float(_row0(order_rows, "total_revenue_cny", 0.0))
        aov      = float(_row0(order_rows, "avg_order_value_cny", 0.0))
        repeat   = int(_row0(repeat_rows, "repeat_customers"))
        repurchase_rate = round(repeat / custs * 100, 2) if custs else 0
        orders_per_cust = round(orders / custs, 2) if custs else 0
        return {
            "order_count": orders,
            "customer_count": custs,
            "total_revenue_cny": revenue,
            "avg_order_value_cny": aov,
            "repurchase_rate": repurchase_rate,
            "orders_per_customer": orders_per_cust,
        }

    with_data    = _cohort(with_rows, repeat_with)
    without_data = _cohort(without_rows, repeat_without)

    # Compute lift ratios
    def _lift(a, b):
        return round((a - b) / b * 100, 1) if b else None

    return {
        "period": period,
        "coupon_user_count": coupon_user_count,
        "with_coupon": with_data,
        "without_coupon": without_data,
        "lift": {
            "aov_lift_pct": _lift(
                with_data["avg_order_value_cny"],
                without_data["avg_order_value_cny"],
            ),
            "repurchase_lift_pct": _lift(
                with_data["repurchase_rate"],
                without_data["repurchase_rate"],
            ),
            "orders_per_cust_lift_pct": _lift(
                with_data["orders_per_customer"],
                without_data["orders_per_customer"],
            ),
        },
    }


def _print_coupon_lift(data: dict) -> None:
    """Rich display for coupon lift analysis."""
    from rich.table import Table
    from rich import box as rich_box
    from rich.panel import Panel

    period = data.get("period", "-")
    coupon_users = data.get("coupon_user_count", 0)
    w  = data.get("with_coupon", {})
    wo = data.get("without_coupon", {})
    lift = data.get("lift", {})

    def _lift_str(val):
        if val is None:
            return "[dim]-[/dim]"
        style = "green" if val > 0 else "red"
        sign = "+" if val > 0 else ""
        return f"[{style}]{sign}{val:.1f}%[/{style}]"

    # Summary panel
    aov_lift = lift.get("aov_lift_pct")
    rep_lift  = lift.get("repurchase_lift_pct")
    summary = (
        f"[bold]Period:[/bold] {period}   "
        f"[bold]Coupon users:[/bold] {coupon_users:,}\n\n"
        f"[bold]AOV Lift:[/bold]           {_lift_str(aov_lift)}"
        f"  (¥{w.get('avg_order_value_cny', 0):,.2f} vs ¥{wo.get('avg_order_value_cny', 0):,.2f})\n"
        f"[bold]Repurchase Lift:[/bold]    {_lift_str(rep_lift)}"
        f"  ({w.get('repurchase_rate', 0):.1f}% vs {wo.get('repurchase_rate', 0):.1f}%)\n"
        f"[bold]Orders/Customer Lift:[/bold] {_lift_str(lift.get('orders_per_cust_lift_pct'))}"
        f"  ({w.get('orders_per_customer', 0):.2f} vs {wo.get('orders_per_customer', 0):.2f})"
    )
    console.print(Panel(summary, title="[bold]Coupon Lift Analysis[/bold]", border_style="green"))

    # Detail comparison table
    t = Table(box=rich_box.SIMPLE, header_style="bold")
    t.add_column("Metric")
    t.add_column("With Coupon",    justify="right", style="green")
    t.add_column("Without Coupon", justify="right", style="dim")
    t.add_column("Lift",           justify="right")

    rows_def = [
        ("Customers",         f"{w.get('customer_count', 0):,}",
                               f"{wo.get('customer_count', 0):,}",       "-"),
        ("Orders",            f"{w.get('order_count', 0):,}",
                               f"{wo.get('order_count', 0):,}",          "-"),
        ("Revenue (CNY)",     f"{w.get('total_revenue_cny', 0):,.2f}",
                               f"{wo.get('total_revenue_cny', 0):,.2f}", "-"),
        ("Avg Order Value",   f"¥{w.get('avg_order_value_cny', 0):,.2f}",
                               f"¥{wo.get('avg_order_value_cny', 0):,.2f}",
                               _lift_str(aov_lift)),
        ("Repurchase Rate",   f"{w.get('repurchase_rate', 0):.1f}%",
                               f"{wo.get('repurchase_rate', 0):.1f}%",
                               _lift_str(rep_lift)),
        ("Orders/Customer",   f"{w.get('orders_per_customer', 0):.2f}",
                               f"{wo.get('orders_per_customer', 0):.2f}",
                               _lift_str(lift.get("orders_per_cust_lift_pct"))),
    ]
    for row in rows_def:
        t.add_row(*row)
    console.print(t)
    console.print(
        "[dim]Lift% = (with_coupon - without_coupon) / without_coupon × 100[/dim]"
    )


def _get_mcp_coupons_by_rule(config, period: str, limit: int) -> list:
    """Per-coupon-rule: issued, used, redeemed value, and attributed GMV."""
    start_date, _ = _compute_date_range(period)
    date_filter_c = _safe_date_filter("c.create_time", start_date)
    date_filter_o = _safe_date_filter("o.order_date", start_date)
    if not isinstance(limit, int) or limit < 1 or limit > 200:
        limit = 20

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
        api_key=config.mcp.api_key,
    )
    database = config.mcp.database

    with MCPClient(mcp_config) as client:
        client.initialize()

        # Coupon issuance & usage stats per rule
        issue_rows = client.query(f"""
            SELECT
                coupon_rule_code,
                COUNT(*)                                              AS issued,
                SUM(CASE WHEN status = 2 THEN 1 ELSE 0 END)          AS used,
                SUM(CASE WHEN status = 2 THEN par_value ELSE 0 END) / 100.0
                                                                      AS discount_given_cny
            FROM dwd_coupon_instance c
            {date_filter_c}
            GROUP BY coupon_rule_code
            ORDER BY issued DESC
            LIMIT {limit}
        """, database=database)

        if not isinstance(issue_rows, list) or not issue_rows:
            return []

        # Attributed GMV: orders placed by coupon users in period
        attr_rows = client.query(f"""
            SELECT
                c.coupon_rule_code,
                COUNT(DISTINCT o.code)          AS attributed_orders,
                SUM(o.total_amount) / 100.0     AS attributed_gmv_cny
            FROM dwd_coupon_instance c
            JOIN dwd_v_order o
              ON o.customer_code = c.customer_code
            {date_filter_o.replace('WHERE', 'AND')}
              AND c.status = 2
            {date_filter_c.replace('WHERE', 'AND')}
            GROUP BY c.coupon_rule_code
        """, database=database)

        attr_map = {}
        if isinstance(attr_rows, list):
            for r in attr_rows:
                attr_map[r.get("coupon_rule_code")] = r

    result = []
    for r in issue_rows:
        rule = r.get("coupon_rule_code") or "—"
        issued = int(r.get("issued") or 0)
        used   = int(r.get("used") or 0)
        disc   = float(r.get("discount_given_cny") or 0)
        attr   = attr_map.get(rule, {})
        gmv    = float(attr.get("attributed_gmv_cny") or 0)
        roi_val = gmv / disc if disc > 0 else None
        result.append({
            "coupon_rule_code": rule,
            "issued": issued,
            "used": used,
            "use_rate": f"{used/issued*100:.1f}%" if issued else "—",
            "discount_given_cny": disc,
            "attributed_gmv_cny": gmv,
            "roi": f"{roi_val:.1f}x" if roi_val is not None else "—",
            "roi_value": roi_val,
        })
    return result


def _print_coupons_by_rule(rows: list, period: str, output: str = None) -> None:
    from rich.table import Table
    from rich import box as rich_box

    if output:
        format_output(rows, "json", output)
        return
    if not rows:
        console.print("[yellow]No coupon rule data[/yellow]")
        return

    tbl = Table(title=f"Coupon Rule ROI  ({period})",
                box=rich_box.SIMPLE_HEAVY, header_style="bold cyan")
    tbl.add_column("Rule Code",   style="dim", max_width=22)
    tbl.add_column("Issued",      justify="right")
    tbl.add_column("Used",        justify="right")
    tbl.add_column("Use Rate",    justify="right")
    tbl.add_column("Discount (¥)",justify="right")
    tbl.add_column("Attr. GMV (¥)",justify="right", style="green")
    tbl.add_column("ROI",         justify="right", style="cyan")

    for r in sorted(rows, key=lambda x: x["attributed_gmv_cny"], reverse=True):
        roi = r["roi"]
        roi_val = r.get("roi_value")
        roi_color = "green" if roi_val is not None and roi_val >= 3 else (
                    "yellow" if roi_val is not None and roi_val >= 1 else "red")
        tbl.add_row(
            r["coupon_rule_code"],
            f"{r['issued']:,}", f"{r['used']:,}", r["use_rate"],
            f"{r['discount_given_cny']:,.0f}",
            f"{r['attributed_gmv_cny']:,.0f}",
            f"[{roi_color}]{roi}[/{roi_color}]",
        )
    console.print(tbl)
    console.print("[dim]ROI = attributed GMV / discount given. Attribution: coupon user orders in same period.[/dim]")


def _get_mcp_coupon_anomaly(config, lookback: int = 30, detect_days: int = 7) -> dict:
    """Detect abnormal daily coupon redeem volume using mean+2sigma."""
    from datetime import datetime, timedelta

    today      = datetime.now().date()
    start_base = (today - timedelta(days=lookback + detect_days)).isoformat()
    end_base   = (today - timedelta(days=detect_days + 1)).isoformat()
    start_det  = (today - timedelta(days=detect_days)).isoformat()
    end_det    = today.isoformat()

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
        api_key=config.mcp.api_key,
    )
    database = config.mcp.database

    with MCPClient(mcp_config) as client:
        client.initialize()

        rows = None
        dws_ok = False
        try:
            rows = client.query(f"""
                SELECT biz_date AS day,
                       redeem_cnt  AS redeem_vol,
                       redeem_amount AS redeem_amt
                FROM dws_coupon_base_metrics_d
                WHERE biz_date BETWEEN '{start_base}' AND '{end_det}'
                ORDER BY day
            """, database=database)
            if isinstance(rows, list) and rows:
                dws_ok = True
        except Exception:
            pass

        if not dws_ok:
            rows = client.query(f"""
                SELECT DATE(use_time) AS day,
                       COUNT(*)        AS redeem_vol,
                       SUM(face_value) AS redeem_amt
                FROM dwd_v_coupon_record
                WHERE delete_flag = 0 AND use_status = 1
                  AND use_time BETWEEN '{start_base}' AND '{end_det}'
                GROUP BY DATE(use_time)
                ORDER BY day
            """, database=database)

    history_rows = rows if isinstance(rows, list) else []
    baseline  = [r for r in history_rows if str(r.get("day","")) <= end_base]
    detection = [r for r in history_rows if str(r.get("day","")) >= start_det]

    def _vol(r):
        return float(r.get("redeem_vol") or 0)

    base_vals = [_vol(r) for r in baseline]
    if not base_vals:
        return {"error": "Insufficient baseline data"}

    mean = sum(base_vals) / len(base_vals)
    std  = (sum((x - mean) ** 2 for x in base_vals) / len(base_vals)) ** 0.5
    upper = mean + 2 * std
    lower = max(0.0, mean - 2 * std)

    flagged = []
    for r in detection:
        v     = _vol(r)
        day   = str(r.get("day",""))
        delta = (v - mean) / mean * 100 if mean else 0
        status = "high" if v > upper else ("low" if v < lower else "normal")
        flagged.append({
            "day": day, "redeem_vol": v,
            "redeem_amt": float(r.get("redeem_amt") or 0) / 100,
            "delta_pct": delta, "status": status,
        })

    return {
        "dws_used": dws_ok,
        "baseline_days": len(base_vals),
        "mean": mean, "std": std,
        "upper_2sigma": upper, "lower_2sigma": lower,
        "detection": flagged,
        "anomaly_count": sum(1 for f in flagged if f["status"] != "normal"),
    }


def _print_coupon_anomaly(data: dict) -> None:
    from rich.table import Table
    from rich import box as rich_box
    from rich.panel import Panel

    if "error" in data:
        console.print(f"[red]{data['error']}[/red]")
        return

    mean, std  = data["mean"], data["std"]
    upper, lower = data["upper_2sigma"], data["lower_2sigma"]
    flagged    = data["detection"]
    n_anom     = data["anomaly_count"]
    sc         = "green" if n_anom == 0 else ("yellow" if n_anom <= 2 else "red")

    summary = (
        f"Baseline: mean={mean:.0f}/day  std={std:.0f}\n"
        f"Band:     [{lower:.0f}, {upper:.0f}]  (mean +/- 2sigma)\n"
        f"Anomalies: [{sc}]{n_anom} day(s)[/{sc}]  "
        f"({'[green]Normal[/green]' if n_anom == 0 else '[red]Needs review[/red]'})"
    )
    console.print(Panel(summary, title="[bold cyan]Coupon Redeem Anomaly[/bold cyan]", border_style="cyan"))

    if not flagged:
        return

    tbl = Table(box=rich_box.SIMPLE_HEAVY, header_style="bold cyan",
                title=f"Detection Window ({len(flagged)} days)")
    tbl.add_column("Date",       style="dim")
    tbl.add_column("Redeem Vol", justify="right")
    tbl.add_column("Redeem Amt",  justify="right")
    tbl.add_column("vs Mean",    justify="right")
    tbl.add_column("Status",     justify="center")

    for f in flagged:
        st    = f["status"]
        delta = f["delta_pct"]
        sym   = "[red]HIGH[/red]" if st == "high" else ("[yellow]LOW[/yellow]" if st == "low" else "[green]ok[/green]")
        ds    = f"[green]+{delta:.1f}%[/green]" if delta >= 0 else f"[red]{delta:.1f}%[/red]"
        tbl.add_row(f["day"], f"{f['redeem_vol']:,.0f}", f"¥{f['redeem_amt']:,.0f}", ds, sym)

    console.print(tbl)

    highs = [f for f in flagged if f["status"] == "high"]
    lows  = [f for f in flagged if f["status"] == "low"]
    if highs:
        console.print(
            f"[red]HIGH on {', '.join(f['day'] for f in highs)}[/red] — "
            "check: bulk issuance, batch exploit, duplicate records"
        )
    if lows:
        console.print(
            f"[yellow]LOW on {', '.join(f['day'] for f in lows)}[/yellow] — "
            "check: expiry cliff, campaign end, delivery failure"
        )
    console.print(
        f"\n[dim]Baseline: {data['baseline_days']} days. "
        f"Source: {'dws_coupon_base_metrics_d' if data['dws_used'] else 'dwd_v_coupon_record (fallback)'}.[/dim]"
    )
