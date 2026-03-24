"""Member analytics commands.

Uses pre-aggregated das_demoen tables to surface member KPIs that are
not yet exposed by the existing analytics commands:
  - ads_das_business_overview_d   (daily snapshot: active/churn bitmaps)
  - ads_das_custs_tier_distribution_d (tier breakdown with risk bitmaps)
  - ads_v_rfm                     (RFM value segmentation)
  - dwd_v_order + dim_customer_info (top-member ranking)
"""

import re
from datetime import datetime, timedelta
from typing import Optional

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..api.mcp_client import MCPClient, MCPConfig as MCPClientConfig, MCPError
from ..config import load_config
from ..output.table import print_error

app = typer.Typer(help="Member analytics commands")
console = Console()

# Only members (identity_type=1) unless noted otherwise
_MEMBER_TYPE = 1

VALID_PERIODS = frozenset({"7d", "30d", "90d", "365d", "all"})
VALID_GROWTH_BY = frozenset({"day", "week", "month"})
VALID_TOP_BY = frozenset({"spend", "orders"})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_date_range(period: str, from_date: Optional[str], to_date: Optional[str]):
    """Return (start_date, end_date) as date objects.

    --from / --to take priority over --period.
    """
    today = datetime.now().date()

    if from_date or to_date:
        try:
            start = datetime.strptime(from_date, "%Y-%m-%d").date() if from_date else today - timedelta(days=365)
            end = datetime.strptime(to_date, "%Y-%m-%d").date() if to_date else today
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")
        if start > end:
            raise ValueError("--from must be earlier than --to")
        return start, end

    if period not in VALID_PERIODS:
        raise ValueError(f"Invalid period '{period}'. Valid options: {', '.join(sorted(VALID_PERIODS))}")

    if period == "all":
        return None, today

    days_map = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}
    return today - timedelta(days=days_map[period]), today


def _date_filter(column: str, start, end=None) -> str:
    """Build a safe SQL date clause.

    If end is provided → BETWEEN; otherwise → >= start.
    Returns empty string when start is None (all-time query).
    """
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', column):
        raise ValueError(f"Invalid column name: {column}")

    if start is None:
        return ""

    start_str = start.isoformat()
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', start_str):
        raise ValueError(f"Invalid date: {start_str}")

    if end is not None:
        end_str = end.isoformat()
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', end_str):
            raise ValueError(f"Invalid date: {end_str}")
        return f"AND {column} BETWEEN '{start_str}' AND '{end_str}'"

    return f"AND {column} >= '{start_str}'"


def _mcp_client(config) -> MCPClient:
    return MCPClient(MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    ))


def _latest_biz_date(client, database: str) -> str:
    """Latest available biz_date in the overview table."""
    result = client.query(
        "SELECT MAX(biz_date) AS latest FROM ads_das_business_overview_d",
        database=database,
    )
    if isinstance(result, list) and result:
        return str(result[0].get("latest", ""))
    return ""


def _fmt(n) -> str:
    """Format a number with comma separators, or '-' for None/0."""
    try:
        v = int(n or 0)
        return f"{v:,}" if v else "-"
    except (TypeError, ValueError):
        return "-"


def _pct(part, total) -> str:
    try:
        p, t = int(part or 0), int(total or 0)
        return f"{p / t * 100:.1f}%" if t else "-"
    except (TypeError, ValueError, ZeroDivisionError):
        return "-"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.command("overview")
