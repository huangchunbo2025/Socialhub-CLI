"""HTML Report Generator for analytics data."""

import base64
import io
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from rich.console import Console

console = Console()

# Check if matplotlib is available
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
except ImportError:
    HAS_MATPLOTLIB = False


def fig_to_base64(fig) -> str:
    """Convert matplotlib figure to base64 string."""
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')
    buf.close()
    plt.close(fig)
    return f"data:image/png;base64,{img_base64}"


def create_bar_chart_base64(data: dict[str, float], title: str = "Bar Chart") -> Optional[str]:
    """Create bar chart and return as base64."""
    if not HAS_MATPLOTLIB:
        return None

    fig, ax = plt.subplots(figsize=(8, 5))
    labels = list(data.keys())
    values = list(data.values())

    colors = ['#00C9A7', '#4ADE80', '#A3E635', '#FBBF24', '#F87171', '#A78BFA']
    ax.bar(labels, values, color=colors[:len(labels)])
    ax.set_title(title, fontsize=12, fontweight='bold')
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()

    return fig_to_base64(fig)


def create_pie_chart_base64(data: dict[str, float], title: str = "Pie Chart") -> Optional[str]:
    """Create pie chart and return as base64."""
    if not HAS_MATPLOTLIB:
        return None

    fig, ax = plt.subplots(figsize=(8, 6))
    labels = list(data.keys())
    values = list(data.values())

    colors = ['#00C9A7', '#4ADE80', '#A3E635', '#FBBF24', '#F87171', '#A78BFA']
    ax.pie(values, labels=labels, autopct='%1.1f%%', colors=colors[:len(labels)], startangle=90)
    ax.set_title(title, fontsize=12, fontweight='bold')

    return fig_to_base64(fig)


