"""Customer management commands."""

import json
import re
from typing import Optional

import typer
from rich import box as rich_box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..api.client import APIError, SocialHubClient
from ..api.mcp_client import MCPClient, MCPConfig as MCPClientConfig, MCPError
from ..config import load_config
from ..local.reader import read_customers_csv
from ..output.export import export_data, format_output, print_export_success
from ..output.table import print_dataframe, print_dict, print_error, print_list


# ---------------------------------------------------------------------------
# MCP helpers — Customer 360 Profile
# ---------------------------------------------------------------------------

def _sanitize_id(value: str, max_len: int = 50) -> str:
    """Allow only alphanumeric, dash, underscore."""
    return re.sub(r"[^a-zA-Z0-9_\-]", "", str(value))[:max_len]


def _sanitize_phone(value: str) -> str:
    """Allow digits and leading + only."""
    return re.sub(r"[^\d+]", "", str(value))[:20]


def _mcp_customer_profile(config, consumer_code: str = None, phone: str = None) -> dict:
    """Fetch Customer 360 profile across dts_demoen + das_demoen.

    Lookup priority: consumer_code > phone.
    Tables joined:
      dts_demoen: vdm_t_consumer → vdm_t_member → vdm_t_points_account
      dts_demoen: vdm_t_order (last 5)
      das_demoen: dwd_coupon_instance (active coupons)
    """
    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
    )
    src_db = "dts_demoen"
    das_db = config.mcp.database  # das_demoen

    with MCPClient(mcp_config) as client:
        client.initialize()

        # ── Step 1: resolve consumer_code from phone if needed ──────────────
        if not consumer_code and phone:
            safe_phone = _sanitize_phone(phone)
            rows = client.query(f"""
                SELECT code AS consumer_code
                FROM vdm_t_consumer
                WHERE mobilephone = '{safe_phone}'
                  AND delete_flag = 0
                LIMIT 1
            """, database=src_db)
            if isinstance(rows, list) and rows:
                consumer_code = rows[0].get("consumer_code")
            if not consumer_code:
                return {}

        safe_code = _sanitize_id(consumer_code)
        if not safe_code:
            return {}

        # ── Step 2: base info + membership + points ──────────────────────────
        profile_rows = client.query(f"""
            SELECT
                c.code            AS consumer_code,
                c.name,
                c.mobilephone,
                c.gender,
                c.source_code     AS register_channel,
                c.create_time     AS register_time,
                c.first_order_time,
                c.last_order_time,
                m.card_no,
                m.tier_code,
                m.loyalty_program_code,
                m.create_time     AS member_since,
                m.status          AS member_status,
                pa.available_points,
                pa.accumulative_points,
                pa.transit_points,
                pa.expired_points,
                pa.used_points
            FROM vdm_t_consumer c
            LEFT JOIN vdm_t_member m
                   ON m.consumer_code = c.code
                  AND m.delete_flag = 0
            LEFT JOIN vdm_t_points_account pa
                   ON pa.member_code = m.card_no
                  AND pa.delete_flag = 0
            WHERE c.code = '{safe_code}'
              AND c.delete_flag = 0
            LIMIT 1
        """, database=src_db)

        # ── Step 3: last 5 orders ────────────────────────────────────────────
        order_rows = client.query(f"""
            SELECT
                code         AS order_code,
                order_date,
                cost_amount / 100.0  AS amount_cny,
                direction,
                store_name,
                source_name  AS channel
            FROM vdm_t_order
            WHERE customer_code = '{safe_code}'
              AND delete_flag = 0
            ORDER BY order_date DESC
            LIMIT 5
        """, database=src_db)

        # ── Step 4: active coupons (das_demoen) ──────────────────────────────
        coupon_rows = client.query(f"""
            SELECT
                coupon_code,
                coupon_rule_code,
                status,
                par_value / 100.0 AS face_value_cny,
                end_time
            FROM dwd_coupon_instance
            WHERE customer_code = '{safe_code}'
              AND status IN ('issued', '1')
            ORDER BY end_time ASC
            LIMIT 10
        """, database=das_db)

    profile = profile_rows[0] if isinstance(profile_rows, list) and profile_rows else {}
    profile["recent_orders"]  = order_rows if isinstance(order_rows, list) else []
    profile["active_coupons"] = coupon_rows if isinstance(coupon_rows, list) else []
    return profile


