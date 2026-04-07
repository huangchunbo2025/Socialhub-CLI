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
- 协议: MCP 1.8+（**HTTP Streamable Transport 为生产主路径**，兼容 M365 Copilot；stdio 用于本地调试）
- 工具数量: 36+ 分析工具（其中 8 个暴露给 M365 Declarative Agent）
- 缓存: 内存 TTL 缓存（900s），cache key 含 tenant_id 防跨租户泄漏；`_inflight` 并发上限 500 请求
- HTTP 认证: API Key（环境变量 `MCP_API_KEYS=key1:tenant1,key2:tenant2`）
- HTTP 部署: Render（`pip install -e ".[http]"`，`uvicorn mcp_server.http_app:app`）
- Analytics 适配层: `cli/analytics/mcp_adapter.py` 是 MCP Server 访问 CLI 分析能力的稳定接口，不得绕过直接 import `cli.commands.analytics`

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
    insights.py         # 执行完成后生成 AI 洞察摘要（兼调用 memory.save_insight_from_ai）
    prompt.py           # BASE_SYSTEM_PROMPT（SYSTEM_PROMPT 为兼容别名）
  memory/               # 持久化记忆系统（4层：L4偏好/L3洞察/L2摘要/L4业务上下文）
    manager.py          # MemoryManager 统一入口（非单例，每次 CLI 调用新建）
    store.py            # 文件 CRUD（原子写入 0o600，TTL+数量裁剪）
    injector.py         # 动态 SYSTEM_PROMPT 拼装（tiktoken budget，切割顺序 L3→L2）
    extractor.py        # 会话结束 LLM 提取（daemon thread + 30s timeout）
    pii.py              # PII 扫描：手机/身份证/邮箱/订单号
    models.py           # Pydantic v2 数据模型（MemoryContext/Insight/Campaign 等）
    存储位置: ~/.socialhub/memory/  # user_profile.yaml / analysis_insights/ / session_summaries/
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

# 记忆管理子命令
sh memory status          # 查看记忆状态
sh memory list [--type]   # 列出记忆（profile/insights/summaries/campaigns）
sh memory show <id>       # 查看单条记忆详情
sh memory set <key> <val> # 设置偏好（key格式：analysis.default_period）
sh memory delete <id>     # 删除记忆条目
sh memory clear           # 清空记忆层
sh memory init            # 交互式初始化（非TTY模式返回默认值）
sh memory add-campaign    # 添加活动（--id/--name/--start/--end）
sh memory update-campaign # 更新活动效果摘要
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
- **配置分层**: 代码内默认值 → `~/.socialhub/config.json` → 环境变量（最高优先级，由 `_apply_env_overrides()` 统一处理，包括 AI 和 MCP 字段）
- **Skills 下载强制 TLS**: `store_client.py` 始终以 `verify=True` 请求，忽略全局 `NetworkConfig.ssl_verify`，防止供应链劫持
- **多租户隔离**: MCP 调用通过 `tenant_id` 隔离数据，禁止跨租户查询
- **Store URL 硬编码**: `https://skills.socialhub.ai/api/v1` 在代码中硬编码，不允许运行时覆盖，防止供应链劫持

---

## 项目红线（code review 逐条检查）

