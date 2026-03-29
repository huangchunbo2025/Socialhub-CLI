> CTO 审查: 有条件批准 — 2026-03-29

# SocialHub × M365 Copilot Declarative Agent — 技术设计方案

> 文档版本：1.0
> 日期：2026-03-29
> 作者：架构设计
> 依据：CLAUDE.md / 05-prd.md / 01-research/（project-status、mcp-http-transport、deployment）
> 状态：经过 3 轮自我对抗迭代后的最终版本

---

## 一、与现有架构的映射

### PRD 功能点 → 现有代码模块

| PRD 需求 | 现有模块 | 映射关系 | 改动类型 |
|---|---|---|---|
| HTTP Streamable Transport | `mcp_server/__main__.py` | 入口添加 `--transport http` 分支 | 修改 |
| API Key 认证 + tenant_id 注入 | 无对应模块 | 全新创建 `mcp_server/auth.py` | 新建 |
| Starlette ASGI App 组装 | 无对应模块 | 全新创建 `mcp_server/http_app.py` | 新建 |
| `_cache_key()` 加 tenant_id | `mcp_server/server.py:51` | 函数签名增加 `tenant_id` 参数 | 修改（安全必改） |
| 8 个精选工具的 Schema | `mcp_server/server.py` 中的 `_HANDLERS` + `TOOLS` | 不修改现有工具，新建工具 Schema 声明文件 | 新建（manifest 文件） |
| /health 端点 | 无对应模块 | 在 `http_app.py` 中实现 | 新建（在 http_app.py 内） |
| Teams App 包（manifest/plugin） | 无对应目录 | 新建 `build/m365-agent/` 目录 | 新建 |
| Render 部署配置 | 无 `render.yaml` | 新建仓库根目录 `render.yaml` | 新建 |
| `pyproject.toml` HTTP 依赖声明 | `pyproject.toml` | 新增 `[http]` optional-dep | 修改 |

### 现有机制在 HTTP 模式下的兼容性确认

| 机制 | 位置 | HTTP 模式状态 | 说明 |
|---|---|---|---|
| `_run_with_cache()` | `server.py:62` | 完全兼容 | 基于 `threading.Lock` + 内存 dict，与传输层无关 |
| `_analytics_ready` Event | `server.py:41` | 完全兼容 | daemon thread 在 `__main__.py` 启动时触发，与传输层无关 |
| `loop.run_in_executor()` | `server.py:938` | 完全兼容 | 同步 handler 推入线程池，避免阻塞 ASGI event loop |
| `probe_upstream_mcp()` | `server.py` | 完全兼容 | HTTP 模式启动前调用，仅记录日志，不阻断启动 |
| `_HANDLERS` dispatch table | `server.py:869` | 完全兼容 | 纯函数映射，零传输层依赖 |
| `create_server()` | `server.py:907` | 完全兼容 | 返回标准 `mcp.server.Server` 实例 |
| `_get_config()` 全局单例 | `server.py:31` | **需要改造** | HTTP 多租户场景需从请求上下文读 tenant_id，不能依赖全局 config |

---

## 二、改动清单（精确到文件级别）

### 新建文件

| 文件 | 职责 | 优先级 | PRD 追溯 |
|---|---|---|---|
| `mcp_server/auth.py` | API Key → tenant_id 映射；Bearer token 解析；`APIKeyMiddleware` Starlette 中间件 | P0 | PRD §3.4、§6.3、验收 T4 |
| `mcp_server/http_app.py` | Starlette ASGI app 组装；路由（/mcp、/health）；中间件顺序（CORS → Auth → MCP） | P0 | PRD §3.1、§5.1、验收 T1 |
| `build/m365-agent/manifest.json` | Teams App 包清单文件，声明 Declarative Agent 引用 | P0 | PRD §3.2、验收 T2 |
| `build/m365-agent/declarativeAgent.json` | Agent 名称、Instructions、Conversation Starters、actions 配置 | P0 | PRD §3.2.1、验收 T2 |
| `build/m365-agent/plugin.json` | MCP Server URL、auth 配置（MVP: ApiKeyPluginVault；GA: OAuthPluginVault） | P0 | PRD §3.4、验收 T2 |
| `build/m365-agent/mcp-tools.json` | 8 个精选工具的完整 inputSchema（M365 Copilot tool routing 使用） | P0 | PRD §3.1、§6.4（≤3000 tokens）、验收 T2 |
| `render.yaml` | Render Blueprint 部署配置（Starter 层，/health 探针，环境变量声明） | P0 | PRD §7（Render Starter 部署）、验收 T1 |
| `tests/test_auth.py` | `auth.py` 单元测试（合法 key、非法 key、/health 跳过认证） | P1 | PRD 验收 T4 |
| `tests/test_cache_isolation.py` | `_cache_key()` 含 tenant_id 隔离的单元测试 | P0 | PRD §6.3、验收 T1（最后一条） |

### 修改文件

| 文件 | 修改内容 | PRD 追溯 |
|---|---|---|
| `mcp_server/__main__.py` | 新增 `argparse` 参数（`--transport [stdio\|http]`、`--port`）；新增 HTTP 分支（导入 `http_app`，启动 `uvicorn`）；HTTP 模式下 `StreamHandler` 改用 `stderr` 避免污染响应 | PRD §7（HTTP Transport 必须包含） |
| `mcp_server/server.py` | `_cache_key()` 增加 `tenant_id` 参数；`_run_with_cache()` 传入 `tenant_id`；`call_tool()` 从请求上下文提取 `tenant_id` | PRD §6.3（安全必改项）、验收 T1 |
| `pyproject.toml` | 新增 `[project.optional-dependencies]` 中的 `http` 条目（`uvicorn>=0.30.0`）；将 `mcp>=1.0.0` 升级为 `mcp>=1.8.0` | 技术依赖更新 |

### 不动文件

| 文件 | 不动原因 |
|---|---|
| `mcp_server/server.py` 中的 `_HANDLERS`、`TOOLS`、所有 `_handle_*` 函数 | 传输层与工具处理层完全解耦，36+ handler 零修改；`call_tool()` 继续用 `_HANDLERS.get(name)` dispatch（满足 CLAUDE.md 硬约束） |
| `cli/` 整个包 | CLI 功能与本次 M365 集成无关 |
| `skills-store/` | 独立服务，无关 |
| `frontend/` | 无关 |
| `docs/` | CLAUDE.md 硬约束：`docs/` 目录冻结，生产 GitHub Pages，任何情况下不得修改 |

---

## 三、关键设计决策

### 决策 1：传输层选择 — HTTP Streamable vs 旧版 SSE

**选择**：HTTP Streamable Transport（MCP spec 2025-03-26）

**理由**：
- 旧版 SSE transport（2024-11-05）已在 MCP 规范中被明确废弃（deprecated），M365 Copilot 官方示例使用 Streamable HTTP
- 单端点 `/mcp` 设计简化 CORS 配置，减少 Render 路由复杂度
- `stateless_http=True` 完全匹配 M365 Copilot 无状态工具调用模型
- `mcp 1.26.0` 已在环境中安装，`StreamableHTTPSessionManager` 开箱即用

**放弃的替代方案**：旧版 `SseServerTransport`（`/sse` + `/messages` 双端点）——已废弃，不投资于废弃接口

---

### 决策 2：stateless_http=True

**选择**：`stateless_http=True`（每请求独立 transport，无 Session ID）

**理由**：
- M365 Copilot 每次工具调用是独立 HTTP 请求，不需要跨请求维持 MCP session 状态
- Render 部署可安全使用单 worker（`--workers 1`），进程级内存缓存（`_run_with_cache`）在 worker 内共享，15 分钟 TTL 持续有效
- stateless 模式与 `_run_with_cache()` 的线程安全缓存完全兼容——请求级 session 无状态，但进程级缓存有状态，两层不冲突
- 若未来扩容到多 worker，stateless 模式支持水平扩展，无需引入 Redis

**放弃的替代方案**：stateful 模式——需要 sticky session，多 worker 时 session 跨 worker 查找失败；Free tier 冷启动后 session 全丢失

---

### 决策 3：认证方案 — Starlette BaseHTTPMiddleware vs mcp.server.auth BearerAuthBackend

**选择**：`Starlette BaseHTTPMiddleware`（自定义 `APIKeyMiddleware`）

**理由**：
- `mcp.server.auth.BearerAuthBackend` 设计用于 JWT/OAuth token 验证，需要 `TokenVerifier` 接口和 `AuthenticationMiddleware`，对 API Key 场景偏重
- `BaseHTTPMiddleware` 实现更简洁，API Key 验证只需 `hmac.compare_digest()`，无额外依赖
- 中间件可直接在 `dispatch()` 中注入 `request.state.tenant_id`，工具层通过 `contextvars.ContextVar` 传递，清晰可测
- `/health` 端点跳过认证在 `dispatch()` 中一行判断即可

**放弃的替代方案**：
- `mcp.server.auth.BearerAuthBackend` — 为 JWT OAuth 场景设计，当前 MVP API Key 场景过度复杂；GA 阶段切换 Entra OAuth 时再引入
- 工具层内部验证（`get_http_request()` 依赖注入）— 违反关注点分离，每个 handler 都要重复验证逻辑

---

### 决策 4：tenant_id 传递机制 — contextvars vs threading.local

**选择**：`contextvars.ContextVar`（Python 3.7+ 标准库）

**理由**：
- ASGI 框架（Starlette/anyio）在 async 任务树中正确传播 `contextvars`，每个异步请求的 ContextVar 值独立
- `_run_with_cache()` 运行在 `loop.run_in_executor(None, _run)` 的线程池中，`asyncio` 会将调用者的 context 复制到 executor 线程，`ContextVar` 在 executor 线程中可读
- `threading.local` 在 executor 线程池中行为不确定（线程可能被重用，导致 tenant_id 串用）

**放弃的替代方案**：`threading.local` — 线程池场景下线程复用导致值污染风险；传参改造（修改所有 handler 签名）— 改动量大，违反最小改动原则

---

### 决策 5：8 工具精选策略

**选择**：仅在 `mcp-tools.json` 中声明 8 个工具，MCP Server 的 36+ 工具全部保留但不对 M365 暴露

**理由**：
- PRD §6.4：工具 Schema 总 token ≤ 3,000 tokens，8 个工具可控制在此预算内
- M365 Copilot 工具路由基于 `mcp-tools.json` 中的描述进行语义匹配，工具数量过多导致路由混乱和 LLM 上下文浪费
- `plugin.json` 中 `functions` 字段引用 `mcp-tools.json`，只有声明的工具会被 M365 Copilot 调用

**工具名称映射**（PRD 工具名 → server.py 现有 `_HANDLERS` key）：

| PRD 工具名 | server.py handler key | 映射关系 |
|---|---|---|
| `get_customer_overview` | `analytics_overview` | 语义对应，Schema 声明使用 PRD 工具名 |
| `get_retention_analysis` | `analytics_retention` | 语义对应 |
| `get_rfm_analysis` | `analytics_rfm` | 语义对应 |
| `get_customer_list` | `analytics_customers` | 语义对应 |
| `get_anomaly_detection` | `analytics_anomaly` | 语义对应 |
| `get_order_trends` | `analytics_orders` | 语义对应 |
| `get_ltv_analysis` | `analytics_ltv` | 语义对应 |
| `get_campaign_analysis` | `analytics_campaigns` | 语义对应 |

**重要说明**：`mcp-tools.json` 中的工具名必须与 MCP Server `_HANDLERS` dict 的 key 完全一致，否则 M365 Copilot 发出的 `tools/call` 请求会因 `_HANDLERS.get(name)` 返回 `None` 而失败。因此使用 server.py 现有 key 名称（`analytics_*`），在 `description` 字段中使用 PRD 中用户友好的描述文案。

---

### 决策 6：环境变量格式 — API Key 多租户映射

**选择**：`MCP_API_KEYS` 单变量，`key:tenant_id` 逗号分隔格式

**理由**：
- EA 阶段租户数 ≤ 20，单变量管理足够
- 比独立变量（`MCP_API_KEY_TENANT_001`, `MCP_API_KEY_TENANT_002`, ...）更易于批量管理
- Render Secret Files 方案（JSON 文件 `/etc/secrets/api-keys.json`）作为扩展选项，MVP 阶段先用环境变量

**格式**：
```
MCP_API_KEYS=sh_abc123...xyz:tenant-acme-001,sh_def456...uvw:tenant-beta-002
```

**放弃的替代方案**：JSON 格式的单变量 `MCP_TENANT_MAP={"key1":"t1"}` — JSON 在 shell 环境变量中转义麻烦；Render Secret Files — MVP 阶段增加操作复杂度

