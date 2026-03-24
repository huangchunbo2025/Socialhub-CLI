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
    """Get campaign analytics from MCP database."""
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

        # Build safe WHERE clause
        conditions = []
        if start_date:
            date_str = start_date.isoformat()
            if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
                conditions.append(f"create_time >= '{date_str}'")

        if campaign_id:
            # Sanitize campaign_id (alphanumeric only)
            safe_id = _sanitize_string_input(campaign_id, 50)
            if safe_id:
                conditions.append(f"activity_id = '{safe_id}'")

        if name:
            # Sanitize name for LIKE query
            safe_name = _sanitize_string_input(name, 100)
            if safe_name:
                conditions.append(f"activity_name LIKE '%{safe_name}%'")

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        result = client.query(f"""
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

        if isinstance(result, list):
            return result
        return []


def _get_mcp_points(config, period: str) -> dict:
    """Get points analytics from MCP database."""
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

        # Query points statistics with safe date filter
        result = client.query(f"""
            SELECT
                SUM(CASE WHEN change_type = 'earn' THEN points ELSE 0 END) as total_earned,
                SUM(CASE WHEN change_type = 'redeem' THEN points ELSE 0 END) as total_redeemed,
                COUNT(DISTINCT member_id) as active_members,
                COUNT(*) as total_transactions
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

        if isinstance(result, list) and len(result) > 0:
            row = result[0]
            data["total_earned"] = row.get("total_earned") or 0
            data["total_redeemed"] = row.get("total_redeemed") or 0
            data["active_members"] = row.get("active_members") or 0
            data["total_transactions"] = row.get("total_transactions") or 0

        return data


def _get_mcp_coupons(config, period: str, roi: bool = False) -> dict:
    """Get coupon analytics from MCP database."""
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

        # Query coupon statistics with safe date filter
        result = client.query(f"""
            SELECT
                COUNT(*) as total_issued,
                SUM(CASE WHEN status = 'used' THEN 1 ELSE 0 END) as total_used,
                SUM(CASE WHEN status = 'expired' THEN 1 ELSE 0 END) as total_expired,
                COUNT(DISTINCT customer_code) as unique_customers
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
        }

        if isinstance(result, list) and len(result) > 0:
            row = result[0]
            data["total_issued"] = row.get("total_issued") or 0
            data["total_used"] = row.get("total_used") or 0
            data["total_expired"] = row.get("total_expired") or 0
            data["unique_customers"] = row.get("unique_customers") or 0
            if data["total_issued"] > 0:
                data["usage_rate"] = round(data["total_used"] / data["total_issued"] * 100, 2)

        return data


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

    if funnel and isinstance(data, dict):
        # Show funnel data as table
        funnel_data = {
            "Target": f"{data.get('target_count', 0):,}",
            "Reached": f"{data.get('reached_count', 0):,}",
            "Opened": f"{data.get('opened_count', 0):,}",
            "Clicked": f"{data.get('clicked_count', 0):,}",
            "Converted": f"{data.get('converted_count', 0):,}",
        }
        print_dict(funnel_data, title=f"Campaign Funnel: {data.get('campaign_name', 'Unknown')}")
    else:
        format_output(data, format, output)


@app.command("points")
def analytics_points(
    period: str = typer.Option("30d", "--period", "-p", help="Time period"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to file"),
) -> None:
    """Analyze points program metrics."""
    config = load_config()

    if config.mode == "mcp":
        # MCP mode - query real database
        try:
            data = _get_mcp_points(config, period)
        except MCPError as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)
        except Exception as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)
    elif config.mode == "api":
        try:
            with SocialHubClient() as client:
                # Get points statistics
                result = client.get("/api/v1/analytics/points", params={"period": period})
                data = result.get("data", result)
        except APIError as e:
            print_error(f"API Error: {e.message}")
            raise typer.Exit(1)
    else:
        print_error("Points analytics requires API or MCP mode")
        raise typer.Exit(1)

    format_output(data, format, output)


@app.command("coupons")
def analytics_coupons(
    period: str = typer.Option("30d", "--period", "-p", help="Time period"),
    roi: bool = typer.Option(False, "--roi", help="Calculate ROI"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to file"),
) -> None:
    """Analyze coupon usage metrics."""
    config = load_config()

    if config.mode == "mcp":
        # MCP mode - query real database
        try:
            data = _get_mcp_coupons(config, period, roi)
        except MCPError as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)
        except Exception as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)
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
    else:
        print_error("Coupon analytics requires API or MCP mode")
        raise typer.Exit(1)

    format_output(data, format, output)


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
