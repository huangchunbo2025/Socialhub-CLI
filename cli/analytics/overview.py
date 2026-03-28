"""Overview analytics functions."""

import re

from rich.console import Console

from ..api.mcp_client import MCPClient, MCPConfig as MCPClientConfig, MCPError
from .common import (
    _compute_date_range,
    _mcp_query_timeout,
    _safe_date_filter,
)

console = Console()


def _get_mcp_overview(config, period: str) -> dict:
    """Get analytics overview from MCP database."""
    # Validate and compute safe date range
    start_date, _ = _compute_date_range(period)

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    database = config.mcp.database
    query_timeout = _mcp_query_timeout(period)

    with MCPClient(mcp_config) as client:
        client.initialize()

        # Query customer count
        customer_result = client.query(
            "SELECT COUNT(*) as total FROM dim_customer_info",
            database=database
        )
        total_customers = 0
        if isinstance(customer_result, list) and len(customer_result) > 0:
            total_customers = customer_result[0].get("total", 0)

        # Query overview data (with safe date filter)
        date_filter = _safe_date_filter("biz_date", start_date)
        overview_result = client.query(f"""
            SELECT
                SUM(add_custs_num) as new_customers,
                SUM(total_order_num) as total_orders,
                SUM(total_transaction_amt) as total_revenue
            FROM ads_das_business_overview_d
            {date_filter}
        """, database=database)

        new_customers = 0
        total_orders = 0
        total_revenue = 0.0

        if isinstance(overview_result, list) and len(overview_result) > 0:
            row = overview_result[0]
            new_customers = row.get("new_customers") or 0
            total_orders = row.get("total_orders") or 0
            total_revenue = float(row.get("total_revenue") or 0)

        # Query active customers (with safe date filter)
        order_date_filter = _safe_date_filter("order_date", start_date)
        active_result = client.query(f"""
            SELECT COUNT(DISTINCT customer_code) as active
            FROM dwd_v_order
            {order_date_filter}
        """, database=database)

        active_customers = 0
        if isinstance(active_result, list) and len(active_result) > 0:
            active_customers = active_result[0].get("active", 0)

        avg_order_value = total_revenue / total_orders if total_orders > 0 else 0

        return {
            "period": period,
            "total_customers": total_customers,
            "new_customers": new_customers,
            "active_customers": active_customers,
            "total_orders": total_orders,
            "total_revenue": total_revenue,
            "avg_order_value": avg_order_value,
        }


