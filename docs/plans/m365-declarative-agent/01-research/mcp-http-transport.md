# MCP HTTP Streamable Transport 规范

> 调研日期：2026-03-29
> 适用规范版本：MCP spec 2025-03-26（取代 2024-11-05 的 HTTP+SSE transport）
> Python SDK 最低版本要求：mcp >= 1.8.0（2025-05-08 发布）

---

## 协议端点规范

### 核心设计原则

HTTP Streamable Transport（2025-03-26 spec）用单一 HTTP 端点（通常为 `/mcp`）替代了旧版 SSE transport 的双端点设计（`GET /sse` + `POST /messages`）。所有 MCP 流量均通过同一路径以 JSON-RPC 2.0 / UTF-8 编码传输。服务器按需将响应升级为 SSE 流。

### 端点行为详解

#### POST /mcp — 主要请求端点

客户端通过 POST 发送所有 MCP 消息（initialize、tools/call、tools/list 等）。

**请求格式：**
```
POST /mcp HTTP/1.1
Content-Type: application/json
Accept: application/json, text/event-stream
Mcp-Session-Id: <session_id>   （初始化后必须携带）
Authorization: Bearer <token>   （认证头，可选但推荐）

{ "jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": { ... } }
```

**响应行为（服务器可选择其一）：**

| 场景 | 响应方式 | Content-Type |
|---|---|---|
| 简单请求/响应 | 直接返回 JSON | `application/json` |
| 需要流式输出 | 升级为 SSE 流 | `text/event-stream` |
| 消息已接收但异步处理 | 202 Accepted，空 body | — |

**初始化响应示例（包含 session ID）：**
```
HTTP/1.1 200 OK
Content-Type: application/json
Mcp-Session-Id: a1b2c3d4-e5f6-7890-abcd-ef1234567890

{ "jsonrpc": "2.0", "id": 1, "result": { "protocolVersion": "2025-03-26", ... } }
```

#### GET /mcp — SSE 流订阅（可选）

客户端可以通过 GET 建立长连接 SSE 流，用于接收服务器主动推送的通知。

**请求格式：**
```
GET /mcp HTTP/1.1
Accept: text/event-stream
Mcp-Session-Id: <session_id>
Last-Event-ID: <last_event_id>   （断线重连时携带）
```

**响应：**
```
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache

data: {"jsonrpc":"2.0","method":"notifications/progress","params":{...}}

data: {"jsonrpc":"2.0","method":"notifications/tools/list_changed","params":{}}
```

若服务器不支持 GET，应返回 `405 Method Not Allowed`。

#### DELETE /mcp — 会话终止（可选）

客户端在不再需要某会话时，应发送 DELETE 请求显式关闭它。

```
DELETE /mcp HTTP/1.1
Mcp-Session-Id: <session_id>
```

服务器应返回 `200 OK` 或 `204 No Content`。

### Session ID 管理规则

- 服务器在初始化响应中通过 `Mcp-Session-Id` 响应头返回 session ID（可选，stateless 模式不需要）
- Session ID 应为全局唯一且密码学安全的值（UUID v4、JWT 或哈希值）
- 客户端在初始化完成后的**所有后续请求**中必须携带 `Mcp-Session-Id` 头
- 若服务器返回 `404 Not Found`（session 过期），客户端必须重新发送不带 session ID 的 `initialize` 请求
- 服务器可以随时终止 session

### Stateless 模式（推荐用于生产/无服务器部署）

在 `stateless_http=True` 模式下，每个 POST 请求创建独立的 ServerSession，不维护跨请求状态。没有 session ID，没有 GET 订阅端点，完全支持水平扩展和负载均衡。

---

## Python SDK 实现方式

### 依赖安装

```bash
# 最低要求（mcp >= 1.8.0 包含 HTTP Streamable Transport 支持）
pip install "mcp>=1.8.0"

# 或带可选 CLI 工具
pip install "mcp[cli]>=1.8.0"

# 自动安装的核心依赖（无需手动指定）：
# - starlette（ASGI 框架，SDK 内置使用）
# - anyio（异步运行时）
# - uvicorn（需单独安装，用于生产部署）
pip install uvicorn
```

