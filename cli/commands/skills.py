"""Skills management commands."""

import json
import re

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..output.table import print_error, print_info, print_success, print_warning
from ..skills.loader import SkillLoader, SkillLoadError
from ..skills.manager import SkillManager, SkillManagerError
from ..skills.registry import SkillRegistry
from ..skills.security import SecurityError, SkillHealthChecker
from ..skills.store_client import SkillsStoreClient, StoreError

app = typer.Typer(help="Skills Store - Install and manage official skills")
console = Console()


@app.command("login")
def login_store(
    email: str | None = typer.Option(None, "--email", "-e", help="Account email"),
    password: str | None = typer.Option(None, "--password", "-p", help="Account password"),
) -> None:
    """Log in to SocialHub.AI Skills Store to sync your skill library."""
    if not email:
        email = typer.prompt("Email")
    if not password:
        password = typer.prompt("Password", hide_input=True)

    try:
        with SkillsStoreClient() as client:
            user = client.login(email, password)
            name = user.get("user", {}).get("name") or user.get("name") or email
            print_success(f"Logged in as {name}")
            console.print("[dim]Your skill library will now sync between CLI and web.[/dim]")
    except StoreError as e:
        print_error(f"Login failed: {e.message}")
        raise typer.Exit(1)


@app.command("logout")
def logout_store() -> None:
    """Log out from SocialHub.AI Skills Store."""
    client = SkillsStoreClient()
    client.logout()
    print_success("Logged out from Skills Store")


@app.command("browse")
def browse_skills(
    category: str | None = typer.Option(None, "--category", "-c", help="Filter by category"),
    limit: int = typer.Option(20, "--limit", "-l", help="Number of results"),
) -> None:
    """Browse available skills in the official store."""
    try:
        with SkillManager() as manager:
            console.print("\n[bold cyan]SocialHub.AI Skills Store[/bold cyan]")
            console.print("[dim]Official certified skills only[/dim]")

            skills = manager.search(category=category)

            # Check if in demo mode (after first request)
            if manager.store._force_demo or manager.store._demo_mode:
                console.print("[yellow]Demo Mode: Showing sample skills (Store unavailable)[/yellow]\n")

            if not skills:
                print_info("No skills found")
                return

            table = Table(title="Available Skills", show_header=True)
            table.add_column("Name", style="cyan")
            table.add_column("Description")
            table.add_column("Version")
            table.add_column("Category")
            table.add_column("Downloads", justify="right")
            table.add_column("Rating", justify="center")

            registry = SkillRegistry()

            for skill in skills[:limit]:
                # Check if installed
                installed = registry.get_installed(skill.name)
                name_display = skill.name
                if installed:
                    name_display = f"{skill.name} [green][OK][/green]"

                # Rating stars
                rating = "★" * int(skill.rating) + "☆" * (5 - int(skill.rating))

                table.add_row(
                    name_display,
                    skill.description[:50] + "..." if len(skill.description) > 50 else skill.description,
                    skill.version,
                    skill.category.value,
                    f"{skill.downloads:,}",
                    f"{rating} ({skill.rating:.1f})",
                )

            console.print(table)
            console.print(f"\n[dim]Showing {min(len(skills), limit)} of {len(skills)} skills[/dim]")
            console.print("[dim]Use 'skills info <name>' for details[/dim]")

    except StoreError as e:
        print_error(f"Store error: {e.message}")
        raise typer.Exit(1)


@app.command("search")
def search_skills(
    query: str = typer.Argument(..., help="Search query"),
    category: str | None = typer.Option(None, "--category", "-c", help="Filter by category"),
) -> None:
    """Search for skills in the store."""
    try:
        with SkillManager() as manager:
            skills = manager.search(query=query, category=category)

            if not skills:
                print_info(f"No skills found matching '{query}'")
                return

            console.print(f"\n[bold]Search results for '{query}':[/bold]\n")

            for skill in skills:
                certified_badge = "[green][Certified][/green]" if skill.certified else ""
                console.print(f"[cyan]{skill.name}[/cyan] v{skill.version} {certified_badge}")
                console.print(f"  {skill.description}")
                console.print(f"  [dim]Category: {skill.category.value} | Downloads: {skill.downloads:,}[/dim]")
                console.print()

    except StoreError as e:
        print_error(f"Store error: {e.message}")
        raise typer.Exit(1)


