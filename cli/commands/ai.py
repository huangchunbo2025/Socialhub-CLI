"""AI-powered natural language command interface."""

import logging
import re

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from ..ai.client import call_ai_api
from ..ai.executor import execute_command, execute_plan
from ..ai.parser import extract_plan_steps
from ..ai.sanitizer import sanitize_user_input, validate_input_length

app = typer.Typer(help="AI assistant for natural language queries")
console = Console()
logger = logging.getLogger(__name__)


@app.command("chat")
def ai_chat(
    query: str = typer.Argument(..., help="Natural language query"),
    api_key: str | None = typer.Option(None, "--api-key", "-k", help="OpenAI API Key"),
    execute: bool = typer.Option(False, "--execute", "-e", help="Auto-execute generated commands"),
    auto: bool = typer.Option(False, "--auto", "-a", help="Auto-execute multi-step plan (with confirmation)"),
    session_id: str | None = typer.Option(None, "-c", "--session", help="Session ID for multi-turn conversation"),
    no_memory: bool = typer.Option(False, "--no-memory", help="Disable memory injection for this query"),
) -> None:
    """
    Interact with CLI using natural language.

    Examples:
        ai chat "analyze customer retention for last 30 days"
        ai chat "show all VIP members"
        ai chat "export high-value customers to Excel"
        ai chat "show order distribution and trends" --auto
        ai chat "analyze sales" -c session-id  # continue a session
        ai chat "analyze sales" --no-memory    # skip personalization
    """
    console.print(f"\n[dim]Analyzing: {query}[/dim]\n")

    ok, msg = validate_input_length(query)
    if not ok:
        console.print(f"[red]Input too long ({len(query)} chars, limit 2000). Please shorten your query.[/red]")
        raise typer.Exit(1)
    query = sanitize_user_input(query)

    # Load or create session (ephemeral for single-turn memory persistence)
    from ..ai.session import SessionStore
    store = SessionStore()
    session, session_history = store.load_or_create(session_id)
    if session_id and session_history is None:
        console.print(f"[yellow]Session '{session_id}' not found or expired. Starting fresh.[/yellow]")

    # Load memory context and build personalized system prompt (P3: inject shared tracer)
    _memory_manager = None
    _effective_system_prompt = None
    if not no_memory:
        try:
            from ..ai.trace import get_tracer
            from ..memory import MemoryManager
            _memory_manager = MemoryManager(trace_logger=get_tracer())
            _memory_ctx = _memory_manager.load()
            _effective_system_prompt = _memory_manager.build_system_prompt(_memory_ctx)
        except Exception as _mem_err:
            logger.debug("Memory initialization failed (non-fatal): %s", _mem_err)

    response, _usage = call_ai_api(query, api_key, session_history=session_history, system_prompt=_effective_system_prompt)

    # Save session turn and extract memory
    if session is not None and store is not None:
        from ..config import load_config as _lc
        session.add_turn(query, response, max_history=_lc().session.max_history)
        store.save(session)
        if _memory_manager is not None:
            _summary_id = _memory_manager.save_session_memory(session, no_memory=no_memory)
            if _summary_id:
                console.print(f"[dim]已记录本次会话摘要 · sh memory show summary/{_summary_id} 查看[/dim]")

    steps = extract_plan_steps(response)

    if steps:
        display_response = response.replace("[PLAN_START]", "").replace("[PLAN_END]", "")
        console.print(Panel(Markdown(display_response), title="AI Assistant - Analysis Plan", border_style="cyan"))

        if auto or execute:
            console.print(f"\n[bold]Detected {len(steps)} execution steps:[/bold]")
            for step in steps:
                console.print(f"  {step['number']}. {step['description']}")

            console.print()
            if typer.confirm("Execute this plan?", default=True):
                _prompt_tokens = (_usage or {}).get("prompt_tokens", 0)
                _completion_tokens = (_usage or {}).get("completion_tokens", 0)
                execute_plan(steps, original_query=query, session_id=session_id or "", prompt_tokens=_prompt_tokens, completion_tokens=_completion_tokens, no_memory=no_memory, memory_manager=_memory_manager)
            else:
                console.print("[yellow]Plan not executed. You can run the commands manually.[/yellow]")
    else:
        console.print(Panel(Markdown(response), title="AI Assistant", border_style="cyan"))

        if (execute or auto) and "```bash" in response:
            commands = re.findall(r"```bash\n(.*?)\n```", response, re.DOTALL)
            if commands:
                cmd = commands[0].strip()
                if typer.confirm(f"\nExecute command: {cmd}?"):
                    console.print(f"\n[dim]Executing: {cmd}[/dim]\n")
                    success, output = execute_command(cmd)
                    if output:
                        console.print(output)


@app.command("help")
def ai_help(
    topic: str = typer.Argument("general", help="Help topic"),
) -> None:
    """Get help for specific features."""
    help_topics = {
        "general": """
## SocialHub.AI CLI User Guide

### Quick Start
```bash
# View all commands
python -m cli.main --help

# Data analytics
python -m cli.main analytics overview

# Customer management
python -m cli.main customers list
```

### AI Assistant
Interact with CLI using natural language:
```bash
python -m cli.main ai chat "your question"
```
        """,
        "analytics": """
## Data Analytics Commands

### Overview Analysis
```bash
python -m cli.main analytics overview --period=7d
python -m cli.main analytics overview --from=2024-01-01 --to=2024-03-01
```

### Customer Analysis
```bash
python -m cli.main analytics customers --period=30d
python -m cli.main analytics retention --days=7,14,30
```

### Order Analysis
```bash
python -m cli.main analytics orders --period=30d
python -m cli.main analytics orders --by=channel
```
        """,
        "customers": """
## Customer Management Commands

### Query Customers
```bash
python -m cli.main customers list --type=member
python -m cli.main customers search --phone=138
python -m cli.main customers get C001
```

### Export Customers
```bash
python -m cli.main customers export --output=customers.csv
python -m cli.main customers export --type=member --output=members.xlsx
```
        """,
    }

    content = help_topics.get(topic, help_topics["general"])
    console.print(Markdown(content))


@app.command("analyze")
def analyze_shortcut(
    target: str = typer.Argument("overview", help="Analysis target: overview/customers/orders/retention"),
    period: str = typer.Option("30d", "--period", "-p", help="Time period"),
) -> None:
    """Quick analysis command shortcut."""
    from . import analytics

    target_map = {
        "overview": lambda: analytics.analytics_overview(period=period, format="table", from_date=None, to_date=None, customer_type="all", output=None),
        "customers": lambda: analytics.analytics_customers(period=period, channel="all", format="table", output=None),
        "orders": lambda: analytics.analytics_orders(period=period, metric="sales", repurchase_rate=False, by=None, format="table", output=None),
        "retention": lambda: analytics.analytics_retention(days="7,14,30", format="table", output=None),
    }

    if target in target_map:
        target_map[target]()
    else:
        console.print(f"[yellow]Unknown analysis target: {target}[/yellow]")
        console.print("Options: overview, customers, orders, retention")