### CLI / AI 执行层
- **禁止 `shell=True`**: `executor.py` 中所有 `subprocess.run()` 必须 `shell=False`
- **危险字符必须过滤**: AI 生成参数中的 `;` `&&` `||` `|` `` ` `` `$` 必须被 `executor.py` 拦截，不得透传给子进程
- **AI 命令必须通过 validator**: `call_ai_api()` 的输出在执行前必须经过 `validate_command()`，严禁直接 `eval` 或 `exec`

### 记忆系统
- **PII 写入前必须扫描**: 任何调用 `store.save_insight()` 或 `store.save_summary()` 之前必须经过 `pii.scan_and_mask()`，检测到 PII 则跳过写入
- **`call_ai_api()` 不持有 MemoryManager**: 系统 prompt 由调用方（`main.py`/`commands/ai.py`）通过 `mm.build_system_prompt(ctx)` 预构建后以 `system_prompt=` 参数传入，禁止在 `call_ai_api()` 内部创建 MemoryManager
- **Skills 不得访问 `.socialhub/memory`**: `filesystem.py` 的 `PROTECTED_PATHS` 已包含该路径，不可删除此保护
- **记忆失败不阻塞 AI 调用**: MemoryManager 所有 public 方法必须内部 catch 异常、优雅降级，严禁向上抛出影响主流程

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

## 异常策略层次

不同层使用不同的异常处理策略，新代码应遵守所在层的约定：

| 层次 | 策略 | 示例 |
|---|---|---|
| Commands 层（`cli/commands/`） | **fail-fast** — 向用户打印错误并 `raise typer.Exit(1)` | 参数缺失、配置不合法 |
| AI 执行层（`cli/ai/executor.py`） | **fail-fast + 可选继续** — 非交互模式直接中止；交互模式提示用户是否继续 | plan 步骤失败 |
| AI 客户端（`cli/ai/client.py`） | **retry with backoff** — 最多重试 3 次，指数退避 | 网络超时、API 限流 |
| Memory 层（`cli/memory/`） | **graceful degrade** — 所有 public 方法内部 catch，返回默认值，**绝不向上抛出** | 文件读写失败、TTL 裁剪异常 |
| MCP Server（`mcp_server/`） | **返回错误 TextContent** — handler 不抛异常，通过 `list[TextContent]` 返回错误信息 | 工具参数非法、后端不可达 |

## 环境变量清单

所有环境变量由 `cli/config.py::_apply_env_overrides()` 统一处理（最高优先级，覆盖 config.json）：

| 变量 | 说明 | 示例 |
|---|---|---|
| `AI_PROVIDER` | AI Provider：azure / openai | `azure` |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI 端点 | `https://xxx.openai.azure.com` |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API Key | — |
| `AZURE_OPENAI_DEPLOYMENT` | Azure 部署名称 | `gpt-4o` |
| `AZURE_OPENAI_API_VERSION` | Azure API 版本 | `2024-08-01-preview` |
| `OPENAI_API_KEY` | OpenAI API Key | — |
| `OPENAI_MODEL` | OpenAI 模型名称 | `gpt-4o-mini` |
| `MCP_SSE_URL` | MCP SSE 端点 | `http://host:port/sse` |
| `MCP_POST_URL` | MCP 消息端点 | `http://host:port/message` |
| `MCP_TENANT_ID` | 租户 ID（stdio 模式必须） | `demoen` |
| `MCP_DATABASE` | 默认数据库名 | `das_demoen` |
| `MCP_API_KEY` | MCP API Key（HTTP 模式） | — |
| `SOCIALHUB_OAUTH_ENABLED` | 启用 OAuth2 gate（1/true/yes） | `false` |
| `SOCIALHUB_OAUTH_AUTH_URL` | Auth API 地址 | — |
| `SOCIALHUB_TRACE_ENABLED` | 启用 AI 决策追踪（1/true/yes） | `true` |
| `SOCIALHUB_TRACE_DIR` | trace 日志目录 | `~/.socialhub` |
| `SOCIALHUB_CA_BUNDLE` | 自定义 CA 证书路径 | `/etc/ssl/custom.pem` |
| `SOCIALHUB_SSL_VERIFY` | SSL 验证开关（1/true/yes） | `true` |
| `HTTP_PROXY` / `HTTPS_PROXY` | 代理设置（标准 env） | — |

> 新增环境变量时，必须同步更新 `_apply_env_overrides()` 中的 env map，不要在字段 `default_factory` 中读取 env（避免双重读取）。

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
MCP_DATABASE      # 默认数据库名（通常不需要设置，由下面的库路由接管）

