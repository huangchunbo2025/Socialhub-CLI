"""Command executor — runs CLI commands and multi-step plans."""

import logging
import shlex
import subprocess
import sys
import time

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..config import load_config
from .trace import TraceLogger

console = Console()
logger = logging.getLogger(__name__)

# Module-level TraceLogger singleton — initialized once on first plan execution.
# TraceLogger is stateless per-plan (each plan gets its own trace_id), so a
# shared instance is safe. Avoids re-reading config.json + re-compiling PII
# regexes on every call.
_tracer: "TraceLogger | None" = None


def _get_tracer() -> TraceLogger:
    global _tracer
    if _tracer is None:
        _tracer = TraceLogger(load_config().trace)
    return _tracer

MAX_PLAN_STEPS = 10
PLAN_WALL_CLOCK = 300


class _CircuitEntry:
    __slots__ = ("failures", "opened_at")

    def __init__(self) -> None:
        self.failures: int = 0
        self.opened_at: float = 0.0


class ToolCircuitBreaker:
    """Per-command circuit breaker: open after 3 consecutive failures, half-open after 60s."""

    _FAILURE_THRESHOLD = 3
    _COOLDOWN_SECONDS = 60

    def __init__(self):
        self._state: dict[str, _CircuitEntry] = {}  # cmd_prefix -> entry

    def key(self, cmd: str) -> str:
        # Use first two tokens as circuit key (e.g., "sh analytics")
        parts = cmd.strip().split()
        return " ".join(parts[:2]) if len(parts) >= 2 else parts[0] if parts else "unknown"

    def allow(self, cmd: str) -> bool:
        """Return True if command is allowed (circuit closed or half-open)."""
        key = self.key(cmd)
        if key not in self._state:
            return True
        entry = self._state[key]
        if entry.failures < self._FAILURE_THRESHOLD:
            return True
        # Circuit is open — check cooldown
        elapsed = time.time() - entry.opened_at
        if elapsed >= self._COOLDOWN_SECONDS:
            # Half-open: allow one probe
            entry.failures = self._FAILURE_THRESHOLD - 1
            return True
        return False

    def record_result(self, cmd: str, success: bool) -> None:
        """Record command result."""
        key = self.key(cmd)
        if key not in self._state:
            self._state[key] = _CircuitEntry()
        entry = self._state[key]
        if success:
            entry.failures = 0
        else:
            entry.failures += 1
            if entry.failures >= self._FAILURE_THRESHOLD:
                entry.opened_at = time.time()


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
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        output = result.stdout if result.stdout else result.stderr
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Command execution timeout"
    except Exception as e:
        return False, f"Execution error: {str(e)}"


def save_scheduled_task(task: dict) -> bool:
    """Save scheduled task to Heartbeat.md.

    Delegates to heartbeat module which owns the Heartbeat.md format.
    """
    from ..commands.heartbeat import save_task_to_heartbeat
    return save_task_to_heartbeat(task)


