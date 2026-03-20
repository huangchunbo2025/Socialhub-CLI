"""Chart output for terminal and image visualization."""

import os
from pathlib import Path
from typing import Any, Optional

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()

# Check if matplotlib is available
try:
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    HAS_MATPLOTLIB = True

    # Set Chinese font support
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
except ImportError:
    HAS_MATPLOTLIB = False


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
        bar = "#" * bar_width

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
    filled_char: str = "#",
    empty_char: str = "-",
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

    blocks = " ._-=+*#@"

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
        bar = " " * padding + "#" * bar_width + " " * padding

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


# ============ Image Chart Generation ============

def save_bar_chart(
    data: dict[str, float],
    output_path: str,
    title: str = "Bar Chart",
    xlabel: str = "",
    ylabel: str = "",
    color: str = "#00C9A7",
    horizontal: bool = False,
) -> Optional[str]:
    """Generate and save a bar chart as image."""
    if not HAS_MATPLOTLIB:
        console.print("[yellow]matplotlib not installed. Run: pip install matplotlib[/yellow]")
        return None

    fig, ax = plt.subplots(figsize=(10, 6))

    labels = list(data.keys())
    values = list(data.values())

    if horizontal:
        bars = ax.barh(labels, values, color=color)
        ax.set_xlabel(ylabel or "Value")
        ax.set_ylabel(xlabel or "Category")
    else:
        bars = ax.bar(labels, values, color=color)
        ax.set_xlabel(xlabel or "Category")
        ax.set_ylabel(ylabel or "Value")
        plt.xticks(rotation=45, ha='right')

    ax.set_title(title, fontsize=14, fontweight='bold')

    # Add value labels
    for bar, val in zip(bars, values):
        if horizontal:
            ax.text(bar.get_width(), bar.get_y() + bar.get_height()/2,
                   f'{val:,.0f}', va='center', ha='left', fontsize=9)
        else:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                   f'{val:,.0f}', va='bottom', ha='center', fontsize=9)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()

    console.print(f"[green]Chart saved: {output_path}[/green]")
    return output_path


