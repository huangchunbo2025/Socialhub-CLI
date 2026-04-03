"""Segment analytics — stable MCP adapter functions for customer segment analysis."""

from __future__ import annotations

import re

from ..api.mcp_client import MCPClient
from ..api.mcp_client import MCPConfig as MCPClientConfig

_GROUP_ID_RE = re.compile(r"^[0-9a-zA-Z_\-]{1,64}$")
_VALID_PERIODS = ("7d", "30d", "90d", "365d")


def _mcp_segment_analyze(config, group_id: str, period: str, max_members: int) -> dict:
    """Analyze a customer segment: metadata, current member count, and member sample.

    Args:
        config: loaded app config (from cli.config.load_config)
        group_id: segment / customer-group ID
        period: analysis window — one of "7d", "30d", "90d", "365d"
        max_members: maximum number of member rows to return (1-1000)

    Returns:
        dict with keys:
            group_id, group_name, group_type, period,
            member_count, members (list), max_members
    """
    if not _GROUP_ID_RE.match(group_id):
        raise ValueError(f"Invalid group_id: {group_id!r}")
    if period not in _VALID_PERIODS:
        period = "30d"
    max_members = max(1, min(int(max_members), 1000))

    mcp_config = MCPClientConfig(
        sse_url=config.mcp.sse_url,
        post_url=config.mcp.post_url,
        tenant_id=config.mcp.tenant_id,
        api_key=config.mcp.api_key,
    )
    database = config.mcp.database or "datanow_demoen"

    with MCPClient(mcp_config) as client:
        client.initialize()

        meta = client.query(
            f"SELECT group_name, group_type, generate_type, create_time, update_time"
            f" FROM t_customer_group"
            f" WHERE id = '{group_id}' AND delete_flag = 0"
            f" LIMIT 1",
            database=database,
        ) or []

        count_rows = client.query(
            f"SELECT COUNT(*) AS member_count"
            f" FROM t_customer_group_member"
            f" WHERE group_id = '{group_id}'",
            database=database,
        ) or []

        members = client.query(
            f"SELECT customer_id, join_time"
            f" FROM t_customer_group_member"
            f" WHERE group_id = '{group_id}'"
            f" ORDER BY join_time DESC"
            f" LIMIT {max_members}",
            database=database,
        ) or []

    group_meta = meta[0] if isinstance(meta, list) and meta else {}
    member_count = 0
    if isinstance(count_rows, list) and count_rows:
        member_count = int(count_rows[0].get("member_count") or 0)

    return {
        "group_id": group_id,
        "group_name": group_meta.get("group_name") or group_id,
        "group_type": group_meta.get("group_type") or "—",
        "period": period,
        "member_count": member_count,
        "members": members if isinstance(members, list) else [],
        "max_members": max_members,
    }
