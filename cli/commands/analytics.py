"""Data analytics commands."""

import json
from pathlib import Path

import typer
from rich.console import Console

from ..analytics.advanced import (
    _get_mcp_anomaly,
    _get_mcp_canvas,
    _get_mcp_ltv,
    _get_mcp_recommend,
    _get_mcp_repurchase,
    _get_mcp_repurchase_path,
    _get_mcp_rfm,
    _print_anomaly,
    _print_canvas,
    _print_ltv,
    _print_recommend,
    _print_repurchase,
    _print_repurchase_path,
    _print_rfm,
)
from ..analytics.campaigns import (
    _build_postmortem_markdown,
    _get_mcp_campaign_audience,
    _get_mcp_campaign_detail,
    _get_mcp_campaign_postmortem,
    _get_mcp_campaign_roi,
    _get_mcp_campaigns,
    _print_campaign_audience,
    _print_campaign_detail,
    _print_campaign_roi,
    _print_campaigns_mcp,
)

# Analytics sub-module imports
from ..analytics.common import (
    _compute_date_range,
    _print_sql_trace,
    _safe_date_filter,
    _sql_trace_ctx,
)
from ..analytics.coupons import (
    _get_mcp_coupon_anomaly,
    _get_mcp_coupon_lift,
    _get_mcp_coupons,
    _get_mcp_coupons_by_rule,
    _print_coupon_anomaly,
    _print_coupon_lift,
    _print_coupons_by_rule,
    _print_coupons_mcp,
)
from ..analytics.customers import (
    _get_mcp_customer_gender,
    _get_mcp_customer_source,
    _get_mcp_customers,
    _get_mcp_retention,
    _print_customer_gender,
    _print_customer_source,
)
from ..analytics.funnel import (
    _build_diagnose_prompt,
    _get_mcp_diagnose_context,
    _get_mcp_funnel,
    _print_funnel,
)
from ..analytics.loyalty import (
    _build_loyalty_health_markdown,
    _get_mcp_loyalty,
    _get_mcp_loyalty_health,
    _get_mcp_points,
    _get_mcp_points_at_risk,
    _get_mcp_points_daily_trend,
    _print_loyalty_mcp,
    _print_points_at_risk,
    _print_points_daily_trend,
    _print_points_mcp,
)
from ..analytics.orders import (
    _get_mcp_order_returns,
    _get_mcp_orders,
    _get_mcp_orders_compare_both,
    _print_order_returns,
    _print_orders_by_product,
    _print_orders_compare,
)
from ..analytics.overview import (
    _compute_compare_range,
    _get_mcp_overview,
    _get_mcp_overview_compare_both,
    _print_overview_compare,
)
from ..analytics.products import (
    _get_mcp_products,
    _print_products,
)
from ..analytics.report import (
    _build_report_markdown,
    _get_mcp_report,
    _write_md_report,
)
from ..analytics.stores import (
    _get_mcp_stores,
    _print_stores,
)
from ..api.client import APIError, SocialHubClient
from ..api.mcp_client import MCPClient, MCPError
from ..api.mcp_client import MCPConfig as MCPClientConfig
from ..config import load_config
from ..local.processor import DataProcessor
from ..local.reader import LocalDataReader, read_customers_csv, read_orders_csv
from ..output.export import export_data, format_output, print_export_success
from ..output.formatter import OutputFormatter
from ..output.table import (
    print_dict,
    print_error,
    print_overview,
    print_retention_table,
)

app = typer.Typer(help="Data analytics commands")
console = Console()


_OVERVIEW_EXPLAIN = """[bold dim]── Data Source ──────────────────────────────────────────────[/bold dim]
  Tables   : [cyan]ads_das_business_overview_d[/cyan] (das_demoen)
             [cyan]dwd_v_order[/cyan] (das_demoen) — active buyers
  Updated  : Daily partition on [dim]biz_date[/dim]

[bold dim]Metric Definitions[/bold dim]
  GMV            [dim]total_transaction_amt[/dim] — sum of payment amounts in period
  Orders         [dim]total_order_num[/dim] — count of completed orders
  New customers  [dim]add_custs_num[/dim] — first-time registrations in period
  Active buyers  [dim]COUNT(DISTINCT customer_code)[/dim] from dwd_v_order
  AOV            [dim]GMV ÷ Orders[/dim] — average order value"""


