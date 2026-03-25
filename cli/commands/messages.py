"""Message management commands."""

import json
import re
from datetime import datetime, timedelta
from typing import Optional

import typer
from rich import box as rich_box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..api.client import APIError, SocialHubClient
from ..api.mcp_client import MCPClient, MCPConfig as MCPClientConfig, MCPError
from ..config import load_config
from ..output.export import format_output
from ..output.table import create_table, print_dict, print_error, print_list, print_success

# vdm_t_message_record.channel_type codes
_CHANNEL_LABELS = {
    1: "国内短信",
    2: "国际短信",
    4: "邮件",
    8: "微信",
    16: "WhatsApp",
    17: "Line",
}

# vdm_t_message_record.status codes
# 1=待提交 2=提交中 3=提交成功 4=提交失败 5=发送成功 6=发送失败
_STATUS_SENT    = (3, 5)   # considered delivered
_STATUS_FAILED  = (4, 6)

# vdm_t_message_record.operate_status codes
# 1=打开 2=点击 3=退信 4=退订


def _mcp_message_stats(config, period: str) -> dict:
    """Query vdm_t_message_record in dts_demoen for delivery + engagement metrics."""
    # Compute start date
    _period_map = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}
    days = _period_map.get(period, 30)
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    if not re.match(r"^\d{4}-\d{2}-\d{2}$", start_date):
        raise ValueError("Invalid date computed")

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    src_db = "dts_demoen"

    with MCPClient(mcp_config) as client:
        client.initialize()

        # Overall delivery summary
        summary = client.query(f"""
            SELECT
                COUNT(*) AS total_sent,
                SUM(CASE WHEN status IN (3, 5) THEN 1 ELSE 0 END) AS delivered,
                SUM(CASE WHEN status IN (4, 6) THEN 1 ELSE 0 END) AS failed,
                SUM(CASE WHEN operate_status = 1  THEN 1 ELSE 0 END) AS opened,
                SUM(CASE WHEN operate_status = 2  THEN 1 ELSE 0 END) AS clicked,
                SUM(CASE WHEN operate_status = 3  THEN 1 ELSE 0 END) AS bounced,
                SUM(CASE WHEN operate_status = 4  THEN 1 ELSE 0 END) AS unsubscribed
            FROM vdm_t_message_record
            WHERE create_time >= '{start_date}'
              AND delete_flag = 0
        """, database=src_db)

        # Breakdown by channel_type
        by_channel = client.query(f"""
            SELECT
                channel_type,
                COUNT(*) AS total_sent,
                SUM(CASE WHEN status IN (3, 5) THEN 1 ELSE 0 END) AS delivered,
                SUM(CASE WHEN status IN (4, 6) THEN 1 ELSE 0 END) AS failed,
                SUM(CASE WHEN operate_status = 1  THEN 1 ELSE 0 END) AS opened,
                SUM(CASE WHEN operate_status = 2  THEN 1 ELSE 0 END) AS clicked
            FROM vdm_t_message_record
            WHERE create_time >= '{start_date}'
              AND delete_flag = 0
            GROUP BY channel_type
            ORDER BY total_sent DESC
        """, database=src_db)

        # Daily trend (last 14 days within period)
        daily = client.query(f"""
            SELECT
                DATE(create_time) AS send_date,
                COUNT(*) AS total_sent,
                SUM(CASE WHEN status IN (3, 5) THEN 1 ELSE 0 END) AS delivered
            FROM vdm_t_message_record
            WHERE create_time >= '{start_date}'
              AND delete_flag = 0
            GROUP BY DATE(create_time)
            ORDER BY send_date DESC
            LIMIT 14
        """, database=src_db)

    s = summary[0] if isinstance(summary, list) and summary else {}
    total = int(s.get("total_sent") or 0)
    delivered = int(s.get("delivered") or 0)
    opened = int(s.get("opened") or 0)
    clicked = int(s.get("clicked") or 0)

    return {
        "period": period,
        "total_sent": total,
        "delivered": delivered,
        "failed": int(s.get("failed") or 0),
        "opened": opened,
        "clicked": clicked,
        "bounced": int(s.get("bounced") or 0),
        "unsubscribed": int(s.get("unsubscribed") or 0),
        "delivery_rate": round(delivered / total * 100, 2) if total else 0,
        "open_rate": round(opened / delivered * 100, 2) if delivered else 0,
        "click_rate": round(clicked / delivered * 100, 2) if delivered else 0,
        "by_channel": by_channel if isinstance(by_channel, list) else [],
        "daily": daily if isinstance(daily, list) else [],
    }