def _get_mcp_report_data(config) -> dict:
    """Get report data from MCP database."""
    # Use safe date computation (30d period)
    start_date, _ = _compute_date_range("30d")
    date_filter_biz = _safe_date_filter("biz_date", start_date)
    date_filter_order = _safe_date_filter("order_date", start_date)

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    database = config.mcp.database

    report_data = {}

    with MCPClient(mcp_config) as client:
        client.initialize()

        # Overview statistics
        customer_result = client.query(
            "SELECT COUNT(*) as total FROM dim_customer_info",
            database=database
        )
        total_customers = 0
        if isinstance(customer_result, list) and len(customer_result) > 0:
            total_customers = customer_result[0].get("total", 0)

        overview_result = client.query(f"""
            SELECT
                SUM(add_custs_num) as new_customers,
                SUM(total_order_num) as total_orders,
                SUM(total_transaction_amt) as total_revenue
            FROM ads_das_business_overview_d
            {date_filter_biz}
        """, database=database)

        new_customers = 0
        total_orders = 0
        total_revenue = 0.0

        if isinstance(overview_result, list) and len(overview_result) > 0:
            row = overview_result[0]
            new_customers = row.get("new_customers") or 0
            total_orders = row.get("total_orders") or 0
            total_revenue = float(row.get("total_revenue") or 0)

        avg_order_value = total_revenue / total_orders if total_orders > 0 else 0

        report_data['overview'] = {
            'total_customers': total_customers,
            'new_customers': new_customers,
            'total_orders': total_orders,
            'total_revenue': total_revenue,
            'avg_order_value': avg_order_value,
            'active_customers': total_customers,
        }

        # Customer type distribution
        type_result = client.query("""
            SELECT
                CASE
                    WHEN member_level IS NOT NULL AND member_level != '' THEN 'member'
                    ELSE 'registered'
                END as customer_type,
                COUNT(*) as count
            FROM dim_customer_info
            GROUP BY customer_type
        """, database=database)

        if isinstance(type_result, list) and len(type_result) > 0:
            report_data['customer_types'] = {row['customer_type']: row['count'] for row in type_result}

        # Top customers by spending (using safe date filter)
        # Build WHERE clause manually since column has table alias
        start_date_str = start_date.isoformat() if start_date else None
        order_where = f"WHERE o.order_date >= '{start_date_str}'" if start_date_str else ""
        top_result = client.query(f"""
            SELECT
                c.customer_name as name,
                SUM(o.payment_amount) as total_spent
            FROM dwd_v_order o
            JOIN dim_customer_info c ON o.customer_code = c.customer_code
            {order_where}
            GROUP BY c.customer_name
            ORDER BY total_spent DESC
            LIMIT 5
        """, database=database)

        if isinstance(top_result, list) and len(top_result) > 0:
            report_data['top_customers'] = {row['name']: float(row['total_spent'] or 0) for row in top_result}

        # Sales trend (last 10 days) - using safe date filter
        trend_result = client.query(f"""
            SELECT
                DATE(order_date) as date,
                SUM(payment_amount) as amount
            FROM dwd_v_order
            {date_filter_order}
            GROUP BY DATE(order_date)
            ORDER BY date
            LIMIT 10
        """, database=database)

        if isinstance(trend_result, list) and len(trend_result) > 0:
            report_data['sales_trend'] = {
                'dates': [str(row['date']) for row in trend_result],
                'values': [float(row['amount'] or 0) for row in trend_result],
            }

        # Recent customers
        customers_result = client.query("""
            SELECT
                customer_code as id,
                customer_name as name,
                CASE WHEN member_level IS NOT NULL THEN 'member' ELSE 'registered' END as customer_type,
                0 as total_orders,
                0 as total_spent,
                0 as points_balance
            FROM dim_customer_info
            LIMIT 20
        """, database=database)

        if isinstance(customers_result, list):
            report_data['customers'] = customers_result

        # Recent orders - using safe date filter
        orders_result = client.query(f"""
            SELECT
                order_code as order_id,
                customer_name,
                payment_amount as amount,
                channel,
                order_status as status,
                DATE(order_date) as order_date
            FROM dwd_v_order
            {date_filter_order}
            ORDER BY order_date DESC
            LIMIT 20
        """, database=database)

        if isinstance(orders_result, list):
            report_data['orders'] = orders_result

    return report_data


def _compute_compare_range(period: str):
    """Return (prev_start, prev_end, cur_start, cur_end) for period-over-period.

    The previous window is the same duration immediately before the current one.
    Only fixed-length periods are supported (not 'all').
    """
    from datetime import datetime, timedelta

    days_map = {"today": 1, "7d": 7, "30d": 30, "90d": 90, "365d": 365}
    days = days_map.get(period)
    if not days:
        raise ValueError(
            f"--compare not supported for period '{period}'. "
            "Use: today, 7d, 30d, 90d, 365d"
        )
    today = datetime.now().date()
    cur_start = today - timedelta(days=days)
    cur_end = today
    prev_end = cur_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)
    return prev_start, prev_end, cur_start, cur_end


def _overview_from_rows(start_str: str, end_str: str,
                        overview_result: list, active_result: list) -> dict:
    """Build overview dict from two query result lists."""
    new_customers = total_orders = 0
    total_revenue = 0.0
    if isinstance(overview_result, list) and overview_result:
        row = overview_result[0]
        new_customers = row.get("new_customers") or 0
        total_orders = row.get("total_orders") or 0
        total_revenue = float(row.get("total_revenue") or 0)
    active_customers = 0
    if isinstance(active_result, list) and active_result:
        active_customers = active_result[0].get("active", 0)
    avg_order_value = total_revenue / total_orders if total_orders > 0 else 0.0
    return {
        "start": start_str,
        "end": end_str,
        "new_customers": new_customers,
        "active_customers": active_customers,
        "total_orders": total_orders,
        "total_revenue": total_revenue,
        "avg_order_value": avg_order_value,
    }


