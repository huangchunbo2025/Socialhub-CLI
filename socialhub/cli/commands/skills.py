"""Skills management commands."""

from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

from ..skills.manager import SkillManager, SkillManagerError
from ..skills.registry import SkillRegistry
from ..skills.loader import SkillLoader, SkillLoadError
from ..skills.store_client import StoreError
from ..skills.security import SecurityError
from ..output.table import print_success, print_error, print_warning, print_info

app = typer.Typer(help="Skills Store - Install and manage official skills")
console = Console()


@app.command("browse")
def browse_skills(
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter by category"),
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
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter by category"),
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
    name: str = typer.Argument(..., help="Skill name (optionally with @version)"),
    force: bool = typer.Option(False, "--force", "-f", help="Force reinstall"),
) -> None:
    """Install a skill from the official store."""
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
            console.print(f"\n[dim]Use 'skills list' to see installed skills[/dim]")

    except SkillManagerError as e:
        print_error(str(e))
        raise typer.Exit(1)
    except SecurityError as e:
        print_error(f"Security error: {e}")
        raise typer.Exit(1)
    except StoreError as e:
        print_error(f"Store error: {e.message}")
        raise typer.Exit(1)


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
    name: Optional[str] = typer.Argument(None, help="Skill name (or --all for all)"),
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
) -> None:
    """List installed skills."""
    registry = SkillRegistry()
    skills = registry.list_installed()

    if enabled_only:
        skills = [s for s in skills if s.enabled]

    if not skills:
        print_info("No skills installed")
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

    # Stats
    stats = registry.get_stats()
    console.print(f"\n[dim]Total: {stats['total_installed']} | Enabled: {stats['enabled']} | Disabled: {stats['disabled']}[/dim]")


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


@app.command("run")
def run_skill_command(
    command: str = typer.Argument(..., help="Command in format 'skill:command' or 'skill command'"),
    args: Optional[list[str]] = typer.Argument(None, help="Command arguments"),
) -> None:
    """Run a command from an installed skill."""
    # Parse command
    if ":" in command:
        skill_name, cmd_name = command.split(":", 1)
    elif " " in command:
        skill_name, cmd_name = command.split(" ", 1)
    else:
        print_error("Invalid command format. Use 'skill:command' or 'skill command'")
        raise typer.Exit(1)

    try:
        loader = SkillLoader()
        result = loader.execute_command(skill_name, cmd_name, *(args or []))

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
    name: Optional[str] = typer.Argument(None, help="Skill name (optional)"),
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