def _print_message_stats_mcp(data: dict) -> None:
    """Rich display for MCP message stats."""
    period = data.get("period", "-")
    total = data.get("total_sent", 0)
    delivered = data.get("delivered", 0)
    opened = data.get("opened", 0)
    clicked = data.get("clicked", 0)

    summary_text = (
        f"[bold]Period:[/bold] {period}\n"
        f"[bold]Total Sent:[/bold]     {total:,}\n"
        f"[bold]Delivered:[/bold]      {delivered:,}  "
        f"([cyan]{data.get('delivery_rate', 0):.1f}%[/cyan])\n"
        f"[bold]Failed:[/bold]         {data.get('failed', 0):,}\n"
        f"[bold]Opened:[/bold]         {opened:,}  "
        f"([green]{data.get('open_rate', 0):.1f}%[/green] of delivered)\n"
        f"[bold]Clicked:[/bold]        {clicked:,}  "
        f"([green]{data.get('click_rate', 0):.1f}%[/green] of delivered)\n"
        f"[bold]Bounced:[/bold]        {data.get('bounced', 0):,}\n"
        f"[bold]Unsubscribed:[/bold]   {data.get('unsubscribed', 0):,}"
    )
    console.print(Panel(summary_text, title="[bold]Message Delivery Stats[/bold]", border_style="blue"))

    # Channel breakdown
    by_channel = data.get("by_channel", [])
    if by_channel:
        ct = Table(title="By Channel", box=rich_box.SIMPLE, header_style="bold")
        ct.add_column("Channel")
        ct.add_column("Sent",      justify="right")
        ct.add_column("Delivered", justify="right", style="cyan")
        ct.add_column("Deliv%",    justify="right")
        ct.add_column("Opened",    justify="right", style="green")
        ct.add_column("Open%",     justify="right")
        ct.add_column("Clicked",   justify="right", style="green")
        ct.add_column("Failed",    justify="right", style="red")
        for r in by_channel:
            ch = _CHANNEL_LABELS.get(r.get("channel_type"), f"Ch{r.get('channel_type', '?')}")
            sent = int(r.get("total_sent") or 0)
            deliv = int(r.get("delivered") or 0)
            fail = int(r.get("failed") or 0)
            opn = int(r.get("opened") or 0)
            clk = int(r.get("clicked") or 0)
            ct.add_row(
                ch,
                f"{sent:,}",
                f"{deliv:,}",
                f"{deliv/sent*100:.1f}%" if sent else "-",
                f"{opn:,}",
                f"{opn/deliv*100:.1f}%" if deliv else "-",
                f"{clk:,}",
                f"{fail:,}",
            )
        console.print(ct)

    # Daily trend
    daily = data.get("daily", [])
    if daily:
        dt = Table(title="Daily Trend (latest 14 days)", box=rich_box.SIMPLE, header_style="bold dim")
        dt.add_column("Date")
        dt.add_column("Sent",      justify="right")
        dt.add_column("Delivered", justify="right", style="cyan")
        dt.add_column("Deliv%",    justify="right")
        for r in daily:
            sent = int(r.get("total_sent") or 0)
            deliv = int(r.get("delivered") or 0)
            dt.add_row(
                str(r.get("send_date") or "-"),
                f"{sent:,}",
                f"{deliv:,}",
                f"{deliv/sent*100:.1f}%" if sent else "-",
            )
        console.print(dt)

app = typer.Typer(help="Message management commands")
console = Console()

# Subcommand for message templates
templates_app = typer.Typer(help="Message template management")
app.add_typer(templates_app, name="templates")


