"""Workflow commands — high-level business workflows composing analytics."""

from datetime import datetime, timedelta

import typer
from rich import box as rich_box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..api.mcp_client import MCPClient, MCPError
from ..api.mcp_client import MCPConfig as MCPClientConfig
from ..config import load_config
from ..output.table import print_error

app = typer.Typer(help="Business workflow shortcuts (daily-brief, etc.)")
console = Console()

_PERIOD_LABELS: dict[str, str] = {
    "today": "Today",
    "7d":    "Last 7 Days",
    "30d":   "Last 30 Days",
}


# ---------------------------------------------------------------------------
# Data layer
# ---------------------------------------------------------------------------

def _get_mcp_daily_brief(config, period: str) -> dict:
    """Fetch data for the daily business brief.

    Returns current-period totals and 7-day rolling-average baseline
    so the caller can compute delta percentages.

    period: 'today' | '7d' | '30d'
    """
    today = datetime.now().date()

    if period == "today":
        cur_start = today
        cur_end = today
    elif period == "7d":
        cur_start = today - timedelta(days=7)
        cur_end = today - timedelta(days=1)
    elif period == "30d":
        cur_start = today - timedelta(days=30)
        cur_end = today - timedelta(days=1)
    else:
        cur_start = today
        cur_end = today

    # Baseline: the 7 days immediately before cur_start
    base_end = cur_start - timedelta(days=1)
    base_start = base_end - timedelta(days=6)

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    database = config.mcp.database

    n_cur_days  = (cur_end - cur_start).days + 1
    n_base_days = (base_end - base_start).days + 1

    with MCPClient(mcp_config) as client:
        client.initialize()

        def _q(sql: str):
            return client.query(sql, database=database)

        def _overview_sum(start, end) -> dict:
            rows = _q(f"""
                SELECT
                    SUM(total_transaction_amt) AS gmv,
                    SUM(total_order_num)       AS orders,
                    SUM(add_custs_num)         AS new_customers
                FROM ads_das_business_overview_d
                WHERE biz_date BETWEEN '{start}' AND '{end}'
            """)
            row = rows[0] if rows else {}
            gmv    = float(row.get("gmv")    or 0)
            orders = int(row.get("orders")   or 0)
            new_c  = int(row.get("new_customers") or 0)
            aov    = gmv / orders if orders else 0
            return {"gmv": gmv, "orders": orders, "new_customers": new_c, "aov": aov}

        def _active_buyers(start, end) -> int:
            rows = _q(f"""
                SELECT COUNT(DISTINCT customer_code) AS buyers
                FROM dwd_v_order
                WHERE order_date BETWEEN '{start}' AND '{end}'
            """)
            return int(rows[0].get("buyers", 0)) if rows else 0

        cur  = _overview_sum(cur_start, cur_end)
        base = _overview_sum(base_start, base_end)
        cur["active_buyers"]  = _active_buyers(cur_start, cur_end)
        base["active_buyers"] = _active_buyers(base_start, base_end)

    # Normalise to per-day averages so periods of different length compare fairly
    def _avg(d: dict, n: int) -> dict:
        return {k: v / n for k, v in d.items()} if n else d

    cur_avg  = _avg(cur,  n_cur_days)
    base_avg = _avg(base, n_base_days)

    def _delta(cur_val, base_val) -> float | None:
        if base_val and base_val != 0:
            return (cur_val - base_val) / abs(base_val) * 100
        return None

    return {
        "period":       period,
        "cur_start":    cur_start.isoformat(),
        "cur_end":      cur_end.isoformat(),
        "base_start":   base_start.isoformat(),
        "base_end":     base_end.isoformat(),
        "current":      cur,
        "baseline_avg": base_avg,
        "delta": {
            k: _delta(cur_avg[k], base_avg[k])
            for k in ["gmv", "orders", "aov", "new_customers", "active_buyers"]
        },
    }


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt_cny(v: float) -> str:
    if v >= 1_000_000:
        return f"¥{v/1_000_000:.2f}M"
    if v >= 1_000:
        return f"¥{v/1_000:.1f}K"
    return f"¥{v:.0f}"


def _fmt_delta(pct: float | None) -> str:
    if pct is None:
        return "[dim]—[/dim]"
    arrow = "▲" if pct >= 0 else "▼"
    color = "green" if pct >= 0 else "red"
    return f"[{color}]{arrow} {abs(pct):.1f}% vs 7-day avg[/{color}]"


