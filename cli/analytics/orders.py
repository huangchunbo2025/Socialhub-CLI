"""Order analytics functions."""

import re

from rich.console import Console

from ..api.mcp_client import MCPClient, MCPConfig as MCPClientConfig, MCPError
from ..output.export import format_output
from .common import (
    _compute_date_range,
    _mcp_query_timeout,
    _safe_date_filter,
    _validate_group_by,
)
from .overview import _fmt_cny, _pct_delta, _color_delta, _print_compare_row

console = Console()


def _get_mcp_orders_overall_with_client(client, database: str, date_filter: str, timeout=None) -> dict:
    """Get overall order metrics in one query within an existing MCP session."""
    result = client.query(f"""
        SELECT
            COUNT(*) AS total_orders,
            SUM(total_amount) AS total_sales,
            AVG(total_amount) AS avg_order_value,
            COUNT(DISTINCT customer_code) AS unique_customers,
            COUNT(DISTINCT CASE WHEN order_cnt > 1 THEN customer_code END) AS repeat_customers
        FROM (
            SELECT
                customer_code,
                total_amount,
                COUNT(*) OVER (PARTITION BY customer_code) AS order_cnt
            FROM dwd_v_order
            {date_filter}
        ) t
    """, database=database, timeout=timeout)

    data = {
        "total_orders": 0,
        "total_sales": 0.0,
        "avg_order_value": 0.0,
        "unique_customers": 0,
        "repurchase_rate": 0.0,
    }
    if isinstance(result, list) and result:
        row = result[0]
        data["total_orders"] = row.get("total_orders") or 0
        data["total_sales"] = float(row.get("total_sales") or 0)
        data["avg_order_value"] = float(row.get("avg_order_value") or 0)
        data["unique_customers"] = row.get("unique_customers") or 0
        repeat_customers = row.get("repeat_customers") or 0
        if data["unique_customers"] > 0:
            data["repurchase_rate"] = round(repeat_customers / data["unique_customers"] * 100, 2)
    return data


def _get_mcp_orders_grouped_with_client(client, database: str, date_filter: str, by: str, timeout=None) -> list:
    """Get grouped order metrics within an existing MCP session."""
    if by == "channel":
        result = client.query(f"""
            SELECT
                COALESCE(source_name, 'unknown') as channel,
                COUNT(*) as order_count,
                SUM(total_amount) as total_sales,
                AVG(total_amount) as avg_order_value
            FROM dwd_v_order
            {date_filter}
            GROUP BY source_name
            ORDER BY total_sales DESC
        """, database=database, timeout=timeout)
        return result if isinstance(result, list) else []

    result = client.query(f"""
        SELECT
            COALESCE(store_name, 'Online') as store,
            COUNT(*) as order_count,
            SUM(total_amount) as total_sales
        FROM dwd_v_order
        {date_filter}
        GROUP BY store_name
        ORDER BY total_sales DESC
        LIMIT 20
    """, database=database, timeout=timeout)
    return result if isinstance(result, list) else []


def _get_mcp_order_returns_with_client(client, database: str, date_filter: str, period: str, timeout=None) -> dict:
    """Get return/exchange analysis within an existing MCP session."""
    summary = client.query(f"""
        SELECT
            direction,
            COUNT(*) AS order_count,
            SUM(total_amount) / 100.0 AS amount_cny,
            COUNT(DISTINCT customer_code) AS unique_customers
        FROM dwd_v_order
        {date_filter}
        GROUP BY direction
        ORDER BY direction
    """, database=database, timeout=timeout)

    trend = client.query(f"""
        SELECT
            order_date,
            COUNT(CASE WHEN direction = 0 THEN 1 END) AS normal_orders,
            COUNT(CASE WHEN direction = 1 THEN 1 END) AS return_orders,
            COUNT(CASE WHEN direction = 2 THEN 1 END) AS exchange_orders
        FROM dwd_v_order
        {date_filter}
        GROUP BY order_date
        ORDER BY order_date DESC
        LIMIT 14
    """, database=database, timeout=timeout)

    direction_labels = {0: "姝ｅ崟 (Sale)", 1: "閫€鍗?(Return)", 2: "鎹㈣揣鍗?(Exchange)"}
    breakdown = []
    totals = {"normal": 0, "return": 0, "exchange": 0, "total": 0}

    if isinstance(summary, list):
        for row in summary:
            d = row.get("direction")
            cnt = int(row.get("order_count") or 0)
            breakdown.append({
                "direction": d,
                "label": direction_labels.get(d, f"Unknown ({d})"),
                "order_count": cnt,
                "amount_cny": float(row.get("amount_cny") or 0),
                "unique_customers": int(row.get("unique_customers") or 0),
            })
            if d == 0:
                totals["normal"] = cnt
            elif d == 1:
                totals["return"] = cnt
            elif d == 2:
                totals["exchange"] = cnt
            totals["total"] += cnt

    total = totals["total"]
    return {
        "period": period,
        "breakdown": breakdown,
        "return_rate": round(totals["return"] / total * 100, 2) if total else 0,
        "exchange_rate": round(totals["exchange"] / total * 100, 2) if total else 0,
        "return_exchange_rate": round((totals["return"] + totals["exchange"]) / total * 100, 2) if total else 0,
        "trend": trend if isinstance(trend, list) else [],
    }