@templates_app.command("list")
def list_message_templates(
    channel: Optional[str] = typer.Option(None, "--channel", "-c", help="Channel filter (sms, email, wechat, app_push)"),
    limit: int = typer.Option(50, "--limit", "-l", help="Number of records"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
) -> None:
    """List message templates."""
    config = load_config()

    if config.mode != "api":
        print_error("Messages require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.list_message_templates(channel=channel, page_size=limit)
            data = result.get("data", {}).get("items", result.get("data", []))
            total = result.get("data", {}).get("total", len(data))
            console.print(f"[dim]Total: {total} templates[/dim]")
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)

    if format == "table" and isinstance(data, list):
        table = create_table(
            title="Message Templates",
            columns=["ID", "Name", "Channel", "Variables", "Status"],
        )

        channel_icons = {
            "sms": "📱",
            "email": "📧",
            "wechat": "💬",
            "app_push": "🔔",
        }

        for item in data:
            enabled = item.get("enabled", False)
            status = "[green]Enabled[/green]" if enabled else "[red]Disabled[/red]"
            channel_val = item.get("channel", "")
            icon = channel_icons.get(channel_val, "")

            variables = item.get("variables", [])
            var_str = ", ".join(variables[:3])
            if len(variables) > 3:
                var_str += f" (+{len(variables) - 3})"

            table.add_row(
                str(item.get("id", "-")),
                str(item.get("name", "-")),
                f"{icon} {channel_val}",
                var_str or "-",
                status,
            )

        console.print(table)
    else:
        format_output(data, format)


@templates_app.command("get")
def get_message_template(
    template_id: str = typer.Argument(..., help="Template ID"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
) -> None:
    """Get message template details."""
    config = load_config()

    if config.mode != "api":
        print_error("Messages require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.get_message_template(template_id)
            data = result.get("data", result)
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)

    if format == "json":
        console.print_json(json.dumps(data, default=str))
    else:
        # Pretty display template
        console.print(Panel(
            f"[bold]Name:[/bold] {data.get('name', '-')}\n"
            f"[bold]Channel:[/bold] {data.get('channel', '-')}\n"
            f"[bold]Status:[/bold] {'Enabled' if data.get('enabled') else 'Disabled'}",
            title=f"Template: {template_id}",
            border_style="cyan",
        ))

        if "content" in data:
            console.print("\n[bold]Content:[/bold]")
            console.print(Panel(data["content"], border_style="dim"))

        if "variables" in data and data["variables"]:
            console.print("\n[bold]Variables:[/bold]")
            for var in data["variables"]:
                console.print(f"  • [cyan]{{{{{var}}}}}[/cyan]")


@app.command("records")
def list_message_records(
    channel: Optional[str] = typer.Option(None, "--channel", "-c", help="Channel filter"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Status filter (success, failed, pending)"),
    limit: int = typer.Option(50, "--limit", "-l", help="Number of records"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
) -> None:
    """List message send records."""
    config = load_config()

    if config.mode != "api":
        print_error("Messages require API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.list_message_records(
                channel=channel,
                status=status,
                page_size=limit,
            )
            data = result.get("data", {}).get("items", result.get("data", []))
            total = result.get("data", {}).get("total", len(data))
            console.print(f"[dim]Total: {total} records[/dim]")
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)

    if format == "table" and isinstance(data, list):
        table = create_table(
            title="Message Records",
            columns=["ID", "Template", "Channel", "Recipient", "Status", "Sent At"],
        )

        status_colors = {
            "success": "green",
            "delivered": "green",
            "failed": "red",
            "pending": "yellow",
            "sending": "cyan",
        }

        for item in data:
            status_val = item.get("status", "unknown")
            color = status_colors.get(status_val, "white")

            table.add_row(
                str(item.get("id", "-")),
                str(item.get("template_name", item.get("template_id", "-"))),
                str(item.get("channel", "-")),
                str(item.get("recipient", "-")),
                f"[{color}]{status_val}[/{color}]",
                str(item.get("sent_at", "-"))[:16] if item.get("sent_at") else "-",
            )

        console.print(table)
    else:
        format_output(data, format)


@app.command("stats")
def get_message_stats(
    period: str = typer.Option("30d", "--period", "-p", help="Time period (7d/30d/90d/365d)"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to file"),
) -> None:
    """Get message delivery statistics.

    In MCP mode, queries vdm_t_message_record (dts_demoen) for channel
    breakdown, delivery rate, open rate, and click rate.

    Examples:
        sh messages stats --period=30d
        sh messages stats --period=7d --output=msg_stats.json
    """
    config = load_config()

    if config.mode == "mcp":
        try:
            data = _mcp_message_stats(config, period)
        except MCPError as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)
        except Exception as e:
            print_error(f"Error: {e}")
            raise typer.Exit(1)

        if output or format == "json":
            format_output(data, "json", output)
        else:
            _print_message_stats_mcp(data)
        return

    if config.mode != "api":
        print_error("Messages stats requires API or MCP mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.get_message_stats(period=period)
            data = result.get("data", result)
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)

    if format == "json":
        console.print_json(json.dumps(data, default=str))
    else:
        # Pretty display stats
        console.print(f"\n[bold]Message Statistics ({period})[/bold]\n")

        # Overall stats
        if "total" in data:
            print_dict({
                "Total Sent": data.get("total", 0),
                "Success": data.get("success", 0),
                "Failed": data.get("failed", 0),
                "Success Rate": f"{data.get('success_rate', 0):.1f}%",
            }, title="Overview")

        # By channel
        if "by_channel" in data and isinstance(data["by_channel"], dict):
            console.print()
            print_dict(data["by_channel"], title="Messages by Channel")

        # By day
        if "by_day" in data and isinstance(data["by_day"], dict):
            console.print()
            print_dict(data["by_day"], title="Messages by Day")


# =============================================================================
# messages health — Deliverability diagnostics
# =============================================================================

def _mcp_message_health(config, period: str) -> dict:
    """Query vdm_t_message_record for failure/bounce/unsubscribe rates by channel."""
    _period_map = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}
    days = _period_map.get(period, 30)
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", start_date):
        raise ValueError("Invalid date computed")

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )

    with MCPClient(mcp_config) as client:
        client.initialize()

        # Overall summary
        summary = client.query(f"""
            SELECT
                COUNT(*)                                                        AS total,
                SUM(CASE WHEN status IN (3, 5) THEN 1 ELSE 0 END)             AS delivered,
                SUM(CASE WHEN status IN (4, 6) THEN 1 ELSE 0 END)             AS failed,
                SUM(CASE WHEN operate_status = 3 THEN 1 ELSE 0 END)           AS bounced,
                SUM(CASE WHEN operate_status = 4 THEN 1 ELSE 0 END)           AS unsubscribed
            FROM vdm_t_message_record
            WHERE create_time >= '{start_date}'
        """, database="dts_demoen")

        totals = summary[0] if isinstance(summary, list) and summary else {}

        # By channel
        by_channel = client.query(f"""
            SELECT
                channel_type,
                COUNT(*)                                                        AS total,
                SUM(CASE WHEN status IN (3, 5) THEN 1 ELSE 0 END)             AS delivered,
                SUM(CASE WHEN status IN (4, 6) THEN 1 ELSE 0 END)             AS failed,
                SUM(CASE WHEN operate_status = 3 THEN 1 ELSE 0 END)           AS bounced,
                SUM(CASE WHEN operate_status = 4 THEN 1 ELSE 0 END)           AS unsubscribed
            FROM vdm_t_message_record
            WHERE create_time >= '{start_date}'
            GROUP BY channel_type
            ORDER BY total DESC
        """, database="dts_demoen")

    return {
        "period": period,
        "summary": totals,
        "by_channel": by_channel if isinstance(by_channel, list) else [],
    }


def _print_message_health(data: dict, output: str = None) -> None:
    """Rich display for message health diagnostics."""
    from ..output.export import format_output

    if output:
        format_output(data, "json", output)
        return

    period = data["period"]
    s = data["summary"]

    def _pct(part, total):
        try:
            return f"{int(part or 0) / int(total) * 100:.1f}%"
        except (ZeroDivisionError, TypeError):
            return "—"

    total = int(s.get("total") or 0)
    delivered = int(s.get("delivered") or 0)
    failed = int(s.get("failed") or 0)
    bounced = int(s.get("bounced") or 0)
    unsubscribed = int(s.get("unsubscribed") or 0)

    fail_color = "red" if total and failed / total > 0.05 else "green"
    bounce_color = "red" if total and bounced / total > 0.02 else "green"
    unsub_color = "red" if total and unsubscribed / total > 0.01 else "green"

    console.print(Panel(
        f"Total:          [bold]{total:,}[/bold]\n"
        f"Delivered:      [green]{delivered:,}[/green]  ({_pct(delivered, total)})\n"
        f"Failed:         [{fail_color}]{failed:,}[/{fail_color}]  ({_pct(failed, total)})\n"
        f"Bounced:        [{bounce_color}]{bounced:,}[/{bounce_color}]  ({_pct(bounced, total)})\n"
        f"Unsubscribed:   [{unsub_color}]{unsubscribed:,}[/{unsub_color}]  ({_pct(unsubscribed, total)})",
        title=f"[bold cyan]Message Health  ({period})[/bold cyan]",
        border_style="cyan",
    ))

    rows = data["by_channel"]
    if not rows:
        return

    tbl = Table(
        title="By Channel",
        box=rich_box.SIMPLE_HEAVY, header_style="bold cyan",
    )
    tbl.add_column("Channel",     style="bold")
    tbl.add_column("Total",       justify="right")
    tbl.add_column("Delivered",   justify="right", style="green")
    tbl.add_column("Deliv. Rate", justify="right")
    tbl.add_column("Failed",      justify="right")
    tbl.add_column("Fail Rate",   justify="right")
    tbl.add_column("Bounced",     justify="right")
    tbl.add_column("Unsub.",      justify="right")

    _CHANNEL_LABELS_LOCAL = {
        1: "国内短信", 2: "国际短信", 4: "邮件",
        8: "微信", 16: "WhatsApp", 17: "Line",
    }

    for r in rows:
        ch = _CHANNEL_LABELS_LOCAL.get(r.get("channel_type"), f"ch{r.get('channel_type')}")
        tot = int(r.get("total") or 0)
        dlv = int(r.get("delivered") or 0)
        fld = int(r.get("failed") or 0)
        bnc = int(r.get("bounced") or 0)
        usb = int(r.get("unsubscribed") or 0)
        fail_rate = _pct(fld, tot)
        fr_color = "red" if tot and fld / tot > 0.05 else "white"
        tbl.add_row(
            ch,
            f"{tot:,}",
            f"{dlv:,}",
            _pct(dlv, tot),
            f"[{fr_color}]{fld:,}[/{fr_color}]",
            f"[{fr_color}]{fail_rate}[/{fr_color}]",
            f"{bnc:,}",
            f"{usb:,}",
        )

    console.print(tbl)
    console.print("[dim]Thresholds: Fail >5% ⚠  Bounce >2% ⚠  Unsub >1% ⚠[/dim]")


def _mcp_message_trend(config, period: str) -> dict:
    """Daily send/fail/bounce trend for spike detection (mean+2sigma)."""
    _period_map = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}
    days = _period_map.get(period, 30)
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )

    # Try DWS first, fallback to raw record table
    with MCPClient(mcp_config) as client:
        client.initialize()
        dws_ok = False
        daily_rows = []
        try:
            rows = client.query(f"""
                SELECT biz_date AS day,
                       send_cnt    AS total,
                       success_cnt AS delivered,
                       fail_cnt    AS failed
                FROM dws_message_base_metrics_d
                WHERE biz_date >= '{start_date}'
                ORDER BY day
            """, database="das_demoen")
            if isinstance(rows, list) and rows:
                daily_rows = rows
                dws_ok = True
        except Exception:
            pass

        if not dws_ok:
            rows = client.query(f"""
                SELECT DATE(create_time) AS day,
                       COUNT(*)                                              AS total,
                       SUM(CASE WHEN status IN (3,5) THEN 1 ELSE 0 END)    AS delivered,
                       SUM(CASE WHEN status IN (4,6) THEN 1 ELSE 0 END)    AS failed
                FROM vdm_t_message_record
                WHERE create_time >= '{start_date}'
                GROUP BY DATE(create_time)
                ORDER BY day
            """, database="dts_demoen")
            if isinstance(rows, list):
                daily_rows = rows

    # Mean+2sigma anomaly on fail_cnt
    def _f(r):
        return float(r.get("failed") or 0)

    if len(daily_rows) < 3:
        return {"rows": daily_rows, "anomalies": [], "dws_used": dws_ok}

    vals = [_f(r) for r in daily_rows[:-1]]  # exclude today from baseline
    mean = sum(vals) / len(vals)
    std  = (sum((x - mean) ** 2 for x in vals) / len(vals)) ** 0.5
    upper = mean + 2 * std

    flagged = []
    for r in daily_rows:
        v      = _f(r)
        status = "spike" if v > upper else "normal"
        flagged.append({**r, "fail_spike": status, "mean_fail": mean, "upper_2sigma": upper})

    return {
        "rows":     flagged,
        "anomalies": [r for r in flagged if r["fail_spike"] == "spike"],
        "dws_used": dws_ok,
        "mean_fail": mean,
        "upper_2sigma": upper,
    }