### 方式 A：最简单 — mcp.run() 直接启动（推荐快速原型）

```python
# mcp_server/http_server.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "SocialHub Analytics",
    stateless_http=True,   # 推荐：每请求独立 session，支持水平扩展
    json_response=True,    # 推荐：返回 JSON 而非 SSE（简化客户端）
    host="0.0.0.0",
    port=8090,
)

@mcp.tool()
def get_overview(tenant_id: str) -> str:
    """获取总览数据"""
    return "..."

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
    # 等价于: uvicorn 监听 0.0.0.0:8090，路径 /mcp
```

启动后可访问：`http://0.0.0.0:8090/mcp`

### 方式 B：挂载到 Starlette/FastAPI（推荐生产）

此方式允许在 MCP 之外添加 `/health`、CORS 中间件、API Key 中间件等。

```python
# mcp_server/http_app.py
import contextlib
import os
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from mcp.server.fastmcp import FastMCP

# --- 创建 MCP 实例 ---
mcp = FastMCP(
    "SocialHub Analytics MCP",
    stateless_http=True,
    json_response=True,
)

# --- 注册工具（或从 server.py 导入） ---
@mcp.tool()
def get_overview(tenant_id: str) -> str:
    """获取客户总览"""
    return "..."

# --- 健康检查端点 ---
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "socialhub-mcp"})

# --- Lifespan（管理 session manager 生命周期） ---
@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    async with mcp.session_manager.run():
        yield

# --- 组装 Starlette App ---
app = Starlette(
    routes=[
        Route("/health", health),
        Mount("/mcp", app=mcp.streamable_http_app()),
    ],
    lifespan=lifespan,
)

# --- CORS 中间件（必须在最外层） ---
app = CORSMiddleware(
    app,
    allow_origins=["*"],           # 生产环境应限制来源
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Mcp-Session-Id"],  # 必须暴露此头
    max_age=86400,
)
```

启动：
```bash
uvicorn mcp_server.http_app:app --host 0.0.0.0 --port 8090
```

MCP 端点：`https://your-domain.com/mcp`
健康检查：`https://your-domain.com/health`

### 方式 C：复用现有 server.py 工具（适用于本项目）

本项目 `mcp_server/server.py` 已有 `mcp = FastMCP(...)` 实例和 36+ 工具定义（通过 `@mcp.tool()` 装饰器注册）。只需在启动入口中改变 transport 即可：

```python
# mcp_server/__main__.py（修改版）
import sys
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()

    if args.transport == "stdio":
        # 现有逻辑不变
        from mcp_server.server import mcp
        mcp.run(transport="stdio")
    elif args.transport == "http":
        from mcp_server.http_app import app  # 方式 B 的 app
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=args.port)

if __name__ == "__main__":
    main()
```

### Stateless 模式 vs 有状态模式对比

| 特性 | stateless_http=True | stateless_http=False（默认） |
|---|---|---|
| Session ID | 无 | 有，需客户端携带 |
| GET /mcp 订阅 | 不支持 | 支持 |
| 水平扩展 | 完全支持 | 需 sticky session |
| 服务器通知推送 | 不支持 | 支持 |
| M365 Copilot 兼容性 | 兼容（推荐） | 兼容 |
| 适用场景 | 无服务器、Render | 本地开发、有状态工作流 |

---

## CORS 配置要求

### 必须配置的 CORS 参数

```python
CORSMiddleware(
    app,
    allow_origins=["*"],                   # 或指定 M365 Copilot 域名
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Accept",
        "Authorization",
        "X-API-Key",
        "Mcp-Session-Id",
        "Last-Event-ID",                   # GET 断线重连需要
    ],
    expose_headers=["Mcp-Session-Id"],     # 关键：浏览器必须能读此头
    max_age=86400,
)
```

### 关键注意事项

1. **`expose_headers` 必须包含 `Mcp-Session-Id`**：若不暴露，浏览器端（M365 Copilot WebClient）将无法读取 session ID，导致后续请求均无 session ID，服务器会不断创建新 session。

2. **`allow_methods` 必须包含 DELETE**：客户端需要 DELETE 来关闭 session，部分 CORS 配置只允许 GET/POST 会导致问题。

