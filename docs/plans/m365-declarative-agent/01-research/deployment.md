# 远程 MCP Server 部署方案

> 调研日期：2026-03-29
> 背景：将 SocialHub MCP Server 从 stdio 迁移为 HTTP Streamable Transport，部署到 Render.com，供 M365 Copilot Declarative Agent 通过 RemoteMCPServer 调用。

---

## Render 部署配置（render.yaml 示例）

### 完整 render.yaml

Render Blueprint（IaC）文件放在 Git 仓库根目录，文件名固定为 `render.yaml`：

```yaml
services:
  - type: web
    runtime: python
    name: socialhub-mcp
    repo: https://github.com/your-org/Socialhub-CLI.git
    branch: main
    plan: starter                          # $7/月，无冷启动，始终运行
    region: oregon                         # 可选：oregon / frankfurt / singapore
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn mcp_server.http_app:app --host 0.0.0.0 --port 10000
    healthCheckPath: /health               # 用于零停机部署探针
    autoDeploy: true                       # 每次 push 自动部署
    envVars:
      # 敏感值：在 Dashboard 中手动填写，不写入 Git
      - key: MCP_API_KEY
        sync: false
      - key: MCP_TENANT_ID
        sync: false
      - key: MCP_SSE_URL
        sync: false
      - key: MCP_POST_URL
        sync: false
      # 非敏感配置：可写入 render.yaml
      - key: FASTMCP_STATELESS_HTTP
        value: "true"
      - key: LOG_LEVEL
        value: "INFO"
      - key: PORT
        value: "10000"
```

### 关键字段说明

| 字段 | 值 | 说明 |
|---|---|---|
| `runtime` | `python` | Render 自动检测 Python 版本 |
| `plan` | `starter` | $7/月，512 MB RAM，0.5 CPU，无 spin-down |
| `port` | `10000` | Render 默认 PORT，服务必须绑定 `0.0.0.0:10000` |
| `healthCheckPath` | `/health` | 新版本部署时探针，通过后才切流量 |
| `sync: false` | 敏感环境变量 | 值不进 Git，在 Render Dashboard 中填写 |
| `autoDeploy` | `true` | push 到 main 分支即触发部署 |

### startCommand 选项对比

```bash
# 选项 A：单进程 uvicorn（推荐用于 MCP 无状态模式）
uvicorn mcp_server.http_app:app --host 0.0.0.0 --port 10000

# 选项 B：多进程 gunicorn + uvicorn worker（需要 stateless_http=True）
gunicorn mcp_server.http_app:app -k uvicorn.workers.UvicornWorker \
  --workers 2 --bind 0.0.0.0:10000

# 注意：多 worker 模式下必须开启 stateless_http=True
# 否则不同 worker 间 session 不共享，导致请求失败
```

---

## 冷启动问题与解决方案

### 问题描述

| 层级 | 场景 | 影响 |
|---|---|---|
| **Free Tier** | 15 分钟无流量后 spin down | 首次请求冷启动约 60 秒，M365 Copilot 调用直接超时 |
| **Starter Tier** | 无 spin down，始终运行 | 无冷启动问题 |
| **部署期间** | 健康检查通过前旧版本继续服务 | 配置 `healthCheckPath` 即可实现零停机 |

### Free Tier 冷启动的具体影响

M365 Copilot 的 RemoteMCPServer 调用有严格的超时限制（通常 30 秒以内）。Free Tier 的 ~60 秒冷启动时间**几乎必然导致 M365 Copilot 首次调用失败**，用户体验极差。

### 解决方案

**方案 1（推荐）：使用 Starter Tier（$7/月）**
- Starter Tier 无 spin-down，服务始终运行
- 对于 M365 Copilot 生产场景，这是**唯一可靠选项**