def _print_message_trend(data: dict) -> None:
    rows     = data.get("rows", [])
    anomalies = data.get("anomalies", [])
    mean_f   = data.get("mean_fail", 0)
    upper    = data.get("upper_2sigma", 0)
    n_spike  = len(anomalies)

    sc = "green" if n_spike == 0 else "red"
    console.print(Panel(
        f"Daily fail baseline: mean={mean_f:.0f}  2-sigma upper={upper:.0f}\n"
        f"Spike days: [{sc}]{n_spike}[/{sc}]  "
        f"({'[green]No spikes[/green]' if n_spike == 0 else '[red]Review needed[/red]'})\n"
        f"Source: {'dws_message_base_metrics_d' if data.get('dws_used') else 'vdm_t_message_record (fallback)'}",
        title="[bold cyan]Message Delivery Trend[/bold cyan]", border_style="cyan"
    ))

    if not rows:
        return

    tbl = Table(box=rich_box.SIMPLE_HEAVY, header_style="bold cyan",
                title=f"Daily Trend ({len(rows)} days)")
    tbl.add_column("Date",      style="dim")
    tbl.add_column("Sent",      justify="right")
    tbl.add_column("Delivered", justify="right", style="green")
    tbl.add_column("Failed",    justify="right")
    tbl.add_column("Fail%",     justify="right")
    tbl.add_column("Status",    justify="center")

    for r in rows:
        total = int(r.get("total") or 0)
        dlv   = int(r.get("delivered") or 0)
        fld   = int(r.get("failed") or 0)
        pct   = fld / total * 100 if total else 0
        st    = r.get("fail_spike", "normal")
        sym   = "[red]SPIKE[/red]" if st == "spike" else "[green]ok[/green]"
        fld_s = f"[red]{fld:,}[/red]" if st == "spike" else f"{fld:,}"
        tbl.add_row(str(r.get("day","-")), f"{total:,}", f"{dlv:,}",
                    fld_s, f"{pct:.1f}%", sym)

    console.print(tbl)

    if anomalies:
        days_str = ", ".join(str(a.get("day","-")) for a in anomalies)
        console.print(f"\n[red]Failure spikes on: {days_str}[/red]")
        console.print("[dim]Check: gateway issues, invalid recipient lists, bulk campaign triggers[/dim]")