@app.command("overview")
def analytics_overview(
    ctx: typer.Context,
    period: str = typer.Option("7d", "--period", "-p", help="Time period (today, 7d, 30d, 90d, 365d, ytd)"),
    from_date: str | None = typer.Option(None, "--from", help="Start date (YYYY-MM-DD)"),
    to_date: str | None = typer.Option(None, "--to", help="End date (YYYY-MM-DD)"),
    customer_type: str = typer.Option("all", "--type", "-t", help="Customer type (all, members, visitors)"),
    compare: bool = typer.Option(False, "--compare", help="Compare with previous period (MCP only)"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
    output: str | None = typer.Option(None, "--output", "-o", help="Export to file"),
    explain: bool = typer.Option(False, "--explain", help="Show metric definitions and data sources"),
    sql_trace: bool = typer.Option(False, "--sql-trace", help="Print SQL queries executed"),
) -> None:
    """Show analytics overview dashboard.

    Examples:
        sh analytics overview --period=30d
        sh analytics overview --period=30d --compare
        sh analytics overview --explain
    """
    config = load_config()

    if config.mode == "mcp":
        # MCP mode - query real database
        try:
            if sql_trace:
                with _sql_trace_ctx() as sql_log:
                    if compare:
                        prev_start, prev_end, cur_start, cur_end = _compute_compare_range(period)
                        cur_data, prev_data = _get_mcp_overview_compare_both(
                            config, prev_start, prev_end, cur_start, cur_end
                        )
                        _print_overview_compare(cur_data, prev_data, period)
                        _print_sql_trace(sql_log)
                        return
                    data = _get_mcp_overview(config, period)
                _print_sql_trace(sql_log)
            else:
                if compare:
                    prev_start, prev_end, cur_start, cur_end = _compute_compare_range(period)
                    cur_data, prev_data = _get_mcp_overview_compare_both(
                        config, prev_start, prev_end, cur_start, cur_end
                    )
                    _print_overview_compare(cur_data, prev_data, period)
                    if explain:
                        console.print(_OVERVIEW_EXPLAIN)  # already in MCP branch
                    return
                data = _get_mcp_overview(config, period)
        except MCPError as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)
        except Exception as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)
    elif config.mode == "api":
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
    fmt = OutputFormatter.from_context(ctx)
    if output:
        path = export_data(data if isinstance(data, list) else [data], output)
        print_export_success(path)
    elif fmt.fmt != "text":
        fmt.print_record(data if isinstance(data, dict) else {"data": data}, title=f"Analytics Overview ({period})")
    else:
        print_overview(data, title=f"Analytics Overview ({period})")
        if explain:
            if config.mode == "mcp":
                console.print(_OVERVIEW_EXPLAIN)
            else:
                console.print(
                    f"[dim]-- explain is only available in MCP mode "
                    f"(current mode: {config.mode})[/dim]"
                )


@app.command("customers")
def analytics_customers(
    ctx: typer.Context,
    period: str = typer.Option("30d", "--period", "-p", help="Time period"),
    channel: str = typer.Option("all", "--channel", "-c", help="Channel filter (all, wechat, app, web, tmall)"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
    output: str | None = typer.Option(None, "--output", "-o", help="Export to file"),
    source: bool = typer.Option(False, "--source", "-s", help="Show customer acquisition source breakdown (MCP)"),
    gender: bool = typer.Option(False, "--gender", "-g", help="Show gender distribution (MCP)"),
) -> None:
    """Analyze customer metrics."""
    config = load_config()

    if source or gender:
        if config.mode != "mcp":
            print_error("--source and --gender require MCP mode")
            raise typer.Exit(1)
        if source:
            try:
                rows = _get_mcp_customer_source(config, period)
            except Exception as e:
                print_error(f"Error: {e}")
                raise typer.Exit(1)
            if output:
                format_output(rows, format, output)
            else:
                _print_customer_source(rows, period)
        if gender:
            try:
                rows = _get_mcp_customer_gender(config)
            except Exception as e:
                print_error(f"Error: {e}")
                raise typer.Exit(1)
            if output:
                format_output(rows, format, output)
            else:
                _print_customer_gender(rows)
        return

    if config.mode == "mcp":
        # MCP mode - query real database
        try:
            data = _get_mcp_customers(config, period, channel)
        except MCPError as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)
        except Exception as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)
    elif config.mode == "api":
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

    fmt = OutputFormatter.from_context(ctx)
    if not output and fmt.fmt != "text":
        if isinstance(data, list):
            fmt.print_table(data, title=f"Customer Analytics ({period})")
        else:
            fmt.print_record(data, title=f"Customer Analytics ({period})")
    else:
        format_output(data, format, output)


@app.command("retention")
def analytics_retention(
    ctx: typer.Context,
    days: str = typer.Option("7,14,30", "--days", "-d", help="Retention periods in days (comma-separated)"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
    output: str | None = typer.Option(None, "--output", "-o", help="Export to file"),
) -> None:
    """Analyze customer retention rates."""
    # Parse days
    days_list = [int(d.strip()) for d in days.split(",")]

    config = load_config()

    if config.mode == "mcp":
        # MCP mode - query real database
        try:
            data = _get_mcp_retention(config, days_list)
        except MCPError as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)
        except Exception as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)
    elif config.mode == "api":
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

    fmt = OutputFormatter.from_context(ctx)
    if output:
        path = export_data(data, output)
        print_export_success(path)
    elif fmt.fmt != "text":
        if isinstance(data, list):
            fmt.print_table(data, title="Customer Retention")
        else:
            fmt.print_record(data, title="Customer Retention")
    elif format == "json":
        format_output(data, format, None)
    else:
        print_retention_table(data)


