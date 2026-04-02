"""SocialHub.AI CLI - Main entry point."""

import json
import sys
from pathlib import Path

# Windows GBK terminals can't encode characters like ¥ (U+00A5).
# Reconfigure stdout/stderr to UTF-8 so Rich renders correctly.
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import __version__
from .commands import (
    ai,
    analytics,
    auth,
    campaigns,
    config_cmd,
    coupons,
    customers,
    heartbeat,
    history,
    mcp,
    members,
    messages,
    points,
    schema,
    segments,
    session_cmd,
    skills,
    tags,
    trace_cmd,
    workflow,
)

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
app.add_typer(auth.app, name="auth", help="Authentication management")
app.add_typer(ai.app, name="ai", help="AI assistant (natural language interface)")
app.add_typer(skills.app, name="skills", help="Skills Store - Install official skills")
app.add_typer(skills.app, name="skill", help="Skills Store (alias)", hidden=True)
app.add_typer(mcp.app, name="mcp", help="MCP analytics database (connect to SocialHub.AI)")
app.add_typer(schema.app, name="schema", help="Warehouse schema explorer - discover tables and fields")
app.add_typer(heartbeat.app, name="heartbeat", help="Scheduled task management")
app.add_typer(history.app, name="history", help="Run history: list, inspect, and replay past commands")
app.add_typer(workflow.app, name="workflow", help="Business workflow shortcuts (daily-brief, etc.)")
app.add_typer(session_cmd.app, name="session", help="Manage AI conversation sessions")
app.add_typer(trace_cmd.app, name="trace", help="View and manage AI decision traces")

# Derive valid commands from registered groups — single source of truth
VALID_COMMANDS = (
    {g.name for g in app.registered_groups if g.name}
    | {"--help", "-h", "--version", "-v"}
)


def version_callback(value: bool) -> None:
    """Show version and exit."""
    if value:
        console.print(f"SocialHub.AI CLI v{__version__}")
        raise typer.Exit()


# Commands exempt from OAuth2 auth gate
_AUTH_EXEMPT_COMMANDS = {"auth", "config", "--help", "-h", "--version", "-v"}


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
    output_format: str = typer.Option(
        "text",
        "--output-format",
        help="Output format",
        metavar="FORMAT",
        show_default=True,
    ),
    session_id: str = typer.Option(
        None,
        "-c",
        "--session",
        help="Session ID for conversation continuation",
        metavar="SESSION_ID",
    ),
) -> None:
    """
    SocialHub.AI CLI - Customer Intelligence Platform

    A command-line tool for data analysts and marketing managers to:

    - Query and generate reports
    - Manage marketing campaigns
    - Analyze customer segments
    - Track points and coupons

    Use [bold]sh <command> --help[/bold] for more information on a specific command.
    """
    _run_auth_gate()
    obj = ctx.ensure_object(dict)
    obj["output_format"] = output_format
    obj["session_id"] = session_id

def _run_auth_gate() -> None:
    """Run OAuth2 auth gate for registered commands (Typer path)."""
    args = sys.argv[1:]
    if not args:
        return
    first_arg = args[0]
    if first_arg in _AUTH_EXEMPT_COMMANDS:
        return
    from .auth.gate import ensure_authenticated

    ensure_authenticated()


def load_history() -> dict:
    """Load command history from file."""
    try:
        if HISTORY_FILE.exists():
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
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
    except (OSError, json.JSONDecodeError):
        pass


REPEAT_PHRASES = {
    "repeat", "again", "retry", "redo", "run again",
    "execute again", "one more time", "!!"
}