def _print_customer_profile(data: dict) -> None:
    """Rich display for Customer 360 profile."""
    if not data:
        console.print("[yellow]Customer not found[/yellow]")
        return

    _gender = {"M": "男", "F": "女", "0": "未知", "1": "男", "2": "女"}
    _direction = {0: "正单", 1: "退单", 2: "换货单"}
    _mem_status = {"1": "正常", "0": "停用", "active": "正常", "inactive": "停用"}

    # ── header ───────────────────────────────────────────────────────────────
    phone_raw = str(data.get("mobilephone") or "")
    phone_mask = phone_raw[:3] + "****" + phone_raw[-4:] if len(phone_raw) >= 8 else phone_raw
    gender_label = _gender.get(str(data.get("gender", "")), str(data.get("gender", "-")))

    header = (
        f"[bold cyan]{data.get('name') or '(unnamed)'}[/bold cyan]  "
        f"[dim]{data.get('consumer_code', '-')}[/dim]\n"
        f"Phone: {phone_mask}   Gender: {gender_label}   "
        f"Channel: {data.get('register_channel') or '-'}\n"
        f"Registered: {str(data.get('register_time') or '-')[:10]}   "
        f"First Order: {str(data.get('first_order_time') or '-')[:10]}   "
        f"Last Order: {str(data.get('last_order_time') or '-')[:10]}"
    )
    console.print(Panel(header, title="Customer 360 Profile", border_style="cyan"))

    # ── membership ───────────────────────────────────────────────────────────
    card_no = data.get("card_no")
    if card_no:
        mem_lines = [
            f"[bold]Card No:[/bold]      {card_no}",
            f"[bold]Tier:[/bold]         [yellow]{data.get('tier_code') or '-'}[/yellow]",
            f"[bold]Program:[/bold]      {data.get('loyalty_program_code') or '-'}",
            f"[bold]Member Since:[/bold] {str(data.get('member_since') or '-')[:10]}",
            f"[bold]Status:[/bold]       {_mem_status.get(str(data.get('member_status', '')), str(data.get('member_status', '-')))}",
        ]
        avail = int(data.get("available_points") or 0)
        accum = int(data.get("accumulative_points") or 0)
        transit = int(data.get("transit_points") or 0)
        expired = int(data.get("expired_points") or 0)
        used = int(data.get("used_points") or 0)
        mem_lines += [
            "",
            f"[bold]Available Points:[/bold]    [green]{avail:,}[/green]",
            f"[bold]Cumulative Earned:[/bold]   {accum:,}",
            f"[bold]In Transit:[/bold]          {transit:,}",
            f"[bold]Used:[/bold]                {used:,}",
            f"[bold]Expired:[/bold]             [red]{expired:,}[/red]",
        ]
        console.print(Panel("\n".join(mem_lines), title="Membership & Points", border_style="yellow"))
    else:
        console.print("[dim]No membership record[/dim]")

    # ── recent orders ─────────────────────────────────────────────────────────
    orders = data.get("recent_orders", [])
    if orders:
        ot = Table(title="Recent Orders (last 5)", box=rich_box.SIMPLE, header_style="bold dim")
        ot.add_column("Order Code",  style="dim", max_width=20)
        ot.add_column("Date",        max_width=12)
        ot.add_column("Amount (CNY)", justify="right", style="green")
        ot.add_column("Type",        max_width=8)
        ot.add_column("Store/Channel", max_width=20)
        for o in orders:
            d = o.get("direction")
            dtype = _direction.get(d, str(d or "-"))
            dstyle = "red" if d == 1 else ("yellow" if d == 2 else "green")
            ot.add_row(
                str(o.get("order_code") or "-"),
                str(o.get("order_date") or "-")[:10],
                f"{float(o.get('amount_cny') or 0):,.2f}",
                f"[{dstyle}]{dtype}[/{dstyle}]",
                str(o.get("store_name") or o.get("channel") or "-"),
            )
        console.print(ot)
    else:
        console.print("[dim]No order records[/dim]")

    # ── active coupons ───────────────────────────────────────────────────────
    coupons = data.get("active_coupons", [])
    if coupons:
        ct = Table(title="Active Coupons", box=rich_box.SIMPLE, header_style="bold dim")
        ct.add_column("Coupon Code",  style="dim", max_width=20)
        ct.add_column("Rule",         max_width=16)
        ct.add_column("Face Value",   justify="right", style="green")
        ct.add_column("Expires",      max_width=12)
        for c in coupons:
            ct.add_row(
                str(c.get("coupon_code") or "-"),
                str(c.get("coupon_rule_code") or "-"),
                f"¥{float(c.get('face_value_cny') or 0):.2f}",
                str(c.get("end_time") or "-")[:10],
            )
        console.print(ct)
    else:
        console.print("[dim]No active coupons[/dim]")

