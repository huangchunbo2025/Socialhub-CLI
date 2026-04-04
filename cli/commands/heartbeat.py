"""Heartbeat - Scheduled task execution engine."""

import logging
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..ai.executor import DANGEROUS_CHARS as _DANGEROUS_CHARS, _SUBPROCESS_AUTH_SKIP_ENV

logger = logging.getLogger(__name__)

app = typer.Typer(help="Scheduled task management (Heartbeat)")
console = Console()

# Heartbeat file location — stored alongside other .socialhub data
HEARTBEAT_FILE = Path.home() / ".socialhub" / "Heartbeat.md"

# Process-level lock: prevents two concurrent `heartbeat check` calls in the same process
_CHECK_LOCK = threading.Lock()


def _heartbeat_tmp_path() -> Path:
    """Return a unique per-process temp path for atomic Heartbeat.md writes."""
    return HEARTBEAT_FILE.with_name(f"Heartbeat.{os.getpid()}.{uuid.uuid4().hex[:6]}.tmp")


def _escape_note(note: str) -> str:
    """Escape pipe characters so they don't break Markdown table cells."""
    return note.replace("|", "\\|")


def _resolve_marker(content: str, en: str, cn: str) -> str:
    """Return the English marker if present in content, otherwise the Chinese fallback."""
    return en if en in content else cn


def _patch_heartbeat_content(
    content: str,
    task_id: str,
    status: str,
    note_safe: str,
    now: str,
    update_status: bool = False,
    override_status: str | None = None,
) -> str:
    """Apply all in-memory mutations to a Heartbeat.md content string.

    Handles execution-log table, next-check regex, check-record table, and
    (when update_status=True) the task's own Status field — all in a single
    split/join pass to avoid redundant string allocations.
    """
    content = re.sub(r"\*Next check: .+?\*", "*Next check: Waiting for trigger*", content)
    lines = content.split("\n")

    log_marker = _resolve_marker(
        content,
        "| Time | Task ID | Status | Note |",
        "| 时间 | 任务ID | 状态 | 备注 |",
    )

    in_target_task = False
    for i, line in enumerate(lines):
        if log_marker in line and i + 2 < len(lines) and lines[i + 1].startswith("|---"):
            lines.insert(i + 2, f"| {now} | {task_id} | {status} | {note_safe} |")
            continue
        if "| - | - | - | No records |" in line or "| - | - | - | 暂无执行记录 |" in line:
            lines[i] = f"| {now} | {task_id} | {status} | {note_safe} |"
            continue
        # Check Record placeholder is now handled by _append_check_record()
        if update_status:
            if f"- **ID**: {task_id}" in line:
                in_target_task = True
            elif in_target_task and line.startswith("### "):
                in_target_task = False
            elif in_target_task and "- **Status**:" in line:
                effective = override_status if override_status is not None else status
                lines[i] = f"- **Status**: `{effective}`"
                in_target_task = False

    return "\n".join(lines)


def _safe_field(value: str) -> str:
    """Strip newlines and backticks from user-controlled task fields.

    Prevents Markdown injection: a field value containing ``\\n### N. Evil``
    would create a second task section that ``parse_heartbeat_tasks()`` would
    later parse and ``execute_task()`` would execute.
    """
    return value.replace("\n", " ").replace("\r", " ").replace("`", "'").replace("#", "")


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


_CN_WEEKDAY_MAP = {
    "周一": 0, "星期一": 0, "一": 0,
    "周二": 1, "星期二": 1, "二": 1,
    "周三": 2, "星期三": 2, "三": 2,
    "周四": 3, "星期四": 3, "四": 3,
    "周五": 4, "星期五": 4, "五": 4,
    "周六": 5, "星期六": 5, "六": 5,
    "周日": 6, "星期日": 6, "周天": 6, "日": 6,
}