@app.command("health")
def message_health(
    period: str = typer.Option("30d", "--period", "-p", help="Time period (7d/30d/90d/365d)"),
    trend: bool = typer.Option(False, "--trend", "-t",
                               help="Show daily delivery trend with spike detection"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to JSON file"),
) -> None:
    """Message deliverability health check: fail/bounce/unsubscribe rates by channel (MCP).

    Queries vdm_t_message_record (dts_demoen) and flags channels exceeding
    recommended thresholds (fail >5%, bounce >2%, unsubscribe >1%).

    Use --trend for daily time-series with mean+2sigma spike detection.

    Examples:
        sh messages health
        sh messages health --period=7d
        sh messages health --trend
        sh messages health --trend --output=trend.json
    """
    config = load_config()

    if config.mode != "mcp":
        print_error("messages health requires MCP mode")
        raise typer.Exit(1)

    try:
        if trend:
            trend_data = _mcp_message_trend(config, period)
            if output:
                format_output(trend_data, "json", output)
                console.print(f"[green]Exported to {output}[/green]")
            else:
                _print_message_trend(trend_data)
            return
        data = _mcp_message_health(config, period)
    except MCPError as e:
        print_error(f"MCP Error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Error: {e}")
        raise typer.Exit(1)

    _print_message_health(data, output)


# =============================================================================
# messages template-stats — Per-template open/click performance (P1)
# =============================================================================

def _mcp_template_stats(config, period: str, limit: int) -> list:
    """Rank message templates by open and click rate.

    Tries ads_das_v_message_analysis_d (ADS) first; falls back to
    vdm_t_message_record (source) on exception.
    """
    _period_map = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}
    days = _period_map.get(period, 30)
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    if not isinstance(limit, int) or limit < 1 or limit > 200:
        limit = 20

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    with MCPClient(mcp_config) as client:
        client.initialize()

        # Try ADS pre-aggregated view first
        try:
            rows = client.query(f"""
                SELECT
                    template_id,
                    channel_type,
                    SUM(send_cnt)    AS total_sent,
                    SUM(success_cnt) AS delivered,
                    SUM(open_cnt)    AS opened,
                    SUM(click_cnt)   AS clicked,
                    SUM(fail_cnt)    AS failed
                FROM ads_das_v_message_analysis_d
                WHERE biz_date >= '{start_date}'
                  AND template_id IS NOT NULL
                GROUP BY template_id, channel_type
                ORDER BY total_sent DESC
                LIMIT {limit}
            """, database="das_demoen")
            if isinstance(rows, list) and rows:
                return rows
        except Exception:
            pass

        # Fallback: vdm_t_message_record (source)
        rows = client.query(f"""
            SELECT
                template_id,
                channel_type,
                COUNT(*)                                                          AS total_sent,
                SUM(CASE WHEN status IN (3,5)        THEN 1 ELSE 0 END)          AS delivered,
                SUM(CASE WHEN operate_status = 1     THEN 1 ELSE 0 END)          AS opened,
                SUM(CASE WHEN operate_status = 2     THEN 1 ELSE 0 END)          AS clicked,
                SUM(CASE WHEN operate_status = 4     THEN 1 ELSE 0 END)          AS unsubscribed
            FROM vdm_t_message_record
            WHERE create_time >= '{start_date}'
              AND template_id IS NOT NULL
            GROUP BY template_id, channel_type
            ORDER BY total_sent DESC
            LIMIT {limit}
        """, database="dts_demoen")
    return rows if isinstance(rows, list) else []