---

## 四、mcp_server/auth.py 设计

### 完整设计

```python
"""
mcp_server/auth.py

API Key 认证中间件。
- 从 Authorization: Bearer <key> 或 X-API-Key: <key> 提取 API Key
- 查映射表得到 tenant_id，注入 request.state.tenant_id
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

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# ContextVar：在 executor 线程中可读取当前请求的 tenant_id
# 在 auth 中间件的 dispatch() 中写入，在 _handle_* handler 中通过 _get_tenant_id() 读取
_tenant_id_var: ContextVar[str] = ContextVar("tenant_id", default="")


def _get_tenant_id() -> str:
    """从当前请求上下文读取 tenant_id（供 handler 调用）。"""
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
        # 每次实例化时重新加载（测试中可 mock _load_api_key_map）
        self._key_map = _API_KEY_MAP

    async def dispatch(self, request: Request, call_next):
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
        token = _tenant_id_var.set(tenant_id)

        try:
            response = await call_next(request)
        finally:
            # 请求结束后重置 ContextVar，防止线程池复用时值残留
            _tenant_id_var.reset(token)

        return response
```

### 关键设计要点

1. **`hmac.compare_digest()` 防时序攻击**：遍历所有 key 逐一对比，防止通过响应时间差推断 key 前缀
2. **ContextVar + reset token**：`_tenant_id_var.set()` 返回 token，`finally` 块中 `reset(token)` 确保请求结束后恢复默认值，防止线程池复用时值残留（对抗 Round 1 中识别的并发多租户风险）
3. **进程级 `_API_KEY_MAP`**：模块首次导入时加载，Render 重部署（环境变量更新后自动触发）是 key 轮换的机制
4. **白名单路径**：`/health` 和 `/health/`（带尾斜杠）均豁免，Render 健康检查不需要 API Key

---

## 五、mcp_server/http_app.py 设计

### 完整设计

```python
"""
mcp_server/http_app.py

Starlette ASGI app 组装，供 HTTP Streamable Transport 使用。
路由：
  GET  /health  — 健康检查（无需认证）
  POST /mcp     — MCP Streamable HTTP Transport 端点（需认证）
  GET  /mcp     — SSE 订阅（stateless 模式下不支持，返回 405）
  DELETE /mcp   — Session 终止（stateless 模式下无意义，返回 200）

中间件顺序（从外到内，即请求处理顺序从上到下）：
  1. CORSMiddleware   — 处理 OPTIONS preflight，添加 CORS 响应头
  2. APIKeyMiddleware — 验证 Bearer Token，注入 tenant_id
  3. Starlette Router — 路由到 /health 或 MCP session manager

依赖：mcp >= 1.8.0, starlette, uvicorn（启动时注入）
"""

from __future__ import annotations

import contextlib
import datetime
import logging
import os

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from mcp_server.auth import APIKeyMiddleware
from mcp_server.server import create_server, _load_analytics, probe_upstream_mcp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 计算 M365 Widget Renderer origin（如未来启用 Adaptive Card 需要）
# ---------------------------------------------------------------------------

def _compute_widget_origin(domain: str) -> str:
    import hashlib
    hashed = hashlib.sha256(domain.encode()).hexdigest()
    return f"https://{hashed}.widget-renderer.usercontent.microsoft.com"


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
    # M365 Widget Renderer（当前未启用 Adaptive Card，保留注释供将来参考）
    # _compute_widget_origin(_RENDER_DOMAIN),
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
    PRD §5.1 规范：status 字段值为 "ok" / "degraded" / "down"
    """
    from mcp_server.server import _analytics_ready

    checks: dict[str, str] = {}

    # 检查 analytics 是否已加载
    checks["analytics"] = "ok" if _analytics_ready.is_set() else "loading"

    # 检查 API Key 配置
    from mcp_server.auth import _API_KEY_MAP
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
            "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "checks": checks,
        },
    )


# ---------------------------------------------------------------------------
# MCP Session Manager（进程级单例）
# ---------------------------------------------------------------------------

def _build_session_manager() -> StreamableHTTPSessionManager:
    """
    构建 StreamableHTTPSessionManager。
    stateless=True：每个 POST /mcp 请求创建独立 ServerSession，
    请求结束后销毁，无跨请求状态，支持 Render 单 worker 部署。

    PRD §3.4 追溯：M365 Copilot 每次工具调用是独立请求，无需持久 session。
    """
    mcp_server = create_server()
    return StreamableHTTPSessionManager(
        app=mcp_server,
        stateless=True,     # M365 Copilot 无状态调用模型
        json_response=True, # 简单请求返回 JSON 而非 SSE 流，减少客户端复杂度
    )


_session_manager = _build_session_manager()


# ---------------------------------------------------------------------------
# Lifespan：管理 session manager 和 analytics 预加载
# ---------------------------------------------------------------------------

@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    """
    启动时：
    1. 启动 analytics 预加载线程（与 stdio 模式一致）
    2. 探测上游 MCP 连通性（失败不阻断启动）
    3. 启动 StreamableHTTPSessionManager

    关闭时：清理 session manager 资源
    """
    import threading
    from mcp_server.server import _load_analytics, probe_upstream_mcp

    # 上游健康检查（非阻塞，失败只记日志）
    ok, message = probe_upstream_mcp()
    if ok:
        logger.info("Upstream MCP probe succeeded: %s", message)
    else:
        logger.warning("Upstream MCP probe failed (non-fatal): %s", message)

    # 预加载重型 analytics 依赖（pandas 等）
    threading.Thread(target=_load_analytics, daemon=True).start()
    logger.info("Analytics preload thread started")

    # 启动 MCP session manager
    async with _session_manager.run():
        logger.info("StreamableHTTPSessionManager started (stateless=True)")
        yield

    logger.info("HTTP MCP app shutting down")


# ---------------------------------------------------------------------------
# Starlette App 组装
# ---------------------------------------------------------------------------

_app = Starlette(
    routes=[
        Route("/health", health, methods=["GET"]),
        Mount("/mcp", app=_session_manager.handle_request),
    ],
    lifespan=lifespan,
)

# 中间件包裹顺序（从内到外，越外越先执行）
# 顺序：CORS（最外层）→ APIKey（认证层）→ Starlette Router（内层）
# 注意：CORS 必须在 APIKey 之外，否则 OPTIONS preflight 会因缺 Key 被 401 拒绝
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
        "mcp-session-id",        # 小写变体兼容
        "mcp-protocol-version",
        "Last-Event-ID",         # SSE 断线重连
    ],
    expose_headers=["Mcp-Session-Id", "mcp-session-id"],  # 关键：浏览器端工具需要读此头
    max_age=86400,
    allow_credentials=False,     # 不使用 credentials（API Key 已在 header 中）
)

# 导出给 uvicorn 使用
app = _app
```

### 中间件顺序说明

```
请求 → [CORSMiddleware] → [APIKeyMiddleware] → [Starlette Router]
                                                      |
                                            /health → health()（无认证）
                                            /mcp    → session_manager（已认证）
```

- `CORSMiddleware` 在最外层：OPTIONS preflight 请求在认证之前处理，返回正确的 CORS 响应头，不会因缺少 API Key 被 401 拦截
- `APIKeyMiddleware` 在 CORS 之后：认证通过后注入 `tenant_id` 到请求 state 和 ContextVar

### stateless_http=True 的理由

1. M365 Copilot 每次 Copilot Chat 中的工具调用是独立 HTTP 请求，无跨请求 MCP session 需求
2. Render 单 worker 部署下，`stateless=True` 配合进程级 `_run_with_cache()` 缓存实现性能优化（无需 Redis）
3. `stateless=True` 时服务器不返回 `Mcp-Session-Id` 响应头（无 session 可维护），但 CORS 配置中仍 `expose_headers` 以确保调试工具兼容

---

## 六、mcp_server/__main__.py 修改

### 修改后完整文件

```python
"""Entry point for the SocialHub.AI MCP Server.

stdio 模式（默认，Claude Desktop / GitHub Copilot）：
    python -m mcp_server
    python -m mcp_server --transport stdio

HTTP 模式（M365 Copilot / 远程部署）：
    python -m mcp_server --transport http --port 8090
    uvicorn mcp_server.http_app:app --host 0.0.0.0 --port $PORT  # 等价
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
from pathlib import Path


def _configure_logging(http_mode: bool = False) -> Path:
    log_dir = Path.home() / ".socialhub" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "mcp_server.log"

    handlers: list[logging.Handler] = [
        logging.FileHandler(log_file, encoding="utf-8"),
    ]

    if http_mode:
        # HTTP 模式：日志输出到 stderr，避免污染 MCP 响应（stdout 为 ASGI 响应通道）
        handlers.append(logging.StreamHandler(sys.stderr))
    else:
        # stdio 模式：MCP 协议走 stdin/stdout，日志输出到 stderr
        handlers.append(logging.StreamHandler(sys.stderr))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=handlers,
        force=True,
    )
    return log_file


def _run_stdio() -> None:
    """stdio transport（现有逻辑，零修改）。"""
    import anyio
    from mcp.server.stdio import stdio_server
    from .server import create_server, _load_analytics, probe_upstream_mcp

    log_file = _configure_logging(http_mode=False)
    logger = logging.getLogger(__name__)
    pid = os.getpid()
    logger.info("Starting SocialHub MCP server (stdio) pid=%s", pid)
    logger.info("Server log file: %s", log_file)

    ok, message = probe_upstream_mcp()
    if ok:
        logger.info("Upstream MCP probe succeeded: %s", message)
    else:
        logger.error("Upstream MCP probe failed: %s", message)

    threading.Thread(target=_load_analytics, daemon=True).start()

    async def run() -> None:
        server = create_server()
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    anyio.run(run)


def _run_http(port: int) -> None:
    """HTTP Streamable Transport（M365 Copilot 远程部署）。"""
    import uvicorn
    from .http_app import app  # lifespan 在 http_app 中管理 probe 和 analytics 加载

    _configure_logging(http_mode=True)
    logger = logging.getLogger(__name__)
    pid = os.getpid()
    logger.info("Starting SocialHub MCP server (HTTP) pid=%s port=%s", pid, port)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SocialHub MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m mcp_server                      # stdio（Claude Desktop）
  python -m mcp_server --transport http     # HTTP（M365 Copilot）
  python -m mcp_server --transport http --port 9000
        """,
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport mode: stdio (default) or http",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", "8090")),
        help="HTTP server port (default: 8090, or $PORT env var)",
    )

    args = parser.parse_args()

    if args.transport == "stdio":
        _run_stdio()
    elif args.transport == "http":
        _run_http(args.port)


if __name__ == "__main__":
    main()
```

### 关键修改说明

1. **日志 handler 改为 `stderr`**：stdio 和 HTTP 两种模式下日志均输出到 `stderr`，不污染 MCP 协议通道（stdio 模式的 `stdin/stdout` 是 MCP 管道）
2. **`--port` 读取 `$PORT` 环境变量**：Render 会自动注入 `PORT=10000`，无需在 `render.yaml` 中额外配置启动参数
3. **HTTP 分支不重复调用 `probe_upstream_mcp()` 和 `_load_analytics()`**：这两个操作已在 `http_app.py` 的 `lifespan()` 中处理，避免重复调用

---

## 七、mcp_server/server.py 必要修改

### 修改 1：`_cache_key()` 加入 tenant_id

**安全必改，不可跳过**（PRD §6.3：「缓存 Key 含租户隔离」是不可妥协约束）

**现有代码（第 51-52 行）**：
```python
def _cache_key(name: str, args: dict) -> str:
    return f"{name}:{json.dumps(args, sort_keys=True)}"
```

**修改后**：
```python
def _cache_key(name: str, args: dict, tenant_id: str = "") -> str:
    """
    生成缓存 key。
    tenant_id 必须纳入 key，防止不同租户共享同一缓存结果（跨租户数据泄露）。
    stdio 模式下 tenant_id 来自环境变量 MCP_TENANT_ID，
    HTTP 模式下 tenant_id 来自 auth 中间件注入的 ContextVar。
    """
    return f"{tenant_id}:{name}:{json.dumps(args, sort_keys=True)}"
```

### 修改 2：`call_tool()` 中从 ContextVar 读取 tenant_id

**现有 `call_tool()` 内的 `_run()` 闭包（第 933-936 行）**：
```python
def _run():
    if not _analytics_ready.wait(timeout=120):
        return _err("Analytics failed to load within 120s")
    return _run_with_cache(name, args, lambda: handler(args))
```

