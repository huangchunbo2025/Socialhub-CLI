"""Authentication management commands (sh auth login/logout/status)."""

from datetime import datetime, timezone
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from ..auth.oauth_client import OAuthClient, OAuthError
from ..auth.token_store import delete_oauth_token, load_oauth_token, save_oauth_token
from ..config import load_config

app = typer.Typer(help="Authentication management commands")
console = Console()


@app.command("login")
def login(
    username: Optional[str] = typer.Option(None, "--username", "-u", help="Account username"),
    password: Optional[str] = typer.Option(None, "--password", "-p", help="Account password"),
) -> None:
    """Authenticate with the SocialHub platform via OAuth2."""
    config = load_config()
    oauth = config.oauth

    if not oauth.enabled:
        console.print(
            "[yellow]OAuth2 is not enabled.[/yellow]\n"
            "Run: [cyan]sh config set oauth.enabled true[/cyan]"
        )
        raise typer.Exit(1)

    if not oauth.token_url or not oauth.client_id:
        console.print(
            "[red]Error: OAuth2 is not configured.[/red]\n"
            "Run:\n"
            "  [cyan]sh config set oauth.token_url YOUR_TOKEN_URL[/cyan]\n"
            "  [cyan]sh config set oauth.client_id YOUR_CLIENT_ID[/cyan]"
        )
        raise typer.Exit(1)

    if not username:
        username = typer.prompt("Username")
    if not password:
        password = typer.prompt("Password", hide_input=True)

    try:
        client = OAuthClient(oauth.token_url, oauth.client_id, oauth.scopes)
        data = client.fetch_token_with_password(username, password)
        save_oauth_token(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", ""),
            expires_in=int(data.get("expires_in", 3600)),
            token_type=data.get("token_type", "Bearer"),
        )
        console.print("[green]Login successful.[/green]")
    except OAuthError as exc:
        console.print(f"[red]Login failed: {exc.message}[/red]")
        raise typer.Exit(1)


@app.command("logout")
def logout() -> None:
    """Clear local OAuth2 token (log out)."""
    delete_oauth_token()
    console.print("[green]Logged out. Local token removed.[/green]")


@app.command("status")
def status() -> None:
    """Show current authentication status."""
    config = load_config()
    oauth = config.oauth

    if not oauth.enabled:
        console.print("[dim]OAuth2 auth gate is disabled.[/dim]")
        return

    token = load_oauth_token()
    if token:
        expires_at = token.get("expires_at", "unknown")
        try:
            exp = datetime.fromisoformat(expires_at)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            remaining = exp - datetime.now(timezone.utc)
            mins = int(remaining.total_seconds() // 60)
            expires_display = f"{expires_at}  ({mins} min remaining)"
        except Exception:
            expires_display = expires_at

        content = (
            f"[green]Authenticated[/green]\n"
            f"Token type:  {token.get('token_type', 'Bearer')}\n"
            f"Expires at:  {expires_display}\n"
            f"Server:      {oauth.token_url}"
        )
    else:
        content = (
            f"[red]Not authenticated[/red]\n"
            f"Server:  {oauth.token_url or '(not configured)'}\n"
            "Run: [cyan]sh auth login[/cyan]"
        )

    console.print(Panel(content, title="OAuth2 Status", border_style="blue"))