def _print_template_stats(rows: list, period: str) -> None:
    if not rows:
        console.print("[yellow]No template data found (template_id may be NULL)[/yellow]")
        return

    _CHANNEL = {1:"国内短信",2:"国际短信",4:"邮件",8:"微信",16:"WhatsApp",17:"Line"}

    def _r(p, t):
        try: return f"{int(p)/int(t)*100:.1f}%"
        except: return "—"

    tbl = Table(title=f"Template Performance  ({period})",
                box=rich_box.SIMPLE_HEAVY, header_style="bold cyan")
    tbl.add_column("Template ID", style="dim", max_width=20)
    tbl.add_column("Channel",     style="bold")
    tbl.add_column("Sent",        justify="right")
    tbl.add_column("Delivered",   justify="right", style="green")
    tbl.add_column("Open Rate",   justify="right")
    tbl.add_column("Click Rate",  justify="right")
    tbl.add_column("Unsub Rate",  justify="right")

    for r in rows:
        ch   = _CHANNEL.get(r.get("channel_type"), f"ch{r.get('channel_type')}")
        sent = int(r.get("total_sent") or 0)
        dlv  = int(r.get("delivered") or 0)
        opn  = int(r.get("opened") or 0)
        clk  = int(r.get("clicked") or 0)
        usb  = int(r.get("unsubscribed") or 0)
        cr   = _r(clk, sent)
        ucol = "red" if sent and usb/sent > 0.01 else "white"
        tbl.add_row(
            str(r.get("template_id") or "—"), ch,
            f"{sent:,}", f"{dlv:,}",
            _r(opn, dlv), f"[cyan]{cr}[/cyan]",
            f"[{ucol}]{_r(usb, sent)}[/{ucol}]",
        )
    console.print(tbl)