**方案 2：Free Tier + Keep-Alive Ping（仅测试/Demo 用）**
```yaml
# 在 render.yaml 中添加 cron job 每 14 分钟 ping 一次
services:
  - type: cron
    name: mcp-keepalive
    runtime: python
    plan: free
    schedule: "*/14 * * * *"
    buildCommand: pip install httpx
    startCommand: python -c "import httpx; httpx.get('https://socialhub-mcp.onrender.com/health')"
```
- 缺点：Render 免费 Cron Job 有次数限制，且 ping 策略违反 Render 服务条款（未明确禁止但不鼓励）
- 不适合 M365 Copilot 生产部署

**方案 3：外部 Uptime Monitor（仅 Demo）**
- 使用 UptimeRobot 免费套餐（5 分钟间隔 ping）保持 Free Tier 活跃
- 适合个人 Demo，不适合企业生产

### 结论

**生产场景必须使用 Starter Tier（$7/月）**。Free Tier 仅适用于开发调试，不可用于 M365 Copilot 集成。

---

## 健康检查端点设计

### 端点规范

MCP Server 需实现两个健康检查端点：

#### `/health`（Liveness Probe）

```python
@app.get("/health")
async def health_check():
    """
    轻量级存活检查。
    - 仅确认进程在运行、事件循环未阻塞
    - Render 部署探针使用此端点
    - 响应必须 < 100ms
    """
    return {
        "status": "healthy",
        "service": "socialhub-mcp",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
```

响应示例（HTTP 200）：
```json
{
  "status": "healthy",
  "service": "socialhub-mcp",
  "version": "1.0.0",
  "timestamp": "2026-03-29T10:00:00Z"
}
```

#### `/ready`（Readiness Probe，可选）

```python
@app.get("/ready")
async def readiness_check():
    """
    完整就绪检查。
    - 验证上游 MCP 连接可用
    - 验证关键配置存在
    - 响应可能较慢（< 5s），不适合作为 Render healthCheckPath
    """
    checks = {}

    # 检查环境变量
    checks["config"] = {
        "status": "healthy" if os.getenv("MCP_SSE_URL") else "unhealthy",
        "message": "MCP_SSE_URL configured" if os.getenv("MCP_SSE_URL") else "MCP_SSE_URL missing"
    }

    # 检查上游 MCP 连通性（可选，避免慢速检查阻塞）
    # checks["upstream"] = await check_upstream_mcp()

    all_ready = all(c["status"] == "healthy" for c in checks.values())
    status_code = 200 if all_ready else 503

    return JSONResponse(
        content={
            "ready": all_ready,
            "checks": checks,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        },
        status_code=status_code
    )
```

### 在 FastMCP 中注册自定义路由

FastMCP 支持通过 `@mcp.custom_route` 装饰器添加非 MCP 端点：

```python
from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse

mcp = FastMCP("socialhub-mcp", stateless_http=True)

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse({"status": "healthy", "service": "socialhub-mcp"})
```

如果是 FastAPI 挂载模式，直接在 FastAPI app 上注册路由即可。

### Render healthCheckPath 行为

- `healthCheckPath: /health` 配置后，Render 在每次部署时会持续探测此端点
- 只有 `/health` 返回 HTTP 200 后，Render 才将流量切换到新版本
- 探测失败超过阈值则回滚到上一个版本
- **实现要点**：`/health` 必须极其轻量，不依赖外部服务，避免因上游超时导致探测失败

---

## CORS 配置

### M365 Copilot 调用时的 Origin

M365 Copilot 的 RemoteMCPServer 调用**不经过浏览器**，而是由 Microsoft 服务端（云端编排器）直接发起 HTTP 请求。因此：

- **服务端调用无需 CORS**：CORS 是浏览器安全机制，服务端调用不受约束
- **但仍建议配置 CORS**：为未来可能的 Web 客户端调用、调试工具（如 MCP Inspector）提供兼容性

### 例外：Adaptive Card Widget

如果 MCP Server 提供 Adaptive Card Widget UI，M365 Copilot 会在特定 origin 下渲染：

```
{sha256_of_mcp_domain}.widget-renderer.usercontent.microsoft.com
```

