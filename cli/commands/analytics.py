"""Data analytics commands."""

import json
import re
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from ..api.client import APIError, SocialHubClient
from ..api.mcp_client import MCPClient, MCPConfig as MCPClientConfig, MCPError
from ..config import load_config
from ..local.processor import DataProcessor
from ..local.reader import LocalDataReader, read_customers_csv, read_orders_csv
from ..output.export import export_data, format_output, print_export_success
from ..output.table import (
    print_dataframe,
    print_dict,
    print_error,
    print_list,
    print_overview,
    print_retention_table,
)

app = typer.Typer(help="Data analytics commands")
console = Console()

# =============================================================================
# SQL Trace — monkey-patch MCPClient.query to capture SQL for --show-sql flag
# =============================================================================

from contextlib import contextmanager


@contextmanager
def _sql_trace_ctx():
    """Capture every MCPClient.query call within this context.

    Yields a list that accumulates {sql, database} entries.
    Restores the original method on exit (thread-safe for CLI use).
    """
    log: list[dict] = []
    _orig = MCPClient.query

    def _patched(self, sql: str, **kwargs):
        log.append({"sql": sql.strip(), "database": kwargs.get("database", "—")})
        return _orig(self, sql, **kwargs)

    MCPClient.query = _patched
    try:
        yield log
    finally:
        MCPClient.query = _orig


def _print_sql_trace(log: list[dict]) -> None:
    """Print captured SQL queries in a readable format."""
    from rich.syntax import Syntax

    if not log:
        console.print("[dim]No SQL queries captured.[/dim]")
        return

    console.print("\n[bold dim]── SQL Trace (" + str(len(log)) + " queries) ──────────────────────[/bold dim]")
    for i, entry in enumerate(log, 1):
        console.print(f"\n[dim]Query {i}  database={entry['database']}[/dim]")
        console.print(Syntax(entry["sql"], "sql", theme="monokai", word_wrap=True))


# =============================================================================
# SECURITY: Input Validation & SQL Safety
# =============================================================================

# Whitelist of valid period values
VALID_PERIODS = frozenset({"all", "today", "7d", "30d", "90d", "365d"})

# Whitelist of valid 'by' grouping options
VALID_GROUP_BY = frozenset({"channel", "province", "store", "date", "month", "product"})


def _validate_period(period: str) -> str:
    """Validate period parameter against whitelist.

    Returns the validated period or raises ValueError.
    """
    if period not in VALID_PERIODS:
        raise ValueError(f"Invalid period '{period}'. Must be one of: {', '.join(sorted(VALID_PERIODS))}")
    return period


def _validate_group_by(by: str) -> str:
    """Validate 'by' grouping parameter against whitelist."""
    if by and by not in VALID_GROUP_BY:
        raise ValueError(f"Invalid grouping '{by}'. Must be one of: {', '.join(sorted(VALID_GROUP_BY))}")
    return by


def _compute_date_range(period: str):
    """Compute safe date range from validated period.

    Returns (start_date, end_date) tuple. start_date is None for 'all' period.
    Dates are Python date objects, safe for SQL interpolation.
    """
    from datetime import datetime, timedelta

    period = _validate_period(period)
    today = datetime.now().date()

    if period == "all":
        return None, today

    days_map = {"today": 1, "7d": 7, "30d": 30, "90d": 90, "365d": 365}
    days = days_map.get(period, 365)
    start_date = today - timedelta(days=days)

    return start_date, today


def _mcp_query_timeout(period: str, grouped: bool = False) -> int:
    """Choose a safer MCP query timeout for larger analytics windows."""
    period = _validate_period(period)

    if period == "365d":
        return 180 if grouped else 120
    if period == "90d":
        return 120 if grouped else 90
    if period == "30d":
        return 90 if grouped else 60
    return 60


def _safe_date_filter(column: str, start_date, operator: str = ">=") -> str:
    """Build a safe SQL date filter clause.

    Args:
        column: Column name (must be alphanumeric/underscore only)
        start_date: Date object or None
        operator: Comparison operator (only >= and > allowed)

    Returns:
        SQL WHERE clause or empty string if no filter needed
    """
    if start_date is None:
        return ""

    # Validate column name (alphanumeric/underscore, optionally prefixed with table alias)
    import re
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)?$', column):
        raise ValueError(f"Invalid column name: {column}")

    # Validate operator
    if operator not in (">=", ">", "<=", "<", "="):
        raise ValueError(f"Invalid operator: {operator}")

    # Format date safely (Python date object -> ISO format string)
    date_str = start_date.isoformat() if hasattr(start_date, 'isoformat') else str(start_date)

    # Validate date format (YYYY-MM-DD)
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        raise ValueError(f"Invalid date format: {date_str}")

    return f"WHERE {column} {operator} '{date_str}'"


def _safe_date_between(column: str, start_date, end_date) -> str:
    """Build a safe SQL BETWEEN clause for dates.

    Args:
        column: Column name (must be alphanumeric/underscore only)
        start_date: Start date object
        end_date: End date object

    Returns:
        SQL WHERE clause with BETWEEN
    """
    import re

    # Validate column name (alphanumeric/underscore, optionally prefixed with table alias)
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)?$', column):
        raise ValueError(f"Invalid column name: {column}")

    # Format dates safely
    start_str = start_date.isoformat() if hasattr(start_date, 'isoformat') else str(start_date)
    end_str = end_date.isoformat() if hasattr(end_date, 'isoformat') else str(end_date)

    # Validate date formats
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', start_str):
        raise ValueError(f"Invalid start date format: {start_str}")
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', end_str):
        raise ValueError(f"Invalid end date format: {end_str}")

    return f"WHERE {column} BETWEEN '{start_str}' AND '{end_str}'"


def _validate_days_list(days_list: list) -> list:
    """Validate a list of day periods for retention analysis."""
    validated = []
    for d in days_list:
        if isinstance(d, int) and 1 <= d <= 365:
            validated.append(d)
        elif isinstance(d, str) and d.isdigit():
            val = int(d)
            if 1 <= val <= 365:
                validated.append(val)
    return validated


def get_data_source():
    """Get data source based on config mode."""
    config = load_config()
    return config.mode


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


def _get_mcp_customers(config, period: str, channel: str) -> dict:
    """Get customer analytics from MCP database.

    Tries dws_customer_base_metrics (DWS pre-aggregated) first;
    falls back to dim_customer_info + dwd_v_order on exception.
    """
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

        # --- DWS-first: dws_customer_base_metrics ---
        dws_ok = False
        total_customers = 0
        new_customers = 0
        active_customers = 0
        try:
            dws_result = client.query(f"""
                SELECT
                    COUNT(*)                                                              AS total_customers,
                    SUM(CASE WHEN first_order_date >= '{start_date}' THEN 1 ELSE 0 END) AS new_customers,
                    SUM(CASE WHEN last_order_date  >= '{start_date}' THEN 1 ELSE 0 END) AS active_customers
                FROM dws_customer_base_metrics
                WHERE identity_type = 1
            """, database=database, timeout=query_timeout)
            if isinstance(dws_result, list) and dws_result and dws_result[0].get("total_customers") is not None:
                row = dws_result[0]
                total_customers  = int(row.get("total_customers") or 0)
                new_customers    = int(row.get("new_customers") or 0)
                active_customers = int(row.get("active_customers") or 0)
                dws_ok = True
        except Exception:
            pass

        if not dws_ok:
            # Fallback: dim_customer_info for totals
            total_result = client.query(
                "SELECT COUNT(*) as total FROM dim_customer_info",
                database=database
            )
            if isinstance(total_result, list) and total_result:
                total_customers = total_result[0].get("total", 0)

            new_date_filter = _safe_date_filter("create_date", start_date)
            new_result = client.query(f"""
                SELECT COUNT(*) as new_count
                FROM dim_customer_info
                {new_date_filter}
            """, database=database, timeout=query_timeout)
            if isinstance(new_result, list) and new_result:
                new_customers = new_result[0].get("new_count", 0)

            active_date_filter = _safe_date_filter("order_date", start_date)
            active_result = client.query(f"""
                SELECT COUNT(DISTINCT customer_code) as active
                FROM dwd_v_order
                {active_date_filter}
            """, database=database, timeout=query_timeout)
            if isinstance(active_result, list) and active_result:
                active_customers = active_result[0].get("active", 0)

        # Customer by type (dim_customer_info, small query)
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

        by_type = {}
        if isinstance(type_result, list):
            for row in type_result:
                by_type[row.get("customer_type", "unknown")] = row.get("count", 0)

        return {
            "period": period,
            "total_customers": total_customers,
            "new_customers": new_customers,
            "active_customers": active_customers,
            "by_type": by_type,
            "dws_used": dws_ok,
        }


def _get_mcp_retention(config, days_list: list) -> list:
    """Get retention analytics from MCP database."""
    from datetime import datetime, timedelta
    import re

    # Validate days_list
    days_list = _validate_days_list(days_list)

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    database = config.mcp.database
    longest_window = max(days_list) if days_list else 30
    retention_period = "365d" if longest_window > 90 else "90d" if longest_window > 30 else "30d"
    query_timeout = _mcp_query_timeout(retention_period, grouped=True)

    today = datetime.now().date()
    results = []

    with MCPClient(mcp_config) as client:
        client.initialize()

        for period_days in days_list:
            # Get cohort: customers who made first purchase N days ago
            cohort_start = today - timedelta(days=period_days * 2)
            cohort_end = today - timedelta(days=period_days)

            # Safe date formatting
            cohort_start_str = cohort_start.isoformat()
            cohort_end_str = cohort_end.isoformat()

            # Validate date formats
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', cohort_start_str) or \
               not re.match(r'^\d{4}-\d{2}-\d{2}$', cohort_end_str):
                continue  # Skip invalid dates

            # Find customers in cohort (using validated dates)
            cohort_result = client.query(f"""
                SELECT COUNT(DISTINCT customer_code) as cohort_size
                FROM dwd_v_order
                WHERE order_date BETWEEN '{cohort_start_str}' AND '{cohort_end_str}'
            """, database=database, timeout=query_timeout)

            cohort_size = 0
            if isinstance(cohort_result, list) and len(cohort_result) > 0:
                cohort_size = cohort_result[0].get("cohort_size", 0)

            # Find retained customers (made another purchase after cohort period)
            retained_result = client.query(f"""
                SELECT COUNT(DISTINCT a.customer_code) as retained
                FROM dwd_v_order a
                WHERE a.order_date BETWEEN '{cohort_start_str}' AND '{cohort_end_str}'
                AND EXISTS (
                    SELECT 1 FROM dwd_v_order b
                    WHERE b.customer_code = a.customer_code
                    AND b.order_date > '{cohort_end_str}'
                )
            """, database=database, timeout=query_timeout)

            retained_count = 0
            if isinstance(retained_result, list) and len(retained_result) > 0:
                retained_count = retained_result[0].get("retained", 0)

            retention_rate = (retained_count / cohort_size * 100) if cohort_size > 0 else 0

            results.append({
                "period_days": period_days,
                "cohort_size": cohort_size,
                "retained_count": retained_count,
                "retention_rate": retention_rate,
            })

    return results


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
            """, database=database, timeout=query_timeout)
            # Return list directly for proper table display
            return result if isinstance(result, list) else []

        elif by == "province" or by == "store":
            # Use store_name for regional distribution (province data is not available)
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
            """, database=database, timeout=query_timeout)
            return result if isinstance(result, list) else []

        elif by == "product":
            return _get_mcp_products(config, period, by_category=False, limit=30)

        else:
            # Overall metrics
            result = client.query(f"""
                SELECT
                    COUNT(*) as total_orders,
                    SUM(total_amount) as total_sales,
                    AVG(total_amount) as avg_order_value,
                    COUNT(DISTINCT customer_code) as unique_customers
                FROM dwd_v_order
                {date_filter}
            """, database=database, timeout=query_timeout)

            data = {
                "period": period,
                "total_orders": 0,
                "total_sales": 0.0,
                "avg_order_value": 0.0,
                "unique_customers": 0,
            }

            if isinstance(result, list) and len(result) > 0:
                row = result[0]
                data["total_orders"] = row.get("total_orders") or 0
                data["total_sales"] = float(row.get("total_sales") or 0)
                data["avg_order_value"] = float(row.get("avg_order_value") or 0)
                data["unique_customers"] = row.get("unique_customers") or 0

            # Repurchase rate
            repurchase_result = client.query(f"""
                SELECT
                    COUNT(*) as repeat_customers
                FROM (
                    SELECT customer_code, COUNT(*) as order_cnt
                    FROM dwd_v_order
                    {date_filter}
                    GROUP BY customer_code
                    HAVING order_cnt > 1
                ) t
            """, database=database, timeout=query_timeout)

            if isinstance(repurchase_result, list) and len(repurchase_result) > 0:
                repeat_customers = repurchase_result[0].get("repeat_customers", 0)
                if data["unique_customers"] > 0:
                    data["repurchase_rate"] = round(repeat_customers / data["unique_customers"] * 100, 2)
                else:
                    data["repurchase_rate"] = 0

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


def _sanitize_string_input(value: str, max_length: int = 100) -> str:
    """Sanitize string input for SQL queries.

    Removes dangerous characters and limits length.
    """
    if not value:
        return ""
    import re
    # Remove any characters that could be used for SQL injection
    sanitized = re.sub(r"['\";\\%_\-\-]", "", str(value))
    return sanitized[:max_length]


def _get_mcp_campaigns(config, period: str, campaign_id: str = None, name: str = None) -> list:
    """Get campaign analytics from MCP database.

    Merges two sources:
    - ads_das_activity_channel_effect_d : funnel metrics (target/reach/click/convert)
    - ads_das_activity_analysis_d        : reward metrics (points/coupons/messages/participants)
    """
    import re

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
    import re

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

    t = Table(box=_rich_box_rounded(), header_style="bold cyan", show_lines=False)
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


