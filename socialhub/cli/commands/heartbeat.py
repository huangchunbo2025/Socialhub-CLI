"""Heartbeat - Scheduled task execution engine."""

import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

app = typer.Typer(help="Scheduled task management (Heartbeat)")
console = Console()

# Heartbeat file location
HEARTBEAT_FILE = Path.home() / "socialhub" / "Heartbeat.md"


def parse_heartbeat_tasks() -> list[dict]:
    """Parse tasks from Heartbeat.md file."""
    if not HEARTBEAT_FILE.exists():
        return []

    content = HEARTBEAT_FILE.read_text(encoding="utf-8")
    tasks = []

    # Split content by "---" to get individual task sections
    # First, find the task list section (support both English and Chinese headers)
    task_list_start = content.find("## Scheduled Tasks")
    if task_list_start == -1:
        task_list_start = content.find("## Task List")
    if task_list_start == -1:
        return []

    # Find where task list ends (at execution log or next major section)
    task_list_end = content.find("## Execution Log")
    if task_list_end == -1:
        task_list_end = len(content)

    task_content = content[task_list_start:task_list_end]

    # Split by task headers
    sections = re.split(r"(?=### \d+\.)", task_content)

    for section in sections:
        # Pattern to match task info (support both English and Chinese field names)
        task_match = re.search(
            r"### \d+\. (.+?)\n- \*\*ID\*\*: (.+?)\n- \*\*(?:Frequency|频率)\*\*: (.+?)\n- \*\*(?:Status|状态)\*\*: `(.+?)`",
            section,
            re.DOTALL
        )
        if task_match:
            task = {
                "name": task_match.group(1).strip(),
                "id": task_match.group(2).strip(),
                "frequency": task_match.group(3).strip(),
                "status": task_match.group(4).strip(),
            }

            # Extract command - handle indented code blocks
            cmd_match = re.search(r"```bash\r?\n\s*(.+?)\r?\n\s*```", section, re.DOTALL)
            if cmd_match:
                # Clean up the command (remove extra whitespace from each line)
                cmd_lines = cmd_match.group(1).strip().split("\n")
                task["command"] = " && ".join(line.strip() for line in cmd_lines if line.strip())

            # Check for AI insights flag (support both English and Chinese)
            if ("AI Insights" in section or "AI洞察" in section) and "true" in section.lower():
                task["insights"] = True

            tasks.append(task)

    return tasks


def parse_frequency(frequency: str) -> dict:
    """Parse frequency string to schedule info."""
    schedule = {"type": None, "hour": None, "minute": 0, "weekday": None}

    # Daily HH:MM (English)
    daily_match = re.search(r"[Dd]aily\s*(\d{1,2}):(\d{2})", frequency)
    if daily_match:
        schedule["type"] = "daily"
        schedule["hour"] = int(daily_match.group(1))
        schedule["minute"] = int(daily_match.group(2))
        return schedule

    # Weekly Day HH:MM (English)
    weekly_match = re.search(r"[Ww]eekly\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\w*\s*(\d{1,2}):(\d{2})", frequency)
    if weekly_match:
        weekday_map = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
        schedule["type"] = "weekly"
        schedule["weekday"] = weekday_map.get(weekly_match.group(1), 0)
        schedule["hour"] = int(weekly_match.group(2))
        schedule["minute"] = int(weekly_match.group(3))
        return schedule

    # Hourly
    if "hourly" in frequency.lower():
        schedule["type"] = "hourly"
        return schedule

    return schedule


def should_run_task(task: dict, now: datetime, last_check: Optional[datetime] = None) -> bool:
    """Check if task should run based on current time."""
    if task["status"] != "pending":
        return False

    schedule = parse_frequency(task["frequency"])

    if schedule["type"] == "daily":
        # Check if current hour:minute matches
        if now.hour == schedule["hour"] and now.minute >= schedule["minute"]:
            # Only run once per day - check if we're within the execution window (first 59 minutes of the hour)
            if now.minute < schedule["minute"] + 59:
                return True

    elif schedule["type"] == "weekly":
        if now.weekday() == schedule["weekday"] and now.hour == schedule["hour"]:
            if now.minute >= schedule["minute"] and now.minute < schedule["minute"] + 59:
                return True

    elif schedule["type"] == "hourly":
        # Run at the start of each hour
        if now.minute < 5:
            return True

    return False