# 各租户数据库路由（格式: tenant_id:database，多个用逗号分隔）
# 不配置时默认值为 das_{tenant_id} / dts_{tenant_id} / datanow_{tenant_id}
DAS_DATABASE      # DAS 库映射，例: uat:das_test,dev:das_dev
DTS_DATABASE      # DTS 库映射，例: uat:dts_test
DATANOW_DATABASE  # DataNow 库映射，例: uat:datanow_test

# SQL 自动库路由规则（MCPClient._rewrite_sql() 实现）：
# ads_/dwd_/dim_/dws_ 前缀 → DAS_DATABASE
# vdm_ 前缀               → DTS_DATABASE
# t_/v_ 前缀              → DATANOW_DATABASE
# 已含 db.table 格式的 SQL 不重写

# SocialHub App 凭证（优先级低于 Portal DB 配置）
# 格式: tenant_id:app_id:app_secret
MCP_TENANT_CREDS  # 示例: uat:your_app_id:your_app_secret

# AI Provider
AI_PROVIDER       # azure | openai（覆盖 config.json）
AZURE_OPENAI_ENDPOINT
AZURE_OPENAI_API_KEY
AZURE_OPENAI_DEPLOYMENT
OPENAI_API_KEY
```

---

## SAP Joule 集成

将 MCP Server 接入 SAP Joule Studio，无需修改服务端代码，纯配置实现。

> 官方文档：[Add MCP Servers to Your Joule Agent](https://help.sap.com/docs/Joule_Studio/45f9d2b8914b4f0ba731570ff9a85313/3d9dfad0bc39468292d508f0808a12fe.html)

### 官方要求

| 要求 | 说明 |
|------|------|
| 传输协议 | HTTP Streamable（SSE 不支持）|
| Destination 类型 | 必须是 Streamable HTTPS-type |
| 认证方式 | `NoAuthentication`（通过 `URL.headers` 注入静态 Header）|
| 额外属性 | `sap-joule-studio-mcp-server = true` |
| URL 限制 | Destination URL 不能以 `/mcp` 结尾（Joule 自动追加）|
| Path 限制 | MCP path 不能含 `? : = .` |

### 现有服务兼容性

| 检查项 | 现状 | 状态 |
|--------|------|------|
| HTTP Streamable 传输 | `StreamableHTTPSessionManager(stateless=True)` | ✅ |
| `/mcp` 端点 | `Mount("/mcp", ...)` | ✅ |
| HTTPS | Render 自动提供 | ✅ |
| API Key 认证 | 支持 `X-API-Key` Header | ✅ 通过 BTP Destination `URL.headers` 注入 |

### BTP Destination 配置

在 SAP BTP Cockpit → Connectivity → Destinations 创建：

```
Name:           socialhub-mcp
Type:           HTTP
URL:            https://socialhub-mcp.onrender.com    ← 基础 URL，不含 /mcp
Authentication: NoAuthentication
ProxyType:      Internet

Additional Properties:
  sap-joule-studio-mcp-server  =  true
  URL.headers.X-API-Key        =  <your_api_key>
```

`URL.headers.X-API-Key` 将 API Key 静态注入到每个请求，`auth.py` 中间件识别后映射到对应 `tenant_id`，认证链路完整。

### Joule Studio 操作步骤

1. Joule Studio → Agent → **MCP Servers** tab → **Add MCP Server**
2. 选择 Destination `socialhub-mcp`
3. **Path**: `/mcp`（默认值，无需修改）
4. 填写 Name 和 Description（Description 影响 Joule 决策何时调用此 Server）
5. 保存 → Joule 自动发起 `POST <base_url>/mcp` 完成 initialize

### Joule vs M365 Copilot 对比

| 项目 | SAP Joule Studio | M365 Declarative Agent |
|------|-----------------|----------------------|
| 传输协议 | HTTP Streamable | HTTP Streamable |
| 认证 | BTP Destination NoAuth + `URL.headers` | ApiKeyPluginVault |
| SSE | 不支持 | 不支持 |
| 配置入口 | BTP Cockpit + Joule Studio | Teams Developer Portal |
| 工具暴露 | 所有工具（Namespace 隔离）| 8 个精选工具（mcp-tools.json）|