@app.command("orders")
def analytics_orders(
    ctx: typer.Context,
    period: str = typer.Option("30d", "--period", "-p", help="Time period"),
    metric: str = typer.Option("sales", "--metric", "-m", help="Metric (sales, volume, atv)"),
    repurchase_rate: bool = typer.Option(False, "--repurchase-rate", help="Show repurchase rate"),
    by: str | None = typer.Option(None, "--by", help="Group by (channel, province, product)"),
    returns: bool = typer.Option(False, "--returns", help="Show return/exchange rate analysis (direction field)"),
    compare: bool = typer.Option(False, "--compare", help="Compare with previous period (MCP only)"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
    output: str | None = typer.Option(None, "--output", "-o", help="Export to file"),
) -> None:
    """Analyze order metrics.

    Examples:
        sh analytics orders --period=30d
        sh analytics orders --period=30d --compare
        sh analytics orders --by=channel
        sh analytics orders --by=product
        sh analytics orders --returns
    """
    config = load_config()

    if config.mode == "mcp":
        # MCP mode - query real database
        try:
            if compare and not by and not returns:
                prev_start, prev_end, cur_start, cur_end = _compute_compare_range(period)
                cur_data, prev_data = _get_mcp_orders_compare_both(
                    config, prev_start, prev_end, cur_start, cur_end
                )
                _print_orders_compare(cur_data, prev_data, period)
                return
            if returns:
                data = _get_mcp_order_returns(config, period)
                if output:
                    format_output(data, "json", output)
                else:
                    _print_order_returns(data)
                return
            data = _get_mcp_orders(config, period, metric, by)
            # Product grouping gets its own rich display
            if by == "product" and isinstance(data, list):
                _print_orders_by_product(data, period, output)
                return
        except MCPError as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)
        except Exception as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)
    elif config.mode == "api":
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

    fmt = OutputFormatter.from_context(ctx)
    if not output and fmt.fmt != "text":
        if isinstance(data, list):
            fmt.print_table(data, title=f"Order Analytics ({period})")
        else:
            fmt.print_record(data, title=f"Order Analytics ({period})")
    else:
        format_output(data, format, output)


@app.command("campaigns")
def analytics_campaigns(
    campaign_id: str | None = typer.Option(None, "--id", help="Campaign ID"),
    name: str | None = typer.Option(None, "--name", "-n", help="Campaign name filter"),
    period: str = typer.Option("30d", "--period", "-p", help="Time period"),
    funnel: bool = typer.Option(False, "--funnel", help="Show conversion funnel"),
    detail: bool = typer.Option(False, "--detail", help="Deep analysis for a single campaign (requires --id)"),
    audience: bool = typer.Option(False, "--audience", help="Tier audience breakdown via BITMAP_AND (requires --id)"),
    campaign_roi: bool = typer.Option(False, "--roi", help="Attributed GMV per campaign (participant orders within window)"),
    window: int = typer.Option(30, "--window", "-w", help="Attribution window days for --roi (1-60)"),
    canvas: str | None = typer.Option(None, "--canvas", help="Canvas journey funnel for a canvas campaign ID"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
    output: str | None = typer.Option(None, "--output", "-o", help="Export to file"),
) -> None:
    """Analyze marketing campaign performance.

    Examples:
        sh analytics campaigns --period=30d
        sh analytics campaigns --id ACT001 --detail
        sh analytics campaigns --id ACT001 --audience
        sh analytics campaigns --name=spring --funnel
        sh analytics campaigns --roi --period=90d
        sh analytics campaigns --canvas ACT_CANVAS_001
    """
    config = load_config()

    if config.mode == "mcp":
        # MCP mode - query real database
        try:
            if canvas:
                canvas_data = _get_mcp_canvas(config, canvas)
                if output:
                    format_output(canvas_data, "json", output,
                                  title=f"Canvas Journey — {canvas}")
                    console.print(f"[green]Exported to {output}[/green]")
                else:
                    _print_canvas(canvas_data)
                return

            if campaign_roi:
                roi_rows = _get_mcp_campaign_roi(config, period, window)
                if output:
                    format_output(roi_rows, "json", output)
                else:
                    _print_campaign_roi(roi_rows, period, window)
                return
            # --audience: BITMAP_AND campaign participants × tier bitmaps
            if audience:
                if not campaign_id:
                    print_error("--audience requires --id <campaign_id>")
                    raise typer.Exit(1)
                aud_rows = _get_mcp_campaign_audience(config, campaign_id)
                if output:
                    format_output(aud_rows, "json", output)
                else:
                    _print_campaign_audience(aud_rows, campaign_id)
                return

            # --detail requires --id
            if detail:
                if not campaign_id:
                    print_error("--detail requires --id <campaign_id>")
                    raise typer.Exit(1)
                detail_data = _get_mcp_campaign_detail(config, campaign_id)
                if output:
                    format_output(detail_data, "json", output)
                else:
                    _print_campaign_detail(detail_data)
                return
            data = _get_mcp_campaigns(config, period, campaign_id, name)
        except MCPError as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)
        except Exception as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)
    elif config.mode == "api":
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
        print_error("Campaign analytics requires API or MCP mode")
        raise typer.Exit(1)

    if config.mode == "mcp" and isinstance(data, list):
        _print_campaigns_mcp(data, output)
    elif funnel and isinstance(data, dict):
        funnel_data = {
            "Target":    f"{data.get('target_count', 0):,}",
            "Reached":   f"{data.get('reached_count', 0):,}",
            "Opened":    f"{data.get('opened_count', 0):,}",
            "Clicked":   f"{data.get('clicked_count', 0):,}",
            "Converted": f"{data.get('converted_count', 0):,}",
        }
        print_dict(funnel_data, title=f"Campaign Funnel: {data.get('campaign_name', 'Unknown')}")
    else:
        format_output(data, format, output)


