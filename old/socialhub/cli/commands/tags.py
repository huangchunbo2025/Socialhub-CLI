"""Tag management commands."""

import json
from typing import Optional

import typer
from rich.console import Console

from ..api.client import APIError, SocialHubClient
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
