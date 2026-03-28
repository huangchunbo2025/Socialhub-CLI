"""AI-powered natural language command interface."""

import re
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from ..ai.client import call_ai_api
from ..ai.executor import execute_command, execute_plan, save_scheduled_task
from ..ai.parser import extract_plan_steps, extract_scheduled_task

app = typer.Typer(help="AI assistant for natural language queries")
console = Console()


@app.command("chat")
def ai_chat(
    query: str = typer.Argument(..., help="Natural language query"),
    api_key: Optional[str] = typer.Option(None, "--api-key", "-k", help="OpenAI API Key"),
    execute: bool = typer.Option(False, "--execute", "-e", help="Auto-execute generated commands"),
    auto: bool = typer.Option(False, "--auto", "-a", help="Auto-execute multi-step plan (with confirmation)"),
) -> None:
    """
    Interact with CLI using natural language.

    Examples:
        ai chat "analyze customer retention for last 30 days"
        ai chat "show all VIP members"
        ai chat "export high-value customers to Excel"
        ai chat "show order distribution and trends" --auto
    """
    console.print(f"\n[dim]Analyzing: {query}[/dim]\n")

    response = call_ai_api(query, api_key)

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
                execute_plan(steps, original_query=query)
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