def members_overview(
    period: str = typer.Option("30d", "--period", "-p", help="Period for new-member count: 7d/30d/90d/365d/all"),
    from_date: Optional[str] = typer.Option(None, "--from", help="Start date YYYY-MM-DD (overrides --period)"),
    to_date: Optional[str] = typer.Option(None, "--to", help="End date YYYY-MM-DD"),
):
    """Member KPI overview: total, active, buying, new, pre-churn, churned, silent."""
    config = load_config()
    database = config.mcp.database

    try:
        start, end = _resolve_date_range(period, from_date, to_date)
    except ValueError as e:
        print_error(str(e))
        raise typer.Exit(1)

    try:
        with _mcp_client(config) as client:
            client.initialize()

            latest = _latest_biz_date(client, database)
            if not latest:
                print_error("No data in ads_das_business_overview_d")
                raise typer.Exit(1)

            # Snapshot KPIs (bitmaps give unique people counts)
            snap_rows = client.query(f"""
                SELECT
                    SUM(total_custs_num)                               AS total_members,
                    BITMAP_COUNT(BITMAP_UNION(active_custs_bitnum))    AS active_members,
                    BITMAP_COUNT(BITMAP_UNION(buyer_bitnum))            AS buying_members,
                    BITMAP_COUNT(BITMAP_UNION(pre_churn_custs_bitnum)) AS pre_churn_members,
                    BITMAP_COUNT(BITMAP_UNION(churn_custs_bitnum))      AS churned_members,
                    BITMAP_COUNT(BITMAP_UNION(dead_custs_bitnum))       AS silent_members
                FROM ads_das_business_overview_d
                WHERE biz_date = '{latest}'
                  AND identity_type = {_MEMBER_TYPE}
            """, database=database)

            # New members in the selected period
            range_filter = _date_filter("biz_date", start, end)
            new_rows = client.query(f"""
                SELECT SUM(add_custs_num) AS new_members
                FROM ads_das_business_overview_d
                WHERE identity_type = {_MEMBER_TYPE}
                  {range_filter}
            """, database=database)

        snap = snap_rows[0] if isinstance(snap_rows, list) and snap_rows else {}
        new_val = (new_rows[0] if isinstance(new_rows, list) and new_rows else {}).get("new_members")

        total    = int(snap.get("total_members") or 0)
        active   = int(snap.get("active_members") or 0)
        buying   = int(snap.get("buying_members") or 0)
        pre_churn = int(snap.get("pre_churn_members") or 0)
        churned  = int(snap.get("churned_members") or 0)
        silent   = int(snap.get("silent_members") or 0)
        new_m    = int(new_val or 0)

        period_label = f"{from_date or start} ~ {to_date or end}"

        t = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
        t.add_column("Metric", style="dim", min_width=22)
        t.add_column("Value", style="bold", justify="right", min_width=12)
        t.add_column("Rate", style="dim", min_width=10)

        t.add_row("Total Members",     _fmt(total),     "")
        t.add_row("Active Members",    _fmt(active),    _pct(active, total))
        t.add_row("Buying Members",    _fmt(buying),    _pct(buying, total))
        t.add_row("New Members",       _fmt(new_m),     period_label)
        t.add_row("", "", "")
        t.add_row("Pre-churn (at risk)", _fmt(pre_churn), _pct(pre_churn, total))
        t.add_row("Churned",           _fmt(churned),   _pct(churned, total))
        t.add_row("Silent",            _fmt(silent),    _pct(silent, total))

        console.print()
        console.print(Panel(
            t,
            title=f"[bold cyan]Member Overview[/bold cyan]  [dim]snapshot: {latest}[/dim]",
            border_style="cyan",
        ))

    except MCPError as e:
        print_error(f"MCP error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Error: {e}")
        raise typer.Exit(1)


@app.command("tier-distribution")
def tier_distribution():
    """Member distribution across loyalty tiers, with churn risk per tier."""
    config = load_config()
    database = config.mcp.database

    try:
        with _mcp_client(config) as client:
            client.initialize()

            latest = _latest_biz_date(client, database)
            if not latest:
                print_error("No data available")
                raise typer.Exit(1)

            rows = client.query(f"""
                SELECT
                    tier_name,
                    loyalty_program_name,
                    SUM(total_custs_num_td)                                AS member_count,
                    BITMAP_COUNT(BITMAP_UNION(pre_churn_custs_bitnum))     AS pre_churn,
                    BITMAP_COUNT(BITMAP_UNION(churn_custs_bitnum))          AS churned,
                    BITMAP_COUNT(BITMAP_UNION(dead_custs_bitnum))           AS silent
                FROM ads_das_custs_tier_distribution_d
                WHERE biz_date = '{latest}'
                  AND identity_type = {_MEMBER_TYPE}
                GROUP BY tier_name, loyalty_program_name
                ORDER BY member_count DESC
            """, database=database)

    except MCPError as e:
        print_error(f"MCP error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Error: {e}")
        raise typer.Exit(1)

    if not rows:
        console.print("[yellow]No tier data found[/yellow]")
        return

    t = Table(box=box.ROUNDED, header_style="bold cyan")
    t.add_column("Tier", style="bold")
    t.add_column("Program", style="dim")
    t.add_column("Members", justify="right")
    t.add_column("Pre-churn", justify="right", style="yellow")
    t.add_column("Risk %", justify="right", style="yellow")
    t.add_column("Churned", justify="right", style="red")
    t.add_column("Silent", justify="right", style="dim")

    for r in rows:
        count = int(r.get("member_count") or 0)
        t.add_row(
            str(r.get("tier_name") or "-"),
            str(r.get("loyalty_program_name") or "-"),
            _fmt(count),
            _fmt(r.get("pre_churn")),
            _pct(r.get("pre_churn"), count),
            _fmt(r.get("churned")),
            _fmt(r.get("silent")),
        )

    console.print()
    console.print(Panel(t, title=f"[bold cyan]Tier Distribution[/bold cyan]  [dim]snapshot: {latest}[/dim]", border_style="cyan"))