def normalize_frequency(raw: str) -> str:
    """Convert Chinese/natural-language schedule strings to canonical form.

    Examples:
        "每周五 15:00"   → "Weekly Fri 15:00"
        "每天 08:30"     → "Daily 08:30"
        "每小时"         → "hourly"
        "每周一 09:00"   → "Weekly Mon 09:00"
    """
    en_weekday = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    # 每周<中文星期> HH:MM
    for cn, idx in _CN_WEEKDAY_MAP.items():
        m = re.search(rf"每{cn}\s*(\d{{1,2}}):(\d{{2}})", raw)
        if m:
            return f"Weekly {en_weekday[idx]} {int(m.group(1)):02d}:{m.group(2)}"

    # 每天 / 每日 HH:MM
    m = re.search(r"每[天日]\s*(\d{1,2}):(\d{2})", raw)
    if m:
        return f"Daily {int(m.group(1)):02d}:{m.group(2)}"

    # 每小时 / 每1小时
    if "每小时" in raw or "每1小时" in raw:
        return "hourly"

    return raw  # already in English or unrecognised — pass through


def parse_frequency(frequency: str) -> dict:
    """Parse frequency string to schedule info."""
    frequency = normalize_frequency(frequency)
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


def should_run_task(task: dict, now: datetime) -> bool:
    """Check if task should run based on current time.

    Schedules are expressed in local wall-clock time (operators write "Daily 08:00"
    expecting local time). If *now* is timezone-aware (e.g. UTC), convert to the
    local timezone before comparing hour/minute/weekday.
    """
    if task["status"] != "pending":
        return False

    schedule = parse_frequency(task["frequency"])

    # Convert to local time so schedule comparisons match operator intent
    local_now = now.astimezone() if now.tzinfo is not None else now

    if schedule["type"] == "daily":
        # Check if current hour:minute matches
        if local_now.hour == schedule["hour"] and local_now.minute >= schedule["minute"]:
            # Only run once per day - check if we're within the execution window (5 minutes)
            if local_now.minute < schedule["minute"] + 5:
                return True

    elif schedule["type"] == "weekly":
        if local_now.weekday() == schedule["weekday"] and local_now.hour == schedule["hour"]:
            if local_now.minute >= schedule["minute"] and local_now.minute < schedule["minute"] + 5:
                return True

    elif schedule["type"] == "hourly":
        # Run at the start of each hour
        if local_now.minute < 5:
            return True

    return False


