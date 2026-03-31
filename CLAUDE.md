# SocialHub CLI

## 项目性质

面向电商/零售企业运营团队的客户智能平台 CLI 工具。用户通过自然语言或命令行直接查询客户留存、RFM 分层、订单趋势、营销活动等分析数据，无需进入 BI 系统。核心能力：自然语言 → AI 解析 → 命令验证 → 安全执行。

---

## 技术栈

### CLI 核心
- 语言: Python 3.10+
- 命令框架: Typer + Rich（终端渲染）
- AI Provider: Azure OpenAI（默认）/ OpenAI（可切换）
- HTTP 客户端: httpx
- 配置: Pydantic v2 (`~/.socialhub/config.json`)
- 安全: cryptography（Ed25519 签名验证）

### MCP Server
- 协议: MCP 1.8+（stdio 默认；HTTP Streamable Transport 可选，兼容 M365 Copilot）
- 工具数量: 36+ 分析工具（其中 8 个暴露给 M365 Declarative Agent）
- 缓存: 内存 TTL 缓存（900s），cache key 含 tenant_id 防跨租户泄漏
- HTTP 认证: API Key（环境变量 `MCP_API_KEYS=key1:tenant1,key2:tenant2`）
- HTTP 部署: Render（`pip install -e ".[http]"`，`uvicorn mcp_server.http_app:app`）

### Skills Store 后端
- 框架: FastAPI + SQLAlchemy
- 数据库: PostgreSQL（Render 托管）
- 迁移: Alembic
- 认证: JWT（PBKDF2 密码哈希）
- 部署: Render（`render-clean` 分支）

### Skills Store 前端
- 框架: React 18 + Vite + React Router

### 工具链
- 测试: pytest + pytest-cov
- Lint: ruff（行长 100）
- 格式化: black（行长 100）
- 类型检查: mypy

---

## 目录结构

```
cli/                    # CLI 主包（入口: cli/main.py:cli()）
  commands/             # 命令模块（每个文件对应一个 Typer sub-app）
    analytics.py        # sh analytics overview/customers/orders/retention/...
    customers.py        # sh customers search/list/get/export
    campaigns.py        # sh campaigns
    skills.py           # sh skills install/uninstall/list/login/logout
    heartbeat.py        # sh heartbeat（定时任务调度）
    config_cmd.py       # sh config get/set
    workflow.py         # sh workflow（业务场景快捷方式）
    ...
  ai/                   # AI 集成层
    client.py           # call_ai_api()：Azure/OpenAI provider 调用
    prompt.py           # SYSTEM_PROMPT（命令参考 + 格式规范）
    parser.py           # 从 AI 响应提取 [PLAN_START]...[PLAN_END] 等标记
    validator.py        # 命令合法性校验（对照 Typer 命令树）
    executor.py         # 多步计划执行（subprocess, shell=False）
    insights.py         # 执行完成后生成 AI 洞察摘要
  skills/               # Skills 插件系统
    manager.py          # 10步安装流水线（下载→哈希→签名→权限→解压）
    loader.py           # 动态 importlib 加载 + sandbox 激活
    security.py         # Ed25519 签名验证 + SHA-256 + CRL 吊销检查
    store_client.py     # 官方 Store REST 客户端
    registry.py         # ~/.socialhub/skills/registry.json 读写
    sandbox/            # 沙箱隔离
      filesystem.py     # monkey-patch builtins.open + pathlib.Path
      network.py        # monkey-patch socket
      execute.py        # monkey-patch subprocess + os.system
  config.py             # Pydantic v2 Config 模型（AIConfig/MCPConfig/...）
  main.py               # CLI 入口：智能模式检测（自然语言 vs 注册命令）

mcp_server/             # MCP Server 包（入口: socialhub-mcp 命令）
  __main__.py           # stdio / HTTP 传输启动（--transport [stdio|http] --port）
  server.py             # 工具定义 + 36+ handler + 缓存层（支持 tenant_id 隔离）
  auth.py               # API Key 认证中间件（Starlette BaseHTTPMiddleware + ContextVar 多租户）
  http_app.py           # HTTP Streamable Transport ASGI 应用（/health + /mcp）

build/m365-agent/       # M365 Teams App 包（zip 后上传 Teams Developer Portal）
  manifest.json         # Teams App manifest v1.17
  declarativeAgent.json # M365 Declarative Agent（Instructions + 6 Conversation Starters）
  plugin.json           # M365 Plugin（ApiKeyPluginVault + MCPServer runtime）
  mcp-tools.json        # 8 个分析工具 Schema（token 预算 1172/3000）

render.yaml             # Render Blueprint（Starter plan，/health 探针，单 worker）

skills-store/           # Skills Store 服务（独立部署）
  backend/app/
    main.py             # FastAPI app
    models/             # SQLAlchemy 模型
    routers/            # API 路由（auth/users/user_skills/public/admin/developer）
    schemas/            # Pydantic schemas
    services/           # 业务逻辑
    auth/               # JWT 依赖（dependencies.py + jwt.py）
  alembic/              # 数据库迁移

frontend/               # React 18 Storefront（Vite 构建）
  src/pages/            # CatalogPage / SkillDetailPage / UserPage / UserLoginPage
  src/lib/              # api.js / session.js

docs/                   # 静态 GitHub Pages（已冻结，勿修改）

tests/                  # pytest 测试套件
```

