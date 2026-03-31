"""OAuth2 authentication gate.

Called before any CLI command to ensure the user is authenticated.
If oauth.enabled is False (default), the gate is a no-op for backward compatibility.
"""

import typer
from rich.console import Console

from ..config import load_config
from .oauth_client import OAuthClient, OAuthError
from .token_store import get_refresh_token, load_oauth_token, save_oauth_token

console = Console()


def ensure_authenticated() -> None:
    """Verify the user holds a valid OAuth2 token.

    Flow:
    1. oauth.enabled == False → return (no-op)
    2. Valid cached token → return
    3. Expired access_token + valid refresh_token → refresh & return
    4. No token at all → prompt username/password → fetch & save
    5. All attempts fail → raise typer.Exit(1)
    """
    config = load_config()
    oauth = config.oauth

    # ── 1. Gate disabled ────────────────────────────────────────────
    if not oauth.enabled:
        return

    # ── Validate config ─────────────────────────────────────────────
    if not oauth.token_url or not oauth.client_id:
        console.print(
            "[red]Error: OAuth2 is enabled but not configured.[/red]\n"
            "Run the following commands:\n"
            "  [cyan]sh config set oauth.token_url YOUR_TOKEN_URL[/cyan]\n"
            "  [cyan]sh config set oauth.client_id YOUR_CLIENT_ID[/cyan]"
        )
        raise typer.Exit(1)

    # ── 2. Valid cached token ───────────────────────────────────────
    cached = load_oauth_token()
    if cached and cached.get("access_token"):
        return

    client = OAuthClient(oauth.token_url, oauth.client_id, oauth.scopes)

    # ── 3. Try refresh ──────────────────────────────────────────────
    refresh_token = get_refresh_token()
    if refresh_token:
        try:
            data = client.refresh_access_token(refresh_token)
            save_oauth_token(
                access_token=data["access_token"],
                refresh_token=data.get("refresh_token", refresh_token),
                expires_in=int(data.get("expires_in", 3600)),
                token_type=data.get("token_type", "Bearer"),
            )
            console.print("[dim]Token refreshed.[/dim]")
            return
        except OAuthError:
            # Refresh failed, fall through to credential prompt
            pass

    # ── 4. Prompt for credentials ───────────────────────────────────
    console.print("[yellow]Authentication required. Please log in.[/yellow]")
    username = typer.prompt("Username")
    password = typer.prompt("Password", hide_input=True)

    try:
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