3. **`allow_headers` 必须包含 `Last-Event-ID`**：SSE 断线重连使用此头。

4. **对 M365 Copilot**：目前 M365 Copilot 作为服务端调用，不受浏览器 CORS 策略限制，但为兼容 MCP Inspector 等调试工具，仍建议配置完整 CORS。

5. **中间件顺序**：CORS 中间件必须是最外层（最先处理请求），API Key 中间件在 CORS 之后。

---

## 认证集成方式

### 方式 1：Starlette 自定义中间件（推荐本项目）

```python
# mcp_server/auth.py
import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

VALID_API_KEYS = {
    # api_key -> tenant_id 映射（生产环境应从数据库读取）
    os.getenv("API_KEY_TENANT_001", ""): "tenant_001",
    os.getenv("API_KEY_TENANT_002", ""): "tenant_002",
}

class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 健康检查端点跳过认证
        if request.url.path == "/health":
            return await call_next(request)

        # 支持 X-API-Key 或 Authorization: Bearer <key>
        api_key = (
            request.headers.get("X-API-Key")
            or request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        )

        if not api_key or api_key not in VALID_API_KEYS:
            return JSONResponse(
                {"error": "Unauthorized", "code": 401},
                status_code=401
            )

        # 将 tenant_id 注入请求 state，工具处理器可读取
        request.state.tenant_id = VALID_API_KEYS[api_key]
        return await call_next(request)
```

集成到 Starlette App：
```python
from starlette.middleware import Middleware
from mcp_server.auth import APIKeyMiddleware

app = Starlette(
    routes=[...],
    middleware=[
        Middleware(APIKeyMiddleware),
    ],
    lifespan=lifespan,
)
```

### 方式 2：FastMCP 内置 Bearer Auth（JWT，适合复杂场景）

```python
from mcp.server.auth.providers.bearer import BearerAuthProvider, RSAKeyPair

key_pair = RSAKeyPair.generate()
auth_provider = BearerAuthProvider(public_key=key_pair.public_key)

mcp = FastMCP("SocialHub", auth=auth_provider)
```

### 方式 3：依赖注入读取 API Key（工具级别验证）

```python
from fastmcp.server.dependencies import get_http_request

@mcp.tool()
async def get_customers(tenant_id: str) -> str:
    request = get_http_request()
    api_key = request.headers.get("X-API-Key", "")
    # 验证 api_key 并解析实际 tenant_id
    ...
```

### M365 ApiKeyPluginVault 集成

M365 Copilot 通过 `ApiKeyPluginVault` 将 API Key 注入请求头。在 `plugin.json` 中配置：

```json
{
  "auth": {
    "type": "ApiKeyPluginVault",
    "reference_id": "${{SOCIALHUB_API_KEY}}"
  }
}
```

M365 会自动将 API Key 以 `Authorization: Bearer <key>` 或自定义头发送，因此服务器端同时支持两种头格式最稳妥（见方式 1 中的双格式解析）。

### API Key 与 tenant_id 绑定策略

本项目硬约束：不允许跨租户查询，tenant_id 必须从 API Key 解析，不能由客户端传入。

推荐实现：
- 环境变量：`SOCIALHUB_API_KEY_{TENANT}=<key>` 或统一 `API_KEYS={"key1":"tenant1","key2":"tenant2"}`
- 工具处理器从 `request.state.tenant_id` 读取，禁止信任客户端传入的 `tenant_id` 参数

---

## 与 stdio transport 的差异（影响现有代码哪些部分）

### 协议层差异

| 维度 | stdio transport（现有） | HTTP Streamable Transport（目标） |
|---|---|---|
| 连接方式 | 父进程 stdin/stdout 管道 | HTTP 长连接或无状态 POST |
| 生命周期 | 进程级（客户端启动时 fork） | 请求级（stateless）或 session 级 |
| 并发客户端 | 1 个（单进程） | 多个（ASGI 异步处理） |
| 认证 | 无（进程隔离） | 必须通过 HTTP 头认证 |
| 日志输出 | stdout/stderr 均可 | **不能写入 stdout**，必须用 logging |

### 对 `mcp_server/server.py` 的影响

