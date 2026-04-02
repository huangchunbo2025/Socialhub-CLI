"""Loyalty program analytics functions."""

from rich.console import Console

from ..api.mcp_client import MCPClient, MCPConfig as MCPClientConfig, MCPError
from ..output.export import format_output
from .common import (
    _compute_date_range,
    _mcp_query_timeout,
    _safe_date_filter,
)

console = Console()


def _rich_box_rounded():
    """Return rich ROUNDED box (avoids re-importing at multiple call sites)."""
    from rich import box as rich_box
    return rich_box.ROUNDED


def _get_mcp_points(config, period: str, expiring_days: int = 0, breakdown: bool = False) -> dict:
    """Get points analytics from MCP database.

    Args:
        expiring_days: when > 0, add expiration risk section
        breakdown: when True, add per-operation_type breakdown
    """
    # Validate and compute safe date range
    start_date, _ = _compute_date_range(period)
    date_filter = _safe_date_filter("create_time", start_date)

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
        api_key=config.mcp.api_key,
    )
    database = config.mcp.database

    # Validate expiring_days
    if not isinstance(expiring_days, int) or expiring_days < 0 or expiring_days > 3650:
        expiring_days = 0

    with MCPClient(mcp_config) as client:
        client.initialize()

        # --- Base summary: try dws_points_base_metrics_d first ---
        data = {
            "period": period,
            "total_earned": 0,
            "total_redeemed": 0,
            "active_members": 0,
            "total_transactions": 0,
            "dws_used": False,
        }

        dws_ok = False
        try:
            dws_result = client.query(f"""
                SELECT
                    SUM(earn_points)     AS total_earned,
                    SUM(consume_points)  AS total_redeemed,
                    SUM(earn_cnt)        AS total_transactions
                FROM dws_points_base_metrics_d
                WHERE biz_date >= '{start_date}'
            """, database=database)
            if isinstance(dws_result, list) and dws_result and dws_result[0].get("total_earned") is not None:
                row = dws_result[0]
                data["total_earned"]       = row.get("total_earned") or 0
                data["total_redeemed"]     = row.get("total_redeemed") or 0
                data["total_transactions"] = row.get("total_transactions") or 0
                data["dws_used"] = True
                dws_ok = True
        except Exception:
            pass

        if not dws_ok:
            result = client.query(f"""
                SELECT
                    SUM(CASE WHEN change_type = 'earn'   THEN points ELSE 0 END) AS total_earned,
                    SUM(CASE WHEN change_type = 'redeem' THEN points ELSE 0 END) AS total_redeemed,
                    COUNT(DISTINCT member_id) AS active_members,
                    COUNT(*) AS total_transactions
                FROM dwd_member_points_log
                {date_filter}
            """, database=database)

            if isinstance(result, list) and result:
                row = result[0]
                data["total_earned"]       = row.get("total_earned") or 0
                data["total_redeemed"]     = row.get("total_redeemed") or 0
                data["active_members"]     = row.get("active_members") or 0
                data["total_transactions"] = row.get("total_transactions") or 0

        # --- Expiration risk ---
        if expiring_days > 0:
            exp_result = client.query(f"""
                SELECT
                    SUM(points)              AS expiring_points,
                    COUNT(DISTINCT member_id) AS affected_members
                FROM dwd_member_points_log
                WHERE effective_end_time > NOW()
                  AND effective_end_time <= DATE_ADD(NOW(), INTERVAL {expiring_days} DAY)
                  AND change_type = 'earn'
            """, database=database)

            data["expiring_days"] = expiring_days
            data["expiring_points"] = 0
            data["expiring_affected_members"] = 0
            if isinstance(exp_result, list) and exp_result:
                data["expiring_points"]           = exp_result[0].get("expiring_points") or 0
                data["expiring_affected_members"] = exp_result[0].get("affected_members") or 0

        # --- Breakdown by operation_type ---
        if breakdown:
            # operation_type: 1=purchase 2=promotion 3=return 4=manual+ 5=manual- 6=behavior 8=redeem-gift 9=redeem-coupon 11=expired
            bd_result = client.query(f"""
                SELECT
                    operation_type,
                    SUM(points)              AS total_points,
                    COUNT(DISTINCT member_id) AS members,
                    COUNT(*)                 AS transactions
                FROM dwd_member_points_log
                {date_filter}
                GROUP BY operation_type
                ORDER BY total_points DESC
            """, database=database)

            op_labels = {
                "1": "Purchase earn", "2": "Promotion earn", "3": "Return deduct",
                "4": "Manual add",    "5": "Manual deduct",  "6": "Behavior earn",
                "8": "Redeem gift",   "9": "Redeem coupon",  "11": "Expired deduct",
            }
            breakdown_rows = []
            if isinstance(bd_result, list):
                for r in bd_result:
                    op = str(r.get("operation_type") or "")
                    breakdown_rows.append({
                        "operation_type": op,
                        "label":          op_labels.get(op, f"Type {op}"),
                        "total_points":   r.get("total_points") or 0,
                        "members":        r.get("members") or 0,
                        "transactions":   r.get("transactions") or 0,
                    })
            data["breakdown"] = breakdown_rows

        return data