def _get_mcp_orders(config, period: str, metric: str, by: str = None) -> dict:
    """Get order analytics from MCP database."""
    # Validate inputs
    start_date, _ = _compute_date_range(period)
    if by:
        _validate_group_by(by)

    # Build safe date filter
    date_filter = _safe_date_filter("order_date", start_date)

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    database = config.mcp.database
    query_timeout = _mcp_query_timeout(period, grouped=bool(by))

    with MCPClient(mcp_config) as client:
        client.initialize()

        if by == "channel":
            return _get_mcp_orders_grouped_with_client(client, database, date_filter, by, query_timeout)

        elif by == "province" or by == "store":
            return _get_mcp_orders_grouped_with_client(client, database, date_filter, by, query_timeout)

        elif by == "product":
            from .products import _get_mcp_products
            return _get_mcp_products(config, period, by_category=False, limit=30)

        else:
            data = _get_mcp_orders_overall_with_client(client, database, date_filter, query_timeout)
            data["period"] = period
            return data


def _get_mcp_order_returns(config, period: str) -> dict:
    """Get return/exchange rate analysis from dwd_v_order using direction field.

    direction: 0=正单, 1=退单, 2=换货单
    """
    start_date, _ = _compute_date_range(period)
    date_filter = _safe_date_filter("order_date", start_date)

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    database = config.mcp.database

    with MCPClient(mcp_config) as client:
        client.initialize()

        # Summary by direction
        summary = client.query(f"""
            SELECT
                direction,
                COUNT(*) AS order_count,
                SUM(total_amount) / 100.0 AS amount_cny,
                COUNT(DISTINCT customer_code) AS unique_customers
            FROM dwd_v_order
            {date_filter}
            GROUP BY direction
            ORDER BY direction
        """, database=database)

        # Daily trend (last 14 days within period) for returns only
        trend = client.query(f"""
            SELECT
                order_date,
                COUNT(CASE WHEN direction = 0 THEN 1 END) AS normal_orders,
                COUNT(CASE WHEN direction = 1 THEN 1 END) AS return_orders,
                COUNT(CASE WHEN direction = 2 THEN 1 END) AS exchange_orders
            FROM dwd_v_order
            {date_filter}
            GROUP BY order_date
            ORDER BY order_date DESC
            LIMIT 14
        """, database=database)

    direction_labels = {0: "正单 (Sale)", 1: "退单 (Return)", 2: "换货单 (Exchange)"}
    breakdown = []
    totals = {"normal": 0, "return": 0, "exchange": 0, "total": 0}

    if isinstance(summary, list):
        for row in summary:
            d = row.get("direction")
            cnt = int(row.get("order_count") or 0)
            breakdown.append({
                "direction": d,
                "label": direction_labels.get(d, f"Unknown ({d})"),
                "order_count": cnt,
                "amount_cny": float(row.get("amount_cny") or 0),
                "unique_customers": int(row.get("unique_customers") or 0),
            })
            if d == 0:
                totals["normal"] = cnt
            elif d == 1:
                totals["return"] = cnt
            elif d == 2:
                totals["exchange"] = cnt
            totals["total"] += cnt

    total = totals["total"]
    return {
        "period": period,
        "breakdown": breakdown,
        "return_rate": round(totals["return"] / total * 100, 2) if total else 0,
        "exchange_rate": round(totals["exchange"] / total * 100, 2) if total else 0,
        "return_exchange_rate": round((totals["return"] + totals["exchange"]) / total * 100, 2) if total else 0,
        "trend": trend if isinstance(trend, list) else [],
    }


