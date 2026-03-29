# 调研汇总

> 汇总日期：2026-03-29
> 覆盖调研：project-status / mcp-http-transport / m365-agent-spec / m365-auth / deployment / reference-implementations

---

## 核心共识

### 1. 技术可行，主要障碍是认证而非工程

六份调研收敛到同一结论：**将 SocialHub MCP Server 暴露为 M365 Copilot Declarative Agent 的技术路径完全可行**。工程量集中在两个方面：
- HTTP Streamable Transport（改动极小，3-4 个文件）
- 认证层设计（这是真正的复杂点）

### 2. API Key 认证存在官方限制，但有可行绕路

官方文档明确："MCP plugins don't support API key authentication"（`ApiKeyPluginVault` 仅限 OpenApi runtime）。

但这个限制有三条绕路：
- **绕路 A**：社区参考实现 `jmservera/declarative-agent-mcp-apikey` 证明通过 ATK（M365 Agents Toolkit）的 `env/.env.development` 注入机制，API Key 事实上可以工作——只是官方不正式支持
- **绕路 B**：MVP 阶段用 `auth: None` + 服务器端网络 IP 白名单（限制只有 M365 Copilot 的 IP 段才能访问），不依赖 M365 的认证基础设施
- **正路 C**：Entra ID SSO（OAuthPluginVault + Azure AD 应用注册），每个企业用户首次使用时一键授权，token 中包含租户信息，MCP Server 从 token 提取 tenant_id

### 3. HTTP Streamable Transport 改动极小

`mcp_server/server.py` 中的 `create_server()` 与传输层完全解耦——**36+ 工具处理器、缓存、并发去重机制零改动**。
只需：
- 新建 `mcp_server/http_app.py`（Starlette ASGI app + CORS + Auth 中间件）
- 新建 `mcp_server/auth.py`（API Key / Bearer token 验证）
- 修改 `mcp_server/__main__.py`（加 `--transport http` 分支，约 30 行）
- 新建 `render.yaml`（Render 部署配置）

### 4. 工具数量必须裁剪

现有 36+ 工具全部放入单一 plugin 会导致 token 窗口问题（超过 10 个时响应质量下降）。需精选核心 8-10 个工具。

### 5. SSE transport 已废弃，只能用 HTTP Streamable

M365 Copilot 在 2025 年 8 月后全面要求 HTTP Streamable Transport。旧的 SSE 方案不可用。

---

## 调研分歧：认证策略选择

这是全部调研中唯一存在分歧的地方。

| 策略 | 官方支持 | 实现复杂度 | 企业多租户支持 | 用户体验 | 适用场景 |
|---|---|---|---|---|---|
| **auth: None** | 是 | 极低 | 需网络层隔离 | 无感 | 内部测试、单租户 PoC |
| **API Key via ATK** | 非官方 | 低 | API Key = tenant 绑定 | 无感（管理员配置一次） | 快速 MVP、多租户 |
| **Entra ID SSO** | 是（官方推荐） | 高 | 原生支持 | 用户首次授权 | 企业生产、AppSource 上架 |

**分歧点**：认证方案 auth.md 认为 API Key 可以通过 ATK 路径实现；m365-agent-spec.md 引用官方文档说不支持。两者都是事实——官方文档的限制是针对 Copilot 运行时自动注入 Key 的路径，ATK 的注入机制是另一条路。

---

## 非显而易见的关键洞察

### 1. tenant_id 隔离设计必须在认证层完成

无论选择哪种认证方式，SocialHub 的核心安全约束（禁止跨租户查询）要求 `tenant_id` 必须从服务器验证的凭证中提取，而非信任客户端传入参数。具体实现：
- API Key → tenant_id 映射在服务器端环境变量或数据库中维护
- OAuth/Entra token → claims 中提取 `tid`（tenant ID）或自定义 claim

全局 `_cache_key()` 必须加入 `tenant_id`，防止不同租户的缓存数据互污。

### 2. Render 冷启动是 M365 Copilot 场景的真实风险

M365 Copilot 发出工具调用请求时，超时通常在 5-30 秒。Render Free Tier 冷启动需要 60 秒。**必须使用 Starter 层（$7/月）**。这个成本约束需要在产品层面确认。

### 3. Stateless HTTP 是 Render 多进程部署的必选项

如果将来 Render 服务需要扩容（多 worker/多实例），有状态 MCP session 会在不同进程间找不到。`stateless_http=True` 是架构前提，也完全符合 M365 Copilot 的无状态调用模式。