def _print_points_mcp(data: dict) -> None:
    """Rich output for MCP points analytics."""
    from rich.panel import Panel
    from rich.table import Table
    from rich import box as rich_box

    earned   = int(data.get("total_earned") or 0)
    redeemed = int(data.get("total_redeemed") or 0)
    balance  = earned - redeemed
    redemption_rate = f"{redeemed/earned*100:.1f}%" if earned else "-"

    t = Table(show_header=False, box=rich_box.SIMPLE, padding=(0, 2))
    t.add_column("Metric", style="dim", min_width=22)
    t.add_column("Value", style="bold", justify="right", min_width=14)
    t.add_column("Note", style="dim")

    t.add_row("Total Earned",     f"{earned:,}",        f"Period: {data.get('period')}")
    t.add_row("Total Redeemed",   f"{redeemed:,}",      f"Redemption rate: {redemption_rate}")
    t.add_row("Net Balance",      f"{balance:,}",       "Earned minus redeemed")
    t.add_row("Active Members",   f"{int(data.get('active_members') or 0):,}", "Had point activity")
    t.add_row("Transactions",     f"{int(data.get('total_transactions') or 0):,}", "Total point events")

    # Expiration risk section
    if "expiring_days" in data:
        exp_pts = int(data.get("expiring_points") or 0)
        exp_mem = int(data.get("expiring_affected_members") or 0)
        exp_pct = f"{exp_pts/earned*100:.1f}%" if earned else "-"
        t.add_row("", "", "")
        t.add_row(
            f"[yellow]Expiring (next {data['expiring_days']}d)[/yellow]",
            f"[yellow]{exp_pts:,}[/yellow]",
            f"[yellow]{exp_mem:,} members affected ({exp_pct} of earned)[/yellow]",
        )

    console.print()
    console.print(Panel(t, title="[bold cyan]Points Analytics[/bold cyan]", border_style="cyan"))

    # Breakdown table
    if "breakdown" in data and data["breakdown"]:
        bt = Table(title="Points by Operation Type", box=rich_box.ROUNDED, header_style="bold cyan")
        bt.add_column("Type", style="dim")
        bt.add_column("Label")
        bt.add_column("Points", justify="right", style="bold")
        bt.add_column("Members", justify="right")
        bt.add_column("Transactions", justify="right")

        for r in data["breakdown"]:
            bt.add_row(
                str(r.get("operation_type") or "-"),
                str(r.get("label") or "-"),
                f"{int(r.get('total_points') or 0):,}",
                f"{int(r.get('members') or 0):,}",
                f"{int(r.get('transactions') or 0):,}",
            )
        console.print(bt)


def _get_mcp_points_at_risk(config, expiring_days: int, limit: int = 200) -> list:
    """List members whose earned points expire within N days.

    Cross-table (das_demoen):
      dwd_member_points_log  → earned points + effective_end_time
      dim_customer_info      → customer_name, mobilephone

    Returns one row per member_id, sorted by earliest_expiry ASC then
    expiring_points DESC so the most urgent cases appear first.
    """
    if not isinstance(expiring_days, int) or expiring_days < 1 or expiring_days > 3650:
        raise ValueError(f"expiring_days must be 1–3650, got {expiring_days}")
    safe_limit = max(1, min(int(limit), 1000))
    safe_days  = int(expiring_days)

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
        api_key=config.mcp.api_key,
    )
    database = config.mcp.database

    with MCPClient(mcp_config) as client:
        client.initialize()

        rows = client.query(f"""
            SELECT
                pl.member_id,
                c.customer_name,
                c.mobilephone,
                SUM(pl.points)               AS expiring_points,
                MIN(pl.effective_end_time)   AS earliest_expiry,
                COUNT(*)                     AS expiring_txn_count
            FROM dwd_member_points_log pl
            LEFT JOIN dim_customer_info c
                   ON c.customer_code = pl.member_id
            WHERE pl.change_type = 'earn'
              AND pl.effective_end_time > NOW()
              AND pl.effective_end_time <= DATE_ADD(NOW(), INTERVAL {safe_days} DAY)
            GROUP BY pl.member_id, c.customer_name, c.mobilephone
            HAVING expiring_points > 0
            ORDER BY earliest_expiry ASC, expiring_points DESC
            LIMIT {safe_limit}
        """, database=database)

    return rows if isinstance(rows, list) else []