@app.command("points")
def analytics_points(
    period: str = typer.Option("30d", "--period", "-p", help="Time period: 7d/30d/90d/365d"),
    expiring_days: int = typer.Option(0, "--expiring-days", help="Show points expiring within N days (0=off)"),
    breakdown: bool = typer.Option(False, "--breakdown", help="Break down by operation type"),
    at_risk_members: bool = typer.Option(False, "--at-risk-members", help="List members with points expiring (requires --expiring-days)"),
    daily_trend: bool = typer.Option(False, "--daily-trend", help="Show day-by-day earn vs redeem trend"),
    limit: int = typer.Option(200, "--limit", "-n", help="Max members for --at-risk-members"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
    output: str | None = typer.Option(None, "--output", "-o", help="Export to file"),
) -> None:
    """Analyze points program metrics.

    Examples:
        sh analytics points --period=30d
        sh analytics points --daily-trend --period=30d
        sh analytics points --expiring-days=30
        sh analytics points --expiring-days=30 --at-risk-members
        sh analytics points --expiring-days=30 --at-risk-members --output=at_risk.json
        sh analytics points --breakdown
    """
    config = load_config()

    if config.mode == "mcp":
        # --daily-trend: day-by-day earn vs redeem
        if daily_trend:
            try:
                rows = _get_mcp_points_daily_trend(config, period)
            except (MCPError, Exception) as e:
                print_error(f"Error: {e}")
                raise typer.Exit(1)
            if output:
                format_output(rows, "json", output)
            else:
                _print_points_daily_trend(rows, period)
            return

        # --at-risk-members: produce exportable member list
        if at_risk_members:
            if expiring_days < 1:
                print_error("--at-risk-members requires --expiring-days N (e.g. --expiring-days=30)")
                raise typer.Exit(1)
            try:
                rows = _get_mcp_points_at_risk(config, expiring_days, limit)
            except (MCPError, ValueError) as e:
                print_error(f"Error: {e}")
                raise typer.Exit(1)
            except Exception as e:
                print_error(f"Error: {e}")
                raise typer.Exit(1)
            _print_points_at_risk(rows, expiring_days, output)
            return

        try:
            data = _get_mcp_points(config, period, expiring_days, breakdown)
        except MCPError as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)
        except Exception as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)

        if format == "json" or output:
            format_output(data, format, output)
            return

        _print_points_mcp(data)

    elif config.mode == "api":
        try:
            with SocialHubClient() as client:
                result = client.get("/api/v1/analytics/points", params={"period": period})
                data = result.get("data", result)
        except APIError as e:
            print_error(f"API Error: {e.message}")
            raise typer.Exit(1)
        format_output(data, format, output)
    else:
        print_error("Points analytics requires API or MCP mode")
        raise typer.Exit(1)


@app.command("coupons")
def analytics_coupons(
    period: str = typer.Option("30d", "--period", "-p", help="Time period: 7d/30d/90d/365d"),
    roi: bool = typer.Option(False, "--roi", help="Show face-value ROI and per-rule breakdown"),
    lift: bool = typer.Option(False, "--lift", help="Coupon lift analysis: compare coupon users vs non-users"),
    by_rule: bool = typer.Option(False, "--by-rule", help="Per-rule GMV attribution and ROI"),
    anomaly: bool = typer.Option(False, "--anomaly", help="Detect abnormal daily redeem volume (mean+2sigma)"),
    lookback: int = typer.Option(30, "--lookback", "-l", help="Baseline days for anomaly detection"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max rules for --by-rule (1-200)"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, json)"),
    output: str | None = typer.Option(None, "--output", "-o", help="Export to file"),
) -> None:
    """Analyze coupon usage and redemption value.

    Examples:
        sh analytics coupons --period=30d
        sh analytics coupons --roi
        sh analytics coupons --lift --period=30d
        sh analytics coupons --by-rule --period=90d
        sh analytics coupons --anomaly --lookback=30
    """
    config = load_config()

    if config.mode == "mcp":
        try:
            if anomaly:
                anom_data = _get_mcp_coupon_anomaly(config, lookback, 7)
                if output:
                    format_output(anom_data, "json", output, title="Coupon Anomaly")
                    console.print(f"[green]Exported to {output}[/green]")
                else:
                    _print_coupon_anomaly(anom_data)
                return
            if by_rule:
                rule_rows = _get_mcp_coupons_by_rule(config, period, limit)
                _print_coupons_by_rule(rule_rows, period, output)
                return
            if lift:
                lift_data = _get_mcp_coupon_lift(config, period)
                if output:
                    format_output(lift_data, "json", output)
                else:
                    _print_coupon_lift(lift_data)
                return
            data = _get_mcp_coupons(config, period, roi)
        except MCPError as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)
        except Exception as e:
            print_error(f"MCP Error: {e}")
            raise typer.Exit(1)

        if format == "json" or output:
            format_output(data, format, output)
            return

        _print_coupons_mcp(data, roi)

    elif config.mode == "api":
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
    else:
        print_error("Coupon analytics requires API or MCP mode")
        raise typer.Exit(1)


