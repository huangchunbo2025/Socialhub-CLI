"""Tag management commands."""

import json
from typing import Optional

import typer
from rich.console import Console

from ..api.client import APIError, SocialHubClient
from ..api.mcp_client import MCPClient, MCPConfig as MCPClientConfig, MCPError
from ..config import load_config
from ..output.export import format_output
from ..output.table import print_dict, print_error, print_list, print_success

app = typer.Typer(help="Tag management commands")
console = Console()


@app.command("list")
def list_tags(
    group: Optional[str] = typer.Option(None, "--group", "-g", help="Tag group filter"),
    tag_type: Optional[str] = typer.Option(None, "--type", "-t", help="Tag type (rfm, aipl, static, computed)"),
    limit: int = typer.Option(50, "--limit", "-l", help="Number of records"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
) -> None:
    """List tags."""
    config = load_config()

    if config.mode != "api":
        print_error("Tags require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.list_tags(group=group, tag_type=tag_type, page_size=limit)
            data = result.get("data", {}).get("items", result.get("data", []))
            total = result.get("data", {}).get("total", len(data))
            console.print(f"[dim]Total: {total} tags[/dim]")
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)

    format_output(data, format)


@app.command("get")
def get_tag(
    tag_id: str = typer.Argument(..., help="Tag ID"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
) -> None:
    """Get tag details."""
    config = load_config()

    if config.mode != "api":
        print_error("Tags require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.get_tag(tag_id)
            data = result.get("data", result)
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)

    format_output(data, format)


@app.command("analysis")
def analyze_tag(
    tag_id: str = typer.Argument(..., help="Tag ID"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
) -> None:
    """Analyze tag distribution and usage."""
    config = load_config()

    if config.mode != "api":
        print_error("Tags require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.get_tag_analysis(tag_id)
            data = result.get("data", result)
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)

    if format == "json":
        console.print_json(json.dumps(data, default=str))
    else:
        # Pretty print analysis
        if "tag" in data:
            print_dict(data["tag"], title="Tag Info")

        if "distribution" in data:
            console.print("\n[bold]Value Distribution:[/bold]")
            print_list(data["distribution"])

        if "summary" in data:
            print_dict(data["summary"], title="Summary")


@app.command("create")
def create_tag(
    name: str = typer.Option(..., "--name", "-n", help="Tag name"),
    tag_type: str = typer.Option("static", "--type", "-t", help="Tag type (rfm, aipl, static, computed)"),
    values: str = typer.Option(..., "--values", "-v", help="Comma-separated tag values"),
    group: Optional[str] = typer.Option(None, "--group", "-g", help="Tag group"),
) -> None:
    """Create a new tag."""
    config = load_config()

    if config.mode != "api":
        print_error("Tags require API mode")
        raise typer.Exit(1)

    # Parse values
    values_list = [v.strip() for v in values.split(",") if v.strip()]

    try:
        with SocialHubClient() as client:
            result = client.create_tag(
                name=name,
                tag_type=tag_type,
                values=values_list,
                group=group,
            )
            data = result.get("data", result)

            print_success(f"Tag created: {data.get('id', 'Unknown')}")
            print_dict(data)
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)


@app.command("update")
def update_tag(
    tag_id: str = typer.Argument(..., help="Tag ID"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="New tag name"),
    values: Optional[str] = typer.Option(None, "--values", "-v", help="New comma-separated values"),
    group: Optional[str] = typer.Option(None, "--group", "-g", help="New tag group"),
) -> None:
    """Update a tag."""
    config = load_config()

    if config.mode != "api":
        print_error("Tags require API mode")
        raise typer.Exit(1)

    # Build update data
    update_data = {}
    if name:
        update_data["name"] = name
    if values:
        update_data["values"] = [v.strip() for v in values.split(",") if v.strip()]
    if group:
        update_data["group"] = group

    if not update_data:
        print_error("No update fields specified")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.put(f"/api/v1/tags/{tag_id}", update_data)
            data = result.get("data", result)

            print_success(f"Tag {tag_id} updated")
            print_dict(data)
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)


@app.command("enable")
def enable_tag(
    tag_id: str = typer.Argument(..., help="Tag ID"),
) -> None:
    """Enable a tag."""
    config = load_config()

    if config.mode != "api":
        print_error("Tags require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            client.enable_tag(tag_id)
            print_success(f"Tag {tag_id} enabled")
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)


@app.command("disable")
def disable_tag(
    tag_id: str = typer.Argument(..., help="Tag ID"),
) -> None:
    """Disable a tag."""
    config = load_config()

    if config.mode != "api":
        print_error("Tags require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            client.disable_tag(tag_id)
            print_success(f"Tag {tag_id} disabled")
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)


# =============================================================================
# tags coverage — Tag distribution & coverage audit (P3)
# =============================================================================

def _mcp_tags_coverage(config, limit: int) -> list:
    """Coverage and value distribution for all tags from t_customer_tag_result."""
    from ..api.mcp_client import MCPClient, MCPConfig as MCPClientConfig, MCPError
    if not isinstance(limit, int) or limit < 1 or limit > 200:
        limit = 30

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )

    with MCPClient(mcp_config) as client:
        client.initialize()

        # Total customers for coverage %
        total_res = client.query(
            "SELECT COUNT(*) AS total FROM dim_customer_info",
            database=config.mcp.database,
        )
        total_custs = total_res[0].get("total", 0) if isinstance(total_res, list) and total_res else 0

        # Per-tag: customer count + distinct values
        rows = client.query(f"""
            SELECT
                tag_id,
                COUNT(DISTINCT customer_code)   AS covered_customers,
                COUNT(DISTINCT tag_value)        AS distinct_values,
                COUNT(*)                         AS total_assignments
            FROM t_customer_tag_result
            GROUP BY tag_id
            ORDER BY covered_customers DESC
            LIMIT {limit}
        """, database="datanow_demoen")

        # Top values per tag (top 3)
        top_values = client.query(f"""
            SELECT
                tag_id,
                tag_value,
                COUNT(DISTINCT customer_code) AS cnt
            FROM t_customer_tag_result
            GROUP BY tag_id, tag_value
            QUALIFY ROW_NUMBER() OVER (PARTITION BY tag_id ORDER BY cnt DESC) <= 3
            ORDER BY tag_id, cnt DESC
            LIMIT 10000
        """, database="datanow_demoen")

    # Build top-values map
    tv_map: dict = {}
    if isinstance(top_values, list):
        for r in top_values:
            tid = r.get("tag_id")
            if tid not in tv_map:
                tv_map[tid] = []
            tv_map[tid].append(f"{r.get('tag_value')}({r.get('cnt'):,})")

    result = []
    if isinstance(rows, list):
        for r in rows:
            tid = r.get("tag_id")
            covered = int(r.get("covered_customers") or 0)
            result.append({
                "tag_id": tid,
                "covered_customers": covered,
                "coverage_pct": f"{covered/total_custs*100:.1f}%" if total_custs else "—",
                "distinct_values": int(r.get("distinct_values") or 0),
                "total_assignments": int(r.get("total_assignments") or 0),
                "top_values": " / ".join(tv_map.get(tid, [])),
            })
    return result