def _print_points_at_risk(rows: list, expiring_days: int, output: str = None) -> None:
    """Rich display for at-risk points member list."""
    from rich.table import Table
    from rich import box as rich_box
    from rich.panel import Panel

    if not rows:
        console.print(f"[green]No members with points expiring in the next {expiring_days} days[/green]")
        return

    if output:
        format_output(rows, "json", output)
        return

    total_pts    = sum(int(r.get("expiring_points") or 0) for r in rows)
    total_members = len(rows)

    summary = (
        f"[bold]Window:[/bold] next [yellow]{expiring_days}[/yellow] days\n"
        f"[bold]At-risk members:[/bold]  [red]{total_members:,}[/red]\n"
        f"[bold]At-risk points:[/bold]   [red]{total_pts:,}[/red]"
        f"  (~{total_pts / 100:,.0f} CNY liability @ 0.01/pt)"
    )
    console.print(Panel(summary, title="[bold red]Points Expiry At-Risk[/bold red]", border_style="red"))

    t = Table(box=rich_box.ROUNDED, header_style="bold cyan", show_lines=False)
    t.add_column("#",               style="dim",  width=5)
    t.add_column("Member ID",       style="dim",  max_width=18)
    t.add_column("Name",                          max_width=16)
    t.add_column("Phone",           style="dim",  max_width=14)
    t.add_column("Expiring Pts",    justify="right", style="red")
    t.add_column("Earliest Expiry", justify="left",  style="yellow", max_width=12)
    t.add_column("Txns",            justify="right", style="dim")

    for i, r in enumerate(rows, 1):
        phone_raw = str(r.get("mobilephone") or "")
        phone_mask = phone_raw[:3] + "****" + phone_raw[-4:] if len(phone_raw) >= 8 else phone_raw
        t.add_row(
            str(i),
            str(r.get("member_id") or "-"),
            str(r.get("customer_name") or "-"),
            phone_mask,
            f"{int(r.get('expiring_points') or 0):,}",
            str(r.get("earliest_expiry") or "-")[:10],
            str(r.get("expiring_txn_count") or "-"),
        )

    console.print(t)
    console.print(
        f"[dim]{total_members} members | {total_pts:,} pts total | "
        f"Use --output to export for campaign targeting[/dim]"
    )


