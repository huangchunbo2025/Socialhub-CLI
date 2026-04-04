"""Shared utilities for analytics sub-modules."""

import re
from contextlib import contextmanager

from rich.console import Console

from ..api.mcp_client import MCPClient
from ..config import load_config

console = Console()

# =============================================================================
# SQL Trace — monkey-patch MCPClient.query to capture SQL for --show-sql flag
# =============================================================================


@contextmanager
def _sql_trace_ctx():
    """Capture every MCPClient.query call within this context.

    Yields a list that accumulates {sql, database} entries.
    Restores the original method on exit (thread-safe for CLI use).
    """
    log: list[dict] = []
    _orig = MCPClient.query

    def _patched(self, sql: str, **kwargs):
        log.append({"sql": sql.strip(), "database": kwargs.get("database", "—")})
        return _orig(self, sql, **kwargs)

    MCPClient.query = _patched
    try:
        yield log
    finally:
        MCPClient.query = _orig


def _print_sql_trace(log: list[dict]) -> None:
    """Print captured SQL queries in a readable format."""
    from rich.syntax import Syntax

    if not log:
        console.print("[dim]No SQL queries captured.[/dim]")
        return

    console.print("\n[bold dim]── SQL Trace (" + str(len(log)) + " queries) ──────────────────────[/bold dim]")
    for i, entry in enumerate(log, 1):
        console.print(f"\n[dim]Query {i}  database={entry['database']}[/dim]")
        console.print(Syntax(entry["sql"], "sql", theme="monokai", word_wrap=True))


# =============================================================================
# SECURITY: Input Validation & SQL Safety
# =============================================================================

# Whitelist of valid period values
VALID_PERIODS = frozenset({"all", "today", "7d", "30d", "90d", "365d"})

# Whitelist of valid 'by' grouping options
VALID_GROUP_BY = frozenset({"channel", "province", "store", "date", "month", "product"})


def _validate_period(period: str) -> str:
    """Validate period parameter against whitelist.

    Returns the validated period or raises ValueError.
    """
    if period not in VALID_PERIODS:
        raise ValueError(f"Invalid period '{period}'. Must be one of: {', '.join(sorted(VALID_PERIODS))}")
    return period


def _validate_group_by(by: str) -> str:
    """Validate 'by' grouping parameter against whitelist."""
    if by and by not in VALID_GROUP_BY:
        raise ValueError(f"Invalid grouping '{by}'. Must be one of: {', '.join(sorted(VALID_GROUP_BY))}")
    return by


def _compute_date_range(period: str):
    """Compute safe date range from validated period.

    Returns (start_date, end_date) tuple. start_date is None for 'all' period.
    Dates are Python date objects, safe for SQL interpolation.
    """
    from datetime import datetime, timedelta, timezone

    period = _validate_period(period)
    today = datetime.now(timezone.utc).date()

    if period == "all":
        return None, today

    days_map = {"today": 1, "7d": 7, "30d": 30, "90d": 90, "365d": 365}
    days = days_map.get(period, 365)
    start_date = today - timedelta(days=days)

    return start_date, today


def _mcp_query_timeout(period: str, grouped: bool = False) -> int:
    """Choose a safer MCP query timeout for larger analytics windows."""
    period = _validate_period(period)

    if period == "365d":
        return 180 if grouped else 120
    if period == "90d":
        return 120 if grouped else 90
    if period == "30d":
        return 90 if grouped else 60
    return 60


def _safe_date_filter(column: str, start_date, operator: str = ">=") -> str:
    """Build a safe SQL date filter clause.

    Args:
        column: Column name (must be alphanumeric/underscore only)
        start_date: Date object or None
        operator: Comparison operator (only >= and > allowed)

    Returns:
        SQL WHERE clause or empty string if no filter needed
    """
    if start_date is None:
        return ""

    # Validate column name (alphanumeric/underscore, optionally prefixed with table alias)
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)?$', column):
        raise ValueError(f"Invalid column name: {column}")

    # Validate operator
    if operator not in (">=", ">", "<=", "<", "="):
        raise ValueError(f"Invalid operator: {operator}")

    # Format date safely (Python date object -> ISO format string)
    date_str = start_date.isoformat() if hasattr(start_date, 'isoformat') else str(start_date)

    # Validate date format (YYYY-MM-DD)
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        raise ValueError(f"Invalid date format: {date_str}")

    return f"WHERE {column} {operator} '{date_str}'"


def _safe_date_between(column: str, start_date, end_date) -> str:
    """Build a safe SQL BETWEEN clause for dates.

    Args:
        column: Column name (must be alphanumeric/underscore only)
        start_date: Start date object
        end_date: End date object

    Returns:
        SQL WHERE clause with BETWEEN
    """
    # Validate column name (alphanumeric/underscore, optionally prefixed with table alias)
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)?$', column):
        raise ValueError(f"Invalid column name: {column}")

    # Format dates safely
    start_str = start_date.isoformat() if hasattr(start_date, 'isoformat') else str(start_date)
    end_str = end_date.isoformat() if hasattr(end_date, 'isoformat') else str(end_date)

    # Validate date formats
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', start_str):
        raise ValueError(f"Invalid start date format: {start_str}")
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', end_str):
        raise ValueError(f"Invalid end date format: {end_str}")

    return f"WHERE {column} BETWEEN '{start_str}' AND '{end_str}'"


def _validate_days_list(days_list: list) -> list:
    """Validate a list of day periods for retention analysis."""
    validated = []
    for d in days_list:
        if isinstance(d, int) and 1 <= d <= 365:
            validated.append(d)
        elif isinstance(d, str) and d.isdigit():
            val = int(d)
            if 1 <= val <= 365:
                validated.append(val)
    return validated


def get_data_source():
    """Get data source based on config mode."""
    config = load_config()
    return config.mode
