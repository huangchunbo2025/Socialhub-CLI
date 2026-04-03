"""sh memory — persistent memory management commands."""

import sys

import typer
from rich import box as rich_box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(help="Manage AI memory: preferences, insights, and session summaries")
console = Console()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_manager():
    from ..memory import MemoryManager
    return MemoryManager()


# ---------------------------------------------------------------------------
# sh memory status
# ---------------------------------------------------------------------------


@app.command("status")
def memory_status() -> None:
    """Show a summary of current memory state."""
    mm = _get_manager()
    info = mm.get_status()

    if not info.get("enabled"):
        console.print("[yellow]Memory system is disabled (config.memory.enabled=false)[/yellow]")
        return

    tbl = Table(show_header=False, box=None, padding=(0, 2))
    tbl.add_column("Key", style="dim")
    tbl.add_column("Value", style="bold")

    tbl.add_row("Memory dir", str(info.get("memory_dir", "-")))
    tbl.add_row("Profile updated", info.get("profile_updated") or "never")
    tbl.add_row("Stored insights", str(info.get("insight_count", 0)))
    tbl.add_row("Session summaries", str(info.get("summary_count", 0)))
    tbl.add_row("Campaigns", str(info.get("campaign_count", 0)))

    console.print(Panel(tbl, title="[bold cyan]Memory Status[/bold cyan]", border_style="cyan"))


# ---------------------------------------------------------------------------
# sh memory list
# ---------------------------------------------------------------------------


@app.command("list")
def memory_list(
    type_filter: str | None = typer.Option(
        None, "--type", "-t",
        help="Filter by type: profile|insights|summaries|campaigns"
    ),
    sort_time: bool = typer.Option(False, "--sort=time", help="Sort by time instead of grouping"),
) -> None:
    """List all stored memory items."""
    mm = _get_manager()
    store = mm._store

    if type_filter in (None, "profile"):
        _print_profile(store)

    if type_filter in (None, "campaigns"):
        _print_campaigns(store)

    if type_filter in (None, "insights"):
        _print_insights(store)

    if type_filter in (None, "summaries"):
        _print_summaries(store)


def _print_profile(store) -> None:
    profile = store.load_user_profile()
    lines = []
    a = profile.analysis
    o = profile.output
    s = profile.scope
    if a.default_period:
        lines.append(f"default_period = {a.default_period}")
    if a.preferred_dimensions:
        lines.append(f"preferred_dimensions = {', '.join(a.preferred_dimensions)}")
    if a.key_metrics:
        lines.append(f"key_metrics = {', '.join(a.key_metrics)}")
    if a.rfm_focus:
        lines.append(f"rfm_focus = {', '.join(a.rfm_focus)}")
    if o.format:
        lines.append(f"output.format = {o.format}")
    if o.show_yoy:
        lines.append("output.show_yoy = true")
    if s.channels:
        lines.append(f"scope.channels = {', '.join(s.channels)}")

    if lines:
        console.print("\n[bold]User Preferences[/bold]")
        for line in lines:
            console.print(f"  {line}")


def _print_campaigns(store) -> None:
    campaigns = store.load_campaigns()
    if not campaigns:
        return
    console.print("\n[bold]Campaigns[/bold]")
    tbl = Table(box=rich_box.SIMPLE_HEAVY, header_style="bold cyan")
    tbl.add_column("ID", style="dim")
    tbl.add_column("Name")
    tbl.add_column("Period")
    tbl.add_column("Status", justify="center")
    tbl.add_column("Effect")
    for c in campaigns:
        status_str = f"[green]{c.status}[/green]" if c.status == "active" else f"[dim]{c.status}[/dim]"
        tbl.add_row(c.id, c.name, f"{c.period.start}~{c.period.end}", status_str, c.effect_summary or "-")
    console.print(tbl)


def _print_insights(store) -> None:
    insights = store.load_recent_insights(n=50)
    if not insights:
        return
    console.print("\n[bold]Analysis Insights[/bold]")
    tbl = Table(box=rich_box.SIMPLE_HEAVY, header_style="bold cyan")
    tbl.add_column("ID", style="dim", min_width=30)
    tbl.add_column("Date", width=12)
    tbl.add_column("Topic")
    tbl.add_column("Conf.", justify="center", width=6)
    for ins in insights:
        conf_color = "green" if ins.confidence == "high" else ("yellow" if ins.confidence == "medium" else "dim")
        tbl.add_row(ins.id, ins.date, ins.topic[:60], f"[{conf_color}]{ins.confidence}[/{conf_color}]")
    console.print(tbl)


def _print_summaries(store) -> None:
    summaries = store.load_recent_summaries(n=10)
    if not summaries:
        return
    console.print("\n[bold]Session Summaries[/bold]")
    for s in summaries:
        console.print(f"  [dim]{s.session_id}[/dim]  [{s.date}] {s.summary}")


