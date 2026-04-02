"""Stable adapter layer between the MCP server and analytics CLI commands.

This module is the single, versioned import surface that ``mcp_server/server.py``
uses to access analytics functions.  It re-exports the relevant private helpers
from the various ``cli.analytics.*`` sub-modules so that:

* Internal refactoring of the sub-modules does not break the MCP server import.
* The public contract between the server and the CLI is explicit and auditable.
* Import aliases or shims can be added here without touching ``server.py``.

Usage in server.py::

    from cli.analytics.mcp_adapter import (
        _get_mcp_overview,
        _get_mcp_customers,
        ...
    )

Maintenance note — adding a new analytics MCP tool requires updates in 5 places:
  1. ``cli/analytics/<module>.py``       — implement ``_get_mcp_<tool>``
  2. ``cli/analytics/mcp_adapter.py``    — re-export here (import + __all__)
  3. ``mcp_server/server.py``            — add handler + TOOLS entry + _HANDLERS entry
  4. ``mcp_server/server.py::_load_analytics``  — add to the import list
  5. ``cli/commands/analytics.py``       — add CLI command that calls the same function
     (analytics.py imports directly from cli.analytics.* for CLI rendering; it is a
     separate entry point from mcp_adapter and must be kept in sync manually)
"""

from cli.analytics.overview import (
    _get_mcp_overview,
    _get_mcp_report_data,
    _compute_compare_range,
    _get_mcp_overview_compare_both,
    _fmt_cny,
)
from cli.analytics.customers import (
    _get_mcp_customers,
    _get_mcp_retention,
    _get_mcp_customer_source,
    _get_mcp_customer_gender,
)
from cli.analytics.orders import (
    _get_mcp_orders,
    _get_mcp_order_returns,
    _get_mcp_orders_tool_payload,
    _get_mcp_orders_compare_both,
)
from cli.analytics.campaigns import (
    _sanitize_string_input,
    _get_mcp_campaigns,
    _get_mcp_campaign_detail,
    _get_mcp_campaign_audience,
    _get_mcp_campaign_roi,
    _get_mcp_campaign_postmortem,
    _build_postmortem_markdown,
)
from cli.analytics.loyalty import (
    _get_mcp_points,
    _get_mcp_points_at_risk,
    _get_mcp_loyalty,
    _get_mcp_points_daily_trend,
    _get_mcp_loyalty_health,
    _build_loyalty_health_markdown,
)
from cli.analytics.coupons import (
    _get_mcp_coupons,
    _get_mcp_coupon_lift,
    _get_mcp_coupons_by_rule,
    _get_mcp_coupon_anomaly,
)
from cli.analytics.products import (
    _get_mcp_products,
)
from cli.analytics.stores import (
    _get_mcp_stores,
)
from cli.analytics.funnel import (
    _get_mcp_funnel,
    _get_mcp_diagnose_context,
    _build_diagnose_prompt,
)
from cli.analytics.advanced import (
    _ANOMALY_METRICS,
    _get_mcp_ltv,
    _get_mcp_repurchase,
    _get_mcp_repurchase_path,
    _get_mcp_anomaly,
    _get_mcp_canvas,
    _get_mcp_recommend,
    _get_mcp_rfm,
)
from cli.analytics.report import (
    _get_mcp_report,
    _build_report_markdown,
    _write_md_report,
)
from cli.analytics.segments import _mcp_segment_analyze

__all__ = [
    # overview
    "_get_mcp_overview",
    "_get_mcp_report_data",
    "_compute_compare_range",
    "_get_mcp_overview_compare_both",
    "_fmt_cny",
    # customers
    "_get_mcp_customers",
    "_get_mcp_retention",
    "_get_mcp_customer_source",
    "_get_mcp_customer_gender",
    # orders
    "_get_mcp_orders",
    "_get_mcp_order_returns",
    "_get_mcp_orders_tool_payload",
    "_get_mcp_orders_compare_both",
    # campaigns
    "_sanitize_string_input",
    "_get_mcp_campaigns",
    "_get_mcp_campaign_detail",
    "_get_mcp_campaign_audience",
    "_get_mcp_campaign_roi",
    "_get_mcp_campaign_postmortem",
    "_build_postmortem_markdown",
    # loyalty
    "_get_mcp_points",
    "_get_mcp_points_at_risk",
    "_get_mcp_loyalty",
    "_get_mcp_points_daily_trend",
    "_get_mcp_loyalty_health",
    "_build_loyalty_health_markdown",
    # coupons
    "_get_mcp_coupons",
    "_get_mcp_coupon_lift",
    "_get_mcp_coupons_by_rule",
    "_get_mcp_coupon_anomaly",
    # products
    "_get_mcp_products",
    # stores
    "_get_mcp_stores",
    # funnel
    "_get_mcp_funnel",
    "_get_mcp_diagnose_context",
    "_build_diagnose_prompt",
    # advanced
    "_ANOMALY_METRICS",
    "_get_mcp_ltv",
    "_get_mcp_repurchase",
    "_get_mcp_repurchase_path",
    "_get_mcp_anomaly",
    "_get_mcp_canvas",
    "_get_mcp_recommend",
    "_get_mcp_rfm",
    # report
    "_get_mcp_report",
    "_build_report_markdown",
    "_write_md_report",
    # segments
    "_mcp_segment_analyze",
]
