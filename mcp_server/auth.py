"""
mcp_server/auth.py

API Key 认证中间件。
- 从 Authorization: Bearer <key> 或 X-API-Key: <key> 提取 API Key
- 查映射表得到 tenant_id，注入 request.state.tenant_id 和 ContextVar
- /health 端点不需要认证（跳过）
- 认证失败返回 RFC 7807 风格 JSON 错误响应

环境变量：
  MCP_API_KEYS=sh_abc123:tenant-acme-001,sh_def456:tenant-beta-002
  （每个 key 和 tenant_id 用冒号分隔，多组用逗号分隔）
"""

from __future__ import annotations

import hmac
import logging
import os
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# ContextVar：在 executor 线程中可读取当前请求的 tenant_id
# 在 auth 中间件的 dispatch() 中写入，在 call_tool 的 _run() 闭包中通过 _get_tenant_id() 读取
_tenant_id_var: ContextVar[str] = ContextVar("tenant_id", default="")


def _get_tenant_id() -> str:
    """从当前请求上下文读取 tenant_id（供 call_tool handler 调用）。"""
    return _tenant_id_var.get()


def _load_api_key_map() -> dict[str, str]:
    """
    从环境变量 MCP_API_KEYS 加载 API Key -> tenant_id 映射。
    格式：sh_abc123:tenant-acme-001,sh_def456:tenant-beta-002
    启动时调用一次，结果在进程生命周期内缓存（Render 重部署会重载）。
    """
    raw = os.getenv("MCP_API_KEYS", "").strip()
    if not raw:
        logger.warning("MCP_API_KEYS 未设置，HTTP 模式下所有请求将被拒绝")
        return {}

    mapping: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if ":" not in pair:
            logger.error("MCP_API_KEYS 格式错误，跳过无效条目: %s", pair)
            continue
        key, _, tenant_id = pair.partition(":")
        key = key.strip()
        tenant_id = tenant_id.strip()
        if not key or not tenant_id:
            logger.error("MCP_API_KEYS 含空 key 或 tenant_id，跳过: %s", pair)
            continue
        mapping[key] = tenant_id
        logger.info("已加载 API Key 映射: key_prefix=%s... tenant=%s", key[:8], tenant_id)

    logger.info("API Key 映射加载完成，共 %d 个租户", len(mapping))
    return mapping


# 进程级映射表，模块首次导入时加载
_API_KEY_MAP: dict[str, str] = _load_api_key_map()

# 不需要认证的路径白名单
_AUTH_EXEMPT_PATHS: frozenset[str] = frozenset({"/health", "/health/"})


def _extract_api_key(request: Request) -> str:
    """
    从请求提取 API Key。
    优先级：X-API-Key header > Authorization: Bearer <key>
    两种格式均支持，以兼容 M365 ApiKeyPluginVault 不同注入方式。
    """
    x_api_key = request.headers.get("X-API-Key", "").strip()
    if x_api_key:
        return x_api_key

    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()

    return ""


class APIKeyMiddleware(BaseHTTPMiddleware):
    """
    Starlette 中间件：API Key 认证 + tenant_id 注入。

    成功：在 request.state.tenant_id 和 ContextVar _tenant_id_var 中注入 tenant_id
    失败：返回 401 JSON 响应，不调用 call_next
    /health：直接放行，不检查 Key
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        # 使用进程级映射表（测试中可直接替换 middleware._key_map）
        self._key_map = _API_KEY_MAP

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 白名单路径跳过认证
        if request.url.path in _AUTH_EXEMPT_PATHS:
            return await call_next(request)

        api_key = _extract_api_key(request)

        # 使用 hmac.compare_digest 防止时序攻击
        tenant_id: str | None = None
        for stored_key, tid in self._key_map.items():
            if api_key and hmac.compare_digest(api_key, stored_key):
                tenant_id = tid
                break

        if tenant_id is None:
            ref_id = str(uuid.uuid4())
            logger.warning(
                "API Key 认证失败: path=%s ref_id=%s key_prefix=%s",
                request.url.path,
                ref_id,
                api_key[:8] if api_key else "<empty>",
            )
            return JSONResponse(
                status_code=401,
                content={
                    "error": "unauthorized",
                    "message": "Invalid or missing API Key",
                    "reference_id": ref_id,
                },
            )

        # 注入 tenant_id 到请求 state（同步代码可读）和 ContextVar（executor 线程可读）
        request.state.tenant_id = tenant_id
        logger.info(
            "API Key authentication succeeded: path=%s tenant=%s key_prefix=%s",
            request.url.path,
            tenant_id,
            api_key[:8] if api_key else "<empty>",
        )
        token = _tenant_id_var.set(tenant_id)

        try:
            response = await call_next(request)
        finally:
            # 请求结束后重置 ContextVar，防止线程池复用时值残留（防止跨租户数据污染）
            _tenant_id_var.reset(token)

        return response