@app.command("info")
def skill_info(
    name: str = typer.Argument(..., help="Skill name"),
) -> None:
    """Show detailed information about a skill."""
    try:
        with SkillManager() as manager:
            skill = manager.get_skill_info(name)

            # Check if installed
            registry = SkillRegistry()
            installed = registry.get_installed(name)
            installed_version = installed.version if installed else None

            # Header
            console.print(Panel(
                f"[bold]{skill.display_name or skill.name}[/bold]\n"
                f"v{skill.version} by {skill.author}\n"
                f"[green][Certified by SocialHub.AI][/green]" if skill.certified else "",
                title=f"Skill: {skill.name}",
                border_style="cyan",
            ))

            # Installation status
            if installed:
                if installed_version == skill.version:
                    print_success(f"Installed (v{installed_version})")
                else:
                    print_warning(f"Installed (v{installed_version}) - Update available!")
            else:
                print_info("Not installed")

            # Description
            console.print(f"\n[bold]Description:[/bold]\n{skill.description}")

            # Category and tags
            console.print(f"\n[bold]Category:[/bold] {skill.category.value}")
            if skill.tags:
                console.print(f"[bold]Tags:[/bold] {', '.join(skill.tags)}")

            # Commands
            if skill.commands:
                console.print("\n[bold]Commands:[/bold]")
                for cmd in skill.commands:
                    console.print(f"  • [cyan]{cmd.name}[/cyan]: {cmd.description}")

            # Permissions
            if skill.permissions:
                console.print("\n[bold]Permissions Required:[/bold]")
                for perm in skill.permissions:
                    console.print(f"  • {perm.value}")

            # Dependencies
            if skill.dependencies.python:
                console.print("\n[bold]Python Dependencies:[/bold]")
                for dep in skill.dependencies.python:
                    console.print(f"  • {dep}")

            # Available versions
            if skill.versions:
                console.print(f"\n[bold]Available Versions:[/bold] {', '.join(skill.versions[:5])}")

            # Links
            if skill.homepage:
                console.print(f"\n[bold]Homepage:[/bold] {skill.homepage}")
            console.print(f"[bold]License:[/bold] {skill.license}")

            # Install hint
            if not installed:
                console.print(f"\n[dim]Install with: skills install {name}[/dim]")

    except StoreError as e:
        print_error(f"Store error: {e.message}")
        raise typer.Exit(1)


@app.command("install")
def install_skill(
    name: str = typer.Argument(..., help="Skill name or local .zip path (with --dev-mode)"),
    force: bool = typer.Option(False, "--force", "-f", help="Force reinstall"),
    dev_mode: bool = typer.Option(False, "--dev-mode", help="Install from local .zip file (development use only)"),
) -> None:
    """Install a skill from the official store, or a local .zip (--dev-mode)."""
    if dev_mode:
        import os as _os
        if not _os.getenv("SOCIALHUB_DEV"):
            print_error(
                "--dev-mode requires SOCIALHUB_DEV=1 environment variable. "
                "This flag bypasses signature verification and must not be used in production."
            )
            raise typer.Exit(1)
        _install_local_skill(name, force=force)
        return

    # Parse name@version
    version = None
    if "@" in name:
        name, version = name.rsplit("@", 1)

    try:
        with SkillManager() as manager:
            console.print(f"\n[bold]Installing skill: {name}[/bold]")
            if version:
                console.print(f"[dim]Version: {version}[/dim]")

            skill = manager.install(name, version=version, force=force)

            print_success(f"Successfully installed {skill.name} v{skill.version}")
            console.print("\n[dim]Use 'skills list' to see installed skills[/dim]")
            from ..ai.validator import invalidate_cmd_tree
            invalidate_cmd_tree()

    except SkillManagerError as e:
        print_error(str(e))
        raise typer.Exit(1)
    except SecurityError as e:
        print_error(f"Security error: {e}")
        raise typer.Exit(1)
    except StoreError as e:
        print_error(f"Store error: {e.message}")
        raise typer.Exit(1)