def execute_plan(
    steps: list[dict],
    original_query: str = "",
    session_id: str = "",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> None:
    """Execute a multi-step plan with progress display."""
    if not steps:
        console.print("[yellow]No steps to execute.[/yellow]")
        return

    if len(steps) > MAX_PLAN_STEPS:
        console.print(
            f"[red]Error: plan has {len(steps)} steps which exceeds the maximum of "
            f"{MAX_PLAN_STEPS}. Execution refused.[/red]"
        )
        return

    _config = load_config()
    _tracer = _get_tracer()
    _model = _config.ai.azure_deployment if _config.ai.provider == "azure" else _config.ai.openai_model
    trace_id = _tracer.log_plan_start(
        session_id=session_id,
        user_input=original_query,
        model=_model,
    )

    console.print(f"\n[bold cyan]Executing {len(steps)} steps...[/bold cyan]\n")

    all_results = []
    _success_count = 0

    plan_start = time.time()
    _confirm_wait_s = 0.0  # Accumulated time spent in typer.confirm() — excluded from budget
    _is_interactive = sys.stdin.isatty()
    # ToolCircuitBreaker is intentionally per-request (per execute_plan call).
    # A per-process singleton would cause false circuit-opens across unrelated queries.
    _breaker = ToolCircuitBreaker()

    report_step_idx = None
    for i, step in enumerate(steps):
        if "report" in step.get("command", "").lower():
            report_step_idx = i
            break

    for idx, step in enumerate(steps):
        step_num = step.get("number", idx + 1)
        description = step.get("description", f"Step {idx + 1}")
        command = step.get("command", "")

        if not command:
            console.print(f"[red][SKIP][/red] Step {step_num}: malformed step — missing 'command' field\n")
            all_results.append({
                "step": step_num,
                "description": description,
                "success": False,
                "output": "Skipped: malformed step (missing command field)",
            })
            console.print()
            continue

        # Wall-clock budget check (excluding time spent waiting for user input)
        if time.time() - plan_start - _confirm_wait_s > PLAN_WALL_CLOCK:
            console.print(
                f"[yellow]Warning: wall-clock budget of {PLAN_WALL_CLOCK}s exceeded. "
                f"Aborting remaining steps.[/yellow]"
            )
            break

        # Circuit breaker check
        if not _breaker.allow(command):
            console.print(
                f"[yellow]Warning: circuit breaker open for '{_breaker.key(command)}'. "
                f"Skipping step {step_num}.[/yellow]"
            )
            all_results.append({
                "step": step_num,
                "description": description,
                "success": False,
                "output": "Skipped: circuit breaker open",
            })
            console.print()
            continue

        console.print(f"[bold yellow]Step {step_num}:[/bold yellow] {description}")
        console.print(f"[dim]Command: {command}[/dim]\n")

        step_start = time.time()
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task(description="Executing...", total=None)
            success, output = execute_command(command)

        _breaker.record_result(command, success)
        _tracer.log_step(
            trace_id, step_num, command, success,
            int((time.time() - step_start) * 1000), len(output),
            error_msg=output if not success else "",
        )

        all_results.append({
            "step": step_num,
            "description": description,
            "success": success,
            "output": output,
        })
        if success:
            _success_count += 1

        if success:
            console.print(f"[green][OK][/green] Step {step_num} completed\n")
            if output:
                console.print(output)
            if report_step_idx is not None and idx == report_step_idx and original_query and all_results:
                if any(r["success"] for r in all_results):
                    try:
                        _emit_insights(original_query, all_results)
                    except Exception as _ins_err:
                        logger.warning("Insights generation failed (non-fatal): %s", _ins_err)
        else:
            console.print(f"[red][FAIL][/red] Step {step_num} failed\n")
            if output:
                console.print(f"[red]{output}[/red]")

            if idx < len(steps) - 1:
                if not _is_interactive:
                    console.print("[yellow]Non-interactive mode: aborting remaining steps on failure.[/yellow]")
                    _tracer.log_plan_end(
                        trace_id, len(steps),
                        _success_count,
                        prompt_tokens, completion_tokens,
                    )
                    return
                _confirm_t = time.time()
                _confirmed = typer.confirm("Continue with remaining steps?", default=False)
                _confirm_wait_s += time.time() - _confirm_t
                if not _confirmed:
                    console.print("[yellow]Execution cancelled[/yellow]")
                    _tracer.log_plan_end(
                        trace_id, len(steps),
                        _success_count,
                        prompt_tokens, completion_tokens,
                    )
                    return

        console.print()

    console.print("[bold green]All steps completed![/bold green]\n")

    _tracer.log_plan_end(
        trace_id, len(steps),
        _success_count,
        prompt_tokens, completion_tokens,
    )

    if report_step_idx is None and original_query and any(r["success"] for r in all_results):
        try:
            _emit_insights(original_query, all_results)
        except Exception as _ins_err:
            logger.warning("Insights generation failed (non-fatal): %s", _ins_err)
