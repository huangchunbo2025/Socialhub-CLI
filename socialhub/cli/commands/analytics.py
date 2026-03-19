"""Data analytics commands."""

import json
from typing import Optional

import typer
from rich.console import Console

from ..api.client import APIError, SocialHubClient
from ..config import load_config
from ..local.processor import DataProcessor
from ..local.reader import LocalDataReader, read_customers_csv, read_orders_csv
from ..output.chart import (
    create_bar_chart,
    print_funnel_chart,
    save_bar_chart,
    save_pie_chart,
    save_line_chart,
    generate_dashboard,
)
from ..output.report import generate_html_report
from ..output.export import export_data, format_output, print_export_success
from ..output.table import (
    print_dataframe,
    print_dict,
    print_error,
    print_list,
    print_overview,
    print_retention_table,
)

app = typer.Typer(help="Data analytics commands")
console = Console()


def get_data_source():
    """Get data source based on config mode."""
    config = load_config()
    return config.mode


@app.command("overview")
def analytics_overview(
    period: str = typer.Option("7d", "--period", "-p", help="Time period (today, 7d, 30d, 90d, 365d, ytd)"),
    from_date: Optional[str] = typer.Option(None, "--from", help="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = typer.Option(None, "--to", help="End date (YYYY-MM-DD)"),
    customer_type: str = typer.Option("all", "--type", "-t", help="Customer type (all, members, visitors)"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to file"),
) -> None:
    """Show analytics overview dashboard."""
    config = load_config()

    if config.mode == "api":
        try:
            with SocialHubClient() as client:
                result = client.get_analytics_overview(
                    period=period,
                    from_date=from_date,
                    to_date=to_date,
                    customer_type=customer_type,
                )
                data = result.get("data", result)
        except APIError as e:
            print_error(f"API Error: {e.message}")
            raise typer.Exit(1)
    else:
        # Local mode
        try:
            reader = LocalDataReader(config.local.data_dir)
            customers_df = read_customers_csv("customers.csv", config.local.data_dir)
            orders_df = read_orders_csv("orders.csv", config.local.data_dir)

            data = DataProcessor.calculate_overview(
                customers_df, orders_df, period
            )
        except Exception as e:
            print_error(f"Local data error: {e}")
            raise typer.Exit(1)

    # Output
    if output:
        path = export_data(data if isinstance(data, list) else [data], output)
        print_export_success(path)
    elif format == "json":
        console.print_json(json.dumps(data, default=str))
    else:
        print_overview(data, title=f"Analytics Overview ({period})")


@app.command("customers")
def analytics_customers(
    period: str = typer.Option("30d", "--period", "-p", help="Time period"),
    channel: str = typer.Option("all", "--channel", "-c", help="Channel filter (all, wechat, app, web, tmall)"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to file"),
) -> None:
    """Analyze customer metrics."""
    config = load_config()

    if config.mode == "api":
        try:
            with SocialHubClient() as client:
                result = client.get_customer_analytics(period=period, channel=channel)
                data = result.get("data", result)
        except APIError as e:
            print_error(f"API Error: {e.message}")
            raise typer.Exit(1)
    else:
        # Local mode - simplified customer stats
        try:
            customers_df = read_customers_csv("customers.csv", config.local.data_dir)

            # Basic stats
            data = {
                "total_customers": len(customers_df),
                "by_type": customers_df["customer_type"].value_counts().to_dict() if "customer_type" in customers_df.columns else {},
            }

            if channel != "all" and "channels" in customers_df.columns:
                customers_df = customers_df[customers_df["channels"].str.contains(channel, case=False, na=False)]
                data["filtered_count"] = len(customers_df)
        except Exception as e:
            print_error(f"Local data error: {e}")
            raise typer.Exit(1)

    format_output(data, format, output)


@app.command("retention")
def analytics_retention(
    days: str = typer.Option("7,14,30", "--days", "-d", help="Retention periods in days (comma-separated)"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to file"),
) -> None:
    """Analyze customer retention rates."""
    # Parse days
    days_list = [int(d.strip()) for d in days.split(",")]

    config = load_config()

    if config.mode == "api":
        try:
            with SocialHubClient() as client:
                result = client.get_retention_analytics(days=days_list)
                data = result.get("data", result)
        except APIError as e:
            print_error(f"API Error: {e.message}")
            raise typer.Exit(1)
    else:
        # Local mode
        try:
            orders_df = read_orders_csv("orders.csv", config.local.data_dir)
            data = DataProcessor.calculate_retention(orders_df, days_list)
        except Exception as e:
            print_error(f"Local data error: {e}")
            raise typer.Exit(1)

    if output:
        path = export_data(data, output)
        print_export_success(path)
    elif format == "json":
        console.print_json(json.dumps(data, default=str))
    else:
        print_retention_table(data)


@app.command("orders")
def analytics_orders(
    period: str = typer.Option("30d", "--period", "-p", help="Time period"),
    metric: str = typer.Option("sales", "--metric", "-m", help="Metric (sales, volume, atv)"),
    repurchase_rate: bool = typer.Option(False, "--repurchase-rate", help="Show repurchase rate"),
    by: Optional[str] = typer.Option(None, "--by", help="Group by (channel, province)"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to file"),
) -> None:
    """Analyze order metrics."""
    config = load_config()

    if config.mode == "api":
        try:
            with SocialHubClient() as client:
                result = client.get_order_analytics(period=period, metric=metric)
                data = result.get("data", result)
        except APIError as e:
            print_error(f"API Error: {e.message}")
            raise typer.Exit(1)
    else:
        # Local mode
        try:
            orders_df = read_orders_csv("orders.csv", config.local.data_dir)

            if by == "channel":
                df = DataProcessor.group_by_channel(orders_df, period)
                format_output(df, format, output)
                return
            elif by == "province":
                df = DataProcessor.group_by_province(orders_df, period)
                format_output(df, format, output)
                return
            else:
                data = DataProcessor.calculate_order_metrics(orders_df, period, metric)
        except Exception as e:
            print_error(f"Local data error: {e}")
            raise typer.Exit(1)

    format_output(data, format, output)


@app.command("campaigns")
def analytics_campaigns(
    campaign_id: Optional[str] = typer.Option(None, "--id", help="Campaign ID"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Campaign name filter"),
    period: str = typer.Option("30d", "--period", "-p", help="Time period"),
    funnel: bool = typer.Option(False, "--funnel", help="Show conversion funnel"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to file"),
) -> None:
    """Analyze marketing campaign performance."""
    config = load_config()

    if config.mode == "api":
        try:
            with SocialHubClient() as client:
                result = client.get_campaign_analytics(
                    campaign_id=campaign_id,
                    name=name,
                    period=period,
                )
                data = result.get("data", result)
        except APIError as e:
            print_error(f"API Error: {e.message}")
            raise typer.Exit(1)
    else:
        # Local mode - not supported without campaign data
        print_error("Campaign analytics requires API mode")
        raise typer.Exit(1)

    if funnel and isinstance(data, dict):
        # Show funnel visualization
        stages = [
            ("Target", data.get("target_count", 0)),
            ("Reached", data.get("reached_count", 0)),
            ("Opened", data.get("opened_count", 0)),
            ("Clicked", data.get("clicked_count", 0)),
            ("Converted", data.get("converted_count", 0)),
        ]
        print_funnel_chart(stages, title=f"Campaign Funnel: {data.get('campaign_name', 'Unknown')}")
    else:
        format_output(data, format, output)


@app.command("points")
def analytics_points(
    period: str = typer.Option("30d", "--period", "-p", help="Time period"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to file"),
) -> None:
    """Analyze points program metrics."""
    config = load_config()

    if config.mode != "api":
        print_error("Points analytics requires API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            # Get points statistics
            result = client.get("/api/v1/analytics/points", params={"period": period})
            data = result.get("data", result)
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)

    format_output(data, format, output)


@app.command("coupons")
def analytics_coupons(
    period: str = typer.Option("30d", "--period", "-p", help="Time period"),
    roi: bool = typer.Option(False, "--roi", help="Calculate ROI"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export to file"),
) -> None:
    """Analyze coupon usage metrics."""
    config = load_config()

    if config.mode != "api":
        print_error("Coupon analytics requires API mode")
        raise typer.Exit(1)

    try:
        with SocialHubClient() as client:
            params = {"period": period}
            if roi:
                params["include_roi"] = "true"
            result = client.get("/api/v1/analytics/coupons", params=params)
            data = result.get("data", result)
    except APIError as e:
        print_error(f"API Error: {e.message}")
        raise typer.Exit(1)

    format_output(data, format, output)


@app.command("chart")
def generate_chart(
    chart_type: str = typer.Argument(..., help="Chart type: bar, pie, line, funnel, dashboard"),
    data_source: str = typer.Option("customers", "--data", "-d", help="Data source: customers, orders"),
    metric: str = typer.Option("count", "--metric", "-m", help="Metric: count, total_spent, orders"),
    group_by: str = typer.Option("customer_type", "--group", "-g", help="Group by field"),
    output: str = typer.Option("chart.png", "--output", "-o", help="Output file path"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Chart title"),
) -> None:
    """Generate analysis charts and save as image.

    Examples:
        sh analytics chart bar --data=customers --group=customer_type
        sh analytics chart pie --data=orders --metric=total_spent --group=channel
        sh analytics chart dashboard --output=report.png
    """
    config = load_config()

    try:
        # Load data based on source
        if data_source == "customers":
            df = read_customers_csv("customers.csv", config.local.data_dir)
        elif data_source == "orders":
            df = read_orders_csv("orders.csv", config.local.data_dir)
        else:
            print_error(f"Unknown data source: {data_source}")
            raise typer.Exit(1)

        # Calculate metrics based on grouping
        if metric == "count":
            chart_data = df.groupby(group_by).size().to_dict()
        elif metric == "total_spent":
            if "total_spent" in df.columns:
                chart_data = df.groupby(group_by)["total_spent"].sum().to_dict()
            elif "amount" in df.columns:
                chart_data = df.groupby(group_by)["amount"].sum().to_dict()
            else:
                print_error("No spending column found in data")
                raise typer.Exit(1)
        elif metric == "orders":
            if "total_orders" in df.columns:
                chart_data = df.groupby(group_by)["total_orders"].sum().to_dict()
            else:
                chart_data = df.groupby(group_by).size().to_dict()
        else:
            print_error(f"Unknown metric: {metric}")
            raise typer.Exit(1)

        # Generate chart title
        chart_title = title or f"{data_source.title()} by {group_by.replace('_', ' ').title()}"

        # Generate chart based on type
        if chart_type == "bar":
            save_bar_chart(chart_data, output, title=chart_title)
        elif chart_type == "pie":
            save_pie_chart(chart_data, output, title=chart_title)
        elif chart_type == "line":
            # For line chart, need time series data
            if "date" in df.columns or "created_at" in df.columns:
                date_col = "date" if "date" in df.columns else "created_at"
                df[date_col] = df[date_col].astype(str).str[:10]
                line_data = df.groupby(date_col).size().to_dict()
                dates = list(line_data.keys())
                values = list(line_data.values())
                save_line_chart({"Count": values}, dates, output, title=chart_title)
            else:
                print_error("Line chart requires date column")
                raise typer.Exit(1)
        elif chart_type == "dashboard":
            # Generate comprehensive dashboard
            customers_df = read_customers_csv("customers.csv", config.local.data_dir)
            orders_df = read_orders_csv("orders.csv", config.local.data_dir)

            dashboard_data = {
                "customer_types": customers_df.groupby("customer_type").size().to_dict(),
                "channels": customers_df["channels"].str.split(";").explode().value_counts().head(5).to_dict(),
                "top_customers": customers_df.nlargest(5, "total_spent").set_index("name")["total_spent"].to_dict(),
            }

            # Add sales trend if orders have dates
            if "date" in orders_df.columns or "order_date" in orders_df.columns:
                date_col = "date" if "date" in orders_df.columns else "order_date"
                orders_df[date_col] = orders_df[date_col].astype(str).str[:10]
                trend = orders_df.groupby(date_col)["amount"].sum()
                dashboard_data["sales_trend"] = {
                    "dates": trend.index.tolist()[-10:],
                    "values": trend.values.tolist()[-10:],
                }

            generate_dashboard(dashboard_data, output, title=chart_title or "Analytics Dashboard")
        elif chart_type == "funnel":
            # Create a sample funnel from customer journey
            total = len(df)
            funnel_stages = [
                ("Total Customers", total),
                ("Active (30d)", int(total * 0.7)),
                ("Made Purchase", int(total * 0.5)),
                ("Repeat Purchase", int(total * 0.3)),
                ("VIP", int(total * 0.1)),
            ]
            from ..output.chart import save_funnel_chart
            save_funnel_chart(funnel_stages, output, title=chart_title or "Customer Funnel")
        else:
            print_error(f"Unknown chart type: {chart_type}. Use: bar, pie, line, funnel, dashboard")
            raise typer.Exit(1)

    except FileNotFoundError as e:
        print_error(f"Data file not found: {e}")
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Error generating chart: {e}")
        raise typer.Exit(1)


@app.command("report")
def generate_report(
    output: str = typer.Option("report.html", "--output", "-o", help="Output HTML file path"),
    title: str = typer.Option("SocialHub 数据分析报告", "--title", "-t", help="Report title"),
    include_customers: bool = typer.Option(True, "--customers/--no-customers", help="Include customer list"),
    include_orders: bool = typer.Option(True, "--orders/--no-orders", help="Include order list"),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Open report in browser"),
) -> None:
    """Generate comprehensive HTML analysis report.

    The report can be printed as PDF using browser's print function (Ctrl+P).

    Examples:
        sh analytics report
        sh analytics report --output=monthly_report.html --title="3月分析报告"
        sh analytics report --no-customers --no-orders
    """
    config = load_config()

    try:
        # Load all data
        customers_df = read_customers_csv("customers.csv", config.local.data_dir)
        orders_df = read_orders_csv("orders.csv", config.local.data_dir)

        # Prepare report data
        report_data = {}

        # Overview statistics
        report_data['overview'] = {
            'total_customers': len(customers_df),
            'total_orders': customers_df['total_orders'].sum() if 'total_orders' in customers_df.columns else len(orders_df),
            'total_revenue': customers_df['total_spent'].sum() if 'total_spent' in customers_df.columns else orders_df['amount'].sum() if 'amount' in orders_df.columns else 0,
            'avg_order_value': orders_df['amount'].mean() if 'amount' in orders_df.columns else 0,
            'new_customers': len(customers_df[customers_df['customer_type'] == 'registered']) if 'customer_type' in customers_df.columns else 0,
            'active_customers': len(customers_df[customers_df['total_orders'] > 0]) if 'total_orders' in customers_df.columns else len(customers_df),
        }

        # Customer type distribution
        if 'customer_type' in customers_df.columns:
            report_data['customer_types'] = customers_df.groupby('customer_type').size().to_dict()

        # Channel distribution
        if 'channels' in customers_df.columns:
            report_data['channels'] = customers_df['channels'].str.split(';').explode().value_counts().head(5).to_dict()

        # Top customers
        if 'total_spent' in customers_df.columns and 'name' in customers_df.columns:
            top_customers = customers_df.nlargest(5, 'total_spent')
            report_data['top_customers'] = dict(zip(top_customers['name'], top_customers['total_spent']))

        # Sales trend
        if 'order_date' in orders_df.columns or 'date' in orders_df.columns:
            date_col = 'order_date' if 'order_date' in orders_df.columns else 'date'
            orders_df[date_col] = orders_df[date_col].astype(str).str[:10]
            if 'amount' in orders_df.columns:
                trend = orders_df.groupby(date_col)['amount'].sum()
                report_data['sales_trend'] = {
                    'dates': trend.index.tolist()[-10:],
                    'values': trend.values.tolist()[-10:],
                }

        # Customer list
        if include_customers:
            report_data['customers'] = customers_df.head(20).to_dict(orient='records')

        # Order list
        if include_orders:
            report_data['orders'] = orders_df.head(20).to_dict(orient='records')

        # Generate report
        report_path = generate_html_report(report_data, output, title=title)

        # Open in browser
        if open_browser:
            import webbrowser
            webbrowser.open(f'file://{report_path}')
            console.print("[cyan]Report opened in browser[/cyan]")

        console.print(f"\n[bold green]✓ Report generated successfully![/bold green]")
        console.print(f"[dim]To save as PDF: Open in browser → Ctrl+P → Save as PDF[/dim]")

    except FileNotFoundError as e:
        print_error(f"Data file not found: {e}")
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Error generating report: {e}")
        raise typer.Exit(1)
