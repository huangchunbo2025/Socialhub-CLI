"""Segment management commands."""

import json
from pathlib import Path
from typing import Optional

import typer
from rich import box as rich_box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..api.client import APIError, SocialHubClient
from ..api.mcp_client import MCPClient, MCPConfig as MCPClientConfig, MCPError
from ..config import load_config
from ..local.reader import LocalDataReader, read_customers_csv
from ..output.export import export_data, format_output, print_export_success
from ..output.table import print_dict, print_error, print_list, print_success

app = typer.Typer(help="Customer segment management commands")
console = Console()


@app.command("list")
def list_segments(
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Status filter (enabled, disabled, draft)"),
    limit: int = typer.Option(50, "--limit", "-l", help="Number of records"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
) -> None:
    """List customer segments."""
    config = load_config()

    if config.mode != "api":
        print_error("Segments require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.list_segments(status=status, page_size=limit)
            data = result.get("data", {}).get("items", result.get("data", []))
            total = result.get("data", {}).get("total", len(data))
            console.print(f"[dim]Total: {total} segments[/dim]")
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)

    format_output(data, format)


@app.command("get")
def get_segment(
    segment_id: str = typer.Argument(..., help="Segment ID"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
) -> None:
    """Get segment details."""
    config = load_config()

    if config.mode != "api":
        print_error("Segments require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.get_segment(segment_id)
            data = result.get("data", result)
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)

    format_output(data, format)


@app.command("preview")
def preview_segment(
    segment_id: str = typer.Argument(..., help="Segment ID"),
    limit: int = typer.Option(20, "--limit", "-l", help="Number of preview records"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
) -> None:
    """Preview customers in a segment."""
    config = load_config()

    if config.mode != "api":
        print_error("Segments require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.preview_segment(segment_id)
            data = result.get("data", result)

            # Limit preview results
            if isinstance(data, list):
                console.print(f"[dim]Showing {min(len(data), limit)} of {len(data)} customers[/dim]")
                data = data[:limit]
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)

    format_output(data, format)


@app.command("create")
def create_segment(
    name: str = typer.Option(..., "--name", "-n", help="Segment name"),
    rules: Optional[str] = typer.Option(None, "--rules", "-r", help="Rules as JSON string or file path"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="Segment description"),
) -> None:
    """Create a new customer segment."""
    config = load_config()

    if config.mode != "api":
        print_error("Segments require API mode")
        raise typer.Exit(1)

    # Parse rules
    rules_dict = {}
    if rules:
        if Path(rules).exists():
            # Load from file
            with open(rules, "r", encoding="utf-8") as f:
                rules_dict = json.load(f)
        else:
            # Parse as JSON string
            try:
                rules_dict = json.loads(rules)
            except json.JSONDecodeError as e:
                print_error(f"Invalid JSON rules: {e}")
                raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.create_segment(
                name=name,
                rules=rules_dict,
                description=description,
            )
            data = result.get("data", result)

            print_success(f"Segment created: {data.get('id', 'Unknown')}")
            print_dict(data)
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)


@app.command("create-from-file")
def create_segment_from_file(
    file: str = typer.Option(..., "--file", "-f", help="Customer list file (CSV)"),
    name: str = typer.Option(..., "--name", "-n", help="Segment name"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="Segment description"),
) -> None:
    """Create a segment from a customer list file."""
    config = load_config()

    if config.mode != "api":
        print_error("Segments require API mode")
        raise typer.Exit(1)

    # Read customer IDs from file
    try:
        reader = LocalDataReader(config.local.data_dir)
        df = reader.read_file(file)

        # Look for ID column
        id_column = None
        for col in ["id", "customer_id", "客户ID", "客户编号"]:
            if col in df.columns:
                id_column = col
                break

        if not id_column:
            print_error("Could not find customer ID column in file")
            raise typer.Exit(1)

        customer_ids = df[id_column].dropna().astype(str).tolist()
        console.print(f"[dim]Found {len(customer_ids)} customer IDs[/dim]")
    except Exception as e:
        print_error(f"Failed to read file: {e}")
        raise typer.Exit(1)

    # Create segment with customer ID list
    try:
        with SocialHubClient() as client:
            result = client.post("/api/v1/segments/from-list", {
                "name": name,
                "description": description,
                "customer_ids": customer_ids,
            })
            data = result.get("data", result)

            print_success(f"Segment created: {data.get('id', 'Unknown')}")
            print_dict(data)
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)


@app.command("enable")
def enable_segment(
    segment_id: str = typer.Argument(..., help="Segment ID"),
) -> None:
    """Enable a segment."""
    config = load_config()

    if config.mode != "api":
        print_error("Segments require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            client.enable_segment(segment_id)
            print_success(f"Segment {segment_id} enabled")
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)


@app.command("disable")
def disable_segment(
    segment_id: str = typer.Argument(..., help="Segment ID"),
) -> None:
    """Disable a segment."""
    config = load_config()

    if config.mode != "api":
        print_error("Segments require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            client.disable_segment(segment_id)
            print_success(f"Segment {segment_id} disabled")
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)


@app.command("export")
def export_segment(
    segment_id: str = typer.Argument(..., help="Segment ID"),
    output: str = typer.Option("segment_export.csv", "--output", "-o", help="Output file path"),
) -> None:
    """Export segment customers to file."""
    config = load_config()

    if config.mode != "api":
        print_error("Segments require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.export_segment(segment_id)
            data = result.get("data", result)

            if isinstance(data, list):
                path = export_data(data, output)
                print_export_success(path)
                console.print(f"[green]Exported {len(data)} customers[/green]")
            else:
                print_error("Unexpected response format")
                raise typer.Exit(1)
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# MCP helpers for segment analytics
# ---------------------------------------------------------------------------

def _mcp_segment_performance(config, limit: int = 30) -> list:
    """Query t_customer_group + t_customer_group_detail in datanow_demoen.

    Returns a list of groups with member count, type, and status.
    group_type: 0=静态群组, 1=动态群组
    generate_type: 0=规则群组, 1=导入群组
    """
    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    seg_db = "datanow_demoen"
    safe_limit = max(1, min(int(limit), 200))

    with MCPClient(mcp_config) as client:
        client.initialize()

        rows = client.query(f"""
            SELECT
                g.id              AS group_id,
                g.group_name,
                g.group_type,
                g.generate_type,
                g.status,
                g.create_time,
                g.update_time,
                COUNT(d.customer_code) AS member_count
            FROM t_customer_group g
            LEFT JOIN t_customer_group_detail d
                   ON d.group_id = g.id
                  AND d.status = 1
                  AND d.delete_flag = 0
            WHERE g.delete_flag = 0
            GROUP BY g.id, g.group_name, g.group_type, g.generate_type,
                     g.status, g.create_time, g.update_time
            ORDER BY member_count DESC
            LIMIT {safe_limit}
        """, database=seg_db)

    return rows if isinstance(rows, list) else []


def _print_segment_performance(rows: list, output: Optional[str] = None) -> None:
    """Rich table display for segment performance."""
    if not rows:
        console.print("[yellow]No segment data found[/yellow]")
        return

    if output:
        format_output(rows, "json", output)
        return

    _group_type_label = {0: "静态", 1: "动态"}
    _gen_type_label   = {0: "规则", 1: "导入"}

    t = Table(box=rich_box.ROUNDED, header_style="bold cyan", show_lines=False)
    t.add_column("ID",      style="dim",  max_width=10)
    t.add_column("Name",                  max_width=28)
    t.add_column("Type",    style="dim")
    t.add_column("Source",  style="dim")
    t.add_column("Status",  style="dim")
    t.add_column("Members", justify="right", style="cyan")
    t.add_column("Updated", style="dim",  max_width=12)

    for r in rows:
        gtype = _group_type_label.get(r.get("group_type"), str(r.get("group_type", "-")))
        gtype_style = "green" if r.get("group_type") == 1 else "blue"
        gentype = _gen_type_label.get(r.get("generate_type"), str(r.get("generate_type", "-")))
        updated = str(r.get("update_time") or r.get("create_time") or "-")[:10]
        cnt = int(r.get("member_count") or 0)
        t.add_row(
            str(r.get("group_id") or "-"),
            str(r.get("group_name") or "-"),
            f"[{gtype_style}]{gtype}[/{gtype_style}]",
            gentype,
            str(r.get("status") or "-"),
            f"{cnt:,}",
            updated,
        )

    console.print()
    console.print(t)

    total_members = sum(int(r.get("member_count") or 0) for r in rows)
    dynamic_count = sum(1 for r in rows if r.get("group_type") == 1)
    static_count  = sum(1 for r in rows if r.get("group_type") == 0)
    console.print(
        f"[dim]{len(rows)} segments | "
        f"Dynamic: {dynamic_count}  Static: {static_count} | "
        f"Total members across all groups: {total_members:,}[/dim]"
    )


@app.command("performance")
def segment_performance(
    limit: int = typer.Option(30, "--limit", "-l", help="Max segments to show"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to JSON file"),
) -> None:
    """Analyze customer segment sizes and types (MCP mode).

    Queries t_customer_group and t_customer_group_detail in datanow_demoen,
    showing each segment's member count, type (static/dynamic), and source.

    Examples:
        sh segments performance
        sh segments performance --limit=50
        sh segments performance --output=segments.json
    """
    config = load_config()

    if config.mode != "mcp":
        print_error("Segment performance requires MCP mode")
        raise typer.Exit(1)

    try:
        rows = _mcp_segment_performance(config, limit)
    except MCPError as e:
        print_error(f"MCP Error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Error: {e}")
        raise typer.Exit(1)

    _print_segment_performance(rows, output)



# ---------------------------------------------------------------------------
# Segment overlap analysis — two-group customer intersection
# ---------------------------------------------------------------------------

def _mcp_segment_overlap(config, id1: int, id2: int) -> dict:
    """Compute overlap between two customer groups in datanow_demoen.

    Three queries (all in one session):
    1. COUNT for group A  (t_customer_group_detail)
    2. COUNT for group B
    3. COUNT of intersection (INNER JOIN on customer_code)

    Computes: overlap, union, Jaccard similarity, exclusive sets.
    Includes group names from t_customer_group for context.
    """
    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    seg_db = "datanow_demoen"
    safe_id1 = int(id1)
    safe_id2 = int(id2)

    with MCPClient(mcp_config) as client:
        client.initialize()

        # 1. Group metadata
        meta_rows = client.query(f"""
            SELECT id, group_name, group_type, generate_type, status
            FROM t_customer_group
            WHERE id IN ({safe_id1}, {safe_id2})
              AND delete_flag = 0
        """, database=seg_db)

        # 2. Count for group A
        cnt_a_rows = client.query(f"""
            SELECT COUNT(*) AS cnt
            FROM t_customer_group_detail
            WHERE group_id = {safe_id1}
              AND status = 1
              AND delete_flag = 0
        """, database=seg_db)

        # 3. Count for group B
        cnt_b_rows = client.query(f"""
            SELECT COUNT(*) AS cnt
            FROM t_customer_group_detail
            WHERE group_id = {safe_id2}
              AND status = 1
              AND delete_flag = 0
        """, database=seg_db)

        # 4. Intersection count
        overlap_rows = client.query(f"""
            SELECT COUNT(*) AS overlap
            FROM t_customer_group_detail a
            JOIN t_customer_group_detail b
              ON b.customer_code = a.customer_code
             AND b.group_id = {safe_id2}
             AND b.status = 1
             AND b.delete_flag = 0
            WHERE a.group_id = {safe_id1}
              AND a.status = 1
              AND a.delete_flag = 0
        """, database=seg_db)

    # Parse metadata
    meta = {}
    if isinstance(meta_rows, list):
        for r in meta_rows:
            meta[int(r.get("id"))] = r

    _gt = {0: "静态", 1: "动态"}
    _gs = {0: "规则", 1: "导入"}

    def _group_info(gid):
        r = meta.get(gid, {})
        return {
            "id": gid,
            "name": r.get("group_name") or f"Group {gid}",
            "type": _gt.get(r.get("group_type"), "-"),
            "source": _gs.get(r.get("generate_type"), "-"),
            "status": r.get("status") or "-",
        }

    def _cnt(rows):
        return int((rows[0].get("cnt") or 0) if isinstance(rows, list) and rows else 0)

    cnt_a    = _cnt(cnt_a_rows)
    cnt_b    = _cnt(cnt_b_rows)
    overlap  = int((overlap_rows[0].get("overlap") or 0) if isinstance(overlap_rows, list) and overlap_rows else 0)
    union    = cnt_a + cnt_b - overlap
    jaccard  = round(overlap / union * 100, 2) if union else 0
    only_a   = cnt_a - overlap
    only_b   = cnt_b - overlap

    return {
        "group_a":  _group_info(safe_id1),
        "group_b":  _group_info(safe_id2),
        "count_a":   cnt_a,
        "count_b":   cnt_b,
        "overlap":   overlap,
        "union":     union,
        "only_a":    only_a,
        "only_b":    only_b,
        "jaccard_pct": jaccard,
        "overlap_pct_of_a": round(overlap / cnt_a * 100, 2) if cnt_a else 0,
        "overlap_pct_of_b": round(overlap / cnt_b * 100, 2) if cnt_b else 0,
    }


def _print_segment_overlap(data: dict, output: Optional[str] = None) -> None:
    """Rich display for segment overlap analysis."""
    if output:
        format_output(data, "json", output)
        return

    ga = data.get("group_a", {})
    gb = data.get("group_b", {})
    cnt_a    = data.get("count_a", 0)
    cnt_b    = data.get("count_b", 0)
    overlap  = data.get("overlap", 0)
    union    = data.get("union", 0)
    jaccard  = data.get("jaccard_pct", 0)

    header = (
        f"[bold cyan]A:[/bold cyan] {ga.get('name')}  [dim]({ga.get('id')} | {ga.get('type')} {ga.get('source')})[/dim]\n"
        f"[bold green]B:[/bold green] {gb.get('name')}  [dim]({gb.get('id')} | {gb.get('type')} {gb.get('source')})[/dim]"
    )
    console.print(Panel(header, title="Segment Overlap Analysis", border_style="cyan"))

    # Venn-style summary
    t = Table(box=rich_box.SIMPLE, header_style="bold")
    t.add_column("Metric")
    t.add_column("Count",        justify="right")
    t.add_column("% of A",       justify="right")
    t.add_column("% of B",       justify="right")

    def _pct(n, d):
        return f"{n/d*100:.1f}%" if d else "-"

    t.add_row("[cyan]Group A[/cyan]",        f"{cnt_a:,}",   "100%",               _pct(cnt_a, cnt_b))
    t.add_row("[green]Group B[/green]",      f"{cnt_b:,}",   _pct(cnt_b, cnt_a),   "100%")
    t.add_row("[bold]Overlap (A∩B)[/bold]",  f"[bold]{overlap:,}[/bold]",
              f"[bold]{data.get('overlap_pct_of_a', 0):.1f}%[/bold]",
              f"[bold]{data.get('overlap_pct_of_b', 0):.1f}%[/bold]")
    t.add_row("Union (A∪B)",                 f"{union:,}",    _pct(union, cnt_a),   _pct(union, cnt_b))
    t.add_row("Only in A",                   f"{data.get('only_a', 0):,}",
              f"{data.get('only_a', 0)/cnt_a*100:.1f}%" if cnt_a else "-", "-")
    t.add_row("Only in B",                   f"{data.get('only_b', 0):,}",
              "-", f"{data.get('only_b', 0)/cnt_b*100:.1f}%" if cnt_b else "-")
    t.add_row("[bold]Jaccard Similarity[/bold]",
              f"[bold yellow]{jaccard:.2f}%[/bold yellow]", "", "")
    console.print(t)

    # Interpretation
    if jaccard >= 50:
        interp = "[green]High overlap — groups are largely the same audience[/green]"
    elif jaccard >= 20:
        interp = "[yellow]Moderate overlap — significant shared audience[/yellow]"
    elif jaccard >= 5:
        interp = "[cyan]Low overlap — mostly distinct audiences[/cyan]"
    else:
        interp = "[dim]Very low overlap — nearly independent audiences[/dim]"
    console.print(f"  {interp}")
    console.print(
        "[dim]Jaccard = |A∩B| / |A∪B|  |  "
        "Data source: t_customer_group_detail (datanow_demoen)[/dim]"
    )


@app.command("overlap")
def segment_overlap(
    id1: int = typer.Option(..., "--id1", help="First segment group ID"),
    id2: int = typer.Option(..., "--id2", help="Second segment group ID"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export result to JSON"),
) -> None:
    """Compute overlap between two customer segments (MCP mode).

    Counts customers in group A, group B, intersection A∩B, and union A∪B.
    Reports Jaccard similarity and exclusive-only members per group.

    Uses t_customer_group_detail (datanow_demoen).

    Examples:
        sh segments overlap --id1=101 --id2=205
        sh segments overlap --id1=101 --id2=205 --output=overlap.json
    """
    config = load_config()

    if config.mode != "mcp":
        print_error("segments overlap requires MCP mode")
        raise typer.Exit(1)

    try:
        data = _mcp_segment_overlap(config, id1, id2)
    except MCPError as e:
        print_error(f"MCP Error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Error: {e}")
        raise typer.Exit(1)

    _print_segment_overlap(data, output)


# =============================================================================
# segments growth — Member-count trend per segment (P3)
# =============================================================================

def _mcp_segment_growth(config, group_id: str, period: str) -> dict:
    """Daily member count trend for one segment from t_customer_group_history."""
    import re as _re
    if not _re.match(r'^[0-9a-zA-Z_\-]{1,64}$', group_id):
        raise ValueError(f"Invalid group_id: {group_id}")

    _period_map = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}
    days = _period_map.get(period, 30)
    from datetime import datetime, timedelta
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )

    with MCPClient(mcp_config) as client:
        client.initialize()

        # Segment meta
        meta = client.query(f"""
            SELECT group_name, group_type, generate_type
            FROM t_customer_group
            WHERE id = '{group_id}' AND delete_flag = 0
            LIMIT 1
        """, database="datanow_demoen")

        # Daily snapshot from history table
        # t_customer_group_history: group_id, snapshot_date (or biz_date), member_bitmap
        history = client.query(f"""
            SELECT
                snapshot_date                              AS day,
                BITMAP_COUNT(BITMAP_UNION(member_bitmap))  AS member_count
            FROM t_customer_group_history
            WHERE group_id = '{group_id}'
              AND snapshot_date >= '{start_date}'
            GROUP BY snapshot_date
            ORDER BY snapshot_date
        """, database="datanow_demoen")

        # Fallback: if history table uses different column names
        if not isinstance(history, list) or not history:
            history = client.query(f"""
                SELECT
                    biz_date                                           AS day,
                    BITMAP_COUNT(BITMAP_UNION(custs_bitnum))           AS member_count
                FROM t_customer_group_history
                WHERE group_id = '{group_id}'
                  AND biz_date >= '{start_date}'
                GROUP BY biz_date
                ORDER BY biz_date
            """, database="datanow_demoen")

    group_name = "—"
    if isinstance(meta, list) and meta:
        group_name = meta[0].get("group_name") or group_id

    rows = history if isinstance(history, list) else []
    return {
        "group_id": group_id,
        "group_name": group_name,
        "period": period,
        "rows": rows,
    }


def _print_segment_growth(data: dict) -> None:
    from rich.table import Table
    from rich import box as rich_box
    from rich.panel import Panel

    rows = data["rows"]
    if not rows:
        console.print("[yellow]No history data found — t_customer_group_history may not have snapshots for this segment[/yellow]")
        return

    counts = [int(r.get("member_count") or 0) for r in rows]
    max_c = max(counts) or 1

    tbl = Table(
        title=f"Segment Growth: {data['group_name']}  ({data['period']})",
        box=rich_box.SIMPLE, header_style="bold cyan",
    )
    tbl.add_column("Date",      style="dim")
    tbl.add_column("Members",   justify="right", style="cyan")
    tbl.add_column("Δ vs prev", justify="right")
    tbl.add_column("Trend",     no_wrap=True)

    prev = None
    for r in rows:
        cnt = int(r.get("member_count") or 0)
        if prev is not None:
            delta = cnt - prev
            delta_str = f"[green]{delta:+,}[/green]" if delta > 0 else (f"[red]{delta:+,}[/red]" if delta < 0 else "—")
        else:
            delta_str = "—"
        bar = "█" * int(cnt / max_c * 20)
        tbl.add_row(str(r.get("day") or "—"), f"{cnt:,}", delta_str, f"[cyan]{bar}[/cyan]")
        prev = cnt

    console.print(tbl)

    if len(counts) >= 2:
        net = counts[-1] - counts[0]
        color = "green" if net >= 0 else "red"
        console.print(Panel(
            f"Start: [bold]{counts[0]:,}[/bold]  →  End: [bold]{counts[-1]:,}[/bold]  "
            f"Net: [{color}]{net:+,}[/{color}]  "
            f"Peak: [bold]{max(counts):,}[/bold]",
            title="Period Summary", border_style="dim",
        ))


@app.command("growth")
def segment_growth(
    group_id: str = typer.Argument(..., help="Segment / group ID"),
    period: str   = typer.Option("30d", "--period", "-p", help="Time period (7d/30d/90d/365d)"),
) -> None:
    """Daily member count trend for a segment from t_customer_group_history (MCP).

    Examples:
        sh segments growth 12345
        sh segments growth 12345 --period=90d
    """
    config = load_config()
    if config.mode != "mcp":
        print_error("segments growth requires MCP mode")
        raise typer.Exit(1)
    try:
        data = _mcp_segment_growth(config, group_id, period)
    except (MCPError, ValueError, Exception) as e:
        print_error(f"Error: {e}"); raise typer.Exit(1)
    _print_segment_growth(data)
