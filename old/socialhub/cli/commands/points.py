"""Points management commands."""

import json
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from ..api.client import APIError, SocialHubClient
from ..config import load_config
from ..output.export import format_output
from ..output.table import create_table, print_dict, print_error, print_list, print_success

app = typer.Typer(help="Points program management commands")
console = Console()

# Subcommand for points rules
rules_app = typer.Typer(help="Points rule management")
app.add_typer(rules_app, name="rules")


@rules_app.command("list")
def list_points_rules(
    rule_type: Optional[str] = typer.Option(None, "--type", "-t", help="Type filter (basic, promo)"),
    limit: int = typer.Option(50, "--limit", "-l", help="Number of records"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
) -> None:
    """List points rules."""
    config = load_config()

    if config.mode != "api":
        print_error("Points require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.list_points_rules(rule_type=rule_type, page_size=limit)
            data = result.get("data", {}).get("items", result.get("data", []))
            total = result.get("data", {}).get("total", len(data))
            console.print(f"[dim]Total: {total} points rules[/dim]")
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)

    if format == "table" and isinstance(data, list):
        table = create_table(
            title="Points Rules",
            columns=["ID", "Name", "Type", "Points/Yuan", "Multiplier", "Status"],
        )

        for item in data:
            enabled = item.get("enabled", False)
            status = "[green]Enabled[/green]" if enabled else "[red]Disabled[/red]"

            table.add_row(
                str(item.get("id", "-")),
                str(item.get("name", "-")),
                str(item.get("rule_type", "-")),
                f"{item.get('points_per_yuan', 1):.1f}",
                f"{item.get('multiplier', 1):.1f}x",
                status,
            )

        console.print(table)
    else:
        format_output(data, format)


@rules_app.command("get")
def get_points_rule(
    rule_id: str = typer.Argument(..., help="Points rule ID"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
) -> None:
    """Get points rule details."""
    config = load_config()

    if config.mode != "api":
        print_error("Points require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.get_points_rule(rule_id)
            data = result.get("data", result)
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)

    format_output(data, format)


@app.command("balance")
def get_points_balance(
    member_id: str = typer.Argument(..., help="Member ID"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
) -> None:
    """Get member points balance."""
    config = load_config()

    if config.mode != "api":
        print_error("Points require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.get_points_balance(member_id)
            data = result.get("data", result)
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)

    if format == "json":
        console.print_json(json.dumps(data, default=str))
    else:
        # Pretty display
        balance = data.get("balance", 0)
        pending = data.get("pending", 0)
        expiring = data.get("expiring_soon", 0)

        console.print(Panel(
            f"[bold green]{balance:,}[/bold green] points\n"
            f"[dim]Pending: {pending:,}[/dim]\n"
            f"[yellow]Expiring soon: {expiring:,}[/yellow]",
            title=f"Points Balance: {member_id}",
            border_style="cyan",
        ))

        if "tier" in data:
            console.print(f"\n[bold]Membership Tier:[/bold] {data['tier']}")


@app.command("history")
def get_points_history(
    member_id: str = typer.Argument(..., help="Member ID"),
    limit: int = typer.Option(50, "--limit", "-l", help="Number of records"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
) -> None:
    """Get member points transaction history."""
    config = load_config()

    if config.mode != "api":
        print_error("Points require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.get_points_history(member_id, page_size=limit)
            data = result.get("data", {}).get("items", result.get("data", []))
            total = result.get("data", {}).get("total", len(data))
            console.print(f"[dim]Total: {total} transactions[/dim]")
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)

    if format == "table" and isinstance(data, list):
        table = create_table(
            title=f"Points History: {member_id}",
            columns=["Date", "Type", "Points", "Description", "Balance After"],
        )

        for item in data:
            points = item.get("points", 0)
            if points >= 0:
                points_str = f"[green]+{points:,}[/green]"
            else:
                points_str = f"[red]{points:,}[/red]"

            table.add_row(
                str(item.get("created_at", "-"))[:16] if item.get("created_at") else "-",
                str(item.get("type", "-")),
                points_str,
                str(item.get("description", "-"))[:30],
                f"{item.get('balance_after', 0):,}",
            )

        console.print(table)
    else:
        format_output(data, format)