def _print_order_returns(data: dict) -> None:
    """Rich display for order return/exchange analysis."""
    from rich.table import Table
    from rich import box as rich_box
    from rich.panel import Panel

    period = data.get("period", "-")
    breakdown = data.get("breakdown", [])
    trend = data.get("trend", [])

    # Summary panel
    lines = [
        f"[bold]Period:[/bold] {period}",
        f"[bold]Return Rate:[/bold]   [red]{data.get('return_rate', 0):.2f}%[/red]  (退单/total)",
        f"[bold]Exchange Rate:[/bold] [yellow]{data.get('exchange_rate', 0):.2f}%[/yellow]  (换货单/total)",
        f"[bold]Combined:[/bold]      [magenta]{data.get('return_exchange_rate', 0):.2f}%[/magenta]  ((退+换)/total)",
    ]
    console.print(Panel("\n".join(lines), title="[bold]Order Return Analysis[/bold]", border_style="red"))

    # Breakdown table
    if breakdown:
        t = Table(box=rich_box.SIMPLE, header_style="bold")
        t.add_column("Type")
        t.add_column("Orders", justify="right")
        t.add_column("Amount (CNY)", justify="right")
        t.add_column("Unique Customers", justify="right")
        t.add_column("Share", justify="right")

        total_orders = sum(r.get("order_count", 0) for r in breakdown)
        for r in breakdown:
            cnt = r.get("order_count", 0)
            share = f"{cnt / total_orders * 100:.1f}%" if total_orders else "-"
            d = r.get("direction")
            style = "red" if d == 1 else ("yellow" if d == 2 else "green")
            t.add_row(
                f"[{style}]{r.get('label', '-')}[/{style}]",
                f"{cnt:,}",
                f"{r.get('amount_cny', 0):,.2f}",
                f"{r.get('unique_customers', 0):,}",
                share,
            )
        console.print(t)

    # Daily trend
    if trend:
        console.print("[bold]Daily Trend (last 14 days)[/bold]")
        tt = Table(box=rich_box.SIMPLE, header_style="bold dim")
        tt.add_column("Date")
        tt.add_column("Sales", justify="right", style="green")
        tt.add_column("Returns", justify="right", style="red")
        tt.add_column("Exchanges", justify="right", style="yellow")
        tt.add_column("Return Rate", justify="right")
        for r in trend:
            normal = int(r.get("normal_orders") or 0)
            ret = int(r.get("return_orders") or 0)
            exc = int(r.get("exchange_orders") or 0)
            total_day = normal + ret + exc
            rate = f"{ret / total_day * 100:.1f}%" if total_day else "-"
            tt.add_row(
                str(r.get("order_date") or "-"),
                f"{normal:,}",
                f"{ret:,}",
                f"{exc:,}",
                rate,
            )
        console.print(tt)


def _print_orders_by_product(rows: list, period: str, output: str = None) -> None:
    """Rich table for top-product order breakdown."""
    from rich.table import Table
    from rich import box as rich_box

    if not rows:
        console.print("[yellow]No product data found[/yellow]")
        return

    if output:
        format_output(rows, "json", output)
        return

    total_rev = sum(float(r.get("total_revenue_cny") or 0) for r in rows)

    t = Table(
        title=f"Top Products by Revenue  ({period})",
        box=rich_box.ROUNDED, header_style="bold cyan", show_lines=False,
    )
    t.add_column("#",             style="dim",   width=4)
    t.add_column("Product",                      max_width=28)
    t.add_column("Category",      style="dim",   max_width=16)
    t.add_column("Revenue (CNY)", justify="right", style="green")
    t.add_column("Rev Share",     justify="right")
    t.add_column("Qty",           justify="right")
    t.add_column("Orders",        justify="right")
    t.add_column("Buyers",        justify="right", style="cyan")
    t.add_column("Avg Price",     justify="right", style="dim")

    for i, r in enumerate(rows, 1):
        rev = float(r.get("total_revenue_cny") or 0)
        share = f"{rev / total_rev * 100:.1f}%" if total_rev else "-"
        t.add_row(
            str(i),
            str(r.get("product_name") or r.get("product_code") or "-"),
            str(r.get("category") or "-"),
            f"{rev:,.2f}",
            share,
            f"{int(r.get('total_quantity') or 0):,}",
            f"{int(r.get('order_count') or 0):,}",
            f"{int(r.get('unique_buyers') or 0):,}",
            f"{float(r.get('avg_price_cny') or 0):.2f}",
        )

    console.print()
    console.print(t)
    console.print(
        f"[dim]{len(rows)} products | Normal orders only (direction=0) | "
        f"Total revenue: {total_rev:,.2f} CNY[/dim]"
    )