def save_pie_chart(
    data: dict[str, float],
    output_path: str,
    title: str = "Pie Chart",
    colors: Optional[list[str]] = None,
) -> Optional[str]:
    """Generate and save a pie chart as image."""
    if not HAS_MATPLOTLIB:
        console.print("[yellow]matplotlib not installed. Run: pip install matplotlib[/yellow]")
        return None

    fig, ax = plt.subplots(figsize=(10, 8))

    labels = list(data.keys())
    values = list(data.values())

    if colors is None:
        colors = ['#00C9A7', '#4ADE80', '#A3E635', '#FBBF24', '#F87171', '#A78BFA', '#60A5FA', '#F472B6']

    # Create pie chart
    wedges, texts, autotexts = ax.pie(
        values,
        labels=labels,
        autopct='%1.1f%%',
        colors=colors[:len(labels)],
        startangle=90,
        explode=[0.02] * len(labels),
    )

    ax.set_title(title, fontsize=14, fontweight='bold')

    # Add legend
    ax.legend(wedges, [f'{l}: {v:,.0f}' for l, v in zip(labels, values)],
              title="Categories", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()

    console.print(f"[green]Chart saved: {output_path}[/green]")
    return output_path


def save_line_chart(
    data: dict[str, list[float]],
    x_labels: list[str],
    output_path: str,
    title: str = "Line Chart",
    xlabel: str = "",
    ylabel: str = "",
) -> Optional[str]:
    """Generate and save a line chart as image."""
    if not HAS_MATPLOTLIB:
        console.print("[yellow]matplotlib not installed. Run: pip install matplotlib[/yellow]")
        return None

    fig, ax = plt.subplots(figsize=(12, 6))

    colors = ['#00C9A7', '#4ADE80', '#A3E635', '#FBBF24', '#F87171', '#A78BFA']

    for i, (label, values) in enumerate(data.items()):
        ax.plot(x_labels, values, marker='o', label=label, color=colors[i % len(colors)], linewidth=2)

    ax.set_xlabel(xlabel or "Period")
    ax.set_ylabel(ylabel or "Value")
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()

    console.print(f"[green]Chart saved: {output_path}[/green]")
    return output_path


def save_funnel_chart(
    stages: list[tuple[str, int]],
    output_path: str,
    title: str = "Conversion Funnel",
) -> Optional[str]:
    """Generate and save a funnel chart as image."""
    if not HAS_MATPLOTLIB:
        console.print("[yellow]matplotlib not installed. Run: pip install matplotlib[/yellow]")
        return None

    fig, ax = plt.subplots(figsize=(10, 8))

    labels = [s[0] for s in stages]
    values = [s[1] for s in stages]
    max_val = values[0] if values else 1

    colors = ['#00C9A7', '#4ADE80', '#A3E635', '#FBBF24', '#F87171']

    y_positions = range(len(stages))

    for i, (label, value) in enumerate(stages):
        width = (value / max_val) * 0.8
        left = (1 - width) / 2

        # Draw bar
        ax.barh(i, width, left=left, height=0.6, color=colors[i % len(colors)], alpha=0.8)

        # Add label and value
        conv_rate = f"({value/stages[i-1][1]*100:.1f}%)" if i > 0 else "(100%)"
        ax.text(0.5, i, f"{label}\n{value:,} {conv_rate}", ha='center', va='center', fontsize=11, fontweight='bold')

    ax.set_xlim(0, 1)
    ax.set_ylim(-0.5, len(stages) - 0.5)
    ax.invert_yaxis()
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.axis('off')

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()

    console.print(f"[green]Chart saved: {output_path}[/green]")
    return output_path


def generate_dashboard(
    data: dict[str, Any],
    output_path: str,
    title: str = "Analytics Dashboard",
) -> Optional[str]:
    """Generate a multi-chart dashboard image."""
    if not HAS_MATPLOTLIB:
        console.print("[yellow]matplotlib not installed. Run: pip install matplotlib[/yellow]")
        return None

    fig = plt.figure(figsize=(16, 12))

    # Title
    fig.suptitle(title, fontsize=16, fontweight='bold', y=0.98)

    # Chart 1: Customer Type Distribution (Pie)
    if 'customer_types' in data:
        ax1 = fig.add_subplot(2, 2, 1)
        labels = list(data['customer_types'].keys())
        values = list(data['customer_types'].values())
        colors = ['#00C9A7', '#4ADE80', '#A3E635']
        ax1.pie(values, labels=labels, autopct='%1.1f%%', colors=colors)
        ax1.set_title('Customer Distribution')

    # Chart 2: Sales Trend (Line)
    if 'sales_trend' in data:
        ax2 = fig.add_subplot(2, 2, 2)
        dates = data['sales_trend'].get('dates', [])
        values = data['sales_trend'].get('values', [])
        ax2.plot(dates, values, marker='o', color='#00C9A7', linewidth=2)
        ax2.set_title('Sales Trend')
        ax2.tick_params(axis='x', rotation=45)
        ax2.grid(True, alpha=0.3)

    # Chart 3: Channel Performance (Bar)
    if 'channels' in data:
        ax3 = fig.add_subplot(2, 2, 3)
        labels = list(data['channels'].keys())
        values = list(data['channels'].values())
        ax3.bar(labels, values, color='#4ADE80')
        ax3.set_title('Channel Performance')

    # Chart 4: Top Customers (Horizontal Bar)
    if 'top_customers' in data:
        ax4 = fig.add_subplot(2, 2, 4)
        labels = list(data['top_customers'].keys())
        values = list(data['top_customers'].values())
        ax4.barh(labels, values, color='#A3E635')
        ax4.set_title('Top Customers by Spend')

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()

    console.print(f"[green]Dashboard saved: {output_path}[/green]")
    return output_path