def show_welcome() -> None:
    """Display welcome banner."""
    logo = """
  ____             _       _ _   _       _        _    ___
 / ___|  ___   ___(_) __ _| | | | |_   _| |__    / \\  |_ _|
 \\___ \\ / _ \\ / __| |/ _` | | |_| | | | | '_ \\  / _ \\  | |
  ___) | (_) | (__| | (_| | |  _  | |_| | |_) |/ ___ \\ | |
 |____/ \\___/ \\___|_|\\__,_|_|_| |_|\\__,_|_.__//_/   \\_\\___|
    """

    logo_text = Text(logo, style="bold cyan")

    info = Text()
    info.append(f"v{__version__}", style="dim")
    info.append(" | ", style="dim")
    info.append("Customer Intelligence Platform", style="italic")

    quick_start = Table(show_header=False, box=None, padding=(0, 2))
    quick_start.add_column("Command", style="green")
    quick_start.add_column("Description", style="dim")

    quick_start.add_row("sh analytics overview", "Business overview")
    quick_start.add_row("sh analytics orders", "Order analysis")
    quick_start.add_row("sh mcp sql", "Interactive SQL")
    quick_start.add_row("sh ai chat \"...\"", "AI assistant")
    quick_start.add_row("sh <query>", "Smart mode")
    quick_start.add_row("sh --help", "All commands")

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

    if not args:
        show_welcome()
        return

    first_arg = args[0]
    if first_arg in VALID_COMMANDS:
        app()
        return

    # Extract -c/--session flag from args before building the query string,
    # so the session flag is not accidentally included in the NL query sent to AI.
    _session_id_early: str = None
    clean_args = []
    _skip_next = False
    for _i, _a in enumerate(args):
        if _skip_next:
            _skip_next = False
            continue
        if _a in ("-c", "--session") and _i + 1 < len(args):
            _session_id_early = args[_i + 1]
            _skip_next = True
        else:
            clean_args.append(_a)
    query = " ".join(clean_args)

    query_lower = query.lower().strip()
    if query_lower in REPEAT_PHRASES or any(p in query_lower for p in REPEAT_PHRASES):
        history = load_history()
        last_query = history.get("last_query", "")
        last_commands = history.get("last_commands", [])

        if last_commands:
            console.print("\n[dim]Re-executing last command...[/dim]")
            from .ai import execute_command

            for cmd in last_commands:
                console.print(f"\n[cyan]Executing: {cmd}[/cyan]\n")
                success, output = execute_command(cmd)
                if output:
                    console.print(output)
            return
        elif last_query:
            query = last_query
            console.print(f"\n[dim]Re-executing: {query}[/dim]")
        else:
            console.print("[yellow]No previous command found. Please enter a query.[/yellow]")
            return

    console.print(f"\n[dim]Smart mode: {query}[/dim]")

    # Auth gate for smart-mode (natural language path bypasses Typer callback)
    from .auth.gate import ensure_authenticated

    ensure_authenticated()

    try:
        import re

        from .ai import (
            call_ai_api,
            execute_command,
            execute_plan,
            extract_plan_steps,
            extract_scheduled_task,
            save_scheduled_task,
        )
        from .ai.sanitizer import sanitize_user_input, validate_input_length

        ok, msg = validate_input_length(query)
        if not ok:
            console.print(f"[red]Input too long ({len(query)} chars, limit 2000). Please shorten your query.[/red]")
            return
        query = sanitize_user_input(query)

        session_history = None
        session = None
        _session_id = _session_id_early  # extracted above before query was built

        if _session_id:
            from .ai.session import SessionStore

            store = SessionStore()
            session = store.load(_session_id)
            if session is None:
                console.print(
                    f"[yellow]Session '{_session_id}' not found or expired. Starting fresh.[/yellow]"
                )
            else:
                session_history = session.get_history()

        response, _usage = call_ai_api(query, session_history=session_history)

        if response.startswith("Error:"):
            console.print(f"[red]{response}[/red]")
            return

        if _session_id and session is not None:
            from .config import load_config as _load_cfg
            session.add_turn(query, response, max_history=_load_cfg().session.max_history)
            store.save(session)

        scheduled_task = extract_scheduled_task(response)
        if scheduled_task:
            display_response = re.sub(r"\[SCHEDULE_TASK\].*?\[/SCHEDULE_TASK\]", "", response, flags=re.DOTALL)
            from rich.markdown import Markdown

            console.print(Panel(Markdown(display_response), title="AI Assistant - Scheduled Task", border_style="green"))
            console.print("\n[bold]Scheduled task detected:[/bold]")
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

        steps = extract_plan_steps(response)
        from rich.markdown import Markdown

        if steps:
            display_response = response.replace("[PLAN_START]", "").replace("[PLAN_END]", "")
            console.print(Panel(Markdown(display_response), title="AI Assistant - Analysis Plan", border_style="cyan"))
            console.print(f"\n[bold]Detected {len(steps)} execution steps:[/bold]")
            for step in steps:
                console.print(f"  {step['number']}. {step['description']}")

            console.print()
            if typer.confirm("Execute this plan?", default=True):
                commands = [step["command"] for step in steps]
                save_history(query, commands)
                execute_plan(
                    steps,
                    original_query=query,
                    session_id=_session_id or "",
                    prompt_tokens=(_usage or {}).get("prompt_tokens", 0),
                    completion_tokens=(_usage or {}).get("completion_tokens", 0),
                )
            else:
                console.print("[yellow]Plan not executed. You can run the commands manually.[/yellow]")
        else:
            console.print(Panel(Markdown(response), title="AI Assistant", border_style="cyan"))

            if "```bash" in response:
                commands = re.findall(r"```bash\n(.*?)\n```", response, re.DOTALL)
                if commands:
                    cmd = commands[0].strip()
                    if typer.confirm(f"\nExecute command: {cmd}?", default=True):
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