此 origin 需要在 CORS 白名单中。计算方式：
```python
import hashlib
domain = "socialhub-mcp.onrender.com"
hashed = hashlib.sha256(domain.encode()).hexdigest()
widget_origin = f"https://{hashed}.widget-renderer.usercontent.microsoft.com"
```

### 生产 CORS 配置

使用 Starlette CORSMiddleware（FastMCP 基于 Starlette）：

```python
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

ALLOWED_ORIGINS = [
    # 本地开发
    "http://localhost:3000",
    "http://localhost:8080",
    # MCP Inspector 工具
    "https://inspector.modelcontextprotocol.io",
    # M365 Widget Renderer（如启用 Adaptive Card）
    # f"https://{sha256_of_domain}.widget-renderer.usercontent.microsoft.com",
]

middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "mcp-session-id",
            "mcp-protocol-version",
        ],
        expose_headers=["mcp-session-id"],  # 关键：浏览器 JS 需要读取 session ID
        allow_credentials=True,
    )
]

app = mcp.http_app(middleware=middleware)
```

### SSE 流式响应的 CORS 特殊处理

对于 SSE（Server-Sent Events）响应，需要额外设置响应头：

```python
headers = {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
    "Access-Control-Allow-Credentials": "true",
}
```

### 重要提示

- `expose_headers=["mcp-session-id"]` 是**必须的**：没有它，浏览器 JS 虽然收到 session ID 但无法读取，导致 session 管理失败
- 生产环境**禁止使用** `allow_origins=["*"]`：会导致安全风险
- M365 Copilot 服务端调用不受 CORS 约束，CORS 配置主要影响浏览器端工具

---

## Session 和并发管理

### HTTP Streamable Transport 的 Session 机制

MCP Streamable HTTP Transport 使用 `Mcp-Session-Id` 请求头维护会话：

1. 客户端发送 `POST /mcp`（初始化请求）
2. Server 返回响应，包含 `Mcp-Session-Id` 响应头
3. 后续请求携带相同 `Mcp-Session-Id`，服务端关联到同一会话

### Stateful vs Stateless 模式

| 模式 | 配置 | 适用场景 | 风险 |
|---|---|---|---|
| **Stateful（默认）** | `stateless_http=False` | 单实例部署，有长对话状态需求 | 多实例时跨实例 session 找不到 |
| **Stateless** | `stateless_http=True` | 多实例/多 worker，水平扩展 | 每次请求重新初始化，无持久 session |

### M365 Copilot 的 Session 需求

M365 Copilot 的每次 Copilot Chat 对话对 MCP Server 是**独立的工具调用请求**，不需要长期维持 MCP session。因此：

- **推荐使用 `stateless_http=True`**：适合 Render 的单/多实例部署，无需粘性路由
- 每次 M365 Copilot 工具调用创建新的 MCP 请求上下文
- SocialHub 的多租户隔离（`tenant_id`）通过 API Key 绑定实现，不依赖 MCP session

### 并发处理

```python
# 推荐配置：无状态 + 多 worker
mcp = FastMCP("socialhub-mcp", stateless_http=True)

# Render 启动命令（多 worker 模式）
# gunicorn mcp_server.http_app:app -k uvicorn.workers.UvicornWorker --workers 2 --bind 0.0.0.0:10000
```

**并发能力估算（Starter 512MB/0.5CPU）**：
- 单 uvicorn 进程：异步，理论上可处理数十并发（取决于上游 MCP 响应时间）
- 2 worker 模式：并发翻倍，但内存需除以 worker 数
- SocialHub 已有 15 分钟 TTL 内存缓存，可减少上游调用次数，降低并发压力

### Session ID 冲突风险

多 worker 模式下，若使用 stateful 模式：
- 请求 1（worker A）建立 session `abc-123`
- 请求 2（worker B）查找 session `abc-123` → 找不到 → 报错

**必须用 `stateless_http=True` 或配置 Redis 外部 session 存储**（后者复杂度高，不推荐初期实现）。

