# SocialHub 成为 M365 Copilot Declarative Agent

## 目标

将 SocialHub 的客户分析能力打包为 Microsoft 365 Copilot 的声明式 Agent（Declarative Agent），让企业用户在 M365 Copilot Chat 界面直接用自然语言查询客户数据——无需打开 CLI 或 BI 系统，直接从 M365 的日常工作界面获得客户智能。

**核心交付物**：一个可部署到 M365 Copilot 的 Teams 应用包（.zip），包含声明式 Agent 配置和 MCP Plugin，连接到 SocialHub 的远程 HTTPS MCP Server。

## 客户/利益相关方

| 角色 | 诉求 |
|---|---|
| **企业运营/增长团队** | 在 M365 Copilot 日常工作流中直接问"最近30天大客户流失风险"，不用切换系统 |
| **管理层** | 在 Teams/M365 界面快速获取业务数据摘要，每日 stand-up 前用 Copilot 拉数字 |
| **SocialHub 产品/BD** | 进入 M365 生态，降低企业客户的接入门槛，提升平台粘性 |
| **IT/系统集成商** | 标准化 Teams App 部署流程，通过 Teams Admin Center 统一推送给员工 |

## 项目上下文

### 已有能力（可复用）

- **MCP Server**（`mcp_server/server.py`）：27+ 分析工具已实现，含完整 Tool Schema、15 分钟 TTL 缓存、并发去重。工具覆盖：overview、customers、orders、retention、rfm、ltv、campaigns、anomaly、products、stores、points、coupons、loyalty、repurchase 等
- **上游 MCP 连接**（`cli/api/mcp_client.py`）：已有 SSE+POST 通信与 tenant_id 隔离
- **Remote Service 迁移设计**（`design/remote-mcp-service-migration.md`）：已有将 MCP Server 暴露为远程服务的完整架构设计方案

### 关键技术缺口

- **当前 MCP Server 仅支持 stdio**：`mcp_server/__main__.py` 只启动了 `stdio_server`，无 HTTP/SSE transport 实现（文档注释中提到 `--transport sse --port 8090` 但未实现）
- **M365 Copilot 只支持 Remote MCP**：`RemoteMCPServer` runtime 要求 HTTPS URL，stdio 不可用
- **无 API Key 认证层**：当前 MCP Server 无认证机制，暴露公网前必须加 Auth
- **无 Teams App 包**：需新建 `build/m365-agent/` 目录和相关配置文件

### 技术栈

- CLI/MCP：Python 3.10+ / mcp 1.0 SDK / anyio
- 当前传输：stdio（需扩展为 HTTP Streamable）
- 配置：Pydantic v2，环境变量覆盖
- 部署目标：Render（已有 Skills Store 后端部署经验）

### 相关硬约束（来自 CLAUDE.md）

- MCP 工具处理器必须返回 `list[TextContent]`
- 多租户隔离通过 `tenant_id` 实现
- 不允许跨租户查询

## 交付物

- [ ] `mcp_server/` 新增 HTTP Streamable Transport 支持（`--transport http --port 8090`）
- [ ] HTTP MCP Server 的 API Key 认证中间件
- [ ] `build/m365-agent/manifest.json` — Teams App Manifest
- [ ] `build/m365-agent/declarativeAgent.json` — 声明式 Agent 配置
- [ ] `build/m365-agent/plugin.json` — MCP Plugin（RemoteMCPServer runtime）
- [ ] `build/m365-agent/mcp-tools.json` — MCP 工具描述（供 M365 Copilot 解析）
- [ ] Render 部署配置（`render.yaml` 或 Dockerfile）
- [ ] 部署和注册文档（API Key 注册、Teams Admin 上传步骤）

## 调研方向

Phase 2 将并行调研以下 6 个方向：

1. **项目现状**（代码级）：HTTP Streamable MCP transport 实现现状、缺口、改造方案
2. **MCP HTTP Transport 规范**：MCP 协议的 HTTP Streamable Transport 技术细节和 Python SDK 实现
3. **M365 Declarative Agent + Plugin 规范**：manifest v1.6、plugin v2.4、RemoteMCPServer 配置约束
4. **M365 Plugin 认证方案**：ApiKeyPluginVault 注册流程、OAuthPluginVault 对比、企业部署实践
5. **远程 MCP Server 部署实践**：Render/Railway 部署 Python MCP HTTP Server 的最佳实践、CORS、健康检查
6. **竞品/参考实现**：已有第三方 MCP Server 集成 M365 Copilot 的案例（GitHub MCP Server 等）

## 假设

- [假设: MCP Python SDK 1.0+ 已支持 HTTP Streamable Transport] — 需调研确认，若不支持则需手写 FastAPI 适配层
- [假设: 部署到 Render 的 HTTPS 端点即可满足 M365 Copilot 的 RemoteMCPServer URL 要求]
- [假设: API Key 认证（ApiKeyPluginVault）对企业场景已足够，不需要 OAuth SSO]
- [假设: tenant_id 通过 API Key 绑定，每个企业客户一个独立 API Key]
