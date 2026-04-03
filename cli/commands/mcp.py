"""MCP (Model Context Protocol) commands for analytics database."""

import json

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from ..api.mcp_client import MCPClient, MCPConfig, MCPError
from ..config import load_config

_MAX_SQL_LEN = 10_000

app = typer.Typer(help="MCP analytics database commands")
console = Console()


def _print_mcp_unavailable(err: MCPError) -> None:
    """Print a degraded-mode hint when the MCP server is unreachable."""
    console.print(f"[red]MCP error: {err}[/red]")
    msg = str(err).lower()
    if "sse connection lost" in msg or "timed out" in msg or "connection" in msg or "configure" in msg:
        console.print(
            "[yellow]Hint: MCP server may be unavailable. Check:[/yellow]\n"
            "  • [dim]sh config get mcp.sse_url[/dim]  — SSE endpoint configured?\n"
            "  • [dim]MCP_TENANT_ID[/dim] env var set?\n"
            "  • Network / VPN access to the MCP server\n"
            "  • [dim]sh mcp connect[/dim] to test connectivity"
        )


def _build_mcp_config(tenant: str | None = None) -> MCPConfig:
    app_config = load_config()
    return MCPConfig(
        sse_url=app_config.mcp.sse_url,
        post_url=app_config.mcp.post_url,
        tenant_id=tenant or app_config.mcp.tenant_id,
    )


@app.command("connect")
def mcp_connect(
    tenant: str | None = typer.Option(None, "--tenant", "-t", help="Tenant ID (defaults to config)"),
) -> None:
    """Connect to MCP analytics database and show info."""
    config = _build_mcp_config(tenant)

    console.print("\n[cyan]Connecting to MCP...[/cyan]")
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
    tenant: str | None = typer.Option(None, "--tenant", "-t", help="Tenant ID (defaults to config)"),
    database: str | None = typer.Option(None, "--database", "-d", help="Database name"),
    format: str = typer.Option("table", "--format", "-f", help="Output: table, json, csv"),
    output: str | None = typer.Option(None, "--output", "-o", help="Output file"),
    timeout: int = typer.Option(60, "--timeout", help="Query timeout in seconds"),
) -> None:
    """Execute SQL query via MCP."""
    config = _build_mcp_config(tenant)

    if len(sql) > _MAX_SQL_LEN:
        console.print(f"[red]SQL too long (max {_MAX_SQL_LEN:,} chars).[/red]")
        raise typer.Exit(1)

    console.print("\n[cyan]Query:[/cyan]")
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
            _print_mcp_unavailable(e)
            raise typer.Exit(1)


@app.command("tables")
def mcp_tables(
    tenant: str | None = typer.Option(None, "--tenant", "-t", help="Tenant ID (defaults to config)"),
    database: str | None = typer.Option(None, "--database", "-d", help="Database name"),
) -> None:
    """List database tables."""
    config = _build_mcp_config(tenant)

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
            _print_mcp_unavailable(e)


@app.command("schema")
def mcp_schema(
    table_name: str = typer.Argument(..., help="Table name"),
    tenant: str | None = typer.Option(None, "--tenant", "-t", help="Tenant ID (defaults to config)"),
    database: str | None = typer.Option(None, "--database", "-d", help="Database name"),
) -> None:
    """Show table schema."""
    config = _build_mcp_config(tenant)

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
            _print_mcp_unavailable(e)


@app.command("databases")
def mcp_databases(
    tenant: str | None = typer.Option(None, "--tenant", "-t", help="Tenant ID (defaults to config)"),
) -> None:
    """List available databases."""
    config = _build_mcp_config(tenant)

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
            _print_mcp_unavailable(e)


@app.command("stats")
def mcp_stats(
    tenant: str | None = typer.Option(None, "--tenant", "-t", help="Tenant ID (defaults to config)"),
) -> None:
    """Show database statistics."""
    config = _build_mcp_config(tenant)

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
            _print_mcp_unavailable(e)


@app.command("sql")
def mcp_sql(
    tenant: str | None = typer.Option(None, "--tenant", "-t", help="Tenant ID (defaults to config)"),
) -> None:
    """Interactive SQL session."""
    config = _build_mcp_config(tenant)

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

                if len(sql) > _MAX_SQL_LEN:
                    console.print(f"[red]SQL too long (max {_MAX_SQL_LEN:,} chars).[/red]")
                    continue

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
                _print_mcp_unavailable(e)
            except KeyboardInterrupt:
                console.print("\n[dim]Use 'exit' to quit[/dim]")
            except EOFError:
                break

        console.print("[green]Session ended[/green]")