@app.command("report")
def generate_analytics_report(
    topic: str = typer.Option("客户分析报告", "--topic", "-t", help="Report topic"),
    output: str = typer.Option("analytics_report.md", "--output", "-o", help="Output file path"),
    period: str = typer.Option("365d", "--period", "-p", help="Data period (7d, 30d, 90d, 365d)"),
    formats: str = typer.Option("all", "--formats", "-f", help="Output formats (md, html, pdf, all)"),
) -> None:
    """Generate data-driven analytics report with insights.

    This command fetches real data from MCP and generates a comprehensive
    report with visualizations and strategic recommendations.

    Examples:
        sh analytics report --topic="客户分布分析" --output=report.md
        sh analytics report --topic="市场拓展策略" --period=90d --formats=all
    """
    from datetime import timedelta

    config = load_config()

    if config.mode != "mcp":
        print_error("Analytics report requires MCP mode. Use: sh config set mode mcp")
        raise typer.Exit(1)

    console.print("[dim]Fetching analytics data...[/dim]")

    # Collect all data
    data = {}

    try:
        # 1. Overview data
        data.update(_get_mcp_overview(config, period))

        # 2. Channel data
        mcp_config = MCPClientConfig(
            sse_url=config.mcp.sse_url,
            post_url=config.mcp.post_url,
            tenant_id=config.mcp.tenant_id,
        )
        database = config.mcp.database

        # Use safe date computation
        start_date, today = _compute_date_range(period)

        # Build safe date filter
        date_filter = _safe_date_filter("order_date", start_date)

        with MCPClient(mcp_config) as client:
            client.initialize()

            # Channel distribution (using source_name as channel)
            channel_result = client.query(f"""
                SELECT
                    COALESCE(source_name, 'unknown') as channel,
                    COUNT(*) as order_count,
                    SUM(total_amount) as total_sales,
                    AVG(total_amount) as avg_order_value
                FROM dwd_v_order
                {date_filter}
                GROUP BY source_name
                ORDER BY total_sales DESC
                LIMIT 15
            """, database=database)
            data['channels'] = channel_result if channel_result else []

            # Retention data
            retention_result = []
            for days_period in [7, 30, 90]:
                period_start = today - timedelta(days=days_period)
                ret_result = client.query(f"""
                    SELECT
                        COUNT(DISTINCT CASE WHEN first_order_date >= '{period_start}' THEN customer_code END) as cohort_size,
                        COUNT(DISTINCT CASE WHEN first_order_date >= '{period_start}' AND order_count > 1 THEN customer_code END) as retained_count
                    FROM (
                        SELECT
                            customer_code,
                            MIN(order_date) as first_order_date,
                            COUNT(*) as order_count
                        FROM dwd_v_order
                        GROUP BY customer_code
                    ) t
                """, database=database)

                if ret_result and len(ret_result) > 0:
                    cohort_size = ret_result[0].get("cohort_size", 0) or 0
                    retained = ret_result[0].get("retained_count", 0) or 0
                    rate = (retained / cohort_size * 100) if cohort_size > 0 else 0
                    retention_result.append({
                        "period_days": days_period,
                        "cohort_size": cohort_size,
                        "retained_count": retained,
                        "retention_rate": rate
                    })
            data['retention'] = retention_result

        console.print(f"[dim]Data fetched: {data.get('total_customers', 0):,} customers, {data.get('total_orders', 0):,} orders[/dim]")

        # Generate report using the skill
        console.print("[dim]Generating report...[/dim]")

        # Import the report generator directly via spec to avoid polluting sys.path
        import importlib.util as _ilu
        _rg_path = Path(__file__).parent.parent / 'skills' / 'store' / 'report-generator' / 'main.py'
        try:
            _spec = _ilu.spec_from_file_location("_report_generator", _rg_path)
            report_main = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(report_main)

            result = report_main.generate_data_report(
                topic=topic,
                output=output,
                period=period,
                formats=formats,
                data_json=json.dumps(data)
            )

            console.print("\n[bold green]Report generated successfully![/bold green]")
            console.print(result)

        except Exception as e:
            print_error(f"Error generating report: {e}")
            raise typer.Exit(1)

    except MCPError as e:
        print_error(f"MCP Error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Error: {e}")
        raise typer.Exit(1)


@app.command("loyalty")
def analytics_loyalty(
    output: str | None = typer.Option(None, "--output", "-o", help="Export to JSON file"),
) -> None:
    """Loyalty program overview: enrollment, tier distribution, points liability (MCP).

    Joins vdm_t_loyalty_program, vdm_t_member, vdm_t_points_account in
    dts_demoen to show per-program membership, tier breakdown, and full
    points liability (available + in-transit).

    Examples:
        sh analytics loyalty
        sh analytics loyalty --output=loyalty.json
    """
    config = load_config()

    if config.mode != "mcp":
        print_error("analytics loyalty requires MCP mode")
        raise typer.Exit(1)

    try:
        data = _get_mcp_loyalty(config)
    except MCPError as e:
        print_error(f"MCP Error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Error: {e}")
        raise typer.Exit(1)

    _print_loyalty_mcp(data, output)