def _rich_box_rounded():
    """Return rich ROUNDED box (avoids re-importing at multiple call sites)."""
    from rich import box as rich_box
    return rich_box.ROUNDED


def _get_mcp_points(config, period: str, expiring_days: int = 0, breakdown: bool = False) -> dict:
    """Get points analytics from MCP database.

    Args:
        expiring_days: when > 0, add expiration risk section
        breakdown: when True, add per-operation_type breakdown
    """
    # Validate and compute safe date range
    start_date, _ = _compute_date_range(period)
    date_filter = _safe_date_filter("create_time", start_date)

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    database = config.mcp.database

    # Validate expiring_days
    if not isinstance(expiring_days, int) or expiring_days < 0 or expiring_days > 3650:
        expiring_days = 0

    with MCPClient(mcp_config) as client:
        client.initialize()

        # --- Base summary: try dws_points_base_metrics_d first ---
        data = {
            "period": period,
            "total_earned": 0,
            "total_redeemed": 0,
            "active_members": 0,
            "total_transactions": 0,
            "dws_used": False,
        }

        dws_ok = False
        try:
            dws_result = client.query(f"""
                SELECT
                    SUM(earn_points)     AS total_earned,
                    SUM(consume_points)  AS total_redeemed,
                    SUM(earn_cnt)        AS total_transactions
                FROM dws_points_base_metrics_d
                WHERE biz_date >= '{start_date}'
            """, database=database)
            if isinstance(dws_result, list) and dws_result and dws_result[0].get("total_earned") is not None:
                row = dws_result[0]
                data["total_earned"]       = row.get("total_earned") or 0
                data["total_redeemed"]     = row.get("total_redeemed") or 0
                data["total_transactions"] = row.get("total_transactions") or 0
                data["dws_used"] = True
                dws_ok = True
        except Exception:
            pass

        if not dws_ok:
            result = client.query(f"""
                SELECT
                    SUM(CASE WHEN change_type = 'earn'   THEN points ELSE 0 END) AS total_earned,
                    SUM(CASE WHEN change_type = 'redeem' THEN points ELSE 0 END) AS total_redeemed,
                    COUNT(DISTINCT member_id) AS active_members,
                    COUNT(*) AS total_transactions
                FROM dwd_member_points_log
                {date_filter}
            """, database=database)

            if isinstance(result, list) and result:
                row = result[0]
                data["total_earned"]       = row.get("total_earned") or 0
                data["total_redeemed"]     = row.get("total_redeemed") or 0
                data["active_members"]     = row.get("active_members") or 0
                data["total_transactions"] = row.get("total_transactions") or 0

        # --- Expiration risk ---
        if expiring_days > 0:
            exp_result = client.query(f"""
                SELECT
                    SUM(points)              AS expiring_points,
                    COUNT(DISTINCT member_id) AS affected_members
                FROM dwd_member_points_log
                WHERE effective_end_time > NOW()
                  AND effective_end_time <= DATE_ADD(NOW(), INTERVAL {expiring_days} DAY)
                  AND change_type = 'earn'
            """, database=database)

            data["expiring_days"] = expiring_days
            data["expiring_points"] = 0
            data["expiring_affected_members"] = 0
            if isinstance(exp_result, list) and exp_result:
                data["expiring_points"]           = exp_result[0].get("expiring_points") or 0
                data["expiring_affected_members"] = exp_result[0].get("affected_members") or 0

        # --- Breakdown by operation_type ---
        if breakdown:
            # operation_type: 1=purchase 2=promotion 3=return 4=manual+ 5=manual- 6=behavior 8=redeem-gift 9=redeem-coupon 11=expired
            bd_result = client.query(f"""
                SELECT
                    operation_type,
                    SUM(points)              AS total_points,
                    COUNT(DISTINCT member_id) AS members,
                    COUNT(*)                 AS transactions
                FROM dwd_member_points_log
                {date_filter}
                GROUP BY operation_type
                ORDER BY total_points DESC
            """, database=database)

            op_labels = {
                "1": "Purchase earn", "2": "Promotion earn", "3": "Return deduct",
                "4": "Manual add",    "5": "Manual deduct",  "6": "Behavior earn",
                "8": "Redeem gift",   "9": "Redeem coupon",  "11": "Expired deduct",
            }
            breakdown_rows = []
            if isinstance(bd_result, list):
                for r in bd_result:
                    op = str(r.get("operation_type") or "")
                    breakdown_rows.append({
                        "operation_type": op,
                        "label":          op_labels.get(op, f"Type {op}"),
                        "total_points":   r.get("total_points") or 0,
                        "members":        r.get("members") or 0,
                        "transactions":   r.get("transactions") or 0,
                    })
            data["breakdown"] = breakdown_rows

        return data


def _print_points_mcp(data: dict) -> None:
    """Rich output for MCP points analytics."""
    from rich.panel import Panel
    from rich.table import Table
    from rich import box as rich_box

    earned   = int(data.get("total_earned") or 0)
    redeemed = int(data.get("total_redeemed") or 0)
    balance  = earned - redeemed
    redemption_rate = f"{redeemed/earned*100:.1f}%" if earned else "-"

    t = Table(show_header=False, box=rich_box.SIMPLE, padding=(0, 2))
    t.add_column("Metric", style="dim", min_width=22)
    t.add_column("Value", style="bold", justify="right", min_width=14)
    t.add_column("Note", style="dim")

    t.add_row("Total Earned",     f"{earned:,}",        f"Period: {data.get('period')}")
    t.add_row("Total Redeemed",   f"{redeemed:,}",      f"Redemption rate: {redemption_rate}")
    t.add_row("Net Balance",      f"{balance:,}",       "Earned minus redeemed")
    t.add_row("Active Members",   f"{int(data.get('active_members') or 0):,}", "Had point activity")
    t.add_row("Transactions",     f"{int(data.get('total_transactions') or 0):,}", "Total point events")

    # Expiration risk section
    if "expiring_days" in data:
        exp_pts = int(data.get("expiring_points") or 0)
        exp_mem = int(data.get("expiring_affected_members") or 0)
        exp_pct = f"{exp_pts/earned*100:.1f}%" if earned else "-"
        t.add_row("", "", "")
        t.add_row(
            f"[yellow]Expiring (next {data['expiring_days']}d)[/yellow]",
            f"[yellow]{exp_pts:,}[/yellow]",
            f"[yellow]{exp_mem:,} members affected ({exp_pct} of earned)[/yellow]",
        )

    console.print()
    console.print(Panel(t, title="[bold cyan]Points Analytics[/bold cyan]", border_style="cyan"))

    # Breakdown table
    if "breakdown" in data and data["breakdown"]:
        bt = Table(title="Points by Operation Type", box=rich_box.ROUNDED, header_style="bold cyan")
        bt.add_column("Type", style="dim")
        bt.add_column("Label")
        bt.add_column("Points", justify="right", style="bold")
        bt.add_column("Members", justify="right")
        bt.add_column("Transactions", justify="right")

        for r in data["breakdown"]:
            bt.add_row(
                str(r.get("operation_type") or "-"),
                str(r.get("label") or "-"),
                f"{int(r.get('total_points') or 0):,}",
                f"{int(r.get('members') or 0):,}",
                f"{int(r.get('transactions') or 0):,}",
            )
        console.print(bt)


def _get_mcp_points_at_risk(config, expiring_days: int, limit: int = 200) -> list:
    """List members whose earned points expire within N days.

    Cross-table (das_demoen):
      dwd_member_points_log  → earned points + effective_end_time
      dim_customer_info      → customer_name, mobilephone

    Returns one row per member_id, sorted by earliest_expiry ASC then
    expiring_points DESC so the most urgent cases appear first.
    """
    if not isinstance(expiring_days, int) or expiring_days < 1 or expiring_days > 3650:
        raise ValueError(f"expiring_days must be 1–3650, got {expiring_days}")
    safe_limit = max(1, min(int(limit), 1000))
    safe_days  = int(expiring_days)

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    database = config.mcp.database

    with MCPClient(mcp_config) as client:
        client.initialize()

        rows = client.query(f"""
            SELECT
                pl.member_id,
                c.customer_name,
                c.mobilephone,
                SUM(pl.points)               AS expiring_points,
                MIN(pl.effective_end_time)   AS earliest_expiry,
                COUNT(*)                     AS expiring_txn_count
            FROM dwd_member_points_log pl
            LEFT JOIN dim_customer_info c
                   ON c.customer_code = pl.member_id
            WHERE pl.change_type = 'earn'
              AND pl.effective_end_time > NOW()
              AND pl.effective_end_time <= DATE_ADD(NOW(), INTERVAL {safe_days} DAY)
            GROUP BY pl.member_id, c.customer_name, c.mobilephone
            HAVING expiring_points > 0
            ORDER BY earliest_expiry ASC, expiring_points DESC
            LIMIT {safe_limit}
        """, database=database)

    return rows if isinstance(rows, list) else []


def _print_points_at_risk(rows: list, expiring_days: int, output: str = None) -> None:
    """Rich display for at-risk points member list."""
    from rich.table import Table
    from rich import box as rich_box
    from rich.panel import Panel

    if not rows:
        console.print(f"[green]No members with points expiring in the next {expiring_days} days[/green]")
        return

    if output:
        format_output(rows, "json", output)
        return

    total_pts    = sum(int(r.get("expiring_points") or 0) for r in rows)
    total_members = len(rows)

    summary = (
        f"[bold]Window:[/bold] next [yellow]{expiring_days}[/yellow] days\n"
        f"[bold]At-risk members:[/bold]  [red]{total_members:,}[/red]\n"
        f"[bold]At-risk points:[/bold]   [red]{total_pts:,}[/red]"
        f"  (~{total_pts / 100:,.0f} CNY liability @ 0.01/pt)"
    )
    console.print(Panel(summary, title="[bold red]Points Expiry At-Risk[/bold red]", border_style="red"))

    t = Table(box=rich_box.ROUNDED, header_style="bold cyan", show_lines=False)
    t.add_column("#",               style="dim",  width=5)
    t.add_column("Member ID",       style="dim",  max_width=18)
    t.add_column("Name",                          max_width=16)
    t.add_column("Phone",           style="dim",  max_width=14)
    t.add_column("Expiring Pts",    justify="right", style="red")
    t.add_column("Earliest Expiry", justify="left",  style="yellow", max_width=12)
    t.add_column("Txns",            justify="right", style="dim")

    for i, r in enumerate(rows, 1):
        phone_raw = str(r.get("mobilephone") or "")
        phone_mask = phone_raw[:3] + "****" + phone_raw[-4:] if len(phone_raw) >= 8 else phone_raw
        t.add_row(
            str(i),
            str(r.get("member_id") or "-"),
            str(r.get("customer_name") or "-"),
            phone_mask,
            f"{int(r.get('expiring_points') or 0):,}",
            str(r.get("earliest_expiry") or "-")[:10],
            str(r.get("expiring_txn_count") or "-"),
        )

    console.print(t)
    console.print(
        f"[dim]{total_members} members | {total_pts:,} pts total | "
        f"Use --output to export for campaign targeting[/dim]"
    )


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


# ---------------------------------------------------------------------------
# Coupon lift analysis — coupon users vs non-users
# ---------------------------------------------------------------------------

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


@app.command("overview")
def analytics_overview(
    period: str = typer.Option("7d", "--period", "-p", help="Time period (today, 7d, 30d, 90d, 365d, ytd)"),
    from_date: Optional[str] = typer.Option(None, "--from", help="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = typer.Option(None, "--to", help="End date (YYYY-MM-DD)"),
    customer_type: str = typer.Option("all", "--type", "-t", help="Customer type (all, members, visitors)"),
    compare: bool = typer.Option(False, "--compare", help="Compare with previous period (MCP only)"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to file"),
) -> None:
    """Show analytics overview dashboard.

    Examples:
        sh analytics overview --period=30d
        sh analytics overview --period=30d --compare
    """
    config = load_config()

    if config.mode == "mcp":
        # MCP mode - query real database
        try:
            if compare:
                prev_start, prev_end, cur_start, cur_end = _compute_compare_range(period)
                cur_data, prev_data = _get_mcp_overview_compare_both(
                    config, prev_start, prev_end, cur_start, cur_end
                )
                _print_overview_compare(cur_data, prev_data, period)
                return
            data = _get_mcp_overview(config, period)
        except MCPError as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)
        except Exception as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)
    elif config.mode == "api":
        try:
            with SocialHubClient() as client:
                result = client.get_analytics_overview(
                    period=period,
                    from_date=from_date,
                    to_date=to_date,
                    customer_type=customer_type,
                )
                data = result.get("data", result)
        except APIError as e:
            print_error(f"API Error: {e.message}")
            raise typer.Exit(1)
    else:
        # Local mode
        try:
            reader = LocalDataReader(config.local.data_dir)
            customers_df = read_customers_csv("customers.csv", config.local.data_dir)
            orders_df = read_orders_csv("orders.csv", config.local.data_dir)

            data = DataProcessor.calculate_overview(
                customers_df, orders_df, period
            )
        except Exception as e:
            print_error(f"Local data error: {e}")
            raise typer.Exit(1)

    # Output
    if output:
        path = export_data(data if isinstance(data, list) else [data], output)
        print_export_success(path)
    elif format == "json":
        console.print_json(json.dumps(data, default=str))
    else:
        print_overview(data, title=f"Analytics Overview ({period})")