---

## 命令入口

```bash
socialhub          # CLI 主命令（cli/main.py:cli）
socialhub-mcp      # MCP Server（mcp_server/__main__.py:main）
```

---

## 测试与检查命令

```bash
# 单测（跑失败即停）
pytest tests/ -x -q

# 带覆盖率
pytest tests/ --cov=cli --cov-report=term-missing

# Lint
ruff check cli/ mcp_server/

# 格式检查
black --check cli/ mcp_server/

# 类型检查
mypy cli/

# 安装开发依赖
pip install -e ".[dev]"
```

---

## 架构原则

- **自然语言安全执行链**: 所有 AI 生成的命令必须经过 `validator.py` 校验（对照 Typer 命令树），再由 `executor.py` 以 `shell=False` 子进程执行，输出结果后调用 `insights.py` 生成洞察
- **MCP 优先集成**: 对外集成（Claude Desktop / GitHub Copilot / M365 Copilot）统一走 MCP 协议，不暴露裸 REST
- **Skills 零信任沙箱**: 第三方 Skills 在 filesystem + network + execute 三层沙箱中运行，安装前必须完成 Ed25519 签名验证 + SHA-256 哈希验证 + CRL 吊销检查
- **配置分层**: 代码内默认值 → `~/.socialhub/config.json` → 环境变量（最高优先级）
- **多租户隔离**: MCP 调用通过 `tenant_id` 隔离数据，禁止跨租户查询
- **Store URL 硬编码**: `https://skills.socialhub.ai/api/v1` 在代码中硬编码，不允许运行时覆盖，防止供应链劫持

---

## 项目红线（code review 逐条检查）