def _get_mcp_loyalty(config) -> dict:
    """Loyalty program overview: enrollment, tier distribution, points liability.

    Joins (dts_demoen):
      vdm_t_loyalty_program
      vdm_t_member          (by loyalty_program_code)
      vdm_t_points_account  (by card_no = member_code)
    """
    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
        api_key=config.mcp.api_key,
    )
    src_db = "dts_demoen"

    with MCPClient(mcp_config) as client:
        client.initialize()

        # 1. Program list
        programs = client.query(
            "SELECT code, name, status FROM vdm_t_loyalty_program WHERE delete_flag = 0 ORDER BY code",
            database=src_db,
        )

        # 2. Member count + tier distribution per program
        tier_dist = client.query("""
            SELECT
                loyalty_program_code,
                tier_code,
                COUNT(*) AS member_count
            FROM vdm_t_member
            WHERE delete_flag = 0
            GROUP BY loyalty_program_code, tier_code
            ORDER BY loyalty_program_code, member_count DESC
        """, database=src_db)

        # 3. Points liability per program
        liability = client.query("""
            SELECT
                m.loyalty_program_code,
                COUNT(DISTINCT m.card_no)  AS accounts_with_points,
                SUM(pa.available_points)   AS available_points,
                SUM(pa.transit_points)     AS transit_points,
                SUM(pa.accumulative_points) AS accumulative_points,
                SUM(pa.used_points)        AS used_points,
                SUM(pa.expired_points)     AS expired_points
            FROM vdm_t_member m
            JOIN vdm_t_points_account pa
              ON pa.member_code = m.card_no
             AND pa.delete_flag = 0
            WHERE m.delete_flag = 0
            GROUP BY m.loyalty_program_code
        """, database=src_db)

    # Build lookup maps
    tier_map = {}
    if isinstance(tier_dist, list):
        for r in tier_dist:
            prog = str(r.get("loyalty_program_code") or "")
            tier_map.setdefault(prog, []).append({
                "tier_code": r.get("tier_code") or "-",
                "member_count": int(r.get("member_count") or 0),
            })

    liab_map = {}
    if isinstance(liability, list):
        for r in liability:
            prog = str(r.get("loyalty_program_code") or "")
            liab_map[prog] = r

    prog_list = []
    if isinstance(programs, list):
        for p in programs:
            code = str(p.get("code") or "")
            tiers = tier_map.get(code, [])
            total_members = sum(t["member_count"] for t in tiers)
            liab = liab_map.get(code, {})
            prog_list.append({
                "code": code,
                "name": p.get("name") or code,
                "status": p.get("status") or "-",
                "total_members": total_members,
                "tiers": tiers,
                "available_points": int(liab.get("available_points") or 0),
                "transit_points": int(liab.get("transit_points") or 0),
                "accumulative_points": int(liab.get("accumulative_points") or 0),
                "used_points": int(liab.get("used_points") or 0),
                "expired_points": int(liab.get("expired_points") or 0),
                "accounts_with_points": int(liab.get("accounts_with_points") or 0),
            })

    grand_members = sum(p["total_members"] for p in prog_list)
    grand_avail   = sum(p["available_points"] for p in prog_list)
    grand_transit = sum(p["transit_points"] for p in prog_list)
    grand_accum   = sum(p["accumulative_points"] for p in prog_list)

    return {
        "programs": prog_list,
        "totals": {
            "programs": len(prog_list),
            "members": grand_members,
            "available_points": grand_avail,
            "transit_points": grand_transit,
            "accumulative_points": grand_accum,
        },
    }


def _print_loyalty_mcp(data: dict, output: str = None) -> None:
    """Rich display for loyalty program overview."""
    from rich.table import Table
    from rich import box as rich_box
    from rich.panel import Panel

    if output:
        format_output(data, "json", output)
        return

    programs = data.get("programs", [])
    totals   = data.get("totals", {})

    if not programs:
        console.print("[yellow]No loyalty program data found[/yellow]")
        return

    avail_pts   = totals.get("available_points", 0)
    transit_pts = totals.get("transit_points", 0)
    liability_cny = (avail_pts + transit_pts) / 100.0

    summary = (
        f"[bold]Total Programs:[/bold]  {totals.get('programs', 0)}\n"
        f"[bold]Total Members:[/bold]   {totals.get('members', 0):,}\n"
        f"[bold]Available Points:[/bold]  [green]{avail_pts:,}[/green]"
        f"  (~{liability_cny:,.0f} CNY liability @ 0.01/pt)\n"
        f"[bold]In Transit:[/bold]       {transit_pts:,}\n"
        f"[bold]All-time Issued:[/bold]  {totals.get('accumulative_points', 0):,}"
    )
    console.print(Panel(summary, title="[bold]Loyalty Program Overview[/bold]", border_style="yellow"))

    for p in programs:
        status_style = "green" if str(p.get("status")) in ("1", "active", "enabled") else "dim"
        prog_header = (
            f"[bold]{p.get('name')}[/bold]  [dim]{p.get('code')}[/dim]  "
            f"[{status_style}]{p.get('status')}[/{status_style}]\n"
            f"Members: {p.get('total_members', 0):,}   "
            f"Accounts w/ points: {p.get('accounts_with_points', 0):,}"
        )
        console.print(Panel(prog_header, border_style="dim", padding=(0, 2)))

        tiers = p.get("tiers", [])
        if tiers:
            tt = Table(box=rich_box.SIMPLE, header_style="bold dim")
            tt.add_column("Tier",    style="yellow")
            tt.add_column("Members", justify="right")
            tt.add_column("Share",   justify="right")
            total_m = p.get("total_members") or 1
            for tier in tiers:
                cnt = tier.get("member_count", 0)
                tt.add_row(
                    str(tier.get("tier_code") or "-"),
                    f"{cnt:,}",
                    f"{cnt / total_m * 100:.1f}%",
                )
            console.print(tt)

        avail   = p.get("available_points", 0)
        transit = p.get("transit_points", 0)
        used    = p.get("used_points", 0)
        expired = p.get("expired_points", 0)
        accum   = p.get("accumulative_points", 0)
        redemption_rate = round(used / accum * 100, 1) if accum else 0
        console.print(
            f"  [dim]Points — Available: [green]{avail:,}[/green]  "
            f"In-transit: {transit:,}  "
            f"Used: {used:,}  "
            f"Expired: [red]{expired:,}[/red]  "
            f"Redemption rate: {redemption_rate}%[/dim]\n"
        )


