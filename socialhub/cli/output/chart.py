"""ASCII chart output for terminal visualization."""

from typing import Any, Optional

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()


def create_bar_chart(
    data: dict[str, float],
    title: Optional[str] = None,
    max_width: int = 40,
    show_values: bool = True,
    color: str = "cyan",
) -> None:
    """Create a horizontal bar chart."""
    if not data:
        console.print("[yellow]No data to display[/yellow]")
        return

    max_value = max(data.values()) if data.values() else 1
    max_label_len = max(len(str(k)) for k in data.keys())

    lines = []
    for label, value in data.items():
        # Calculate bar width
        bar_width = int((value / max_value) * max_width) if max_value > 0 else 0
        bar = "█" * bar_width

        # Format value
        if isinstance(value, float):
            value_str = f"{value:,.2f}"
        else:
            value_str = f"{value:,}"

        # Create line
        padded_label = str(label).ljust(max_label_len)
        if show_values:
            line = f"{padded_label} │ [{color}]{bar}[/{color}] {value_str}"
        else:
            line = f"{padded_label} │ [{color}]{bar}[/{color}]"

        lines.append(line)

    content = "\n".join(lines)

    if title:
        panel = Panel(content, title=title, border_style=color)
        console.print(panel)
    else:
        console.print(content)


def create_percentage_bar(
    value: float,
    width: int = 30,
    filled_char: str = "█",
    empty_char: str = "░",
) -> str:
    """Create a percentage progress bar."""
    value = max(0, min(100, value))  # Clamp to 0-100
    filled = int(value / 100 * width)
    return filled_char * filled + empty_char * (width - filled)


def create_sparkline(
    values: list[float],
    width: Optional[int] = None,
) -> str:
    """Create a simple sparkline from values."""
    if not values:
        return ""

    blocks = " ▁▂▃▄▅▆▇█"

    # Normalize values
    min_val = min(values)
    max_val = max(values)
    range_val = max_val - min_val if max_val != min_val else 1

    # Sample values if width is specified
    if width and len(values) > width:
        step = len(values) / width
        sampled = [values[int(i * step)] for i in range(width)]
        values = sampled

    # Create sparkline
    line = ""
    for v in values:
        idx = int((v - min_val) / range_val * (len(blocks) - 1))
        line += blocks[idx]

    return line


def create_trend_indicator(current: float, previous: float) -> str:
    """Create a trend indicator (up/down arrow with percentage)."""
    if previous == 0:
        if current > 0:
            return "[green]↑ New[/green]"
        return "[dim]- No change[/dim]"

    change = ((current - previous) / previous) * 100

    if change > 0:
        return f"[green]↑ {change:.1f}%[/green]"
    elif change < 0:
        return f"[red]↓ {abs(change):.1f}%[/red]"
    else:
        return "[dim]→ 0%[/dim]"


def print_funnel_chart(
    stages: list[tuple[str, int]],
    title: str = "Conversion Funnel",
) -> None:
    """Print a funnel chart for conversion analysis."""
    if not stages:
        console.print("[yellow]No data to display[/yellow]")
        return

    max_value = stages[0][1] if stages else 1
    max_label_len = max(len(s[0]) for s in stages)
    max_width = 50

    lines = []
    prev_value = None

    for stage_name, value in stages:
        # Calculate bar width
        bar_width = int((value / max_value) * max_width) if max_value > 0 else 0

        # Center the bar
        padding = (max_width - bar_width) // 2
        bar = " " * padding + "█" * bar_width + " " * padding

        # Calculate conversion rate from previous stage
        if prev_value is not None and prev_value > 0:
            conv_rate = f"({value / prev_value * 100:.1f}%)"
        else:
            conv_rate = "(100%)"

        # Format line
        padded_label = stage_name.ljust(max_label_len)
        lines.append(f"{padded_label} │ [cyan]{bar}[/cyan] {value:,} {conv_rate}")

        prev_value = value

    content = "\n".join(lines)
    panel = Panel(content, title=title, border_style="cyan")
    console.print(panel)


def print_comparison_chart(
    data: list[dict[str, Any]],
    metric_key: str,
    label_key: str,
    title: Optional[str] = None,
) -> None:
    """Print a comparison bar chart from list of dicts."""
    chart_data = {item[label_key]: item[metric_key] for item in data if label_key in item and metric_key in item}
    create_bar_chart(chart_data, title=title)


def print_time_series(
    dates: list[str],
    values: list[float],
    title: str = "Trend",
) -> None:
    """Print a simple time series visualization."""
    if not dates or not values:
        console.print("[yellow]No data to display[/yellow]")
        return

    # Create sparkline
    sparkline = create_sparkline(values)

    # Show summary stats
    lines = [
        f"[bold]Period:[/bold] {dates[0]} - {dates[-1]}",
        f"[bold]Trend:[/bold] {sparkline}",
        f"[bold]Min:[/bold] {min(values):,.2f}  [bold]Max:[/bold] {max(values):,.2f}  [bold]Avg:[/bold] {sum(values)/len(values):,.2f}",
    ]

    content = "\n".join(lines)
    panel = Panel(content, title=title, border_style="cyan")
    console.print(panel)
