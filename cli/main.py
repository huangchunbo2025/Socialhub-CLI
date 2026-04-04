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
    memory,
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
app.add_typer(memory.app, name="memory", help="Manage AI memory: preferences, insights, campaigns")

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

# Global options that Typer handles before the sub-command
_GLOBAL_OPTIONS_WITH_VALUE = {"--output-format", "-c", "--session"}
_GLOBAL_OPTIONS_FLAGS = {"--help", "-h", "--version", "-v"}


def _find_first_command(args: list[str]) -> str | None:
    """Skip leading global options/flags to find the first sub-command token.

    Returns the command name, or None if args contain only options.
    """
    skip_next = False
    for a in args:
        if skip_next:
            skip_next = False
            continue
        if a in _GLOBAL_OPTIONS_WITH_VALUE:
            skip_next = True
            continue
        if a.startswith("-"):
            # Any other flag (e.g. --no-memory, unknown flags) — skip
            continue
        return a  # first non-option token is the command
    return None


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
    cmd = _find_first_command(args)
    if cmd is None or cmd in _AUTH_EXEMPT_COMMANDS:
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


def save_history(query: str, commands: list | None = None) -> None:
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


# ---------------------------------------------------------------------------
# Smart-mode helpers (D8: extracted from monolithic cli())
# ---------------------------------------------------------------------------


def _parse_smart_mode_flags(args: list[str]) -> tuple[str | None, bool, str]:
    """Extract -c/--session and --no-memory from args.

    Returns (session_id, no_memory, query).
    """
    session_id: str | None = None
    no_memory = False
    clean_args: list[str] = []
    skip_next = False
    for i, a in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if a in ("-c", "--session") and i + 1 < len(args):
            session_id = args[i + 1]
            skip_next = True
        elif a == "--no-memory":
            no_memory = True
        else:
            clean_args.append(a)
    return session_id, no_memory, " ".join(clean_args)


def _resolve_repeat(query: str) -> str | None:
    """Resolve repeat-phrase queries from history.

    Returns the actual query string to use, or None if the caller should return
    immediately (command already executed or nothing to do).

    Only triggers when the *entire* query (after stripping) matches a repeat
    phrase exactly.  Queries like "analyze retention again by channel" are
    passed through as new requests.
    """
    query_lower = query.lower().strip()
    if query_lower not in REPEAT_PHRASES:
        return query  # not an exact repeat phrase, pass through unchanged

    hist = load_history()
    last_commands = hist.get("last_commands", [])
    last_query = hist.get("last_query", "")

    if last_commands:
        console.print("\n[dim]Re-executing last command...[/dim]")
        from .ai import execute_command

        for cmd in last_commands:
            console.print(f"\n[cyan]Executing: {cmd}[/cyan]\n")
            success, output = execute_command(cmd)
            if output:
                console.print(output)
        return None  # handled; caller should return

    if last_query:
        console.print(f"\n[dim]Re-executing: {last_query}[/dim]")
        return last_query

    console.print("[yellow]No previous command found. Please enter a query.[/yellow]")
    return None  # nothing to do; caller should return


def _load_session(session_id: str | None):
    """Load or create session. Returns (session, session_history, store)."""
    from .ai.session import SessionStore

    store = SessionStore()
    session, history = store.load_or_create(session_id)
    if session_id and history is None:
        console.print(
            f"[yellow]Session '{session_id}' not found or expired. Starting fresh.[/yellow]"
        )
    return session, history, store


def _load_memory(no_memory: bool):
    """Load MemoryManager (with TraceLogger) and build system prompt.

    Returns (manager, effective_system_prompt). Both are None on failure or when
    no_memory=True — memory failures never block the main AI call (P3 + graceful degradation).
    """
    if no_memory:
        return None, None
    try:
        from .ai.trace import get_tracer
        from .memory import MemoryManager

        mm = MemoryManager(trace_logger=get_tracer())  # P3: inject shared tracer
        ctx = mm.load()
        return mm, mm.build_system_prompt(ctx)
    except Exception:
        return None, None


def _save_session_turn(
    query: str,
    response: str,
    session,
    store,
    memory_manager,
    session_id: str,
    no_memory: bool,
) -> None:
    """Persist one Q&A conversation turn and optional memory summary."""
    if session is None or store is None:
        return
    from .config import load_config as _lc

    session.add_turn(query, response, max_history=_lc().session.max_history)
    store.save(session)
    if memory_manager is not None:
        _sid = memory_manager.save_session_memory(session, trace_id="", no_memory=no_memory)
        if _sid:
            console.print(
                f"[dim]已记录本次会话摘要 · sh memory show summary/{_sid} 查看[/dim]"
            )


def _handle_scheduled_task(response: str, scheduled_task: dict) -> None:
    """Display and optionally persist a SCHEDULE_TASK response."""
    import re

    from rich.markdown import Markdown

    display_response = re.sub(
        r"\[SCHEDULE_TASK\].*?\[/SCHEDULE_TASK\]", "", response, flags=re.DOTALL
    )
    console.print(
        Panel(Markdown(display_response), title="AI Assistant - Scheduled Task", border_style="green")
    )
    console.print("\n[bold]Scheduled task detected:[/bold]")
    console.print(f"  Task name: {scheduled_task.get('name', '-')}")
    console.print(f"  Frequency: {scheduled_task.get('frequency', '-')}")
    console.print(f"  Command: {scheduled_task.get('command', '-')}")
    console.print(f"  AI Insights: {scheduled_task.get('insights', 'false')}")
    console.print()

    if typer.confirm("Add this task to Heartbeat.md?", default=True):
        # D4: import directly from heartbeat (commands layer owns this format)
        from .commands.heartbeat import save_task_to_heartbeat

        if save_task_to_heartbeat(scheduled_task):
            console.print("[green][OK] Scheduled task added to Heartbeat.md[/green]")
        else:
            console.print("[red]Failed to add scheduled task[/red]")


