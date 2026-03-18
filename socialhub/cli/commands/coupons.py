"""Coupon management commands."""

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from ..api.client import APIError, SocialHubClient
from ..config import load_config
from ..output.export import format_output
from ..output.table import create_table, print_dict, print_error, print_list, print_success

app = typer.Typer(help="Coupon management commands")
console = Console()

# Subcommand for coupon rules
rules_app = typer.Typer(help="Coupon rule management")
app.add_typer(rules_app, name="rules")


@rules_app.command("list")
def list_coupon_rules(
    coupon_type: Optional[str] = typer.Option(None, "--type", "-t", help="Type filter (discount, percent, exchange)"),
    limit: int = typer.Option(50, "--limit", "-l", help="Number of records"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
) -> None:
    """List coupon rules."""
    config = load_config()

    if config.mode != "api":
        print_error("Coupons require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.list_coupon_rules(coupon_type=coupon_type, page_size=limit)
            data = result.get("data", {}).get("items", result.get("data", []))
            total = result.get("data", {}).get("total", len(data))
            console.print(f"[dim]Total: {total} coupon rules[/dim]")
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)

    if format == "table" and isinstance(data, list):
        table = create_table(
            title="Coupon Rules",
            columns=["ID", "Name", "Type", "Value", "Min Purchase", "Total", "Used", "Status"],
        )

        for item in data:
            enabled = item.get("enabled", False)
            status = "[green]Enabled[/green]" if enabled else "[red]Disabled[/red]"

            coupon_type = item.get("coupon_type", "")
            if coupon_type == "percent":
                value = f"{item.get('discount_value', 0)}%"
            else:
                value = f"¥{item.get('discount_value', 0):.2f}"

            table.add_row(
                str(item.get("id", "-")),
                str(item.get("name", "-")),
                coupon_type,
                value,
                f"¥{item.get('min_purchase', 0):.2f}",
                f"{item.get('total_count', 0):,}",
                f"{item.get('used_count', 0):,}",
                status,
            )

        console.print(table)
    else:
        format_output(data, format)


@rules_app.command("get")
def get_coupon_rule(
    rule_id: str = typer.Argument(..., help="Coupon rule ID"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
) -> None:
    """Get coupon rule details."""
    config = load_config()

    if config.mode != "api":
        print_error("Coupons require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.get_coupon_rule(rule_id)
            data = result.get("data", result)
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)

    format_output(data, format)


@rules_app.command("create")
def create_coupon_rule(
    config_file: str = typer.Option(..., "--config", "-c", help="Config file path (JSON)"),
) -> None:
    """Create a new coupon rule from config file."""
    config = load_config()

    if config.mode != "api":
        print_error("Coupons require API mode")
        raise typer.Exit(1)

    # Load config
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            rule_config = json.load(f)
    except Exception as e:
        print_error(f"Failed to read config file: {e}")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.create_coupon_rule(rule_config)
            data = result.get("data", result)

            print_success(f"Coupon rule created: {data.get('id', 'Unknown')}")
            print_dict(data)
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)


@app.command("list")
def list_coupons(
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Status filter (unused, used, expired)"),
    limit: int = typer.Option(50, "--limit", "-l", help="Number of records"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
) -> None:
    """List coupon instances."""
    config = load_config()

    if config.mode != "api":
        print_error("Coupons require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.list_coupons(status=status, page_size=limit)
            data = result.get("data", {}).get("items", result.get("data", []))
            total = result.get("data", {}).get("total", len(data))
            console.print(f"[dim]Total: {total} coupons[/dim]")
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)

    if format == "table" and isinstance(data, list):
        table = create_table(
            title="Coupons",
            columns=["ID", "Code", "Rule ID", "Status", "Customer", "Used At", "Order ID"],
        )

        status_colors = {
            "unused": "cyan",
            "used": "green",
            "expired": "dim",
        }

        for item in data:
            status_val = item.get("status", "unknown")
            color = status_colors.get(status_val, "white")

            table.add_row(
                str(item.get("id", "-")),
                str(item.get("code", "-")),
                str(item.get("rule_id", "-")),
                f"[{color}]{status_val}[/{color}]",
                str(item.get("customer_id", "-")),
                str(item.get("used_at", "-"))[:16] if item.get("used_at") else "-",
                str(item.get("order_id", "-")),
            )

        console.print(table)
    else:
        format_output(data, format)


@app.command("get")
def get_coupon(
    coupon_id: str = typer.Argument(..., help="Coupon ID"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
) -> None:
    """Get coupon details."""
    config = load_config()

    if config.mode != "api":
        print_error("Coupons require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.get_coupon(coupon_id)
            data = result.get("data", result)
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)

    format_output(data, format)


@app.command("analysis")
def analyze_coupon(
    rule_id: str = typer.Argument(..., help="Coupon rule ID"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
) -> None:
    """Analyze coupon rule usage and ROI."""
    config = load_config()

    if config.mode != "api":
        print_error("Coupons require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.get_coupon_analysis(rule_id)
            data = result.get("data", result)
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)

    if format == "json":
        console.print_json(json.dumps(data, default=str))
    else:
        # Pretty print analysis
        if "rule" in data:
            print_dict(data["rule"], title="Coupon Rule")

        if "usage" in data:
            console.print()
            print_dict(data["usage"], title="Usage Statistics")

        if "roi" in data:
            console.print()
            print_dict(data["roi"], title="ROI Analysis")

        # Show usage rate as progress bar
        if "total_count" in data and "used_count" in data:
            total = data["total_count"]
            used = data["used_count"]
            if total > 0:
                rate = used / total * 100
                bar_width = 30
                filled = int(rate / 100 * bar_width)
                bar = "█" * filled + "░" * (bar_width - filled)
                console.print(f"\n[bold]Usage Rate:[/bold] [{rate:.1f}%] {bar}")
