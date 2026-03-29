# 项目现状：MCP HTTP Transport 调研

> 调研日期：2026-03-29
> 调研范围：`mcp_server/`、`design/remote-mcp-service-migration.md`、`pyproject.toml`、已安装 mcp 包

---

## 当前传输层实现（代码级）

### 结论：纯 stdio，HTTP/SSE 注释存在但代码完全未实现

`mcp_server/server.py` 文件头部注释写道：

```
Runs over stdio (Claude Desktop compatible) or SSE (HTTP agents).
Usage:
    python -m mcp_server                        # stdio (default)
    python -m mcp_server --transport sse --port 8090
```

但这是**死注释**，没有任何对应实现。

`mcp_server/__main__.py` 中：
- 硬编码导入 `from mcp.server.stdio import stdio_server`
- 无 argparse / typer 参数解析（无 `--transport`、`--port` 参数）
- 无任何条件分支切换传输层
- 完整启动流程：`anyio.run(run_stdio)` → `stdio_server()` → `server.run(read, write, ...)`

**Grep 证据**：对 `mcp_server/` 目录搜索 `transport|sse|SSE|http_server|streamable` 返回 **0 匹配**。整个 `mcp_server` 包中不存在任何 HTTP/SSE/Streamable 相关代码。

### 现有机制盘点

| 机制 | 位置 | 说明 |
|---|---|---|
| `probe_upstream_mcp()` | `server.py:163` | 启动时连接上游 MCP 后端做健康检查，同步阻塞调用 |
| `_load_analytics()` | `server.py:100` | 启动时在独立线程预加载 pandas 等重型依赖，避免 Windows event-loop 死锁 |
| `_run_with_cache()` | `server.py:61` | 内存 TTL 缓存（15分钟），并发去重（threading.Event），同一请求只跑一次 |
| `_analytics_ready` | `server.py:40` | threading.Event，工具调用最多等待 120s 让 analytics 加载完成 |
| `create_server()` | `server.py:907` | 工厂函数，注册 `list_tools` 和 `call_tool` handler，返回 `mcp.server.Server` 实例 |
| `_HANDLERS` | `server.py:869` | 16个工具的 dispatch table，所有 handler 返回 `list[TextContent]` |

`call_tool` 使用 `await loop.run_in_executor(None, _run)` 将同步计算推入线程池，与传输层完全解耦——**这意味着切换传输层不影响 handler 逻辑**。

---

## MCP Python SDK HTTP 能力

### 结论：mcp 1.26.0 已内置完整 HTTP Streamable Transport，无需额外安装

实际环境中已安装版本：`mcp 1.26.0`（远高于 pyproject.toml 中声明的最低版本 `mcp>=1.0.0`）。

通过 `pkgutil.walk_packages` 枚举 `mcp.server` 的子模块，确认以下 HTTP 相关模块**已存在**：

| 模块 | 说明 |
|---|---|
| `mcp.server.streamable_http` | HTTP Streamable Transport 核心实现，基于 Starlette ASGI |
| `mcp.server.streamable_http_manager` | `StreamableHTTPSessionManager`，管理会话生命周期 |
| `mcp.server.sse` | 旧版 SSE Transport（`SseServerTransport`），仍存在但属于遗留接口 |
| `mcp.server.auth` | Bearer Token 认证中间件（`BearerAuthBackend`）、OAuth 相关 handler |
| `mcp.server.fastmcp` | 高层 FastMCP 封装，可进一步简化 HTTP server 开发 |

**关键 API 签名（已通过 Python inspect 验证）**：

```python
# HTTP Streamable Session Manager
StreamableHTTPSessionManager(
    app: MCPServer,
    event_store: EventStore | None = None,
    json_response: bool = False,
    stateless: bool = False,           # 无状态模式：每个请求独立 transport，适合 M365 场景
    security_settings: TransportSecuritySettings | None = None,
    retry_interval: int | None = None,
)

# 旧版 SSE Transport
SseServerTransport(endpoint: str, security_settings=None)

# Bearer Auth Middleware
BearerAuthBackend(token_verifier: TokenVerifier)
```

**mcp 1.26.0 的依赖**（由 pip 自动解析，已安装）：
`anyio`, `httpx`, `httpx-sse`, `sse-starlette`, `starlette`, `uvicorn`, `pydantic-settings`, `pyjwt`, `python-multipart`

这些全部已在环境中可用，**不需要额外 `pip install`**。

