"""Command executor — runs CLI commands and multi-step plans."""

import re
import shlex
import subprocess
import sys
from datetime import datetime

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


def _emit_insights(original_query: str, all_results: list[dict]) -> None:
    """Generate and display AI insights for completed plan results."""
    from .insights import generate_insights

    console.print("[bold cyan]Generating AI insights...[/bold cyan]\n")
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(description="AI analyzing...", total=None)
        insights = generate_insights(original_query, all_results)

    if insights and "Error" not in insights:
        console.print(Panel(
            Markdown(insights),
            title="[bold magenta]AI Insights[/bold magenta]",
            border_style="magenta",
        ))
        console.print()


def execute_command(cmd: str) -> tuple[bool, str]:
    """Execute a CLI command and return success status and output.

    SECURITY: Only allows 'sh' commands (SocialHub CLI) to be executed.
    Uses shell=False with argument list to prevent command injection.
    Validates the command against the registered command registry before running.
    """
    from .validator import validate_command

    python_exe = sys.executable

    if not cmd.startswith("sh "):
        return False, "Only 'sh' commands are allowed for security reasons"

    is_valid, reason = validate_command(cmd)
    if not is_valid:
        return False, f"Invalid command (AI generated an unrecognised command): {reason}"

    cli_args = cmd[3:].strip()

    dangerous_chars = [';', '&&', '||', '|', '`', '$', '>', '<', '\n', '\r']
    for char in dangerous_chars:
        if char in cli_args:
            return False, f"Invalid command: contains disallowed character '{char}'"

    try:
        args = shlex.split(cli_args)
    except ValueError as e:
        return False, f"Invalid command format: {e}"

    full_cmd = [python_exe, "-m", "cli.main"] + args

    try:
        result = subprocess.run(
            full_cmd,
            shell=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout if result.stdout else result.stderr
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Command execution timeout"
    except Exception as e:
        return False, f"Execution error: {str(e)}"


def save_scheduled_task(task: dict) -> bool:
    """Save scheduled task to Heartbeat.md."""
    from ..commands.heartbeat import HEARTBEAT_FILE

    heartbeat_path = HEARTBEAT_FILE

    if not heartbeat_path.exists():
        return False

    try:
        content = heartbeat_path.read_text(encoding="utf-8")

        insert_marker = "## Execution Log"
        if insert_marker not in content:
            insert_marker = "## Add New Task Template"

        task_entry = f"""
### {len(re.findall(r'### \\d+\\.', content)) + 1}. {task.get('name', 'New Task')}
- **ID**: {task.get('id', 'task-' + datetime.now().strftime('%Y%m%d%H%M%S'))}
- **Frequency**: {task.get('frequency', 'Daily 00:00')}
- **Status**: `pending`
- **Command**:
  ```bash
  {task.get('command', 'sh analytics overview')}
  ```
- **Description**: {task.get('description', '')}
- **AI Insights**: {task.get('insights', 'false')}

---

"""

        if insert_marker in content:
            content = content.replace(insert_marker, task_entry + insert_marker)
        else:
            content += task_entry

        heartbeat_path.write_text(content, encoding="utf-8")
        return True

    except Exception as e:
        console.print(f"[red]Failed to save scheduled task: {e}[/red]")
        return False


def execute_plan(steps: list[dict], original_query: str = "") -> None:
    """Execute a multi-step plan with progress display."""
    console.print(f"\n[bold cyan]Executing {len(steps)} steps...[/bold cyan]\n")

    all_results = []
    insights = ""

    report_step_idx = None
    for i, step in enumerate(steps):
        if "report" in step["command"].lower():
            report_step_idx = i
            break

    for idx, step in enumerate(steps):
        step_num = step["number"]
        description = step["description"]
        command = step["command"]

        if report_step_idx is not None and idx == report_step_idx and original_query and all_results:
            if any(r["success"] for r in all_results):
                _emit_insights(original_query, all_results)

        console.print(f"[bold yellow]Step {step_num}:[/bold yellow] {description}")
        console.print(f"[dim]Command: {command}[/dim]\n")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task(description="Executing...", total=None)
            success, output = execute_command(command)

        all_results.append({
            "step": step_num,
            "description": description,
            "success": success,
            "output": output,
        })

        if success:
            console.print(f"[green][OK][/green] Step {step_num} completed\n")
            if output:
                console.print(output)
        else:
            console.print(f"[red][FAIL][/red] Step {step_num} failed\n")
            if output:
                console.print(f"[red]{output}[/red]")

            if idx < len(steps) - 1:
                if not typer.confirm("Continue with remaining steps?", default=False):
                    console.print("[yellow]Execution cancelled[/yellow]")
                    return

        console.print()

    console.print("[bold green]All steps completed![/bold green]\n")

    if report_step_idx is None and original_query and any(r["success"] for r in all_results):
        _emit_insights(original_query, all_results)