def _orders_metrics_query(client, database: str, start_str: str, end_str: str) -> dict:
    """Run orders+repurchase metrics for a date range within an existing MCP session."""
    result = client.query(f"""
        SELECT
            COUNT(*)                      AS total_orders,
            SUM(total_amount)             AS total_sales,
            AVG(total_amount)             AS avg_order_value,
            COUNT(DISTINCT customer_code) AS unique_customers,
            COUNT(DISTINCT CASE WHEN order_cnt > 1 THEN customer_code END)
                                          AS repeat_customers
        FROM (
            SELECT customer_code, total_amount,
                   COUNT(*) OVER (PARTITION BY customer_code) AS order_cnt
            FROM dwd_v_order
            WHERE order_date BETWEEN '{start_str}' AND '{end_str}'
        ) t
    """, database=database)

    data = {"start": start_str, "end": end_str,
            "total_orders": 0, "total_sales": 0.0,
            "avg_order_value": 0.0, "unique_customers": 0,
            "repurchase_rate": 0.0}

    if isinstance(result, list) and result:
        row = result[0]
        data["total_orders"] = row.get("total_orders") or 0
        data["total_sales"] = float(row.get("total_sales") or 0)
        data["avg_order_value"] = float(row.get("avg_order_value") or 0)
        data["unique_customers"] = row.get("unique_customers") or 0
        repeat = row.get("repeat_customers") or 0
        if data["unique_customers"] > 0:
            data["repurchase_rate"] = round(
                repeat / data["unique_customers"] * 100, 1
            )

    return data


def _get_mcp_orders_compare_both(config, prev_start, prev_end, cur_start, cur_end):
    """Run orders metrics for both periods in a single MCP session."""
    for d in (prev_start, prev_end, cur_start, cur_end):
        s = d.isoformat()
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", s):
            raise ValueError(f"Invalid date: {s}")

    ps, pe = prev_start.isoformat(), prev_end.isoformat()
    cs, ce = cur_start.isoformat(), cur_end.isoformat()

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    database = config.mcp.database

    with MCPClient(mcp_config) as client:
        client.initialize()
        cur_data = _orders_metrics_query(client, database, cs, ce)
        prev_data = _orders_metrics_query(client, database, ps, pe)

    return cur_data, prev_data


def _get_mcp_orders_tool_payload(config, period: str, group_by: str = None, include_returns: bool = False) -> dict:
    """Fetch MCP tool payload for orders in a single session."""
    start_date, _ = _compute_date_range(period)
    if group_by:
        _validate_group_by(group_by)

    date_filter = _safe_date_filter("order_date", start_date)
    query_timeout = _mcp_query_timeout(period, grouped=bool(group_by) or include_returns)
    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    database = config.mcp.database

    with MCPClient(mcp_config) as client:
        client.initialize()
        if group_by == "product":
            from .products import _get_mcp_products
            result = {"orders": _get_mcp_products(config, period, by_category=False, limit=30)}
        elif group_by:
            result = {"orders": _get_mcp_orders_grouped_with_client(client, database, date_filter, group_by, query_timeout)}
        else:
            orders = _get_mcp_orders_overall_with_client(client, database, date_filter, query_timeout)
            orders["period"] = period
            result = {"orders": orders}

        if include_returns:
            result["returns"] = _get_mcp_order_returns_with_client(client, database, date_filter, period, query_timeout)

        return result


def _print_orders_compare(cur: dict, prev: dict, period: str) -> None:
    """Side-by-side period-over-period orders table."""
    from rich.table import Table
    from rich import box

    title = (
        f"Orders Compare — Current ({cur['start']} → {cur['end']}) "
        f"vs Previous ({prev['start']} → {prev['end']})"
    )
    tbl = Table(title=title, box=box.SIMPLE_HEAVY, show_header=True,
                header_style="bold cyan")
    tbl.add_column("Metric", style="bold")
    tbl.add_column(f"Current ({period})", justify="right")
    tbl.add_column("Previous Period", justify="right")
    tbl.add_column("Delta", justify="right")

    _print_compare_row(tbl, "Total Orders",
                       f"{cur['total_orders']:,}", f"{prev['total_orders']:,}",
                       cur["total_orders"], prev["total_orders"])
    _print_compare_row(tbl, "Unique Customers",
                       f"{cur['unique_customers']:,}", f"{prev['unique_customers']:,}",
                       cur["unique_customers"], prev["unique_customers"])
    _print_compare_row(tbl, "Total Sales",
                       _fmt_cny(cur["total_sales"]), _fmt_cny(prev["total_sales"]),
                       cur["total_sales"], prev["total_sales"])
    _print_compare_row(tbl, "Avg Order Value",
                       _fmt_cny(cur["avg_order_value"], 1), _fmt_cny(prev["avg_order_value"], 1),
                       cur["avg_order_value"], prev["avg_order_value"])
    _print_compare_row(tbl, "Repurchase Rate",
                       f"{cur['repurchase_rate']:.1f}%", f"{prev['repurchase_rate']:.1f}%",
                       cur["repurchase_rate"], prev["repurchase_rate"])

    console.print(tbl)
