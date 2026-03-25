"""SocialHub.AI CLI - Main entry point."""

import json
import sys
from pathlib import Path
import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table

from . import __version__
from .commands import ai, analytics, campaigns, config_cmd, coupons, customers, heartbeat, history, mcp, members, messages, points, schema, segments, skills, tags

# History file for storing last command
HISTORY_FILE = Path.home() / ".socialhub" / "history.json"

# Create main app
app = typer.Typer(
    name="sh",
    help="SocialHub.AI CLI - Customer Intelligence Platform command line tool",
    no_args_is_help=False,
    rich_markup_mode="rich",
)

console = Console()

# Valid CLI commands
VALID_COMMANDS = {
    "analytics", "customers", "members", "segments", "tags", "campaigns",
    "coupons", "points", "messages", "config", "ai", "skills", "skill",
    "mcp", "schema", "heartbeat", "history",
    "--help", "-h", "--version", "-v"
}

# Register command groups
app.add_typer(analytics.app, name="analytics", help="Data analytics commands")
app.add_typer(members.app, name="members", help="Member analytics commands")
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
app.add_typer(skills.app, name="skill", help="Skills Store (alias)", hidden=True)  # Alias for 'skills'
app.add_typer(mcp.app, name="mcp", help="MCP analytics database (connect to SocialHub.AI)")
app.add_typer(schema.app, name="schema", help="Warehouse schema explorer — discover tables and fields")
app.add_typer(heartbeat.app, name="heartbeat", help="Scheduled task management")
app.add_typer(history.app, name="history", help="Run history: list, inspect, and replay past commands")


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
    SocialHub.AI CLI - Customer Intelligence Platform

    A command-line tool for data analysts and marketing managers to:

    • Query and generate reports
    • Manage marketing campaigns
    • Analyze customer segments
    • Track points and coupons

    Use [bold]sh <command> --help[/bold] for more information on a specific command.
    """
    pass


def load_history() -> dict:
    """Load command history from file."""
    try:
        if HISTORY_FILE.exists():
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, IOError):
        # Silently ignore history load failures (non-critical)
        pass
    return {"last_query": "", "last_commands": []}


def save_history(query: str, commands: list = None) -> None:
    """Save command to history."""
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        history = load_history()
        history["last_query"] = query
        if commands:
            history["last_commands"] = commands
        HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")
    except (OSError, IOError, json.JSONDecodeError):
        # Silently ignore history save failures (non-critical)
        pass


# Phrases that mean "repeat last command"
REPEAT_PHRASES = {
    "repeat", "again", "retry", "redo", "run again",
    "execute again", "one more time", "!!"
}


def show_welcome() -> None:
    """Display welcome banner."""
    # ASCII art logo - Windows GBK compatible
    logo = """
  ____             _       _ _   _       _        _    ___
 / ___|  ___   ___(_) __ _| | | | |_   _| |__    / \\  |_ _|
 \\___ \\ / _ \\ / __| |/ _` | | |_| | | | | '_ \\  / _ \\  | |
  ___) | (_) | (__| | (_| | |  _  | |_| | |_) |/ ___ \\ | |
 |____/ \\___/ \\___|_|\\__,_|_|_| |_|\\__,_|_.__//_/   \\_\\___|
    """

    # Create styled logo
    logo_text = Text(logo, style="bold cyan")

    # Version and tagline
    info = Text()
    info.append(f"v{__version__}", style="dim")
    info.append(" | ", style="dim")
    info.append("Customer Intelligence Platform", style="italic")

    # Quick start commands table
    quick_start = Table(show_header=False, box=None, padding=(0, 2))
    quick_start.add_column("Command", style="green")
    quick_start.add_column("Description", style="dim")

    quick_start.add_row("socialhub analytics overview", "Business overview")
    quick_start.add_row("socialhub analytics orders", "Order analysis")
    quick_start.add_row("socialhub mcp sql", "Interactive SQL")
    quick_start.add_row("socialhub ai chat \"...\"", "AI assistant")
    quick_start.add_row("socialhub <query>", "Smart mode")
    quick_start.add_row("socialhub --help", "All commands")

    # Print welcome
    console.print()
    console.print(logo_text, justify="center")
    console.print(info, justify="center")
    console.print()
    console.print(Panel(quick_start, title="[bold]Quick Start[/bold]", border_style="blue", padding=(1, 2)))
    console.print()
    console.print("[dim]Enter a command to get started, or type natural language for smart queries[/dim]", justify="center")
    console.print()


def cli() -> None:
    """CLI entry point with smart natural language detection."""
    args = sys.argv[1:]

    # No arguments - show welcome banner
    if not args:
        show_welcome()
        return

    first_arg = args[0]

    # Check if it's a valid command
    if first_arg in VALID_COMMANDS:
        app()
        return

    # Join all arguments as the query
    query = " ".join(args)

    # Check for repeat command phrases
    query_lower = query.lower().strip()
    if query_lower in REPEAT_PHRASES or any(p in query_lower for p in REPEAT_PHRASES):
        history = load_history()
        last_query = history.get("last_query", "")
        last_commands = history.get("last_commands", [])

        if last_commands:
            # Re-execute last commands directly
            console.print(f"\n[dim]Re-executing last command...[/dim]")
            from .commands.ai import execute_command
            for cmd in last_commands:
                console.print(f"\n[cyan]Executing: {cmd}[/cyan]\n")
                success, output = execute_command(cmd)
                if output:
                    console.print(output)
            return
        elif last_query:
            # Use last query
            query = last_query
            console.print(f"\n[dim]Re-executing: {query}[/dim]")
        else:
            console.print("[yellow]No previous command found. Please enter a query.[/yellow]")
            return

    console.print(f"\n[dim]Smart mode: {query}[/dim]")

    try:
        # Call AI to process and execute
        from .commands.ai import call_ai_api, extract_plan_steps, execute_plan, execute_command, extract_scheduled_task, save_scheduled_task
        import re

        response = call_ai_api(query)

        # Check if response indicates an error
        if response.startswith("Error:"):
            console.print(f"[red]{response}[/red]")
            return

        # Check for scheduled task
        scheduled_task = extract_scheduled_task(response)
        if scheduled_task:
            # Display response without markers
            display_response = re.sub(r"\[SCHEDULE_TASK\].*?\[/SCHEDULE_TASK\]", "", response, flags=re.DOTALL)
            from rich.markdown import Markdown
            console.print(Panel(Markdown(display_response), title="AI Assistant - Scheduled Task", border_style="green"))

            console.print(f"\n[bold]Scheduled task detected:[/bold]")
            console.print(f"  Task name: {scheduled_task.get('name', '-')}")
            console.print(f"  Frequency: {scheduled_task.get('frequency', '-')}")
            console.print(f"  Command: {scheduled_task.get('command', '-')}")
            console.print(f"  AI Insights: {scheduled_task.get('insights', 'false')}")
            console.print()

            if typer.confirm("Add this task to Heartbeat.md?", default=True):
                if save_scheduled_task(scheduled_task):
                    console.print("[green][OK] Scheduled task added to Heartbeat.md[/green]")
                else:
                    console.print("[red]Failed to add scheduled task[/red]")
            return

        # Check for multi-step plan
        steps = extract_plan_steps(response)

        # Display response
        from rich.markdown import Markdown

        if steps:
            # Display plan without markers
            display_response = response.replace("[PLAN_START]", "").replace("[PLAN_END]", "")
            console.print(Panel(Markdown(display_response), title="AI Assistant - Analysis Plan", border_style="cyan"))

            # Show step summary and ask for confirmation
            console.print(f"\n[bold]Detected {len(steps)} execution steps:[/bold]")
            for step in steps:
                console.print(f"  {step['number']}. {step['description']}")

            console.print()
            if typer.confirm("Execute this plan?", default=True):
                # Save commands to history before executing
                commands = [step["command"] for step in steps]
                save_history(query, commands)
                execute_plan(steps, original_query=query)
            else:
                console.print("[yellow]Plan not executed. You can run the commands manually.[/yellow]")
        else:
            console.print(Panel(Markdown(response), title="AI Assistant", border_style="cyan"))

            # Extract and execute single command
            if "```bash" in response:
                commands = re.findall(r"```bash\n(.*?)\n```", response, re.DOTALL)
                if commands:
                    cmd = commands[0].strip()
                    if typer.confirm(f"\nExecute command: {cmd}?", default=True):
                        # Save to history
                        save_history(query, [cmd])
                        console.print(f"\n[dim]Executing: {cmd}[/dim]\n")
                        success, output = execute_command(cmd)
                        if output:
                            console.print(output)

    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        console.print("[dim]Please try again or check your network connection.[/dim]")


if __name__ == "__main__":
    cli()