def create_line_chart_base64(dates: list, values: list, title: str = "Trend") -> Optional[str]:
    """Create line chart and return as base64."""
    if not HAS_MATPLOTLIB:
        return None

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(dates, values, marker='o', color='#00C9A7', linewidth=2)
    ax.set_title(title, fontsize=12, fontweight='bold')
    ax.grid(True, alpha=0.3)
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()

    return fig_to_base64(fig)


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif;
            background: #f5f7fa;
            color: #1a1a2e;
            line-height: 1.6;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }}

        .header {{
            background: linear-gradient(135deg, #121C3D 0%, #1e3a5f 100%);
            color: white;
            padding: 40px 20px;
            text-align: center;
            margin-bottom: 30px;
            border-radius: 12px;
        }}

        .header h1 {{
            font-size: 28px;
            margin-bottom: 10px;
        }}

        .header .subtitle {{
            color: #a0aec0;
            font-size: 14px;
        }}

        .section {{
            background: white;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }}

        .section h2 {{
            color: #121C3D;
            font-size: 18px;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #00C9A7;
        }}

        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 24px;
        }}

        .stat-card {{
            background: linear-gradient(135deg, #00C9A7 0%, #4ADE80 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
        }}

        .stat-card .value {{
            font-size: 32px;
            font-weight: bold;
            margin-bottom: 5px;
        }}

        .stat-card .label {{
            font-size: 14px;
            opacity: 0.9;
        }}

        .chart-container {{
            text-align: center;
            margin: 20px 0;
        }}

        .chart-container img {{
            max-width: 100%;
            height: auto;
            border-radius: 8px;
        }}

        .chart-row {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 24px;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 16px;
        }}

        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #e2e8f0;
        }}

        th {{
            background: #f8fafc;
            font-weight: 600;
            color: #475569;
        }}

        tr:hover {{
            background: #f8fafc;
        }}

        .footer {{
            text-align: center;
            color: #718096;
            padding: 20px;
            font-size: 12px;
        }}

        .badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
        }}

        .badge-success {{
            background: #d1fae5;
            color: #065f46;
        }}

        .badge-warning {{
            background: #fef3c7;
            color: #92400e;
        }}

        .badge-info {{
            background: #dbeafe;
            color: #1e40af;
        }}

        /* Print styles */
        @media print {{
            body {{
                background: white;
            }}

            .container {{
                max-width: 100%;
                padding: 0;
            }}

            .section {{
                box-shadow: none;
                border: 1px solid #e2e8f0;
                page-break-inside: avoid;
            }}

            .header {{
                background: #121C3D !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
            }}

            .stat-card {{
                background: #00C9A7 !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
            }}

            .chart-row {{
                grid-template-columns: 1fr 1fr;
            }}
        }}

        @page {{
            size: A4;
            margin: 15mm;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
            <p class="subtitle">Generated: {generated_at} | SocialHub.AI Analytics Report</p>
        </div>

        {content}

        <div class="footer">
            <p>Powered by SocialHub.AI CLI | Stop Adding AI, We Are AI.</p>
            <p>To print as PDF, use browser print function (Ctrl+P) and select "Save as PDF"</p>
        </div>
    </div>
</body>
</html>
"""


def generate_overview_section(data: dict) -> str:
    """Generate overview statistics section."""
    stats_html = '<div class="stats-grid">'

    stat_items = [
        ("total_customers", "Total Customers", ""),
        ("total_orders", "Total Orders", ""),
        ("total_revenue", "Total Revenue", ""),
        ("avg_order_value", "Avg Order Value", ""),
        ("new_customers", "New Customers", ""),
        ("active_customers", "Active Customers", ""),
    ]

    for key, label, unit in stat_items:
        if key in data:
            value = data[key]
            if isinstance(value, float):
                formatted = f"{value:,.2f}"
            else:
                formatted = f"{value:,}"
            stats_html += f'''
            <div class="stat-card">
                <div class="value">{formatted}</div>
                <div class="label">{label} ({unit})</div>
            </div>
            '''

    stats_html += '</div>'
    return stats_html


def generate_table_section(data: list[dict], title: str, columns: list[tuple[str, str]]) -> str:
    """Generate a table section."""
    if not data:
        return f'<p>No {title} data available</p>'

    html = f'<table><thead><tr>'
    for col_key, col_name in columns:
        html += f'<th>{col_name}</th>'
    html += '</tr></thead><tbody>'

    for row in data[:20]:  # Limit to 20 rows
        html += '<tr>'
        for col_key, col_name in columns:
            value = row.get(col_key, '-')
            if isinstance(value, float):
                value = f"{value:,.2f}"
            elif isinstance(value, int):
                value = f"{value:,}"
            html += f'<td>{value}</td>'
        html += '</tr>'

    html += '</tbody></table>'

    if len(data) > 20:
        html += f'<p style="color: #718096; margin-top: 10px; font-size: 12px;">Showing first 20 records of {len(data)} total</p>'

    return html


def generate_html_report(
    report_data: dict[str, Any],
    output_path: str,
    title: str = "Analytics Report",
) -> str:
    """Generate a comprehensive HTML report.

    Args:
        report_data: Dictionary containing:
            - overview: dict with summary statistics
            - customers: list of customer data
            - orders: list of order data
            - charts: dict with chart configurations
        output_path: Path to save the HTML file
        title: Report title

    Returns:
        Path to the generated report
    """
    content_parts = []

    # Overview Section
    if 'overview' in report_data:
        content_parts.append(f'''
        <div class="section">
            <h2>📊 Overview</h2>
            {generate_overview_section(report_data['overview'])}
        </div>
        ''')

    # Charts Section
    charts_html = []

    if 'customer_types' in report_data:
        chart_img = create_pie_chart_base64(report_data['customer_types'], "Customer Types Distribution")
        if chart_img:
            charts_html.append(f'''
            <div class="chart-container">
                <img src="{chart_img}" alt="Customer Types Distribution">
            </div>
            ''')

    if 'channels' in report_data:
        chart_img = create_bar_chart_base64(report_data['channels'], "Channel Distribution")
        if chart_img:
            charts_html.append(f'''
            <div class="chart-container">
                <img src="{chart_img}" alt="Channel Distribution">
            </div>
            ''')

    if 'sales_trend' in report_data:
        trend = report_data['sales_trend']
        chart_img = create_line_chart_base64(trend.get('dates', []), trend.get('values', []), "Sales Trend")
        if chart_img:
            charts_html.append(f'''
            <div class="chart-container">
                <img src="{chart_img}" alt="Sales Trend">
            </div>
            ''')

    if 'top_customers' in report_data:
        chart_img = create_bar_chart_base64(report_data['top_customers'], "Top Customer Spending")
        if chart_img:
            charts_html.append(f'''
            <div class="chart-container">
                <img src="{chart_img}" alt="Top Customers">
            </div>
            ''')

    if charts_html:
        content_parts.append(f'''
        <div class="section">
            <h2>📈 Charts</h2>
            <div class="chart-row">
                {"".join(charts_html)}
            </div>
        </div>
        ''')

    # Customer Table
    if 'customers' in report_data and report_data['customers']:
        columns = [
            ('id', 'ID'),
            ('name', 'Name'),
            ('customer_type', 'Type'),
            ('total_orders', 'Orders'),
            ('total_spent', 'Total Spent'),
            ('points_balance', 'Points'),
        ]
        content_parts.append(f'''
        <div class="section">
            <h2>👥 Customers</h2>
            {generate_table_section(report_data['customers'], 'customer', columns)}
        </div>
        ''')

    # Orders Table
    if 'orders' in report_data and report_data['orders']:
        columns = [
            ('order_id', 'Order ID'),
            ('customer_name', 'Customer'),
            ('amount', 'Amount'),
            ('channel', 'Channel'),
            ('status', 'Status'),
            ('order_date', 'Date'),
        ]
        content_parts.append(f'''
        <div class="section">
            <h2>📦 Orders</h2>
            {generate_table_section(report_data['orders'], 'order', columns)}
        </div>
        ''')

    # Segments Summary
    if 'segments' in report_data and report_data['segments']:
        segments_html = '<div class="stats-grid">'
        for seg in report_data['segments'][:6]:
            segments_html += f'''
            <div class="stat-card" style="background: linear-gradient(135deg, #4ADE80 0%, #A3E635 100%);">
                <div class="value">{seg.get('count', 0):,}</div>
                <div class="label">{seg.get('name', 'Unknown')}</div>
            </div>
            '''
        segments_html += '</div>'

        content_parts.append(f'''
        <div class="section">
            <h2>🎯 Customer Segments</h2>
            {segments_html}
        </div>
        ''')

    # Generate final HTML
    content = "\n".join(content_parts)

    html = HTML_TEMPLATE.format(
        title=title,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        content=content,
    )

    # Save to file
    output_file = Path(output_path)
    output_file.write_text(html, encoding='utf-8')

    console.print(f"[green]Report saved: {output_path}[/green]")
    console.print(f"[dim]Open in browser and press Ctrl+P to print as PDF[/dim]")

    return str(output_file.absolute())