def _get_mcp_customer_source(config, period: str) -> list:
    """Query ads_das_custs_source_analysis_d for acquisition channel breakdown."""
    start_date, end_date = _compute_date_range(period)
    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    database = config.mcp.database
    with MCPClient(mcp_config) as client:
        client.initialize()
        rows = client.query(f"""
            SELECT
                source_channel,
                SUM(new_custs_cnt)                              AS new_customers,
                BITMAP_COUNT(BITMAP_UNION(custs_bitnum))        AS total_customers
            FROM ads_das_custs_source_analysis_d
            WHERE biz_date BETWEEN '{start_date}' AND '{end_date}'
            GROUP BY source_channel
            ORDER BY new_customers DESC
        """, database=database)
    result = []
    if isinstance(rows, list):
        total_new = sum(int(r.get("new_customers") or 0) for r in rows)
        for r in rows:
            nc = int(r.get("new_customers") or 0)
            tc = int(r.get("total_customers") or 0)
            result.append({
                "source_channel": r.get("source_channel") or "Unknown",
                "new_customers": nc,
                "total_customers": tc,
                "share_pct": round(nc / total_new * 100, 1) if total_new else 0,
            })
    return result


def _print_customer_source(rows: list, period: str) -> None:
    """Rich table for customer acquisition source breakdown."""
    from rich.table import Table
    from rich import box as rich_box
    from rich.panel import Panel

    if not rows:
        console.print("[yellow]No source data found in ads_das_custs_source_analysis_d[/yellow]")
        return

    t = Table(
        title=f"Customer Acquisition by Source  ({period})",
        box=rich_box.ROUNDED, header_style="bold cyan",
    )
    t.add_column("Source Channel", style="bold")
    t.add_column("New Customers",  justify="right", style="green")
    t.add_column("Share %",        justify="right")
    t.add_column("Total (Bitmap)", justify="right", style="cyan")
    t.add_column("Bar", no_wrap=True)

    max_new = max((r.get("new_customers", 0) for r in rows), default=1) or 1
    for r in rows:
        nc    = int(r.get("new_customers") or 0)
        pct   = r.get("share_pct", 0)
        bar   = "█" * int(nc / max_new * 20)
        pct_c = "green" if pct >= 20 else ("yellow" if pct >= 5 else "dim")
        t.add_row(
            str(r.get("source_channel") or "Unknown"),
            f"{nc:,}",
            f"[{pct_c}]{pct:.1f}%[/{pct_c}]",
            f"{int(r.get('total_customers') or 0):,}",
            f"[cyan]{bar}[/cyan]",
        )
    console.print(t)
    total = sum(int(r.get("new_customers") or 0) for r in rows)
    console.print(
        f"[dim]Total new customers across all sources: {total:,}  |  "
        f"Source: ads_das_custs_source_analysis_d[/dim]"
    )


def _get_mcp_customer_gender(config) -> list:
    """Query ads_das_custs_gender_distribution_d for gender distribution."""
    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    database = config.mcp.database
    with MCPClient(mcp_config) as client:
        client.initialize()
        rows = client.query("""
            SELECT
                gender,
                BITMAP_COUNT(BITMAP_UNION(custs_bitnum)) AS customer_count
            FROM ads_das_custs_gender_distribution_d
            WHERE biz_date = (SELECT MAX(biz_date) FROM ads_das_custs_gender_distribution_d)
            GROUP BY gender
            ORDER BY gender
        """, database=database)
    _GENDER = {0: "Unknown", 1: "Male", 2: "Female"}
    result = []
    if isinstance(rows, list):
        total = sum(int(r.get("customer_count") or 0) for r in rows)
        for r in rows:
            g   = int(r.get("gender") or 0)
            cnt = int(r.get("customer_count") or 0)
            result.append({
                "gender_code": g,
                "gender_label": _GENDER.get(g, f"Code {g}"),
                "customer_count": cnt,
                "share_pct": round(cnt / total * 100, 1) if total else 0,
            })
    return result


def _print_customer_gender(rows: list) -> None:
    """Rich table for gender distribution."""
    from rich.table import Table
    from rich import box as rich_box

    if not rows:
        console.print("[yellow]No gender data found in ads_das_custs_gender_distribution_d[/yellow]")
        return

    t = Table(title="Customer Gender Distribution", box=rich_box.ROUNDED, header_style="bold cyan")
    t.add_column("Gender",   style="bold")
    t.add_column("Count",    justify="right", style="cyan")
    t.add_column("Share %",  justify="right")
    t.add_column("Bar", no_wrap=True)

    total = sum(r.get("customer_count", 0) for r in rows)
    for r in rows:
        cnt  = int(r.get("customer_count") or 0)
        pct  = r.get("share_pct", 0)
        bar  = "█" * int(cnt / (total or 1) * 30)
        t.add_row(
            str(r.get("gender_label") or "-"),
            f"{cnt:,}",
            f"{pct:.1f}%",
            f"[cyan]{bar}[/cyan]",
        )
    console.print(t)
    console.print(
        f"[dim]Total: {total:,}  |  Source: ads_das_custs_gender_distribution_d (latest snapshot)[/dim]"
    )


@app.command("customers")
def analytics_customers(
    period: str = typer.Option("30d", "--period", "-p", help="Time period"),
    channel: str = typer.Option("all", "--channel", "-c", help="Channel filter (all, wechat, app, web, tmall)"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to file"),
    source: bool = typer.Option(False, "--source", "-s", help="Show customer acquisition source breakdown (MCP)"),
    gender: bool = typer.Option(False, "--gender", "-g", help="Show gender distribution (MCP)"),
) -> None:
    """Analyze customer metrics."""
    config = load_config()

    if source or gender:
        if config.mode != "mcp":
            print_error("--source and --gender require MCP mode")
            raise typer.Exit(1)
        if source:
            try:
                rows = _get_mcp_customer_source(config, period)
            except Exception as e:
                print_error(f"Error: {e}")
                raise typer.Exit(1)
            if output:
                format_output(rows, "json", output)
            else:
                _print_customer_source(rows, period)
        if gender:
            try:
                rows = _get_mcp_customer_gender(config)
            except Exception as e:
                print_error(f"Error: {e}")
                raise typer.Exit(1)
            if output:
                format_output(rows, "json", output)
            else:
                _print_customer_gender(rows)
        return

    if config.mode == "mcp":
        # MCP mode - query real database
        try:
            data = _get_mcp_customers(config, period, channel)
        except MCPError as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)
        except Exception as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)
    elif config.mode == "api":
        try:
            with SocialHubClient() as client:
                result = client.get_customer_analytics(period=period, channel=channel)
                data = result.get("data", result)
        except APIError as e:
            print_error(f"API Error: {e.message}")
            raise typer.Exit(1)
    else:
        # Local mode - simplified customer stats
        try:
            customers_df = read_customers_csv("customers.csv", config.local.data_dir)

            # Basic stats
            data = {
                "total_customers": len(customers_df),
                "by_type": customers_df["customer_type"].value_counts().to_dict() if "customer_type" in customers_df.columns else {},
            }

            if channel != "all" and "channels" in customers_df.columns:
                customers_df = customers_df[customers_df["channels"].str.contains(channel, case=False, na=False)]
                data["filtered_count"] = len(customers_df)
        except Exception as e:
            print_error(f"Local data error: {e}")
            raise typer.Exit(1)

    format_output(data, format, output)


@app.command("retention")
def analytics_retention(
    days: str = typer.Option("7,14,30", "--days", "-d", help="Retention periods in days (comma-separated)"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to file"),
) -> None:
    """Analyze customer retention rates."""
    # Parse days
    days_list = [int(d.strip()) for d in days.split(",")]

    config = load_config()

    if config.mode == "mcp":
        # MCP mode - query real database
        try:
            data = _get_mcp_retention(config, days_list)
        except MCPError as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)
        except Exception as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)
    elif config.mode == "api":
        try:
            with SocialHubClient() as client:
                result = client.get_retention_analytics(days=days_list)
                data = result.get("data", result)
        except APIError as e:
            print_error(f"API Error: {e.message}")
            raise typer.Exit(1)
    else:
        # Local mode
        try:
            orders_df = read_orders_csv("orders.csv", config.local.data_dir)
            data = DataProcessor.calculate_retention(orders_df, days_list)
        except Exception as e:
            print_error(f"Local data error: {e}")
            raise typer.Exit(1)

    if output:
        path = export_data(data, output)
        print_export_success(path)
    elif format == "json":
        console.print_json(json.dumps(data, default=str))
    else:
        print_retention_table(data)


@app.command("orders")
def analytics_orders(
    period: str = typer.Option("30d", "--period", "-p", help="Time period"),
    metric: str = typer.Option("sales", "--metric", "-m", help="Metric (sales, volume, atv)"),
    repurchase_rate: bool = typer.Option(False, "--repurchase-rate", help="Show repurchase rate"),
    by: Optional[str] = typer.Option(None, "--by", help="Group by (channel, province, product)"),
    returns: bool = typer.Option(False, "--returns", help="Show return/exchange rate analysis (direction field)"),
    compare: bool = typer.Option(False, "--compare", help="Compare with previous period (MCP only)"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to file"),
) -> None:
    """Analyze order metrics.

    Examples:
        sh analytics orders --period=30d
        sh analytics orders --period=30d --compare
        sh analytics orders --by=channel
        sh analytics orders --by=product
        sh analytics orders --returns
    """
    config = load_config()

    if config.mode == "mcp":
        # MCP mode - query real database
        try:
            if compare and not by and not returns:
                prev_start, prev_end, cur_start, cur_end = _compute_compare_range(period)
                cur_data, prev_data = _get_mcp_orders_compare_both(
                    config, prev_start, prev_end, cur_start, cur_end
                )
                _print_orders_compare(cur_data, prev_data, period)
                return
            if returns:
                data = _get_mcp_order_returns(config, period)
                if output:
                    format_output(data, "json", output)
                else:
                    _print_order_returns(data)
                return
            data = _get_mcp_orders(config, period, metric, by)
            # Product grouping gets its own rich display
            if by == "product" and isinstance(data, list):
                _print_orders_by_product(data, period, output)
                return
        except MCPError as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)
        except Exception as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)
    elif config.mode == "api":
        try:
            with SocialHubClient() as client:
                result = client.get_order_analytics(period=period, metric=metric)
                data = result.get("data", result)
        except APIError as e:
            print_error(f"API Error: {e.message}")
            raise typer.Exit(1)
    else:
        # Local mode
        try:
            orders_df = read_orders_csv("orders.csv", config.local.data_dir)

            if by == "channel":
                df = DataProcessor.group_by_channel(orders_df, period)
                format_output(df, format, output)
                return
            elif by == "province":
                df = DataProcessor.group_by_province(orders_df, period)
                format_output(df, format, output)
                return
            else:
                data = DataProcessor.calculate_order_metrics(orders_df, period, metric)
        except Exception as e:
            print_error(f"Local data error: {e}")
            raise typer.Exit(1)

    format_output(data, format, output)


@app.command("campaigns")
def analytics_campaigns(
    campaign_id: Optional[str] = typer.Option(None, "--id", help="Campaign ID"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Campaign name filter"),
    period: str = typer.Option("30d", "--period", "-p", help="Time period"),
    funnel: bool = typer.Option(False, "--funnel", help="Show conversion funnel"),
    detail: bool = typer.Option(False, "--detail", help="Deep analysis for a single campaign (requires --id)"),
    audience: bool = typer.Option(False, "--audience", help="Tier audience breakdown via BITMAP_AND (requires --id)"),
    campaign_roi: bool = typer.Option(False, "--roi", help="Attributed GMV per campaign (participant orders within window)"),
    window: int = typer.Option(30, "--window", "-w", help="Attribution window days for --roi (1-60)"),
    canvas: Optional[str] = typer.Option(None, "--canvas", help="Canvas journey funnel for a canvas campaign ID"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to file"),
) -> None:
    """Analyze marketing campaign performance.

    Examples:
        sh analytics campaigns --period=30d
        sh analytics campaigns --id ACT001 --detail
        sh analytics campaigns --id ACT001 --audience
        sh analytics campaigns --name=spring --funnel
        sh analytics campaigns --roi --period=90d
        sh analytics campaigns --canvas ACT_CANVAS_001
    """
    config = load_config()

    if config.mode == "mcp":
        # MCP mode - query real database
        try:
            if canvas:
                canvas_data = _get_mcp_canvas(config, canvas)
                if output:
                    format_output(canvas_data, "json", output,
                                  title=f"Canvas Journey — {canvas}")
                    console.print(f"[green]Exported to {output}[/green]")
                else:
                    _print_canvas(canvas_data)
                return

            if campaign_roi:
                roi_rows = _get_mcp_campaign_roi(config, period, window)
                if output:
                    format_output(roi_rows, "json", output)
                else:
                    _print_campaign_roi(roi_rows, period, window)
                return
            # --audience: BITMAP_AND campaign participants × tier bitmaps
            if audience:
                if not campaign_id:
                    print_error("--audience requires --id <campaign_id>")
                    raise typer.Exit(1)
                aud_rows = _get_mcp_campaign_audience(config, campaign_id)
                if output:
                    format_output(aud_rows, "json", output)
                else:
                    _print_campaign_audience(aud_rows, campaign_id)
                return

            # --detail requires --id
            if detail:
                if not campaign_id:
                    print_error("--detail requires --id <campaign_id>")
                    raise typer.Exit(1)
                detail_data = _get_mcp_campaign_detail(config, campaign_id)
                if output:
                    format_output(detail_data, "json", output)
                else:
                    _print_campaign_detail(detail_data)
                return
            data = _get_mcp_campaigns(config, period, campaign_id, name)
        except MCPError as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)
        except Exception as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)
    elif config.mode == "api":
        try:
            with SocialHubClient() as client:
                result = client.get_campaign_analytics(
                    campaign_id=campaign_id,
                    name=name,
                    period=period,
                )
                data = result.get("data", result)
        except APIError as e:
            print_error(f"API Error: {e.message}")
            raise typer.Exit(1)
    else:
        # Local mode - not supported without campaign data
        print_error("Campaign analytics requires API or MCP mode")
        raise typer.Exit(1)

    if config.mode == "mcp" and isinstance(data, list):
        _print_campaigns_mcp(data, output)
    elif funnel and isinstance(data, dict):
        funnel_data = {
            "Target":    f"{data.get('target_count', 0):,}",
            "Reached":   f"{data.get('reached_count', 0):,}",
            "Opened":    f"{data.get('opened_count', 0):,}",
            "Clicked":   f"{data.get('clicked_count', 0):,}",
            "Converted": f"{data.get('converted_count', 0):,}",
        }
        print_dict(funnel_data, title=f"Campaign Funnel: {data.get('campaign_name', 'Unknown')}")
    else:
        format_output(data, format, output)


