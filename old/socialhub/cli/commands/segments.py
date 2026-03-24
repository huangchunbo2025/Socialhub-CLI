"""Segment management commands."""

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from ..api.client import APIError, SocialHubClient
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