def execute_task(task: dict) -> tuple[bool, str]:
    """Execute a task command.

    SECURITY: Only allows 'sh' (SocialHub CLI) commands.
    Uses shell=False with argument list to prevent command injection.
    """
    import shlex

    if "command" not in task:
        return False, "No command defined"

    command = task["command"].strip()

    # SECURITY: Only allow 'sh ' commands
    if not command.startswith("sh "):
        return False, "Only 'sh' commands are allowed for security reasons"

    # Extract the command part after 'sh '
    cli_args = command[3:].strip()

    # SECURITY: Block dangerous shell characters (no chaining allowed)
    dangerous_chars = [';', '&&', '||', '|', '`', '$', '>', '<', '\n', '\r']
    for char in dangerous_chars:
        if char in cli_args:
            return False, f"Invalid command: contains disallowed character '{char}'"

    try:
        # Parse arguments safely using shlex
        args = shlex.split(cli_args)
    except ValueError as e:
        return False, f"Invalid command format: {e}"

    # Build the full command as a list
    python_exe = sys.executable
    full_cmd = [python_exe, "-m", "socialhub.cli.main"] + args

    try:
        console.print(f"\n[cyan]Executing: {task['command']}[/cyan]")

        # Run the command with shell=False for security
        result = subprocess.run(
            full_cmd,
            shell=False,  # SECURITY: Never use shell=True
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            encoding="utf-8",
            errors="replace"
        )

        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr

        if result.returncode == 0:
            return True, output
        else:
            return False, f"Exit code {result.returncode}"

    except subprocess.TimeoutExpired:
        return False, "Task timed out (5 minutes)"
    except Exception as e:
        return False, str(e)


def update_execution_log(task_id: str, status: str, note: str = "") -> None:
    """Update execution log in Heartbeat.md."""
    if not HEARTBEAT_FILE.exists():
        return

    content = HEARTBEAT_FILE.read_text(encoding="utf-8")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Find the execution log table and add new entry (support both English and Chinese)
    log_marker = "| Time | Task ID | Status | Note |"
    if log_marker not in content:
        log_marker = "| 时间 | 任务ID | 状态 | 备注 |"

    if log_marker in content:
        # Find the line after the header separator
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if "| - | - | - | No records |" in line or "| - | - | - | 暂无执行记录 |" in line:
                # Replace placeholder with actual log
                lines[i] = f"| {now} | {task_id} | {status} | {note} |"
                break
            elif log_marker in line and i + 2 < len(lines):
                # Insert new log entry after header
                if lines[i + 1].startswith("|---"):
                    new_entry = f"| {now} | {task_id} | {status} | {note} |"
                    lines.insert(i + 2, new_entry)
                    break

        content = "\n".join(lines)

    # Update last check time
    content = re.sub(
        r"\*Next check: .+?\*",
        f"*Next check: Waiting for trigger*",
        content
    )

    # Update heartbeat check record (support both English and Chinese)
    check_marker = "| Check Time | Pending | Executed | Note |"
    if check_marker not in content:
        check_marker = "| 检查时间 | 待执行任务数 | 执行任务数 | 备注 |"

    if check_marker in content:
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if "| - | - | - | Waiting for first check |" in line or "| - | - | - | 等待首次检查 |" in line:
                lines[i] = f"| {now} | - | 1 | Task: {task_id} |"
                break
        content = "\n".join(lines)

    HEARTBEAT_FILE.write_text(content, encoding="utf-8")