**修改后**：
```python
def _run():
    if not _analytics_ready.wait(timeout=120):
        return _err("Analytics failed to load within 120s")

    # 从 ContextVar 读取 tenant_id（HTTP 模式由 auth 中间件注入）
    # stdio 模式回退到环境变量 MCP_TENANT_ID
    from mcp_server.auth import _get_tenant_id
    tid = _get_tenant_id() or os.getenv("MCP_TENANT_ID", "")

    if not tid:
        logger.warning("tenant_id 未设置，tool=%s", name)
        return _err("Tenant not configured. Contact IT administrator.")

    return _run_with_cache(name, args, tid, lambda: handler(args))
```

### 修改 3：`_run_with_cache()` 传递 tenant_id 到 `_cache_key()`

**现有代码（第 62-64 行）**：
```python
def _run_with_cache(name: str, args: dict, compute_fn) -> list:
    """Reuse cached or in-flight work for identical tool requests."""
    key = _cache_key(name, args)
```

**修改后**：
```python
def _run_with_cache(name: str, args: dict, tenant_id: str, compute_fn) -> list:
    """Reuse cached or in-flight work for identical tool requests."""
    key = _cache_key(name, args, tenant_id)
```

### 关于 client 传入 tenant_id 参数的处理

PRD §6.3：「客户端传入的 tenant_id 参数一律忽略，以 API Key 映射的 tenant_id 为准」。

实现方式：在 `call_tool()` 的 `_run()` 闭包中，在构建传给 handler 的 `args` 之前，强制删除 `tenant_id` key：

```python
# 在 _run() 闭包内，_run_with_cache 调用之前
safe_args = {k: v for k, v in args.items() if k != "tenant_id"}
return _run_with_cache(name, safe_args, tid, lambda: handler(safe_args))
```

这样即使客户端在 tool arguments 中传入 `tenant_id`，也会被静默丢弃，实际使用的 tenant_id 始终来自 API Key 映射。

---

## 八、build/m365-agent/ 文件设计

### 目录结构

```
build/
└── m365-agent/
    ├── manifest.json          # Teams App 包清单（必须）
    ├── declarativeAgent.json  # Declarative Agent 配置
    ├── plugin.json            # MCP Plugin（工具描述 + 认证）
    ├── mcp-tools.json         # 8 个精选工具的完整 inputSchema
    ├── color.png              # App 图标，192×192px（需要实际图片文件）
    └── outline.png            # App 图标轮廓，32×32px（需要实际图片文件）
```

### manifest.json 完整内容

```json
{
  "$schema": "https://developer.microsoft.com/en-us/json-schemas/teams/v1.17/MicrosoftTeams.schema.json",
  "manifestVersion": "1.17",
  "version": "1.0.0",
  "id": "com.socialhub.ai.m365-agent",
  "developer": {
    "name": "SocialHub.AI",
    "websiteUrl": "https://app.socialhub.ai",
    "privacyUrl": "https://app.socialhub.ai/privacy",
    "termsOfUseUrl": "https://app.socialhub.ai/terms"
  },
  "icons": {
    "color": "color.png",
    "outline": "outline.png"
  },
  "name": {
    "short": "SocialHub 助手",
    "full": "SocialHub 客户智能助手"
  },
  "description": {
    "short": "在 Copilot 中直接查询客户数据分析",
    "full": "帮助企业运营和管理团队在 M365 Copilot 中直接查询客户健康指标，涵盖留存分析、RFM 分层、订单趋势、营销活动效果等核心分析场景，无需切换 CLI 或 BI 系统。"
  },
  "accentColor": "#0078D4",
  "copilotAgents": {
    "declarativeAgents": [
      {
        "id": "socialhub-agent",
        "file": "declarativeAgent.json"
      }
    ]
  },
  "permissions": [
    "identity",
    "messageTeamMembers"
  ],
  "validDomains": [
    "mcp.socialhub.ai",
    "app.socialhub.ai"
  ]
}
```

**说明**：
- `manifestVersion: "1.17"` 是支持 `copilotAgents` 字段的最低版本
- `id` 使用反向域名格式，确保全局唯一性
- `validDomains` 必须包含 MCP Server 域名和深链接域名

### declarativeAgent.json 完整内容

```json
{
  "$schema": "https://developer.microsoft.com/en-us/json-schemas/copilot/declarative-agent/v1.0/schema.json",
  "schema_version": "v1.0",
  "name": "SocialHub 客户智能助手",
  "description": "帮助企业运营和管理团队在 M365 Copilot 中直接查询客户数据，涵盖留存分析、RFM 分层、异常检测、营销活动效果等核心分析场景。",
  "instructions": "你是 SocialHub 客户智能助手，帮助企业运营和管理团队快速获取客户数据洞察。\n\n## 你的能力范围\n你只分析 SocialHub 系统中该企业的客户数据，包括：客户概况、留存分析、RFM 分层、订单趋势、异常检测、营销活动效果、客户生命周期价值。\n\n## 调用工具的规则\n1. 当用户的问题涉及「整体情况/概况/摘要/关键数字」时，优先调用 analytics_overview\n2. 当用户问到「流失/留存/复购/回头客」时，调用 analytics_retention\n3. 当用户问到「高价值客户/大客户/VIP/客户分层/RFM/值钱的客户」时，调用 analytics_rfm\n4. 当用户需要「具体客户群规模/找出哪些客户/多少人满足条件」时，调用 analytics_customers\n5. 当用户问「有没有问题/有什么异常/需要关注什么/上周出了什么」时，调用 analytics_anomaly\n6. 当用户问到「业绩/订单量/销售额/趋势/和上月比」时，调用 analytics_orders\n7. 当用户问到「LTV/客户价值/高潜力/续费价值/值钱」时，调用 analytics_ltv\n8. 当用户问到「活动/营销/大促/转化率/活动效果/双十一」时，调用 analytics_campaigns\n9. 如果一个问题同时涉及多个维度，可以顺序调用 2-3 个工具，综合结果后统一回答\n10. 如果用户的问题超出上述工具的覆盖范围，明确告知「当前版本暂不支持查询 [具体内容]」，不要编造数据\n\n## 数据口径透明化（重要）\n每次返回关键指标时，必须附加一行口径说明。格式示例：\n- 「留存率 67.3%（统计口径：近 30 天有购买记录的用户 ÷ 31-60 天内有购买记录的用户）」\n- 「高价值客户 1,234 人（口径：历史消费金额位于前 20%，基于近 180 天数据）」\n- 「异常判断基准：相比过去 4 周均值偏差超过 2 个标准差」\n口径说明使用小号文字或放在括号内，不占用主要回答篇幅。\n\n## 时间范围处理\n- 用户说「最近」「近期」时，默认使用近 30 天\n- 用户说「上周」时，使用上一个完整自然周（周一至周日）\n- 用户说「本月」时，使用当月 1 日至今\n- 在回答的第一行说明实际使用的时间范围，例如「以下是 2026-02-28 至 2026-03-29 的数据：」\n- 时间表述模糊时，先给出基于默认假设的回答，末尾注明「如需调整时间范围，请告诉我」\n\n## 可操作下一步\n当分析结果提示可以采取行动时（如发现流失风险客户群、活动效果低于基线），在回答末尾附加：\n「→ 在 SocialHub 中针对这批客户创建活动：https://app.socialhub.ai/campaigns/new」\n（EA 阶段升级为带预填参数的深链接）\n\n## 输出格式规范\n- 始终用中文回答（除非用户明确要求英文）\n- 关键数字使用**加粗**标注\n- 多个指标用分隔列表而非连续长句\n- 每次回答末尾提供 1-2 个追问建议（「你还可以问：…」），引导用户深入探索\n- 对于严重异常，在数字前加 ⚠️ 标注\n- 回答长度：汇总摘要控制在 200 字以内（含口径说明），详细分析不超过 500 字\n- 不要暴露工具调用的内部名称（如不要说「我调用了 analytics_rfm」）\n\n## 错误处理\n当出现以下情况时，使用对应的引导语：\n- 查询结果为空：「该时间段内暂无符合条件的数据。可能原因：①该时段无业务发生 ②筛选条件过严。建议调整时间范围或放宽筛选条件再试。」\n- 工具调用超时：「数据查询耗时较长，请稍后重试。如问题持续，请联系 IT 管理员确认服务状态。」\n- 认证相关错误：「身份验证遇到问题，请联系贵司 IT 管理员，或访问 https://status.socialhub.ai 查看服务状态。」\n\n## 安全与边界\n- 只返回本企业的聚合统计数据，不展示具体消费者的姓名、手机号或身份证等个人信息\n- 禁止回答与客户数据分析无关的问题（如通用知识问答、其他系统操作等）",
  "conversation_starters": [
    {
      "text": "近 30 天的客户健康度怎么样？给我一个关键数字的快速摘要"
    },
    {
      "text": "上周有没有数据异常？重点看订单量和客户留存"
    },
    {
      "text": "帮我找出最近 60 天没有复购、但历史消费金额较高的客户群"
    },
    {
      "text": "最近一次营销活动的效果怎么样？新客和复购各带来了多少？"
    },
    {
      "text": "我们的高价值客户（LTV 前 20%）最近活跃度如何？有流失风险吗？"
    },
    {
      "text": "本月整体业绩趋势如何？和上个月相比有什么变化？"
    }
  ],
  "capabilities": [
    {
      "name": "OneDriveAndSharePoint"
    }
  ],
  "actions": [
    {
      "id": "socialhub-mcp-plugin",
      "file": "plugin.json"
    }
  ]
}
```

**说明**：
- `instructions` 中工具名使用 server.py 的 `_HANDLERS` key（`analytics_*`），与 `mcp-tools.json` 中的 `name` 字段保持一致
- `conversation_starters` 使用数组对象格式（新版 schema 格式）
- `capabilities` 中 `OneDriveAndSharePoint` 是 M365 Copilot 标准能力声明，用于表明这是一个内置于 M365 生态的 Agent

### plugin.json — MVP 版本（ApiKeyPluginVault）

```json
{
  "$schema": "https://developer.microsoft.com/en-us/json-schemas/copilot/plugin/v2.2/schema.json",
  "schema_version": "v2.2",
  "name_for_human": "SocialHub 客户分析",
  "name_for_model": "socialhub_analytics",
  "description_for_human": "查询企业客户数据，包括留存率、RFM 分层、订单趋势、营销活动效果等分析。",
  "description_for_model": "Provides customer analytics data for the enterprise, including customer overview, retention analysis, RFM segmentation, order trends, anomaly detection, LTV analysis, and campaign analysis. All data is tenant-isolated and returned as structured JSON.",
  "logo_url": "https://mcp.socialhub.ai/static/logo.png",
  "contact_email": "support@socialhub.ai",
  "legal_info_url": "https://app.socialhub.ai/terms",
  "privacy_policy_url": "https://app.socialhub.ai/privacy",
  "auth": {
    "type": "ApiKeyPluginVault",
    "reference_id": "${{SOCIALHUB_API_KEY}}"
  },
  "api": {
    "type": "openapi",
    "url": "https://mcp.socialhub.ai/openapi.json"
  },
  "runtimes": [
    {
      "type": "OpenApi",
      "spec": {
        "url": "https://mcp.socialhub.ai/openapi.json"
      },
      "run_for_functions": [
        "analytics_overview",
        "analytics_retention",
        "analytics_rfm",
        "analytics_customers",
        "analytics_anomaly",
        "analytics_orders",
        "analytics_ltv",
        "analytics_campaigns"
      ]
    },
    {
      "type": "MCPServer",
      "server_url": "https://mcp.socialhub.ai/mcp",
      "allowed_tools": [
        "analytics_overview",
        "analytics_retention",
        "analytics_rfm",
        "analytics_customers",
        "analytics_anomaly",
        "analytics_orders",
        "analytics_ltv",
        "analytics_campaigns"
      ]
    }
  ],
  "functions": [
    {"name": "analytics_overview"},
    {"name": "analytics_retention"},
    {"name": "analytics_rfm"},
    {"name": "analytics_customers"},
    {"name": "analytics_anomaly"},
    {"name": "analytics_orders"},
    {"name": "analytics_ltv"},
    {"name": "analytics_campaigns"}
  ]
}
```

### plugin.json — GA 版本（OAuthPluginVault，EA 结束前完成）