@app.command("growth")
def members_growth(
    from_date: Optional[str] = typer.Option(None, "--from", help="Start date YYYY-MM-DD"),
    to_date: Optional[str] = typer.Option(None, "--to", help="End date YYYY-MM-DD"),
    period: str = typer.Option("90d", "--period", "-p", help="Fallback period if --from/--to not set"),
    by: str = typer.Option("month", "--by", help="Group by: day / week / month"),
):
    """New member growth trend grouped by day, week, or month."""
    if by not in VALID_GROWTH_BY:
        print_error(f"Invalid --by '{by}'. Use: {', '.join(sorted(VALID_GROWTH_BY))}")
        raise typer.Exit(1)

    config = load_config()
    database = config.mcp.database

    try:
        start, end = _resolve_date_range(period, from_date, to_date)
    except ValueError as e:
        print_error(str(e))
        raise typer.Exit(1)

    fmt_map = {"day": "%Y-%m-%d", "week": "%Y-%u", "month": "%Y-%m"}
    date_fmt = fmt_map[by]
    range_filter = _date_filter("biz_date", start, end)

    try:
        with _mcp_client(config) as client:
            client.initialize()
            rows = client.query(f"""
                SELECT
                    DATE_FORMAT(biz_date, '{date_fmt}') AS period,
                    SUM(add_custs_num) AS new_members
                FROM ads_das_business_overview_d
                WHERE identity_type = {_MEMBER_TYPE}
                  {range_filter}
                GROUP BY period
                ORDER BY period
            """, database=database)

    except MCPError as e:
        print_error(f"MCP error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Error: {e}")
        raise typer.Exit(1)

    if not rows:
        console.print("[yellow]No growth data in the selected range[/yellow]")
        return

    t = Table(box=box.ROUNDED, header_style="bold cyan")
    t.add_column("Period")
    t.add_column("New Members", justify="right", style="bold")

    total_new = 0
    for r in rows:
        n = int(r.get("new_members") or 0)
        total_new += n
        t.add_row(str(r.get("period") or "-"), _fmt(n))

    t.add_section()
    t.add_row("[bold]Total[/bold]", f"[bold]{_fmt(total_new)}[/bold]")

    label = f"{start} ~ {end}" if start else f"All time ~ {end}"
    console.print()
    console.print(Panel(t, title=f"[bold cyan]Member Growth[/bold cyan]  [dim]by {by} | {label}[/dim]", border_style="cyan"))


