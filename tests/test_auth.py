"""
tests/test_auth.py

Unit tests for mcp_server/auth.py — API Key 认证中间件。
覆盖：_load_api_key_map、_extract_api_key、APIKeyMiddleware 的认证逻辑。
"""

from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# _load_api_key_map tests
# ---------------------------------------------------------------------------

def test_load_api_key_map_valid():
    """有效的 MCP_API_KEYS 环境变量正确解析为 key->tenant 映射。"""
    with patch.dict(os.environ, {"MCP_API_KEYS": "key1:tenant-a,key2:tenant-b"}, clear=False):
        from mcp_server.auth import _load_api_key_map
        m = _load_api_key_map()
        assert m["key1"] == "tenant-a"
        assert m["key2"] == "tenant-b"
        assert len(m) == 2


def test_load_api_key_map_empty():
    """MCP_API_KEYS 为空时返回空字典。"""
    with patch.dict(os.environ, {"MCP_API_KEYS": ""}, clear=False):
        from mcp_server.auth import _load_api_key_map
        m = _load_api_key_map()
        assert m == {}


def test_load_api_key_map_malformed_pair_skipped():
    """格式错误的条目（缺少冒号）被跳过，合法条目正常加载。"""
    with patch.dict(os.environ, {"MCP_API_KEYS": "badentry,goodkey:tenant-ok"}, clear=False):
        from mcp_server.auth import _load_api_key_map
        m = _load_api_key_map()
        assert "goodkey" in m
        assert "badentry" not in m


def test_load_api_key_map_whitespace_trimmed():
    """key 和 tenant_id 前后空白被去除。"""
    with patch.dict(os.environ, {"MCP_API_KEYS": " key1 : tenant-a "}, clear=False):
        from mcp_server.auth import _load_api_key_map
        m = _load_api_key_map()
        assert "key1" in m
        assert m["key1"] == "tenant-a"


# ---------------------------------------------------------------------------
# _extract_api_key tests
# ---------------------------------------------------------------------------

def _make_request(headers: dict) -> MagicMock:
    """构造带有指定 headers 的 mock Request。"""
    request = MagicMock()
    request.headers = headers
    return request


def test_extract_api_key_from_x_api_key():
    """X-API-Key header 被正确提取。"""
    from mcp_server.auth import _extract_api_key
    req = _make_request({"X-API-Key": "sh_abc123"})
    assert _extract_api_key(req) == "sh_abc123"


def test_extract_api_key_from_bearer():
    """Authorization: Bearer <key> 被正确提取。"""
    from mcp_server.auth import _extract_api_key
    req = _make_request({"Authorization": "Bearer sh_def456", "X-API-Key": ""})
    assert _extract_api_key(req) == "sh_def456"


def test_extract_api_key_x_api_key_takes_priority():
    """X-API-Key 的优先级高于 Authorization: Bearer。"""
    from mcp_server.auth import _extract_api_key
    req = _make_request({
        "X-API-Key": "sh_from_x_api_key",
        "Authorization": "Bearer sh_from_bearer",
    })
    assert _extract_api_key(req) == "sh_from_x_api_key"


def test_extract_api_key_missing_returns_empty():
    """无 API Key 相关 header 时返回空字符串。"""
    from mcp_server.auth import _extract_api_key
    req = _make_request({})
    assert _extract_api_key(req) == ""


def test_extract_api_key_bearer_case_insensitive():
    """Bearer 前缀大小写不敏感。"""
    from mcp_server.auth import _extract_api_key
    req = _make_request({"Authorization": "BEARER sh_xyz789", "X-API-Key": ""})
    assert _extract_api_key(req) == "sh_xyz789"


# ---------------------------------------------------------------------------
# APIKeyMiddleware dispatch tests（使用 Starlette TestClient）
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_key() -> str:
    return "sh_test_valid_key_abc123"


@pytest.fixture
def valid_tenant() -> str:
    return "tenant-test-001"


@pytest.fixture
def app_with_middleware(valid_key, valid_tenant):
    """构造带有 APIKeyMiddleware 的最小 Starlette app 用于测试。"""
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient
    from mcp_server.auth import APIKeyMiddleware

    async def echo(request):
        tenant = getattr(request.state, "tenant_id", None)
        return JSONResponse({"tenant_id": tenant})

    async def health(request):
        return JSONResponse({"status": "ok"})

    app = Starlette(routes=[
        Route("/echo", echo, methods=["POST"]),
        Route("/health", health, methods=["GET"]),
    ])
    middleware = APIKeyMiddleware(app)
    middleware._key_map = {valid_key: valid_tenant}

    client = TestClient(middleware, raise_server_exceptions=True)
    return client, valid_key, valid_tenant