`server.py` 中的工具定义（`@mcp.tool()` 装饰器）**完全不需要修改**，FastMCP 负责 transport 层的适配。

需要修改的部分：

1. **`mcp_server/__main__.py`**：当前只有 `mcp.run(transport="stdio")`，需增加 `--transport http` 分支
2. **`tenant_id` 来源**：当前从环境变量 `MCP_TENANT_ID` 读取，HTTP 模式下需改为从 API Key 解析，禁止客户端传参
3. **日志**：检查是否有直接 `print()` 到 stdout 的代码（HTTP 模式下会污染响应）
4. **缓存层**：15 分钟 TTL 内存缓存在 stateless 模式下每请求独立，会失效 — 需评估是否改为跨请求共享缓存（如 Redis 或进程级共享）

### 对 `cli/api/mcp_client.py` 的影响

现有 `mcp_client.py` 使用 SSE+POST 通信（旧版 transport），需更新为 Streamable HTTP：

```python
# 旧版 SSE transport（2024-11-05 spec，已废弃）
from mcp.client.sse import sse_client
async with sse_client(sse_url, post_url) as (read, write): ...

# 新版 Streamable HTTP transport（2025-03-26 spec）
from mcp.client.streamable_http import streamablehttp_client
async with streamablehttp_client(
    url="https://your-server.com/mcp",
    headers={"X-API-Key": api_key}
) as (read, write, get_session_id): ...
```

---

## 部署要求

### ASGI Server

HTTP Streamable Transport 必须运行在 ASGI 兼容服务器上：

```bash
# 生产部署推荐（Render/Railway）
uvicorn mcp_server.http_app:app \
    --host 0.0.0.0 \
    --port ${PORT:-8090} \
    --workers 1 \       # stateless 模式可用多 worker
    --log-level info
```

注意：`stateless_http=True` 时可安全使用多 worker（无共享状态）；有状态模式必须 `--workers 1`。

### 依赖清单（新增）

```toml
# pyproject.toml 新增依赖
[project.optional-dependencies]
http = [
    "mcp[cli]>=1.8.0",
    "uvicorn>=0.30.0",
    "starlette>=0.40.0",  # mcp SDK 已依赖，可不显式指定
]
```

### Render 部署配置

```yaml
# render.yaml
services:
  - type: web
    name: socialhub-mcp
    runtime: python
    buildCommand: pip install -e ".[http]"
    startCommand: uvicorn mcp_server.http_app:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /health
    envVars:
      - key: PORT
        value: "8090"
      - key: PYTHONUNBUFFERED
        value: "1"
      - key: API_KEY_TENANT_001
        sync: false   # 从 Render Dashboard 设置
```

### 健康检查端点要求

Render 会定期 GET `/health`（或配置的路径），服务必须在 30 秒内返回 `200 OK`：

```python
async def health(request: Request) -> JSONResponse:
    return JSONResponse({
        "status": "ok",
        "service": "socialhub-mcp",
        "transport": "streamable-http",
        "version": "1.0.0",
    })
```

### 端口与 URL

- 开发：`http://localhost:8090/mcp`
- Render 生产：`https://socialhub-mcp.onrender.com/mcp`（Render 自动提供 TLS，HTTP→HTTPS）
- M365 Copilot `plugin.json` 中 `runtimes[].spec.url` 填写生产 HTTPS URL

### 启动时间与冷启动

Render 免费层有冷启动（首次请求需约 30 秒唤醒），M365 Copilot 调用超时可能导致第一次失败。建议：
- 升级为 Render Starter 实例（无冷启动）
- 或添加定时 ping 防止休眠（Render UptimeRobot 集成）

---

## 关键发现和对本项目的启示

### 1. SDK 版本确认

**结论：`mcp >= 1.8.0` 已原生支持 HTTP Streamable Transport，无需手写 FastAPI 适配层。**

项目假设 `[假设: MCP Python SDK 1.0+ 已支持 HTTP Streamable Transport]` 已确认为真，但需注意版本号：支持版本是 **1.8.0**（2025-05-08），而非 1.0.x。当前 `pyproject.toml` 中若固定了 `mcp==1.0.x` 则需升级。