@app.command("points")
def analytics_points(
    period: str = typer.Option("30d", "--period", "-p", help="Time period: 7d/30d/90d/365d"),
    expiring_days: int = typer.Option(0, "--expiring-days", help="Show points expiring within N days (0=off)"),
    breakdown: bool = typer.Option(False, "--breakdown", help="Break down by operation type"),
    at_risk_members: bool = typer.Option(False, "--at-risk-members", help="List members with points expiring (requires --expiring-days)"),
    daily_trend: bool = typer.Option(False, "--daily-trend", help="Show day-by-day earn vs redeem trend"),
    limit: int = typer.Option(200, "--limit", "-n", help="Max members for --at-risk-members"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to file"),
) -> None:
    """Analyze points program metrics.

    Examples:
        sh analytics points --period=30d
        sh analytics points --daily-trend --period=30d
        sh analytics points --expiring-days=30
        sh analytics points --expiring-days=30 --at-risk-members
        sh analytics points --expiring-days=30 --at-risk-members --output=at_risk.json
        sh analytics points --breakdown
    """
    config = load_config()

    if config.mode == "mcp":
        # --daily-trend: day-by-day earn vs redeem
        if daily_trend:
            try:
                rows = _get_mcp_points_daily_trend(config, period)
            except (MCPError, Exception) as e:
                print_error(f"Error: {e}")
                raise typer.Exit(1)
            if output:
                format_output(rows, "json", output)
            else:
                _print_points_daily_trend(rows, period)
            return

        # --at-risk-members: produce exportable member list
        if at_risk_members:
            if expiring_days < 1:
                print_error("--at-risk-members requires --expiring-days N (e.g. --expiring-days=30)")
                raise typer.Exit(1)
            try:
                rows = _get_mcp_points_at_risk(config, expiring_days, limit)
            except (MCPError, ValueError) as e:
                print_error(f"Error: {e}")
                raise typer.Exit(1)
            except Exception as e:
                print_error(f"Error: {e}")
                raise typer.Exit(1)
            _print_points_at_risk(rows, expiring_days, output)
            return

        try:
            data = _get_mcp_points(config, period, expiring_days, breakdown)
        except MCPError as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)
        except Exception as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)

        if format == "json" or output:
            format_output(data, format, output)
            return

        _print_points_mcp(data)

    elif config.mode == "api":
        try:
            with SocialHubClient() as client:
                result = client.get("/api/v1/analytics/points", params={"period": period})
                data = result.get("data", result)
        except APIError as e:
            print_error(f"API Error: {e.message}")
            raise typer.Exit(1)
        format_output(data, format, output)
    else:
        print_error("Points analytics requires API or MCP mode")
        raise typer.Exit(1)


@app.command("coupons")
def analytics_coupons(
    period: str = typer.Option("30d", "--period", "-p", help="Time period: 7d/30d/90d/365d"),
    roi: bool = typer.Option(False, "--roi", help="Show face-value ROI and per-rule breakdown"),
    lift: bool = typer.Option(False, "--lift", help="Coupon lift analysis: compare coupon users vs non-users"),
    by_rule: bool = typer.Option(False, "--by-rule", help="Per-rule GMV attribution and ROI"),
    anomaly: bool = typer.Option(False, "--anomaly", help="Detect abnormal daily redeem volume (mean+2sigma)"),
    lookback: int = typer.Option(30, "--lookback", "-l", help="Baseline days for anomaly detection"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max rules for --by-rule (1-200)"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to file"),
) -> None:
    """Analyze coupon usage and redemption value.

    Examples:
        sh analytics coupons --period=30d
        sh analytics coupons --roi
        sh analytics coupons --lift --period=30d
        sh analytics coupons --by-rule --period=90d
        sh analytics coupons --anomaly --lookback=30
    """
    config = load_config()

    if config.mode == "mcp":
        try:
            if anomaly:
                anom_data = _get_mcp_coupon_anomaly(config, lookback, 7)
                if output:
                    format_output(anom_data, "json", output, title="Coupon Anomaly")
                    console.print(f"[green]Exported to {output}[/green]")
                else:
                    _print_coupon_anomaly(anom_data)
                return
            if by_rule:
                rule_rows = _get_mcp_coupons_by_rule(config, period, limit)
                _print_coupons_by_rule(rule_rows, period, output)
                return
            if lift:
                lift_data = _get_mcp_coupon_lift(config, period)
                if output:
                    format_output(lift_data, "json", output)
                else:
                    _print_coupon_lift(lift_data)
                return
            data = _get_mcp_coupons(config, period, roi)
        except MCPError as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)
        except Exception as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)

        if format == "json" or output:
            format_output(data, format, output)
            return

        _print_coupons_mcp(data, roi)

    elif config.mode == "api":
        try:
            with SocialHubClient() as client:
                params = {"period": period}
                if roi:
                    params["include_roi"] = "true"
                result = client.get("/api/v1/analytics/coupons", params=params)
                data = result.get("data", result)
        except APIError as e:
            print_error(f"API Error: {e.message}")
            raise typer.Exit(1)
        format_output(data, format, output)
    else:
        print_error("Coupon analytics requires API or MCP mode")
        raise typer.Exit(1)


@app.command("report")
def generate_analytics_report(
    topic: str = typer.Option("客户分析报告", "--topic", "-t", help="Report topic"),
    output: str = typer.Option("analytics_report.md", "--output", "-o", help="Output file path"),
    period: str = typer.Option("365d", "--period", "-p", help="Data period (7d, 30d, 90d, 365d)"),
    formats: str = typer.Option("all", "--formats", "-f", help="Output formats (md, html, pdf, all)"),
) -> None:
    """Generate data-driven analytics report with insights.

    This command fetches real data from MCP and generates a comprehensive
    report with visualizations and strategic recommendations.

    Examples:
        sh analytics report --topic="客户分布分析" --output=report.md
        sh analytics report --topic="市场拓展策略" --period=90d --formats=all
    """
    import json
    import re
    import sys
    from datetime import timedelta

    config = load_config()

    if config.mode != "mcp":
        print_error("Analytics report requires MCP mode. Use: sh config set mode mcp")
        raise typer.Exit(1)

    console.print("[dim]Fetching analytics data...[/dim]")

    # Collect all data
    data = {}

    try:
        # 1. Overview data
        data.update(_get_mcp_overview(config, period))

        # 2. Channel data
        mcp_config = MCPClientConfig(
            sse_url=config.mcp.sse_url,
            post_url=config.mcp.post_url,
            tenant_id=config.mcp.tenant_id,
        )
        database = config.mcp.database

        # Use safe date computation
        start_date, today = _compute_date_range(period)

        # Build safe date filter
        date_filter = _safe_date_filter("order_date", start_date)

        with MCPClient(mcp_config) as client:
            client.initialize()

            # Channel distribution (using source_name as channel)
            channel_result = client.query(f"""
                SELECT
                    COALESCE(source_name, 'unknown') as channel,
                    COUNT(*) as order_count,
                    SUM(total_amount) as total_sales,
                    AVG(total_amount) as avg_order_value
                FROM dwd_v_order
                {date_filter}
                GROUP BY source_name
                ORDER BY total_sales DESC
                LIMIT 15
            """, database=database)
            data['channels'] = channel_result if channel_result else []

            # Retention data
            retention_result = []
            for days_period in [7, 30, 90]:
                period_start = today - timedelta(days=days_period)
                ret_result = client.query(f"""
                    SELECT
                        COUNT(DISTINCT CASE WHEN first_order_date >= '{period_start}' THEN customer_code END) as cohort_size,
                        COUNT(DISTINCT CASE WHEN first_order_date >= '{period_start}' AND order_count > 1 THEN customer_code END) as retained_count
                    FROM (
                        SELECT
                            customer_code,
                            MIN(order_date) as first_order_date,
                            COUNT(*) as order_count
                        FROM dwd_v_order
                        GROUP BY customer_code
                    ) t
                """, database=database)

                if ret_result and len(ret_result) > 0:
                    cohort_size = ret_result[0].get("cohort_size", 0) or 0
                    retained = ret_result[0].get("retained_count", 0) or 0
                    rate = (retained / cohort_size * 100) if cohort_size > 0 else 0
                    retention_result.append({
                        "period_days": days_period,
                        "cohort_size": cohort_size,
                        "retained_count": retained,
                        "retention_rate": rate
                    })
            data['retention'] = retention_result

        console.print(f"[dim]Data fetched: {data.get('total_customers', 0):,} customers, {data.get('total_orders', 0):,} orders[/dim]")

        # Generate report using the skill
        console.print("[dim]Generating report...[/dim]")

        # Import and use the report generator
        sys.path.insert(0, str(Path(__file__).parent.parent / 'skills' / 'store' / 'report-generator'))
        import importlib
        try:
            import main as report_main
            importlib.reload(report_main)

            result = report_main.generate_data_report(
                topic=topic,
                output=output,
                period=period,
                formats=formats,
                data_json=json.dumps(data)
            )

            console.print(f"\n[bold green]Report generated successfully![/bold green]")
            console.print(result)

        except Exception as e:
            print_error(f"Error generating report: {e}")
            raise typer.Exit(1)

    except MCPError as e:
        print_error(f"MCP Error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Error: {e}")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Product order analytics — display helper
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Loyalty program analytics
# ---------------------------------------------------------------------------

def _get_mcp_loyalty(config) -> dict:
    """Loyalty program overview: enrollment, tier distribution, points liability.

    Joins (dts_demoen):
      vdm_t_loyalty_program
      vdm_t_member          (by loyalty_program_code)
      vdm_t_points_account  (by card_no = member_code)
    """
    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    src_db = "dts_demoen"

    with MCPClient(mcp_config) as client:
        client.initialize()

        # 1. Program list
        programs = client.query(
            "SELECT code, name, status FROM vdm_t_loyalty_program WHERE delete_flag = 0 ORDER BY code",
            database=src_db,
        )

        # 2. Member count + tier distribution per program
        tier_dist = client.query("""
            SELECT
                loyalty_program_code,
                tier_code,
                COUNT(*) AS member_count
            FROM vdm_t_member
            WHERE delete_flag = 0
            GROUP BY loyalty_program_code, tier_code
            ORDER BY loyalty_program_code, member_count DESC
        """, database=src_db)

        # 3. Points liability per program
        liability = client.query("""
            SELECT
                m.loyalty_program_code,
                COUNT(DISTINCT m.card_no)  AS accounts_with_points,
                SUM(pa.available_points)   AS available_points,
                SUM(pa.transit_points)     AS transit_points,
                SUM(pa.accumulative_points) AS accumulative_points,
                SUM(pa.used_points)        AS used_points,
                SUM(pa.expired_points)     AS expired_points
            FROM vdm_t_member m
            JOIN vdm_t_points_account pa
              ON pa.member_code = m.card_no
             AND pa.delete_flag = 0
            WHERE m.delete_flag = 0
            GROUP BY m.loyalty_program_code
        """, database=src_db)

    # Build lookup maps
    tier_map = {}
    if isinstance(tier_dist, list):
        for r in tier_dist:
            prog = str(r.get("loyalty_program_code") or "")
            tier_map.setdefault(prog, []).append({
                "tier_code": r.get("tier_code") or "-",
                "member_count": int(r.get("member_count") or 0),
            })

    liab_map = {}
    if isinstance(liability, list):
        for r in liability:
            prog = str(r.get("loyalty_program_code") or "")
            liab_map[prog] = r

    prog_list = []
    if isinstance(programs, list):
        for p in programs:
            code = str(p.get("code") or "")
            tiers = tier_map.get(code, [])
            total_members = sum(t["member_count"] for t in tiers)
            liab = liab_map.get(code, {})
            prog_list.append({
                "code": code,
                "name": p.get("name") or code,
                "status": p.get("status") or "-",
                "total_members": total_members,
                "tiers": tiers,
                "available_points": int(liab.get("available_points") or 0),
                "transit_points": int(liab.get("transit_points") or 0),
                "accumulative_points": int(liab.get("accumulative_points") or 0),
                "used_points": int(liab.get("used_points") or 0),
                "expired_points": int(liab.get("expired_points") or 0),
                "accounts_with_points": int(liab.get("accounts_with_points") or 0),
            })

    grand_members = sum(p["total_members"] for p in prog_list)
    grand_avail   = sum(p["available_points"] for p in prog_list)
    grand_transit = sum(p["transit_points"] for p in prog_list)
    grand_accum   = sum(p["accumulative_points"] for p in prog_list)

    return {
        "programs": prog_list,
        "totals": {
            "programs": len(prog_list),
            "members": grand_members,
            "available_points": grand_avail,
            "transit_points": grand_transit,
            "accumulative_points": grand_accum,
        },
    }