**两种 HTTP Transport 选项对比**：

| | SSE Transport（旧） | HTTP Streamable（新，推荐） |
|---|---|---|
| 协议 | SSE + POST 分离端点 | 单一 `/mcp` 端点，HTTP POST + SSE 流 |
| M365 兼容性 | 部分支持 | 官方推荐，MCP 规范 2024-11+ |
| 无状态支持 | 否 | 是（`stateless=True`） |
| SDK 内置 | 是 | 是 |

---

## 需要改动的文件清单（含改动难度评估）

### 必改文件

| 文件 | 改动内容 | 难度 | 估时 |
|---|---|---|---|
| `mcp_server/__main__.py` | 新增 argparse 解析 `--transport [stdio\|http]`、`--port`；HTTP 分支用 `StreamableHTTPSessionManager` + `uvicorn` 启动 | 低 | 1-2h |
| `pyproject.toml` | 新增 optional-dependency `[http]`（`uvicorn`, `starlette` 已在 mcp 依赖中，但显式声明更清晰）；新增 `socialhub-mcp-http` entry point（可选） | 极低 | 15min |

### 新建文件

| 文件 | 内容 | 难度 | 估时 |
|---|---|---|---|
| `mcp_server/http_app.py` | 组装 Starlette ASGI app：`StreamableHTTPSessionManager`、CORS 中间件、`/health` 端点、API Key 认证中间件 | 中 | 3-4h |
| `mcp_server/auth.py` | API Key 校验：实现 `TokenVerifier` 接口（从 `Authorization: Bearer <key>` 提取 tenant_id） | 中 | 2-3h |
| `render.yaml` 或 `Dockerfile` | Render 部署配置，`CMD ["python", "-m", "mcp_server", "--transport", "http", "--port", "8090"]` | 低 | 1h |

### 不需要改动的文件

| 文件 | 原因 |
|---|---|
| `mcp_server/server.py` | `create_server()` 返回标准 `mcp.server.Server` 实例，与传输层解耦，**一行不用改** |
| `cli/api/mcp_client.py` | 上游 MCP 通信层，与本次改动无关 |
| `cli/config.py` | 配置层不变；HTTP 新增的 `MCP_API_KEY`、`MCP_PORT` 通过环境变量注入 |
| 所有 `_handle_*` handler | 全部保持不变 |

**总改动文件数：2 个改动 + 2-3 个新建**，核心业务逻辑零改动。

---

## 可复用的现有机制

### 在 HTTP Transport 下完全有效的机制

| 机制 | HTTP 下的行为 | 说明 |
|---|---|---|
| `_run_with_cache()` | 完全有效 | 基于 `threading.Lock` + 内存 dict，与传输层无关；多个并发 HTTP 请求命中同一工具参数时自动合并 |
| `_analytics_ready` Event | 完全有效 | 服务启动后首次 HTTP 请求到来时若 analytics 仍在加载，会等待最多 120s；行为与 stdio 相同 |
| `_load_analytics()` 线程 | 完全有效 | 独立 daemon thread，在 `__main__.py` 启动时触发，与传输层无关 |
| `loop.run_in_executor(None, _run)` | 完全有效 | 将同步 handler 推入线程池，避免阻塞 ASGI event loop；HTTP 场景下尤为重要 |
| `probe_upstream_mcp()` | 完全有效 | 启动时健康检查，HTTP 模式下同样应在 uvicorn 启动前调用 |
| `_HANDLERS` dispatch table | 完全有效 | 纯函数映射，无任何传输层依赖 |
| `create_server()` | 完全有效 | 返回 `mcp.server.Server` 实例，`StreamableHTTPSessionManager(app=create_server())` 直接接受 |

### 需要注意的潜在问题

1. **`_config_cache` 单进程单例**：stdio 模式下一个进程服务一个 Claude 实例，HTTP 模式下一个进程服务多个并发用户。当前 `_get_config()` 从 `~/.socialhub/config.json` 读取单一 tenant_id，HTTP 模式下需要从请求 Token 中解析 tenant_id 并注入请求上下文，而不是依赖全局 config。**这是多租户支持的核心缺口**，但对于单租户快速上线场景（一个 API Key 对应一个固定 tenant）可以暂时绕过。

2. **`_cache` 全局内存字典**：多用户场景下缓存 key 未含 tenant_id，可能导致租户 A 的数据被租户 B 读取（当两个租户查询相同参数时）。需在 `_cache_key()` 中加入 tenant_id。