@app.command("churn")
def members_churn(
    period: str = typer.Option("30d", "--period", "-p", help="Snapshot period: 7d/30d/90d/365d"),
    tier: Optional[str] = typer.Option(None, "--tier", help="Filter by tier name"),
):
    """Churn analysis by tier: pre-churn, churned, and silent counts."""
    config = load_config()
    database = config.mcp.database

    try:
        with _mcp_client(config) as client:
            client.initialize()

            latest = _latest_biz_date(client, database)
            if not latest:
                print_error("No data available")
                raise typer.Exit(1)

            tier_filter = ""
            if tier:
                safe_tier = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff\s_-]", "", tier)[:50]
                tier_filter = f"AND tier_name = '{safe_tier}'"

            rows = client.query(f"""
                SELECT
                    tier_name,
                    BITMAP_COUNT(BITMAP_UNION(pre_churn_custs_bitnum)) AS pre_churn,
                    BITMAP_COUNT(BITMAP_UNION(churn_custs_bitnum))      AS churned,
                    BITMAP_COUNT(BITMAP_UNION(dead_custs_bitnum))       AS silent,
                    SUM(total_custs_num_td)                             AS total
                FROM ads_das_custs_tier_distribution_d
                WHERE biz_date = '{latest}'
                  AND identity_type = {_MEMBER_TYPE}
                  {tier_filter}
                GROUP BY tier_name
                ORDER BY pre_churn DESC
            """, database=database)

    except MCPError as e:
        print_error(f"MCP error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Error: {e}")
        raise typer.Exit(1)

    if not rows:
        console.print("[yellow]No churn data found[/yellow]")
        return

    t = Table(box=box.ROUNDED, header_style="bold cyan")
    t.add_column("Tier", style="bold")
    t.add_column("Total", justify="right")
    t.add_column("Pre-churn", justify="right", style="yellow")
    t.add_column("Pre-churn %", justify="right", style="yellow")
    t.add_column("Churned", justify="right", style="red")
    t.add_column("Silent", justify="right", style="dim")

    for r in rows:
        total = r.get("total")
        t.add_row(
            str(r.get("tier_name") or "-"),
            _fmt(total),
            _fmt(r.get("pre_churn")),
            _pct(r.get("pre_churn"), total),
            _fmt(r.get("churned")),
            _fmt(r.get("silent")),
        )

    console.print()
    console.print(Panel(t, title=f"[bold cyan]Churn Analysis[/bold cyan]  [dim]snapshot: {latest}[/dim]", border_style="cyan"))


@app.command("at-risk")
def members_at_risk(
    limit: int = typer.Option(10, "--limit", "-n", help="Number of tiers to show"),
):
    """Pre-churn members at risk of leaving, ranked by tier."""
    config = load_config()
    database = config.mcp.database

    try:
        with _mcp_client(config) as client:
            client.initialize()

            latest = _latest_biz_date(client, database)
            if not latest:
                print_error("No data available")
                raise typer.Exit(1)

            rows = client.query(f"""
                SELECT
                    tier_name,
                    loyalty_program_name,
                    BITMAP_COUNT(BITMAP_UNION(pre_churn_custs_bitnum)) AS at_risk,
                    SUM(total_custs_num_td)                             AS total
                FROM ads_das_custs_tier_distribution_d
                WHERE biz_date = '{latest}'
                  AND identity_type = {_MEMBER_TYPE}
                GROUP BY tier_name, loyalty_program_name
                ORDER BY at_risk DESC
                LIMIT {max(1, min(limit, 100))}
            """, database=database)

    except MCPError as e:
        print_error(f"MCP error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Error: {e}")
        raise typer.Exit(1)

    if not rows:
        console.print("[yellow]No at-risk data found[/yellow]")
        return

    total_at_risk = sum(int(r.get("at_risk") or 0) for r in rows)

    t = Table(box=box.ROUNDED, header_style="bold cyan")
    t.add_column("Tier", style="bold")
    t.add_column("Program", style="dim")
    t.add_column("At Risk", justify="right", style="yellow bold")
    t.add_column("% of Tier", justify="right", style="yellow")

    for r in rows:
        t.add_row(
            str(r.get("tier_name") or "-"),
            str(r.get("loyalty_program_name") or "-"),
            _fmt(r.get("at_risk")),
            _pct(r.get("at_risk"), r.get("total")),
        )

    console.print()
    console.print(Panel(
        t,
        title=f"[bold yellow]At-Risk Members[/bold yellow]  [dim]total: {_fmt(total_at_risk)} | snapshot: {latest}[/dim]",
        border_style="yellow",
    ))