def _print_loyalty_mcp(data: dict, output: str = None) -> None:
    """Rich display for loyalty program overview."""
    from rich.table import Table
    from rich import box as rich_box
    from rich.panel import Panel

    if output:
        format_output(data, "json", output)
        return

    programs = data.get("programs", [])
    totals   = data.get("totals", {})

    if not programs:
        console.print("[yellow]No loyalty program data found[/yellow]")
        return

    avail_pts   = totals.get("available_points", 0)
    transit_pts = totals.get("transit_points", 0)
    liability_cny = (avail_pts + transit_pts) / 100.0

    summary = (
        f"[bold]Total Programs:[/bold]  {totals.get('programs', 0)}\n"
        f"[bold]Total Members:[/bold]   {totals.get('members', 0):,}\n"
        f"[bold]Available Points:[/bold]  [green]{avail_pts:,}[/green]"
        f"  (~{liability_cny:,.0f} CNY liability @ 0.01/pt)\n"
        f"[bold]In Transit:[/bold]       {transit_pts:,}\n"
        f"[bold]All-time Issued:[/bold]  {totals.get('accumulative_points', 0):,}"
    )
    console.print(Panel(summary, title="[bold]Loyalty Program Overview[/bold]", border_style="yellow"))

    for p in programs:
        status_style = "green" if str(p.get("status")) in ("1", "active", "enabled") else "dim"
        prog_header = (
            f"[bold]{p.get('name')}[/bold]  [dim]{p.get('code')}[/dim]  "
            f"[{status_style}]{p.get('status')}[/{status_style}]\n"
            f"Members: {p.get('total_members', 0):,}   "
            f"Accounts w/ points: {p.get('accounts_with_points', 0):,}"
        )
        console.print(Panel(prog_header, border_style="dim", padding=(0, 2)))

        tiers = p.get("tiers", [])
        if tiers:
            tt = Table(box=rich_box.SIMPLE, header_style="bold dim")
            tt.add_column("Tier",    style="yellow")
            tt.add_column("Members", justify="right")
            tt.add_column("Share",   justify="right")
            total_m = p.get("total_members") or 1
            for tier in tiers:
                cnt = tier.get("member_count", 0)
                tt.add_row(
                    str(tier.get("tier_code") or "-"),
                    f"{cnt:,}",
                    f"{cnt / total_m * 100:.1f}%",
                )
            console.print(tt)

        avail   = p.get("available_points", 0)
        transit = p.get("transit_points", 0)
        used    = p.get("used_points", 0)
        expired = p.get("expired_points", 0)
        accum   = p.get("accumulative_points", 0)
        redemption_rate = round(used / accum * 100, 1) if accum else 0
        console.print(
            f"  [dim]Points — Available: [green]{avail:,}[/green]  "
            f"In-transit: {transit:,}  "
            f"Used: {used:,}  "
            f"Expired: [red]{expired:,}[/red]  "
            f"Redemption rate: {redemption_rate}%[/dim]\n"
        )


@app.command("loyalty")
def analytics_loyalty(
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to JSON file"),
) -> None:
    """Loyalty program overview: enrollment, tier distribution, points liability (MCP).

    Joins vdm_t_loyalty_program, vdm_t_member, vdm_t_points_account in
    dts_demoen to show per-program membership, tier breakdown, and full
    points liability (available + in-transit).

    Examples:
        sh analytics loyalty
        sh analytics loyalty --output=loyalty.json
    """
    config = load_config()

    if config.mode != "mcp":
        print_error("analytics loyalty requires MCP mode")
        raise typer.Exit(1)

    try:
        data = _get_mcp_loyalty(config)
    except MCPError as e:
        print_error(f"MCP Error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Error: {e}")
        raise typer.Exit(1)

    _print_loyalty_mcp(data, output)


