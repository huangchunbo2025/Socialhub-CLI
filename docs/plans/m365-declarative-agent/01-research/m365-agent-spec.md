# M365 Declarative Agent + Plugin 规范

> 调研时间：2026-03-29
> 数据来源：Microsoft Learn 官方文档（截至 2026-03-26 最新版本）

---

## declarativeAgent.json 完整字段参考

**JSON Schema URL**：`https://developer.microsoft.com/json-schemas/copilot/declarative-agent/v1.6/schema.json`

### 根对象字段

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `$schema` | String | 推荐 | — | 指向 schema.json URL |
| `version` | String | **必填** | 固定值 `"v1.6"` | Schema 版本 |
| `id` | String | 可选 | — | Manifest 标识符 |
| `name` | String | **必填** | 可本地化；≥1 非空白字符；≤100 字符 | Agent 名称 |
| `description` | String | **必填** | 可本地化；≥1 非空白字符；≤1000 字符 | Agent 描述 |
| `instructions` | String | **必填** | ≥1 非空白字符；**≤8000 字符** | 详细行为指令 |
| `capabilities` | Array\<Capabilities\> | 可选 | 每种 capability 类型最多一个 | 知识/能力声明 |
| `conversation_starters` | Array\<ConversationStarter\> | 可选 | **最多 6 个**（文档另一处写 12，以 6 为准） | 对话起始建议 |
| `actions` | Array\<Action\> | 可选 | **1-10 个** | 插件（Plugin）引用 |
| `behavior_overrides` | BehaviorOverrides | 可选 | — | 行为覆盖配置 |
| `disclaimer` | Disclaimer | 可选 | — | 对话开始时显示的免责声明 |
| `sensitivity_label` | SensitivityLabel | 可选 | 仅当有嵌入文件时有效（功能尚未上线） | Purview 敏感度标签 |
| `worker_agents` | Array\<WorkerAgent\> | 可选 | 预览功能 | 可调用的其他 Agent |
| `user_overrides` | Array\<UserOverride\> | 可选 | — | 允许用户在 UI 开关的能力 |

### capabilities 可选值（全部）

| name 值 | 说明 | 关键子字段 |
|---|---|---|
| `WebSearch` | 搜索公开网页 | `sites`（可选，最多 4 个；每个 URL 最多两段路径，无查询参数） |
| `OneDriveAndSharePoint` | 搜索 OneDrive/SharePoint | `items_by_sharepoint_ids`、`items_by_url`（两者均省略则搜索全组织） |
| `GraphConnectors` | Copilot 连接器 | `connections`（省略则所有连接器可用） |
| `GraphicArt` | 图像生成（DALL-E） | 无子字段 |
| `CodeInterpreter` | Python 代码执行 | 无子字段 |
| `Dataverse` | Dynamics 365 Dataverse | `knowledge_sources`（含 `host_name`、`skill`、`tables`） |
| `TeamsMessages` | Teams 频道/群聊/会议聊天 | `urls`（可选，最多 5 个） |
| `Email` | 邮件搜索 | `shared_mailbox`、`group_mailboxes`（最多 25 个）、`folders` |
| `People` | 员工信息 | `include_related_content`（Boolean，是否包含共同文档/邮件） |
| `ScenarioModels` | 特定任务模型 | `models`（含 `id`） |
| `Meetings` | 会议信息 | `items_by_id`（最多 5 个，含 `id` 和 `is_series`） |
| `EmbeddedKnowledge` | 本地文件知识（**尚未上线**） | `files`（最多 10 个，≤1MB，支持 .doc/.docx/.ppt/.pptx/.xls/.xlsx/.txt/.pdf） |

**重要约束**：非 WebSearch 的 capabilities 要求租户开启按量计费或用户持有 M365 Copilot 许可证。

### actions 字段

```json
{
  "actions": [
    {
      "id": "socialhubPlugin",      // 必填，唯一标识符（可用 GUID）
      "file": "plugin.json"          // 必填，指向 plugin manifest 文件的相对路径
    }
  ]
}
```

约束：数组 1-10 个元素。当 actions ≤ 5 个时，所有 plugin 总是注入 prompt；超过 5 个时 Copilot 做语义匹配。

