"""Configuration management commands."""

from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from ..config import (
    CONFIG_FILE,
    Config,
    get_config_value,
    load_config,
    save_config,
    set_config_value,
)
from ..output.table import print_dict, print_success, print_error

app = typer.Typer(help="Configuration management commands")
console = Console()


@app.command("init")
def init_config(
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing config"),
) -> None:
    """Initialize configuration file with defaults."""
    if CONFIG_FILE.exists() and not force:
        console.print(f"[yellow]Config file already exists at {CONFIG_FILE}[/yellow]")
        console.print("Use --force to overwrite.")
        raise typer.Exit(1)

    config = Config()
    save_config(config)
    print_success(f"Configuration initialized at {CONFIG_FILE}")


@app.command("show")
def show_config() -> None:
    """Show current configuration."""
    config = load_config()
    data = config.model_dump()

    # Format nested config for display
    flat_config = {}
    for section, values in data.items():
        if isinstance(values, dict):
            for key, value in values.items():
                # Mask API key
                if key == "key" and value:
                    value = value[:4] + "..." + value[-4:] if len(value) > 8 else "***"
                flat_config[f"{section}.{key}"] = value
        else:
            flat_config[section] = values

    console.print(Panel(f"Config file: {CONFIG_FILE}", title="Configuration", border_style="cyan"))
    print_dict(flat_config, key_header="Setting", value_header="Value")


@app.command("get")
def get_config(
    key: str = typer.Argument(..., help="Config key in dot notation (e.g., api.url)"),
) -> None:
    """Get a configuration value."""
    value = get_config_value(key)

    if value is None:
        print_error(f"Config key not found: {key}")
        raise typer.Exit(1)

    # Mask API key
    if "key" in key.lower() and isinstance(value, str) and value:
        value = value[:4] + "..." + value[-4:] if len(value) > 8 else "***"

    console.print(f"[bold]{key}[/bold] = {value}")


@app.command("set")
def set_config(
    key: str = typer.Argument(..., help="Config key in dot notation (e.g., api.url)"),
    value: str = typer.Argument(..., help="Value to set"),
) -> None:
    """Set a configuration value."""
    if set_config_value(key, value):
        print_success(f"Set {key} = {value}")
    else:
        print_error(f"Failed to set {key}")
        raise typer.Exit(1)


@app.command("reset")
def reset_config(
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Reset configuration to defaults."""
    if not confirm:
        confirm = typer.confirm("Reset all configuration to defaults?")

    if confirm:
        config = Config()
        save_config(config)
        print_success("Configuration reset to defaults")
    else:
        console.print("Operation cancelled.")


@app.command("path")
def show_path() -> None:
    """Show configuration file path."""
    console.print(f"Config file: [cyan]{CONFIG_FILE}[/cyan]")
    if CONFIG_FILE.exists():
        console.print("[green]File exists[/green]")
    else:
        console.print("[yellow]File does not exist (using defaults)[/yellow]")
