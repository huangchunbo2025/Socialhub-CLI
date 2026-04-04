"""Authentication management commands (sh auth login/logout/status)."""

from datetime import datetime, timezone

import typer
from rich.console import Console
from rich.panel import Panel

from ..auth.oauth_client import OAuthClient, OAuthError
from ..auth.prompts import prompt_password
from ..auth.token_store import delete_oauth_token, load_oauth_token, save_oauth_token
from ..config import load_config

app = typer.Typer(help="Authentication management commands")
console = Console()


@app.command("login")
def login(
    tenant_id: str | None = typer.Option(None, "--tenant", "-t", help="Tenant ID"),
    account: str | None = typer.Option(None, "--account", "-a", help="Login account"),
    password: str | None = typer.Option(None, "--password", "-p", help="Account password"),
    show_password: bool = typer.Option(
        False,
        "--show-password",
        help="Show typed password instead of hiding it during interactive prompt",
    ),
) -> None:
    """Authenticate with the SocialHub platform."""
    config = load_config()
    oauth = config.oauth

    if not oauth.auth_url:
        console.print(
            "[red]Error: auth_url is not configured.[/red]\n"
            "Run: [cyan]sh config set oauth.auth_url YOUR_AUTH_URL[/cyan]"
        )
        raise typer.Exit(1)

    if not tenant_id:
        tenant_id = typer.prompt("Tenant ID")
    if not account:
        account = typer.prompt("Account")
    if not password:
        password = prompt_password(explicit_visible=show_password)

    try:
        client = OAuthClient(oauth.auth_url)
        data = client.fetch_token(tenant_id, account, password)
        save_oauth_token(data)
        console.print(
            f"[green]Login successful.[/green] "
            f"[dim]({data.get('email', '')})[/dim]"
        )
    except OAuthError as exc:
        console.print(f"[red]Login failed: {exc.message}[/red]")
        raise typer.Exit(1)


@app.command("logout")
def logout() -> None:
    """Clear local auth token (log out)."""
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
            f"Email:       {token.get('email', '-')}\n"
            f"Tenant:      {token.get('tenant_id', '-')}\n"
            f"Expires at:  {expires_display}\n"
            f"Server:      {oauth.auth_url}"
        )
    else:
        content = (
            f"[red]Not authenticated[/red]\n"
            f"Server:  {oauth.auth_url or '(not configured)'}\n"
            "Run: [cyan]sh auth login[/cyan]"
        )

    console.print(Panel(content, title="Auth Status", border_style="blue"))