### conversation_starters 字段

```json
{
  "conversation_starters": [
    {
      "title": "客户风险概览",              // 可选，可本地化
      "text": "最近30天有哪些大客户存在流失风险？"  // 必填，可本地化
    }
  ]
}
```

约束：最多 6 个。

### instructions 最佳实践

- **上限 8000 字符**（含 prompt），内容要精炼
- 避免模糊动词（verify/handle/process），改用精确可观测的动作描述
- 禁止步骤重排或 AI 自行"优化"，要显式指令
- 如需禁止 AI 使用模型自身知识：`"behavior_overrides": { "special_instructions": { "discourage_model_knowledge": true } }`
- 禁用建议功能：`"behavior_overrides": { "suggestions": { "disabled": true } }`

### 完整示例

```json
{
  "$schema": "https://developer.microsoft.com/json-schemas/copilot/declarative-agent/v1.6/schema.json",
  "version": "v1.6",
  "name": "SocialHub 客户智能助手",
  "description": "查询客户留存、RFM 分层、订单趋势和营销活动分析数据",
  "instructions": "你是 SocialHub 客户智能分析专家。使用提供的工具查询客户分析数据并给出洞察。调用工具前必须确认 tenant_id 上下文。仅返回工具返回的数据，不要凭空编造数据。",
  "conversation_starters": [
    { "title": "客户概览", "text": "过去30天的客户整体情况如何？" },
    { "title": "流失风险", "text": "哪些客户有流失风险？" },
    { "title": "RFM 分层", "text": "帮我分析高价值客户分布" }
  ],
  "actions": [
    { "id": "socialhubPlugin", "file": "plugin.json" }
  ],
  "capabilities": [
    { "name": "WebSearch" }
  ]
}
```

---

## plugin.json v2.4 RemoteMCPServer 配置

**JSON Schema URL**：`https://aka.ms/json-schemas/copilot/plugin/v2.4/schema.json`

### 根对象字段

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `schema_version` | String | **必填** | 固定值 `"v2.4"` | Schema 版本 |
| `name_for_human` | String | **必填** | ≥1 非空白；超过 20 字符可能被截断 | 面向用户的插件名 |
| `namespace` | String | **必填** | 匹配 `^[A-Za-z0-9]+` | 防止函数名冲突的命名空间 |
| `description_for_human` | String | **必填** | 超过 100 字符可能被截断 | 面向用户的描述 |
| `description_for_model` | String | 可选 | 超过 2048 字符可能被截断 | 面向模型的描述（何时调用此插件） |
| `logo_url` | String | 可选 | 可相对路径 | 插件 logo |
| `contact_email` | String | 可选 | — | 联系邮箱 |
| `legal_info_url` | String | 可选 | — | 服务条款 URL |
| `privacy_policy_url` | String | 可选 | — | 隐私政策 URL |
| `functions` | Array\<Function\> | 可选 | 函数名在数组内必须唯一 | 函数列表（MCP 场景下可省略，工具由 runtime 提供） |
| `runtimes` | Array\<Runtime\> | 可选 | — | 运行时配置 |
| `capabilities` | PluginCapabilities | 可选 | — | 插件级能力（含 conversation_starters） |

### Runtime 对象（RemoteMCPServer 类型）

```json
{
  "runtimes": [
    {
      "type": "RemoteMCPServer",        // 必填，固定值
      "auth": {                          // 必填
        "type": "OAuthPluginVault",      // 或 "None"；MCP 不支持 ApiKeyPluginVault
        "reference_id": "oauth-reg-id"  // OAuthPluginVault 时必填
      },
      "run_for_functions": ["tool1", "tool2"],  // 可选，通配符支持
      "spec": {
        "url": "https://mcp.socialhub.ai/mcp",  // 必填，绝对 URL，必须 HTTPS
        "mcp_tool_description": {
          "file": "mcp-tools.json"       // 引用外部文件（与 tools 二选一）
          // 或者:
          // "tools": [ ... ]            // 内联工具定义（与 file 二选一）
        }
      }
    }
  ]
}
```

### Runtime authentication object