# ---------------------------------------------------------------------------
# sh memory show
# ---------------------------------------------------------------------------


@app.command("show")
def memory_show(
    item_id: str = typer.Argument(..., help="ID to show: insight/<id> or summary/<session_id>"),
) -> None:
    """Show details for a specific memory item."""
    store = _get_manager()._store

    if item_id.startswith("insight/"):
        insight_id = item_id[len("insight/"):]
        path = store._insight_path(insight_id)
        if not path.exists():
            console.print(f"[red]Insight not found: {insight_id}[/red]")
            raise typer.Exit(1)
        import json
        data = json.loads(path.read_text(encoding="utf-8"))
        for k, v in data.items():
            console.print(f"  [dim]{k}:[/dim] {v}")

    elif item_id.startswith("summary/"):
        session_id = item_id[len("summary/"):]
        path = store._summary_path(session_id)
        if not path.exists():
            console.print(f"[red]Summary not found: {session_id}[/red]")
            raise typer.Exit(1)
        import json
        data = json.loads(path.read_text(encoding="utf-8"))
        for k, v in data.items():
            console.print(f"  [dim]{k}:[/dim] {v}")

    else:
        console.print("[red]Unknown item type. Use 'insight/<id>' or 'summary/<session_id>'[/red]")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# sh memory set
# ---------------------------------------------------------------------------


@app.command("set")
def memory_set(
    key: str = typer.Argument(..., help="Preference key, e.g. analysis.default_period"),
    value: str = typer.Argument(..., help="Value to set"),
) -> None:
    """Set a user preference value."""
    store = _get_manager()._store
    profile = store.load_user_profile()
    parts = key.split(".")

    try:
        if parts[0] == "analysis":
            sub = parts[1] if len(parts) > 1 else ""
            if sub == "default_period":
                profile.analysis.default_period = value
            elif sub == "preferred_dimensions":
                profile.analysis.preferred_dimensions = [v.strip() for v in value.split(",")]
            elif sub == "key_metrics":
                profile.analysis.key_metrics = [v.strip() for v in value.split(",")]
            elif sub == "rfm_focus":
                profile.analysis.rfm_focus = [v.strip() for v in value.split(",")]
            else:
                console.print(f"[red]Unknown key: {key}[/red]")
                raise typer.Exit(1)
        elif parts[0] == "output":
            sub = parts[1] if len(parts) > 1 else ""
            if sub == "format":
                profile.output.format = value
            elif sub == "show_yoy":
                profile.output.show_yoy = value.lower() in ("true", "1", "yes")
            elif sub == "precision":
                profile.output.precision = int(value)
            else:
                console.print(f"[red]Unknown key: {key}[/red]")
                raise typer.Exit(1)
        elif parts[0] == "role":
            profile.role = value
        else:
            console.print(f"[red]Unknown key: {key}[/red]")
            raise typer.Exit(1)

        store.save_user_profile(profile)
        console.print(f"[green]Set {key} = {value}[/green]")
    except (IndexError, ValueError) as e:
        console.print(f"[red]Error setting {key}: {e}[/red]")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# sh memory delete
# ---------------------------------------------------------------------------


