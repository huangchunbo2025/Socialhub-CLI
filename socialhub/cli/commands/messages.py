"""Message management commands."""

import json
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from ..api.client import APIError, SocialHubClient
from ..config import load_config
from ..output.chart import create_bar_chart
from ..output.export import format_output
from ..output.table import create_table, print_dict, print_error, print_list, print_success

app = typer.Typer(help="Message management commands")
console = Console()

# Subcommand for message templates
templates_app = typer.Typer(help="Message template management")
app.add_typer(templates_app, name="templates")


@templates_app.command("list")
def list_message_templates(
    channel: Optional[str] = typer.Option(None, "--channel", "-c", help="Channel filter (sms, email, wechat, app_push)"),
    limit: int = typer.Option(50, "--limit", "-l", help="Number of records"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
) -> None:
    """List message templates."""
    config = load_config()

    if config.mode != "api":
        print_error("Messages require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.list_message_templates(channel=channel, page_size=limit)
            data = result.get("data", {}).get("items", result.get("data", []))
            total = result.get("data", {}).get("total", len(data))
            console.print(f"[dim]Total: {total} templates[/dim]")
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)

    if format == "table" and isinstance(data, list):
        table = create_table(
            title="Message Templates",
            columns=["ID", "Name", "Channel", "Variables", "Status"],
        )

        channel_icons = {
            "sms": "📱",
            "email": "📧",
            "wechat": "💬",
            "app_push": "🔔",
        }

        for item in data:
            enabled = item.get("enabled", False)
            status = "[green]Enabled[/green]" if enabled else "[red]Disabled[/red]"
            channel_val = item.get("channel", "")
            icon = channel_icons.get(channel_val, "")

            variables = item.get("variables", [])
            var_str = ", ".join(variables[:3])
            if len(variables) > 3:
                var_str += f" (+{len(variables) - 3})"

            table.add_row(
                str(item.get("id", "-")),
                str(item.get("name", "-")),
                f"{icon} {channel_val}",
                var_str or "-",
                status,
            )

        console.print(table)
    else:
        format_output(data, format)


@templates_app.command("get")
def get_message_template(
    template_id: str = typer.Argument(..., help="Template ID"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
) -> None:
    """Get message template details."""
    config = load_config()

    if config.mode != "api":
        print_error("Messages require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.get_message_template(template_id)
            data = result.get("data", result)
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)

    if format == "json":
        console.print_json(json.dumps(data, default=str))
    else:
        # Pretty display template
        console.print(Panel(
            f"[bold]Name:[/bold] {data.get('name', '-')}\n"
            f"[bold]Channel:[/bold] {data.get('channel', '-')}\n"
            f"[bold]Status:[/bold] {'Enabled' if data.get('enabled') else 'Disabled'}",
            title=f"Template: {template_id}",
            border_style="cyan",
        ))

        if "content" in data:
            console.print("\n[bold]Content:[/bold]")
            console.print(Panel(data["content"], border_style="dim"))

        if "variables" in data and data["variables"]:
            console.print("\n[bold]Variables:[/bold]")
            for var in data["variables"]:
                console.print(f"  • [cyan]{{{{{var}}}}}[/cyan]")


@app.command("records")
def list_message_records(
    channel: Optional[str] = typer.Option(None, "--channel", "-c", help="Channel filter"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Status filter (success, failed, pending)"),
    limit: int = typer.Option(50, "--limit", "-l", help="Number of records"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
) -> None:
    """List message send records."""
    config = load_config()

    if config.mode != "api":
        print_error("Messages require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.list_message_records(
                channel=channel,
                status=status,
                page_size=limit,
            )
            data = result.get("data", {}).get("items", result.get("data", []))
            total = result.get("data", {}).get("total", len(data))
            console.print(f"[dim]Total: {total} records[/dim]")
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)

    if format == "table" and isinstance(data, list):
        table = create_table(
            title="Message Records",
            columns=["ID", "Template", "Channel", "Recipient", "Status", "Sent At"],
        )

        status_colors = {
            "success": "green",
            "delivered": "green",
            "failed": "red",
            "pending": "yellow",
            "sending": "cyan",
        }

        for item in data:
            status_val = item.get("status", "unknown")
            color = status_colors.get(status_val, "white")

            table.add_row(
                str(item.get("id", "-")),
                str(item.get("template_name", item.get("template_id", "-"))),
                str(item.get("channel", "-")),
                str(item.get("recipient", "-")),
                f"[{color}]{status_val}[/{color}]",
                str(item.get("sent_at", "-"))[:16] if item.get("sent_at") else "-",
            )

        console.print(table)
    else:
        format_output(data, format)


@app.command("stats")
def get_message_stats(
    period: str = typer.Option("7d", "--period", "-p", help="Time period"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
) -> None:
    """Get message delivery statistics."""
    config = load_config()

    if config.mode != "api":
        print_error("Messages require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.get_message_stats(period=period)
            data = result.get("data", result)
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)

    if format == "json":
        console.print_json(json.dumps(data, default=str))
    else:
        # Pretty display stats
        console.print(f"\n[bold]Message Statistics ({period})[/bold]\n")

        # Overall stats
        if "total" in data:
            print_dict({
                "Total Sent": data.get("total", 0),
                "Success": data.get("success", 0),
                "Failed": data.get("failed", 0),
                "Success Rate": f"{data.get('success_rate', 0):.1f}%",
            }, title="Overview")

        # By channel
        if "by_channel" in data and isinstance(data["by_channel"], dict):
            console.print()
            create_bar_chart(
                data["by_channel"],
                title="Messages by Channel",
                color="cyan",
            )

        # By day
        if "by_day" in data and isinstance(data["by_day"], dict):
            console.print()
            create_bar_chart(
                data["by_day"],
                title="Messages by Day",
                color="green",
            )