| type 值 | 适用场景 | reference_id |
|---|---|---|
| `None` | 无鉴权（开发/公开服务） | 不需要 |
| `OAuthPluginVault` | OAuth 2.0 授权码流程 / Entra ID SSO | Teams 开发者门户注册后获得的 ID |
| `ApiKeyPluginVault` | API Key 鉴权 | **仅 API Plugin（OpenApi runtime）支持；MCP Plugin 不支持** |

**关键限制**：`MCP plugins don't support API key authentication.`（官方原文）

OAuth 注册地址：`https://dev.teams.microsoft.com/tools` → Tools → OAuth client registration

OAuth callback URL（必须配置）：`https://teams.microsoft.com/api/platform/v1.0/oAuthRedirect`

Entra ID SSO callback URL：`https://teams.microsoft.com/api/platform/v1.0/oAuthConsentRedirect`

---

## mcp_tool_description JSON 格式

### 外部文件引用方式（推荐，对应 mcp-tools.json）

plugin.json 中引用：
```json
"mcp_tool_description": {
  "file": "mcp-tools.json"
}
```

mcp-tools.json 内容格式（与 MCP `tools/list` 方法返回格式完全一致）：
```json
{
  "tools": [
    {
      "name": "get_customer_overview",
      "description": "获取指定时间段内的客户整体分析概览，包括活跃客户数、新增客户数、流失客户数和收入指标",
      "inputSchema": {
        "type": "object",
        "properties": {
          "tenant_id": {
            "type": "string",
            "description": "租户标识符，用于数据隔离"
          },
          "start_date": {
            "type": "string",
            "description": "查询开始日期，格式 YYYY-MM-DD"
          },
          "end_date": {
            "type": "string",
            "description": "查询结束日期，格式 YYYY-MM-DD"
          }
        },
        "required": ["tenant_id"]
      }
    },
    {
      "name": "get_rfm_analysis",
      "description": "执行 RFM（最近购买、购买频次、消费金额）客户价值分层分析",
      "inputSchema": {
        "type": "object",
        "properties": {
          "tenant_id": {
            "type": "string",
            "description": "租户标识符"
          },
          "segment": {
            "type": "string",
            "description": "客户分层筛选：champions/loyal/at_risk/lost 等",
            "enum": ["champions", "loyal_customers", "potential_loyalist", "at_risk", "cant_loose", "lost"]
          }
        },
        "required": ["tenant_id"]
      }
    }
  ]
}
```

### 内联方式（工具少时可用）

直接在 plugin.json 的 `spec.mcp_tool_description.tools` 中内联：
```json
"mcp_tool_description": {
  "tools": [
    {
      "name": "tool_name",
      "description": "工具描述（建议 50-200 字，清晰说明功能和适用场景）",
      "inputSchema": {
        "type": "object",
        "properties": {
          "param": { "type": "string", "description": "参数说明" }
        },
        "required": ["param"]
      }
    }
  ]
}
```

### inputSchema 字段规范

| 字段 | 要求 |
|---|---|
| `type` | 顶层必须是 `"object"` |
| `properties` | 参数映射，每个参数有 `type`、`description`（可选 `enum`、`default`） |
| `required` | 必填参数名数组 |
| 参数 type 可选值 | `string`、`number`、`integer`、`boolean`、`array` |
| 嵌套对象 | **预览阶段有验证 bug**：properties 中的嵌套对象可能导致 `teamsApp/validateAppPackage` 失败，建议避免 |
| `minimum`/`maximum`/`default` | **预览阶段有验证 bug**：这些字段会导致 validateAppPackage 失败，建议暂时移除 |

---

## Teams App Manifest（copilotAgents 字段）

### 完整 manifest.json 结构

```json
{
  "$schema": "https://developer.microsoft.com/en-us/json-schemas/teams/v1.18/MicrosoftTeams.schema.json",
  "manifestVersion": "1.18",
  "version": "1.0.0",
  "id": "00000000-0000-0000-0000-000000000000",
  "developer": {
    "name": "SocialHub",
    "websiteUrl": "https://socialhub.ai",
    "privacyUrl": "https://socialhub.ai/privacy",
    "termsOfUseUrl": "https://socialhub.ai/terms"
  },
  "icons": {
    "color": "color.png",
    "outline": "outline.png"
  },
  "name": {
    "short": "SocialHub 客户助手",
    "full": "SocialHub 客户智能分析助手"
  },
  "description": {
    "short": "用自然语言查询客户分析数据",
    "full": "SocialHub 客户智能助手，支持客户留存、RFM分层、订单趋势等分析，直接在 M365 Copilot Chat 中使用。"
  },
  "accentColor": "#3690E9",
  "copilotAgents": {
    "declarativeAgents": [
      {
        "id": "socialhubAgent",
        "file": "declarativeAgent.json"
      }
    ]
  }
}
```