def _handle_plan_response(
    display_response: str,
    steps: list[dict],
    query: str,
    session,
    store,
    session_id: str | None,
    usage: dict | None,
    memory_manager=None,
) -> None:
    """Confirm and execute a multi-step plan; D7: save results to session history."""
    from rich.markdown import Markdown

    console.print(
        Panel(Markdown(display_response), title="AI Assistant - Analysis Plan", border_style="cyan")
    )
    console.print(f"\n[bold]Detected {len(steps)} execution steps:[/bold]")
    for step in steps:
        console.print(f"  {step['number']}. {step['description']}")
    console.print()

    if not typer.confirm("Execute this plan?", default=True):
        console.print("[yellow]Plan not executed. You can run the commands manually.[/yellow]")
        return

    from .ai import execute_plan

    commands = [step["command"] for step in steps]
    save_history(query, commands)
    plan_summary = execute_plan(
        steps,
        original_query=query,
        session_id=session_id or "",
        prompt_tokens=(usage or {}).get("prompt_tokens", 0),
        completion_tokens=(usage or {}).get("completion_tokens", 0),
        memory_manager=memory_manager,
    )

    # D7: write plan execution results back to session so future turns have context
    if plan_summary and session is not None and store is not None:
        from .config import load_config as _lc

        session.add_turn(
            f"[计划执行] {query}", plan_summary, max_history=_lc().session.max_history
        )
        store.save(session)


def _handle_inline_command(response: str, query: str) -> None:
    """Execute a bare ```bash block in the response if the user confirms."""
    import re

    if "```bash" not in response:
        return
    commands = re.findall(r"```bash\n(.*?)\n```", response, re.DOTALL)
    if not commands:
        return
    cmd = commands[0].strip()
    if typer.confirm(f"\nExecute command: {cmd}?", default=True):
        from .ai import execute_command

        save_history(query, [cmd])
        console.print(f"\n[dim]Executing: {cmd}[/dim]\n")
        _success, output = execute_command(cmd)
        if output:
            console.print(output)


def _run_smart_mode(query: str, session_id: str | None, no_memory: bool) -> None:
    """Full smart-mode AI pipeline: validate → memory → AI → dispatch response type."""
    from rich.markdown import Markdown

    from .ai import call_ai_api, extract_plan_steps, extract_scheduled_task
    from .ai.sanitizer import sanitize_user_input, validate_input_length

    ok, _msg = validate_input_length(query)
    if not ok:
        console.print(
            f"[red]Input too long ({len(query)} chars, limit 2000). Please shorten your query.[/red]"
        )
        return
    query = sanitize_user_input(query)

    session, session_history, store = _load_session(session_id)
    memory_manager, effective_system_prompt = _load_memory(no_memory)

    response, usage = call_ai_api(
        query,
        session_history=session_history,
        system_prompt=effective_system_prompt,
    )

    if response.startswith("Error:"):
        console.print(f"[red]{response}[/red]")
        return

    # Save the main Q&A turn to session before dispatching plan/task
    _save_session_turn(query, response, session, store, memory_manager, session_id or "", no_memory)

    # Dispatch by response type: scheduled task > plan > plain text / inline command
    scheduled_task = extract_scheduled_task(response)
    if scheduled_task:
        _handle_scheduled_task(response, scheduled_task)
        return

    steps = extract_plan_steps(response)
    if steps:
        display_response = response.replace("[PLAN_START]", "").replace("[PLAN_END]", "")
        _handle_plan_response(display_response, steps, query, session, store, session_id, usage, memory_manager=memory_manager)
    else:
        # Strip control markers that weren't successfully parsed
        clean_response = response.replace("[PLAN_START]", "").replace("[PLAN_END]", "")
        clean_response = clean_response.replace("[SCHEDULE_TASK]", "")
        clean_response = clean_response.replace("[/SCHEDULE_TASK]", "")
        console.print(Panel(Markdown(clean_response), title="AI Assistant", border_style="cyan"))
        _handle_inline_command(clean_response, query)


# ---------------------------------------------------------------------------
# CLI entry point (D8: refactored God Function → thin dispatcher)
# ---------------------------------------------------------------------------


def cli() -> None:
    """CLI entry point with smart natural language detection."""
    args = sys.argv[1:]

    if not args:
        show_welcome()
        return

    # Find the actual command, skipping leading global options like
    # --output-format, -v, --session so that
    # `sh --output-format json analytics overview` is correctly routed.
    cmd = _find_first_command(args)
    if cmd is not None and cmd in VALID_COMMANDS:
        app()
        return

    # Parse session/memory flags before doing anything else
    session_id, no_memory, query = _parse_smart_mode_flags(args)

    # D1 FIX: Auth gate BEFORE repeat-phrase check (was after, allowing unauthenticated replay)
    from .auth.gate import ensure_authenticated

    ensure_authenticated()

    # Resolve repeat phrases; None means "already handled, return now"
    query = _resolve_repeat(query)
    if query is None:
        return

    console.print(f"\n[dim]Smart mode: {query}[/dim]")

    try:
        _run_smart_mode(query, session_id, no_memory)
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        console.print("[dim]Please try again or check your network connection.[/dim]")


if __name__ == "__main__":
    cli()
