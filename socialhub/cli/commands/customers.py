"""Customer management commands."""

import json
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from ..api.client import APIError, SocialHubClient
from ..config import load_config
from ..local.reader import read_customers_csv
from ..output.export import export_data, format_output, print_export_success
from ..output.table import print_dataframe, print_dict, print_error, print_list

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
