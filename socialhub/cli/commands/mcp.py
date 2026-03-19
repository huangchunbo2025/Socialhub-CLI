"""MCP (Model Context Protocol) commands for analytics database."""

import json
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax

from ..api.mcp_client import MCPClient, MCPConfig, MCPError

app = typer.Typer(help="MCP analytics database commands")
console = Console()


@app.command("connect")
def mcp_connect(
    tenant: str = typer.Option("demoen", "--tenant", "-t", help="Tenant ID"),
) -> None:
    """Connect to MCP analytics database and show info."""
    config = MCPConfig(tenant_id=tenant)

    console.print(f"\n[cyan]Connecting to MCP...[/cyan]")
    console.print(f"  SSE: {config.sse_url}")
    console.print(f"  Tenant: {config.tenant_id}\n")

    with MCPClient(config) as client:
        console.print("[dim]Initializing...[/dim]")
        init_result = client.initialize()

        if "error" in init_result:
            console.print(f"[red]Init failed: {init_result['error']}[/red]")
            return

        if "result" in init_result:
            server_info = init_result["result"].get("serverInfo", {})
            console.print(f"[green]Connected to {server_info.get('name', 'MCP')} v{server_info.get('version', '?')}[/green]")

        # List tools
        console.print("\n[dim]Fetching tools...[/dim]")
        tools = client.list_tools()

        if tools:
            table = Table(title="Available Tools", show_header=True)
            table.add_column("Name", style="cyan")
            table.add_column("Description", style="white")

            for tool in tools:
                table.add_row(
                    tool.get("name", ""),
                    tool.get("description", "")[:70],
                )
            console.print(table)
        else:
            console.print("[yellow]No tools found or tools/list not supported[/yellow]")

        console.print("\n[green]MCP connection OK[/green]")