### 4. M365 Agents Toolkit 可以自动生成 plugin.json

只要 MCP Server 已部署在 HTTPS URL 上，ATK 可以自动拉取 `tools/list` 生成 `plugin.json` 和 `mcp-tools.json`，省去手写的工作量。**这意味着先部署 HTTP MCP Server，再用 ATK 生成 Agent 配置，是最省力的顺序**。

### 5. 工具描述是质量瓶颈，不是工程问题

M365 Copilot 基于工具 `description` 做语义匹配决定调用哪个工具。SocialHub 的分析工具描述目前已针对 Claude Desktop 优化（现有 server.py 中的 description 字段非常详细），但需要验证这些描述是否对 M365 Copilot 的语义路由同样有效。两个关键词：**触发场景**（"当用户问...时"）+ **返回什么**（"返回...数据"）。中英文双语描述对中文企业用户尤其重要。

---

## 可复用资源

### 项目内可复用

| 资源 | 位置 | 可复用内容 |
|---|---|---|
| 36+ MCP 工具实现 | `mcp_server/server.py` | 零改动，直接复用 |
| 15分钟 TTL 缓存 + 并发去重 | `mcp_server/server.py:61` | HTTP 模式下单进程继续有效 |
| SDK 依赖（mcp 1.26.0）| 已安装 | 已包含 HTTP Streamable Transport |
| 上游 MCP 连接 | `cli/api/mcp_client.py` | HTTP MCP Server 的 upstream 调用不变 |
| remote-mcp migration.md | `design/` | Auth 设计原则（Section 7）和最小路径（Section 15）可参考 |

### 项目外可复用

| 资源 | URL | 用途 |
|---|---|---|
| Copilot Developer Camp Lab E8/E10 | github.com/microsoft/copilot-camp | 端到端参考代码（无认证+OAuth版） |
| jmservera/declarative-agent-mcp-apikey | github.com/jmservera | API Key 认证路径参考 |
| MCP Inspector | npx @modelcontextprotocol/inspector | 在没有 M365 订阅时测试 HTTP MCP Server |
| M365 Agents Toolkit | VS Code 扩展 | 自动从 MCP Server URL 生成 plugin.json |

---

## 推荐分阶段实施路径

### Phase 0 — 先决条件验证（0.5 天）

在写任何代码之前确认：
- [ ] 确认是否有 M365 Copilot 许可证用于测试
- [ ] 确认是否有 Azure AD 租户（Entra ID）用于 OAuth 注册
- [ ] 确认认证策略（`auth: None` MVP / API Key ATK 路径 / OAuth SSO）

### Phase 1 — HTTP MCP Server（1.5-2 天）

```
新建 mcp_server/auth.py       — API Key 中间件 + tenant_id 注入
新建 mcp_server/http_app.py   — Starlette ASGI + /health + CORS
修改 mcp_server/__main__.py   — 增加 --transport http 分支
修改 mcp_server/server.py     — _cache_key 加入 tenant_id（安全必改）
新建 render.yaml              — Render Starter 部署配置
```

部署到 Render，用 MCP Inspector 验证：`npx @modelcontextprotocol/inspector https://socialhub-mcp.onrender.com/mcp`

### Phase 2 — Declarative Agent 包（0.5-1 天）

```
用 M365 Agents Toolkit 拉取工具列表，自动生成 plugin.json + mcp-tools.json
手写 build/m365-agent/declarativeAgent.json（指令 + 启动对话）
手写 build/m365-agent/manifest.json（Teams App 元数据）
准备 color.png (192×192) + outline.png (32×32)
打包 zip，Teams Admin Center 部署验证
```

### Phase 3 — OAuth 认证升级（2-3 天，生产必须）

```
Azure AD 应用注册（配置 redirect URI）
Teams Developer Portal OAuth 注册（获取 reference_id）
MCP Server 端 Entra token 验证 + tenant_id 提取
plugin.json 更新 auth.type 为 OAuthPluginVault
```

---

## 总体工程量估算

| 阶段 | 工作量 | 可演示里程碑 |
|---|---|---|
| Phase 1（HTTP MCP Server） | 1.5-2 天 | MCP Inspector 可调用 36+ 工具 |
| Phase 2（Declarative Agent 包） | 0.5-1 天 | M365 Copilot Chat 可用（无认证或 API Key 模式） |
| Phase 3（OAuth 认证） | 2-3 天 | 企业生产就绪 |
| **合计** | **4-6 天** | — |
