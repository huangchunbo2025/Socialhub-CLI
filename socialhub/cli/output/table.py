"""Table output formatting using Rich."""

from typing import Any, Optional

import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

console = Console()


def create_table(
    title: Optional[str] = None,
    columns: Optional[list[str]] = None,
    show_header: bool = True,
    show_lines: bool = False,
    box_style: Optional[str] = None,
) -> Table:
    """Create a Rich table with styling."""
    from rich import box

    box_mapping = {
        "simple": box.SIMPLE,
        "rounded": box.ROUNDED,
        "heavy": box.HEAVY,
        "double": box.DOUBLE,
        "minimal": box.MINIMAL,
        None: box.ROUNDED,
    }

    table = Table(
        title=title,
        show_header=show_header,
        show_lines=show_lines,
        box=box_mapping.get(box_style, box.ROUNDED),
        header_style="bold cyan",
        title_style="bold magenta",
    )

    if columns:
        for col in columns:
            table.add_column(col)

    return table


def print_dataframe(
    df: pd.DataFrame,
    title: Optional[str] = None,
    max_rows: int = 50,
    columns: Optional[list[str]] = None,
) -> None:
    """Print pandas DataFrame as a Rich table."""
    if df.empty:
        console.print("[yellow]No data to display[/yellow]")
        return

    # Select columns if specified
    if columns:
        df = df[[c for c in columns if c in df.columns]]

    # Limit rows
    if len(df) > max_rows:
        df = df.head(max_rows)
        console.print(f"[dim]Showing first {max_rows} rows...[/dim]")

    table = create_table(title=title, columns=df.columns.tolist())

    for _, row in df.iterrows():
        table.add_row(*[str(v) if pd.notna(v) else "-" for v in row])

    console.print(table)


def print_dict(
    data: dict[str, Any],
    title: Optional[str] = None,
    key_header: str = "Field",
    value_header: str = "Value",
) -> None:
    """Print dictionary as a two-column table."""
    table = create_table(title=title, columns=[key_header, value_header])

    for key, value in data.items():
        # Format key
        formatted_key = key.replace("_", " ").title()

        # Format value
        if isinstance(value, float):
            formatted_value = f"{value:,.2f}"
        elif isinstance(value, int):
            formatted_value = f"{value:,}"
        elif isinstance(value, list):
            formatted_value = ", ".join(str(v) for v in value)
        elif value is None:
            formatted_value = "-"
        else:
            formatted_value = str(value)

        table.add_row(formatted_key, formatted_value)

    console.print(table)


def print_list(
    items: list[dict[str, Any]],
    title: Optional[str] = None,
    columns: Optional[list[str]] = None,
) -> None:
    """Print list of dictionaries as a table."""
    if not items:
        console.print("[yellow]No data to display[/yellow]")
        return

    # Determine columns from first item if not specified
    if columns is None:
        columns = list(items[0].keys())

    # Create header from column names
    headers = [col.replace("_", " ").title() for col in columns]
    table = create_table(title=title, columns=headers)

    for item in items:
        row = []
        for col in columns:
            value = item.get(col)
            if isinstance(value, float):
                row.append(f"{value:,.2f}")
            elif isinstance(value, int):
                row.append(f"{value:,}")
            elif value is None:
                row.append("-")
            else:
                row.append(str(value))
        table.add_row(*row)

    console.print(table)


def print_overview(data: dict[str, Any], title: str = "Analytics Overview") -> None:
    """Print analytics overview in a formatted panel."""
    # Create metrics display
    lines = []

    metric_formats = {
        "period": ("Period", "{}"),
        "total_customers": ("Total Customers", "{:,}"),
        "new_customers": ("New Customers", "{:,}"),
        "active_customers": ("Active Customers", "{:,}"),
        "total_orders": ("Total Orders", "{:,}"),
        "total_revenue": ("Total Revenue", "CNY {:,.2f}"),
        "average_order_value": ("Avg Order Value", "CNY {:,.2f}"),
        "avg_order_value": ("Avg Order Value", "CNY {:,.2f}"),
        "conversion_rate": ("Conversion Rate", "{:.2f}%"),
        "retention_rate": ("Retention Rate", "{:.2f}%"),
        "repurchase_rate": ("Repurchase Rate", "{:.2f}%"),
    }

    for key, value in data.items():
        if key in metric_formats:
            label, fmt = metric_formats[key]
            try:
                formatted_value = fmt.format(value)
            except (ValueError, TypeError):
                formatted_value = str(value)
            lines.append(f"[bold]{label}:[/bold] {formatted_value}")

    content = "\n".join(lines)
    panel = Panel(content, title=title, border_style="cyan")
    console.print(panel)


def print_retention_table(data: list[dict[str, Any]]) -> None:
    """Print retention analysis table with visual indicators."""
    table = create_table(
        title="Customer Retention Analysis",
        columns=["Period (Days)", "Cohort Size", "Retained", "Retention Rate"],
    )

    for item in data:
        rate = item.get("retention_rate", 0)

        # Color code retention rate
        if rate >= 40:
            rate_style = "green"
        elif rate >= 20:
            rate_style = "yellow"
        else:
            rate_style = "red"

        # Create progress bar
        bar_width = 20
        filled = int(rate / 100 * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)

        table.add_row(
            str(item.get("period_days", "-")),
            f"{item.get('cohort_size', 0):,}",
            f"{item.get('retained_count', 0):,}",
            f"[{rate_style}]{rate:.1f}% {bar}[/{rate_style}]",
        )

    console.print(table)


def print_status_badge(status: str) -> Text:
    """Create a colored status badge."""
    status_colors = {
        "enabled": "green",
        "active": "green",
        "running": "green",
        "success": "green",
        "disabled": "red",
        "inactive": "red",
        "failed": "red",
        "draft": "yellow",
        "pending": "yellow",
        "paused": "yellow",
        "finished": "blue",
        "completed": "blue",
        "expired": "dim",
        "used": "dim",
        "unused": "cyan",
    }

    color = status_colors.get(status.lower(), "white")
    return Text(f"[{status}]", style=color)


def print_success(message: str) -> None:
    """Print success message."""
    console.print(f"[green][OK][/green] {message}")


def print_error(message: str) -> None:
    """Print error message."""
    console.print(f"[red][ERROR][/red] {message}")


def print_warning(message: str) -> None:
    """Print warning message."""
    console.print(f"[yellow][WARN][/yellow] {message}")


def print_info(message: str) -> None:
    """Print info message."""
    console.print(f"[blue][INFO][/blue] {message}")