```json
{
  "$schema": "https://developer.microsoft.com/en-us/json-schemas/copilot/plugin/v2.2/schema.json",
  "schema_version": "v2.2",
  "name_for_human": "SocialHub 客户分析",
  "name_for_model": "socialhub_analytics",
  "description_for_human": "查询企业客户数据，包括留存率、RFM 分层、订单趋势、营销活动效果等分析。",
  "description_for_model": "Provides customer analytics data for the enterprise, including customer overview, retention analysis, RFM segmentation, order trends, anomaly detection, LTV analysis, and campaign analysis. All data is tenant-isolated and returned as structured JSON.",
  "logo_url": "https://mcp.socialhub.ai/static/logo.png",
  "contact_email": "support@socialhub.ai",
  "legal_info_url": "https://app.socialhub.ai/terms",
  "privacy_policy_url": "https://app.socialhub.ai/privacy",
  "auth": {
    "type": "OAuthPluginVault",
    "reference_id": "${{SOCIALHUB_OAUTH_CONFIG}}"
  },
  "runtimes": [
    {
      "type": "MCPServer",
      "server_url": "https://mcp.socialhub.ai/mcp",
      "allowed_tools": [
        "analytics_overview",
        "analytics_retention",
        "analytics_rfm",
        "analytics_customers",
        "analytics_anomaly",
        "analytics_orders",
        "analytics_ltv",
        "analytics_campaigns"
      ]
    }
  ],
  "functions": [
    {"name": "analytics_overview"},
    {"name": "analytics_retention"},
    {"name": "analytics_rfm"},
    {"name": "analytics_customers"},
    {"name": "analytics_anomaly"},
    {"name": "analytics_orders"},
    {"name": "analytics_ltv"},
    {"name": "analytics_campaigns"}
  ]
}
```

**GA 版本 auth.py 新增路径**（EA 结束前实现）：
```python
# mcp_server/auth.py 中新增 Entra ID token 验证
import jwt  # PyJWT，mcp SDK 已依赖

def _verify_entra_token(token: str) -> str | None:
    """
    验证 Entra ID Bearer token，提取 tenant_id。
    从 tid claim 提取 Entra Tenant ID（GUID），
    查映射表得到 SocialHub tenant_id。
    返回 SocialHub tenant_id，验证失败返回 None。
    """
    try:
        # 实际生产中需要从 JWKS 端点获取公钥验证签名
        # MVP GA 版本：验证 issuer + tid claim，签名验证可用 msal 库
        payload = jwt.decode(token, options={"verify_signature": False})
        entra_tenant_id = payload.get("tid", "")
        return _ENTRA_TENANT_MAP.get(entra_tenant_id)
    except Exception:
        return None
```

### mcp-tools.json 完整内容

```json
{
  "schema_version": "v2",
  "name_for_model": "socialhub_analytics",
  "tools": [
    {
      "name": "analytics_overview",
      "description": "获取企业客户整体健康状况快照，返回活跃客户数量、新增客户数、整体留存率、高价值客户占比等核心摘要指标。当用户询问「整体情况」「客户概况」「关键数字」「数据总结」时调用此工具。适用于管理层晨会快查和运营每日例行监控。",
      "inputSchema": {
        "type": "object",
        "properties": {
          "days": {
            "type": "integer",
            "description": "统计近 N 天的数据，默认 30。常用值：7（近一周）、30（近一月）、90（近一季）。",
            "default": 30,
            "minimum": 1,
            "maximum": 365
          },
          "start_date": {
            "type": "string",
            "description": "统计开始日期，格式 YYYY-MM-DD。与 end_date 配合使用可精确指定日期范围，优先级高于 days 参数。",
            "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
          },
          "end_date": {
            "type": "string",
            "description": "统计结束日期，格式 YYYY-MM-DD。",
            "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
          }
        },
        "required": []
      }
    },
    {
      "name": "analytics_retention",
      "description": "分析客户留存率和流失趋势，返回指定周期内的留存率、流失率、复购间隔分布。当用户询问「流失」「留存」「复购」「回头客」「客户流走了多少」时调用此工具。留存率口径：有 N+1 周期购买的用户 ÷ 有 N 周期购买的用户。",
      "inputSchema": {
        "type": "object",
        "properties": {
          "days": {
            "type": "integer",
            "description": "分析时间窗口天数，默认 30。",
            "default": 30,
            "minimum": 7,
            "maximum": 365
          },
          "comparison_period": {
            "type": "integer",
            "description": "对比周期天数，默认与 days 相同。设置后会计算环比变化。",
            "minimum": 7,
            "maximum": 365
          }
        },
        "required": []
      }
    },
    {
      "name": "analytics_rfm",
      "description": "按 RFM 模型（最近购买时间/购买频率/消费金额）对客户进行分层，返回各层级的客户数量和占比。当用户询问「高价值客户」「VIP」「客户分层」「哪类客户最好」「客户细分」时调用。RFM 分层阈值基于该企业历史数据的分位数动态计算。",
      "inputSchema": {
        "type": "object",
        "properties": {
          "days": {
            "type": "integer",
            "description": "分析时间窗口天数，默认 90。",
            "default": 90,
            "minimum": 30,
            "maximum": 365
          },
          "segments": {
            "type": "integer",
            "description": "RFM 分层数量，默认 5（冠军客户/忠实客户/潜力客户/流失风险/流失客户）。",
            "default": 5,
            "minimum": 3,
            "maximum": 10
          }
        },
        "required": []
      }
    },
    {
      "name": "analytics_customers",
      "description": "按条件筛选并返回符合条件的消费者统计列表，返回该群体的规模、平均消费、沉默天数等聚合数据（不返回个人姓名、手机号等 PII 字段）。当用户需要「找出哪些客户」「多少人满足条件」「给我一个名单规模」时调用。",
      "inputSchema": {
        "type": "object",
        "properties": {
          "min_days_since_last_purchase": {
            "type": "integer",
            "description": "最近购买距今最少天数（含），用于筛选沉默客户。",
            "minimum": 0
          },
          "max_days_since_last_purchase": {
            "type": "integer",
            "description": "最近购买距今最多天数（含），与 min 配合筛选特定沉默区间。",
            "minimum": 0
          },
          "ltv_percentile_min": {
            "type": "integer",
            "description": "LTV 分位数下限（0-100），如 80 表示只看消费金额前 20% 的高价值客户。",
            "minimum": 0,
            "maximum": 100
          },
          "days": {
            "type": "integer",
            "description": "历史统计窗口天数，默认 90。",
            "default": 90,
            "minimum": 1,
            "maximum": 365
          },
          "limit": {
            "type": "integer",
            "description": "返回聚合统计的样本条数上限，默认 50。",
            "default": 50,
            "minimum": 1,
            "maximum": 500
          }
        },
        "required": []
      }
    },
    {
      "name": "analytics_anomaly",
      "description": "对多维度指标进行异常检测，返回当前周期内相对历史基线有显著偏差的指标列表，按严重程度排序。当用户询问「有没有问题」「需要关注什么」「有什么异常」「上周出了什么事」时调用。异常判断基准：相比过去 4 个同期周期的均值偏差超过 2 个标准差。",
      "inputSchema": {
        "type": "object",
        "properties": {
          "days": {
            "type": "integer",
            "description": "检查窗口天数，默认 7（通常对应「上周」）。",
            "default": 7,
            "minimum": 1,
            "maximum": 90
          },
          "dimensions": {
            "type": "string",
            "description": "检查维度，默认 all（全部）。可指定 retention（留存）、orders（订单）、campaigns（活动）。",
            "default": "all",
            "enum": ["all", "retention", "orders", "campaigns"]
          }
        },
        "required": []
      }
    },
    {
      "name": "analytics_orders",
      "description": "返回指定时间范围内的订单量、GMV 趋势，以及与上一同等周期的对比变化。当用户询问「业绩」「销售额」「订单量」「趋势」「和上月相比」时调用。与 analytics_overview 互补：orders 提供时间轴趋势，overview 提供当前截面数据。",
      "inputSchema": {
        "type": "object",
        "properties": {
          "days": {
            "type": "integer",
            "description": "统计天数，默认 30。",
            "default": 30,
            "minimum": 1,
            "maximum": 365
          },
          "granularity": {
            "type": "string",
            "description": "时间粒度，默认 day（按天）。可选 week（按周）、month（按月）。",
            "default": "day",
            "enum": ["day", "week", "month"]
          },
          "compare_previous": {
            "type": "boolean",
            "description": "是否附加同期对比（环比），默认 true。",
            "default": true
          }
        },
        "required": []
      }
    },
    {
      "name": "analytics_ltv",
      "description": "分析客户生命周期价值（LTV）分布，返回高价值客户（LTV 前 20%）的规模、活跃度趋势及流失风险指标。当用户询问「LTV」「客户价值」「高潜力客户」「续费价值」「值钱的客户」时调用。LTV 计算基于历史消费总额（不含退款）。",
      "inputSchema": {
        "type": "object",
        "properties": {
          "top_percentile": {
            "type": "integer",
            "description": "关注的高价值客户 LTV 分位数，默认 20（即前 20%，亦即 top 80th percentile）。",
            "default": 20,
            "minimum": 5,
            "maximum": 50
          },
          "days": {
            "type": "integer",
            "description": "分析时间窗口天数，默认 180（近半年）。",
            "default": 180,
            "minimum": 30,
            "maximum": 730
          }
        },
        "required": []
      }
    },
    {
      "name": "analytics_campaigns",
      "description": "返回指定时间范围内营销活动的参与人数、新客转化数、复购激活数、GMV 贡献及与历史活动的对比。当用户询问「活动」「大促」「营销」「转化率」「活动效果」时调用。若时间范围内有多个活动，返回列表供用户选择或分别展示。",
      "inputSchema": {
        "type": "object",
        "properties": {
          "days": {
            "type": "integer",
            "description": "活动所在时间范围天数，默认 14。",
            "default": 14,
            "minimum": 1,
            "maximum": 90
          },
          "campaign_name": {
            "type": "string",
            "description": "活动名称关键词（模糊匹配），可选。不传时返回时间范围内所有活动。",
            "maxLength": 100
          },
          "start_date": {
            "type": "string",
            "description": "活动查询开始日期，格式 YYYY-MM-DD。",
            "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
          },
          "end_date": {
            "type": "string",
            "description": "活动查询结束日期，格式 YYYY-MM-DD。",
            "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
          }
        },
        "required": []
      }
    }
  ]
}
```

---

## 九、render.yaml 设计

### 完整配置

```yaml
# render.yaml — Render Blueprint（Infrastructure as Code）
# 放置于仓库根目录，Render 自动检测并创建服务

services:
  - type: web
    name: socialhub-mcp
    runtime: python
    plan: starter           # $7/月，无冷启动，Render SLA 99.9%（PRD §7 强制要求）
    region: oregon          # 与 skills-store-backend 同区域，减少跨区延迟
    branch: main
    buildCommand: pip install -e ".[http]"
    startCommand: uvicorn mcp_server.http_app:app --host 0.0.0.0 --port $PORT --workers 1 --log-level info
    healthCheckPath: /health   # Render 零停机部署探针，/health 不需要认证（PRD §5.1）
    autoDeploy: true           # push 到 main 分支自动触发重部署

    envVars:
      # -----------------------------------------------------------------------
      # 敏感变量：sync: false，值不写入 Git，首次部署后在 Render Dashboard 手动填写
      # -----------------------------------------------------------------------
      - key: MCP_API_KEYS
        sync: false
        # 格式：sh_abc123...xyz:tenant-acme-001,sh_def456...uvw:tenant-beta-002
        # 每个 API Key 和 tenant_id 用冒号分隔，多个条目用逗号分隔

      - key: MCP_TENANT_ID
        sync: false
        # stdio 模式兼容性保留，HTTP 模式优先使用 MCP_API_KEYS 中的 tenant_id
        # 单租户部署时可只设置此变量（兼容回退）

      - key: MCP_SSE_URL
        sync: false
        # 上游 MCP SSE 端点，probe_upstream_mcp() 使用

      - key: MCP_POST_URL
        sync: false
        # 上游 MCP POST 端点

      # -----------------------------------------------------------------------
      # 非敏感配置：直接写入 render.yaml
      # -----------------------------------------------------------------------
      - key: PYTHONUNBUFFERED
        value: "1"
        # 确保 Python 日志实时输出到 Render Log，不被缓冲

      - key: LOG_LEVEL
        value: "INFO"

      - key: ALLOWED_ORIGINS
        value: ""
        # 逗号分隔的额外 CORS 允许 origin，生产环境留空（使用代码中的默认白名单）
        # 如需添加 M365 Widget Renderer origin，在此填入

      - key: PORT
        value: "10000"
        # Render 会自动注入 PORT 环境变量，此处显式声明为文档目的
        # uvicorn 的 --port $PORT 会读取 Render 注入的实际端口

  # ---------------------------------------------------------------------------
  # Keep-Alive Cron Job（仅 Free Tier 使用，Starter Tier 不需要）
  # 注意：此 cron job 违反 Render 服务条款精神，仅用于开发/Demo 环境
  # 生产环境（Starter Tier）请注释或删除此 cron job
  # ---------------------------------------------------------------------------
  # - type: cron
  #   name: mcp-keepalive
  #   runtime: python
  #   plan: free
  #   schedule: "*/14 * * * *"
  #   buildCommand: pip install httpx
  #   startCommand: python -c "import httpx; httpx.get('https://socialhub-mcp.onrender.com/health')"
```