def _get_mcp_points_daily_trend(config, period: str) -> list:
    """Query daily earn/redeem trend from dwd_member_points_log."""
    start_date, _ = _compute_date_range(period)
    date_filter = _safe_date_filter("create_time", start_date)

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
        api_key=config.mcp.api_key,
    )
    database = config.mcp.database

    with MCPClient(mcp_config) as client:
        client.initialize()
        rows = client.query(f"""
            SELECT
                DATE(create_time)                                           AS day,
                SUM(CASE WHEN change_type = 'earn'   THEN points ELSE 0 END) AS earned,
                SUM(CASE WHEN change_type = 'redeem' THEN points ELSE 0 END) AS redeemed,
                COUNT(DISTINCT member_id)                                   AS members
            FROM dwd_member_points_log
            {date_filter}
            GROUP BY DATE(create_time)
            ORDER BY day
        """, database=database)

    return rows if isinstance(rows, list) else []


def _print_points_daily_trend(rows: list, period: str) -> None:
    """Bar-style daily earn/redeem trend table."""
    from rich.table import Table
    from rich import box as rich_box

    if not rows:
        console.print("[yellow]No daily points data found[/yellow]")
        return

    max_earned = max((r.get("earned") or 0 for r in rows), default=1) or 1

    tbl = Table(
        title=f"Points Daily Trend  ({period})",
        box=rich_box.SIMPLE, header_style="bold cyan",
    )
    tbl.add_column("Date",     style="dim")
    tbl.add_column("Earned",   justify="right", style="green")
    tbl.add_column("Redeemed", justify="right", style="yellow")
    tbl.add_column("Net",      justify="right")
    tbl.add_column("Members",  justify="right", style="cyan")
    tbl.add_column("Trend",    no_wrap=True)

    for r in rows:
        earned   = int(r.get("earned") or 0)
        redeemed = int(r.get("redeemed") or 0)
        net      = earned - redeemed
        members  = int(r.get("members") or 0)
        bar_len  = int(earned / max_earned * 20) if max_earned else 0
        bar      = "[green]" + "█" * bar_len + "[/green]"
        net_str  = f"[green]+{net:,}[/green]" if net >= 0 else f"[red]{net:,}[/red]"
        tbl.add_row(
            str(r.get("day") or "—"),
            f"{earned:,}",
            f"{redeemed:,}",
            net_str,
            f"{members:,}",
            bar,
        )

    console.print(tbl)
    total_earned   = sum(int(r.get("earned") or 0)   for r in rows)
    total_redeemed = sum(int(r.get("redeemed") or 0) for r in rows)
    console.print(
        f"[dim]Period total — Earned: [green]{total_earned:,}[/green]  "
        f"Redeemed: [yellow]{total_redeemed:,}[/yellow]  "
        f"Net: {'[green]+' if total_earned >= total_redeemed else '[red]'}"
        f"{total_earned - total_redeemed:,}[/{'green' if total_earned >= total_redeemed else 'red'}][/dim]"
    )