---

## remote-mcp-service-migration.md 重叠分析

### 文档定位

`design/remote-mcp-service-migration.md` 是一份**宏观架构迁移设计**（约 1779 行），目标是将整个系统从本地 CLI 演进为多层微服务架构（`socialhub_core` + `api_server` + `mcp_server` + Redis + Nginx），属于长期演进路线图。

### 重叠度分析

| 维度 | migration.md 的方案 | 本次 M365 目标 | 重叠度 |
|---|---|---|---|
| 目标 | 完整多服务架构改造，Phase 0-5 | 最小化暴露 HTTP MCP Server 给 M365 Copilot | 部分重叠 |
| MCP 远程化 | Phase 3（需先完成 Phase 0-2） | **直接跳到**，不依赖前序 Phase | 目标一致但路径不同 |
| 传输层 | 文档提到"remote transport + SSE" | HTTP Streamable（更新的规范） | 协议方向一致，具体方案需更新 |
| 认证 | bearer token、OIDC、Redis | API Key（ApiKeyPluginVault） | 重叠，migration.md 中第 7 节 Auth 设计可直接参考 |
| 租户隔离 | request-scoped RequestContext | API Key 绑定 tenant_id | 可复用 migration.md 的思路 |
| 服务层重构 | 提取 `socialhub_core`，重构所有 handler | **不需要**，handler 层不动 | 不重叠 |
| 部署 | Docker + Nginx + Redis | Render（轻量，最快） | 思路可参考，具体配置不同 |

### 可直接复用的内容

1. **Section 7 Auth Model 设计原则**（第 342-374 行）：tenant resolution 必须 request-scoped、token claims 作为 tenant 来源——可直接指导 `mcp_server/auth.py` 的设计。

2. **Section 9 环境变量规范**（第 399-418 行）：`MCP_PORT=8090`、`AUTH_MODE`、`MCP_SSE_URL`、`MCP_POST_URL` 等变量命名约定可复用。

3. **Section 15 Minimum Viable Remote Version**（第 657-675 行）：7步最小化路径，与本次目标高度吻合（步骤 4-7 直接对应：remote MCP over SSE/HTTP、bearer token auth、Redis caching 可选、HTTPS through Nginx/Render）。

4. **`RequestContext` dataclass 设计**（第 235-247 行）：`tenant_id`、`source: "mcp"`、`request_id`、`trace_id` 字段设计，在 `mcp_server/auth.py` 中实现 token 解析时可参照。

### 不可直接复用（本次可跳过）

- Phase 0-2 的 `socialhub_core` 提取和 `api_server` 创建（对 M365 目标非必要）
- Redis 缓存（内存缓存已够用，部署阶段可选）
- Docker Compose + Nginx（Render 原生 HTTPS 代替）

---

## 认证层现状与缺口

### 现状：零认证

当前 `mcp_server/` 完全没有认证层：
- `mcp_server/__main__.py`：无认证相关代码
- `mcp_server/server.py`：无认证相关代码
- `mcp_server/__init__.py`：空文件
- Grep 搜索 `auth|token|api.key|bearer|jwt` 在 `mcp_server/` 目录返回 0 匹配

stdio 模式下不需要认证（Claude Desktop 本地进程通信），但 HTTP 公网暴露必须加认证。

### 认证缺口清单

| 缺口 | 说明 | 优先级 |
|---|---|---|
| **API Key 认证中间件** | HTTP 请求必须携带 `Authorization: Bearer <api_key>` header，服务端验证 key 有效性 | P0，上线前必须 |
| **API Key → tenant_id 映射** | 每个 API Key 对应一个企业租户，用于隔离数据查询 | P0，多租户必须 |
| **`_cache_key` 加入 tenant_id** | 防止不同租户共享缓存结果（数据泄露风险） | P0，多租户必须 |
| **全局 `_config_cache` 重构** | 当前从本地磁盘 config 读取 tenant_id，HTTP 模式需从请求 Token 动态解析 | P1，单租户可暂缓 |
| **HTTPS** | Render 原生提供 TLS，无需手动配置证书；M365 Copilot 要求 HTTPS URL | P0，Render 部署自动满足 |
| **CORS** | M365 Copilot 可能发跨域 preflight 请求，需在 Starlette app 层添加 CORS 中间件 | P1 |
| **Rate Limiting** | 防止 API Key 滥用；M365 场景可暂缓 | P2 |
| **Key Rotation / Revocation** | 企业场景需要，MVP 阶段可用环境变量管理 | P2 |

