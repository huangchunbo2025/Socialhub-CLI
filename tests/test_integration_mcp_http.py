"""Integration tests for MCP Server — external client perspective.

Simulates an external MCP client (Claude Desktop / M365 Copilot) using only
an API Key. No portal login, no JWT tricks.

Target: http://localhost:8091 (local Docker)
API Key: sh_a2d8db3b7011a3e4a4dbf56b49203abf

Run:
    conda run -n dev pytest tests/test_integration_mcp_http.py -v
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

BASE_URL = "http://localhost:8091"
API_KEY = "sh_a2d8db3b7011a3e4a4dbf56b49203abf"
MCP_URL = "/mcp/"  # trailing slash — /mcp redirects 307


@pytest.fixture(scope="session")
def client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=15)


@pytest.fixture(scope="session")
def auth() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }


def mcp_call(client: httpx.Client, auth: dict, method: str,
             params: dict | None = None, req_id: int = 1) -> dict[str, Any]:
    body: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        body["params"] = params
    resp = client.post(MCP_URL, headers=auth, json=body)
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text[:200]}"
    return resp.json()


# ── T1: 服务健康 ────────────────────────────────────────────────────────────────
class TestHealth:
    def test_health_ok(self, client: httpx.Client) -> None:
        """T1-01: 服务正常运行"""
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_no_auth_required(self, client: httpx.Client) -> None:
        """T1-02: /health 无需 API Key"""
        resp = client.get("/health")
        assert resp.status_code == 200


# ── T2: API Key 认证 ────────────────────────────────────────────────────────────
class TestApiKeyAuth:
    def test_no_key_rejected(self, client: httpx.Client) -> None:
        """T2-01: 无 API Key → 401"""
        resp = client.post(MCP_URL, json={})
        assert resp.status_code == 401

    def test_wrong_key_rejected(self, client: httpx.Client) -> None:
        """T2-02: 错误 API Key → 401"""
        resp = client.post(MCP_URL,
                           headers={"Authorization": "Bearer sh_invalid_000",
                                    "Content-Type": "application/json"},
                           json={})
        assert resp.status_code == 401

    def test_valid_key_accepted(self, client: httpx.Client, auth: dict) -> None:
        """T2-03: 有效 API Key 通过认证"""
        body = mcp_call(client, auth, "initialize",
                        params={"protocolVersion": "2024-11-05",
                                "capabilities": {},
                                "clientInfo": {"name": "pytest", "version": "1.0"}})
        assert "result" in body


# ── T3: MCP 握手 ────────────────────────────────────────────────────────────────
class TestMCPHandshake:
    def test_initialize_returns_server_info(self, client: httpx.Client, auth: dict) -> None:
        """T3-01: initialize 返回服务端信息"""
        body = mcp_call(client, auth, "initialize",
                        params={"protocolVersion": "2024-11-05",
                                "capabilities": {},
                                "clientInfo": {"name": "pytest", "version": "1.0"}})
        result = body["result"]
        assert result["serverInfo"]["name"] == "socialhub-analytics"
        assert "protocolVersion" in result

    def test_tools_list_not_empty(self, client: httpx.Client, auth: dict) -> None:
        """T3-02: tools/list 返回非空工具列表"""
        body = mcp_call(client, auth, "tools/list", params={}, req_id=2)
        tools = body["result"]["tools"]
        assert len(tools) > 0

    def test_each_tool_has_schema(self, client: httpx.Client, auth: dict) -> None:
        """T3-03: 每个工具包含 name / description / inputSchema"""
        body = mcp_call(client, auth, "tools/list", params={}, req_id=3)
        for tool in body["result"]["tools"]:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool


# ── T4: MCP 工具调用 ─────────────────────────────────────────────────────────────
class TestMCPToolCall:
    def test_analytics_overview(self, client: httpx.Client, auth: dict) -> None:
        """T4-01: analytics_overview — 有响应（无凭证时返回业务错误，不崩溃）"""
        body = mcp_call(client, auth, "tools/call",
                        params={"name": "analytics_overview", "arguments": {}},
                        req_id=10)
        content = body["result"]["content"]
        assert len(content) > 0
        assert isinstance(content[0]["text"], str)

    def test_analytics_orders(self, client: httpx.Client, auth: dict) -> None:
        """T4-02: analytics_orders"""
        body = mcp_call(client, auth, "tools/call",
                        params={"name": "analytics_orders", "arguments": {}},
                        req_id=11)
        assert "result" in body

    def test_analytics_retention(self, client: httpx.Client, auth: dict) -> None:
        """T4-03: analytics_retention"""
        body = mcp_call(client, auth, "tools/call",
                        params={"name": "analytics_retention", "arguments": {}},
                        req_id=12)
        assert "result" in body

    def test_analytics_rfm(self, client: httpx.Client, auth: dict) -> None:
        """T4-04: analytics_rfm"""
        body = mcp_call(client, auth, "tools/call",
                        params={"name": "analytics_rfm", "arguments": {}},
                        req_id=13)
        assert "result" in body

    def test_analytics_campaigns(self, client: httpx.Client, auth: dict) -> None:
        """T4-05: analytics_campaigns"""
        body = mcp_call(client, auth, "tools/call",
                        params={"name": "analytics_campaigns", "arguments": {}},
                        req_id=14)
        assert "result" in body

    def test_unknown_tool_no_crash(self, client: httpx.Client, auth: dict) -> None:
        """T4-06: 调用不存在工具 → 有响应，不崩溃"""
        body = mcp_call(client, auth, "tools/call",
                        params={"name": "nonexistent_xyz", "arguments": {}},
                        req_id=15)
        assert "result" in body or "error" in body
