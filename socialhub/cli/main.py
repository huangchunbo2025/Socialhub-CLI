"""SocialHub.AI CLI - Main entry point."""

import typer
from rich.console import Console

from . import __version__
from .commands import ai, analytics, campaigns, config_cmd, coupons, customers, messages, points, segments, tags

# Create main app
app = typer.Typer(
    name="sh",
    help="SocialHub.AI CLI - Customer Engagement Platform command line tool",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

console = Console()

# Register command groups
app.add_typer(analytics.app, name="analytics", help="Data analytics commands")
app.add_typer(customers.app, name="customers", help="Customer management commands")
app.add_typer(segments.app, name="segments", help="Customer segment commands")
app.add_typer(tags.app, name="tags", help="Tag management commands")
app.add_typer(campaigns.app, name="campaigns", help="Marketing campaign commands")
app.add_typer(coupons.app, name="coupons", help="Coupon management commands")
app.add_typer(points.app, name="points", help="Points program commands")
app.add_typer(messages.app, name="messages", help="Message management commands")
app.add_typer(config_cmd.app, name="config", help="Configuration management")
app.add_typer(ai.app, name="ai", help="AI assistant (natural language interface)")


def version_callback(value: bool) -> None:
    """Show version and exit."""
    if value:
        console.print(f"SocialHub.AI CLI v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
) -> None:
    """
    SocialHub.AI CLI - Customer Engagement Platform

    A command-line tool for data analysts and marketing managers to:

    • Query and generate reports
    • Manage marketing campaigns
    • Analyze customer segments
    • Track points and coupons

    Use [bold]sh <command> --help[/bold] for more information on a specific command.
    """
    pass


def cli() -> None:
    """CLI entry point."""
    app()


if __name__ == "__main__":
    cli()