def _execute_single_sh_command(cmd: str) -> tuple[bool, str]:
    """Execute a single 'sh ...' command securely.

    SECURITY: Only allows 'sh' (SocialHub CLI) commands.
    Uses shell=False with argument list to prevent command injection.
    """
    import shlex

    cmd = cmd.strip()

    # SECURITY: Only allow 'sh ' commands
    if not cmd.startswith("sh "):
        return False, "Only 'sh' commands are allowed for security reasons"

    cli_args = cmd[3:].strip()

    # SECURITY: Block dangerous shell characters
    for char in _DANGEROUS_CHARS:
        if char in cli_args:
            return False, f"Invalid command: contains disallowed character '{char}'"

    try:
        args = shlex.split(cli_args)
    except ValueError as e:
        return False, f"Invalid command format: {e}"

    python_exe = sys.executable
    full_cmd = [python_exe, "-m", "cli.main"] + args

    _env = os.environ.copy()
    _env[_SUBPROCESS_AUTH_SKIP_ENV] = "1"

    try:
        result = subprocess.run(
            full_cmd,
            env=_env,
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
            return False, f"Exit code {result.returncode}\n{output}"

    except subprocess.TimeoutExpired:
        return False, "Task timed out (5 minutes)"
    except Exception as e:
        return False, str(e)


def execute_task(task: dict) -> tuple[bool, str]:
    """Execute a task command, supporting compound '&&'-chained commands.

    SECURITY: Only allows 'sh' (SocialHub CLI) commands.
    Uses shell=False with argument list to prevent command injection.
    """
    if "command" not in task:
        return False, "No command defined"

    command = task["command"].strip()

    # Support compound commands joined by &&
    sub_commands = [c.strip() for c in command.split(" && ") if c.strip()]

    all_output: list[str] = []
    for sub_cmd in sub_commands:
        console.print(f"\n[cyan]Executing: {sub_cmd}[/cyan]")
        success, output = _execute_single_sh_command(sub_cmd)
        if output:
            all_output.append(output)
        if not success:
            return False, "\n".join(all_output)

    return True, "\n".join(all_output)


def update_execution_log(task_id: str, status: str, note: str = "") -> None:
    """Update execution log in Heartbeat.md (used by manual runs)."""
    if not HEARTBEAT_FILE.exists():
        return
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    content = _patch_heartbeat_content(
        HEARTBEAT_FILE.read_text(encoding="utf-8"),
        task_id, status, _escape_note(note), now,
    )
    tmp = _heartbeat_tmp_path()
    try:
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(HEARTBEAT_FILE)
    finally:
        tmp.unlink(missing_ok=True)


def _append_check_record(
    content: str, now: str, pending_count: int, executed_count: int, note: str,
) -> str:
    """Append a row to the Heartbeat Check Record table."""
    check_marker = _resolve_marker(
        content,
        "| Check Time | Pending | Executed | Note |",
        "| 检查时间 | 待执行 | 已执行 | 备注 |",
    )
    new_row = f"| {now} | {pending_count} | {executed_count} | {_escape_note(note)} |"
    lines = content.split("\n")

    # First pass: replace placeholder if present
    for i, line in enumerate(lines):
        if "| - | - | - | Waiting for first check |" in line or "| - | - | - | 等待首次检查 |" in line:
            lines[i] = new_row
            return "\n".join(lines)

    # Second pass: append after header+separator
    for i, line in enumerate(lines):
        if check_marker in line and i + 1 < len(lines) and lines[i + 1].startswith("|---"):
            lines.insert(i + 2, new_row)
            return "\n".join(lines)

    return content


def _is_periodic(frequency: str) -> bool:
    """Return True if the frequency represents a recurring schedule."""
    schedule = parse_frequency(frequency)
    return schedule["type"] in ("daily", "weekly", "hourly")


def update_task_after_execution(
    task_id: str, status: str, note: str = "", frequency: str = "",
) -> None:
    """Write execution log entry AND update task Status in a single atomic read-write.

    For periodic tasks (daily/weekly/hourly), the status is always reset to
    ``pending`` after logging the result so the task is eligible for the next
    scheduled run.  One-off tasks retain the ``done``/``failed`` status.
    """
    if not HEARTBEAT_FILE.exists():
        return

    # Determine the persisted status: periodic tasks always go back to pending
    persisted_status = status
    if _is_periodic(frequency) and status in ("done", "failed"):
        persisted_status = "pending"

    try:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        content = _patch_heartbeat_content(
            HEARTBEAT_FILE.read_text(encoding="utf-8"),
            task_id, status, _escape_note(note), now,
            update_status=True,
            override_status=persisted_status,
        )
        tmp = _heartbeat_tmp_path()
        try:
            tmp.write_text(content, encoding="utf-8")
            tmp.replace(HEARTBEAT_FILE)
        finally:
            tmp.unlink(missing_ok=True)
    except Exception as _e:
        logger.warning("Failed to update task record for %s: %s", task_id, _e)


def _acquire_task_lock(lock_file: Path) -> bool:
    """Try to acquire a per-task lock file for idempotent execution.

    Returns True if the lock was acquired (caller must unlink when done).
    Returns False if another live process holds the lock.
    Stale locks (dead PID) are removed and one retry is attempted.
    """
    def _try_create() -> bool:
        try:
            fd = os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except FileExistsError:
            return False

    if _try_create():
        return True

    # Lock file exists — check if owning PID is still alive
    stale = False
    try:
        owner_pid = int(lock_file.read_text(encoding="utf-8").strip())
        os.kill(owner_pid, 0)  # signal 0 = existence check only
    except (ValueError, OSError):
        stale = True

    if stale:
        lock_file.unlink(missing_ok=True)
        return _try_create()

    return False


@app.command("check")
def check_tasks(
    force: bool = typer.Option(False, "--force", "-f", help="Force run all pending tasks regardless of schedule"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would run without executing"),
) -> None:
    """Check and execute due scheduled tasks."""

    console.print(Panel("[bold]Heartbeat Check[/bold]", border_style="blue"))

    if not _CHECK_LOCK.acquire(blocking=False):
        console.print("[yellow]Skipped: another heartbeat check is already running in this process[/yellow]")
        return

    if not HEARTBEAT_FILE.exists():
        _CHECK_LOCK.release()
        console.print(f"[red]Heartbeat file not found: {HEARTBEAT_FILE}[/red]")
        raise typer.Exit(1)

    try:
        tasks = parse_heartbeat_tasks()
    except Exception as exc:
        logger.error("Failed to parse Heartbeat.md, skipping this check: %s", exc)
        console.print(f"[red]Failed to parse Heartbeat.md: {exc}[/red]")
        _CHECK_LOCK.release()
        return

    now = datetime.now(timezone.utc)

    console.print(f"[dim]Check time: {now.strftime('%Y-%m-%d %H:%M:%S')}[/dim]")
    console.print(f"[dim]Found {len(tasks)} tasks[/dim]\n")

    due_tasks = []
    for task in tasks:
        if force and task["status"] == "pending":
            due_tasks.append(task)
        elif should_run_task(task, now):
            due_tasks.append(task)

    pending_count = sum(1 for t in tasks if t["status"] == "pending")

    if not due_tasks:
        console.print("[green]No tasks due for execution.[/green]")
        # Record the check even when nothing ran
        try:
            now_str = now.strftime("%Y-%m-%d %H:%M UTC")
            content = HEARTBEAT_FILE.read_text(encoding="utf-8")
            content = _append_check_record(content, now_str, pending_count, 0, "No tasks due")
            tmp = _heartbeat_tmp_path()
            try:
                tmp.write_text(content, encoding="utf-8")
                tmp.replace(HEARTBEAT_FILE)
            finally:
                tmp.unlink(missing_ok=True)
        except Exception as _e:
            logger.debug("Failed to write check record: %s", _e)
        _CHECK_LOCK.release()
        return

    console.print(f"[yellow]Tasks due: {len(due_tasks)}[/yellow]\n")

    _tracer = None
    try:
        from ..ai.trace import get_tracer
        _tracer = get_tracer()
    except Exception as _e:
        logger.debug("Tracer unavailable, skipping: %s", _e)

    lock_dir = Path.home() / ".socialhub" / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Accumulate all mutations on a single in-memory content string
        # to avoid N+1 read-write cycles of Heartbeat.md.
        content = HEARTBEAT_FILE.read_text(encoding="utf-8")
        now_str = now.strftime("%Y-%m-%d %H:%M UTC")
        executed_count = 0

        for task in due_tasks:
            console.print(f"[bold]Task: {task['name']}[/bold] (ID: {task['id']})")
            console.print(f"  Schedule: {task['frequency']}")
            console.print(f"  Command: {task.get('command', 'N/A')}")

            if dry_run:
                console.print("  [dim]-- Dry run, skipping execution --[/dim]\n")
                continue

            lock_file = lock_dir / f"{task['id']}.lock"
            if not _acquire_task_lock(lock_file):
                console.print("  [yellow]Skipped: lock file exists (task may already be running)[/yellow]\n")
                continue

            try:
                step_start = time.time()
                success, output = execute_task(task)
            finally:
                try:
                    lock_file.unlink(missing_ok=True)
                except OSError:
                    pass

            executed_count += 1
            freq = task.get("frequency", "")
            if success:
                console.print("  [green][OK] Task completed[/green]")
                status = "done"
                note_text = "Success"
            else:
                console.print("  [red][FAIL] Task failed[/red]")
                console.print(f"  Error: {output[:200]}")
                status = "failed"
                note_text = output[:50]

            # Apply mutations in memory (no disk I/O per task)
            persisted_status = "pending" if _is_periodic(freq) and status in ("done", "failed") else status
            content = _patch_heartbeat_content(
                content, task["id"], status, _escape_note(note_text), now_str,
                update_status=True, override_status=persisted_status,
            )

            if _tracer is not None:
                try:
                    _tracer.log_heartbeat_execution(
                        task_id=task["id"],
                        task_name=task["name"],
                        success=success,
                        duration_ms=int((time.time() - step_start) * 1000),
                        error_msg="" if success else output[:200],
                    )
                except Exception as _e:
                    logger.warning("Tracer log_heartbeat_execution failed for %s: %s", task["id"], _e)

            if output:
                console.print(output)
            console.print()

        # Append check record and flush all mutations to disk in one write
        try:
            note = f"Executed {executed_count} task(s)" if not dry_run else "Dry run"
            content = _append_check_record(content, now_str, pending_count, executed_count, note)
            tmp = _heartbeat_tmp_path()
            try:
                tmp.write_text(content, encoding="utf-8")
                tmp.replace(HEARTBEAT_FILE)
            finally:
                tmp.unlink(missing_ok=True)
        except Exception as _e:
            logger.debug("Failed to write heartbeat file: %s", _e)
    finally:
        _CHECK_LOCK.release()


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

    # Acquire per-task lock to prevent concurrent execution with heartbeat check
    lock_dir = Path.home() / ".socialhub" / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_file = lock_dir / f"{task_id}.lock"
    if not _acquire_task_lock(lock_file):
        console.print("[yellow]Task is already running (lock held by another process)[/yellow]")
        raise typer.Exit(1)

    try:
        success, output = execute_task(task)
    finally:
        try:
            lock_file.unlink(missing_ok=True)
        except OSError:
            pass

    if success:
        console.print("\n[green][OK] Task completed successfully[/green]")
        update_task_after_execution(
            task_id, "done", "Manual run",
            frequency=task.get("frequency", ""),
        )
    else:
        console.print("\n[red][FAIL] Task failed[/red]")
        if output:
            console.print(f"[dim]{output[:200]}[/dim]")
        update_task_after_execution(
            task_id, "failed", "Manual run failed",
            frequency=task.get("frequency", ""),
        )

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


_HEARTBEAT_TEMPLATE = """\
<!-- schema: v1 -->
# SocialHub Heartbeat

自动化定时任务调度中心。在下方 "Scheduled Tasks" 区块添加任务，
运行 `sh heartbeat check` 或通过 Windows Task Scheduler 定时触发检查。

---

## Scheduled Tasks

<!-- Tasks are inserted here automatically via `sh heartbeat add` or AI. -->

## Execution Log

| Time | Task ID | Status | Note |
|------|---------|--------|------|
| - | - | - | No records |

## Heartbeat Check Record

| Check Time | Pending | Executed | Note |
|------------|---------|----------|------|
| - | - | - | Waiting for first check |
"""


def _init_heartbeat_file() -> None:
    """Create Heartbeat.md with default template if it does not exist."""
    HEARTBEAT_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not HEARTBEAT_FILE.exists():
        tmp = _heartbeat_tmp_path()
        try:
            tmp.write_text(_HEARTBEAT_TEMPLATE, encoding="utf-8")
            tmp.replace(HEARTBEAT_FILE)
        finally:
            tmp.unlink(missing_ok=True)


@app.command("init")
def init_heartbeat() -> None:
    """Initialize ~/socialhub/Heartbeat.md with default template."""
    if HEARTBEAT_FILE.exists():
        console.print(f"[yellow]Heartbeat file already exists: {HEARTBEAT_FILE}[/yellow]")
        console.print("Use [cyan]sh heartbeat list[/cyan] to see existing tasks.")
        return

    _init_heartbeat_file()
    console.print(f"[green][OK] Created {HEARTBEAT_FILE}[/green]")
    console.print("\nNext steps:")
    console.print("  [cyan]sh heartbeat add --name '周报分析' --schedule '每周五 15:00' --command 'sh analytics overview'[/cyan]")
    console.print("  [cyan]sh heartbeat setup[/cyan]  — register Windows Task Scheduler trigger")


@app.command("add")
def add_task(
    name: str = typer.Option(..., "--name", "-n", help="Task name"),
    schedule: str = typer.Option(..., "--schedule", "-s", help="Schedule (e.g. '每周五 15:00', 'Daily 08:30', 'Weekly Fri 15:00')"),
    command: str = typer.Option(..., "--command", "-c", help="sh command to run (must start with 'sh ')"),
    description: str = typer.Option("", "--description", "-d", help="Optional description"),
    insights: bool = typer.Option(False, "--insights", help="Generate AI insights after execution"),
) -> None:
    """Add a new scheduled task to Heartbeat.md."""
    if not command.startswith("sh "):
        console.print("[red]Command must start with 'sh ' (SocialHub CLI commands only)[/red]")
        raise typer.Exit(1)

    # Normalise schedule so we show the canonical form in the file
    canonical = normalize_frequency(schedule)
    parsed = parse_frequency(canonical)
    if parsed["type"] is None:
        console.print(f"[red]Unrecognised schedule format: {schedule!r}[/red]")
        console.print("Examples: '每周五 15:00', '每天 08:30', 'Weekly Fri 15:00', 'Daily 08:30'")
        raise typer.Exit(1)

    if not HEARTBEAT_FILE.exists():
        _init_heartbeat_file()
        console.print(f"[dim]Created {HEARTBEAT_FILE}[/dim]")

    task_id = "task-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    task = {
        "id": task_id,
        "name": name,
        "frequency": canonical,
        "command": command,
        "description": description,
        "insights": str(insights).lower(),
    }

    if save_task_to_heartbeat(task):
        console.print("[green][OK] Task added[/green]")
        console.print(f"  ID:       [cyan]{task_id}[/cyan]")
        console.print(f"  Name:     {name}")
        console.print(f"  Schedule: {canonical}")
        console.print(f"  Command:  {command}")
        console.print("\nRun [cyan]sh heartbeat list[/cyan] to verify.")
    else:
        console.print("[red]Failed to add task.[/red]")
        raise typer.Exit(1)


def save_task_to_heartbeat(task: dict) -> bool:
    """Save a new scheduled task entry to Heartbeat.md.

    This is the single owner of the Heartbeat.md write format.
    Called by cli/ai/executor.py::save_scheduled_task() so that
    format knowledge lives only in this module.
    """
    if not HEARTBEAT_FILE.exists():
        _init_heartbeat_file()

    try:
        content = HEARTBEAT_FILE.read_text(encoding="utf-8")

        # Count existing tasks to assign a number
        existing_count = len(re.findall(r"^### \d+\.", content, re.MULTILINE))
        task_number = existing_count + 1
        task_id = task.get("id") or "task-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

        # Strip newlines/backticks from all user-controlled fields to prevent
        # Markdown injection. See _safe_field() module-level docstring.
        safe_name = _safe_field(task.get("name", "New Task"))
        safe_freq = _safe_field(task.get("frequency", "Daily 00:00"))
        safe_cmd = _safe_field(task.get("command", "sh analytics overview"))
        safe_desc = _safe_field(task.get("description", ""))
        safe_insights = _safe_field(str(task.get("insights", "false")))

        task_entry = (
            f"\n### {task_number}. {safe_name}\n"
            f"- **ID**: {task_id}\n"
            f"- **Frequency**: {safe_freq}\n"
            f"- **Status**: `pending`\n"
            f"- **Command**:\n"
            f"  ```bash\n"
            f"  {safe_cmd}\n"
            f"  ```\n"
            f"- **Description**: {safe_desc}\n"
            f"- **AI Insights**: {safe_insights}\n"
            f"\n---\n\n"
        )

        insert_marker = "## Execution Log"
        if insert_marker not in content:
            insert_marker = "## Add New Task Template"

        if insert_marker in content:
            content = content.replace(insert_marker, task_entry + insert_marker)
        else:
            content += task_entry

        tmp = _heartbeat_tmp_path()
        try:
            tmp.write_text(content, encoding="utf-8")
            tmp.replace(HEARTBEAT_FILE)
        finally:
            tmp.unlink(missing_ok=True)
        return True

    except Exception as e:
        console.print(f"[red]Failed to save scheduled task: {e}[/red]")
        return False


if __name__ == "__main__":
    app()
