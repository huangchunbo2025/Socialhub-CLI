"""Marketing campaign management commands."""

import json
from datetime import datetime

import typer
from rich.console import Console

from ..api.client import APIError, SocialHubClient
from ..config import load_config
from ..output.export import format_output
from ..output.table import create_table, print_dict, print_error, print_success

app = typer.Typer(help="Marketing campaign management commands")
console = Console()


@app.command("list")
def list_campaigns(
    status: str | None = typer.Option(None, "--status", "-s", help="Status filter (draft, running, paused, finished)"),
    limit: int = typer.Option(50, "--limit", "-l", help="Number of records"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
) -> None:
    """List marketing campaigns."""
    config = load_config()

    if config.mode != "api":
        print_error("Campaigns require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.list_campaigns(status=status, page_size=limit)
            data = result.get("data", {}).get("items", result.get("data", []))
            total = result.get("data", {}).get("total", len(data))
            console.print(f"[dim]Total: {total} campaigns[/dim]")
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)

    if format == "table" and isinstance(data, list):
        # Custom table with status coloring
        table = create_table(
            title="Marketing Campaigns",
            columns=["ID", "Name", "Type", "Status", "Target", "Reached", "Converted", "Start Time"],
        )

        status_colors = {
            "draft": "yellow",
            "pending": "yellow",
            "running": "green",
            "paused": "dim",
            "finished": "blue",
        }

        for item in data:
            status_val = item.get("status", "unknown")
            color = status_colors.get(status_val, "white")

            table.add_row(
                str(item.get("id", "-")),
                str(item.get("name", "-")),
                str(item.get("campaign_type", "-")),
                f"[{color}]{status_val}[/{color}]",
                f"{item.get('target_count', 0):,}",
                f"{item.get('reached_count', 0):,}",
                f"{item.get('converted_count', 0):,}",
                str(item.get("start_time", "-"))[:16] if item.get("start_time") else "-",
            )

        console.print(table)
    else:
        format_output(data, format)


@app.command("get")
def get_campaign(
    campaign_id: str = typer.Argument(..., help="Campaign ID"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
) -> None:
    """Get campaign details."""
    config = load_config()

    if config.mode != "api":
        print_error("Campaigns require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.get_campaign(campaign_id)
            data = result.get("data", result)
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)

    format_output(data, format)


@app.command("analysis")
def analyze_campaign(
    campaign_id: str = typer.Argument(..., help="Campaign ID"),
    funnel: bool = typer.Option(False, "--funnel", help="Show conversion funnel"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
) -> None:
    """Analyze campaign performance."""
    config = load_config()

    if config.mode != "api":
        print_error("Campaigns require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.get_campaign_analysis(campaign_id)
            data = result.get("data", result)
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)

    if funnel and isinstance(data, dict):
        # Display funnel data as table
        funnel_data = {
            "Target": f"{data.get('target_count', 0):,}",
            "Reached": f"{data.get('reached_count', 0):,}",
            "Opened": f"{data.get('opened_count', 0):,}",
            "Clicked": f"{data.get('clicked_count', 0):,}",
            "Converted": f"{data.get('converted_count', 0):,}",
        }
        print_dict(funnel_data, title=f"Campaign Funnel: {data.get('campaign_name', campaign_id)}")

        # Also show ROI metrics
        console.print()
        roi_data = {
            "Revenue": f"¥{data.get('revenue', 0):,.2f}",
            "Cost": f"¥{data.get('cost', 0):,.2f}",
            "ROI": f"{data.get('roi', 0):.2f}%",
        }
        print_dict(roi_data, title="ROI Metrics")
    else:
        format_output(data, format)


@app.command("create")
def create_campaign(
    name: str = typer.Option(..., "--name", "-n", help="Campaign name"),
    campaign_type: str = typer.Option("single", "--type", "-t", help="Campaign type (single, recurring)"),
    config_file: str | None = typer.Option(None, "--config", "-c", help="Config file path (JSON)"),
) -> None:
    """Create a new marketing campaign."""
    config = load_config()

    if config.mode != "api":
        print_error("Campaigns require API mode")
        raise typer.Exit(1)

    # Load additional config from file
    extra_config = {}
    if config_file:
        try:
            with open(config_file, encoding="utf-8") as f:
                extra_config = json.load(f)
        except Exception as e:
            print_error(f"Failed to read config file: {e}")
            raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.create_campaign(
                name=name,
                campaign_type=campaign_type,
                config=extra_config,
            )
            data = result.get("data", result)

            print_success(f"Campaign created: {data.get('id', 'Unknown')}")
            print_dict(data)
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)


@app.command("start")
def start_campaign(
    campaign_id: str = typer.Argument(..., help="Campaign ID"),
) -> None:
    """Start a campaign."""
    config = load_config()

    if config.mode != "api":
        print_error("Campaigns require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            client.start_campaign(campaign_id)
            print_success(f"Campaign {campaign_id} started")
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)


@app.command("end")
def end_campaign(
    campaign_id: str = typer.Argument(..., help="Campaign ID"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """End a running campaign."""
    config = load_config()

    if config.mode != "api":
        print_error("Campaigns require API mode")
        raise typer.Exit(1)

    if not confirm:
        confirm = typer.confirm(f"End campaign {campaign_id}?")

    if not confirm:
        console.print("Operation cancelled.")
        raise typer.Exit(0)

    try:
        with SocialHubClient() as client:
            client.end_campaign(campaign_id)
            print_success(f"Campaign {campaign_id} ended")
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)


@app.command("approve")
def approve_campaign(
    campaign_id: str = typer.Argument(..., help="Campaign ID"),
) -> None:
    """Approve a pending campaign."""
    config = load_config()

    if config.mode != "api":
        print_error("Campaigns require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            client.approve_campaign(campaign_id)
            print_success(f"Campaign {campaign_id} approved")
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)


@app.command("calendar")
def show_calendar(
    month: str = typer.Option(None, "--month", "-m", help="Month (YYYY-MM), defaults to current"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
) -> None:
    """Show marketing campaign calendar."""
    config = load_config()

    if config.mode != "api":
        print_error("Campaigns require API mode")
        raise typer.Exit(1)

    # Default to current month
    if not month:
        month = datetime.now().strftime("%Y-%m")

    try:
        with SocialHubClient() as client:
            result = client.get_campaign_calendar(month)
            data = result.get("data", result)
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)

    if format == "json":
        console.print_json(json.dumps(data, default=str))
    else:
        # Display as calendar view
        console.print(f"\n[bold]Marketing Calendar: {month}[/bold]\n")

        if isinstance(data, list):
            # Group by date
            by_date = {}
            for item in data:
                date_str = str(item.get("start_time", ""))[:10]
                if date_str not in by_date:
                    by_date[date_str] = []
                by_date[date_str].append(item)

            for date_str in sorted(by_date.keys()):
                console.print(f"[cyan]{date_str}[/cyan]")
                for campaign in by_date[date_str]:
                    status = campaign.get("status", "unknown")
                    status_icon = {"running": "🟢", "draft": "🟡", "paused": "⚪", "finished": "🔵"}.get(status, "⚪")
                    console.print(f"  {status_icon} {campaign.get('name', 'Unknown')} [{campaign.get('id', '')}]")
                console.print()
        else:
            format_output(data, "table")
