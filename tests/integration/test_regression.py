"""TC-12 ~ TC-15: 其他模块回归测试.

TC-12  MCP Server /health 返回 200
TC-13  MCP Server 无 API Key 返回 401
TC-14  MCP Server 有效 API Key 建立 MCP 会话（initialize 成功）
TC-15  Runner.sync_all() 多租户并发无崩溃
"""

from __future__ import annotations

import asyncio
import json
import os

import asyncpg
import httpx
import pytest

from emarsys_sync.runner import Runner
from mcp_server.sync.models import TenantSyncConfig

_MCP_URL = os.environ.get("MCP_SERVER_URL", "http://mcp-server:8090")
_API_KEY = os.environ.get("MCP_API_KEYS", "").split(",")[0].split(":")[0]


# ---------------------------------------------------------------------------
# TC-12: MCP Server 健康检查
# ---------------------------------------------------------------------------


def test_tc12_mcp_server_health() -> None:
    """MCP Server /health 返回 200."""
    try:
        resp = httpx.get(f"{_MCP_URL}/health", timeout=10)
    except httpx.ConnectError:
        pytest.skip(f"MCP Server 未启动（{_MCP_URL}）")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# TC-13: 无 API Key 返回 401
# ---------------------------------------------------------------------------


def test_tc13_mcp_server_rejects_no_auth() -> None:
    """MCP Server POST /mcp 无 API Key 返回 401."""
    try:
        resp = httpx.post(f"{_MCP_URL}/mcp", timeout=10)
    except httpx.ConnectError:
        pytest.skip(f"MCP Server 未启动（{_MCP_URL}）")
    assert resp.status_code == 401, f"期望 401，实际 {resp.status_code}"


# ---------------------------------------------------------------------------
# TC-14: 有效 API Key 初始化 MCP 会话
# ---------------------------------------------------------------------------


def test_tc14_mcp_server_initialize_with_valid_key() -> None:
    """有效 API Key 发送 MCP initialize，返回 200 且含 serverInfo."""
    if not _API_KEY:
        pytest.skip("MCP_API_KEYS 未设置")

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "integration-test", "version": "0.0.1"},
        },
    }
    try:
        resp = httpx.post(
            f"{_MCP_URL}/mcp",
            headers={
                "X-API-Key": _API_KEY,
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            content=json.dumps(payload),
            timeout=15,
            follow_redirects=True,
        )
    except httpx.ConnectError:
        pytest.skip(f"MCP Server 未启动（{_MCP_URL}）")

    assert resp.status_code == 200, f"期望 200，实际 {resp.status_code}: {resp.text[:200]}"
    body = resp.json()
    assert "result" in body or "serverInfo" in str(body), f"响应缺少 serverInfo: {body}"


# ---------------------------------------------------------------------------
# TC-15: Runner.sync_all() 多租户并发
# ---------------------------------------------------------------------------


async def test_tc15_runner_sync_all_concurrent(pg_pool: asyncpg.Pool) -> None:
    """Runner.sync_all() 多租户并发执行不崩溃，返回 TenantResult 列表."""
    runner = Runner(pg_pool=pg_pool, max_concurrent=2, batch_size=100)
    results = await runner.sync_all()

    # 可以没有租户（空列表），但不能抛异常
    assert isinstance(results, list), "sync_all() 应返回 list"
    for r in results:
        # 每个租户结果必须有 tenant_id，失败可以有但不能是 Exception 对象
        assert hasattr(r, "tenant_id"), f"返回结果不是 TenantResult: {r}"