---

## 十、开发步骤（按依赖顺序，每步可独立验证）

### Step 1：升级依赖 + pyproject.toml 修改

**做什么**：
- 将 `pyproject.toml` 中 `mcp>=1.0.0` 改为 `mcp>=1.8.0`
- 新增 `[project.optional-dependencies]` 下的 `http` 条目：
  ```toml
  http = [
      "uvicorn>=0.30.0",
      "starlette>=0.40.0",
  ]
  ```
- 本地运行 `pip install -e ".[http]"` 验证依赖可安装

**验证方式**：
```bash
pip install -e ".[http]"
python -c "import mcp; import uvicorn; import starlette; print('OK')"
python -c "from mcp.server.streamable_http_manager import StreamableHTTPSessionManager; print('HTTP manager OK')"
```

**耗时估算**：15 分钟

---

### Step 2：新建 mcp_server/auth.py

**做什么**：按第四节完整代码创建 `mcp_server/auth.py`

**验证方式**：
```bash
# 设置测试环境变量
export MCP_API_KEYS="sh_test_key_abc123:tenant-test-001"

# 单元测试
python -c "
from mcp_server.auth import _load_api_key_map, _extract_api_key, APIKeyMiddleware, _get_tenant_id
m = _load_api_key_map()
assert 'sh_test_key_abc123' in m
assert m['sh_test_key_abc123'] == 'tenant-test-001'
print('auth.py unit test PASSED')
"
```

然后运行 `tests/test_auth.py`（Step 8 中创建）

**耗时估算**：2-3 小时（含编写测试）

---

### Step 3：修改 mcp_server/server.py

**做什么**：按第七节的 3 处修改改造 `server.py`：
1. `_cache_key()` 加 `tenant_id` 参数
2. `_run_with_cache()` 接收并传递 `tenant_id`
3. `call_tool()` 内的 `_run()` 闭包：导入 `_get_tenant_id`，删除客户端传入的 `tenant_id` 参数，传 `tid` 给 `_run_with_cache`

**验证方式**：
```bash
# stdio 模式仍然正常工作（回归测试）
export MCP_TENANT_ID="tenant-test-001"
python -c "
from mcp_server.server import _cache_key, _run_with_cache
k1 = _cache_key('test', {'days': 30}, 'tenant-a')
k2 = _cache_key('test', {'days': 30}, 'tenant-b')
assert k1 != k2, 'tenant_id isolation FAILED'
print('cache key isolation test PASSED')
print(f'k1={k1}')
print(f'k2={k2}')
"
pytest tests/ -x -q  # 确保现有测试不回归
```

**耗时估算**：1-2 小时（含回归测试）

---

### Step 4：新建 mcp_server/http_app.py

**做什么**：按第五节完整代码创建 `mcp_server/http_app.py`

**验证方式**：
```bash
export MCP_API_KEYS="sh_test_key_abc123:tenant-test-001"
export MCP_TENANT_ID="tenant-test-001"

# 启动 HTTP 服务（前台运行）
python -c "import uvicorn; from mcp_server.http_app import app; uvicorn.run(app, port=8090)" &
sleep 3

# 1. 健康检查（无需认证）
curl -s http://localhost:8090/health | python -m json.tool
# 期望：{"status": "ok" 或 "degraded", "version": "1.0.0", ...}

# 2. 无 API Key 请求（应返回 401）
curl -s -w "\nHTTP %{http_code}\n" -X POST http://localhost:8090/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{}},"id":1}'
# 期望：HTTP 401

# 3. 有 API Key 的 initialize 请求
curl -s -X POST http://localhost:8090/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sh_test_key_abc123" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{}},"id":1}'
# 期望：{"jsonrpc":"2.0","result":{...},"id":1}

# 4. tools/list
curl -s -X POST http://localhost:8090/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sh_test_key_abc123" \
  -d '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":2}'
# 期望：返回工具列表，包含 analytics_overview 等

kill %1  # 关闭后台服务
```

**耗时估算**：3-4 小时（含 CORS/auth 调试）

---

### Step 5：修改 mcp_server/__main__.py

**做什么**：按第六节完整代码替换 `__main__.py`

**验证方式**：
```bash
# 1. stdio 模式回归（不带参数）
echo '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{}},"id":1}' | \
  python -m mcp_server 2>/dev/null | head -5
# 期望：stdio 模式正常响应

# 2. HTTP 模式启动
export MCP_API_KEYS="sh_test_key_abc123:tenant-test-001"
python -m mcp_server --transport http --port 8091 &
sleep 3
curl -s http://localhost:8091/health
kill %1

# 3. 帮助文档
python -m mcp_server --help
```

**耗时估算**：1 小时

---

### Step 6：创建 build/m365-agent/ 目录和文件

**做什么**：
1. 创建 `build/m365-agent/` 目录
2. 按第八节内容创建 `manifest.json`、`declarativeAgent.json`、`plugin.json`（MVP 版本）、`mcp-tools.json`
3. 准备 `color.png`（192×192）和 `outline.png`（32×32）图标文件

**验证方式**：
```bash
# 1. JSON 语法检查
python -c "
import json, os
for f in ['manifest.json','declarativeAgent.json','plugin.json','mcp-tools.json']:
    path = f'build/m365-agent/{f}'
    with open(path) as fh:
        data = json.load(fh)
    print(f'OK: {f}')
print('All JSON files valid')
"

# 2. 打包 ZIP（Teams App 包格式）
cd build/m365-agent && zip -r ../socialhub-agent-v1.0.zip . && cd ../..
ls -lh build/socialhub-agent-v1.0.zip

# 3. 使用 Teams App Validator（需要 Node.js）
# npx @microsoft/teams-app-validator build/socialhub-agent-v1.0.zip
# 或使用 Teams Developer Portal 在线验证：https://dev.teams.microsoft.com/apps
```

**耗时估算**：2-3 小时（含图标准备）

---

### Step 7：创建 render.yaml

**做什么**：按第九节内容在仓库根目录创建 `render.yaml`

**验证方式**：
```bash
# YAML 语法验证
python -c "import yaml; yaml.safe_load(open('render.yaml')); print('render.yaml syntax OK')"

# 提交到 Git，在 Render Dashboard 中导入（实际部署验证）
git add render.yaml
git commit -m "feat: add Render Blueprint for MCP HTTP server"
```

**耗时估算**：30 分钟

---

### Step 8：编写测试文件

**做什么**：创建 `tests/test_auth.py` 和 `tests/test_cache_isolation.py`

**`tests/test_auth.py` 关键用例**：
```python
import os
import pytest
from unittest.mock import patch

# 测试 _load_api_key_map()
def test_load_api_key_map_valid():
    with patch.dict(os.environ, {"MCP_API_KEYS": "key1:tenant-a,key2:tenant-b"}):
        from importlib import reload
        import mcp_server.auth as auth_module
        m = auth_module._load_api_key_map()
        assert m["key1"] == "tenant-a"
        assert m["key2"] == "tenant-b"

def test_load_api_key_map_empty():
    with patch.dict(os.environ, {"MCP_API_KEYS": ""}, clear=False):
        from mcp_server.auth import _load_api_key_map
        m = _load_api_key_map()
        assert m == {}

# 测试 /health 跳过认证
# 测试 Bearer token 解析
# 测试 X-API-Key 解析（优先级高于 Authorization）
# 测试无效 key 返回 401
# 测试 hmac 对比（防止 == 比较的时序攻击）
```

**`tests/test_cache_isolation.py` 关键用例**：
```python
from mcp_server.server import _cache_key

def test_cache_key_tenant_isolation():
    """不同 tenant_id 产生不同 cache key（PRD §6.3 安全必改验收）"""
    k1 = _cache_key("analytics_overview", {"days": 30}, "tenant-a")
    k2 = _cache_key("analytics_overview", {"days": 30}, "tenant-b")
    assert k1 != k2

def test_cache_key_same_tenant_same_args():
    """相同 tenant_id 和参数产生相同 key（缓存命中正常工作）"""
    k1 = _cache_key("analytics_overview", {"days": 30}, "tenant-a")
    k2 = _cache_key("analytics_overview", {"days": 30}, "tenant-a")
    assert k1 == k2

def test_cache_key_includes_tenant_id():
    """cache key 必须包含 tenant_id"""
    k = _cache_key("analytics_overview", {}, "tenant-xyz")
    assert "tenant-xyz" in k
```

**验证方式**：
```bash
pytest tests/test_auth.py tests/test_cache_isolation.py -v
```

**耗时估算**：2-3 小时

---

### Step 9：Render 部署和端到端验证

**做什么**：
1. Push 包含 `render.yaml` 的代码到 `main` 分支
2. 在 Render Dashboard 中导入 Blueprint，填写敏感环境变量（`MCP_API_KEYS`、`MCP_TENANT_ID`、`MCP_SSE_URL`、`MCP_POST_URL`）
3. 等待部署完成（约 3-5 分钟）
4. 执行端到端验证

**验证方式**：
```bash
export MCP_URL="https://socialhub-mcp.onrender.com"
export API_KEY="sh_your_actual_key"

# T1.1：健康检查
curl -s $MCP_URL/health | python -m json.tool
# 期望：{"status": "ok", ...}

# T1.2：无效 Key 返回 401
curl -s -w "\nHTTP %{http_code}" -X POST $MCP_URL/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer invalid_key" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{}},"id":1}'
# 期望：HTTP 401

# T1.3：有效 Key 的 initialize
curl -s -X POST $MCP_URL/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{}},"id":1}'

# T1.4：MCP Inspector 验证（需要 Node.js）
# npx @modelcontextprotocol/inspector $MCP_URL/mcp

# T1.5：两个不同 tenant 的 Key，验证数据隔离
# （需要配置两个实际 API Key 到不同 tenant）
```

**耗时估算**：2-3 小时（含 Render 配置调试）

---

### Step 10：M365 Copilot 端到端测试

**做什么**：
1. 使用 Microsoft 365 测试租户（需提前申请 M365 开发者账号）
2. 上传 `build/socialhub-agent-v1.0.zip` 到 Teams Admin Center
3. 配置 API Key（在 ATK env/.env.production 中）
4. 在 M365 Copilot Chat 中测试 6 个 Conversation Starters

**验证方式**（对应 PRD 验收 T3）：
- [ ] 6 个 Conversation Starters 全部点击后 10 秒内返回有意义的回答
- [ ] 每次回答包含时间范围说明和至少一条数据口径说明
- [ ] 追问（第二轮）能基于第一轮上下文回答
- [ ] 查询结果为空时返回有帮助的引导文字
- [ ] 响应不包含技术内部名称（如「analytics_rfm」）

**耗时估算**：3-4 小时（含 M365 测试环境配置）

---

## 十一、迭代记录

### Round 1 对抗：「破坏者」视角

#### 发现的问题

**问题 1.1：并发多租户下 ContextVar 的 reset 缺失**

初始设计中 `APIKeyMiddleware.dispatch()` 调用 `_tenant_id_var.set(tenant_id)` 后没有 `reset`。在 ASGI 框架中，asyncio 任务会继承父任务的 context，但 `BaseHTTPMiddleware` 使用的是 Starlette 的任务调度，若 ContextVar 在请求结束后不重置，极端情况下线程池线程被复用时可能残留前一请求的 tenant_id（跨租户数据风险）。

**修正**：在 `dispatch()` 中使用 `token = _tenant_id_var.set(tenant_id)` + `finally: _tenant_id_var.reset(token)` 模式。已在第四节 `auth.py` 设计中体现。

---

**问题 1.2：MCP Server 冷启动期间 /health 返回 503 导致 Render 部署失败**

`_analytics_ready.is_set()` 在 analytics 加载期间为 False。若 `/health` 在 analytics 未加载完成时直接返回 503，Render 健康检查会认为部署失败并回滚。

**修正**：`/health` 设计为：
- analytics loading 状态 → HTTP 200 + `status: "degraded"`（Render 探针通过，不触发回滚）
- config 缺失（无 API Key 配置）→ HTTP 503 + `status: "down"`（这是真正的不可用状态，应触发告警）

已在第五节 `/health` 端点实现中体现。

---

**问题 1.3：M365 Copilot 超时重试导致重复缓存写入**