# =============================================================================
# --compare: Period-over-Period Comparison
# =============================================================================

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
    """Run overview queries for both periods in a single MCP session."""
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

        cur_ov = client.query(f"""
            SELECT SUM(add_custs_num) AS new_customers,
                   SUM(total_order_num) AS total_orders,
                   SUM(total_transaction_amt) AS total_revenue
            FROM ads_das_business_overview_d
            WHERE biz_date BETWEEN '{cs}' AND '{ce}'
        """, database=database)
        cur_act = client.query(f"""
            SELECT COUNT(DISTINCT customer_code) AS active
            FROM dwd_v_order WHERE order_date BETWEEN '{cs}' AND '{ce}'
        """, database=database)
        prev_ov = client.query(f"""
            SELECT SUM(add_custs_num) AS new_customers,
                   SUM(total_order_num) AS total_orders,
                   SUM(total_transaction_amt) AS total_revenue
            FROM ads_das_business_overview_d
            WHERE biz_date BETWEEN '{ps}' AND '{pe}'
        """, database=database)
        prev_act = client.query(f"""
            SELECT COUNT(DISTINCT customer_code) AS active
            FROM dwd_v_order WHERE order_date BETWEEN '{ps}' AND '{pe}'
        """, database=database)

    return (
        _overview_from_rows(cs, ce, cur_ov, cur_act),
        _overview_from_rows(ps, pe, prev_ov, prev_act),
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


# =============================================================================
# analytics funnel — Customer Lifecycle Funnel
# =============================================================================

def _get_mcp_funnel(config, period: str = "30d") -> dict:
    """Customer lifecycle funnel: New → First Purchase → Repeat → Loyal → At-Risk → Churned.

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
    )
    database = config.mcp.database

    from datetime import datetime, timedelta
    today = datetime.now().date()
    at_risk_cutoff = (today - timedelta(days=60)).isoformat()
    at_risk_active = (today - timedelta(days=120)).isoformat()
    churned_cutoff = (today - timedelta(days=180)).isoformat()

    with MCPClient(mcp_config) as client:
        client.initialize()

        # Stage 1: New customers in period
        new_result = client.query(f"""
            SELECT SUM(add_custs_num) AS new_customers
            FROM ads_das_business_overview_d
            WHERE biz_date BETWEEN '{start_str}' AND '{end_str}'
        """, database=database)
        new_customers = 0
        if isinstance(new_result, list) and new_result:
            new_customers = new_result[0].get("new_customers") or 0

        # Stage 2 & 3: First-time vs repeat purchasers in period
        purchase_result = client.query(f"""
            SELECT
                COUNT(CASE WHEN order_cnt = 1 THEN 1 END) AS first_time_buyers,
                COUNT(CASE WHEN order_cnt >= 2 THEN 1 END) AS repeat_buyers
            FROM (
                SELECT customer_code, COUNT(*) AS order_cnt
                FROM dwd_v_order
                WHERE order_date BETWEEN '{start_str}' AND '{end_str}'
                GROUP BY customer_code
            ) t
        """, database=database)
        first_time_buyers = repeat_buyers = 0
        if isinstance(purchase_result, list) and purchase_result:
            row = purchase_result[0]
            first_time_buyers = row.get("first_time_buyers") or 0
            repeat_buyers = row.get("repeat_buyers") or 0

        # Stage 4: Loyal customers (5+ total orders ever)
        loyal_result = client.query("""
            SELECT COUNT(*) AS loyal_customers
            FROM (
                SELECT customer_code
                FROM dwd_v_order
                GROUP BY customer_code
                HAVING COUNT(*) >= 5
            ) t
        """, database=database)
        loyal_customers = 0
        if isinstance(loyal_result, list) and loyal_result:
            loyal_customers = loyal_result[0].get("loyal_customers") or 0

        # Stage 5: At-risk (ordered 60-120 days ago, nothing in last 60 days)
        at_risk_result = client.query(f"""
            SELECT COUNT(DISTINCT customer_code) AS at_risk
            FROM dwd_v_order
            WHERE order_date BETWEEN '{at_risk_active}' AND '{at_risk_cutoff}'
              AND customer_code NOT IN (
                  SELECT DISTINCT customer_code
                  FROM dwd_v_order
                  WHERE order_date > '{at_risk_cutoff}'
              )
        """, database=database)
        at_risk = 0
        if isinstance(at_risk_result, list) and at_risk_result:
            at_risk = at_risk_result[0].get("at_risk") or 0

        # Stage 6: Churned (had orders before 180 days ago, nothing since)
        churned_result = client.query(f"""
            SELECT COUNT(DISTINCT customer_code) AS churned
            FROM dwd_v_order
            WHERE order_date < '{churned_cutoff}'
              AND customer_code NOT IN (
                  SELECT DISTINCT customer_code
                  FROM dwd_v_order
                  WHERE order_date >= '{churned_cutoff}'
              )
        """, database=database)
        churned = 0
        if isinstance(churned_result, list) and churned_result:
            churned = churned_result[0].get("churned") or 0

        # Total active base for conversion reference
        total_result = client.query(
            "SELECT COUNT(*) AS total FROM dim_customer_info",
            database=database
        )
        total_customers = 0
        if isinstance(total_result, list) and total_result:
            total_customers = total_result[0].get("total") or 0

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
    from rich.table import Table
    from rich import box
    from rich.panel import Panel

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


# =============================================================================
# analytics diagnose — AI-Synthesized Business Diagnosis
# =============================================================================

def _get_mcp_diagnose_context(config) -> dict:
    """Gather key metrics from multiple tables for AI diagnosis."""
    from datetime import datetime, timedelta

    today = datetime.now().date()
    start_30d = (today - timedelta(days=30)).isoformat()
    end_str = today.isoformat()
    start_7d = (today - timedelta(days=7)).isoformat()

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
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


@app.command("funnel")
def analytics_funnel(
    period: str = typer.Option("30d", "--period", "-p", help="Time period for new/active metrics"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export raw data to JSON"),
) -> None:
    """Customer lifecycle funnel: New → First Purchase → Repeat → Loyal → At-Risk → Churned.

    Shows conversion rates between lifecycle stages and identifies where customers drop off.

    Examples:
        sh analytics funnel
        sh analytics funnel --period=90d
    """
    config = load_config()

    if config.mode != "mcp":
        print_error("analytics funnel requires MCP mode")
        raise typer.Exit(1)

    try:
        data = _get_mcp_funnel(config, period)
    except MCPError as e:
        print_error(f"MCP Error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Error: {e}")
        raise typer.Exit(1)

    if output:
        path = export_data([data], output)
        print_export_success(path)
    else:
        _print_funnel(data)


@app.command("diagnose")
def analytics_diagnose(
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save AI diagnosis to text file"),
) -> None:
    """AI-synthesized business health diagnosis across all key metrics.

    Gathers data from overview, orders, customers, campaigns and points tables,
    then calls the configured AI (Azure OpenAI / OpenAI) to produce a concise
    diagnosis with actionable recommendations.

    Requires MCP mode and a configured AI API key.

    Examples:
        sh analytics diagnose
        sh analytics diagnose --output=diagnosis.txt
    """
    config = load_config()

    if config.mode != "mcp":
        print_error("analytics diagnose requires MCP mode")
        raise typer.Exit(1)

    console.print("[dim]Gathering metrics from database...[/dim]")
    try:
        ctx = _get_mcp_diagnose_context(config)
    except MCPError as e:
        print_error(f"MCP Error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Error: {e}")
        raise typer.Exit(1)

    prompt = _build_diagnose_prompt(ctx)

    from .ai import call_ai_api
    diagnosis = call_ai_api(prompt, show_thinking=True)

    from rich.panel import Panel
    console.print(Panel(diagnosis, title="[bold cyan]AI Business Diagnosis[/bold cyan]",
                        border_style="cyan", padding=(1, 2)))

    if output:
        Path(output).write_text(diagnosis, encoding="utf-8")
        print_export_success(output)


# =============================================================================
# analytics products — Category & Product Performance
# =============================================================================

def _get_mcp_products(config, period: str, by_category: bool, limit: int) -> list:
    """Query product/category performance from vdm_t_order_detail JOIN vdm_t_product."""
    start_date, _ = _compute_date_range(period)
    date_filter = _safe_date_filter("o.order_date", start_date)
    query_timeout = _mcp_query_timeout(period, grouped=True)

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )

    # Validate limit
    if not isinstance(limit, int) or limit < 1 or limit > 500:
        limit = 30

    with MCPClient(mcp_config) as client:
        client.initialize()

        where_parts = ["o.delete_flag = 0", "o.direction = 0"]
        if start_date:
            where_parts.insert(0, f"o.order_date >= '{start_date.isoformat()}'")
        where_sql = "WHERE " + " AND ".join(where_parts)

        if by_category:
            rows = client.query(f"""
                SELECT
                    COALESCE(p.product_category, od.title, '(未分类)') AS category,
                    COUNT(DISTINCT od.product_code)                     AS sku_count,
                    COUNT(DISTINCT o.code)                              AS order_count,
                    SUM(od.qty)                                         AS total_qty,
                    SUM(od.total_amount) / 100.0                        AS revenue_cny,
                    COUNT(DISTINCT o.customer_code)                     AS unique_buyers
                FROM vdm_t_order o
                JOIN vdm_t_order_detail od
                  ON od.order_code = o.code AND od.delete_flag = 0
                LEFT JOIN vdm_t_product p
                  ON p.code = od.product_code AND p.delete_flag = 0
                {where_sql}
                GROUP BY COALESCE(p.product_category, od.title, '(未分类)')
                ORDER BY revenue_cny DESC
                LIMIT {limit}
            """, database="dts_demoen", timeout=query_timeout)
        else:
            rows = client.query(f"""
                SELECT
                    od.product_code,
                    COALESCE(p.name, od.title, od.product_code)    AS product_name,
                    COALESCE(p.product_category, '-')              AS category,
                    COUNT(DISTINCT o.code)                         AS order_count,
                    SUM(od.qty)                                    AS total_qty,
                    SUM(od.total_amount) / 100.0                   AS revenue_cny,
                    AVG(od.price) / 100.0                          AS avg_price_cny,
                    COUNT(DISTINCT o.customer_code)                AS unique_buyers
                FROM vdm_t_order o
                JOIN vdm_t_order_detail od
                  ON od.order_code = o.code AND od.delete_flag = 0
                LEFT JOIN vdm_t_product p
                  ON p.code = od.product_code AND p.delete_flag = 0
                {where_sql}
                GROUP BY od.product_code, p.name, od.title, p.product_category
                ORDER BY revenue_cny DESC
                LIMIT {limit}
            """, database="dts_demoen", timeout=query_timeout)

    return rows if isinstance(rows, list) else []


def _print_products(rows: list, period: str, by_category: bool, output: str = None) -> None:
    """Rich display for product/category analytics."""
    from rich.table import Table
    from rich import box as rich_box

    if not rows:
        console.print("[yellow]No product data found[/yellow]")
        return

    if output:
        format_output(rows, "json", output)
        return

    total_rev = sum(float(r.get("revenue_cny") or 0) for r in rows)

    if by_category:
        title = f"Revenue by Category  ({period})"
        tbl = Table(title=title, box=rich_box.ROUNDED, header_style="bold cyan")
        tbl.add_column("#",          style="dim", width=4)
        tbl.add_column("Category",               max_width=24)
        tbl.add_column("SKUs",       justify="right")
        tbl.add_column("Revenue (¥)",justify="right", style="green")
        tbl.add_column("Rev Share",  justify="right")
        tbl.add_column("Orders",     justify="right")
        tbl.add_column("Qty",        justify="right")
        tbl.add_column("Buyers",     justify="right", style="cyan")

        for i, r in enumerate(rows, 1):
            rev = float(r.get("revenue_cny") or 0)
            share = f"{rev / total_rev * 100:.1f}%" if total_rev else "—"
            tbl.add_row(
                str(i),
                str(r.get("category") or "-"),
                f"{r.get('sku_count') or 0:,}",
                f"{rev:,.0f}",
                share,
                f"{r.get('order_count') or 0:,}",
                f"{r.get('total_qty') or 0:,}",
                f"{r.get('unique_buyers') or 0:,}",
            )
    else:
        title = f"Top Products by Revenue  ({period})"
        tbl = Table(title=title, box=rich_box.ROUNDED, header_style="bold cyan")
        tbl.add_column("#",           style="dim", width=4)
        tbl.add_column("Product",                  max_width=26)
        tbl.add_column("Category",   style="dim",  max_width=14)
        tbl.add_column("Revenue (¥)", justify="right", style="green")
        tbl.add_column("Rev Share",  justify="right")
        tbl.add_column("Orders",     justify="right")
        tbl.add_column("Qty",        justify="right")
        tbl.add_column("Avg Price",  justify="right")
        tbl.add_column("Buyers",     justify="right", style="cyan")

        for i, r in enumerate(rows, 1):
            rev = float(r.get("revenue_cny") or 0)
            share = f"{rev / total_rev * 100:.1f}%" if total_rev else "—"
            tbl.add_row(
                str(i),
                str(r.get("product_name") or r.get("product_code") or "-"),
                str(r.get("category") or "-"),
                f"{rev:,.0f}",
                share,
                f"{r.get('order_count') or 0:,}",
                f"{r.get('total_qty') or 0:,}",
                f"¥{float(r.get('avg_price_cny') or 0):,.1f}",
                f"{r.get('unique_buyers') or 0:,}",
            )

    console.print(tbl)
    console.print(f"[dim]Total revenue: ¥{total_rev:,.0f}  |  Showing top {len(rows)} rows[/dim]")


@app.command("products")
def analytics_products(
    period: str = typer.Option("30d", "--period", "-p", help="Time period: today/7d/30d/90d/365d"),
    by_category: bool = typer.Option(False, "--by-category", help="Roll up by product category instead of SKU"),
    limit: int = typer.Option(30, "--limit", "-n", help="Max rows (1-500)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to JSON file"),
    show_sql: bool = typer.Option(False, "--show-sql", help="Print SQL queries used"),
) -> None:
    """Product and category revenue analysis (MCP only).

    Joins vdm_t_order → vdm_t_order_detail → vdm_t_product in dts_demoen.
    Normal sales only (direction=0).

    Examples:
        sh analytics products --period=30d
        sh analytics products --by-category
        sh analytics products --by-category --period=90d --output=cats.json
    """
    config = load_config()

    if config.mode != "mcp":
        print_error("analytics products requires MCP mode")
        raise typer.Exit(1)

    try:
        with _sql_trace_ctx() as _sql_log:
            rows = _get_mcp_products(config, period, by_category, limit)
    except MCPError as e:
        print_error(f"MCP Error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Error: {e}")
        raise typer.Exit(1)

    _print_products(rows, period, by_category, output)
    if show_sql:
        _print_sql_trace(_sql_log)


# =============================================================================
# analytics points --daily-trend
# =============================================================================

def _get_mcp_points_daily_trend(config, period: str) -> list:
    """Query daily earn/redeem trend from dwd_member_points_log."""
    start_date, _ = _compute_date_range(period)
    date_filter = _safe_date_filter("create_time", start_date)

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    database = config.mcp.database

    with MCPClient(mcp_config) as client:
        client.initialize()
        rows = client.query(f"""
            SELECT
                DATE(create_time)                                           AS day,
                SUM(CASE WHEN change_type = 'earn'   THEN points ELSE 0 END) AS earned,
                SUM(CASE WHEN change_type = 'redeem' THEN points ELSE 0 END) AS redeemed,
                COUNT(DISTINCT member_id)                                   AS members
            FROM dwd_member_points_log
            {date_filter}
            GROUP BY DATE(create_time)
            ORDER BY day
        """, database=database)

    return rows if isinstance(rows, list) else []


def _print_points_daily_trend(rows: list, period: str) -> None:
    """Bar-style daily earn/redeem trend table."""
    from rich.table import Table
    from rich import box as rich_box

    if not rows:
        console.print("[yellow]No daily points data found[/yellow]")
        return

    max_earned = max((r.get("earned") or 0 for r in rows), default=1) or 1

    tbl = Table(
        title=f"Points Daily Trend  ({period})",
        box=rich_box.SIMPLE, header_style="bold cyan",
    )
    tbl.add_column("Date",     style="dim")
    tbl.add_column("Earned",   justify="right", style="green")
    tbl.add_column("Redeemed", justify="right", style="yellow")
    tbl.add_column("Net",      justify="right")
    tbl.add_column("Members",  justify="right", style="cyan")
    tbl.add_column("Trend",    no_wrap=True)

    for r in rows:
        earned   = int(r.get("earned") or 0)
        redeemed = int(r.get("redeemed") or 0)
        net      = earned - redeemed
        members  = int(r.get("members") or 0)
        bar_len  = int(earned / max_earned * 20) if max_earned else 0
        bar      = "[green]" + "█" * bar_len + "[/green]"
        net_str  = f"[green]+{net:,}[/green]" if net >= 0 else f"[red]{net:,}[/red]"
        tbl.add_row(
            str(r.get("day") or "—"),
            f"{earned:,}",
            f"{redeemed:,}",
            net_str,
            f"{members:,}",
            bar,
        )

    console.print(tbl)
    total_earned   = sum(int(r.get("earned") or 0)   for r in rows)
    total_redeemed = sum(int(r.get("redeemed") or 0) for r in rows)
    console.print(
        f"[dim]Period total — Earned: [green]{total_earned:,}[/green]  "
        f"Redeemed: [yellow]{total_redeemed:,}[/yellow]  "
        f"Net: {'[green]+' if total_earned >= total_redeemed else '[red]'}"
        f"{total_earned - total_redeemed:,}[/{'green' if total_earned >= total_redeemed else 'red'}][/dim]"
    )


# =============================================================================
# analytics stores — Store deep analytics (P1)
# =============================================================================

def _get_mcp_stores(config, period: str, limit: int) -> list:
    """Store-level sales KPIs from dwd_v_order."""
    start_date, _ = _compute_date_range(period)
    date_filter = _safe_date_filter("order_date", start_date)
    if not isinstance(limit, int) or limit < 1 or limit > 200:
        limit = 30

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    database = config.mcp.database

    with MCPClient(mcp_config) as client:
        client.initialize()
        rows = client.query(f"""
            SELECT
                COALESCE(store_name, '线上/未知')          AS store,
                COUNT(*)                                    AS order_count,
                COUNT(DISTINCT customer_code)               AS unique_customers,
                SUM(total_amount) / 100.0                   AS revenue_cny,
                AVG(total_amount) / 100.0                   AS atv_cny,
                COUNT(DISTINCT CASE WHEN repeat_cnt > 1
                      THEN customer_code END)               AS repeat_buyers
            FROM (
                SELECT store_name, customer_code, total_amount,
                       COUNT(*) OVER (PARTITION BY customer_code) AS repeat_cnt
                FROM dwd_v_order
                {date_filter}
            ) t
            GROUP BY store_name
            ORDER BY revenue_cny DESC
            LIMIT {limit}
        """, database=database)
    return rows if isinstance(rows, list) else []


def _print_stores(rows: list, period: str, output: str = None) -> None:
    from rich.table import Table
    from rich import box as rich_box

    if output:
        format_output(rows, "json", output)
        return
    if not rows:
        console.print("[yellow]No store data found[/yellow]")
        return

    total_rev = sum(float(r.get("revenue_cny") or 0) for r in rows)

    tbl = Table(title=f"Store Performance  ({period})",
                box=rich_box.ROUNDED, header_style="bold cyan")
    tbl.add_column("#",          style="dim", width=4)
    tbl.add_column("Store",                   max_width=22)
    tbl.add_column("Revenue (¥)", justify="right", style="green")
    tbl.add_column("Rev Share",  justify="right")
    tbl.add_column("Orders",     justify="right")
    tbl.add_column("Customers",  justify="right", style="cyan")
    tbl.add_column("ATV (¥)",    justify="right")
    tbl.add_column("Repeat Buy", justify="right")
    tbl.add_column("Repeat %",   justify="right")

    for i, r in enumerate(rows, 1):
        rev  = float(r.get("revenue_cny") or 0)
        custs = int(r.get("unique_customers") or 0)
        rep  = int(r.get("repeat_buyers") or 0)
        share = f"{rev/total_rev*100:.1f}%" if total_rev else "—"
        rep_pct = f"{rep/custs*100:.1f}%" if custs else "—"
        tbl.add_row(
            str(i), str(r.get("store") or "—"),
            f"{rev:,.0f}", share,
            f"{int(r.get('order_count') or 0):,}",
            f"{custs:,}",
            f"{float(r.get('atv_cny') or 0):,.1f}",
            f"{rep:,}", rep_pct,
        )
    console.print(tbl)
    console.print(f"[dim]Total revenue: ¥{total_rev:,.0f}[/dim]")


@app.command("stores")
def analytics_stores(
    period: str = typer.Option("30d", "--period", "-p", help="Time period: today/7d/30d/90d/365d"),
    limit: int  = typer.Option(30,    "--limit",  "-n", help="Max stores (1-200)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export JSON"),
    show_sql: bool = typer.Option(False, "--show-sql", help="Print SQL queries used"),
) -> None:
    """Store-level performance: revenue, ATV, unique customers, repeat rate (MCP).

    Examples:
        sh analytics stores
        sh analytics stores --period=90d --limit=50
    """
    config = load_config()
    if config.mode != "mcp":
        print_error("analytics stores requires MCP mode")
        raise typer.Exit(1)
    try:
        with _sql_trace_ctx() as _sql_log:
            rows = _get_mcp_stores(config, period, limit)
    except (MCPError, Exception) as e:
        print_error(f"Error: {e}"); raise typer.Exit(1)
    _print_stores(rows, period, output)
    if show_sql:
        _print_sql_trace(_sql_log)


# =============================================================================
# analytics coupons --by-rule  — Per-rule GMV attribution (P2)
# =============================================================================

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


# =============================================================================
# analytics campaigns --roi  — Campaign incremental revenue (P2)
# =============================================================================

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


# =============================================================================
# analytics ltv — Cohort-based Lifetime Value (P3)
# =============================================================================

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


@app.command("ltv")
def analytics_ltv(
    cohorts: int  = typer.Option(6,  "--cohorts",  "-c", help="Number of past cohort-months to show (1-24)"),
    window: int   = typer.Option(3,  "--window",   "-w", help="Follow-up months per cohort (1-12)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export JSON"),
    show_sql: bool = typer.Option(False, "--show-sql", help="Print SQL queries used"),
) -> None:
    """Cohort-based Lifetime Value: GMV per customer by first-order month (MCP).

    Groups customers by the month of their first order, then tracks
    per-customer GMV for each follow-up month (M0, M1, M2 …).

    Examples:
        sh analytics ltv
        sh analytics ltv --cohorts=12 --window=6
        sh analytics ltv --output=ltv.json
    """
    config = load_config()
    if config.mode != "mcp":
        print_error("analytics ltv requires MCP mode")
        raise typer.Exit(1)
    try:
        with _sql_trace_ctx() as _sql_log:
            rows = _get_mcp_ltv(config, cohorts, window)
    except (MCPError, Exception) as e:
        print_error(f"Error: {e}"); raise typer.Exit(1)

    if output:
        format_output(rows, "json", output)
    else:
        _print_ltv(rows, cohorts, window)
    if show_sql:
        _print_sql_trace(_sql_log)


# =============================================================================
# analytics repurchase — Repurchase rate, timing, GMV contribution
# =============================================================================

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


@app.command("repurchase")
def analytics_repurchase(
    period: str = typer.Option("90d", "--period", "-p",
                               help="Analysis period: 30d/90d/365d"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to JSON/CSV/MD"),
    show_sql: bool = typer.Option(False, "--show-sql", help="Print SQL queries used"),
) -> None:
    """Repurchase rate, GMV contribution, and first-to-second order timing distribution (MCP).

    Key repurchase health metrics:
    - Repurchase buyer count and rate
    - GMV contribution from repeat orders
    - Days-to-repurchase distribution: impulse / habit / demand / low-frequency
    - Monthly repurchase rate trend

    Examples:
        sh analytics repurchase
        sh analytics repurchase --period=365d
        sh analytics repurchase --output=repurchase.json
    """
    config = load_config()
    if config.mode != "mcp":
        print_error("analytics repurchase requires MCP mode")
        raise typer.Exit(1)
    try:
        with _sql_trace_ctx() as _sql_log:
            data = _get_mcp_repurchase(config, period)
    except (MCPError, Exception) as e:
        print_error(f"Error: {e}")
        raise typer.Exit(1)

    if output:
        format_output(data, "json", output)
    else:
        _print_repurchase(data)
    if show_sql:
        _print_sql_trace(_sql_log)


# =============================================================================
# analytics repurchase-path — First→Second order category transition matrix
# =============================================================================

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


@app.command("repurchase-path")
def analytics_repurchase_path(
    period: str = typer.Option("90d", "--period", "-p",
                               help="Analysis period: 30d/90d/365d"),
    limit: int  = typer.Option(20,  "--limit",  "-n",
                               help="Number of category pairs to show (1-100)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to JSON/CSV/MD"),
    show_sql: bool = typer.Option(False, "--show-sql", help="Print SQL queries used"),
) -> None:
    """First-to-repurchase category transition path analysis (MCP).

    Answers 'what category do customers buy on their second order?':
    - First-order category -> repurchase category Top-N transition matrix
    - Per-first-category repurchase rate and same-category retention (stickiness)

    Examples:
        sh analytics repurchase-path
        sh analytics repurchase-path --period=365d --limit=30
        sh analytics repurchase-path --output=path.json
    """
    config = load_config()
    if config.mode != "mcp":
        print_error("analytics repurchase-path requires MCP mode")
        raise typer.Exit(1)
    try:
        with _sql_trace_ctx() as _sql_log:
            data = _get_mcp_repurchase_path(config, period, limit)
    except (MCPError, Exception) as e:
        print_error(f"Error: {e}")
        raise typer.Exit(1)

    if output:
        format_output(data, "json", output)
    else:
        _print_repurchase_path(data)
    if show_sql:
        _print_sql_trace(_sql_log)


# =============================================================================
# analytics anomaly — Statistical anomaly detection on daily metrics
# Uses dws_order_base_metrics_d (DWS layer) for pre-aggregated daily GMV.
# Falls back to dwd_v_order if DWS table is unavailable.
# =============================================================================

_ANOMALY_METRICS = {
    "gmv":        ("GMV (¥)",       "gmv",              True),   # (label, field, fen->cny)
    "orders":     ("Orders",        "order_cnt",        False),
    "aov":        ("AOV (¥)",       "aov",              True),
    "new_buyers": ("New Buyers",    "new_buyer_cnt",    False),
}


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


@app.command("anomaly")
def analytics_anomaly(
    metric: str = typer.Option("gmv", "--metric", "-m",
                               help="Metric to monitor: gmv / orders / aov / new_buyers"),
    lookback: int = typer.Option(30, "--lookback", "-l",
                                 help="Baseline history days (default 30)"),
    days: int = typer.Option(7, "--days", "-d",
                             help="Detection window: flag anomalies in last N days (default 7)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export JSON / CSV / MD"),
    show_sql: bool = typer.Option(False, "--show-sql", help="Print SQL queries used"),
) -> None:
    """Statistical anomaly detection on daily business metrics (MCP).

    Computes mean +/- 2 sigma from the baseline window and flags any day
    in the detection window that falls outside the band.

    Metrics: gmv | orders | aov | new_buyers

    Data source: dws_order_base_metrics_d (DWS pre-aggregated layer).
    Falls back to dwd_v_order if the DWS table is unavailable.

    Examples:
        sh analytics anomaly
        sh analytics anomaly --metric=orders --days=7
        sh analytics anomaly --metric=gmv --lookback=60 --days=14
        sh analytics anomaly --output=anomaly.md
    """
    config = load_config()
    if config.mode != "mcp":
        print_error("analytics anomaly requires MCP mode")
        raise typer.Exit(1)

    try:
        with _sql_trace_ctx() as _sql_log:
            data = _get_mcp_anomaly(config, metric, lookback, days)
    except (MCPError, Exception) as e:
        print_error(f"Error: {e}")
        raise typer.Exit(1)

    if output:
        from datetime import datetime
        meta = {"metric": metric, "lookback": f"{lookback}d", "detect_window": f"{days}d",
                "generated": datetime.now().strftime("%Y-%m-%d %H:%M")}
        format_output(data, "json", output,
                      title=f"Anomaly Detection — {metric}", metadata=meta)
        console.print(f"[green]Exported to {output}[/green]")
    else:
        _print_anomaly(data)

    if show_sql:
        _print_sql_trace(_sql_log)


# =============================================================================
# analytics campaigns --canvas — Journey node funnel (canvas campaigns)
# Uses ads_das_activity_canvas_analysis_d + ads_das_activity_node_canvas_analysis_d
# =============================================================================

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


# =============================================================================
# analytics report — Standard weekly/monthly report templates (MCP)
# Outputs a structured Markdown report combining GMV, orders, new buyers,
# top products, and anomaly summary.
# =============================================================================

def _get_mcp_report(config, period: str) -> dict:
    """Collect data for the standard report template.

    period: 'weekly' (last 7 days) or 'monthly' (last 30 days).
    Queries:
      1. Period vs prior-period KPI comparison
      2. Daily GMV trend
      3. Top 5 products by GMV
      4. Anomaly quick-scan (last N days vs baseline)
    All from DWS layer where available.
    """
    from datetime import datetime, timedelta

    today = datetime.now().date()
    if period == "weekly":
        n_days     = 7
        prior_days = 7
    else:
        n_days     = 30
        prior_days = 30

    start_cur   = (today - timedelta(days=n_days)).isoformat()
    end_cur     = today.isoformat()
    start_prior = (today - timedelta(days=n_days + prior_days)).isoformat()
    end_prior   = (today - timedelta(days=n_days + 1)).isoformat()

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    database = config.mcp.database

    with MCPClient(mcp_config) as client:
        client.initialize()

        # 1. KPI comparison (try DWS first)
        kpi_cur = kpi_prior = {}
        try:
            rows = client.query(f"""
                SELECT
                    SUM(gmv)           AS gmv,
                    SUM(order_cnt)     AS orders,
                    SUM(new_buyer_cnt) AS new_buyers,
                    AVG(aov)           AS aov
                FROM dws_order_base_metrics_d
                WHERE biz_date BETWEEN '{start_cur}' AND '{end_cur}'
            """, database=database)
            if isinstance(rows, list) and rows:
                kpi_cur = rows[0]

            rows = client.query(f"""
                SELECT
                    SUM(gmv)           AS gmv,
                    SUM(order_cnt)     AS orders,
                    SUM(new_buyer_cnt) AS new_buyers,
                    AVG(aov)           AS aov
                FROM dws_order_base_metrics_d
                WHERE biz_date BETWEEN '{start_prior}' AND '{end_prior}'
            """, database=database)
            if isinstance(rows, list) and rows:
                kpi_prior = rows[0]
        except Exception:
            # Fallback: dwd_v_order
            try:
                rows = client.query(f"""
                    SELECT
                        SUM(total_amount)          AS gmv,
                        COUNT(*)                   AS orders,
                        COUNT(DISTINCT customer_code) AS new_buyers,
                        AVG(total_amount)           AS aov
                    FROM dwd_v_order
                    WHERE delete_flag=0 AND direction=0
                      AND order_date BETWEEN '{start_cur}' AND '{end_cur}'
                """, database=database)
                if isinstance(rows, list) and rows:
                    kpi_cur = rows[0]

                rows = client.query(f"""
                    SELECT
                        SUM(total_amount)          AS gmv,
                        COUNT(*)                   AS orders,
                        COUNT(DISTINCT customer_code) AS new_buyers,
                        AVG(total_amount)           AS aov
                    FROM dwd_v_order
                    WHERE delete_flag=0 AND direction=0
                      AND order_date BETWEEN '{start_prior}' AND '{end_prior}'
                """, database=database)
                if isinstance(rows, list) and rows:
                    kpi_prior = rows[0]
            except Exception:
                pass

        # 2. Daily GMV trend
        daily_rows = []
        try:
            rows = client.query(f"""
                SELECT biz_date AS day, gmv
                FROM dws_order_base_metrics_d
                WHERE biz_date BETWEEN '{start_cur}' AND '{end_cur}'
                ORDER BY day
            """, database=database)
            if isinstance(rows, list):
                daily_rows = rows
        except Exception:
            try:
                rows = client.query(f"""
                    SELECT order_date AS day, SUM(total_amount) AS gmv
                    FROM dwd_v_order
                    WHERE delete_flag=0 AND direction=0
                      AND order_date BETWEEN '{start_cur}' AND '{end_cur}'
                    GROUP BY order_date ORDER BY day
                """, database=database)
                if isinstance(rows, list):
                    daily_rows = rows
            except Exception:
                pass

        # 3. Top 5 products
        top_products = []
        try:
            rows = client.query(f"""
                SELECT
                    product_name,
                    SUM(sale_amount) AS gmv,
                    SUM(sale_qty)    AS qty
                FROM dwd_v_order_item
                WHERE order_date BETWEEN '{start_cur}' AND '{end_cur}'
                GROUP BY product_name
                ORDER BY gmv DESC
                LIMIT 5
            """, database=database)
            if isinstance(rows, list):
                top_products = rows
        except Exception:
            pass

    return {
        "period":       period,
        "start":        start_cur,
        "end":          end_cur,
        "kpi_cur":      kpi_cur,
        "kpi_prior":    kpi_prior,
        "daily_trend":  daily_rows,
        "top_products": top_products,
        "generated":    datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def _build_report_markdown(data: dict) -> str:
    """Render the report data as a Markdown string."""
    period   = data["period"].capitalize()
    start    = data["start"]
    end      = data["end"]
    cur      = data["kpi_cur"]
    prior    = data["kpi_prior"]
    daily    = data["daily_trend"]
    top_p    = data["top_products"]
    gen      = data["generated"]

    def _pct(c, p, key, fen=True):
        cv = float(c.get(key) or 0) / (100 if fen else 1)
        pv = float(p.get(key) or 0) / (100 if fen else 1)
        if not pv:
            return "N/A"
        diff = (cv - pv) / pv * 100
        arrow = "+" if diff >= 0 else ""
        return f"{arrow}{diff:.1f}%"

    gmv_cur     = float(cur.get("gmv") or 0) / 100
    orders_cur  = int(cur.get("orders") or 0)
    buyers_cur  = int(cur.get("new_buyers") or 0)
    aov_cur     = float(cur.get("aov") or 0) / 100

    lines = [
        f"# {period} Business Report",
        f"",
        f"_Period: {start} ~ {end}_  |  _Generated: {gen}_",
        f"",
        f"---",
        f"",
        f"## KPI Summary",
        f"",
        f"| Metric | Current Period | vs Prior Period |",
        f"| --- | --- | --- |",
        f"| GMV (¥) | {gmv_cur:,.0f} | {_pct(cur, prior, 'gmv', True)} |",
        f"| Orders | {orders_cur:,} | {_pct(cur, prior, 'orders', False)} |",
        f"| New Buyers | {buyers_cur:,} | {_pct(cur, prior, 'new_buyers', False)} |",
        f"| AOV (¥) | {aov_cur:,.1f} | {_pct(cur, prior, 'aov', True)} |",
        f"",
    ]

    # Daily trend
    if daily:
        lines += [
            f"## Daily GMV Trend",
            f"",
            f"| Date | GMV (¥) |",
            f"| --- | --- |",
        ]
        for r in daily:
            day = r.get("day", "-")
            gmv = float(r.get("gmv") or 0) / 100
            lines.append(f"| {day} | {gmv:,.0f} |")
        lines.append("")

    # Top products
    if top_p:
        lines += [
            f"## Top Products",
            f"",
            f"| Product | GMV (¥) | Qty |",
            f"| --- | --- | --- |",
        ]
        for p in top_p:
            pname = p.get("product_name", "-")
            pgmv  = float(p.get("gmv") or 0) / 100
            pqty  = int(p.get("qty") or 0)
            lines.append(f"| {pname} | {pgmv:,.0f} | {pqty:,} |")
        lines.append("")

    lines += [
        f"---",
        f"",
        f"_Source: SocialHub.AI CLI — auto-generated {period} report_",
    ]
    return "\n".join(lines)


def _print_report_console(data: dict) -> None:
    """Print a condensed report to the console."""
    from rich.panel import Panel
    from rich.markdown import Markdown

    md = _build_report_markdown(data)
    console.print(Panel(Markdown(md), title=f"[bold cyan]{data['period'].capitalize()} Report[/bold cyan]",
                         border_style="cyan"))


def _write_md_report(md: str, output: Optional[str], title: str) -> None:
    """Write or print a markdown report. Shared by all report sub-types."""
    if output:
        ext = Path(output).suffix.lower()
        out_path = output if ext == ".md" else (output + ".md" if not ext else output)
        Path(out_path).write_text(md, encoding="utf-8")
        console.print(f"[green]Report exported to {out_path}[/green]")
    else:
        from rich.panel import Panel
        from rich.markdown import Markdown
        console.print(Panel(Markdown(md), title=f"[bold cyan]{title}[/bold cyan]",
                            border_style="cyan"))


@app.command("report")
def analytics_report(
    period: str = typer.Argument("weekly", help="weekly | monthly | campaign | loyalty"),
    campaign_id: Optional[str] = typer.Option(None, "--id", help="Campaign ID (required for 'campaign' period)"),
    output: Optional[str] = typer.Option(None, "--output", "-o",
                                          help="Export Markdown report to file (e.g. report.md)"),
    show_sql: bool = typer.Option(False, "--show-sql", help="Print SQL queries used"),
) -> None:
    """Generate standard business reports (MCP).

    Periods:
      weekly    — last 7 days vs prior 7 days (GMV, orders, new buyers, top products)
      monthly   — last 30 days vs prior 30 days
      campaign  — post-mortem for a single campaign (requires --id)
      loyalty   — loyalty program health review (enrollment, points, churn)

    Examples:
        sh analytics report weekly
        sh analytics report monthly --output=monthly_report.md
        sh analytics report campaign --id ACT001 --output=postmortem.md
        sh analytics report loyalty --output=loyalty_health.md
    """
    valid = ("weekly", "monthly", "campaign", "loyalty")
    if period not in valid:
        console.print(f"[red]period must be one of: {', '.join(valid)}[/red]")
        raise typer.Exit(1)

    if period == "campaign" and not campaign_id:
        console.print("[red]'campaign' report requires --id <campaign_id>[/red]")
        raise typer.Exit(1)

    config = load_config()
    if config.mode != "mcp":
        console.print("[red]analytics report requires MCP mode[/red]")
        raise typer.Exit(1)

    try:
        with _sql_trace_ctx() as _sql_log:
            if period == "campaign":
                data = _get_mcp_campaign_postmortem(config, campaign_id)
                md   = _build_postmortem_markdown(data)
                _write_md_report(md, output, f"Campaign Post-Mortem: {campaign_id}")
            elif period == "loyalty":
                data = _get_mcp_loyalty_health(config)
                md   = _build_loyalty_health_markdown(data)
                _write_md_report(md, output, "Loyalty Program Health Review")
            else:
                data = _get_mcp_report(config, period)
                md   = _build_report_markdown(data)
                _write_md_report(md, output, f"{period.capitalize()} Report")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if show_sql:
        _print_sql_trace(_sql_log)


# =============================================================================
# analytics report campaign — Campaign post-mortem (D1)
# Combines: campaign detail + ROI + audience tier breakdown + attribution
# =============================================================================

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


# =============================================================================
# analytics report loyalty — Loyalty program health review (D1)
# Combines: enrollment, tier dist, points liability, redeem rate, churn risk
# =============================================================================

def _get_mcp_loyalty_health(config) -> dict:
    """Fetch loyalty program health metrics."""
    from datetime import datetime, timedelta
    today    = datetime.now().date()
    start_30 = (today - timedelta(days=30)).isoformat()

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    database = config.mcp.database

    with MCPClient(mcp_config) as client:
        client.initialize()

        # Enrollment + tier distribution (vdm_t_* tables live in dts_demoen)
        tier_rows = client.query("""
            SELECT m.tier_code AS tier_name,
                   COUNT(*) AS members,
                   SUM(COALESCE(pa.points_available, 0)) AS available_pts,
                   SUM(COALESCE(pa.points_in_transit, 0)) AS transit_pts
            FROM vdm_t_member m
            LEFT JOIN vdm_t_points_account pa ON m.member_code = pa.member_code
            GROUP BY m.tier_code
            ORDER BY members DESC
        """, database="dts_demoen")

        # Points liability (total unredeemed value)
        pts_rows = client.query("""
            SELECT
                SUM(points_available)   AS total_available,
                SUM(points_in_transit)  AS total_transit,
                SUM(points_expired)     AS total_expired_30d,
                COUNT(DISTINCT member_code) AS active_holders
            FROM vdm_t_points_account
            WHERE points_available > 0
        """, database="dts_demoen")

        # Redeem rate (last 30d)
        redeem_rows = client.query(f"""
            SELECT
                SUM(points_consume) AS redeemed_30d,
                SUM(points_earn)    AS earned_30d,
                COUNT(DISTINCT member_code) AS redeemers
            FROM vdm_t_points_record
            WHERE create_time >= '{start_30}'
        """, database="dts_demoen")

        # Churn risk — members with no activity last 90d
        churn_rows = client.query("""
            SELECT COUNT(*) AS at_risk
            FROM vdm_t_member
            WHERE last_active_date < DATE_SUB(CURRENT_DATE, INTERVAL 90 DAY)
              AND status = 1
        """, database="dts_demoen")

    tiers   = tier_rows if isinstance(tier_rows, list) else []
    pts     = pts_rows[0] if isinstance(pts_rows, list) and pts_rows else {}
    redeem  = redeem_rows[0] if isinstance(redeem_rows, list) and redeem_rows else {}
    churn   = churn_rows[0] if isinstance(churn_rows, list) and churn_rows else {}

    total_members = sum(int(t.get("members") or 0) for t in tiers)

    return {
        "tiers":         tiers,
        "total_members": total_members,
        "points":        pts,
        "redeem":        redeem,
        "churn":         churn,
        "generated":     datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def _build_loyalty_health_markdown(data: dict) -> str:
    tiers   = data["tiers"]
    total   = data["total_members"]
    pts     = data["points"]
    redeem  = data["redeem"]
    churn   = data["churn"]
    gen     = data["generated"]

    avail   = float(pts.get("total_available") or 0)
    transit = float(pts.get("total_transit") or 0)
    expired = float(pts.get("total_expired_30d") or 0)
    holders = int(pts.get("active_holders") or 0)

    redeemed = float(redeem.get("redeemed_30d") or 0)
    earned   = float(redeem.get("earned_30d") or 0)
    redeem_rate = redeemed / earned * 100 if earned else 0
    at_risk  = int(churn.get("at_risk") or 0)
    churn_pct = at_risk / total * 100 if total else 0

    lines = [
        f"# Loyalty Program Health Review",
        f"",
        f"_Generated: {gen}_",
        f"",
        f"---",
        f"",
        f"## Membership Overview",
        f"",
        f"Total enrolled members: **{total:,}**  |  "
        f"Active point holders: **{holders:,}**",
        f"",
        f"### Tier Distribution",
        f"",
        f"| Tier | Members | Share | Available Pts | In-Transit Pts |",
        f"| --- | --- | --- | --- | --- |",
    ]
    for t in tiers:
        m  = int(t.get("members") or 0)
        sh = m / total * 100 if total else 0
        ap = float(t.get("available_pts") or 0)
        tp = float(t.get("transit_pts") or 0)
        lines.append(f"| {t.get('tier_name','-')} | {m:,} | {sh:.1f}% | {ap:,.0f} | {tp:,.0f} |")

    lines += [
        f"",
        f"## Points Health",
        f"",
        f"| Metric | Value |",
        f"| --- | --- |",
        f"| Total Available (liability) | {avail:,.0f} pts |",
        f"| In-Transit | {transit:,.0f} pts |",
        f"| Expired (last 30d) | {expired:,.0f} pts |",
        f"| Earned (last 30d) | {earned:,.0f} pts |",
        f"| Redeemed (last 30d) | {redeemed:,.0f} pts |",
        f"| Redeem Rate | {redeem_rate:.1f}% |",
        f"",
        f"## Churn Risk",
        f"",
        f"Members inactive 90+ days: **{at_risk:,}** ({churn_pct:.1f}% of enrolled)",
        f"",
        f"---",
        f"",
        f"_Source: SocialHub.AI CLI — Loyalty Health Review_",
    ]
    return "\n".join(lines)


# =============================================================================
# analytics coupons --anomaly — Abnormal redeem behavior detection (B4)
# Uses dws_coupon_base_metrics_d; mean+2sigma on daily redeem_cnt
# =============================================================================

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


# =============================================================================
# analytics recommend — B7 Recommendation analysis
# Uses dwd_rec_user_product_rating, dws_rec_user_recs,
#      dws_rec_product_to_prdocut_rating (typo preserved from schema)
# =============================================================================

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


@app.command("recommend")
def analytics_recommend(
    user_id: Optional[str] = typer.Option(None, "--user", "-u",
                                           help="Show recommendations for a specific user ID"),
    product_id: Optional[str] = typer.Option(None, "--product", "-p",
                                              help="Show products associated with a product ID"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of results (default 20)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to file"),
    show_sql: bool = typer.Option(False, "--show-sql", help="Print SQL queries used"),
) -> None:
    """Recommendation engine analysis: top products, user recs, product affinity (MCP).

    Uses dwd_rec_user_product_rating, dws_rec_user_recs,
    dws_rec_product_to_prdocut_rating.

    Examples:
        sh analytics recommend
        sh analytics recommend --user U12345
        sh analytics recommend --product P00123
        sh analytics recommend --limit=50 --output=recs.json
    """
    config = load_config()
    if config.mode != "mcp":
        console.print("[red]analytics recommend requires MCP mode[/red]")
        raise typer.Exit(1)

    try:
        with _sql_trace_ctx() as _sql_log:
            data = _get_mcp_recommend(config, user_id, product_id, limit)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if output:
        format_output(data, "json", output, title="Recommendation Analysis")
        console.print(f"[green]Exported to {output}[/green]")
    else:
        _print_recommend(data)

    if show_sql:
        _print_sql_trace(_sql_log)


# =============================================================================
# analytics rfm — RFM customer value segmentation
# =============================================================================

def _get_mcp_rfm(config, limit: int = 0, segment_filter: str = "") -> dict:
    """Query ads_v_rfm for RFM segment distribution and optionally top customers.

    Args:
        limit: when > 0, also return top `limit` customers by rfm_score
        segment_filter: if set, filter to rfm_segment = this value
    """
    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    database = config.mcp.database
    safe_limit = max(1, min(int(limit), 500)) if limit > 0 else 0
    safe_seg   = _sanitize_string_input(segment_filter, 50) if segment_filter else ""

    seg_where  = f"WHERE rfm_segment = '{safe_seg}'" if safe_seg else ""
    seg_and    = f"AND rfm_segment = '{safe_seg}'" if safe_seg else ""

    with MCPClient(mcp_config) as client:
        client.initialize()

        # Segment distribution
        dist_rows = client.query(f"""
            SELECT
                rfm_segment,
                rfm_label,
                COUNT(*)                       AS customer_count,
                AVG(monetary)  / 100.0         AS avg_monetary_cny,
                AVG(frequency)                 AS avg_frequency,
                AVG(recency_score)             AS avg_recency_days
            FROM ads_v_rfm
            {seg_where}
            GROUP BY rfm_segment, rfm_label
            ORDER BY customer_count DESC
        """, database=database)

        # Total for share %
        total_rows = client.query(f"""
            SELECT COUNT(*) AS total FROM ads_v_rfm {seg_where}
        """, database=database)

        total = int((total_rows[0].get("total") or 0) if isinstance(total_rows, list) and total_rows else 0)

        distribution = []
        if isinstance(dist_rows, list):
            for r in dist_rows:
                cnt = int(r.get("customer_count") or 0)
                distribution.append({
                    "rfm_segment":      str(r.get("rfm_segment") or "-"),
                    "rfm_label":        str(r.get("rfm_label") or "-"),
                    "customer_count":   cnt,
                    "share_pct":        round(cnt / total * 100, 1) if total else 0,
                    "avg_monetary_cny": round(float(r.get("avg_monetary_cny") or 0), 2),
                    "avg_frequency":    round(float(r.get("avg_frequency") or 0), 1),
                    "avg_recency_days": round(float(r.get("avg_recency_days") or 0), 1),
                })

        # Top customers (optional)
        top_customers = []
        if safe_limit > 0:
            top_rows = client.query(f"""
                SELECT
                    customer_code,
                    rfm_segment,
                    rfm_label,
                    recency_score,
                    frequency,
                    monetary / 100.0 AS monetary_cny,
                    rfm_score
                FROM ads_v_rfm
                WHERE 1=1 {seg_and}
                ORDER BY rfm_score DESC
                LIMIT {safe_limit}
            """, database=database)
            if isinstance(top_rows, list):
                top_customers = [
                    {
                        "customer_code":  r.get("customer_code") or "-",
                        "rfm_segment":    r.get("rfm_segment") or "-",
                        "rfm_label":      r.get("rfm_label") or "-",
                        "recency_days":   int(r.get("recency_score") or 0),
                        "frequency":      int(r.get("frequency") or 0),
                        "monetary_cny":   round(float(r.get("monetary_cny") or 0), 2),
                        "rfm_score":      round(float(r.get("rfm_score") or 0), 3),
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


@app.command("rfm")
def analytics_rfm(
    segment: str = typer.Option("", "--segment", "-s",
                                help="Filter to specific RFM segment code (e.g. high_value, at_risk)"),
    top: int = typer.Option(0, "--top", "-t",
                            help="Also show top N customers by RFM score (0=off, max 500)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export JSON"),
) -> None:
    """RFM customer segmentation — segment distribution, avg spend, avg orders (MCP).

    Queries ads_v_rfm in das_demoen. Shows segment distribution with average
    spend, order frequency, and recency. Use --top N to list highest-scoring customers.

    Examples:
        sh analytics rfm
        sh analytics rfm --segment=high_value
        sh analytics rfm --top=20
        sh analytics rfm --output=rfm.json
    """
    config = load_config()
    if config.mode != "mcp":
        console.print("[red]analytics rfm requires MCP mode[/red]")
        raise typer.Exit(1)

    try:
        with _sql_trace_ctx() as _sql_log:
            data = _get_mcp_rfm(config, limit=top, segment_filter=segment)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if output:
        format_output(data, "json", output, title="RFM Analysis")
        console.print(f"[green]Exported to {output}[/green]")
    else:
        _print_rfm(data, show_top=(top > 0))
