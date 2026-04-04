"""OAuth2 authentication gate.

Called before any CLI command to ensure the user is authenticated.
If oauth.enabled is False (default), the gate is a no-op for backward compatibility.
"""

import logging
import os
import sys

logger = logging.getLogger(__name__)

import typer
from rich.console import Console

from ..config import load_config
from .oauth_client import OAuthClient, OAuthError
from .prompts import should_show_password, prompt_password
from .token_store import get_stored_token, load_oauth_token, save_oauth_token

console = Console()


def ensure_authenticated() -> None:
    """Verify the user holds a valid SocialHub auth token.

    Flow:
    1. oauth.enabled == False  -> return (no-op)
    2. Valid cached token       -> return
    3. Expired token + refresh  -> refresh & return
    4. No token at all          -> prompt account/password -> fetch & save
    5. All attempts fail        -> raise typer.Exit(1)
    """
    # ── 0. Subprocess skip (set by executor.py when spawning sub-CLI) ────
    # This env var is set only by our own executor, never exported to user shells.
    from . import SUBPROCESS_AUTH_SKIP_ENV
    if os.environ.get(SUBPROCESS_AUTH_SKIP_ENV):
        return

    config = load_config()
    oauth = config.oauth

    # ── 1. Gate disabled ────────────────────────────────────────────
    if not oauth.enabled:
        return

    # ── Validate config ─────────────────────────────────────────────
    if not oauth.auth_url:
        console.print(
            "[red]Error: OAuth2 is enabled but auth_url is not configured.[/red]\n"
            "Run: [cyan]sh config set oauth.auth_url YOUR_AUTH_URL[/cyan]"
        )
        raise typer.Exit(1)

    # ── 2. Valid cached token ───────────────────────────────────────
    cached = load_oauth_token()
    if cached and cached.get("token"):
        if not cached.get("_grace"):
            return  # Token still valid — no action needed
        # Token in grace period — try refresh, fall back to using grace token
        logger.debug("Token in grace period, attempting refresh")

    client = OAuthClient(oauth.auth_url)

    # ── 3. Try refresh ──────────────────────────────────────────────
    stored = get_stored_token()
    if stored and stored.get("refresh_token") and stored.get("token"):
        try:
            data = client.refresh_token(
                current_token=stored["token"],
                refresh_token=stored["refresh_token"],
            )
            save_oauth_token(data)
            console.print("[dim]Token refreshed.[/dim]")
            return
        except OAuthError as e:
            logger.debug("Token refresh failed: %s", e)
            # If we have a grace-period token, use it as fallback
            if cached and cached.get("_grace") and cached.get("token"):
                logger.debug("Using grace-period token as fallback")
                return

    # ── 4. Prompt for credentials ───────────────────────────────────
    if not sys.stdin.isatty():
        console.print(
            "[red]Authentication required but running in non-interactive mode.[/red]\n"
            "Set [cyan]SOCIALHUB_OAUTH_ENABLED=false[/cyan] or pre-configure credentials "
            "via [cyan]sh config set oauth.auth_url ...[/cyan] and log in interactively first."
        )
        raise typer.Exit(1)

    console.print("[yellow]Authentication required. Please log in.[/yellow]")
    if not should_show_password():
        console.print(
            "[dim]Password input is hidden. In PowerShell, characters may not appear while typing."
            " Set SOCIALHUB_SHOW_PASSWORD=1 to use visible input if needed.[/dim]"
        )
    tenant_id = typer.prompt("Tenant ID")
    account = typer.prompt("Account")
    password = prompt_password()

    try:
        data = client.fetch_token(tenant_id, account, password)
        save_oauth_token(data)
        console.print(
            f"[green]Login successful.[/green] "
            f"[dim]({data.get('email', '')})[/dim]"
        )
    except OAuthError as exc:
        console.print(f"[red]Login failed: {exc.message}[/red]")
        raise typer.Exit(1)