M365 Copilot 在工具调用超时后会重试。`_run_with_cache()` 中的 `_inflight` 机制（`threading.Event`）可以合并重复的并发请求，但如果第一次请求超时（M365 放弃等待）而服务端仍在计算，第二次重试到来时：
- 服务端仍在处理第一次请求（`_inflight` 中有该 key 的 Event）
- 第二次请求会等待第一次完成（`event.wait()`），第一次完成后两次请求共享同一结果

这是正确行为，`_inflight` 机制天然处理了重试合并。但需要确认超时设置：工具调用上游超时应设为 10 秒（PRD §6.1 P95 < 2 秒），远小于 M365 Copilot 的 30 秒超时。

**修正**：在工具 handler 内部确保上游调用有 10 秒超时（现有 handler 中的 `httpx.AsyncClient` 应设置 `timeout=10.0`）。这是现有代码问题，不在本次改动范围内，记录为 P2 技术债。

---

**问题 1.4：API Key 泄露后的快速失效机制**

环境变量方式的 API Key 轮换需要 Render 重部署（约 2-3 分钟）。若 Key 泄露，在 Render 重部署完成前，旧 Key 仍然有效。

**修正（MVP 可接受）**：MVP 阶段 Render 重部署 2-3 分钟是可接受的 Key 失效窗口，优先级低于功能实现。GA 阶段引入数据库存储 Key 并支持即时失效。记录为 P2 技术债，不影响本次实现。

---

**问题 1.5：`_load_api_key_map()` 模块级调用导致测试困难**

`_API_KEY_MAP = _load_api_key_map()` 在模块首次导入时执行，单元测试需要 mock 环境变量。若测试文件在 `from mcp_server.auth import ...` 之前设置环境变量（通过 `monkeypatch`），模块已被缓存则 mock 不生效。

**修正**：`APIKeyMiddleware.__init__()` 中重新调用 `_load_api_key_map()`（已在第四节设计中体现：`self._key_map = _API_KEY_MAP`，测试中可直接替换 `middleware._key_map`）。完整测试方案在 `test_auth.py` 中使用 `importlib.reload()` 配合 `patch.dict(os.environ, ...)`。

---

### Round 2 对抗：「CLAUDE.md 守护者」视角

#### CLAUDE.md 硬约束逐条核对

**约束 1：MCP 工具处理器返回 `list[TextContent]`**

- 状态：✅ 满足
- 现有 `server.py` 中所有 `_handle_*` 函数返回 `_ok(data)` 或 `_err(msg)`，这两个函数返回 `list[TextContent]`
- 本次改动不修改任何 `_handle_*` 函数
- `call_tool()` 中的异常处理（`MCPError`、`ValueError`、`Exception`）均通过 `_err()` 返回 `list[TextContent]`，不抛出未捕获异常

**约束 2：多租户 tenant_id 隔离**

- 状态：✅ 满足（需完成 Step 3 的 server.py 修改）
- `auth.py` 中间件：从 API Key 映射得到 tenant_id，注入 `request.state.tenant_id` 和 ContextVar
- `server.py` 修改：`call_tool()` 从 ContextVar 读取 tenant_id，客户端传入的 `tenant_id` 参数被静默删除
- `_cache_key()` 加入 tenant_id，防止跨租户缓存污染
- 验收 T1 最后一条：「传入两个不同企业的有效 API Key，返回的数据租户隔离」需要端到端测试验证

**约束 3：危险字符过滤在 HTTP 场景下如何体现**

- HTTP 模式下不存在 `shell=True` 风险（MCP Server 只接受结构化 JSON 参数，不执行 shell 命令）
- `tool arguments` 中的危险字符（`;`、`&&`、`|`、`` ` ``、`$`）在 MCP 协议层以 JSON 结构传输，不经过 shell 解析
- 现有 `executor.py` 中的危险字符过滤是 CLI 层的防护，与 MCP Server HTTP 模式无关
- MCP Server 中工具参数的合法性由 JSON Schema 中的 `type`、`minimum`、`maximum`、`pattern`、`enum`、`maxLength` 字段约束（已在 `mcp-tools.json` 中体现）
- 状态：✅ HTTP 场景下危险字符风险通过 JSON Schema 约束而非字符串过滤处理，设计合理

**约束 4：`docs/` 目录冻结**

- 状态：✅ 本次所有新建文件均在 `mcp_server/`、`build/m365-agent/`、`tests/` 下，不触碰 `docs/` 目录

**约束 5：Skills Store 双源头、Store URL 硬编码等**

- 状态：✅ 本次改动不涉及 Skills Store、`store_client.py`、`frontend/`

**发现的额外问题：`_cache_key()` 调用链不完整**

初始设计中只改了 `_cache_key()` 函数签名和 `_run_with_cache()` 签名，但漏掉了 `_get_cached_result()` 也依赖 `_cache_key()`。检查第 55-59 行：

```python
def _get_cached_result(key: str) -> list | None:
    cached = _cache.get(key)
    if cached and time.time() - cached[1] < _CACHE_TTL:
        return cached[0]
    return None
