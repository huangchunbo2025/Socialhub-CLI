"""Session management commands."""


import typer
from rich.console import Console
from rich.table import Table

from ..ai.session import SessionStore
from ..output.table import print_error, print_info, print_success

app = typer.Typer(help="Manage AI conversation sessions")
console = Console()


@app.command("list")
def list_sessions(
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum number of sessions to show"),
) -> None:
    """List all active sessions."""
    store = SessionStore()
    sessions = store.list_sessions()[:limit]

    if not sessions:
        print_info("No active sessions")
        console.print("[dim]Start a session with: sh -c <query>[/dim]")
        return

    table = Table(title="Active Sessions", show_header=True)
    table.add_column("Session ID", style="cyan")
    table.add_column("Created")
    table.add_column("Last Active")
    table.add_column("Turns", justify="right")

    for s in sessions:
        table.add_row(
            s["session_id"],
            s["created_at"],
            s["last_active"],
            str(s["turns"]),
        )

    console.print(table)
    console.print("\n[dim]Continue a session: sh -c <session_id> <query>[/dim]")


@app.command("clear")
def clear_sessions(
    session_id: str | None = typer.Argument(None, help="Session ID to clear (clears all if omitted)"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Clear one session or all sessions."""
    store = SessionStore()

    if session_id is None:
        if not confirm:
            confirm = typer.confirm("Clear all sessions?", default=False)
        if not confirm:
            console.print("Cancelled.")
            raise typer.Exit(0)

    count = store.clear(session_id)
    if count:
        print_success(f"Cleared {count} session(s)")
    else:
        print_info("No sessions found to clear")


@app.command("purge")
def purge_expired() -> None:
    """Remove all expired sessions."""
    store = SessionStore()
    count = store.purge_expired()
    print_success(f"Purged {count} expired session(s)")


@app.command("show")
def show_session(
    session_id: str = typer.Argument(..., help="Session ID"),
) -> None:
    """Show conversation history for a session."""
    store = SessionStore()
    session = store.load(session_id)

    if session is None:
        print_error(f"Session '{session_id}' not found or expired")
        raise typer.Exit(1)

    console.print(f"\n[bold]Session:[/bold] {session.session_id}")
    console.print(f"[bold]Turns:[/bold] {len(session.messages) // 2}\n")

    for msg in session.messages:
        role = msg["role"]
        content = msg["content"]
        if role == "user":
            console.print(f"[bold cyan]You:[/bold cyan] {content}")
        else:
            console.print(
                f"[bold green]AI:[/bold green] {content[:200]}{'...' if len(content) > 200 else ''}"
            )
        console.print()
