# M365 Plugin 认证方案

> 调研日期：2026-03-29
> 来源：Microsoft Learn 官方文档、Copilot Developer Camp Labs、社区博客（developerscantina.com）、GitHub 参考实现

---

## 1. ApiKeyPluginVault 完整注册流程

### 1.1 什么是 ApiKeyPluginVault

`ApiKeyPluginVault` 是 M365 Copilot Plugin 认证机制之一，由 Teams 开发者门户（Teams Developer Portal）充当 **API Key 密钥保险箱**。开发者在 Portal 中注册并存储 API Key，M365 Copilot 运行时通过注册生成的 `reference_id`（注册 ID）从 Vault 中取出密钥，自动附加到对 MCP/API Server 的 HTTP 请求中。终端用户无需手动输入密钥，密钥在 Microsoft 侧安全托管。

### 1.2 注册步骤（Teams Developer Portal）

**入口：** https://dev.teams.microsoft.com → Tools → API key registration

| 步骤 | 操作 |
|---|---|
| 1 | 打开 [Teams Developer Portal](https://dev.teams.microsoft.com)，登录 M365 账号 |
| 2 | 左侧导航 → **Tools** → **API key registrations** |
| 3 | 若无已有注册：点击 **Create an API key**；若已有注册：点击 **New API key** |
| 4 | 填写注册表单（见下方字段说明） |
| 5 | 点击 **Add secret** → 粘贴实际 API Key 值 |
| 6 | 点击 **Save** → 系统生成 **API key registration ID**（即 `reference_id`） |
| 7 | 复制 registration ID，填入 plugin.json / ai-plugin.json 的 `reference_id` 字段 |
| 8 | 发布 Teams App 后，回到 Portal 将该注册绑定到已发布的 App ID |

### 1.3 注册表单字段说明

| 字段 | 说明 |
|---|---|
| **API key name** | 友好名称，仅作内部标识，如 `socialhub-mcp-key` |
| **Base URL** | 你的 API/MCP Server 的基础 URL，须与 OpenAPI 文档中 `servers` 数组条目一致，例如 `https://mcp.socialhub.ai` |
| **Target tenant** | 限制访问范围：`Home tenant only`（仅限本企业租户）或 `Any tenant`（多租户）。企业内部部署建议选 Home tenant only |
| **Target Teams App** | 若 App 尚未发布可先选 `Any Teams app`，发布后再绑定具体 App ID |

**注意：** 注册完成后你拿到的是 **registration ID（reference_id）**，不是 API Key 本身。实际 Key 值由 Portal 安全托管，不对外暴露明文。

### 1.4 Plugin 配置文件引用

在 `ai-plugin.json`（或 `plugin.json`）中引用该 registration ID：

```json
{
  "schema_version": "v2.4",
  "name_for_human": "SocialHub Analytics",
  "runtimes": [
    {
      "type": "OpenApi",
      "auth": {
        "type": "ApiKeyPluginVault",
        "reference_id": "${{SOCIALHUB_API_KEY_REGISTRATION_ID}}"
      },
      "spec": {
        "url": "openapi.json"
      }
    }
  ]
}
```

对于 **MCP Plugin（RemoteMCPServer）**，在 `plugin.json` 的 `remoteMcpServer` 对象中：

```json
{
  "remoteMcpServer": {
    "mcpServerUrl": "https://mcp.socialhub.ai/mcp",
    "authorization": {
      "type": "ApiKeyPluginVault",
      "referenceId": "${{SOCIALHUB_API_KEY_REGISTRATION_ID}}"
    }
  }
}
```

`${{...}}` 是 Teams Toolkit 的环境变量占位符语法，实际值存在 `env/.env.development` 或 `env/.env.production` 中，不提交到代码仓库。

---

## 2. API Key 传递机制（Header 格式）

### 2.1 三种传递方式

M365 Copilot 根据 OpenAPI 文档中 `securitySchemes` 的定义，自动决定如何附加 API Key：

| 传递方式 | OpenAPI securitySchemes 配置 | 实际 HTTP 请求 |
|---|---|---|
| **Bearer Token**（推荐） | `type: http`，`scheme: bearer` | `Authorization: Bearer <api_key>` |
| **自定义 Header** | `type: apiKey`，`in: header`，`name: X-API-KEY` | `X-API-KEY: <api_key>` |
| **Query Parameter** | `type: apiKey`，`in: query`，`name: api_key` | `?api_key=<api_key>` |

### 2.2 推荐配置（Bearer Token 方式）

在 OpenAPI/openapi.json 中：

```yaml
components:
  securitySchemes:
    ApiKeyAuth:
      type: http
      scheme: bearer

security:
  - ApiKeyAuth: []
```

服务端收到请求：`Authorization: Bearer <api_key_value>`

### 2.3 推荐配置（自定义 Header 方式）

```yaml
components:
  securitySchemes:
    ApiKeyHeader:
      type: apiKey
      in: header
      name: X-API-KEY

security:
  - ApiKeyHeader: []
```

服务端收到请求：`X-API-KEY: <api_key_value>`

**重要发现：** 对于 Copilot Studio 的 MCP connector，API Key 通过 `x-api-key` header 传递（小写，与大写的 `X-API-KEY` 在 HTTP/2 中等价）。另有来源指出 APIM 集成场景下使用 `Ocp-Apim-Subscription-Key` header。

**对本项目的建议：** 使用 Bearer Token 方式（`Authorization: Bearer`），这是最通用的格式，与 HTTP 标准吻合，且对后续迁移到 OAuth 影响最小。

### 2.4 MCP Plugin 与 API Plugin 的差异

- **API Plugin（OpenAPI 规范）**：完整支持以上三种 API Key 传递方式。
- **MCP Plugin（RemoteMCPServer）**：根据最新文档，MCP plugins 在某些场景下**不直接支持 API key authentication**，倾向于使用 OAuth。但 Agent Connector（通过 Teams 注册 MCP Server 的路径）支持 `ApiKeyPluginVault`。
- **Copilot Studio MCP Connector**：明确支持 API Key，通过 `x-api-key` header 传递。

---

## 3. 企业管理员统一部署方式

### 3.1 用户首次使用时的认证体验

当企业用户第一次在 M365 Copilot Chat 中调用配置了 `ApiKeyPluginVault` 的 Agent 时：

1. Copilot 提示用户确认数据连接（首次数据传输前的同意确认）。
2. 对于读取类操作（不修改数据），用户确认一次后后续不再提示。
3. 对于写入/修改类操作，每次均需用户确认。

**关键问题：ApiKeyPluginVault 中的 API Key 由开发者/管理员在 Teams Developer Portal 注册时写入，不是用户自己输入的。** 用户无需知道 API Key 的具体值。这与 OAuth 流程（用户需要自己登录授权）不同。

### 3.2 管理员统一推送（Teams Admin Center）

企业管理员可通过 **Teams Admin Center** 将 Teams App（含 Declarative Agent）统一推送给所有员工：

1. 打包 Teams App（`.zip`）并上传到 Teams Admin Center。
2. 在 **Teams Apps → Manage apps** 中找到该 App，设置为全租户可用或指定用户组。
3. 管理员点击 **Consent on behalf of your organization**（代表组织同意）——这会为租户所有用户完成授权，用户无需各自操作。
4. 通过 **App setup policies** 将 App 固定到用户的 Teams 侧边栏，实现零感知安装。

### 3.3 API Key 的企业级统一管理路径

```
SocialHub 管理后台
    └── 为企业客户生成独立 API Key（per-tenant）
            └── 企业 IT 管理员
                    ├── 在 Teams Developer Portal 注册该 API Key
                    │     → 得到 registration_id
                    └── 将 registration_id 写入 plugin.json
                            └── 打包并通过 Teams Admin Center 推送
                                    → 企业所有用户开箱即用
```

**结论：** 只需管理员操作一次注册 + 部署，所有员工无需任何配置即可使用，体验无缝。

### 3.4 API Plugin 认证：用户是否需要手动输入 Key？

不需要。`ApiKeyPluginVault` 的设计目的正是将 API Key 从用户侧隐藏。Key 由开发者/管理员在 Portal 注册，M365 Copilot 运行时自动附加到请求中，对普通用户完全透明。

---

## 4. MCP Server 端验证实现

### 4.1 Python FastAPI 中间件验证示例

```python
from fastapi import FastAPI, Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import secrets
import os

app = FastAPI()
security = HTTPBearer()

# API Keys 存储（实际应从数据库/环境变量读取）
# 格式: {api_key: tenant_id}
VALID_API_KEYS: dict[str, str] = {
    os.environ.get("TENANT_ACME_API_KEY", ""): "acme_corp",
    os.environ.get("TENANT_BETA_API_KEY", ""): "beta_corp",
}

async def verify_api_key(credentials: HTTPAuthorizationCredentials) -> str:
    """验证 Bearer Token 并返回 tenant_id，用于多租户隔离"""
    api_key = credentials.credentials

    # 使用 secrets.compare_digest 防止时序攻击
    for valid_key, tenant_id in VALID_API_KEYS.items():
        if valid_key and secrets.compare_digest(api_key, valid_key):
            return tenant_id

    raise HTTPException(
        status_code=401,
        detail="Invalid or missing API key",
        headers={"WWW-Authenticate": "Bearer"},
    )

# 中间件方式（统一拦截所有 /mcp 路径）
@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    if request.url.path.startswith("/mcp"):
        auth_header = request.headers.get("Authorization", "")
        x_api_key = request.headers.get("x-api-key", "")

        api_key = None
        if auth_header.startswith("Bearer "):
            api_key = auth_header[7:]
        elif x_api_key:
            api_key = x_api_key

        if not api_key:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing API key"}
            )

        # 验证 Key 并将 tenant_id 注入 request.state
        tenant_id = None
        for valid_key, tid in VALID_API_KEYS.items():
            if valid_key and secrets.compare_digest(api_key, valid_key):
                tenant_id = tid
                break

        if not tenant_id:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid API key"}
            )

        request.state.tenant_id = tenant_id

    return await call_next(request)
```

### 4.2 与现有 MCP Server 的集成

现有 `mcp_server/server.py` 通过 `tenant_id` 实现多租户隔离。HTTP Transport 层需要：

1. 在 FastAPI 路由层提取 `tenant_id`（从 API Key 映射）
2. 将 `tenant_id` 传入每次 MCP 工具调用的上下文
3. `_handle_*` 函数使用该 `tenant_id` 查询对应租户数据

```python
# 在 MCP HTTP 端点处理中
@app.post("/mcp")
async def handle_mcp(request: Request):
    tenant_id = request.state.tenant_id  # 由中间件注入
    # 传递给 MCP handler
    ...
```

### 4.3 双 Header 兼容策略

同时支持 `Authorization: Bearer` 和 `x-api-key` 两种 header，确保兼容：
- M365 Copilot API Plugin（OpenAPI 规范，通常用 Bearer）
- Copilot Studio MCP Connector（使用 `x-api-key`）
- 本地开发测试（curl 测试更方便用 `x-api-key`）

---

## 5. 安全建议（Key 管理、轮换、per-tenant 隔离）

### 5.1 Per-Tenant Key 架构（强烈推荐）

```
全局共享 Key（不推荐）          Per-Tenant Key（推荐）
─────────────────────          ─────────────────────────────────
所有企业客户用同一 Key          每个企业客户有独立 Key
一个 Key 泄露影响所有客户       一个 Key 泄露只影响单个客户
无法区分不同客户的访问          可精确审计每个客户的调用量
无法细粒度撤销权限              可独立撤销/轮换单个客户的 Key
```

**实现：**
- SocialHub 管理后台为每个企业客户生成唯一 API Key
- Key 与 `tenant_id` 在后端数据库中绑定
- MCP Server 通过 Key → `tenant_id` 映射决定数据访问范围
- 符合项目现有的 "多租户隔离通过 tenant_id 实现" 原则

### 5.2 API Key 格式建议

```
格式：sh_<tenant_prefix>_<random_256bit>
示例：sh_acme_4a7f8c2e1b9d3f6a8e2c4b7d1f9a3e5c8b2d4f6a8e1c3b5d7f9a2e4c6b8d0f2
```

- 使用 `secrets.token_hex(32)` 生成（Python 加密安全随机数）
- 长度 ≥ 32 字节（256 bit），防止暴力破解
- 加前缀方便识别来源和格式

### 5.3 存储安全

| 存储位置 | 建议 |
|---|---|
| 服务端数据库 | 存储 Key 的哈希值（SHA-256），不存明文；验证时哈希后比对 |
| 环境变量 | 通过 Render Secret Files / Render Environment Variables 注入，不提交到 git |
| Teams Developer Portal Vault | Microsoft 安全托管，无需额外处理 |
| 企业 IT 侧 | 建议使用 Azure Key Vault 存储并定期轮换 |

**注意：** 若存储哈希，验证时需用 `hmac.compare_digest(hash(input), stored_hash)` 防止时序攻击。或在允许的情况下存储加密形式。

### 5.4 Key 轮换策略

```
触发轮换场景：
1. 定期轮换（推荐 90 天）
2. 疑似泄露（立即轮换）
3. 客户安全审计要求
4. 员工离职（若员工知晓 Key）

轮换流程（零停机）：
1. SocialHub 管理后台生成新 Key，新旧 Key 同时有效（过渡期 7 天）
2. 企业 IT 管理员在 Teams Developer Portal 更新 API key registration 的 secret
3. 确认新 Key 生效后，撤销旧 Key
4. 更新完成，无服务中断
```

MCP Server 验证层需支持 **同一租户多个有效 Key**（便于轮换过渡期）：

```python
# 支持一个 tenant 有多个有效 Key
TENANT_KEYS: dict[str, list[str]] = {
    "acme_corp": ["old_key_hash", "new_key_hash"],  # 轮换过渡期
    "beta_corp": ["current_key_hash"],
}
```

### 5.5 安全加固清单

- [ ] 所有 API Key 验证使用 `secrets.compare_digest` 防时序攻击
- [ ] HTTPS Only（M365 Copilot 要求，Render 默认提供 TLS）
- [ ] 请求频率限制（Rate Limiting）—— 按 tenant_id 限速，防滥用
- [ ] API Key 访问日志（记录时间戳、tenant_id、调用工具名，不记录 Key 明文）
- [ ] Key 有效期设置（可选，结合企业安全策略）
- [ ] 禁止将 Key 嵌入客户端代码或提交到 git

---

## 6. 与 OAuthPluginVault 的选择建议

### 6.1 对比矩阵

| 维度 | ApiKeyPluginVault | OAuthPluginVault（Entra ID） |
|---|---|---|
| **实现复杂度** | 低（Portal 注册 + 一个字段） | 高（注册 Entra App、配置回调 URL、处理 Token 流程） |
| **用户体验** | 无需用户操作，对用户透明 | 用户首次需点击授权（OAuth 同意流程） |
| **用户级审计** | 无（所有用户共享同一 Key） | 有（每个用户用自己的 Token，可精确追踪） |
| **企业安全合规** | 中（共享密钥） | 高（符合 Zero Trust、用户级身份） |
| **Per-tenant 隔离** | 手动实现（Key → tenant_id 映射） | 自动（Azure AD Tenant 天然隔离） |
| **Key 泄露风险** | 存在（静态密钥） | 低（Token 有效期短，自动刷新） |
| **多用户场景** | 不区分用户身份 | 区分用户身份，支持 user-level 权限 |
| **企业 IT 部署** | 管理员一次配置，用户无感 | 需用户各自授权（或管理员 consent on behalf） |
| **适用场景** | 服务对服务（S2S）、企业内部工具、SaaS 多租户平台 | 需要用户级权限、审计合规要求高的场景 |

### 6.2 SocialHub 项目的选择建议

**推荐：ApiKeyPluginVault（阶段 1）**

理由：
1. **项目现有架构**：MCP Server 已通过 `tenant_id` 实现数据隔离，API Key → `tenant_id` 映射天然契合
2. **部署简单**：企业客户（SocialHub 的 B2B 客户）IT 管理员只需一次 Portal 注册，员工无需任何操作
3. **服务特性**：SocialHub 是客户数据分析读取服务，不写入用户个人数据，用户级身份区分不是强需求
4. **实现速度**：相比 OAuth 需要注册 Entra App + 完整授权流程，API Key 方案可在数天内完成

**未来可选升级路径（阶段 2）：OAuthPluginVault**
- 当企业客户提出用户级权限管理需求时
- 当需要精细的访问审计日志（谁查了什么客户数据）时
- 使用 Teams Toolkit 可相对平滑地迁移

### 6.3 认证方式完整清单（M365 Copilot 支持）

| 类型 | 说明 |
|---|---|
| `ApiKeyPluginVault` | API Key（本文主题） |
| `OAuthPluginVault` | OAuth 2.0 Authorization Code Flow（Entra ID / 第三方 IdP） |
| `MicrosoftEntra` | Entra ID SSO（最高安全等级，用户无感登录） |
| `None` | 无认证（仅用于公开 API，不推荐生产环境） |

---

## 7. 关键发现和对本项目的启示

### 7.1 重要发现汇总

**发现 1：MCP Plugin vs API Plugin 的认证支持差异**

> "MCP plugins don't support API key authentication." （来源：Microsoft Learn）

这是一个关键限制。官方文档指出，通过 `RemoteMCPServer` 运行时的 **MCP Plugin** 本身对 API Key 认证支持有限制，而通过 OpenAPI 规范运行时的 **API Plugin** 完整支持。

**但是**，通过 **Teams 的 Agent Connector 路径**（`Register MCP Servers as Agent Connectors`）和 **Copilot Studio 的 MCP Connector** 确实支持 API Key。GitHub 参考实现 `jmservera/declarative-agent-mcp-apikey` 展示了 Declarative Agent 使用 `ApiKeyPluginVault` 连接 MCP Server 的可行方案。

**结论：** 需要通过 Agents Toolkit（ATK）生成配置文件，ATK 会自动处理 MCP + API Key 的集成。或者为 MCP Server 同时提供 OpenAPI 端点（兼容 API Plugin 路径）。

**发现 2：Teams Developer Portal 是 API Key 的唯一注册入口**

不能在代码或配置文件中直接写死 API Key。必须先在 Portal 注册，获取 registration ID，再在 plugin 配置中引用该 ID。这是安全设计，确保 Key 不出现在代码仓库中。

**发现 3：`reference_id` vs `referenceId` 的大小写差异**

- API Plugin（`ai-plugin.json` schema v2.4）：字段名为 `reference_id`（下划线）
- MCP Plugin / Agent Connector（`plugin.json`）：字段名为 `referenceId`（驼峰）

实际使用时需注意 schema 版本匹配。

**发现 4：Teams Toolkit（ATK）自动化注册流程**

Microsoft 365 Agents Toolkit（VS Code 扩展）可以自动：
1. 调用 Developer Portal API 注册 API Key
2. 将 registration ID 存入 `env/.env.development`
3. 自动注入 `ai-plugin.json` 的 auth 字段

参考：`jmservera/declarative-agent-mcp-apikey` 仓库

**发现 5：SSE Transport 已废弃**

> "Copilot Studio no longer supports SSE for MCP after August 2025."

M365 Copilot 生态已全面切换到 **Streamable HTTP Transport**（MCP 1.0 规范的 HTTP 传输模式）。本项目 MCP Server 需实现 HTTP Streamable Transport（`/mcp` POST 端点），不能使用已废弃的 SSE 模式。

**发现 6：企业管理员 Consent on Behalf 机制**

管理员在 Teams Admin Center 部署 App 时，可选择 "Consent on behalf of your organization"，一次性为所有用户完成授权。这使得 `ApiKeyPluginVault` 方案的企业部署真正做到零用户操作。

### 7.2 对本项目的直接启示

| 启示 | 影响 | 行动项 |
|---|---|---|
| API Key 需在 Teams Developer Portal 注册 | 部署文档需包含 Portal 注册步骤 | 编写管理员操作手册 |
| Key 不能硬编码，用 `${{ENV_VAR}}` 占位符 | `plugin.json` 使用环境变量引用 | 确保构建流程注入 env 变量 |
| MCP Plugin 的 API Key 支持需验证 | 可能需要选择 API Plugin（OpenAPI）路径 | 调研 build-mcp-plugins 文档 |
| 推荐 Bearer Token 格式传递 Key | MCP Server 要支持 `Authorization: Bearer` | HTTP 中间件实现 |
| Per-Tenant Key 是正确架构 | 与现有 `tenant_id` 隔离设计完美契合 | Key 注册流程绑定 tenant_id |
| SSE 已废弃，用 Streamable HTTP | MCP Server 必须实现 HTTP POST 端点 | 优先实现 HTTP Transport |
| 管理员 Consent 机制 | 企业部署体验极佳，IT 友好 | 在部署文档中说明此特性 |

### 7.3 推荐的认证实现架构（SocialHub 项目）

```
企业 IT 管理员
    │
    ├─ 在 Teams Developer Portal 注册 API Key
    │       → 得到 registration_id
    │
    ├─ 将 registration_id 写入 .env.production
    │
    └─ 通过 Teams Admin Center 上传并推送 Teams App
            │
            ▼
    M365 Copilot 运行时
            │  ApiKeyPluginVault（从 Vault 取 Key）
            │  Authorization: Bearer <api_key>
            ▼
    SocialHub MCP Server（HTTPS, Render 部署）
            │
            ├─ Bearer Token 验证中间件
            ├─ Key → tenant_id 映射
            └─ MCP Tool Handler（tenant_id 隔离查询）
                    │
                    └─ 返回 list[TextContent] → M365 Copilot
```

---

## 参考资源

- [Configure Authentication for plugins in Agents in Microsoft 365 Copilot](https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/api-plugin-authentication)
- [Build plugins from an MCP server for Microsoft 365 Copilot](https://learn.microsoft.com/en-us/microsoft-365-copilot/extensibility/build-mcp-plugins)
- [Register MCP Servers as Agent Connectors for Microsoft 365](https://learn.microsoft.com/en-us/microsoftteams/platform/m365-apps/agent-connectors)
- [API plugin manifest schema 2.4](https://learn.microsoft.com/en-us/microsoft-365-copilot/extensibility/api-plugin-manifest-2.4)
- [GitHub: jmservera/declarative-agent-mcp-apikey](https://github.com/jmservera/declarative-agent-mcp-apikey)（Declarative Agent + MCP + API Key 参考实现）
- [Consuming an authenticated MCP server with a declarative agent in Copilot Chat](https://www.developerscantina.com/p/mcp-declarative-agent/)
- [Using Model Context Protocol in agents - Copilot Studio and authentication with API key](https://www.developerscantina.com/p/mcp-copilot-studio-api-key/)
- [How to Add an MCP Server to Copilot Studio Using an API Key (Mar 2026)](https://medium.com/a-techies-tidbits/how-to-add-an-mcp-server-to-copilot-studio-using-an-api-key-e1ddaeaa91b1)
- [Lab E10 - Connect Declarative Agent to OAuth-Protected MCP Server](https://microsoft.github.io/copilot-camp/pages/extend-m365-copilot/10-mcp-auth/)
- [Authentication support in TypeSpec for Microsoft 365 Copilot](https://learn.microsoft.com/en-us/microsoft-365-copilot/extensibility/typespec-authentication)
- [m365copilot-docs/api-plugin-authentication.md (GitHub)](https://github.com/MicrosoftDocs/m365copilot-docs/blob/main/docs/api-plugin-authentication.md)