app = typer.Typer(help="Customer management commands")
console = Console()


@app.command("search")
def search_customers(
    phone: Optional[str] = typer.Option(None, "--phone", "-p", help="Phone number"),
    email: Optional[str] = typer.Option(None, "--email", "-e", help="Email address"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Customer name"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
) -> None:
    """Search customers by phone, email, or name."""
    if not any([phone, email, name]):
        print_error("At least one search criteria is required (--phone, --email, or --name)")
        raise typer.Exit(1)

    config = load_config()

    if config.mode == "api":
        try:
            with SocialHubClient() as client:
                result = client.search_customers(phone=phone, email=email, name=name)
                data = result.get("data", result)
        except APIError as e:
            print_error(f"API Error: {e.message}")
            raise typer.Exit(1)
    else:
        # Local mode
        try:
            df = read_customers_csv("customers.csv", config.local.data_dir)

            # Apply filters
            if phone:
                df = df[df["phone"].astype(str).str.contains(phone, na=False)]
            if email:
                df = df[df["email"].astype(str).str.contains(email, case=False, na=False)]
            if name:
                df = df[df["name"].astype(str).str.contains(name, case=False, na=False)]

            data = df.to_dict(orient="records")
        except Exception as e:
            print_error(f"Local data error: {e}")
            raise typer.Exit(1)

    if isinstance(data, list):
        console.print(f"[dim]Found {len(data)} customer(s)[/dim]")
        format_output(data, format)
    else:
        format_output(data, format)


@app.command("get")
def get_customer(
    customer_id: str = typer.Argument(..., help="Customer ID"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
) -> None:
    """Get customer details by ID."""
    config = load_config()

    if config.mode == "api":
        try:
            with SocialHubClient() as client:
                result = client.get_customer(customer_id)
                data = result.get("data", result)
        except APIError as e:
            print_error(f"API Error: {e.message}")
            raise typer.Exit(1)
    else:
        # Local mode
        try:
            df = read_customers_csv("customers.csv", config.local.data_dir)
            # Case-insensitive ID lookup
            customer = df[df["id"].astype(str).str.upper() == str(customer_id).upper()]

            if customer.empty:
                print_error(f"Customer not found: {customer_id}")
                raise typer.Exit(1)

            data = customer.iloc[0].to_dict()
        except Exception as e:
            print_error(f"Local data error: {e}")
            raise typer.Exit(1)

    format_output(data, format)


@app.command("portrait")
def get_customer_portrait(
    customer_id: str = typer.Argument(..., help="Customer ID"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
) -> None:
    """Get customer 360 portrait/profile."""
    config = load_config()

    if config.mode != "api":
        print_error("Customer portrait requires API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            result = client.get_customer_portrait(customer_id)
            data = result.get("data", result)
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)

    if format == "json":
        console.print_json(json.dumps(data, default=str))
    else:
        # Pretty print portrait
        console.print(Panel(f"Customer Portrait: {customer_id}", border_style="cyan"))

        # Basic info
        if "basic" in data:
            print_dict(data["basic"], title="Basic Information")

        # Tags
        if "tags" in data and data["tags"]:
            console.print("\n[bold]Tags:[/bold]")
            tags = ", ".join(f"[cyan]{t}[/cyan]" for t in data["tags"])
            console.print(f"  {tags}")

        # Purchase behavior
        if "purchase" in data:
            print_dict(data["purchase"], title="Purchase Behavior")

        # Recent orders
        if "recent_orders" in data:
            print_list(data["recent_orders"][:5], title="Recent Orders")


@app.command("profile")
def customer_profile(
    code: Optional[str] = typer.Option(None, "--code", "-c", help="Consumer code (01xxxxxxx)"),
    phone: Optional[str] = typer.Option(None, "--phone", "-p", help="Phone number (lookup by phone)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export raw data to JSON"),
) -> None:
    """Customer 360 profile — cross-table view (MCP mode).

    Joins vdm_t_consumer → vdm_t_member → vdm_t_points_account (dts_demoen)
    plus last 5 orders and active coupons (das_demoen).

    Examples:
        sh customers profile --code 01000000001
        sh customers profile --phone 13800138000
        sh customers profile --code 01000000001 --output profile.json
    """
    if not code and not phone:
        print_error("Provide --code or --phone")
        raise typer.Exit(1)

    config = load_config()

    if config.mode != "mcp":
        print_error("customers profile requires MCP mode")
        raise typer.Exit(1)

    try:
        data = _mcp_customer_profile(config, consumer_code=code, phone=phone)
    except MCPError as e:
        print_error(f"MCP Error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Error: {e}")
        raise typer.Exit(1)

    if not data:
        print_error("Customer not found")
        raise typer.Exit(1)

    if output:
        format_output(data, "json", output)
    else:
        _print_customer_profile(data)


@app.command("list")
def list_customers(
    customer_type: Optional[str] = typer.Option(None, "--type", "-t", help="Customer type (member, registered, visitor)"),
    limit: int = typer.Option(50, "--limit", "-l", help="Number of records to return"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to file"),
) -> None:
    """List customers."""
    config = load_config()

    if config.mode == "api":
        try:
            with SocialHubClient() as client:
                result = client.list_customers(
                    customer_type=customer_type,
                    page_size=limit,
                )
                data = result.get("data", {}).get("items", result.get("data", []))
                total = result.get("data", {}).get("total", len(data))
                console.print(f"[dim]Total: {total} customers[/dim]")
        except APIError as e:
            print_error(f"API Error: {e.message}")
            raise typer.Exit(1)
    else:
        # Local mode
        try:
            df = read_customers_csv("customers.csv", config.local.data_dir)

            if customer_type:
                df = df[df["customer_type"] == customer_type]

            console.print(f"[dim]Total: {len(df)} customers[/dim]")
            df = df.head(limit)
            data = df.to_dict(orient="records")
        except Exception as e:
            print_error(f"Local data error: {e}")
            raise typer.Exit(1)

    if output:
        path = export_data(data, output)
        print_export_success(path)
    else:
        format_output(data, format)


@app.command("export")
def export_customers(
    customer_type: Optional[str] = typer.Option(None, "--type", "-t", help="Customer type filter"),
    output: str = typer.Option("customers_export.csv", "--output", "-o", help="Output file path"),
) -> None:
    """Export customers to file."""
    config = load_config()

    if config.mode == "api":
        try:
            with SocialHubClient() as client:
                # Paginate through all customers
                all_customers = []
                page = 1
                page_size = 100

                while True:
                    result = client.list_customers(
                        customer_type=customer_type,
                        page=page,
                        page_size=page_size,
                    )
                    items = result.get("data", {}).get("items", [])
                    all_customers.extend(items)

                    if len(items) < page_size:
                        break
                    page += 1

                    # Safety limit
                    if page > 100:
                        console.print("[yellow]Warning: Export limited to 10,000 records[/yellow]")
                        break

                data = all_customers
        except APIError as e:
            print_error(f"API Error: {e.message}")
            raise typer.Exit(1)
    else:
        # Local mode
        try:
            df = read_customers_csv("customers.csv", config.local.data_dir)

            if customer_type:
                df = df[df["customer_type"] == customer_type]

            data = df.to_dict(orient="records")
        except Exception as e:
            print_error(f"Local data error: {e}")
            raise typer.Exit(1)

    path = export_data(data, output)
    print_export_success(path)
    console.print(f"[green]Exported {len(data)} customers[/green]")
