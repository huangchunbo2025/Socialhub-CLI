"""SocialHub.AI CLI - Main entry point."""

import json
import sys
from pathlib import Path
import typer
from rich.console import Console

from . import __version__
from .commands import ai, analytics, campaigns, config_cmd, coupons, customers, mcp, messages, points, segments, skills, tags

# History file for storing last command
HISTORY_FILE = Path.home() / ".socialhub" / "history.json"

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
    "coupons", "points", "messages", "config", "ai", "skills", "mcp",
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
app.add_typer(mcp.app, name="mcp", help="MCP analytics database (connect to SocialHub.AI)")


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


def load_history() -> dict:
    """Load command history from file."""
    try:
        if HISTORY_FILE.exists():
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except:
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
    except:
        pass


# Phrases that mean "repeat last command"
REPEAT_PHRASES = {
    "再执行一次", "重新执行", "再来一次", "再试一次",
    "重复", "再跑一次", "重跑", "上一个", "!!",
    "repeat", "again", "retry", "redo"
}


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
            console.print(f"\n[dim]重新执行上次命令...[/dim]")
            from .commands.ai import execute_command
            for cmd in last_commands:
                console.print(f"\n[cyan]执行: {cmd}[/cyan]\n")
                success, output = execute_command(cmd)
                if output:
                    console.print(output)
            return
        elif last_query:
            # Use last query
            query = last_query
            console.print(f"\n[dim]重新执行: {query}[/dim]")
        else:
            console.print("[yellow]没有找到上次执行的命令。请输入具体的查询。[/yellow]")
            return

    console.print(f"\n[dim]智能识别: {query}[/dim]")

    # Call AI to process and execute
    from .commands.ai import call_ai_api, extract_plan_steps, execute_plan, execute_command, extract_scheduled_task, save_scheduled_task
    import re

    response = call_ai_api(query)

    # Check for scheduled task
    scheduled_task = extract_scheduled_task(response)
    if scheduled_task:
        # Display response without markers
        display_response = re.sub(r"\[SCHEDULE_TASK\].*?\[/SCHEDULE_TASK\]", "", response, flags=re.DOTALL)
        from rich.panel import Panel
        from rich.markdown import Markdown
        console.print(Panel(Markdown(display_response), title="AI 助手 - 定时任务", border_style="green"))

        console.print(f"\n[bold]检测到定时任务配置:[/bold]")
        console.print(f"  任务名称: {scheduled_task.get('name', '-')}")
        console.print(f"  执行频率: {scheduled_task.get('frequency', '-')}")
        console.print(f"  执行命令: {scheduled_task.get('command', '-')}")
        console.print(f"  AI洞察: {scheduled_task.get('insights', 'false')}")
        console.print()

        if typer.confirm("是否将此任务添加到 Heartbeat.md?", default=True):
            if save_scheduled_task(scheduled_task):
                console.print("[green][OK] 定时任务已添加到 Heartbeat.md[/green]")
            else:
                console.print("[red]添加定时任务失败[/red]")
        return

    # Check for multi-step plan
    steps = extract_plan_steps(response)

    # Display response
    from rich.panel import Panel
    from rich.markdown import Markdown

    if steps:
        # Display plan without markers
        display_response = response.replace("[PLAN_START]", "").replace("[PLAN_END]", "")
        console.print(Panel(Markdown(display_response), title="AI 助手 - 分析计划", border_style="cyan"))

        # Show step summary and ask for confirmation
        console.print(f"\n[bold]检测到 {len(steps)} 个执行步骤:[/bold]")
        for step in steps:
            console.print(f"  {step['number']}. {step['description']}")

        console.print()
        if typer.confirm("是否执行以上计划?", default=True):
            # Save commands to history before executing
            commands = [step["command"] for step in steps]
            save_history(query, commands)
            execute_plan(steps, original_query=query)
        else:
            console.print("[yellow]计划未执行。您可以手动运行上述命令。[/yellow]")
    else:
        console.print(Panel(Markdown(response), title="AI 助手", border_style="cyan"))

        # Extract and execute single command
        if "```bash" in response:
            commands = re.findall(r"```bash\n(.*?)\n```", response, re.DOTALL)
            if commands:
                cmd = commands[0].strip()
                if typer.confirm(f"\n执行命令: {cmd}?", default=True):
                    # Save to history
                    save_history(query, [cmd])
                    console.print(f"\n[dim]执行: {cmd}[/dim]\n")
                    success, output = execute_command(cmd)
                    if output:
                        console.print(output)


if __name__ == "__main__":
    cli()