---

## 环境变量清单

### 必需变量

| 变量名 | 说明 | 示例值 | 安全级别 |
|---|---|---|---|
| `MCP_API_KEY` | API Key 认证密钥（单 key 或逗号分隔多 key） | `sk-socialhub-xxxxx` | 机密，`sync: false` |
| `MCP_TENANT_ID` | 默认租户 ID（单租户部署时） | `tenant-acme-001` | 机密，`sync: false` |
| `MCP_SSE_URL` | 上游 MCP SSE 端点 | `https://api.socialhub.ai/mcp/sse` | 机密，`sync: false` |
| `MCP_POST_URL` | 上游 MCP POST 端点 | `https://api.socialhub.ai/mcp/message` | 机密，`sync: false` |

### 可选变量

| 变量名 | 说明 | 默认值 | 安全级别 |
|---|---|---|---|
| `FASTMCP_STATELESS_HTTP` | 启用无状态模式 | `true` | 非敏感，可写入 render.yaml |
| `LOG_LEVEL` | 日志级别 | `INFO` | 非敏感 |
| `PORT` | 监听端口 | `10000` | 非敏感，Render 自动注入 |
| `ALLOWED_ORIGINS` | CORS 允许的 origin（逗号分隔） | `""` | 非敏感 |
| `MCP_CACHE_TTL` | 缓存 TTL 秒数 | `900` | 非敏感 |
| `MCP_MAX_CONCURRENT` | 最大并发请求 | `50` | 非敏感 |

### 多租户 API Key 绑定方案

SocialHub 是多租户架构，需将 API Key 映射到 `tenant_id`：

```
# 方案 A：单变量 JSON 映射（适合少量租户）
MCP_TENANT_MAP={"sk-tenant-a-xxx": "tenant-001", "sk-tenant-b-yyy": "tenant-002"}

# 方案 B：独立变量（每个租户一组，适合 1-2 个租户）
MCP_API_KEY_TENANT_001=sk-tenant-a-xxx
MCP_API_KEY_TENANT_002=sk-tenant-b-yyy

# 方案 C：外部 KV 存储（生产推荐，Render 可连 Redis/PostgreSQL）
# API Key → tenant_id 映射存储在数据库中，启动时加载
```

### render.yaml 中 sync:false 的使用方式

```yaml
envVars:
  - key: MCP_API_KEY
    sync: false   # 首次部署时 Render Dashboard 弹出输入框，值不写入 Git
```

首次部署后在 Render Dashboard → Service → Environment → 手动填入真实值 → 触发 redeploy。

### Secret Files 方案（替代环境变量）

如果密钥内容复杂（如 JSON 证书），可使用 Render Secret Files：
- 上传文件到 Render Dashboard
- 运行时文件路径为 `/etc/secrets/<filename>`
- Python 读取：`open("/etc/secrets/api-keys.json")`

---

## 成本分析（Render 免费 vs 付费）

### 方案对比

| 维度 | Free Tier | Starter ($7/月) | Standard ($25/月) |
|---|---|---|---|
| **价格** | $0 | $7/月 | $25/月 |
| **CPU** | 0.1 共享 | 0.5 共享 | 1 共享 |
| **内存** | 512 MB | 512 MB | 2 GB |
| **Spin-down** | 15 分钟无流量后休眠 | **无，始终运行** | **无，始终运行** |
| **冷启动** | ~60 秒（不可接受） | 无 | 无 |
| **持久磁盘** | 不支持 | 支持 | 支持 |
| **带宽** | 100 GB/月 | 100 GB/月 | 100 GB/月 |
| **SLA** | 无 | 99.95% | 99.95% |
| **适用场景** | 开发调试 | **M365 Copilot 生产** | 高负载生产 |

### M365 Copilot 集成的最低要求

- **最低方案：Starter（$7/月）**
  - 无冷启动，M365 Copilot 调用不会超时
  - 512 MB 内存对 SocialHub MCP Server（含 TTL 缓存）足够
  - 0.5 CPU 足够处理企业级并发（假设 < 20 并发工具调用）