@app.command("template-stats")
def message_template_stats(
    period: str = typer.Option("30d", "--period", "-p", help="Time period (7d/30d/90d/365d)"),
    limit: int  = typer.Option(20,    "--limit",  "-n", help="Max templates (1-200)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export JSON"),
) -> None:
    """Per-template open/click/unsubscribe rates ranked by volume (MCP).

    Examples:
        sh messages template-stats
        sh messages template-stats --period=7d --limit=10
    """
    config = load_config()
    if config.mode != "mcp":
        print_error("messages template-stats requires MCP mode")
        raise typer.Exit(1)
    try:
        rows = _mcp_template_stats(config, period, limit)
    except (MCPError, Exception) as e:
        print_error(f"Error: {e}"); raise typer.Exit(1)

    if output:
        format_output(rows, "json", output)
    else:
        _print_template_stats(rows, period)


# =============================================================================
# messages attribution — Message-to-purchase conversion (P2)
# =============================================================================

def _mcp_message_attribution(config, period: str, window_days: int) -> dict:
    """Estimate purchase conversion within N days of receiving a message."""
    _period_map = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}
    days = _period_map.get(period, 30)
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    if not isinstance(window_days, int) or window_days < 1 or window_days > 30:
        window_days = 7

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    database = config.mcp.database

    with MCPClient(mcp_config) as client:
        client.initialize()

        # Distinct recipients per channel
        recipients = client.query(f"""
            SELECT
                channel_type,
                COUNT(DISTINCT customer_code) AS recipients
            FROM vdm_t_message_record
            WHERE create_time >= '{start_date}'
              AND status IN (3, 5)
              AND customer_code IS NOT NULL
            GROUP BY channel_type
        """, database="dts_demoen")

        # Converters: ordered within window_days of receiving message
        converters = client.query(f"""
            SELECT
                m.channel_type,
                COUNT(DISTINCT m.customer_code) AS converters,
                SUM(o.total_amount) / 100.0     AS attributed_revenue_cny
            FROM vdm_t_message_record m
            JOIN dwd_v_order o
              ON o.customer_code = m.customer_code
             AND o.order_date >= DATE(m.create_time)
             AND DATEDIFF(o.order_date, DATE(m.create_time)) <= {window_days}
             AND o.order_date >= '{start_date}'
            WHERE m.create_time >= '{start_date}'
              AND m.status IN (3, 5)
              AND m.customer_code IS NOT NULL
            GROUP BY m.channel_type
        """, database=database)

    # Merge by channel_type
    rec_map = {}
    if isinstance(recipients, list):
        for r in recipients:
            rec_map[r.get("channel_type")] = int(r.get("recipients") or 0)

    _CHANNEL = {1:"国内短信",2:"国际短信",4:"邮件",8:"微信",16:"WhatsApp",17:"Line"}
    by_channel = []
    if isinstance(converters, list):
        for r in converters:
            ct = r.get("channel_type")
            rec = rec_map.get(ct, 0)
            conv = int(r.get("converters") or 0)
            rev = float(r.get("attributed_revenue_cny") or 0)
            by_channel.append({
                "channel": _CHANNEL.get(ct, f"ch{ct}"),
                "recipients": rec,
                "converters": conv,
                "conversion_rate": f"{conv/rec*100:.1f}%" if rec else "—",
                "attributed_revenue_cny": rev,
                "revenue_per_recipient": f"¥{rev/rec:.2f}" if rec else "—",
            })

    total_rec  = sum(rec_map.values())
    total_conv = sum(int(r.get("converters") or 0) for r in (converters or []))
    total_rev  = sum(float(r.get("attributed_revenue_cny") or 0) for r in (converters or []))

    return {
        "period": period,
        "window_days": window_days,
        "total_recipients": total_rec,
        "total_converters": total_conv,
        "overall_conversion_rate": f"{total_conv/total_rec*100:.1f}%" if total_rec else "—",
        "total_attributed_revenue_cny": total_rev,
        "by_channel": by_channel,
    }