def test_valid_api_key_returns_200(app_with_middleware):
    """有效 API Key 返回 200 并注入 tenant_id。"""
    client, key, tenant = app_with_middleware
    resp = client.post("/echo", headers={"Authorization": f"Bearer {key}"})
    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == tenant


def test_invalid_api_key_returns_401(app_with_middleware):
    """无效 API Key 返回 401。"""
    client, _, _ = app_with_middleware
    resp = client.post("/echo", headers={"Authorization": "Bearer invalid_key_xyz"})
    assert resp.status_code == 401
    assert resp.json()["error"] == "unauthorized"


def test_missing_api_key_returns_401(app_with_middleware):
    """缺少 API Key header 返回 401。"""
    client, _, _ = app_with_middleware
    resp = client.post("/echo")
    assert resp.status_code == 401


def test_health_endpoint_skips_auth(app_with_middleware):
    """/health 端点跳过认证，无 API Key 也返回 200。"""
    client, _, _ = app_with_middleware
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_x_api_key_header_accepted(app_with_middleware):
    """X-API-Key header 格式被接受。"""
    client, key, tenant = app_with_middleware
    resp = client.post("/echo", headers={"X-API-Key": key})
    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == tenant


def test_bearer_token_format_accepted(app_with_middleware):
    """Authorization: Bearer <key> 格式被接受。"""
    client, key, tenant = app_with_middleware
    resp = client.post("/echo", headers={"Authorization": f"Bearer {key}"})
    assert resp.status_code == 200


def test_401_response_contains_reference_id(app_with_middleware):
    """401 响应包含 reference_id 用于排障。"""
    client, _, _ = app_with_middleware
    resp = client.post("/echo", headers={"Authorization": "Bearer wrong_key"})
    assert resp.status_code == 401
    data = resp.json()
    assert "reference_id" in data
    assert len(data["reference_id"]) > 0


# ---------------------------------------------------------------------------
# ContextVar 多请求串行测试 — 验证跨请求上下文隔离（CTO 审查关键安全点）
# ---------------------------------------------------------------------------

@pytest.fixture
def two_tenant_app():
    """构造带有两个租户 API Key 的 Starlette app，用于多请求串行场景测试。"""
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient
    from mcp_server.auth import APIKeyMiddleware

    async def echo(request):
        tenant = getattr(request.state, "tenant_id", None)
        return JSONResponse({"tenant_id": tenant})

    app = Starlette(routes=[Route("/echo", echo, methods=["POST"])])
    middleware = APIKeyMiddleware(app)
    middleware._key_map = {
        "key-tenant-a": "tenant-a",
        "key-tenant-b": "tenant-b",
    }
    client = TestClient(middleware, raise_server_exceptions=True)
    return client


def test_context_var_reset_between_requests(two_tenant_app):
    """串行两次请求：每次请求的 tenant_id 相互独立，不会残留上一次的值。
    验证 _tenant_id_var.reset(token) 在 finally 块中正确执行。
    """
    client = two_tenant_app

    # 第一个请求：tenant-a
    resp1 = client.post("/echo", headers={"Authorization": "Bearer key-tenant-a"})
    assert resp1.status_code == 200
    assert resp1.json()["tenant_id"] == "tenant-a"

    # 第二个请求：tenant-b（不应看到 tenant-a 的残留）
    resp2 = client.post("/echo", headers={"Authorization": "Bearer key-tenant-b"})
    assert resp2.status_code == 200
    assert resp2.json()["tenant_id"] == "tenant-b", (
        "第二个请求应独立读到 tenant-b，而非上一请求残留的 tenant-a"
    )

    # 第三个请求：无效 Key → 401，此时 ContextVar 应为默认空值，不残留 tenant-b
    resp3 = client.post("/echo", headers={"Authorization": "Bearer wrong_key"})
    assert resp3.status_code == 401


def test_alternating_tenants_no_cross_contamination(two_tenant_app):
    """交替使用两个租户 Key，验证每次请求的 tenant_id 都正确对应各自的 Key。"""
    client = two_tenant_app
    for i in range(3):
        r_a = client.post("/echo", headers={"X-API-Key": "key-tenant-a"})
        r_b = client.post("/echo", headers={"X-API-Key": "key-tenant-b"})
        assert r_a.json()["tenant_id"] == "tenant-a", f"Round {i}: tenant-a request got wrong tenant"
        assert r_b.json()["tenant_id"] == "tenant-b", f"Round {i}: tenant-b request got wrong tenant"