### 关键字段说明

| 字段 | 约束 | 说明 |
|---|---|---|
| `manifestVersion` | 推荐 `"1.18"` 或更高 | Teams App Manifest schema 版本 |
| `id` | GUID 格式 | 全局唯一 App ID，可在 apps.dev.microsoft.com 生成 |
| `copilotAgents.declarativeAgents` | **当前只支持一个 declarative agent** | 声明式 Agent 引用数组 |
| `declarativeAgents[].id` | 字符串，自定义唯一标识 | Agent ID |
| `declarativeAgents[].file` | 相对路径 | 指向 declarativeAgent.json |
| `icons.color` | **192×192 px**，PNG | 颜色图标（在 M365 Copilot UI 展示） |
| `icons.outline` | **32×32 px**，PNG，白色透明底 | 轮廓图标（目前 Copilot 未使用，但通过验证必须有） |

### copilotAgents 注意事项

- `copilotExtensions` 是旧字段名（devPreview），已重命名为 `copilotAgents`
- 每个 app manifest 目前只支持一个 declarative agent
- 如需多语言支持，需在 manifest 中添加 `defaultLanguageTag` 字段

---

## 实际限制（工具数量、Token、HTTPS 要求）

### 工具与插件数量限制

| 限制项 | 数值 | 说明 |
|---|---|---|
| actions 数组上限 | **10 个** | 一个 declarative agent 最多 10 个 action（plugin） |
| ≤5 个 plugin 时 | 全部注入 prompt | 所有 plugin 总是可用 |
| >5 个 plugin 时 | 语义匹配 | Copilot 自动决定调用哪个 plugin |
| 每个 plugin 工具数 | 无硬性上限 | 但超过 **10 个工具**时响应质量可能下降（token 窗口限制） |
| 工具名称格式 | `^[A-Za-z0-9_]+$` | 函数名只能包含字母数字和下划线 |

### Token 和字符限制

| 限制项 | 数值 |
|---|---|
| `instructions` | ≤8000 字符 |
| `name` | ≤100 字符 |
| `description` | ≤1000 字符 |
| `name_for_human` | 超过 20 字符可能被截断 |
| `description_for_human` | 超过 100 字符可能被截断 |
| `description_for_model` | 超过 2048 字符可能被截断 |
| 工具 description | 无明确上限，建议 50-200 字 |
| 所有字符串默认上限 | 4000 字符（除非另有规定） |

### HTTPS 和 URL 要求

- RemoteMCPServer 的 `spec.url` 必须是**有效的绝对 URL**（文档原文 "MUST be a valid absolute URL"）
- 必须 HTTPS（公网部署场景）
- URL 不需要特定路径格式，但 MCP server 需要支持 HTTP Streamable Transport（SSE 已于 2025 年 8 月后被 Copilot Studio 弃用，M365 Copilot 使用 HTTP Streamable）
- WebSearch capability 中的 site URL 最多两段路径，不允许查询参数

### 认证限制（关键）

- **MCP plugins 不支持 API Key 认证**（`ApiKeyPluginVault` 仅限 OpenApi runtime）
- MCP plugins 仅支持：OAuth 2.0 授权码流程 或 无认证（`None`）
- OAuth 2.0 只支持授权码流（不支持 307 重定向的 token endpoint）
- 不支持 Client Credentials flow（无用户上下文的机器间认证）

### 预览阶段已知 Bug（截至 2026-03）

- `teamsApp/validateAppPackage` 验证可能对以下情况失败：
  - inputSchema 中 properties 包含嵌套对象
  - properties 中有 `minimum`、`maximum` 或 `default` 字段
  - 解决方案：暂时移除这些字段再重试 provision

