"""CLI run history — record, list, show, and rerun past commands."""

import json
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box as rich_box

app = typer.Typer(help="Run history: record and replay past CLI commands")
console = Console()

RUNS_DIR = Path.home() / ".socialhub" / "runs"


def _runs_dir() -> Path:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    return RUNS_DIR


def save_run(
    command: str,
    args: list[str],
    status: str = "ok",
    output_snippet: str = "",
    sql_trace: list[dict] | None = None,
    exec_time_ms: int | None = None,
    output_artifact: str | None = None,
) -> str:
    """Persist a run record and return the run_id.

    F4 auditability fields:
      sql_trace:       list of {sql, database} dicts captured during the run
      exec_time_ms:    wall-clock duration in milliseconds
      output_artifact: absolute path to any exported file
    """
    now = datetime.now()
    run_id = now.strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:6]
    record = {
        "run_id":          run_id,
        "timestamp":       now.isoformat(timespec="seconds"),
        "command":         command,
        "args":            args,
        "status":          status,
        "output_snippet":  output_snippet[:500],
        "exec_time_ms":    exec_time_ms,
        "output_artifact": output_artifact,
        "sql_trace":       sql_trace or [],
    }
    path = _runs_dir() / f"{run_id}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return run_id


def _load_run(run_id: str) -> Optional[dict]:
    runs = _runs_dir()
    path = runs / f"{run_id}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, IsADirectoryError):
        # Prefix search fallback
        matches = sorted(runs.glob(f"{run_id}*.json"))
        if not matches:
            return None
        try:
            return json.loads(matches[-1].read_text(encoding="utf-8"))
        except Exception:
            return None
    except Exception:
        return None


def _all_runs(limit: int = 50) -> list[dict]:
    runs_dir = _runs_dir()
    files = sorted(runs_dir.glob("*.json"), reverse=True)[:limit]
    records = []
    for f in files:
        try:
            records.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return records


@app.command("list")
def history_list(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of recent runs to show"),
    status: Optional[str] = typer.Option(None, "--status", "-s",
                                          help="Filter by status: ok / error"),
) -> None:
    """List recent CLI run history."""
    runs = _all_runs(limit * 2)  # fetch extra for filtering

    if status:
        runs = [r for r in runs if r.get("status") == status]

    runs = runs[:limit]

    if not runs:
        console.print("[dim]No run history found.[/dim]")
        return

    tbl = Table(
        title=f"Run History (last {len(runs)})",
        box=rich_box.SIMPLE_HEAVY,
        header_style="bold cyan",
    )
    tbl.add_column("Run ID",    style="dim",    min_width=22)
    tbl.add_column("Timestamp", style="dim",    width=20)
    tbl.add_column("Command",   style="bold",   min_width=30)
    tbl.add_column("Status",    justify="center", width=8)

    for r in runs:
        ts  = r.get("timestamp", "-")[:19]
        cmd = r.get("command", "-")
        args = " ".join(r.get("args", []))
        full = f"{cmd} {args}".strip()
        if len(full) > 60:
            full = full[:57] + "..."
        st  = r.get("status", "ok")
        st_disp = f"[green]{st}[/green]" if st == "ok" else f"[red]{st}[/red]"
        tbl.add_row(r.get("run_id", "-"), ts, full, st_disp)

    console.print(tbl)
    console.print(
        f"\n[dim]Run [bold]sh history show <run_id>[/bold] for details, "
        f"[bold]sh history rerun <run_id>[/bold] to replay.[/dim]"
    )


@app.command("show")
def history_show(
    run_id: str = typer.Argument(..., help="Run ID (or prefix) to inspect"),
) -> None:
    """Show details for a specific run."""
    record = _load_run(run_id)
    if not record:
        console.print(f"[red]Run not found: {run_id}[/red]")
        raise typer.Exit(1)

    st = record.get("status", "ok")
    st_color = "green" if st == "ok" else "red"
    exec_ms  = record.get("exec_time_ms")
    artifact = record.get("output_artifact")
    exec_str = f"{exec_ms:,} ms" if exec_ms is not None else "-"
    art_str  = artifact or "-"
    summary = (
        f"Run ID:    [bold]{record['run_id']}[/bold]\n"
        f"Timestamp: {record.get('timestamp', '-')}\n"
        f"Command:   [cyan]{record.get('command', '-')}[/cyan] "
        f"{' '.join(record.get('args', []))}\n"
        f"Status:    [{st_color}]{st}[/{st_color}]\n"
        f"Exec time: {exec_str}\n"
        f"Artifact:  {art_str}"
    )
    console.print(Panel(summary, title="[bold cyan]Run Detail[/bold cyan]", border_style="cyan"))

    # SQL trace
    sql_trace = record.get("sql_trace", [])
    if sql_trace:
        console.print(f"\n[dim]SQL Trace ({len(sql_trace)} queries):[/dim]")
        for i, entry in enumerate(sql_trace, 1):
            console.print(f"  [dim]{i}. [{entry.get('database','-')}][/dim]")
            console.print(f"     [dim]{entry.get('sql','')[:200]}[/dim]")

    snippet = record.get("output_snippet", "")
    if snippet:
        console.print("\n[dim]Output snippet:[/dim]")
        console.print(Panel(snippet, border_style="dim"))


@app.command("rerun")
def history_rerun(
    run_id: str = typer.Argument(..., help="Run ID (or prefix) to re-execute"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print command without executing"),
) -> None:
    """Re-execute a previous run."""
    record = _load_run(run_id)
    if not record:
        console.print(f"[red]Run not found: {run_id}[/red]")
        raise typer.Exit(1)

    cmd   = record.get("command", "")
    args  = record.get("args", [])
    full  = [sys.executable, "-m", "cli.main"] + shlex.split(cmd) + args

    console.print(f"[dim]Replaying:[/dim] [cyan]{' '.join(full[2:])}[/cyan]")

    if dry_run:
        console.print("[yellow]Dry run — command not executed.[/yellow]")
        return

    result = subprocess.run(full, check=False)
    if result.returncode != 0:
        raise typer.Exit(result.returncode)


@app.command("clear")
def history_clear(
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Delete all run history records."""
    runs_dir = _runs_dir()
    files = list(runs_dir.glob("*.json"))
    if not files:
        console.print("[dim]No history to clear.[/dim]")
        return

    if not confirm:
        typer.confirm(f"Delete {len(files)} run record(s)?", abort=True)

    for f in files:
        f.unlink(missing_ok=True)
    console.print(f"[green]Cleared {len(files)} run record(s).[/green]")