@app.command("query")
def mcp_query(
    sql: str = typer.Argument(..., help="SQL query to execute"),
    tenant: str = typer.Option("demoen", "--tenant", "-t", help="Tenant ID"),
    database: Optional[str] = typer.Option(None, "--database", "-d", help="Database name"),
    format: str = typer.Option("table", "--format", "-f", help="Output: table, json, csv"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file"),
    timeout: int = typer.Option(60, "--timeout", help="Query timeout in seconds"),
) -> None:
    """Execute SQL query via MCP."""
    config = MCPConfig(tenant_id=tenant)

    console.print(f"\n[cyan]Query:[/cyan]")
    console.print(Syntax(sql, "sql"))

    with MCPClient(config) as client:
        client.initialize()

        try:
            console.print("\n[dim]Executing...[/dim]")
            result = client.query(sql, timeout=timeout, database=database)

            if isinstance(result, list) and len(result) > 0:
                if format == "json":
                    output_text = json.dumps(result, indent=2, ensure_ascii=False)
                    if output:
                        with open(output, "w", encoding="utf-8") as f:
                            f.write(output_text)
                        console.print(f"\n[green]Saved to: {output}[/green]")
                    else:
                        console.print(Syntax(output_text, "json"))

                elif format == "csv":
                    import csv
                    import io

                    if isinstance(result[0], dict):
                        headers = list(result[0].keys())
                        if output:
                            with open(output, "w", encoding="utf-8", newline="") as f:
                                writer = csv.DictWriter(f, fieldnames=headers)
                                writer.writeheader()
                                writer.writerows(result)
                            console.print(f"\n[green]Saved to: {output}[/green]")
                        else:
                            buffer = io.StringIO()
                            writer = csv.DictWriter(buffer, fieldnames=headers)
                            writer.writeheader()
                            writer.writerows(result)
                            console.print(buffer.getvalue())

                else:  # table
                    if isinstance(result[0], dict):
                        table = Table(show_header=True, title=f"Results ({len(result)} rows)")
                        headers = list(result[0].keys())
                        for h in headers:
                            table.add_column(h)

                        for row in result[:100]:
                            table.add_row(*[str(row.get(h, ""))[:50] for h in headers])

                        console.print(table)
                        if len(result) > 100:
                            console.print(f"[dim]Showing 100 of {len(result)} rows[/dim]")

                        if output:
                            with open(output, "w", encoding="utf-8") as f:
                                json.dump(result, f, indent=2, ensure_ascii=False)
                            console.print(f"\n[green]Full data saved to: {output}[/green]")
                    else:
                        console.print(result)

            elif isinstance(result, dict):
                console.print(Syntax(json.dumps(result, indent=2, ensure_ascii=False), "json"))

            else:
                console.print(result if result else "[yellow]No results[/yellow]")

        except MCPError as e:
            console.print(f"[red]Query failed: {e}[/red]")
            raise typer.Exit(1)


@app.command("tables")
def mcp_tables(
    tenant: str = typer.Option("demoen", "--tenant", "-t", help="Tenant ID"),
    database: Optional[str] = typer.Option(None, "--database", "-d", help="Database name"),
) -> None:
    """List database tables."""
    config = MCPConfig(tenant_id=tenant)

    with MCPClient(config) as client:
        client.initialize()

        try:
            console.print("[dim]Fetching tables...[/dim]")
            result = client.list_tables(database=database)

            if isinstance(result, list):
                table = Table(title="Database Tables", show_header=True)
                table.add_column("Table Name", style="cyan")

                for item in result:
                    if isinstance(item, dict):
                        table.add_row(item.get("table_name", item.get("name", str(item))))
                    else:
                        table.add_row(str(item))

                console.print(table)
            elif isinstance(result, dict):
                console.print(Syntax(json.dumps(result, indent=2, ensure_ascii=False), "json"))
            else:
                console.print(result if result else "[yellow]No tables found[/yellow]")

        except MCPError as e:
            console.print(f"[red]Failed: {e}[/red]")


@app.command("schema")
def mcp_schema(
    table_name: str = typer.Argument(..., help="Table name"),
    tenant: str = typer.Option("demoen", "--tenant", "-t", help="Tenant ID"),
    database: Optional[str] = typer.Option(None, "--database", "-d", help="Database name"),
) -> None:
    """Show table schema."""
    config = MCPConfig(tenant_id=tenant)

    with MCPClient(config) as client:
        client.initialize()

        try:
            console.print(f"[dim]Fetching schema for {table_name}...[/dim]")
            result = client.get_table_schema(table_name, database=database)

            if isinstance(result, list):
                table = Table(title=f"Schema: {table_name}", show_header=True)
                table.add_column("Column", style="cyan")
                table.add_column("Type", style="yellow")
                table.add_column("Nullable", style="dim")

                for row in result:
                    table.add_row(
                        row.get("column_name", row.get("name", "")),
                        row.get("data_type", row.get("type", "")),
                        row.get("is_nullable", row.get("nullable", "")),
                    )
                console.print(table)
            elif isinstance(result, dict):
                console.print(Syntax(json.dumps(result, indent=2, ensure_ascii=False), "json"))
            else:
                console.print(f"[yellow]Table not found: {table_name}[/yellow]")

        except MCPError as e:
            console.print(f"[red]Failed: {e}[/red]")


@app.command("databases")
def mcp_databases(
    tenant: str = typer.Option("demoen", "--tenant", "-t", help="Tenant ID"),
) -> None:
    """List available databases."""
    config = MCPConfig(tenant_id=tenant)

    with MCPClient(config) as client:
        client.initialize()

        try:
            console.print("[dim]Fetching databases...[/dim]")
            result = client.list_databases()

            if isinstance(result, list):
                console.print("\n[cyan]Available Databases:[/cyan]")
                for db in result:
                    if isinstance(db, dict):
                        console.print(f"  - {db.get('name', db.get('database', str(db)))}")
                    else:
                        console.print(f"  - {db}")
            elif isinstance(result, dict):
                console.print(Syntax(json.dumps(result, indent=2, ensure_ascii=False), "json"))
            else:
                console.print(result if result else "[yellow]No databases found[/yellow]")

        except MCPError as e:
            console.print(f"[red]Failed: {e}[/red]")


@app.command("stats")
def mcp_stats(
    tenant: str = typer.Option("demoen", "--tenant", "-t", help="Tenant ID"),
) -> None:
    """Show database statistics."""
    config = MCPConfig(tenant_id=tenant)

    with MCPClient(config) as client:
        client.initialize()

        try:
            console.print("[dim]Fetching stats...[/dim]")
            result = client.get_database_stats()

            if result:
                console.print(Panel(
                    Syntax(json.dumps(result, indent=2, ensure_ascii=False), "json"),
                    title="[cyan]Database Statistics[/cyan]",
                ))
            else:
                console.print("[yellow]No stats available[/yellow]")

        except MCPError as e:
            console.print(f"[red]Failed: {e}[/red]")


@app.command("sql")
def mcp_sql(
    tenant: str = typer.Option("demoen", "--tenant", "-t", help="Tenant ID"),
) -> None:
    """Interactive SQL session."""
    config = MCPConfig(tenant_id=tenant)

    console.print(Panel(
        "[cyan]MCP SQL Session[/cyan]\n\n"
        "Enter SQL queries, press Enter to execute\n"
        "Type [bold]exit[/bold] or [bold]quit[/bold] to exit\n"
        "Type [bold]tables[/bold] to list tables",
        title="Interactive Mode",
    ))

    with MCPClient(config) as client:
        client.initialize()

        while True:
            try:
                sql = console.input("\n[cyan]SQL>[/cyan] ").strip()

                if not sql:
                    continue

                if sql.lower() in ("exit", "quit", "q"):
                    break

                if sql.lower() == "tables":
                    sql = "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"

                result = client.query(sql, timeout=60)

                if isinstance(result, list) and len(result) > 0 and isinstance(result[0], dict):
                    table = Table(show_header=True)
                    headers = list(result[0].keys())
                    for h in headers:
                        table.add_column(h)

                    for row in result[:50]:
                        table.add_row(*[str(row.get(h, ""))[:40] for h in headers])

                    console.print(table)
                    if len(result) > 50:
                        console.print(f"[dim]({len(result)} total rows)[/dim]")
                else:
                    console.print(result if result else "[yellow]No results[/yellow]")

            except MCPError as e:
                console.print(f"[red]Error: {e}[/red]")
            except KeyboardInterrupt:
                console.print("\n[dim]Use 'exit' to quit[/dim]")
            except EOFError:
                break

        console.print("[green]Session ended[/green]")