### CLI / AI 执行层
- **禁止 `shell=True`**: `executor.py` 中所有 `subprocess.run()` 必须 `shell=False`
- **危险字符必须过滤**: AI 生成参数中的 `;` `&&` `||` `|` `` ` `` `$` 必须被 `executor.py` 拦截，不得透传给子进程
- **AI 命令必须通过 validator**: `call_ai_api()` 的输出在执行前必须经过 `validate_command()`，严禁直接 `eval` 或 `exec`

### Skills 安全
- **签名验证不可跳过**: `manager.py` 安装流水线中 Ed25519 签名验证和 SHA-256 哈希验证是强制步骤，不允许添加 `--skip-verify` 类参数
- **Store URL 不可覆盖**: `store_client.py` 中官方 Store 地址是硬编码常量，禁止从配置或参数读取
- **沙箱必须激活**: Skills 执行前必须通过 `SandboxManager` 激活三层隔离，不允许直接 `importlib.import_module()` 跳过沙箱

### MCP Server
- **工具处理器返回类型**: 所有 `_handle_*` 函数必须返回 `list[TextContent]`，禁止返回裸字符串或抛出未捕获异常
- **工具名称验证**: `call_tool()` 必须通过 `_HANDLERS.get(name)` 查找，不存在时返回错误 TextContent，不抛出异常

### Skills Store 后端
- **账户表严格隔离**: `developers` 表（技能开发者/管理员）和 `users` 表（Store 用户）绝对不能混用；开发者 JWT 不能访问 `/api/v1/users/me/*`，用户 JWT 不能访问开发者/管理员端点
- **密码哈希**: 所有密码必须使用 PBKDF2 哈希存储，禁止明文或可逆加密
- **权限检查在后端**: 前端不作为任何权限决策的依据

---

## 硬约束

| 约束 | 说明 |
|---|---|
| `docs/` 目录冻结 | 当前 GitHub Pages 生产站点，任何情况下不得修改 |
| `developers.saved_skills` 冻结 | 已废弃的遗留字段，保持原样，不得删除或迁移 |
| `frontend/` 与 `docs/` 独立 | 所有前端新功能只在 `frontend/src/` 中进行，不同步到 `docs/` |
| Web Install ≠ 文件下载 | 点击"Install"只调用 `POST /api/v1/users/me/skills/{name}`，记录到库；实际 zip 下载只通过 CLI `socialhub skills install` 执行 |
| 用户库双源头 | `backend user_skills` 表 → Web UI 数据源；`~/.socialhub/skills/registry.json` → CLI 执行数据源 |

---

## 部署信息

| 服务 | 地址 | 分支 |
|---|---|---|
| Skills Store 后端 | `https://skills-store-backend.onrender.com` | `render-clean` |
| 静态 Storefront | `https://huangchunbo2025.github.io/Socialhub-CLI/` | `render-clean` / `docs/` |
| React Storefront 预览 | `https://huangchunbo2025.github.io/Socialhub-CLI/react-preview/` | — |

---

## API 契约（CLI ↔ Backend）

CLI 的 `store_client.py` 对以下接口有硬编码依赖，响应格式不得随意更改：

```
POST /api/v1/users/login
  响应: { "data": { "access_token": "...", "expires_in": 86400, "user": { "name": "..." } } }

GET /api/v1/users/me/skills
  响应: { "data": { "items": [{ "skill_name", "display_name", "version", "category", "is_enabled", "downloaded_at", "description" }], "total": N } }

POST /api/v1/users/me/skills/{skill_name}  → 201
DELETE /api/v1/users/me/skills/{skill_name} → 204
PATCH /api/v1/users/me/skills/{skill_name}/toggle → 200
```

---

## MCP Server 集成

### Claude Desktop / GitHub Copilot CLI 配置

```json
{
  "mcpServers": {
    "socialhub": {
      "command": "socialhub-mcp",
      "env": { "MCP_TENANT_ID": "<tenant_id>" }
    }
  }
}
```

### 环境变量

```bash
MCP_SSE_URL       # MCP SSE 端点
MCP_POST_URL      # MCP 消息端点
MCP_TENANT_ID     # 租户 ID（stdio 模式必须；HTTP 模式由 API Key 自动映射）
MCP_API_KEYS      # HTTP 模式 API Key 映射（格式: key1:tenant1,key2:tenant2）
MCP_DATABASE      # 默认数据库名
AI_PROVIDER       # azure | openai（覆盖 config.json）
AZURE_OPENAI_ENDPOINT
AZURE_OPENAI_API_KEY
AZURE_OPENAI_DEPLOYMENT
OPENAI_API_KEY
