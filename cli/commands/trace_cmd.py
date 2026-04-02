"""AI decision trace commands."""

import json
from collections import deque
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from ..config import load_config
from ..output.table import print_error, print_info, print_success

app = typer.Typer(help="View and manage AI decision traces")
console = Console()


@app.command("list")
def list_traces(
    limit: int = typer.Option(20, "--limit", "-l", help="Number of recent entries"),
) -> None:
    """List recent AI decision trace entries."""
    config = load_config()
    trace_file = Path(config.trace.trace_dir) / "ai_trace.jsonl"

    if not trace_file.exists():
        print_info("No trace file found. Traces are written when AI commands are executed.")
        return

    recent: deque = deque(maxlen=limit)
    try:
        with open(trace_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        recent.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except OSError as e:
        print_error(f"Cannot read trace file: {e}")
        raise typer.Exit(1)

    if not recent:
        print_info("Trace file is empty")
        return

    table = Table(title=f"Recent Traces (last {len(recent)} of up to {limit})", show_header=True)
    table.add_column("Timestamp", style="dim", width=22)
    table.add_column("Type", width=14)
    table.add_column("Trace ID", style="cyan", width=18)
    table.add_column("Detail", width=40)

    for entry in recent:
        ts = entry.get("ts", "")[:19].replace("T", " ")
        etype = entry.get("type", "")
        trace_id = entry.get("trace_id", "")[:16]

        # Build detail string based on type
        if etype == "plan_start":
            detail = f"query: {entry.get('user_input', '')[:35]}"
        elif etype == "step":
            detail = f"step {entry.get('step', '?')}: {entry.get('command', '')[:30]}"
        elif etype == "plan_end":
            detail = f"steps: {entry.get('total', '?')} success: {entry.get('succeeded', '?')}"
        else:
            detail = str(entry)[:40]

        table.add_row(ts, etype, trace_id, detail)

    console.print(table)
    console.print(f"\n[dim]Trace file: {trace_file}[/dim]")


@app.command("clear")
def clear_traces(
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Clear the AI trace log."""
    config = load_config()
    trace_file = Path(config.trace.trace_dir) / "ai_trace.jsonl"

    if not trace_file.exists():
        print_info("No trace file to clear")
        return

    if not confirm:
        confirm = typer.confirm(f"Clear trace file at {trace_file}?", default=False)
    if not confirm:
        console.print("Cancelled.")
        raise typer.Exit(0)

    try:
        trace_file.unlink()
        print_success("Trace file cleared")
    except OSError as e:
        print_error(f"Failed to clear trace file: {e}")
        raise typer.Exit(1)


@app.command("status")
def trace_status() -> None:
    """Show trace configuration and file status."""
    config = load_config()
    tc = config.trace
    trace_file = Path(tc.trace_dir) / "ai_trace.jsonl"

    console.print("\n[bold]Trace Configuration[/bold]")
    console.print(f"  Enabled:          {tc.enabled}")
    console.print(f"  PII masking:      {tc.pii_masking}")
    console.print(f"  Max file size:    {tc.max_file_size_mb} MB")
    console.print(f"  Trace directory:  {tc.trace_dir}")

    console.print("\n[bold]Trace File[/bold]")
    if trace_file.exists():
        size_kb = trace_file.stat().st_size / 1024
        console.print(f"  Path:   {trace_file}")
        console.print(f"  Size:   {size_kb:.1f} KB")
    else:
        console.print("  [dim]Not yet created[/dim]")