def _install_local_skill(path_str: str, force: bool = False) -> None:
    """Install a skill from a local zip file (dev mode only)."""
    import datetime
    import shutil
    import zipfile
    from pathlib import Path

    from ..skills.models import InstalledSkill, SkillCategory
    from ..skills.registry import SkillRegistry as _SkillRegistry

    local_path = Path(path_str)

    if not local_path.exists():
        print_error(f"File not found: {local_path}")
        raise typer.Exit(1)

    if local_path.suffix != ".zip":
        print_error("Dev mode only supports .zip files")
        raise typer.Exit(1)

    if not zipfile.is_zipfile(local_path):
        print_error(f"Not a valid zip file: {local_path}")
        raise typer.Exit(1)

    # Read manifest from zip
    try:
        with zipfile.ZipFile(local_path, "r") as zf:
            if "manifest.json" not in zf.namelist():
                print_error("Missing manifest.json in skill zip")
                raise typer.Exit(1)
            manifest_data = json.loads(zf.read("manifest.json").decode("utf-8"))
    except zipfile.BadZipFile as e:
        print_error(f"Corrupted zip: {e}")
        raise typer.Exit(1)

    skill_name = manifest_data.get("name")
    skill_version = manifest_data.get("version", "0.0.0-dev")

    if not skill_name:
        print_error("manifest.json missing 'name' field")
        raise typer.Exit(1)

    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_\-]{0,63}", skill_name):
        print_error(f"Invalid skill name in manifest.json: {skill_name!r}")
        raise typer.Exit(1)

    registry = _SkillRegistry()
    if not force and registry.is_installed(skill_name):
        print_warning(f"Skill '{skill_name}' is already installed. Use --force to reinstall.")
        raise typer.Exit(0)

    # Extract to skills installed directory
    skills_dir = registry.get_skill_path(skill_name)
    if skills_dir.exists() and force:
        shutil.rmtree(skills_dir)
    skills_dir.mkdir(parents=True, exist_ok=True)

    # Validate all member paths before extraction (zip-slip prevention)
    resolved_skills_dir = skills_dir.resolve()
    try:
        with zipfile.ZipFile(local_path, "r") as zf:
            for member in zf.namelist():
                try:
                    (resolved_skills_dir / member).resolve().relative_to(resolved_skills_dir)
                except ValueError:
                    shutil.rmtree(skills_dir, ignore_errors=True)
                    print_error(f"Unsafe zip entry detected (zip slip): {member}")
                    raise typer.Exit(1)
            zf.extractall(skills_dir)
    except typer.Exit:
        raise
    except Exception as e:
        shutil.rmtree(skills_dir, ignore_errors=True)
        print_error(f"Failed to extract zip: {e}")
        raise typer.Exit(1)

    # Register skill (dev mode — no signature verification)
    console.print("[yellow][DEV MODE] WARNING: Skipping signature verification — do not use in production.[/yellow]")

    category_str = manifest_data.get("category", "utility")
    try:
        category = SkillCategory(category_str)
    except ValueError:
        category = SkillCategory.UTILITY

    installed = InstalledSkill(
        name=skill_name,
        version=skill_version,
        display_name=manifest_data.get("display_name", skill_name),
        description=manifest_data.get("description", ""),
        path=str(skills_dir),
        category=category,
        enabled=True,
        installed_at=datetime.datetime.now(datetime.timezone.utc),
    )
    registry.register_skill(installed)

    print_success(f"[DEV MODE] Installed {skill_name} v{skill_version} from {local_path.name}")
    console.print("[dim]Note: This skill has not been signature-verified. Do not use in production.[/dim]")