@app.command("delete")
def memory_delete(
    item_id: str = typer.Argument(..., help="ID to delete: insight/<id> or summary/<session_id>"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a specific memory item."""
    store = _get_manager()._store

    if item_id.startswith("insight/"):
        insight_id = item_id[len("insight/"):]
        path = store._insight_path(insight_id)
        if not path.exists():
            console.print(f"[red]Insight not found: {insight_id}[/red]")
            raise typer.Exit(1)
        if not yes:
            typer.confirm(f"Delete insight '{insight_id}'?", abort=True)
        path.unlink()
        console.print(f"[green]Deleted insight: {insight_id}[/green]")

    elif item_id.startswith("summary/"):
        session_id = item_id[len("summary/"):]
        path = store._summary_path(session_id)
        if not path.exists():
            console.print(f"[red]Summary not found: {session_id}[/red]")
            raise typer.Exit(1)
        if not yes:
            typer.confirm(f"Delete summary '{session_id}'?", abort=True)
        path.unlink()
        console.print(f"[green]Deleted summary: {session_id}[/green]")

    else:
        console.print("[red]Use 'insight/<id>' or 'summary/<session_id>'[/red]")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# sh memory clear
# ---------------------------------------------------------------------------


@app.command("clear")
def memory_clear(
    type_filter: str | None = typer.Option(
        None, "--type", "-t",
        help="Clear only this type: insights|summaries|all"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete memory items. Use --yes to skip confirmation."""
    store = _get_manager()._store

    scope = type_filter or "all"
    if not yes:
        typer.confirm(
            f"Delete {scope} memory? This cannot be undone.",
            abort=True,
        )

    count = 0
    if scope in ("insights", "all"):
        for p in store._insights_dir.glob("*.json"):
            p.unlink(missing_ok=True)
            count += 1
    if scope in ("summaries", "all"):
        for p in store._summaries_dir.glob("*.json"):
            p.unlink(missing_ok=True)
            count += 1

    console.print(f"[green]Cleared {count} memory item(s).[/green]")


# ---------------------------------------------------------------------------
# sh memory init
# ---------------------------------------------------------------------------


@app.command("init")
def memory_init() -> None:
    """Interactive setup: answer a few questions to initialize your preferences."""
    is_tty = sys.stdin.isatty()
    console.print("[bold cyan]SocialHub Memory Setup[/bold cyan]")
    console.print("[dim]约 1 分钟，全部问题可跳过（直接回车）[/dim]\n")

    store = _get_manager()._store
    profile = store.load_user_profile()

    # Q1: Default analysis period
    period = _ask("默认分析时间窗口 (7d/30d/90d/all) [7d]: ", default="7d", is_tty=is_tty)
    if period:
        profile.analysis.default_period = period

    # Q2: Preferred dimensions
    dims = _ask("常用分析维度 (如 channel,province，多个用逗号分隔): ", default="", is_tty=is_tty)
    if dims:
        profile.analysis.preferred_dimensions = [d.strip() for d in dims.split(",") if d.strip()]

    # Q3: Key metrics
    metrics = _ask("关注的核心指标 (如 gmv,orders，多个用逗号分隔): ", default="", is_tty=is_tty)
    if metrics:
        profile.analysis.key_metrics = [m.strip() for m in metrics.split(",") if m.strip()]

    # Q4: Role
    role = _ask("角色 (operations/analyst/marketing) [operations]: ", default="operations", is_tty=is_tty)
    if role:
        profile.role = role

    store.save_user_profile(profile)
    console.print("\n[green]偏好已保存。下次 AI 查询时会自动使用这些设置。[/green]")
    console.print("[dim]可用 sh memory set <key> <value> 随时修改。[/dim]")


def _ask(prompt: str, default: str, is_tty: bool) -> str:
    if not is_tty:
        return default
    try:
        val = typer.prompt(prompt.rstrip(": "), default=default, show_default=False)
        return val.strip() if val else default
    except (EOFError, KeyboardInterrupt):
        return default


# ---------------------------------------------------------------------------
# sh memory add-campaign
# ---------------------------------------------------------------------------


@app.command("add-campaign")
def memory_add_campaign(
    campaign_id: str = typer.Option(..., "--id", help="Campaign ID (e.g. ACT001)"),
    name: str = typer.Option(..., "--name", help="Campaign name"),
    start: str = typer.Option(..., "--start", help="Start date (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", help="End date (YYYY-MM-DD)"),
    channel: str = typer.Option("", "--channel", help="Channel (optional)"),
    effect: str = typer.Option("", "--effect", help="Effect summary (optional, e.g. '+15% GMV')"),
) -> None:
    """Record a marketing campaign in memory for AI context."""
    from ..memory.models import Campaign, CampaignPeriod
    store = _get_manager()._store
    campaign = Campaign(
        id=campaign_id,
        name=name,
        period=CampaignPeriod(start=start, end=end),
        channel=channel,
        effect_summary=effect,
    )
    store.save_campaign(campaign)
    console.print(f"[green]Campaign '{name}' ({campaign_id}) saved.[/green]")
    console.print(f"[dim]Status: {campaign.status}[/dim]")


# ---------------------------------------------------------------------------
# sh memory update-campaign
# ---------------------------------------------------------------------------


@app.command("update-campaign")
def memory_update_campaign(
    campaign_id: str = typer.Option(..., "--id", help="Campaign ID to update"),
    effect: str | None = typer.Option(None, "--effect", help="Update effect summary"),
    end: str | None = typer.Option(None, "--end", help="Update end date"),
    notes: str | None = typer.Option(None, "--notes", help="Update notes"),
) -> None:
    """Update an existing campaign's details."""
    store = _get_manager()._store
    campaigns = store.load_campaigns()
    target = next((c for c in campaigns if c.id == campaign_id), None)

    if target is None:
        console.print(f"[red]Campaign not found: {campaign_id}[/red]")
        raise typer.Exit(1)

    if effect is not None:
        target.effect_summary = effect
    if end is not None:
        target.period.end = end
    if notes is not None:
        target.notes = notes

    store.save_campaign(target)
    console.print(f"[green]Campaign '{campaign_id}' updated.[/green]")