@app.command("funnel")
def analytics_funnel(
    period: str = typer.Option("30d", "--period", "-p", help="Time period for new/active metrics"),
    output: str | None = typer.Option(None, "--output", "-o", help="Export raw data to JSON"),
) -> None:
    """Customer lifecycle funnel: New -> First Purchase -> Repeat -> Loyal -> At-Risk -> Churned.

    Shows conversion rates between lifecycle stages and identifies where customers drop off.

    Examples:
        sh analytics funnel
        sh analytics funnel --period=90d
    """
    config = load_config()

    if config.mode != "mcp":
        print_error("analytics funnel requires MCP mode")
        raise typer.Exit(1)

    try:
        data = _get_mcp_funnel(config, period)
    except MCPError as e:
        print_error(f"MCP Error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Error: {e}")
        raise typer.Exit(1)

    if output:
        path = export_data([data], output)
        print_export_success(path)
    else:
        _print_funnel(data)


@app.command("diagnose")
def analytics_diagnose(
    output: str | None = typer.Option(None, "--output", "-o", help="Save AI diagnosis to text file"),
) -> None:
    """AI-synthesized business health diagnosis across all key metrics.

    Gathers data from overview, orders, customers, campaigns and points tables,
    then calls the configured AI (Azure OpenAI / OpenAI) to produce a concise
    diagnosis with actionable recommendations.

    Requires MCP mode and a configured AI API key.

    Examples:
        sh analytics diagnose
        sh analytics diagnose --output=diagnosis.txt
    """
    config = load_config()

    if config.mode != "mcp":
        print_error("analytics diagnose requires MCP mode")
        raise typer.Exit(1)

    console.print("[dim]Gathering metrics from database...[/dim]")
    try:
        ctx = _get_mcp_diagnose_context(config)
    except MCPError as e:
        print_error(f"MCP Error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Error: {e}")
        raise typer.Exit(1)

    prompt = _build_diagnose_prompt(ctx)

    from .ai import call_ai_api
    diagnosis, _ = call_ai_api(prompt, show_thinking=True)

    from rich.panel import Panel
    console.print(Panel(diagnosis, title="[bold cyan]AI Business Diagnosis[/bold cyan]",
                        border_style="cyan", padding=(1, 2)))

    if output:
        Path(output).write_text(diagnosis, encoding="utf-8")
        print_export_success(output)


@app.command("products")
def analytics_products(
    period: str = typer.Option("30d", "--period", "-p", help="Time period: today/7d/30d/90d/365d"),
    by_category: bool = typer.Option(False, "--by-category", help="Roll up by product category instead of SKU"),
    limit: int = typer.Option(30, "--limit", "-n", help="Max rows (1-500)"),
    output: str | None = typer.Option(None, "--output", "-o", help="Export to JSON file"),
    show_sql: bool = typer.Option(False, "--show-sql", help="Print SQL queries used"),
) -> None:
    """Product and category revenue analysis (MCP only).

    Joins vdm_t_order → vdm_t_order_detail → vdm_t_product in dts_demoen.
    Normal sales only (direction=0).

    Examples:
        sh analytics products --period=30d
        sh analytics products --by-category
        sh analytics products --by-category --period=90d --output=cats.json
    """
    config = load_config()

    if config.mode != "mcp":
        print_error("analytics products requires MCP mode")
        raise typer.Exit(1)

    try:
        with _sql_trace_ctx() as _sql_log:
            rows = _get_mcp_products(config, period, by_category, limit)
    except MCPError as e:
        print_error(f"MCP Error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Error: {e}")
        raise typer.Exit(1)

    _print_products(rows, period, by_category, output)
    if show_sql:
        _print_sql_trace(_sql_log)


@app.command("stores")
def analytics_stores(
    period: str = typer.Option("30d", "--period", "-p", help="Time period: today/7d/30d/90d/365d"),
    limit: int  = typer.Option(30,    "--limit",  "-n", help="Max stores (1-200)"),
    output: str | None = typer.Option(None, "--output", "-o", help="Export JSON"),
    show_sql: bool = typer.Option(False, "--show-sql", help="Print SQL queries used"),
) -> None:
    """Store-level performance: revenue, ATV, unique customers, repeat rate (MCP).

    Examples:
        sh analytics stores
        sh analytics stores --period=90d --limit=50
    """
    config = load_config()
    if config.mode != "mcp":
        print_error("analytics stores requires MCP mode")
        raise typer.Exit(1)
    try:
        with _sql_trace_ctx() as _sql_log:
            rows = _get_mcp_stores(config, period, limit)
    except (MCPError, Exception) as e:
        print_error(f"Error: {e}"); raise typer.Exit(1)
    _print_stores(rows, period, output)
    if show_sql:
        _print_sql_trace(_sql_log)