### 许可证要求

- 开发者：需要 Microsoft 365 Copilot 许可证 + Custom App Upload 权限
- 最终用户：需要 Microsoft 365 Copilot 许可证

---

## 打包和部署流程

### ZIP 包文件结构

```
socialhub-copilot-agent.zip
├── manifest.json           # Teams App Manifest（必须）
├── color.png               # 192×192 颜色图标（必须）
├── outline.png             # 32×32 轮廓图标（必须）
├── declarativeAgent.json   # 声明式 Agent 配置
├── plugin.json             # MCP Plugin Manifest（v2.4）
└── mcp-tools.json          # MCP 工具描述（若 plugin.json 引用 file）
```

所有文件必须在 zip 根目录（不能有子目录层级），路径引用均为相对路径。

### 方式一：Teams 客户端侧载（开发/测试）

1. 在 Teams 客户端左下角选择 **Apps**
2. 选择 **Manage your apps** → **Upload an app**
3. 选择 **Upload a customized app**
4. 选择打包好的 `.zip` 文件
5. 前往 `https://m365.cloud.microsoft/chat` 验证 Agent

前提条件：
- 租户管理员已开启 **Custom App Upload**
- 账户已有 **Copilot Access Enabled**

### 方式二：Teams Admin Center 组织部署（生产）

1. 打开 Microsoft 365 Admin Center: `https://admin.microsoft.com`
2. 导航到 **Copilot Control System**（或 Teams Admin → Manage apps）
3. 选择 **Upload** → 上传 `.zip` 文件
4. 在 **Integrated Apps** 中配置部署策略（特定用户/组/全部）
5. 用户无需手动安装，Agent 自动出现在 M365 Copilot 的 Agents 侧边栏

### 方式三：Microsoft 365 Agents Toolkit（推荐开发工作流）

1. VS Code 安装 Microsoft 365 Agents Toolkit v6.3+
2. 创建项目：**Create a New Agent/App** → **Declarative Agent** → **Add an Action** → **Start with an MCP Server**
3. 输入 MCP server URL，Toolkit 自动获取工具列表并生成 plugin.json 和 mcp-tools.json
4. 选择认证类型（OAuth / None）
5. **Lifecycle → Provision** 触发注册和上传
6. 测试：访问 `https://m365.cloud.microsoft/chat`

### OAuth 注册流程（若使用 OAuth 认证）

1. 在 OAuth 提供商注册应用，获取 client_id 和 client_secret
2. 回调 URL 必须包含：`https://teams.microsoft.com/api/platform/v1.0/oAuthRedirect`
3. 打开 Teams Developer Portal: `https://dev.teams.microsoft.com/tools`
4. 选择 **Tools** → **OAuth client registration** → **Register client**
5. 填写：Registration name、Base URL（MCP server 域名）、Client ID/Secret、Auth/Token/Refresh endpoints、Scope
6. 保存后获得 **OAuth client registration ID**
7. 在 plugin.json 的 `auth.reference_id` 中填入该 ID

---

## 关键发现和对本项目的启示

### 1. API Key 认证是硬性障碍

**发现**：`MCP plugins don't support API key authentication`（官方文档明确声明）。

当前项目计划使用 `ApiKeyPluginVault`（在 `00-goal.md` 中假设"API Key 认证对企业场景已足够"）**已被官方文档推翻**。

**影响**：
- 若 MCP Server 需要认证，**必须实现 OAuth 2.0 授权码流程**
- 替代方案 A：在 MCP Server 前加 Entra ID 保护（作为 API 资源），使用 Microsoft Entra ID SSO（用户用公司账号登录）
- 替代方案 B：暂时使用 `"auth": { "type": "None" }` + 网络层隔离（仅白名单 IP/域名访问），适合内部部署测试
- 替代方案 C：OAuth 授权码流程，用户首次使用时手动授权（每个 M365 用户各自授权一次）

SocialHub 的 tenant_id 隔离机制需重新设计：API Key → tenantId 的绑定方式在 MCP plugin 场景下不可用，需改为 OAuth token → Entra ID 用户/组 → tenantId 的映射。

### 2. 工具数量需要裁剪