def _print_message_attribution(data: dict) -> None:
    console.print(Panel(
        f"Recipients:          [bold]{data['total_recipients']:,}[/bold]\n"
        f"Converted buyers:    [green]{data['total_converters']:,}[/green]  "
        f"({data['overall_conversion_rate']})\n"
        f"Attributed revenue:  [green]¥{data['total_attributed_revenue_cny']:,.0f}[/green]\n"
        f"Attribution window:  {data['window_days']} days after message delivery",
        title=f"[bold cyan]Message Attribution  ({data['period']})[/bold cyan]",
        border_style="cyan",
    ))

    rows = data["by_channel"]
    if not rows:
        return
    tbl = Table(title="By Channel", box=rich_box.SIMPLE_HEAVY, header_style="bold cyan")
    tbl.add_column("Channel",       style="bold")
    tbl.add_column("Recipients",    justify="right")
    tbl.add_column("Converters",    justify="right", style="green")
    tbl.add_column("Conv. Rate",    justify="right")
    tbl.add_column("Revenue (¥)",   justify="right", style="green")
    tbl.add_column("Rev/Recipient", justify="right")
    for r in sorted(rows, key=lambda x: x["converters"], reverse=True):
        tbl.add_row(
            r["channel"],
            f"{r['recipients']:,}",
            f"{r['converters']:,}",
            r["conversion_rate"],
            f"{r['attributed_revenue_cny']:,.0f}",
            r["revenue_per_recipient"],
        )
    console.print(tbl)
    console.print("[dim]Note: last-touch attribution — buyer ordered within window after message delivery.[/dim]")


@app.command("attribution")
def message_attribution(
    period: str      = typer.Option("30d", "--period", "-p", help="Time period (7d/30d/90d/365d)"),
    window: int      = typer.Option(7,     "--window", "-w", help="Attribution window in days (1-30)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export JSON"),
) -> None:
    """Message-to-purchase attribution: buyers who ordered within N days of delivery (MCP).

    Uses last-touch model: joins vdm_t_message_record (delivered) with
    dwd_v_order on customer_code within the attribution window.

    Examples:
        sh messages attribution
        sh messages attribution --window=14
        sh messages attribution --period=90d --output=attr.json
    """
    config = load_config()
    if config.mode != "mcp":
        print_error("messages attribution requires MCP mode")
        raise typer.Exit(1)
    try:
        data = _mcp_message_attribution(config, period, window)
    except (MCPError, Exception) as e:
        print_error(f"Error: {e}"); raise typer.Exit(1)

    if output:
        format_output(data, "json", output)
    else:
        _print_message_attribution(data)
