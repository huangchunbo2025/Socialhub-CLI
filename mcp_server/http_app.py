"""
mcp_server/http_app.py

Starlette ASGI app 组装，供 HTTP Streamable Transport 使用。
路由：
  GET  /health  — 健康检查（无需认证，Render 健康探针）
  POST /mcp     — MCP Streamable HTTP Transport 端点（需 API Key 认证）

中间件顺序（从外到内，即请求处理顺序）：
  1. CORSMiddleware   — 处理 OPTIONS preflight，添加 CORS 响应头（最外层，确保 preflight 不被 401 拦截）
  2. APIKeyMiddleware — 验证 Bearer Token / X-API-Key，注入 tenant_id
  3. Starlette Router — 路由到 /health 或 MCP session manager

依赖：mcp >= 1.8.0, starlette, uvicorn（启动时注入）
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import logging
import os
import time
import uuid
from datetime import timezone

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route

from pathlib import Path

from starlette.responses import HTMLResponse

from mcp_server.auth import APIKeyMiddleware
from mcp_server.db import close_db, init_db
from mcp_server.routers.api_keys import create_api_key, list_api_keys, revoke_api_key
from mcp_server.routers.auth_portal import login
from mcp_server.routers.credentials import delete_credentials, get_credentials, upload_credentials
from mcp_server.routers.mcp_credentials import (
    get_mcp_credentials, upsert_mcp_credentials, delete_mcp_credentials,
)
from mcp_server.server import create_server

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log inbound HTTP requests so Render logs show whether Copilot reached /mcp."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        started = time.time()
        logger.info(
            "HTTP request started: id=%s method=%s path=%s user_agent=%s",
            request_id,
            request.method,
            request.url.path,
            request.headers.get("user-agent", "-"),
        )
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "HTTP request failed: id=%s method=%s path=%s elapsed_ms=%s",
                request_id,
                request.method,
                request.url.path,
                int((time.time() - started) * 1000),
            )
            raise

        response.headers["X-Request-Id"] = request_id
        logger.info(
            "HTTP request finished: id=%s method=%s path=%s status=%s elapsed_ms=%s",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            int((time.time() - started) * 1000),
        )
        return response

# ---------------------------------------------------------------------------
# CORS 配置
# ---------------------------------------------------------------------------

_RENDER_DOMAIN = os.getenv("RENDER_EXTERNAL_HOSTNAME", "socialhub-mcp.onrender.com")

ALLOWED_ORIGINS = [
    # 本地开发
    "http://localhost:3000",
    "http://localhost:8080",
    # MCP Inspector 官方调试工具
    "https://inspector.modelcontextprotocol.io",
]

# 生产环境额外允许的 origins（通过环境变量扩展，逗号分隔）
_extra_origins = os.getenv("ALLOWED_ORIGINS", "").strip()
if _extra_origins:
    ALLOWED_ORIGINS.extend([o.strip() for o in _extra_origins.split(",") if o.strip()])


# ---------------------------------------------------------------------------
# /health 端点
# ---------------------------------------------------------------------------

async def health(request: Request) -> JSONResponse:
    """
    轻量级存活检查端点。
    - 不需要认证（在 APIKeyMiddleware 白名单中）
    - 响应时间 < 100ms（不访问上游）
    - Render 健康探针使用此端点（healthCheckPath: /health）

    HTTP 状态码：
    - 200 + status:"ok"      — 完全就绪
    - 200 + status:"degraded" — analytics 仍在加载（冷启动正常过渡，不触发 Render 回滚）
    - 503 + status:"down"    — API Key 未配置，服务不可用
    """
    from mcp_server.server import _analytics_ready
    from mcp_server.auth import _API_KEY_MAP

    checks: dict[str, str] = {}

    # 检查 analytics 是否已加载
    checks["analytics"] = "ok" if _analytics_ready.is_set() else "loading"

    # 检查 API Key 配置
    checks["config"] = "ok" if _API_KEY_MAP else "error"

    # 整体状态
    if all(v == "ok" for v in checks.values()):
        status = "ok"
        http_code = 200
    elif checks.get("config") == "error":
        # 无 API Key 配置，服务不可用
        status = "down"
        http_code = 503
    else:
        # analytics 仍在加载（冷启动正常过渡状态）
        status = "degraded"
        http_code = 200

    return JSONResponse(
        status_code=http_code,
        content={
            "status": status,
            "version": "1.0.0",
            "timestamp": datetime.datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "checks": checks,
        },
    )


_STATIC_DIR = Path(__file__).parent / "static"


async def ui(request: Request) -> HTMLResponse:
    """GET /ui — serve customer portal HTML."""
    html_path = _STATIC_DIR / "ui.html"
    if not html_path.exists():
        return HTMLResponse("<h1>UI not found</h1>", status_code=404)
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# MCP Session Manager（进程级单例）
# ---------------------------------------------------------------------------

def _build_session_manager() -> StreamableHTTPSessionManager:
    """
    构建 StreamableHTTPSessionManager。
    stateless=True：每个 POST /mcp 请求创建独立 ServerSession，
    请求结束后销毁，无跨请求状态，完全匹配 M365 Copilot 无状态工具调用模型。
    """
    mcp_server_instance = create_server()
    return StreamableHTTPSessionManager(
        app=mcp_server_instance,
        stateless=True,      # M365 Copilot 每次工具调用是独立请求，无需持久 session
        json_response=True,  # 简单请求返回 JSON 而非 SSE 流，减少客户端复杂度
    )


_session_manager = _build_session_manager()


# ---------------------------------------------------------------------------
# Lifespan：管理 session manager 和 analytics 预加载
# ---------------------------------------------------------------------------

@contextlib.asynccontextmanager
async def lifespan(app: Starlette):  # type: ignore[type-arg]
    """
    启动时：
    1. 探测上游 MCP 连通性（失败不阻断启动，只记日志）
    2. 启动 analytics 预加载线程（与 stdio 模式一致）
    3. 启动 StreamableHTTPSessionManager

    关闭时：清理 session manager 资源

    注意：probe_upstream_mcp() 是同步阻塞调用，必须通过 asyncio.to_thread() 卸载到线程池，
    否则会阻塞事件循环最长 15 秒，可能导致 Render 健康探针超时触发部署回滚。
    """
    import threading
    from mcp_server.server import _load_analytics, probe_upstream_mcp

    # 启动时校验关键配置
    if not os.getenv("CREDENTIAL_ENCRYPT_KEY"):
        logger.warning(
            "CREDENTIAL_ENCRYPT_KEY is not set — credential encryption/decryption will fail at runtime. "
            "Generate a key with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )

    # 上游健康检查：通过 asyncio.to_thread 避免阻塞事件循环（同步 HTTP 请求最长 15s）
    try:
        ok, message = await asyncio.to_thread(probe_upstream_mcp)
        if ok:
            logger.info("Upstream MCP probe succeeded: %s", message)
        else:
            logger.warning("Upstream MCP probe failed (non-fatal): %s", message)
    except Exception as e:
        logger.warning("Upstream MCP probe raised exception (non-fatal): %s", e)

    # 预加载重型 analytics 依赖（pandas 等），避免首次工具调用时延迟
    threading.Thread(target=_load_analytics, daemon=True).start()
    logger.info("Analytics preload thread started")

    # 初始化数据库
    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning("Database init failed (non-fatal): %s", e)

    # 启动 MCP session manager
    async with _session_manager.run():
        logger.info("StreamableHTTPSessionManager started (stateless=True)")
        yield

    await close_db()
    logger.info("HTTP MCP app shutting down")


# ---------------------------------------------------------------------------
# Starlette App 组装
# ---------------------------------------------------------------------------

_app = Starlette(
    routes=[
        Route("/health", health, methods=["GET"]),
        Route("/ui", ui, methods=["GET"]),
        Route("/auth/login", login, methods=["POST"]),
        Route("/credentials/mcp", get_mcp_credentials, methods=["GET"]),
        Route("/credentials/mcp", upsert_mcp_credentials, methods=["PUT"]),
        Route("/credentials/mcp", delete_mcp_credentials, methods=["DELETE"]),
        Route("/credentials/bigquery", upload_credentials, methods=["POST"]),
        Route("/credentials/bigquery", get_credentials, methods=["GET"]),
        Route("/credentials/bigquery", delete_credentials, methods=["DELETE"]),
        Route("/api-keys", create_api_key, methods=["POST"]),
        Route("/api-keys", list_api_keys, methods=["GET"]),
        Route("/api-keys/{key_id}", revoke_api_key, methods=["DELETE"]),
        Mount("/mcp", app=_session_manager.handle_request),
    ],
    lifespan=lifespan,
)

# 中间件包裹顺序（add_middleware 是从内到外，越后 add 越先执行）
# 执行顺序：CORS（最外层，先执行）→ APIKey → Starlette Router
# CORS 必须在 APIKey 之外，确保 OPTIONS preflight 不被 401 拦截
_app.add_middleware(RequestLoggingMiddleware)
_app.add_middleware(APIKeyMiddleware)
_app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Accept",
        "Authorization",
        "X-API-Key",
        "Mcp-Session-Id",
        "mcp-session-id",
        "mcp-protocol-version",
        "Last-Event-ID",
    ],
    expose_headers=["Mcp-Session-Id", "mcp-session-id"],
    max_age=86400,
    allow_credentials=False,
)

# 导出给 uvicorn 使用
app = _app