@app.command("ltv")
def analytics_ltv(
    cohorts: int  = typer.Option(6,  "--cohorts",  "-c", help="Number of past cohort-months to show (1-24)"),
    window: int   = typer.Option(3,  "--window",   "-w", help="Follow-up months per cohort (1-12)"),
    output: str | None = typer.Option(None, "--output", "-o", help="Export JSON"),
    show_sql: bool = typer.Option(False, "--show-sql", help="Print SQL queries used"),
) -> None:
    """Cohort-based Lifetime Value: GMV per customer by first-order month (MCP).

    Groups customers by the month of their first order, then tracks
    per-customer GMV for each follow-up month (M0, M1, M2 …).

    Examples:
        sh analytics ltv
        sh analytics ltv --cohorts=12 --window=6
        sh analytics ltv --output=ltv.json
    """
    config = load_config()
    if config.mode != "mcp":
        print_error("analytics ltv requires MCP mode")
        raise typer.Exit(1)
    try:
        with _sql_trace_ctx() as _sql_log:
            rows = _get_mcp_ltv(config, cohorts, window)
    except (MCPError, Exception) as e:
        print_error(f"Error: {e}"); raise typer.Exit(1)

    if output:
        format_output(rows, "json", output)
    else:
        _print_ltv(rows, cohorts, window)
    if show_sql:
        _print_sql_trace(_sql_log)


@app.command("repurchase")
def analytics_repurchase(
    period: str = typer.Option("90d", "--period", "-p",
                               help="Analysis period: 30d/90d/365d"),
    output: str | None = typer.Option(None, "--output", "-o", help="Export to JSON/CSV/MD"),
    show_sql: bool = typer.Option(False, "--show-sql", help="Print SQL queries used"),
) -> None:
    """Repurchase rate, GMV contribution, and first-to-second order timing distribution (MCP).

    Key repurchase health metrics:
    - Repurchase buyer count and rate
    - GMV contribution from repeat orders
    - Days-to-repurchase distribution: impulse / habit / demand / low-frequency
    - Monthly repurchase rate trend

    Examples:
        sh analytics repurchase
        sh analytics repurchase --period=365d
        sh analytics repurchase --output=repurchase.json
    """
    config = load_config()
    if config.mode != "mcp":
        print_error("analytics repurchase requires MCP mode")
        raise typer.Exit(1)
    try:
        with _sql_trace_ctx() as _sql_log:
            data = _get_mcp_repurchase(config, period)
    except (MCPError, Exception) as e:
        print_error(f"Error: {e}")
        raise typer.Exit(1)

    if output:
        format_output(data, "json", output)
    else:
        _print_repurchase(data)
    if show_sql:
        _print_sql_trace(_sql_log)


@app.command("repurchase-path")
def analytics_repurchase_path(
    period: str = typer.Option("90d", "--period", "-p",
                               help="Analysis period: 30d/90d/365d"),
    limit: int  = typer.Option(20,  "--limit",  "-n",
                               help="Number of category pairs to show (1-100)"),
    output: str | None = typer.Option(None, "--output", "-o", help="Export to JSON/CSV/MD"),
    show_sql: bool = typer.Option(False, "--show-sql", help="Print SQL queries used"),
) -> None:
    """First-to-repurchase category transition path analysis (MCP).

    Answers 'what category do customers buy on their second order?':
    - First-order category -> repurchase category Top-N transition matrix
    - Per-first-category repurchase rate and same-category retention (stickiness)

    Examples:
        sh analytics repurchase-path
        sh analytics repurchase-path --period=365d --limit=30
        sh analytics repurchase-path --output=path.json
    """
    config = load_config()
    if config.mode != "mcp":
        print_error("analytics repurchase-path requires MCP mode")
        raise typer.Exit(1)
    try:
        with _sql_trace_ctx() as _sql_log:
            data = _get_mcp_repurchase_path(config, period, limit)
    except (MCPError, Exception) as e:
        print_error(f"Error: {e}")
        raise typer.Exit(1)

    if output:
        format_output(data, "json", output)
    else:
        _print_repurchase_path(data)
    if show_sql:
        _print_sql_trace(_sql_log)