def _get_mcp_loyalty_health(config) -> dict:
    """Fetch loyalty program health metrics."""
    from datetime import datetime, timedelta
    today    = datetime.now().date()
    start_30 = (today - timedelta(days=30)).isoformat()

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
        api_key=config.mcp.api_key,
    )
    database = config.mcp.database

    with MCPClient(mcp_config) as client:
        client.initialize()

        # Enrollment + tier distribution (vdm_t_* tables live in dts_demoen)
        tier_rows = client.query("""
            SELECT m.tier_code AS tier_name,
                   COUNT(*) AS members,
                   SUM(COALESCE(pa.points_available, 0)) AS available_pts,
                   SUM(COALESCE(pa.points_in_transit, 0)) AS transit_pts
            FROM vdm_t_member m
            LEFT JOIN vdm_t_points_account pa ON m.member_code = pa.member_code
            GROUP BY m.tier_code
            ORDER BY members DESC
        """, database="dts_demoen")

        # Points liability (total unredeemed value)
        pts_rows = client.query("""
            SELECT
                SUM(points_available)   AS total_available,
                SUM(points_in_transit)  AS total_transit,
                SUM(points_expired)     AS total_expired_30d,
                COUNT(DISTINCT member_code) AS active_holders
            FROM vdm_t_points_account
            WHERE points_available > 0
        """, database="dts_demoen")

        # Redeem rate (last 30d)
        redeem_rows = client.query(f"""
            SELECT
                SUM(points_consume) AS redeemed_30d,
                SUM(points_earn)    AS earned_30d,
                COUNT(DISTINCT member_code) AS redeemers
            FROM vdm_t_points_record
            WHERE create_time >= '{start_30}'
        """, database="dts_demoen")

        # Churn risk — members with no activity last 90d
        churn_rows = client.query("""
            SELECT COUNT(*) AS at_risk
            FROM vdm_t_member
            WHERE last_active_date < DATE_SUB(CURRENT_DATE, INTERVAL 90 DAY)
              AND status = 1
        """, database="dts_demoen")

    tiers   = tier_rows if isinstance(tier_rows, list) else []
    pts     = pts_rows[0] if isinstance(pts_rows, list) and pts_rows else {}
    redeem  = redeem_rows[0] if isinstance(redeem_rows, list) and redeem_rows else {}
    churn   = churn_rows[0] if isinstance(churn_rows, list) and churn_rows else {}

    total_members = sum(int(t.get("members") or 0) for t in tiers)

    return {
        "tiers":         tiers,
        "total_members": total_members,
        "points":        pts,
        "redeem":        redeem,
        "churn":         churn,
        "generated":     datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def _build_loyalty_health_markdown(data: dict) -> str:
    tiers   = data["tiers"]
    total   = data["total_members"]
    pts     = data["points"]
    redeem  = data["redeem"]
    churn   = data["churn"]
    gen     = data["generated"]

    avail   = float(pts.get("total_available") or 0)
    transit = float(pts.get("total_transit") or 0)
    expired = float(pts.get("total_expired_30d") or 0)
    holders = int(pts.get("active_holders") or 0)

    redeemed = float(redeem.get("redeemed_30d") or 0)
    earned   = float(redeem.get("earned_30d") or 0)
    redeem_rate = redeemed / earned * 100 if earned else 0
    at_risk  = int(churn.get("at_risk") or 0)
    churn_pct = at_risk / total * 100 if total else 0

    lines = [
        f"# Loyalty Program Health Review",
        f"",
        f"_Generated: {gen}_",
        f"",
        f"---",
        f"",
        f"## Membership Overview",
        f"",
        f"Total enrolled members: **{total:,}**  |  "
        f"Active point holders: **{holders:,}**",
        f"",
        f"### Tier Distribution",
        f"",
        f"| Tier | Members | Share | Available Pts | In-Transit Pts |",
        f"| --- | --- | --- | --- | --- |",
    ]
    for t in tiers:
        m  = int(t.get("members") or 0)
        sh = m / total * 100 if total else 0
        ap = float(t.get("available_pts") or 0)
        tp = float(t.get("transit_pts") or 0)
        lines.append(f"| {t.get('tier_name','-')} | {m:,} | {sh:.1f}% | {ap:,.0f} | {tp:,.0f} |")

    lines += [
        f"",
        f"## Points Health",
        f"",
        f"| Metric | Value |",
        f"| --- | --- |",
        f"| Total Available (liability) | {avail:,.0f} pts |",
        f"| In-Transit | {transit:,.0f} pts |",
        f"| Expired (last 30d) | {expired:,.0f} pts |",
        f"| Earned (last 30d) | {earned:,.0f} pts |",
        f"| Redeemed (last 30d) | {redeemed:,.0f} pts |",
        f"| Redeem Rate | {redeem_rate:.1f}% |",
        f"",
        f"## Churn Risk",
        f"",
        f"Members inactive 90+ days: **{at_risk:,}** ({churn_pct:.1f}% of enrolled)",
        f"",
        f"---",
        f"",
        f"_Source: SocialHub.AI CLI — Loyalty Health Review_",
    ]
    return "\n".join(lines)