@app.command("check")
def check_tasks(
    force: bool = typer.Option(False, "--force", "-f", help="Force run all pending tasks regardless of schedule"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would run without executing"),
) -> None:
    """Check and execute due scheduled tasks."""

    console.print(Panel("[bold]Heartbeat Check[/bold]", border_style="blue"))

    if not HEARTBEAT_FILE.exists():
        console.print(f"[red]Heartbeat file not found: {HEARTBEAT_FILE}[/red]")
        raise typer.Exit(1)

    tasks = parse_heartbeat_tasks()
    now = datetime.now()

    console.print(f"[dim]Check time: {now.strftime('%Y-%m-%d %H:%M:%S')}[/dim]")
    console.print(f"[dim]Found {len(tasks)} tasks[/dim]\n")

    due_tasks = []
    for task in tasks:
        if force and task["status"] == "pending":
            due_tasks.append(task)
        elif should_run_task(task, now):
            due_tasks.append(task)

    if not due_tasks:
        console.print("[green]No tasks due for execution.[/green]")
        return

    console.print(f"[yellow]Tasks due: {len(due_tasks)}[/yellow]\n")

    for task in due_tasks:
        console.print(f"[bold]Task: {task['name']}[/bold] (ID: {task['id']})")
        console.print(f"  Schedule: {task['frequency']}")
        console.print(f"  Command: {task.get('command', 'N/A')}")

        if dry_run:
            console.print("  [dim]-- Dry run, skipping execution --[/dim]\n")
            continue

        # Execute the task
        success, output = execute_task(task)

        if success:
            console.print(f"  [green][OK] Task completed[/green]")
            update_execution_log(task["id"], "done", "Success")
        else:
            console.print(f"  [red][FAIL] Task failed[/red]")
            console.print(f"  Error: {output[:200]}")
            update_execution_log(task["id"], "failed", output[:50])

        if output:
            console.print(output)
        console.print()


@app.command("list")
def list_tasks() -> None:
    """List all scheduled tasks."""

    if not HEARTBEAT_FILE.exists():
        console.print(f"[red]Heartbeat file not found: {HEARTBEAT_FILE}[/red]")
        raise typer.Exit(1)

    tasks = parse_heartbeat_tasks()

    table = Table(title="Scheduled Tasks")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Schedule", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Command", style="dim", max_width=40)

    for task in tasks:
        status_style = {
            "pending": "yellow",
            "running": "blue",
            "done": "green",
            "paused": "dim",
            "failed": "red"
        }.get(task["status"], "white")

        table.add_row(
            task["id"],
            task["name"],
            task["frequency"],
            f"[{status_style}]{task['status']}[/{status_style}]",
            task.get("command", "-")[:40]
        )

    console.print(table)


@app.command("run")
def run_task(
    task_id: str = typer.Argument(..., help="Task ID to run"),
) -> None:
    """Manually run a specific task by ID."""

    if not HEARTBEAT_FILE.exists():
        console.print(f"[red]Heartbeat file not found: {HEARTBEAT_FILE}[/red]")
        raise typer.Exit(1)

    tasks = parse_heartbeat_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)

    if not task:
        console.print(f"[red]Task not found: {task_id}[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]Running task: {task['name']}[/bold]")

    success, output = execute_task(task)

    if success:
        console.print("\n[green][OK] Task completed successfully[/green]")
        update_execution_log(task_id, "done", "Manual run")
    else:
        console.print(f"\n[red][FAIL] Task failed[/red]")
        if output:
            console.print(f"[dim]{output[:200]}[/dim]")
        update_execution_log(task_id, "failed", "Manual run failed")

    if success and output:
        console.print(output, markup=False)


@app.command("setup")
def setup_scheduler() -> None:
    """Show instructions to setup Windows Task Scheduler."""

    script_path = Path(sys.executable).parent / "socialhub.exe"

    instructions = f"""
[bold]Windows Task Scheduler Setup[/bold]

To run heartbeat checks automatically every hour:

[cyan]1. Open Task Scheduler[/cyan]
   - Press Win+R, type 'taskschd.msc', press Enter

[cyan]2. Create Basic Task[/cyan]
   - Click 'Create Basic Task...' in the right panel
   - Name: SocialHub Heartbeat
   - Description: Hourly check for scheduled tasks

[cyan]3. Set Trigger[/cyan]
   - Select 'Daily'
   - Start time: 00:00:00
   - Check 'Repeat task every: 1 hour'
   - Duration: Indefinitely

[cyan]4. Set Action[/cyan]
   - Select 'Start a program'
   - Program: {script_path}
   - Arguments: heartbeat check

[cyan]5. Finish[/cyan]
   - Check 'Open Properties dialog'
   - In Properties > Settings:
     - Check 'Run task as soon as possible after scheduled start is missed'

[green]Or use this PowerShell command:[/green]

```powershell
$action = New-ScheduledTaskAction -Execute "{script_path}" -Argument "heartbeat check"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration ([TimeSpan]::MaxValue)
Register-ScheduledTask -TaskName "SocialHub Heartbeat" -Action $action -Trigger $trigger -Description "Hourly heartbeat check"
```
"""

    console.print(Panel(instructions, title="Setup Instructions", border_style="blue"))


if __name__ == "__main__":
    app()
