"""Customer analytics functions."""

from rich.console import Console

from ..api.mcp_client import MCPClient, MCPConfig as MCPClientConfig, MCPError
from .common import (
    _compute_date_range,
    _mcp_query_timeout,
    _safe_date_filter,
    _validate_days_list,
)

console = Console()


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