**发现**：每个 plugin 超过 10 个工具时响应质量下降；declarative agent 超过 5 个 plugin 时触发语义匹配而非全注入。

**影响**：当前 MCP Server 有 36+ 工具，全部放入单个 plugin 会导致 token 窗口溢出。

**建议**：
- 将 36+ 工具按业务域拆分为多个 plugin（每个 ≤10 工具），但注意 declarative agent 最多引用 10 个 actions
- 或保留单一 plugin，筛选最核心的 10 个工具（overview、customers、retention、rfm、ltv、orders、anomaly、campaigns、products、stores）
- tools 描述要精炼，直接影响 Copilot 能否正确路由到正确工具

### 3. HTTP Transport 必须是 Streamable HTTP（非 SSE）

**发现**：SSE transport 已于 2025 年 8 月后被 Copilot Studio 弃用，M365 Copilot 要求 HTTP Streamable Transport。

**影响**：当前 MCP Server 只有 stdio 实现。需要实现 HTTP Streamable Transport（MCP Python SDK 1.1+ 已支持，入口为 `streamable_http` server）。

### 4. 打包比预期简单，部署有权限门槛

**发现**：ZIP 包结构简单（4-6个文件），无需编译，直接打包 JSON 文件和图标。

**主要门槛**：
- 需要 M365 Copilot 许可证（开发者和用户均需要）
- 需要租户管理员开启 Custom App Upload 权限
- 生产部署需通过 Teams Admin Center（不需要发布到 AppSource）

### 5. 工具描述质量直接影响调用准确性

**发现**：M365 Copilot 基于 `description` 字段做语义匹配来决定调用哪个工具。

**建议**：
- tool description 要明确说明工具的业务场景（"当用户询问...时使用此工具"）
- inputSchema 中每个参数的 `description` 必须清晰（Copilot 据此生成参数值）
- `description_for_model` 是 plugin 整体的调用时机说明，要精准

### 6. 文件引用方式更利于维护

**发现**：`mcp_tool_description` 支持 `file` 引用外部 JSON 文件，避免 plugin.json 过于臃肿。

**建议**：
- 工具多（>5 个）时使用 `"file": "mcp-tools.json"` 分离工具定义
- mcp-tools.json 格式与 MCP `tools/list` 响应格式完全一致，便于自动生成

### 7. 本项目推荐的最终文件结构

```
build/m365-agent/
├── manifest.json           # Teams App Manifest v1.18
├── declarativeAgent.json   # Declarative Agent v1.6
├── plugin.json             # API Plugin Manifest v2.4（RemoteMCPServer）
├── mcp-tools.json          # MCP 工具描述（≤10 个精选工具）
├── color.png               # 192×192
└── outline.png             # 32×32
```

### 8. 认证方案推荐决策树

```
是否要求每个企业客户数据隔离？
├── 是 → 使用 Entra ID SSO（OAuthPluginVault + Entra ID 应用注册）
│         用户登录的 Entra 用户/租户信息 → MCP Server 侧解析 tenant_id
└── 否（内部单租户演示）→ auth: None + 网络层限制访问来源
```

---

## 参考来源

- [Declarative agent schema 1.6](https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/declarative-agent-manifest-1.6)
- [Plugin manifest schema 2.4](https://learn.microsoft.com/en-us/microsoft-365-copilot/extensibility/plugin-manifest-2.4)
- [Build plugins from an MCP server](https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/build-mcp-plugins)
- [Configure Authentication for plugins](https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/api-plugin-authentication)
- [Microsoft 365 App Model for Agents](https://learn.microsoft.com/en-us/microsoft-365-copilot/extensibility/agents-are-apps)
- [Write effective instructions](https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/declarative-agent-instructions)
- [Build declarative agents with MCP - M365 Dev Blog](https://devblogs.microsoft.com/microsoft365dev/build-declarative-agents-for-microsoft-365-copilot-with-mcp/)
- [Lab E8 - Connect Declarative agent to MCP Server](https://microsoft.github.io/copilot-camp/pages/extend-m365-copilot/08-mcp-server/)
- [Lab E10 - OAuth-Protected MCP Server](https://microsoft.github.io/copilot-camp/pages/extend-m365-copilot/10-mcp-auth/)