### MCP SDK 内置认证支持

`mcp.server.auth` 模块已提供：
- `BearerAuthBackend(token_verifier: TokenVerifier)`：Starlette AuthenticationMiddleware 后端
- `TokenVerifier`：抽象接口，实现 `verify_token(token: str) -> TokenInfo` 即可
- OAuth 相关 handler（`authorize`、`token`、`register`）：适合完整 OAuth 流程，MVP 阶段可跳过

**最简 API Key 认证方案**：实现 `TokenVerifier`，内部做 `hmac.compare_digest(token, VALID_API_KEY)`，并从 token 中查出对应 `tenant_id` 注入请求上下文，无需引入任何新依赖。

---

## 总结：实现 Remote HTTPS MCP Server 的最小路径

### 核心判断

**改动量极小，主要原因**：
1. `mcp 1.26.0` 已在环境中安装，且已内置 `StreamableHTTPSessionManager` 和 `BearerAuthBackend`
2. `mcp_server/server.py` 中的 `create_server()` 与传输层完全解耦，零改动
3. 所有 `_handle_*` handler、缓存、并发去重机制在 HTTP 模式下继续有效
4. Render 原生提供 HTTPS，无需 Nginx/证书管理

### 最小路径（5步）

```
Step 1 — mcp_server/auth.py（新建）
  实现 ApiKeyTokenVerifier(TokenVerifier)
  - 从环境变量 MCP_API_KEYS 读取 "key1:tenant1,key2:tenant2" 格式的 key-tenant 映射
  - verify_token() 验证 Bearer token，返回含 tenant_id 的 TokenInfo

Step 2 — mcp_server/http_app.py（新建）
  from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
  from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend
  from starlette.applications import Starlette
  from starlette.middleware.authentication import AuthenticationMiddleware
  from starlette.middleware.cors import CORSMiddleware

  组装 ASGI app：
  - /mcp 路由 → session_manager.handle_request()
  - /health 路由 → 200 OK（Render 健康检查）
  - 包裹 AuthenticationMiddleware + CORSMiddleware

Step 3 — mcp_server/__main__.py（改动约 30 行）
  新增 argparse --transport [stdio|http] --port 8090
  HTTP 分支：uvicorn.run(http_app, host="0.0.0.0", port=port)

Step 4 — mcp_server/server.py（可选小改动）
  _cache_key() 加入 tenant_id 参数（从请求上下文获取）
  _get_config() 支持从请求上下文注入 tenant_id 而非全局读取
  （MVP 单租户阶段可暂缓，用环境变量固定 MCP_TENANT_ID）

Step 5 — render.yaml（新建）
  services:
    - type: web
      name: socialhub-mcp
      env: python
      buildCommand: pip install -e .
      startCommand: python -m mcp_server --transport http --port 8090
      envVars:
        - key: MCP_API_KEYS
          sync: false
        - key: MCP_TENANT_ID
          sync: false
        - key: MCP_SSE_URL
          sync: false
        - key: MCP_POST_URL
          sync: false
```

### 时间估算（最小可运行版本）

| 步骤 | 工作量 |
|---|---|
| Step 1 auth.py | 2-3h |
| Step 2 http_app.py | 2-3h |
| Step 3 __main__.py 改动 | 1h |
| Step 4 server.py 小改（可选延后） | 1-2h |
| Step 5 render.yaml | 30min |
| 本地测试 + Render 部署验证 | 2-3h |
| **合计** | **~9-13h（1.5-2个工作日）** |

### 主要技术风险

1. **全局 config 多租户问题**：MVP 阶段若只部署单租户，可通过环境变量 `MCP_TENANT_ID` 固定绕过，后续再重构。
2. **M365 Copilot 对 Streamable HTTP vs SSE 的具体要求**：需在调研 Phase 2-3（MCP HTTP Transport 规范、M365 Plugin 规范）中确认 M365 `RemoteMCPServer` runtime 支持的具体协议版本，若只支持旧版 SSE 则切换到 `mcp.server.sse.SseServerTransport`（同样内置，改动量相似）。
3. **probe_upstream_mcp 依赖本地 config**：HTTP 模式启动时仍会尝试连接上游 MCP，若 Render 环境变量未配置会报错但不会阻断启动（已有 `if ok/else` 分支，只记录日志）。