@app.command("rfm")
def members_rfm(
    limit: int = typer.Option(50, "--limit", "-n", help="Number of rows to return"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to CSV file path"),
):
    """RFM customer value segmentation (from ads_v_rfm view)."""
    config = load_config()
    database = config.mcp.database

    try:
        with _mcp_client(config) as client:
            client.initialize()
            rows = client.query(f"""
                SELECT *
                FROM ads_v_rfm
                WHERE identity_type = {_MEMBER_TYPE}
                LIMIT {max(1, min(limit, 1000))}
            """, database=database)

    except MCPError as e:
        print_error(f"MCP error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Error: {e}")
        raise typer.Exit(1)

    if not rows:
        console.print("[yellow]No RFM data found[/yellow]")
        return

    if output:
        # Export to CSV
        try:
            import csv, pathlib
            out_path = pathlib.Path(output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            console.print(f"[green]Exported {len(rows)} rows to {output}[/green]")
        except Exception as e:
            print_error(f"Export failed: {e}")
        return

    # Build table from first row's keys
    headers = list(rows[0].keys())
    t = Table(box=box.ROUNDED, header_style="bold cyan")
    for h in headers:
        t.add_column(h)

    for r in rows:
        t.add_row(*[str(r.get(h) or "-") for h in headers])

    console.print()
    console.print(Panel(t, title=f"[bold cyan]RFM Segments[/bold cyan]  [dim]{len(rows)} rows[/dim]", border_style="cyan"))


@app.command("top")
def members_top(
    by: str = typer.Option("spend", "--by", help="Rank by: spend / orders"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of members to show"),
    period: str = typer.Option("365d", "--period", "-p", help="Purchase period: 7d/30d/90d/365d"),
    from_date: Optional[str] = typer.Option(None, "--from", help="Start date YYYY-MM-DD"),
    to_date: Optional[str] = typer.Option(None, "--to", help="End date YYYY-MM-DD"),
):
    """Top members ranked by total spend or order count."""
    if by not in VALID_TOP_BY:
        print_error(f"Invalid --by '{by}'. Use: spend / orders")
        raise typer.Exit(1)

    config = load_config()
    database = config.mcp.database

    try:
        start, end = _resolve_date_range(period, from_date, to_date)
    except ValueError as e:
        print_error(str(e))
        raise typer.Exit(1)

    range_filter = _date_filter("o.order_date", start, end)
    order_col = "total_spend" if by == "spend" else "order_count"

    try:
        with _mcp_client(config) as client:
            client.initialize()
            rows = client.query(f"""
                SELECT
                    o.customer_code,
                    c.customer_name,
                    c.member_level AS tier,
                    COUNT(*)                    AS order_count,
                    SUM(o.total_amount) / 100.0 AS total_spend
                FROM dwd_v_order o
                JOIN dim_customer_info c ON c.customer_code = o.customer_code
                WHERE c.member_level IS NOT NULL
                  AND c.member_level != ''
                  {range_filter}
                GROUP BY o.customer_code, c.customer_name, c.member_level
                ORDER BY {order_col} DESC
                LIMIT {max(1, min(limit, 200))}
            """, database=database)

    except MCPError as e:
        print_error(f"MCP error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Error: {e}")
        raise typer.Exit(1)

    if not rows:
        console.print("[yellow]No member data found for the selected period[/yellow]")
        return

    t = Table(box=box.ROUNDED, header_style="bold cyan")
    t.add_column("#", justify="right", style="dim")
    t.add_column("Customer Code")
    t.add_column("Name")
    t.add_column("Tier", style="bold")
    t.add_column("Orders", justify="right")
    t.add_column("Total Spend (CNY)", justify="right", style="bold")

    for i, r in enumerate(rows, 1):
        spend = r.get("total_spend")
        spend_str = f"{float(spend):,.2f}" if spend is not None else "-"
        t.add_row(
            str(i),
            str(r.get("customer_code") or "-"),
            str(r.get("customer_name") or "-"),
            str(r.get("tier") or "-"),
            _fmt(r.get("order_count")),
            spend_str,
        )

    label = f"{start} ~ {end}" if start else f"All time ~ {end}"
    console.print()
    console.print(Panel(
        t,
        title=f"[bold cyan]Top {limit} Members[/bold cyan]  [dim]by {by} | {label}[/dim]",
        border_style="cyan",
    ))