```

`_get_cached_result()` 接收已经包含 `tenant_id` 的 key，无需修改。调用链：
`_run_with_cache(name, args, tenant_id, fn)` → `_cache_key(name, args, tenant_id)` → `_get_cached_result(key)`
调用链完整，无遗漏。✅

---

### Round 3 对抗：「新入职工程师」视角

#### 发现的问题

**问题 3.1：Step 3 中 `_get_tenant_id` 循环导入风险**

`server.py` 在 `call_tool()` 内部 `from mcp_server.auth import _get_tenant_id`。`auth.py` 不导入 `server.py`，所以没有循环导入。但 `__main__.py` 先导入 `server.py`（`from .server import create_server`），再导入 `http_app.py`（`from .http_app import app`），`http_app.py` 导入 `auth.py`。调用链无循环。✅

但是，`server.py` 在模块级不导入 `auth.py`（只在 `call_tool()` 的 `_run()` 内部延迟导入），可以避免模块级循环导入问题。✅

**修正**：确保 `server.py` 中的 `from mcp_server.auth import _get_tenant_id` 放在 `_run()` 闭包内部（延迟导入），不放在文件顶部。已在第七节设计中体现。

---

**问题 3.2：工具名映射文档不够清晰**

PRD 中使用 `get_customer_overview` 等工具名，但 server.py 中 `_HANDLERS` 使用 `analytics_overview`。文档中决策 5 说明了映射关系，但开发者在实现 `mcp-tools.json` 时可能混淆。

**修正**：在 `mcp-tools.json` 的 `name` 字段中统一使用 `analytics_*`（server.py 现有 key），在 `description` 中使用用户友好的描述。`declarativeAgent.json` 的 `instructions` 中工具名也必须与 `_HANDLERS` key 一致（`analytics_*`）。已在第八节设计中完成，并加了注释说明。✅

---

**问题 3.3：render.yaml 的 startCommand 端口与 Render 实际端口不一致**

Render 注入的端口是 `$PORT`（通常为 `10000`），但 `render.yaml` 中 `envVars` 声明了 `PORT: "10000"`，同时 `startCommand` 使用 `--port $PORT`。这是正确的，但文档需要说明 Render 优先使用其自动注入的 `$PORT`，不用手动配置。

**修正**：在 `render.yaml` 注释中明确说明 Render 自动注入 `PORT` 环境变量，`envVars` 中的 `PORT: "10000"` 仅作文档目的（Render 实际会覆盖）。已在第九节 `render.yaml` 注释中体现。✅

---

**问题 3.4：Step 4 验证中后台进程未正确清理**

验证脚本中使用 `&` 后台启动，`kill %1` 可能因 job number 不准确而失败（如果有其他后台进程）。

**修正**：使用 `$!` 保存 PID：
```bash
python -m ... &
SERVER_PID=$!
sleep 3
# ... 测试 ...
kill $SERVER_PID
```
已在开发步骤的验证方式中修正为更健壮的写法。✅

---

**问题 3.5：`declarativeAgent.json` 的 `instructions` 字段需要转义**

JSON 文件中 `instructions` 是多行文本，包含中文、换行符、特殊符号（如 `⚠️`、`→`）。需要确保 JSON 编码正确（`\n` 换行，无裸换行符），且 `\u` 转义的 Unicode 字符在 M365 Copilot 中正确渲染。

**修正**：在 `declarativeAgent.json` 中 `instructions` 使用 `\n` 转义的单行字符串，避免 JSON 格式错误。已在第八节 `declarativeAgent.json` 中体现。✅ （实现时工具写入时使用 json.dumps 序列化确保转义正确）

---

**问题 3.6：缺少 `build/m365-agent/` 目录的图标文件说明**

`color.png`（192×192）和 `outline.png`（32×32）是 Teams App 验证的必须文件，但本文档没有给出具体的图标设计规格。

**修正**：补充图标规格说明：
- `color.png`：192×192px，PNG 格式，全彩图标，背景应为品牌色（SocialHub 蓝 `#0078D4`）
- `outline.png`：32×32px，PNG 格式，白色前景 + 透明背景，用于 Teams 侧边栏显示
- 可使用 Figma 或 Adobe Illustrator 导出，也可使用 Microsoft 提供的 [Teams App Icon Generator](https://dev.teams.microsoft.com/tools) 生成

---

**问题 3.7：stdio 模式在 server.py 修改后的回退路径**

修改后的 `call_tool()` 中：`tid = _get_tenant_id() or os.getenv("MCP_TENANT_ID", "")`。stdio 模式下 `_get_tenant_id()` 返回空字符串（ContextVar 默认值），回退到 `os.getenv("MCP_TENANT_ID", "")`。若环境变量也未设置，返回空字符串，`_cache_key()` 会产生 `":analytics_overview:{...}"` 格式的 key（tenant_id 为空字符串前缀）。

此时代码会触发新增的 `if not tid: return _err("Tenant not configured...")` 分支，导致所有工具调用失败。

**修正**：stdio 模式必须设置 `MCP_TENANT_ID` 环境变量（这是现有 CLAUDE.md 中声明的必须环境变量）。在 `__main__.py` 的 stdio 分支启动前增加检查：
```python
def _run_stdio() -> None:
    if not os.getenv("MCP_TENANT_ID"):
        logger.error("MCP_TENANT_ID 环境变量未设置，stdio 模式无法启动")
        sys.exit(1)
    # ... 继续启动
```
HTTP 模式下 `MCP_TENANT_ID` 用作单租户回退，不强制要求（`MCP_API_KEYS` 才是 HTTP 模式的主要配置）。已在第六节 `__main__.py` 修改中补充此检查（`_run_stdio()` 函数）。

---

## 附录：PRD 需求追溯矩阵

| PRD 章节 | 需求 | 实现文件 | 实现位置 |
|---|---|---|---|
| §3.1 工具清单 | 8 个核心工具 Schema | `build/m365-agent/mcp-tools.json` | 完整 8 工具 inputSchema |
| §3.2 declarativeAgent 配置 | JSON 配置文件 | `build/m365-agent/declarativeAgent.json` | 完整内容 |
| §3.2.1 完整 Instructions | 修正后 Instructions 文本 | `declarativeAgent.json` `instructions` 字段 | 含口径透明化、深链接、错误引导 |
| §3.3 部署流程 | 4 步 IT 管理员操作 | `build/m365-agent/` 打包 + 部署文档 | ZIP 包格式 |
| §3.4 API Key 认证 | Bearer token 解析 + tenant_id 注入 | `mcp_server/auth.py` | `APIKeyMiddleware.dispatch()` |
| §3.4 plugin.json auth 配置 | ApiKeyPluginVault + OAuthPluginVault | `build/m365-agent/plugin.json` | MVP 和 GA 两套版本 |
| §4.1 数据口径声明 | `*_definition` 字段规范 | `mcp-tools.json` description 字段 | 每个工具的 description 含口径说明 |
| §5.1 /health 端点规范 | 三态响应 (ok/degraded/down) | `mcp_server/http_app.py` `health()` | 含 checks 字段 |
| §5.2 错误响应规范 | 差异化错误消息 | `mcp_server/server.py` `_err()` + handler | 现有机制，HTTP 场景下继续有效 |
| §6.3 缓存 Key 租户隔离 | `_cache_key()` 加 tenant_id | `mcp_server/server.py` | 安全必改，第七节 |
| §6.3 传输层加密 | 全程 HTTPS | `render.yaml` Render Starter | Render 自动 TLS |
| §6.4 工具 Schema ≤ 3000 tokens | token 预算控制 | `mcp-tools.json` | 8 工具 Schema 设计精简 |
| §7 Render Starter 部署 | 非 Free 层 | `render.yaml` `plan: starter` | 无冷启动 |
| §7 /health 必须包含 | Render 部署探针 | `render.yaml` `healthCheckPath: /health` | 零停机部署 |
| §7 自有域名 | `mcp.socialhub.ai` | `manifest.json` `validDomains` | `plugin.json` `server_url` |
| 验收 T1 | HTTP MCP Server 可用 | Step 9 端到端验证 | 5 条验收检查 |
| 验收 T2 | Teams App 包完整 | Step 6 验证 | ZIP 包 + Validator |
| 验收 T4 | 安全验证 | Step 8 测试 + Step 9 验证 | 3 条安全用例 |

---

## CTO Round 1 修正

> 审查日期：2026-03-29
> 审查视角：找出技术方案中最薄弱的 3 个环节

### 薄弱环节 1：GA 版 Entra Token 验证代码存在严重安全漏洞

**问题定位**：第八节 `plugin.json GA 版本` 对应的 `auth.py` 扩展代码（第 1054 行）：

```python
payload = jwt.decode(token, options={"verify_signature": False})
```

这是一个**签名验证跳过**的严重安全缺陷。代码注释写「实际生产中需要从 JWKS 端点获取公钥验证签名」，但在 MVP 文档中给出了跳过签名验证的示例代码，这会造成以下风险：

1. 任何人可以伪造 JWT token，包含任意 `tid` claim，直接绑定到任意企业 tenant
2. 攻击者可构造 `{"tid": "target-enterprise-guid"}` 的未签名 token，获取目标企业数据
3. 文档中标注「EA 结束前完成」——如果 EA 期间直接使用此代码段，生产环境将零安全保护

**修正要求**：

此代码段必须替换为正确的 JWKS 验证实现骨架，并在代码注释中明确禁止使用 `verify_signature: False`。正确的骨架如下：

```python
# mcp_server/auth.py — Entra ID token 验证（GA 阶段）
# 依赖：pip install msal PyJWT cryptography
import jwt
from msal import PublicClientApplication  # 仅用于 JWKS 获取

# Entra JWKS 端点（微软公钥，用于验证 token 签名）
_ENTRA_JWKS_URI = "https://login.microsoftonline.com/common/discovery/v2.0/keys"
# 注意：应使用 jwt.PyJWKClient 缓存公钥，避免每次请求都拉取 JWKS

def _verify_entra_token(token: str) -> str | None:
    """
    验证 Entra ID Bearer token，提取 tenant_id。
    必须验证签名，禁止使用 verify_signature=False。
    """
    try:
        jwks_client = jwt.PyJWKClient(_ENTRA_JWKS_URI, cache_jwk_set=True, lifespan=3600)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_exp": True},  # 强制验证过期时间
        )
        entra_tenant_id = payload.get("tid", "")
        return _ENTRA_TENANT_MAP.get(entra_tenant_id)
    except Exception as e:
        logger.warning("Entra token 验证失败: %s", type(e).__name__)
        return None
```

**优先级**：P0（GA 阶段开始实现 OAuthPluginVault 之前必须解决）。原文档中的 `verify_signature: False` 示例代码已被本节标记为不可直接使用。

---

### 薄弱环节 2：`_API_KEY_MAP` 进程级单例在 Key 轮换时存在内存残留窗口

**问题定位**：`auth.py` 设计中：

```python
# 进程级映射表，模块首次导入时加载
_API_KEY_MAP: dict[str, str] = _load_api_key_map()
```

`APIKeyMiddleware.__init__()` 中：`self._key_map = _API_KEY_MAP`（直接引用模块级变量）

**风险链**：

1. 企业 A 的 API Key 泄露，SocialHub 运营更新 `MCP_API_KEYS` 环境变量
2. Render 触发重部署，部署过程约 60-90 秒（含 `/health` 探针通过）
3. **在重部署完成前**，旧 Key 仍有效——这在 Round 1 对抗中已被识别为 P2 技术债，但问题比文档描述的更严重：
4. Render 使用**零停机部署（Zero-Downtime Deploy）**：新实例启动并通过健康检查后，旧实例才下线。这意味着旧 Key 的有效窗口不是「2-3 分钟」，而是新实例启动时间（~3 分钟）+ 旧实例排空时间（最多 30 秒），合计约 3.5-4 分钟
5. 更关键的是：如果 `autoDeploy: true` 被意外禁用（如 Render 平台问题），旧 Key 永久有效

**修正方案（MVP 可接受的最小改动）**：

在 `auth.py` 中增加 `reload_api_key_map()` 函数，并在 `http_app.py` 的 `/admin/reload-keys` 端点中暴露（仅限 SocialHub 内部 IP 或通过独立 Admin Secret 保护）：

```python
# auth.py 新增
def reload_api_key_map() -> int:
    """重新加载 API Key 映射（无需重部署）。返回加载的 key 数量。"""
    global _API_KEY_MAP
    new_map = _load_api_key_map()
    _API_KEY_MAP = new_map
    # 更新所有中间件实例（通过模块级变量引用，中间件下次请求时读取）
    return len(new_map)
```

配合 `render.yaml` 中增加 `POST /admin/reload-keys` 的 Admin Secret 保护端点。Render 重部署仍是主要轮换路径，此端点作为紧急失效的备用通道。

**优先级**：P1（EA 期间实现，不阻塞 MVP）。

---

### 薄弱环节 3：工具名双轨制（PRD 名 vs server.py 名）在多文件中的一致性没有测试保障

**问题定位**：决策 5 和 Round 3 问题 3.2 均识别了工具名映射问题，但修正只停留在「文档注释」层面，没有自动化验证：

- `mcp-tools.json` 中的 `name` 字段（`analytics_*`）
- `declarativeAgent.json` 的 `instructions` 中引用的工具名（`analytics_*`）
- `plugin.json` 的 `runtimes[].allowed_tools` 和 `functions[].name`（`analytics_*`）
- `server.py` 中 `_HANDLERS` dict 的 key

四个地方必须完全一致，**任何一处拼写错误都会导致 M365 Copilot 静默失败**（工具调用返回空，用户看到「数据查询失败」但没有有意义的错误信息）。

目前的测试计划（`test_auth.py` + `test_cache_isolation.py`）没有覆盖这个一致性验证。

**修正要求**：在 `tests/` 中增加 `test_tool_schema_consistency.py`：

```python
# tests/test_tool_schema_consistency.py
"""
验证 mcp-tools.json、plugin.json 中的工具名与 server.py _HANDLERS 完全一致。
这是防止「工具名不一致导致 M365 Copilot 静默失败」的回归测试。
"""
import json
from pathlib import Path

def test_tool_names_consistent_with_handlers():
    """mcp-tools.json 中的工具名必须在 server.py _HANDLERS 中存在。"""
    from mcp_server.server import _HANDLERS

    tools_path = Path("build/m365-agent/mcp-tools.json")
    data = json.loads(tools_path.read_text(encoding="utf-8"))
    declared_names = {t["name"] for t in data["tools"]}
    handler_names = set(_HANDLERS.keys())

    missing = declared_names - handler_names
    assert not missing, f"mcp-tools.json 声明的工具在 _HANDLERS 中不存在: {missing}"

def test_plugin_json_tool_names_consistent():
    """plugin.json allowed_tools 中的工具名必须与 mcp-tools.json 一致。"""
    plugin_path = Path("build/m365-agent/plugin.json")
    tools_path = Path("build/m365-agent/mcp-tools.json")

    plugin = json.loads(plugin_path.read_text(encoding="utf-8"))
    tools = json.loads(tools_path.read_text(encoding="utf-8"))

    declared_names = {t["name"] for t in tools["tools"]}
    plugin_names = set()
    for runtime in plugin.get("runtimes", []):
        plugin_names.update(runtime.get("allowed_tools", []))

    assert declared_names == plugin_names, (
        f"plugin.json 与 mcp-tools.json 工具名不一致。"
        f"仅在 plugin: {plugin_names - declared_names}，"
        f"仅在 tools: {declared_names - plugin_names}"
    )
```

**开发步骤调整**：此测试文件加入 Step 8，与 `test_auth.py` 和 `test_cache_isolation.py` 同步编写和执行。PRD 验收 T2（Teams App 包完整）补充一条：`pytest tests/test_tool_schema_consistency.py` 通过。

**优先级**：P0（防止上线后工具静默失败，成本极低）。

---

## CTO Round 2 修正

> 审查日期：2026-03-29
> 审查视角：「生产事故回溯」— 上线后第 3 个月客户投诉「数据不对」，能在 30 分钟内定位根因吗？

### 场景还原：第 3 个月某周一，客户投诉「留存率数字和 BI 系统对不上，差了 5 个百分点」

**现有排障链路逐步走查**：

#### 步骤 1（0-5 分钟）：确认是否服务端问题

- 访问 `https://mcp.socialhub.ai/health` → 返回 `{"status": "ok"}`
- **问题**：`/health` 端点当前只检查「analytics 是否加载」和「MCP_API_KEYS 是否配置」，**不检查上游数据连通性**。`health()` 函数中 `checks["analytics"]` 只判断 `_analytics_ready.is_set()`，而 `probe_upstream_mcp()` 的结果只写入日志，不反映在 `/health` 响应的 `checks` 字段中
- **结论**：`/health` 显示 `ok`，但无法判断「数据层是否有问题」——排障人员会误判为「服务正常，数据问题在 SocialHub 主产品侧」，白白浪费 10-15 分钟

#### 步骤 2（5-15 分钟）：复现问题，确定是哪个工具、哪个参数

- 打开 M365 Copilot，重复问客户的查询
- **问题 1**：MCP 工具调用日志在 Render 的 Log 控制台中，但 Render Starter 层日志只保留 **7 天**，第 3 个月某次 3 天前的历史调用**根本不存在**
- **问题 2**：当前日志格式（`logging.basicConfig`）只记录时间+级别+模块+消息，没有结构化字段。如果需要查询「tenant-acme-001 在 2026-03-26 10:30 调用 analytics_retention 的参数」，只能肉眼扫描非结构化日志
- **问题 3**：工具调用的**入参和出参**没有日志记录。`server.py` 中 `call_tool()` 只在错误时写日志，正常调用无审计日志

#### 步骤 3（15-25 分钟）：确定「数据不对」是数据问题还是口径问题

- 如果是口径问题（留存率计算逻辑不一致），需要看工具返回的 `period_definition` 字段
- **问题**：没有任何工具调用的响应内容被记录。排障人员无法重现「当时工具返回了什么」，只能重新调用工具，但参数可能和客户当时用的不一样（用户自然语言被 M365 Copilot 翻译成参数，这个翻译结果是什么，不可见）

#### 步骤 4（25+ 分钟）：定位根因

- 无法在 30 分钟内定位，因为缺少三个关键信息：
  1. 工具调用的完整参数（M365 Copilot 实际传了什么 days/start_date/end_date）
  2. 工具返回的完整响应（含 period_definition）
  3. 缓存命中情况（客户看到的是实时数据还是 15 分钟前的缓存数据）

---

### 修正方案：最小可观测性增强（不引入外部日志服务）

#### 修正 2.1：结构化访问日志（在现有 `http_app.py` 中增加）

在 `APIKeyMiddleware.dispatch()` 成功认证后，记录结构化日志：

```python
# auth.py dispatch() 成功认证后
logger.info(
    "tool_call_auth ok tenant=%s path=%s method=%s",
    tenant_id,
    request.url.path,
    request.method,
)
```

在 `server.py` 的 `call_tool()` 中，在 `_run()` 闭包执行前后各记录一条：

```python
# call_tool() 中，_run() 执行前（已有 tid 和 name）
logger.info(
    "tool_call_start tool=%s tenant=%s args_keys=%s",
    name,
    tid,
    list(safe_args.keys()),  # 不记录具体值，防止 PII 泄露，只记录参数名
)

# _run() 执行后（在 finally 块中）
elapsed_ms = int((time.monotonic() - t0) * 1000)
logger.info(
    "tool_call_end tool=%s tenant=%s elapsed_ms=%d cache_hit=%s",
    name,
    tid,
    elapsed_ms,
    cache_hit,  # 需要在 _run_with_cache() 中返回是否命中缓存
)
```

**注意**：只记录参数名（`args_keys`），不记录参数值，防止敏感业务数据（如日期范围、客户规模）出现在日志中。

#### 修正 2.2：`/health` 端点增加上游连通性检查

当前 `health()` 函数没有将 `probe_upstream_mcp()` 结果写入 `checks`。修正：

```python
# http_app.py health() 函数中增加
from mcp_server.server import probe_upstream_mcp

# 缓存上次探测结果（避免每次 /health 都触发上游网络请求）
_last_probe_result: tuple[bool, str] = (True, "not checked yet")
_last_probe_time: float = 0.0

async def health(request: Request) -> JSONResponse:
    global _last_probe_result, _last_probe_time
    now = time.monotonic()
    if now - _last_probe_time > 60:  # 最多 60 秒检查一次
        _last_probe_result = probe_upstream_mcp()
        _last_probe_time = now

    ok, msg = _last_probe_result
    checks["upstream"] = "ok" if ok else f"error: {msg[:80]}"  # 截断防止泄露内部细节
    # ... 其余逻辑不变
```

这样排障时第一步访问 `/health` 就能看到上游连通性状态，立即判断是「SocialHub MCP Server 问题」还是「上游数据源问题」。

#### 修正 2.3：缓存命中情况可见

`_run_with_cache()` 修改为返回 `(result, cache_hit: bool)`，在 `tool_call_end` 日志中记录 `cache_hit`。当客户投诉「数据和 BI 对不上」时，如果日志显示 `cache_hit=True`，可以立即判断「客户看到的是 15 分钟前的缓存数据」，定位方向是「缓存时间窗口内数据发生了突变」。

#### 修正 2.4：为排障预留参数快照机制（P2，不阻塞 MVP）

MVP 不实现，但需要在架构上预留：当工具返回空结果或错误时，记录完整的 `args` 到日志（此时无 PII 风险，因为是错误场景，且参数是业务查询条件而非个人信息）。

```python
# 仅在错误路径记录完整参数
if result_is_error:
    logger.warning(
        "tool_call_error_detail tool=%s tenant=%s full_args=%s ref_id=%s",
        name, tid, json.dumps(safe_args), ref_id
    )
```

---

### 修正后的 30 分钟排障链路

| 时间 | 操作 | 现在能得到的信息 |
|---|---|---|
| 0-2 分钟 | `curl /health` | 服务状态 + 上游连通性（修正 2.2 后） |
| 2-8 分钟 | 查 Render 日志，搜 `tenant=acme-001 tool=analytics_retention` | 找到最近调用记录，确认参数名和耗时 |
| 8-15 分钟 | 查 `cache_hit` 字段 | 判断是实时数据还是缓存数据 |
| 15-20 分钟 | 用相同参数重调工具，对比 `period_definition` 口径 | 判断是口径差异还是数据计算错误 |
| 20-30 分钟 | 如果口径一致但数字不同，升级到上游数据源排查 | 确定根因层级（MCP Server / 上游数据 / 口径理解） |

**结论**：修正 2.1-2.3 实现后，30 分钟定位概率从约 30% 提升到约 80%。剩余 20% 的场景（如上游数据源静默返回错误数据）需要上游数据源侧的日志配合，超出 MCP Server 的可观测性边界。

**开发成本**：修正 2.1-2.3 合计约 2-3 小时，不增加外部依赖，纯日志增强。建议加入 Step 4（http_app.py）和 Step 3（server.py）的实现范围。

---

## CTO Round 3 修正

> 审查日期：2026-03-29
> 审查视角：「开发效率」— 10 步顺序是否最优？哪些可以并行？Python 熟悉但 M365 不熟悉的工程师需要哪些额外说明？

### 分析：当前 10 步顺序的问题

**现有顺序**：
```
Step 1: 升级依赖（15分钟）
Step 2: auth.py（2-3小时）
Step 3: server.py 修改（1-2小时）
Step 4: http_app.py（3-4小时）
Step 5: __main__.py 修改（1小时）
Step 6: build/m365-agent/ 文件（2-3小时）
Step 7: render.yaml（30分钟）
Step 8: 测试文件（2-3小时）
Step 9: Render 部署验证（2-3小时）
Step 10: M365 端到端测试（3-4小时）
```

**问题 1：关键阻塞路径识别错误**

当前顺序将「M365 测试环境申请」放到了 Step 10 才开始。但 Microsoft 365 开发者账号申请（如果没有）需要 1-3 个工作日审批，「Teams Admin Center 权限」在企业环境中需要 IT 管理员介入。如果 Step 10 才发现「测试账号还没申请」，整个 pipeline 会在最后一步卡住，浪费前 9 步的工作。

**问题 2：Step 6（M365 文件）被低估了**

`build/m365-agent/` 文件创建，特别是 `plugin.json` 的 `auth.reference_id` 配置、`declarativeAgent.json` 的 schema 版本对齐，是需要工程师熟悉 M365 Agents Toolkit（ATK）的。对 Python 工程师来说，这步的时间估算（2-3 小时）严重低估了「学习 ATK + 理解 ApiKeyPluginVault 注册流程」的时间，实际可能需要 1-2 天。

**问题 3：可并行的步骤没有标注**

Step 2（auth.py）和 Step 3（server.py）之间有依赖（server.py 需要导入 auth.py 的 `_get_tenant_id`），但 Step 6（m365-agent 文件）和 Step 7（render.yaml）完全可以与 Step 1-5 并行进行，没有代码依赖。

**问题 4：Step 8（测试文件）应该与实现步骤同步，不是最后才写**

TDD 原则：`test_cache_isolation.py` 应该在 Step 3 之前写好（定义验收标准），`test_auth.py` 应该在 Step 2 之前写好。测试放在 Step 8 意味着「先实现，后写测试」，这会导致测试用例可能遗漏边界情况。

---

### 修正后的最优执行顺序

#### 前置工作（D-3 开始，与开发并行）

**P0 前置（开发开始前必须启动，否则 Step 10 会阻塞）**：

```
[前置 A] M365 开发者账号申请（如无）
  → 申请 Microsoft 365 Developer Program 免费试用
  → 地址：https://developer.microsoft.com/microsoft-365/dev-program
  → 申请到账号约 1-2 个工作日
  → 该账号包含 25 个 M365 E5 许可证，含 M365 Copilot 测试功能

[前置 B] 理解 Teams App 部署的两种方式
  → 方式 1：Teams Admin Center 上传（需要 Teams 管理员权限）
  → 方式 2：直接在 Teams 客户端「上传自定义应用」（个人测试，无需管理员）
  → MVP 测试阶段用方式 2 即可，不需要管理员权限
  → 文档：https://learn.microsoft.com/microsoftteams/platform/concepts/deploy-and-publish/apps-upload

[前置 C] 安装 M365 Agents Toolkit（ATK） VS Code 插件
  → 安装 Teams Toolkit 插件（支持 API Key vault 注册和本地调试）
  → 用于 Step 6 的 plugin.json auth.reference_id 配置
```

#### 重新排序后的 10 步（最优并行路径）

```
Week 1, Day 1 上午（2小时）:
  Step 1: 升级依赖 + pyproject.toml（15分钟）
  + 立刻开始 [前置 A]（不阻塞开发，后台等待审批）

Week 1, Day 1 下午（6小时）:
  Step 2A（TDD先行）: 编写 tests/test_auth.py 的测试用例（不运行，先定义验收标准）
  Step 2B: 实现 auth.py（按测试用例验收）
  Step 2C: 运行 tests/test_auth.py 全部通过

Week 1, Day 2 上午（4小时）:
  Step 3A（TDD先行）: 编写 tests/test_cache_isolation.py + tests/test_tool_schema_consistency.py 框架
  Step 3B: 修改 server.py（_cache_key + _run_with_cache + call_tool + Round 2 修正的日志增强）
  Step 3C: 运行现有 pytest tests/ -x -q（回归验证）

  [并行，可交给另一人] Step 6: 创建 build/m365-agent/ 文件（不依赖代码）
  [并行，可交给另一人] Step 7: 创建 render.yaml（不依赖代码）

Week 1, Day 2 下午（4小时）:
  Step 4: 实现 http_app.py（含 Round 2 修正的 /health 上游检查和结构化日志）
  Step 5: 修改 __main__.py

Week 1, Day 3 上午（3小时）:
  Step 8: 完成所有测试文件（test_auth.py 补全 + test_cache_isolation.py + test_tool_schema_consistency.py）
  运行 pytest tests/ 全绿

Week 1, Day 3 下午（3小时）:
  Step 9: Render 部署 + 端到端 curl 验证

Week 1 结束 or Week 2 Day 1（4小时）:
  Step 10: M365 端到端测试（依赖前置 A 账号已就绪）
```

**总耗时估算**：约 4-5 个工作日（比原始 10 步总耗时 20-26 小时更现实的日历时间）

---

### 对 Python 熟悉但 M365 不熟悉工程师的补充说明

以下内容原文档缺失或不够详细，会导致 M365 新手卡住：

#### 补充说明 A：`ApiKeyPluginVault` 的 `reference_id` 怎么得到

原文档 `plugin.json` 中写的是 `"reference_id": "${{SOCIALHUB_API_KEY}}"`，但没有解释这个 `${{...}}` 是什么语法，如何注册。

**实际流程**：
1. 在 VS Code 中安装 Teams Toolkit (ATK) 插件
2. 打开 Command Palette → `Teams: Add API Key`
3. ATK 会在 `env/.env.local` 中生成 `SOCIALHUB_API_KEY=<your-actual-key>`
4. `plugin.json` 中的 `${{SOCIALHUB_API_KEY}}` 是 ATK 的环境变量引用语法，ATK 打包时会自动替换
5. 生产部署时，在 ATK 的 `env/.env.production` 中填写实际 API Key

**如果不用 ATK**：可以直接在 `plugin.json` 中硬编码实际 `reference_id` 字符串（ATK 会生成一个 GUID 格式的 reference_id，需要在 Teams Developer Portal 中注册对应的 API Key vault 条目）。这个流程文档极少，建议 MVP 阶段使用 ATK 完成注册。

#### 补充说明 B：Teams App 上传后找不到 Agent 的排查

Teams App 上传成功但在 M365 Copilot 里看不到 Agent，是 M365 新手最常见的卡点：

1. 上传后 Agent 可能需要等待 **最多 24 小时** 才在 M365 Copilot Chat 的应用列表中出现（微软官方文档说明）
2. 测试时建议：上传 App → 在 Teams 客户端左侧边栏找「应用」→ 搜索「SocialHub」→ 点击「打开」→ 这会直接打开 Agent 的聊天界面，无需等待 Copilot 列表更新
3. 如果 Agent 出现但工具调用没有响应：检查 `plugin.json` 中的 `server_url` 是否正确，以及 API Key 是否通过 ATK 正确注册

#### 补充说明 C：`mcp-tools.json` 不是标准 MCP 规范文件

原文档中 `mcp-tools.json` 的格式是 M365 Copilot plugin 的**专有格式**，不是 MCP 协议的标准文件。它的作用是让 M365 Copilot 的 tool routing 做语义匹配，与 MCP Server 的 `tools/list` 响应是独立的。

这意味着：
- `mcp-tools.json` 中的工具名必须与 MCP Server `tools/list` 返回的名称一致（这就是 Round 1 薄弱环节 3 中测试的原因）
- 但 `mcp-tools.json` 的 `inputSchema` 可以比实际工具的 Schema 更简洁（M365 Copilot 用它做路由，不用它做参数验证）
- M365 Copilot 在决定调用哪个工具时，会用 `mcp-tools.json` 中的 `description` 做语义匹配，所以 description 的质量直接影响工具路由准确率

#### 补充说明 D：本地调试 M365 Agent 的方法（不需要每次都部署 Render）

原文档的 Step 10 假设工程师已经部署到 Render，但调试阶段在本地运行 HTTP 服务然后用 M365 测试会更快：

1. 安装 `ngrok`（或 `cloudflared`）：`pip install pyngrok`
2. 本地启动 MCP HTTP Server：`python -m mcp_server --transport http --port 8090`
3. 创建公网隧道：`ngrok http 8090` → 得到 `https://abc123.ngrok.io` 临时 URL
4. 临时修改 `plugin.json` 中的 `server_url` 为 ngrok URL
5. 重新打包 ZIP，上传到 Teams
6. 在 M365 Copilot 中测试
7. ngrok URL 每次重启变化，所以**调试完成后必须改回 `https://mcp.socialhub.ai/mcp`**

**注意**：ngrok 免费版每次隧道重启会更换 URL，调试后必须改回正式 URL 再打包提交给客户。这个细节不注意会导致给客户的 ZIP 包里还是 ngrok URL。

---

### 开发效率总结

| 优化项 | 原方案 | 修正后 |
|---|---|---|
| M365 账号申请 | Step 10 才发现需要 | D-3 前置启动 |
| Step 6+7 与主线并行 | 串行 | 可并行（另一人或下午时段） |
| TDD 顺序 | 先实现后测试 | 先写测试用例框架，再实现 |
| M365 新手最大卡点 | 无说明 | 4 条补充说明覆盖常见坑 |
| 本地调试路径 | 只有 Render 部署路径 | 增加 ngrok 本地调试方法 |
| 预期日历时间 | 未明确 | 约 4-5 个工作日（单人） |