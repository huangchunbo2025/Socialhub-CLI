"""Report generation functions."""

from pathlib import Path
from typing import Optional

from rich.console import Console

from ..api.mcp_client import MCPClient, MCPConfig as MCPClientConfig, MCPError

console = Console()


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