@app.command("anomaly")
def analytics_anomaly(
    metric: str = typer.Option("gmv", "--metric", "-m",
                               help="Metric to monitor: gmv / orders / aov / new_buyers"),
    lookback: int = typer.Option(30, "--lookback", "-l",
                                 help="Baseline history days (default 30)"),
    days: int = typer.Option(7, "--days", "-d",
                             help="Detection window: flag anomalies in last N days (default 7)"),
    output: str | None = typer.Option(None, "--output", "-o", help="Export JSON / CSV / MD"),
    show_sql: bool = typer.Option(False, "--show-sql", help="Print SQL queries used"),
) -> None:
    """Statistical anomaly detection on daily business metrics (MCP).

    Computes mean +/- 2 sigma from the baseline window and flags any day
    in the detection window that falls outside the band.

    Metrics: gmv | orders | aov | new_buyers

    Data source: dws_order_base_metrics_d (DWS pre-aggregated layer).
    Falls back to dwd_v_order if the DWS table is unavailable.

    Examples:
        sh analytics anomaly
        sh analytics anomaly --metric=orders --days=7
        sh analytics anomaly --metric=gmv --lookback=60 --days=14
        sh analytics anomaly --output=anomaly.md
    """
    config = load_config()
    if config.mode != "mcp":
        print_error("analytics anomaly requires MCP mode")
        raise typer.Exit(1)

    try:
        with _sql_trace_ctx() as _sql_log:
            data = _get_mcp_anomaly(config, metric, lookback, days)
    except (MCPError, Exception) as e:
        print_error(f"Error: {e}")
        raise typer.Exit(1)

    if output:
        from datetime import datetime, timezone
        meta = {"metric": metric, "lookback": f"{lookback}d", "detect_window": f"{days}d",
                "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
        format_output(data, "json", output,
                      title=f"Anomaly Detection — {metric}", metadata=meta)
        console.print(f"[green]Exported to {output}[/green]")
    else:
        _print_anomaly(data)

    if show_sql:
        _print_sql_trace(_sql_log)


@app.command("report")
def analytics_report(
    period: str = typer.Argument("weekly", help="weekly | monthly | campaign | loyalty"),
    campaign_id: str | None = typer.Option(None, "--id", help="Campaign ID (required for 'campaign' period)"),
    output: str | None = typer.Option(None, "--output", "-o",
                                          help="Export Markdown report to file (e.g. report.md)"),
    show_sql: bool = typer.Option(False, "--show-sql", help="Print SQL queries used"),
) -> None:
    """Generate standard business reports (MCP).

    Periods:
      weekly    — last 7 days vs prior 7 days (GMV, orders, new buyers, top products)
      monthly   — last 30 days vs prior 30 days
      campaign  — post-mortem for a single campaign (requires --id)
      loyalty   — loyalty program health review (enrollment, points, churn)

    Examples:
        sh analytics report weekly
        sh analytics report monthly --output=monthly_report.md
        sh analytics report campaign --id ACT001 --output=postmortem.md
        sh analytics report loyalty --output=loyalty_health.md
    """
    valid = ("weekly", "monthly", "campaign", "loyalty")
    if period not in valid:
        console.print(f"[red]period must be one of: {', '.join(valid)}[/red]")
        raise typer.Exit(1)

    if period == "campaign" and not campaign_id:
        console.print("[red]'campaign' report requires --id <campaign_id>[/red]")
        raise typer.Exit(1)

    config = load_config()
    if config.mode != "mcp":
        console.print("[red]analytics report requires MCP mode[/red]")
        raise typer.Exit(1)

    try:
        with _sql_trace_ctx() as _sql_log:
            if period == "campaign":
                data = _get_mcp_campaign_postmortem(config, campaign_id)
                md   = _build_postmortem_markdown(data)
                _write_md_report(md, output, f"Campaign Post-Mortem: {campaign_id}")
            elif period == "loyalty":
                data = _get_mcp_loyalty_health(config)
                md   = _build_loyalty_health_markdown(data)
                _write_md_report(md, output, "Loyalty Program Health Review")
            else:
                data = _get_mcp_report(config, period)
                md   = _build_report_markdown(data)
                _write_md_report(md, output, f"{period.capitalize()} Report")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if show_sql:
        _print_sql_trace(_sql_log)


@app.command("recommend")
def analytics_recommend(
    user_id: str | None = typer.Option(None, "--user", "-u",
                                           help="Show recommendations for a specific user ID"),
    product_id: str | None = typer.Option(None, "--product", "-p",
                                              help="Show products associated with a product ID"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of results (default 20)"),
    output: str | None = typer.Option(None, "--output", "-o", help="Export to file"),
    show_sql: bool = typer.Option(False, "--show-sql", help="Print SQL queries used"),
) -> None:
    """Recommendation engine analysis: top products, user recs, product affinity (MCP).

    Uses dwd_rec_user_product_rating, dws_rec_user_recs,
    dws_rec_product_to_prdocut_rating.

    Examples:
        sh analytics recommend
        sh analytics recommend --user U12345
        sh analytics recommend --product P00123
        sh analytics recommend --limit=50 --output=recs.json
    """
    config = load_config()
    if config.mode != "mcp":
        console.print("[red]analytics recommend requires MCP mode[/red]")
        raise typer.Exit(1)

    try:
        with _sql_trace_ctx() as _sql_log:
            data = _get_mcp_recommend(config, user_id, product_id, limit)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if output:
        format_output(data, "json", output, title="Recommendation Analysis")
        console.print(f"[green]Exported to {output}[/green]")
    else:
        _print_recommend(data)

    if show_sql:
        _print_sql_trace(_sql_log)


@app.command("rfm")
def analytics_rfm(
    segment: str = typer.Option("", "--segment", "-s",
                                help="Filter to specific RFM segment code (e.g. high_value, at_risk)"),
    top: int = typer.Option(0, "--top", "-t",
                            help="Also show top N customers by RFM score (0=off, max 500)"),
    output: str | None = typer.Option(None, "--output", "-o", help="Export JSON"),
) -> None:
    """RFM customer segmentation - segment distribution, avg spend, avg orders (MCP).

    Queries ads_v_rfm in das_demoen. Shows segment distribution with average
    spend, order frequency, and recency. Use --top N to list highest-scoring customers.

    Examples:
        sh analytics rfm
        sh analytics rfm --segment=high_value
        sh analytics rfm --top=20
        sh analytics rfm --output=rfm.json
    """
    config = load_config()
    if config.mode != "mcp":
        console.print("[red]analytics rfm requires MCP mode[/red]")
        raise typer.Exit(1)

    try:
        with _sql_trace_ctx() as _sql_log:
            data = _get_mcp_rfm(config, limit=top, segment_filter=segment)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if output:
        format_output(data, "json", output, title="RFM Analysis")
        console.print(f"[green]Exported to {output}[/green]")
    else:
        _print_rfm(data, show_top=(top > 0))