### 2. 最小改动方案

现有 `mcp_server/server.py` 的 36+ 工具定义**零修改**，只需：
- 新建 `mcp_server/http_app.py`（Starlette app + CORS + Auth 中间件）
- 修改 `mcp_server/__main__.py` 增加 `--transport http` 分支
- 新增 `mcp_server/auth.py`（API Key 中间件）

### 3. tenant_id 安全隔离方案

当前 stdio 模式：每个租户启动独立进程，`MCP_TENANT_ID` 环境变量隔离。

HTTP 模式必须变更为：API Key → tenant_id 映射由服务器端维护，工具处理器从 `request.state.tenant_id` 获取，客户端传入的 `tenant_id` 参数**必须与 API Key 绑定的 tenant_id 比对验证**，不匹配则拒绝。

### 4. 缓存层需要评估

现有 15 分钟 TTL 内存缓存在以下场景会失效：
- `stateless_http=True` 且多 worker 时：每个 worker 进程独立缓存，无法共享
- 建议：先用单 worker 部署（`--workers 1`），缓存在进程内共享，满足 MVP 需求

### 5. SSE transport 不建议迁移目标

旧版 `HTTP+SSE transport`（`/sse` + `/messages` 双端点）已被官方标记为废弃（deprecated），在 2025-03-26 spec 中明确被 Streamable HTTP 取代。本项目 `cli/api/mcp_client.py` 中已有的 SSE 客户端代码也应一并迁移。

### 6. M365 Copilot 兼容性

M365 Copilot 的 RemoteMCPServer runtime 要求 HTTPS URL，并支持 Streamable HTTP transport（2025-03-26 spec）。Render 提供免费 TLS，满足需求。建议优先使用 `stateless_http=True` 模式，与 M365 Copilot 的无状态调用模型完全匹配。

### 7. 实现优先级建议

```
Phase 1（MVP）：
  mcp_server/http_app.py     — Starlette app，stateless=True，单 worker
  mcp_server/auth.py         — X-API-Key 中间件，硬编码 API Key
  mcp_server/__main__.py     — 增加 --transport http 参数

Phase 2（生产加固）：
  API Key 持久化存储（PostgreSQL）
  多 tenant API Key 管理
  速率限制中间件
  结构化日志（JSON 格式，Render 可解析）
```

---

## 参考资料

- [MCP Transports 官方规范 2025-03-26](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)
- [MCP Python SDK GitHub](https://github.com/modelcontextprotocol/python-sdk)
- [PyPI mcp 1.9.1](https://pypi.org/project/mcp/1.9.1/)
- [Cloudflare: Bringing streamable HTTP transport and Python support to MCP](https://blog.cloudflare.com/streamable-http-mcp-servers-python/)
- [Why MCP Deprecated SSE and Went with Streamable HTTP](https://blog.fka.dev/blog/2025-06-06-why-mcp-deprecated-sse-and-go-with-streamable-http/)
- [Auth0: Why MCP's Move Away from SSE Simplifies Security](https://auth0.com/blog/mcp-streamable-http/)
- [FastMCP HTTP Deployment Docs](https://gofastmcp.com/deployment/http)
- [CORS Policies for Web-Based MCP Servers (MCPcat)](https://mcpcat.io/guides/implementing-cors-policies-web-based-mcp-servers/)
- [Building Production-Ready MCP Server with Streamable-HTTP (Medium)](https://medium.com/@nsaikiranvarma/building-production-ready-mcp-server-with-streamable-http-transport-in-15-minutes-ba15f350ac3c)
- [MCP Server Python Starlette Mount Example](https://github.com/modelcontextprotocol/python-sdk/blob/main/examples/snippets/servers/streamable_starlette_mount.py)
- [Render FastAPI Deployment Docs](https://render.com/docs/deploy-fastapi)
- [Deploying Remote MCP Server with Python and FastAPI (DEV Community)](https://dev.to/christian_dennishinojosa/-deploying-a-remote-mcp-server-with-python-and-fastapi-1ilo)
- [MCP Transport Comparison (MCPcat)](https://mcpcat.io/guides/comparing-stdio-sse-streamablehttp/)