- **Standard（$25/月）适用于**：
  - 同时服务 5+ 企业租户
  - 工具响应时间要求 < 3 秒
  - 需要更大内存缓存

### 总拥有成本（月）

| 场景 | Render | 其他 | 合计 |
|---|---|---|---|
| 开发/Demo（Free + Uptime ping） | $0 | $0 | $0 |
| 单租户 M365 Copilot 生产 | $7 | $0 | $7 |
| 多租户生产 + Redis session | $7 + $7（Redis） | $0 | $14 |

### 与其他平台对比

| 平台 | 最低生产成本 | Python 支持 | MCP 友好度 |
|---|---|---|---|
| **Render Starter** | $7/月 | 原生 | 高（已有部署经验） |
| Railway Starter | $5/月 | 原生 | 高 |
| Fly.io（最小 VM） | ~$3/月 | Docker | 高（有官方 MCP 文档） |
| Azure App Service（B1） | ~$13/月 | 原生 | 高（Microsoft 生态） |
| Vercel（Serverless） | $0-20/月 | 限制 | 低（无法持久连接） |

**结论**：鉴于 SocialHub 已有 Render 部署经验（Skills Store 后端），**Render Starter 是首选**，成本最低且运维复杂度最小。

---

## 部署验证步骤

### Step 1：本地验证 HTTP Transport

```bash
# 安装依赖
pip install "mcp[cli]" fastmcp uvicorn

# 本地启动 HTTP 模式
uvicorn mcp_server.http_app:app --host 0.0.0.0 --port 8090

# 验证健康检查
curl http://localhost:8090/health
# 期望：{"status": "healthy", ...}

# 验证 MCP 端点（发送 initialize 请求）
curl -X POST http://localhost:8090/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{}},"id":1}'
```

### Step 2：MCP Inspector 验证

```bash
# 使用官方 MCP Inspector 工具验证
npx @modelcontextprotocol/inspector http://localhost:8090/mcp

# 或使用 mcp dev 命令
mcp dev mcp_server/http_app.py --transport streamable-http
```

### Step 3：推送到 Render

```bash
# 确保 render.yaml 在仓库根目录
git add render.yaml requirements.txt mcp_server/
git commit -m "feat: add HTTP streamable transport for M365 Copilot"
git push origin main

# Render 会自动检测 render.yaml 并触发部署
```

### Step 4：Render 部署后验证

```bash
# 替换为实际的 Render 域名
export MCP_URL="https://socialhub-mcp.onrender.com"

# 1. 健康检查
curl $MCP_URL/health
# 期望：HTTP 200, {"status": "healthy"}

# 2. MCP initialize
curl -X POST $MCP_URL/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MCP_API_KEY" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{}},"id":1}'

# 3. tools/list（列出所有工具）
curl -X POST $MCP_URL/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MCP_API_KEY" \
  -H "mcp-session-id: <session-id-from-step-2>" \
  -d '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":2}'
# 期望：返回 27+ 工具列表

# 4. 用 MCP Inspector 做端到端验证
npx @modelcontextprotocol/inspector $MCP_URL/mcp
```

### Step 5：M365 Copilot 集成验证

```bash
# 在 plugin.json 中配置 MCP Server URL
# "runtimeUrl": "https://socialhub-mcp.onrender.com/mcp"

# 通过 Teams Toolkit 或手动上传到 Teams Admin Center
# 在 M365 Copilot Chat 中测试：
# "用 SocialHub 帮我查最近 30 天的客户概览"
```

---

## 关键风险和缓解措施

### 风险 1：Free Tier 冷启动导致 M365 Copilot 超时

- **风险等级**：高
- **影响**：M365 Copilot 首次调用失败，用户体验严重受损
- **缓解**：生产环境强制使用 Starter Tier（$7/月），消除 spin-down
- **测试验证**：在 Free Tier 上故意让服务休眠后调用，确认超时行为，再切换 Starter 对比

