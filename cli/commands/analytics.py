"""Data analytics commands."""

import json
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
# SECURITY: Input Validation & SQL Safety
# =============================================================================

# Whitelist of valid period values
VALID_PERIODS = frozenset({"all", "today", "7d", "30d", "90d", "365d"})

# Whitelist of valid 'by' grouping options
VALID_GROUP_BY = frozenset({"channel", "province", "store", "date", "month"})


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

    # Validate column name (alphanumeric and underscore only)
    import re
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', column):
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

    # Validate column name
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', column):
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
    """Get customer analytics from MCP database."""
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

        # Total customers
        total_result = client.query(
            "SELECT COUNT(*) as total FROM dim_customer_info",
            database=database
        )
        total_customers = 0
        if isinstance(total_result, list) and len(total_result) > 0:
            total_customers = total_result[0].get("total", 0)

        # Customer by type
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

        # New customers in period (safe date filter)
        new_date_filter = _safe_date_filter("create_date", start_date)
        new_result = client.query(f"""
            SELECT COUNT(*) as new_count
            FROM dim_customer_info
            {new_date_filter}
        """, database=database)
        new_customers = 0
        if isinstance(new_result, list) and len(new_result) > 0:
            new_customers = new_result[0].get("new_count", 0)

        # Active customers in period (safe date filter)
        active_date_filter = _safe_date_filter("order_date", start_date)
        active_result = client.query(f"""
            SELECT COUNT(DISTINCT customer_code) as active
            FROM dwd_v_order
            {active_date_filter}
        """, database=database)
        active_customers = 0
        if isinstance(active_result, list) and len(active_result) > 0:
            active_customers = active_result[0].get("active", 0)

        return {
            "period": period,
            "total_customers": total_customers,
            "new_customers": new_customers,
            "active_customers": active_customers,
            "by_type": by_type,
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
            """, database=database)

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
            """, database=database)

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
            """, database=database)
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
            """, database=database)
            # Return list directly for proper table display
            return result if isinstance(result, list) else []

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
            """, database=database)

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
            """, database=database)

            if isinstance(repurchase_result, list) and len(repurchase_result) > 0:
                repeat_customers = repurchase_result[0].get("repeat_customers", 0)
                if data["unique_customers"] > 0:
                    data["repurchase_rate"] = round(repeat_customers / data["unique_customers"] * 100, 2)
                else:
                    data["repurchase_rate"] = 0

            return data


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

        # --- Base summary ---
        result = client.query(f"""
            SELECT
                SUM(CASE WHEN change_type = 'earn'   THEN points ELSE 0 END) AS total_earned,
                SUM(CASE WHEN change_type = 'redeem' THEN points ELSE 0 END) AS total_redeemed,
                COUNT(DISTINCT member_id) AS active_members,
                COUNT(*) AS total_transactions
            FROM dwd_member_points_log
            {date_filter}
        """, database=database)

        data = {
            "period": period,
            "total_earned": 0,
            "total_redeemed": 0,
            "active_members": 0,
            "total_transactions": 0,
        }

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

        # --- Base summary (always) ---
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

        data = {
            "period": period,
            "total_issued": 0,
            "total_used": 0,
            "total_expired": 0,
            "unique_customers": 0,
            "usage_rate": 0.0,
            "total_face_value_cny": 0.0,
            "redeemed_face_value_cny": 0.0,
        }

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
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to file"),
) -> None:
    """Show analytics overview dashboard."""
    config = load_config()

    if config.mode == "mcp":
        # MCP mode - query real database
        try:
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


@app.command("customers")
def analytics_customers(
    period: str = typer.Option("30d", "--period", "-p", help="Time period"),
    channel: str = typer.Option("all", "--channel", "-c", help="Channel filter (all, wechat, app, web, tmall)"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to file"),
) -> None:
    """Analyze customer metrics."""
    config = load_config()

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
    by: Optional[str] = typer.Option(None, "--by", help="Group by (channel, province)"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to file"),
) -> None:
    """Analyze order metrics."""
    config = load_config()

    if config.mode == "mcp":
        # MCP mode - query real database
        try:
            data = _get_mcp_orders(config, period, metric, by)
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
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to file"),
) -> None:
    """Analyze marketing campaign performance."""
    config = load_config()

    if config.mode == "mcp":
        # MCP mode - query real database
        try:
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
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to file"),
) -> None:
    """Analyze points program metrics.

    Examples:
        sh analytics points --period=30d
        sh analytics points --expiring-days=30
        sh analytics points --breakdown
    """
    config = load_config()

    if config.mode == "mcp":
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
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to file"),
) -> None:
    """Analyze coupon usage and redemption value.

    Examples:
        sh analytics coupons --period=30d
        sh analytics coupons --roi
    """
    config = load_config()

    if config.mode == "mcp":
        try:
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