def _get_mcp_overview_compare_both(config, prev_start, prev_end, cur_start, cur_end):
    """Run overview compare queries for both periods in a single MCP session.

    Optimized to reduce upstream round trips:
    - 1 query for overview aggregates of both windows
    - 1 query for active-buyer distinct counts of both windows
    """
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

        overview_rows = client.query(f"""
            SELECT
                CASE
                    WHEN biz_date BETWEEN '{cs}' AND '{ce}' THEN 'current'
                    WHEN biz_date BETWEEN '{ps}' AND '{pe}' THEN 'previous'
                END AS period_label,
                SUM(add_custs_num) AS new_customers,
                SUM(total_order_num) AS total_orders,
                SUM(total_transaction_amt) AS total_revenue
            FROM ads_das_business_overview_d
            WHERE (biz_date BETWEEN '{cs}' AND '{ce}')
               OR (biz_date BETWEEN '{ps}' AND '{pe}')
            GROUP BY period_label
        """, database=database)

        active_rows = client.query(f"""
            SELECT 'current' AS period_label, COUNT(DISTINCT customer_code) AS active
            FROM dwd_v_order
            WHERE order_date BETWEEN '{cs}' AND '{ce}'
            UNION ALL
            SELECT 'previous' AS period_label, COUNT(DISTINCT customer_code) AS active
            FROM dwd_v_order
            WHERE order_date BETWEEN '{ps}' AND '{pe}'
        """, database=database)

    overview_map = {
        row.get("period_label"): [row]
        for row in overview_rows
        if isinstance(row, dict) and row.get("period_label")
    } if isinstance(overview_rows, list) else {}

    active_map = {
        row.get("period_label"): [row]
        for row in active_rows
        if isinstance(row, dict) and row.get("period_label")
    } if isinstance(active_rows, list) else {}

    return (
        _overview_from_rows(cs, ce, overview_map.get("current", []), active_map.get("current", [])),
        _overview_from_rows(ps, pe, overview_map.get("previous", []), active_map.get("previous", [])),
    )


def _fmt_cny(fen, decimals: int = 0) -> str:
    """Format a fen (1/100 CNY) value as a ¥ string."""
    try:
        val = float(fen) / 100
        fmt = f"¥{{:,.{decimals}f}}"
        return fmt.format(val)
    except (TypeError, ValueError):
        return "¥0"


def _pct_delta(cur, prev) -> str:
    """Format delta as +/-X.X% or N/A."""
    try:
        cur, prev = float(cur), float(prev)
    except (TypeError, ValueError):
        return "N/A"
    if prev == 0:
        return "+∞" if cur > 0 else "—"
    delta = (cur - prev) / abs(prev) * 100
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:.1f}%"


def _color_delta(delta: str) -> str:
    """Return rich color for a delta string."""
    if delta.startswith("+"):
        return "green"
    if delta.startswith("-"):
        return "red"
    return ""


def _print_compare_row(tbl, label: str, c_val, p_val, c_raw, p_raw, fmt: str = "int"):
    """Add one row to a compare table with delta coloring."""
    delta = _pct_delta(c_raw, p_raw)
    color = _color_delta(delta)
    colored_delta = f"[{color}]{delta}[/{color}]" if color else delta
    tbl.add_row(label, str(c_val), str(p_val), colored_delta)


def _print_overview_compare(cur: dict, prev: dict, period: str) -> None:
    """Side-by-side period-over-period overview table."""
    from rich.table import Table
    from rich import box

    title = (
        f"Overview Compare — Current ({cur['start']} → {cur['end']}) "
        f"vs Previous ({prev['start']} → {prev['end']})"
    )
    tbl = Table(title=title, box=box.SIMPLE_HEAVY, show_header=True,
                header_style="bold cyan")
    tbl.add_column("Metric", style="bold")
    tbl.add_column(f"Current ({period})", justify="right")
    tbl.add_column("Previous Period", justify="right")
    tbl.add_column("Delta", justify="right")

    _print_compare_row(tbl, "New Customers",
                       f"{cur['new_customers']:,}", f"{prev['new_customers']:,}",
                       cur["new_customers"], prev["new_customers"])
    _print_compare_row(tbl, "Active Customers",
                       f"{cur['active_customers']:,}", f"{prev['active_customers']:,}",
                       cur["active_customers"], prev["active_customers"])
    _print_compare_row(tbl, "Total Orders",
                       f"{cur['total_orders']:,}", f"{prev['total_orders']:,}",
                       cur["total_orders"], prev["total_orders"])
    _print_compare_row(tbl, "Revenue (CNY)",
                       _fmt_cny(cur["total_revenue"]), _fmt_cny(prev["total_revenue"]),
                       cur["total_revenue"], prev["total_revenue"])
    _print_compare_row(tbl, "Avg Order Value",
                       _fmt_cny(cur["avg_order_value"], 1), _fmt_cny(prev["avg_order_value"], 1),
                       cur["avg_order_value"], prev["avg_order_value"])

    console.print(tbl)