def _print_tags_coverage(rows: list) -> None:
    from rich.table import Table
    from rich import box as rich_box

    if not rows:
        console.print("[yellow]No tag data found in t_customer_tag_result[/yellow]")
        return

    tbl = Table(title="Tag Coverage Audit", box=rich_box.SIMPLE_HEAVY, header_style="bold cyan")
    tbl.add_column("Tag ID",      style="dim", max_width=20)
    tbl.add_column("Covered",     justify="right", style="cyan")
    tbl.add_column("Coverage %",  justify="right")
    tbl.add_column("# Values",    justify="right")
    tbl.add_column("Assignments", justify="right")
    tbl.add_column("Top Values",  max_width=40, style="dim")

    for r in rows:
        pct = r["coverage_pct"]
        try:
            pct_f = float(pct.rstrip("%"))
            color = "green" if pct_f >= 80 else ("yellow" if pct_f >= 40 else "red")
        except Exception:
            color = "white"
        tbl.add_row(
            str(r["tag_id"]),
            f"{r['covered_customers']:,}",
            f"[{color}]{pct}[/{color}]",
            f"{r['distinct_values']:,}",
            f"{r['total_assignments']:,}",
            r["top_values"] or "—",
        )
    console.print(tbl)
    console.print("[dim]Coverage % = covered customers / total dim_customer_info. Green ≥80% Yellow ≥40% Red <40%[/dim]")


@app.command("coverage")
def tags_coverage(
    limit: int = typer.Option(30, "--limit", "-n", help="Max tags to show (1-200)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export JSON"),
) -> None:
    """Tag coverage and top-value distribution from t_customer_tag_result (MCP).

    Shows for each tag: how many customers are tagged (and as % of total),
    number of distinct values, and the top 3 most common values.

    Examples:
        sh tags coverage
        sh tags coverage --limit=50
    """
    config = load_config()
    if config.mode != "mcp":
        print_error("tags coverage requires MCP mode")
        raise typer.Exit(1)
    try:
        rows = _mcp_tags_coverage(config, limit)
    except (MCPError, Exception) as e:
        print_error(f"Error: {e}")
        raise typer.Exit(1)
    if output:
        format_output(rows, "json", output)
    else:
        _print_tags_coverage(rows)
