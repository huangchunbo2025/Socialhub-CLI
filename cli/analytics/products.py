"""Product analytics functions."""

from rich.console import Console

from ..api.mcp_client import MCPClient, MCPConfig as MCPClientConfig, MCPError
from ..output.export import format_output
from .common import (
    _compute_date_range,
    _mcp_query_timeout,
    _safe_date_filter,
)

console = Console()


def _get_mcp_products(config, period: str, by_category: bool, limit: int) -> list:
    """Query product/category performance from vdm_t_order_detail JOIN vdm_t_product."""
    start_date, _ = _compute_date_range(period)
    date_filter = _safe_date_filter("o.order_date", start_date)
    query_timeout = _mcp_query_timeout(period, grouped=True)

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
        api_key=config.mcp.api_key,
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