### 风险 2：多 worker 模式下 Stateful Session 失效

- **风险等级**：高（如使用默认 stateful 模式）
- **影响**：部分请求找不到 session，报 "session not found" 错误
- **缓解**：强制设置 `FASTMCP_STATELESS_HTTP=true`，并在 `render.yaml` 中写入此环境变量
- **监控**：日志中搜索 "session not found" 告警

### 风险 3：API Key 泄露

- **风险等级**：高
- **影响**：攻击者可调用 MCP Server 获取任意租户数据
- **缓解**：
  1. `render.yaml` 中 API Key 用 `sync: false`，值不入 Git
  2. MCP Server 实现 API Key 验证中间件（Bearer Token 格式）
  3. 每个租户独立 API Key，且 Key 与 tenant_id 绑定
  4. 定期轮换 API Key（Render Dashboard 更新环境变量自动重部署）

### 风险 4：上游 MCP 连接超时导致工具调用慢

- **风险等级**：中
- **影响**：M365 Copilot 工具调用超时，LLM 编排器可能放弃等待
- **缓解**：
  1. SocialHub 已有 15 分钟 TTL 缓存，缓存命中时无上游调用
  2. 工具调用设置上游超时（建议 10 秒）
  3. `/health` 不依赖上游，避免健康检查与实际请求互相影响

### 风险 5：Render Starter 内存（512 MB）不足

- **风险等级**：低-中
- **影响**：内存缓存过大时触发 OOM，服务重启
- **缓解**：
  1. 监控 Render Dashboard 内存使用
  2. 合理设置缓存条目数量上限（不仅是 TTL）
  3. 如内存持续超 400 MB，升级到 Standard（2 GB，$25/月）

### 风险 6：Render 部署期间短暂不可用

- **风险等级**：低
- **影响**：部署期间 M365 Copilot 调用失败
- **缓解**：配置 `healthCheckPath: /health`，Render 确保新实例健康后才切流量（零停机部署）

### 风险 7：CORS 配置过宽导致安全漏洞

- **风险等级**：中（如误用 `allow_origins=["*"]`）
- **影响**：任意域名可调用 MCP Server，可能绕过认证的跨站攻击
- **缓解**：
  1. 生产环境明确列出允许的 origin，禁止 `*`
  2. M365 Copilot 服务端调用本身不受 CORS 约束，CORS 仅对浏览器端工具有效
  3. 主要安全层应在 API Key 验证，而非 CORS

---

## 参考资料

- [FastMCP HTTP Deployment Guide](https://gofastmcp.com/deployment/http)
- [MCP Python SDK (Official)](https://github.com/modelcontextprotocol/python-sdk)
- [Render Blueprint YAML Reference](https://render.com/docs/blueprint-spec)
- [Render Free Tier Limitations](https://render.com/docs/free)
- [Render Environment Variables & Secrets](https://render.com/docs/configure-environment-variables)
- [CORS Policies for MCP Servers (MCPcat)](https://mcpcat.io/guides/implementing-cors-policies-web-based-mcp-servers/)
- [MCP Health Check Endpoints (MCPcat)](https://mcpcat.io/guides/building-health-check-endpoint-mcp-server/)
- [Build Declarative Agents for M365 Copilot with MCP](https://devblogs.microsoft.com/microsoft365dev/build-declarative-agents-for-microsoft-365-copilot-with-mcp/)
- [Fly.io Remote MCP Server Deployment](https://fly.io/docs/blueprints/remote-mcp-servers/)
- [FastMCP Session Management Issue #1180](https://github.com/modelcontextprotocol/python-sdk/issues/1180)
- [Deploying Remote MCP Server with Python and FastAPI](https://dev.to/christian_dennishinojosa/-deploying-a-remote-mcp-server-with-python-and-fastapi-1ilo)
- [Cloudflare: Streamable HTTP MCP Servers with Python](https://blog.cloudflare.com/streamable-http-mcp-servers-python/)
