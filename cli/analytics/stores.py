"""Store analytics functions."""

from rich.console import Console

from ..api.mcp_client import MCPClient, MCPConfig as MCPClientConfig, MCPError
from ..output.export import format_output
from .common import (
    _compute_date_range,
    _safe_date_filter,
)

console = Console()


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