@app.command("uninstall")
def uninstall_skill(
    name: str = typer.Argument(..., help="Skill name"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Uninstall a skill."""
    if not confirm:
        confirm = typer.confirm(f"Uninstall skill '{name}'?")

    if not confirm:
        console.print("Operation cancelled.")
        raise typer.Exit(0)

    try:
        with SkillManager() as manager:
            manager.uninstall(name)
            print_success(f"Successfully uninstalled {name}")

    except SkillManagerError as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command("update")
def update_skill(
    name: str | None = typer.Argument(None, help="Skill name (or --all for all)"),
    all_skills: bool = typer.Option(False, "--all", "-a", help="Update all skills"),
) -> None:
    """Update installed skill(s)."""
    if not name and not all_skills:
        print_error("Specify a skill name or use --all")
        raise typer.Exit(1)

    try:
        with SkillManager() as manager:
            if all_skills:
                console.print("[bold]Checking for updates...[/bold]")

            updated = manager.update(name=name, all_skills=all_skills)

            if updated:
                print_success(f"Updated {len(updated)} skill(s):")
                for skill in updated:
                    console.print(f"  • {skill.name} → v{skill.version}")
            else:
                print_info("All skills are up to date")

    except SkillManagerError as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command("list")
def list_skills(
    enabled_only: bool = typer.Option(False, "--enabled", help="Show only enabled skills"),
    cloud: bool = typer.Option(False, "--cloud", help="Show cloud library (requires login)"),
) -> None:
    """List skills. When logged in, shows your personal library synced with web."""
    with SkillsStoreClient() as client:
        # If logged in, merge cloud library with local install status
        if client.is_authenticated():
            try:
                cloud_skills = client.get_my_skills()
            except StoreError:
                cloud_skills = []

            if cloud_skills:
                registry = SkillRegistry()
                if enabled_only:
                    cloud_skills = [s for s in cloud_skills if s.get("is_enabled", True)]

                if not cloud_skills:
                    print_info("No skills in your library")
                    console.print("[dim]Use 'skills install <name>' to add skills[/dim]")
                    return

                table = Table(title="My Skills Library", show_header=True)
                table.add_column("Name", style="cyan")
                table.add_column("Version")
                table.add_column("Category")
                table.add_column("Status")
                table.add_column("Local")

                for s in cloud_skills:
                    status = "[green]Enabled[/green]" if s.get("is_enabled", True) else "[red]Disabled[/red]"
                    installed = registry.is_installed(s.get("skill_name", ""))
                    local_status = "[green]Installed[/green]" if installed else "[dim]Not installed[/dim]"
                    table.add_row(
                        s.get("skill_name", ""),
                        s.get("version", "-"),
                        s.get("category", "-"),
                        status,
                        local_status,
                    )

                console.print(table)
                enabled = sum(1 for s in cloud_skills if s.get("is_enabled", True))
                console.print(f"\n[dim]Total: {len(cloud_skills)} | Enabled: {enabled} | Synced with web[/dim]")
                return
            elif cloud_skills is not None:
                print_info("Your library is empty")
                console.print("[dim]Use 'skills install <name>' to add skills, or browse the web store[/dim]")
                return

        # Not authenticated or cloud fetch failed — show local registry
        registry = SkillRegistry()
        skills = registry.list_installed()

        if enabled_only:
            skills = [s for s in skills if s.enabled]

        if not skills:
            print_info("No skills installed")
            if not client.is_authenticated():
                console.print("[dim]Tip: Run 'skills login' to sync with web store[/dim]")
            else:
                console.print("[dim]Use 'skills browse' to discover skills[/dim]")
            return

        table = Table(title="Installed Skills", show_header=True)
        table.add_column("Name", style="cyan")
        table.add_column("Version")
        table.add_column("Category")
        table.add_column("Status")
        table.add_column("Installed")

        for skill in skills:
            status = "[green]Enabled[/green]" if skill.enabled else "[red]Disabled[/red]"
            installed_date = skill.installed_at.strftime("%Y-%m-%d") if skill.installed_at else "-"
            table.add_row(
                skill.name,
                skill.version,
                skill.category.value if hasattr(skill.category, "value") else str(skill.category),
                status,
                installed_date,
            )

        console.print(table)
        stats = registry.get_stats()
        console.print(f"\n[dim]Total: {stats['total_installed']} | Enabled: {stats['enabled']} | Disabled: {stats['disabled']}[/dim]")
        if not client.is_authenticated():
            console.print("[dim]Tip: Run 'skills login' to sync with web store[/dim]")


@app.command("enable")
def enable_skill(
    name: str = typer.Argument(..., help="Skill name"),
) -> None:
    """Enable a disabled skill."""
    try:
        with SkillManager() as manager:
            manager.enable(name)
            print_success(f"Skill '{name}' enabled")

    except SkillManagerError as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command("disable")
def disable_skill(
    name: str = typer.Argument(..., help="Skill name"),
) -> None:
    """Disable a skill."""
    try:
        with SkillManager() as manager:
            manager.disable(name)
            print_success(f"Skill '{name}' disabled")

    except SkillManagerError as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command("run", context_settings={"allow_extra_args": True, "allow_interspersed_args": False})
def run_skill_command(
    ctx: typer.Context,
    skill_name: str = typer.Argument(..., help="Skill name"),
    cmd_name: str = typer.Argument(..., help="Command name"),
) -> None:
    """Run a command from an installed skill.

    Examples:
        sh skill run report-generator generate --topic="Topic" --output=report.md
        sh skills run report-generator swot --subject="Company" --output=swot.md
    """
    # Get extra arguments passed after the command name
    extra_args = ctx.args

    try:
        loader = SkillLoader()

        # Parse keyword arguments from extra_args
        positional_args = []
        keyword_args = {}
        i = 0
        while i < len(extra_args):
            arg = extra_args[i]
            if arg.startswith("--"):
                # Handle --key=value or --key value formats
                if "=" in arg:
                    key, value = arg[2:].split("=", 1)
                    keyword_args[key.replace("-", "_")] = value
                else:
                    # Check if next arg is the value
                    key = arg[2:].replace("-", "_")
                    if i + 1 < len(extra_args) and not extra_args[i + 1].startswith("-"):
                        keyword_args[key] = extra_args[i + 1]
                        i += 1
                    else:
                        # Boolean flag
                        keyword_args[key] = True
            else:
                positional_args.append(arg)
            i += 1

        result = loader.execute_command(skill_name, cmd_name, *positional_args, **keyword_args)

        if result is not None:
            console.print(result)

    except SkillLoadError as e:
        print_error(str(e))
        raise typer.Exit(1)
    except SecurityError as e:
        print_error(f"Security error: {e}")
        raise typer.Exit(1)


@app.command("commands")
def list_skill_commands(
    name: str | None = typer.Argument(None, help="Skill name (optional)"),
) -> None:
    """List available commands from installed skills."""
    loader = SkillLoader()

    if name:
        # List commands for specific skill
        try:
            commands = loader.list_commands(name)

            console.print(f"\n[bold]Commands from skill '{name}':[/bold]\n")
            for cmd in commands:
                console.print(f"  [cyan]{cmd.name}[/cyan]: {cmd.description}")
                console.print(f"    [dim]Run: skills run {name}:{cmd.name}[/dim]")

        except SkillLoadError as e:
            print_error(str(e))
            raise typer.Exit(1)
    else:
        # List all commands
        all_commands = loader.list_all_commands()

        if not all_commands:
            print_info("No skill commands available")
            console.print("[dim]Install skills to add new commands[/dim]")
            return

        console.print("\n[bold]Available Skill Commands:[/bold]\n")
        for skill_name, commands in all_commands.items():
            console.print(f"[bold cyan]{skill_name}[/bold cyan]")
            for cmd in commands:
                console.print(f"  • {cmd.name}: {cmd.description}")
            console.print()


@app.command("cache")
def manage_cache(
    clear: bool = typer.Option(False, "--clear", help="Clear download cache"),
) -> None:
    """Manage skills cache."""
    registry = SkillRegistry()

    if clear:
        count = registry.clear_cache()
        print_success(f"Cleared {count} cached file(s)")
    else:
        # Show cache info
        cache_files = list(registry.cache_dir.glob("*.zip"))
        total_size = sum(f.stat().st_size for f in cache_files)

        console.print(f"[bold]Cache Directory:[/bold] {registry.cache_dir}")
        console.print(f"[bold]Cached Packages:[/bold] {len(cache_files)}")
        console.print(f"[bold]Total Size:[/bold] {total_size / 1024 / 1024:.2f} MB")

        if cache_files:
            console.print("\n[dim]Use 'skills cache --clear' to clear[/dim]")


@app.command("health")
def health_check(
    name: str | None = typer.Argument(None, help="Skill name (optional, checks all if omitted)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed results"),
) -> None:
    """Check health status of installed skills.

    Performs security checks including:
    - Certificate expiration
    - Revocation status
    - File integrity
    - Update availability
    """
    checker = SkillHealthChecker()

    if name:
        # Check specific skill
        result = checker.check_skill(name)
        _display_health_result(result, verbose)
    else:
        # Check all skills
        results = checker.check_all()

        if not results:
            print_info("No skills installed")
            return

        # Display summary
        summary = checker.get_summary(results)
        _display_health_summary(summary, results, verbose)


def _display_health_result(result, verbose: bool = False) -> None:
    """Display health check result for a single skill."""
    # Status colors
    status_colors = {
        "healthy": "green",
        "warning": "yellow",
        "critical": "red",
    }
    status_icons = {
        "healthy": "✓",
        "warning": "⚠",
        "critical": "✗",
    }

    color = status_colors.get(result.status, "white")
    icon = status_icons.get(result.status, "?")

    console.print(f"\n[bold]Health Check: {result.skill_name}[/bold]")
    console.print(f"Status: [{color}]{icon} {result.status.upper()}[/{color}]")
    console.print(f"Checked at: {result.checked_at.strftime('%Y-%m-%d %H:%M:%S')}")

    if verbose or result.status != "healthy":
        console.print("\n[bold]Check Details:[/bold]")

        table = Table(show_header=True, header_style="bold")
        table.add_column("Check", width=15)
        table.add_column("Status", width=10)
        table.add_column("Message", width=45)

        for check_name, check_result in result.checks.items():
            passed = check_result.get("passed", False)
            message = check_result.get("message", "")
            severity = check_result.get("severity", "info")

            if passed:
                status_str = "[green]PASS[/green]"
            else:
                if severity == "critical":
                    status_str = "[red]FAIL[/red]"
                else:
                    status_str = "[yellow]WARN[/yellow]"

            table.add_row(check_name, status_str, message)

        console.print(table)

    # Show issues
    issues = result.get_issues()
    if issues:
        console.print("\n[bold yellow]Issues Found:[/bold yellow]")
        for issue in issues:
            console.print(f"  • {issue}")


def _display_health_summary(summary: dict, results: list, verbose: bool = False) -> None:
    """Display health check summary for all skills."""
    console.print("\n[bold cyan]Skills Health Summary[/bold cyan]\n")

    # Summary stats
    total = summary["total"]
    healthy = summary["healthy"]
    warning = summary["warning"]
    critical = summary["critical"]

    console.print(f"Total Skills: {total}")
    console.print(f"[green]Healthy: {healthy}[/green]")
    if warning > 0:
        console.print(f"[yellow]Warning: {warning}[/yellow]")
    if critical > 0:
        console.print(f"[red]Critical: {critical}[/red]")

    # Results table
    console.print()
    table = Table(show_header=True, header_style="bold")
    table.add_column("Skill", width=25)
    table.add_column("Status", width=12)
    table.add_column("Issues", width=40)

    status_colors = {
        "healthy": "green",
        "warning": "yellow",
        "critical": "red",
    }

    for result in results:
        color = status_colors.get(result.status, "white")
        issues = result.get_issues()
        issues_str = "; ".join(issues[:2]) if issues else "-"
        if len(issues) > 2:
            issues_str += f" (+{len(issues) - 2} more)"

        table.add_row(
            result.skill_name,
            f"[{color}]{result.status.upper()}[/{color}]",
            issues_str,
        )

    console.print(table)

    # Show detailed results if verbose
    if verbose:
        for result in results:
            if result.status != "healthy":
                console.print()
                _display_health_result(result, verbose=True)