def _print_daily_brief(data: dict) -> None:
    period_label = _PERIOD_LABELS.get(data["period"], data["period"])

    title = (
        f"[bold]Daily Business Brief[/bold] — "
        f"{period_label} ({data['cur_start']} → {data['cur_end']})"
    )

    cur   = data["current"]
    delta = data["delta"]

    tbl = Table(box=rich_box.SIMPLE, show_header=False, padding=(0, 2))
    tbl.add_column("Metric",  style="bold",  min_width=18)
    tbl.add_column("Value",   justify="right", min_width=14)
    tbl.add_column("vs Avg",  min_width=26)

    tbl.add_row("GMV",                   _fmt_cny(cur["gmv"]),          _fmt_delta(delta["gmv"]))
    tbl.add_row("Orders",               f"{cur['orders']:,}",           _fmt_delta(delta["orders"]))
    tbl.add_row("AOV",                  _fmt_cny(cur["aov"]),           _fmt_delta(delta["aov"]))
    tbl.add_row("Active Buyers",        f"{cur['active_buyers']:,}",    _fmt_delta(delta["active_buyers"]))
    tbl.add_row("New Signups [dim]*[/dim]", f"{cur['new_customers']:,}",    _fmt_delta(delta["new_customers"]))

    console.print()
    console.print(Panel(tbl, title=title, border_style="cyan", padding=(1, 2)))
    console.print(
        f"[dim]  Baseline: daily average over "
        f"{data['base_start']} → {data['base_end']}[/dim]"
    )
    console.print(
        "[dim]  * New Signups = add_custs_num (all newly registered customers, "
        "not limited to loyalty-program members)[/dim]\n"
    )


def _brief_to_markdown(data: dict) -> str:
    cur   = data["current"]
    delta = data["delta"]
    period_label = _PERIOD_LABELS.get(data["period"], data["period"])

    def _delta_md(pct):
        if pct is None:
            return "—"
        arrow = "▲" if pct >= 0 else "▼"
        return f"{arrow} {abs(pct):.1f}%"

    lines = [
        f"# Daily Business Brief — {period_label}",
        f"**Period:** {data['cur_start']} → {data['cur_end']}  ",
        f"**Baseline:** daily avg {data['base_start']} → {data['base_end']}",
        "",
        "| Metric | Value | vs 7-day avg |",
        "|--------|-------|--------------|",
        f"| GMV | {_fmt_cny(cur['gmv'])} | {_delta_md(delta['gmv'])} |",
        f"| Orders | {cur['orders']:,} | {_delta_md(delta['orders'])} |",
        f"| AOV | {_fmt_cny(cur['aov'])} | {_delta_md(delta['aov'])} |",
        f"| Active Buyers | {cur['active_buyers']:,} | {_delta_md(delta['active_buyers'])} |",
        f"| New Signups * | {cur['new_customers']:,} | {_delta_md(delta['new_customers'])} |",
        "",
        "_* New Signups = add_custs_num (all newly registered customers, not limited to loyalty-program members)_",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.command("daily-brief")
def workflow_daily_brief(
    period: str = typer.Option(
        "today", "--period", "-p",
        help="Time period: today, 7d, 30d",
    ),
    output: str | None = typer.Option(
        None, "--output", "-o",
        help="Export to file (.md or .html)",
    ),
) -> None:
    """Daily business brief — GMV, orders, AOV, buyers vs 7-day average.

    Examples:
        sh workflow daily-brief
        sh workflow daily-brief --period=7d
        sh workflow daily-brief --output=brief.md
    """
    valid_periods = {"today", "7d", "30d"}
    if period not in valid_periods:
        print_error(f"Invalid period '{period}'. Use: {', '.join(sorted(valid_periods))}")
        raise typer.Exit(1)

    config = load_config()
    if config.mode != "mcp":
        print_error("daily-brief requires MCP mode. Run: sh config set mode mcp")
        raise typer.Exit(1)

    try:
        data = _get_mcp_daily_brief(config, period)
    except MCPError as e:
        print_error(f"MCP Error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Error: {e}")
        raise typer.Exit(1)

    if output:
        md = _brief_to_markdown(data)
        if output.endswith(".html"):
            try:
                import markdown as md_lib
                html_body = md_lib.markdown(md, extensions=["tables"])
                html = f"<!DOCTYPE html><html><body>{html_body}</body></html>"
                with open(output, "w", encoding="utf-8") as f:
                    f.write(html)
                console.print(f"[green]Saved → {output}[/green]")
            except ImportError:
                md_path = output.replace(".html", ".md")
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(md)
                console.print("[yellow]markdown package not installed; saved as .md instead[/yellow]")
                console.print(f"[green]Saved → {md_path}[/green]")
        else:
            with open(output, "w", encoding="utf-8") as f:
                f.write(md)
            console.print(f"[green]Saved → {output}[/green]")
    else:
        _print_daily_brief(data)
