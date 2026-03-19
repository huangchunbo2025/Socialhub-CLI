"""SocialHub.AI CLI - Main entry point."""

import sys
import typer
from rich.console import Console

from . import __version__
from .commands import ai, analytics, campaigns, config_cmd, coupons, customers, messages, points, segments, skills, tags

# Create main app
app = typer.Typer(
    name="sh",
    help="SocialHub.AI CLI - Customer Engagement Platform command line tool",
    no_args_is_help=False,
    rich_markup_mode="rich",
)

console = Console()

# Valid CLI commands
VALID_COMMANDS = {
    "analytics", "customers", "segments", "tags", "campaigns",
    "coupons", "points", "messages", "config", "ai", "skills",
    "--help", "-h", "--version", "-v"
}

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
app.add_typer(skills.app, name="skills", help="Skills Store - Install official skills")


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
    """CLI entry point with smart natural language detection."""
    args = sys.argv[1:]

    # No arguments - show help
    if not args:
        app()
        return

    first_arg = args[0]

    # Check if it's a valid command
    if first_arg in VALID_COMMANDS:
        app()
        return

    # Otherwise, treat as natural language query
    # Join all arguments as the query
    query = " ".join(args)
    console.print(f"\n[dim]智能识别: {query}[/dim]")

    # Call AI to process and execute
    from .commands.ai import call_ai_api, SYSTEM_PROMPT
    import subprocess
    import re

    response = call_ai_api(query)

    # Display response
    from rich.panel import Panel
    from rich.markdown import Markdown
    console.print(Panel(Markdown(response), title="AI 助手", border_style="cyan"))

    # Extract and execute command
    if "```bash" in response:
        commands = re.findall(r"```bash\n(.*?)\n```", response, re.DOTALL)
        if commands:
            cmd = commands[0].strip()
            if typer.confirm(f"\n执行命令: {cmd}?", default=True):
                python_exe = sys.executable
                if cmd.startswith("sh "):
                    cmd = cmd.replace("sh ", f'"{python_exe}" -m socialhub.cli.main ', 1)
                console.print(f"\n[dim]执行: {cmd}[/dim]\n")
                subprocess.run(cmd, shell=True)


if __name__ == "__main__":
    cli()
