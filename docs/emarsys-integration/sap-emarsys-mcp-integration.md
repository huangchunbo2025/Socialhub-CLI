# SAP Emarsys MCP 集成方案

> **版本**: v2.0
> **更新日期**: 2026-04-02
> **适用对象**: 业务负责人、产品经理、项目管理者

---

## 1. 方案概述

### 1.1 业务目标

本方案实现将 **SAP Emarsys 邮件营销数据** 通过 **MCP (Model Context Protocol)** 协议集成到 **SAP Joule** AI 助手，让企业用户可以通过自然语言对话方式快速获取营销数据分析报告。

**核心价值**:

- **对话即分析**: 用户用自然语言提问（如"上周邮件打开率如何"），系统自动生成分析报告
- **数据安全隔离**: 多租户架构确保各企业数据完全隔离
- **实时数据同步**: BigQuery 营销数据定时同步到内部数据仓库，保障查询性能

### 1.2 业务流程总览

> **架构图**：[emarsys-mcp-overview.drawio](./emarsys-mcp-overview.drawio)
>
> 图示两条核心路径：① Emarsys BigQuery → 数据同步引擎 → StarRocks（数据流入）；② 企业用户 → SAP Joule → MCP Server → StarRocks（数据查询）。

<!-- 图片待插入：emarsys-mcp-overview.drawio 导出图 -->

---

## 2. 用户订阅流程

### 2.1 流程说明

企业用户从注册到使用 MCP 服务的完整流程：

```
登录门户 ──► 配置凭证 ──► 创建API Key ──► 配置BTP Destination ──► 开始使用
```

| 步骤 | 业务动作 | 参与方 | 交付物 |
|------|----------|--------|--------|
| 1 | 访问门户 `/ui`，使用 SocialHub 账号登录 | 企业用户 | JWT Token |
| 2 | 上传 BigQuery Service Account 凭证 | 企业用户 | 凭证验证结果 |
| 3 | 配置 SocialHub 上游 MCP 凭证（app_id/app_secret） | 企业用户 | 凭证保存确认 |
| 4 | 创建 MCP API Key，记录 `sh_` 开头的密钥 | 企业用户 | API Key |
| 5 | 在 SAP BTP Cockpit 创建 Destination，注入 API Key | 平台运营 | BTP Destination |
| 6 | 在 Joule Studio 添加 MCP Server，绑定 Destination | 平台运营 | Joule MCP 配置 |

### 2.2 企业用户前置条件

企业在使用本服务前，需要完成 SAP 侧准备工作：

1. **签署 SAP Emarsys Open Data 服务订单**
2. **获取 Emarsys Customer ID**（用于识别企业身份）
3. **获取 GCP Service Account 凭证**（用于读取 BigQuery 数据）
4. **拥有 SocialHub 账号**（用于门户登录和 MCP 上游调用）

---

## 3. 门户与认证

### 3.1 门户 UI

MCP Server 内置一个轻量级管理门户，无需独立部署：

| 端点 | 说明 |
|------|------|
| `GET /ui` | 租户自助管理页面（凭证管理、API Key 管理） |
| `POST /auth/login` | 门户登录，验证 SocialHub 账号，返回 JWT |
| `GET /health` | 健康检查（无需认证） |

### 3.2 登录流程

```
POST /auth/login
  请求体: { tenantId, account, pwd }
      │
      ▼
调用 SocialHub Auth API 验证账号
  POST {SOCIALHUB_AUTH_URL}/v1/user/auth/token
      │
      ▼
验证通过 → 签发 Portal JWT (X-Portal-Token)
      │
      ▼
前端携带 JWT 访问 /credentials/* 和 /api-keys 端点
```

### 3.3 双认证路径

| 认证路径 | Header | 适用场景 |
|----------|--------|----------|
| **API Key** | `X-API-Key: sh_xxx` 或 `Authorization: Bearer sh_xxx` | SAP Joule / M365 Copilot 工具调用 |
| **Portal JWT** | `X-Portal-Token: <jwt>` | 门户 UI 管理凭证和 API Key |

API Key 认证优先查询数据库（SHA-256 哈希匹配），未找到则 fallback 到环境变量 `MCP_API_KEYS`，全程使用 `hmac.compare_digest` 防时序攻击。

---

## 4. 凭证管理

### 4.1 凭证类型

本平台管理两类凭证，均加密存储于 PostgreSQL：

| 凭证类型 | 端点 | 说明 |
|----------|------|------|
| **SocialHub MCP 凭证** | `/credentials/mcp` | SocialHub auth_url + app_id + app_secret，用于 MCP 工具上游调用 |
| **BigQuery 凭证** | `/credentials/bigquery` | GCP Service Account JSON，用于读取 Emarsys Open Data |

### 4.2 BigQuery 凭证上传流程

```
POST /credentials/bigquery
      │
      ▼
┌─────────────────┐
│ 1. 格式校验     │
│    检查必填字段  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 2. 连接验证     │
│    测试BQ访问   │
│    自动发现数据集 │
│    (emarsys_*)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 3. Fernet加密   │
│    写入 PG 数据库 │
│    tenant 唯一  │
└────────┬────────┘
         │
         ▼
   返回验证结果
   (datasets_found, tables_found)
```

### 4.3 SocialHub MCP 凭证

```
PUT /credentials/mcp
  请求体: { auth_url, app_id, app_secret }
      │
      ▼
app_secret Fernet 加密写入 tenant_socialhub_credentials 表
      │
      ▼
清除旧 token 缓存（token_manager.invalidate_token）
```

查询时（`GET /credentials/mcp`）不返回明文 secret，仅返回 `auth_url`、`app_id` 和配置时间。

### 4.4 安全机制

| 安全措施 | 实现方式 |
|----------|----------|
| 传输加密 | 全程 HTTPS/TLS |
| 存储加密 | Fernet（AES-128-CBC + HMAC-SHA256），密钥由 `CREDENTIAL_ENCRYPT_KEY` 环境变量提供 |
| 密钥管理 | 加密密钥通过环境变量注入，不存入代码或数据库 |
| 租户隔离 | 所有 DB 查询按 `tenant_id` 过滤，禁止跨租户访问 |
| 防时序攻击 | API Key 比对使用 `hmac.compare_digest` |

---

## 5. API Key 管理

### 5.1 设计原则

- **租户级别**：每个 API Key 绑定一个 tenant_id，一个租户可创建多个 Key
- **单次可见**：创建时返回明文 Key（`sh_` + 32位随机十六进制），之后仅存储 SHA-256 哈希
- **软删除**：撤销通过设置 `revoked_at` 时间戳实现，不物理删除
- **前缀显示**：列表接口返回 `key_prefix`（前8位）供识别

### 5.2 API Key 管理接口

所有接口均需 `X-Portal-Token` JWT 认证：

| 方法 | 端点 | 说明 |
|------|------|------|
| `POST` | `/api-keys` | 创建新 Key，请求体 `{name}`，返回一次性明文 Key |
| `GET` | `/api-keys` | 列出当前租户所有有效 Key（不含明文，含前缀） |
| `DELETE` | `/api-keys/{key_id}` | 撤销指定 Key |

### 5.3 API Key 生命周期

```
创建 → 分发到 BTP Destination → 用于 Joule 工具调用
                                      │
                          需要轮换时   │
                                      ▼
                              撤销旧 Key → 创建新 Key → 更新 BTP Destination
```

---

## 6. MCP 服务调用

### 6.1 调用链路（SAP Joule）

```
用户在 Joule 中提问（自然语言）
      │
      ▼
┌─────────────────┐
│ SAP Joule       │
│ 理解用户意图     │
└────────┬────────┘
         │ POST /mcp（HTTP Streamable Transport）
         │ X-API-Key: sh_xxx（BTP Destination URL.headers 注入）
         ▼
┌─────────────────────────────────────────────────┐
│ MCP Server (Render)                             │
│                                                 │
│  APIKeyMiddleware                               │
│  ├─ DB 查询：SHA-256(key) → tenant_id           │
│  └─ Fallback：env MCP_API_KEYS                  │
│                                                 │
│  ContextVar 注入 tenant_id                      │
│                                                 │
│  StreamableHTTPSessionManager (stateless=True)  │
│  └─ call_tool(name, args)                       │
│      └─ 读取 ContextVar 获取 tenant_id           │
│          └─ 查询内部数据仓库                     │
└────────┬────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│ 内部数据仓库     │
│ 存储营销数据     │
└─────────────────┘
```

### 6.2 支持的查询能力

用户可以通过 Joule 对话获取以下营销数据分析：

| 查询类型 | 示例问题 | 输出内容 |
|----------|----------|----------|
| **邮件发送统计** | "昨天发了多少封邮件" | 发送量、发送成功率 |
| **互动率分析** | "上周邮件打开率如何" | 打开率、点击率、趋势 |
| **活动效果** | "春节营销活动转化如何" | 漏斗分析、转化数据 |
| **RFM 分层** | "高价值客户占比多少" | RFM 分层分布、趋势 |
| **联系人分析** | "哪些客户最活跃" | 活跃客户列表、行为统计 |

### 6.3 智能分析特性

- **默认时间范围**: 未指定日期时，默认查询最近 7 天数据
- **智能对比**: 涉及具体数字时，自动提供环比/同比参考
- **多租户隔离**: ContextVar 确保工具执行过程中 tenant_id 全程有效
- **低延迟响应**: 数据已预同步到内部仓库，查询响应快

---

## 7. SAP Joule 集成

### 7.1 集成架构确认

| 确认项 | 结果 |
|--------|------|
| 传输协议 | HTTP Streamable（`StreamableHTTPSessionManager(stateless=True)`）|
| 认证方式 | `X-API-Key` Header（通过 BTP Destination `URL.headers` 静态注入）|
| MCP 端点 | `POST https://socialhub-mcp.onrender.com/mcp` |
| 部署位置 | Render（当前）|

### 7.2 BTP Destination 配置

在 SAP BTP Cockpit → Connectivity → Destinations 创建：

```
Name:           socialhub-mcp
Type:           HTTP
URL:            https://socialhub-mcp.onrender.com   ← 基础 URL，不含 /mcp
Authentication: NoAuthentication
ProxyType:      Internet

Additional Properties:
  sap-joule-studio-mcp-server  =  true
  URL.headers.X-API-Key        =  sh_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

> **注意**：URL 末尾不能含 `/mcp`，Joule Studio 会自动追加 `/mcp` path。

### 7.3 Joule Studio 操作步骤

1. Joule Studio → Agent → **MCP Servers** tab → **Add MCP Server**
2. 选择 Destination `socialhub-mcp`
3. **Path**: `/mcp`（默认值，无需修改）
4. 填写 Name 和 Description
5. 保存 → Joule 自动发起 `POST /mcp` 完成 initialize

---

## 8. 部署架构

### 8.1 部署组件

| 组件 | 部署位置 | 说明 |
|------|----------|------|
| MCP Server | Render（`socialhub-mcp` 服务） | 对外服务接口，提供 `/mcp` + `/ui` + `/credentials/*` + `/api-keys` |
| PostgreSQL | Render（托管数据库） | 单实例，`socialhub_mcp` 库 |
| 数据同步引擎 | 内部数据中心 | 定时任务，BigQuery → 内部数据仓库 |
| 内部数据仓库 | 内部数据中心 | 营销数据存储和查询（DAS / DataNow 库） |

### 8.2 数据库表结构

| 表名 | 说明 |
|------|------|
| `tenant_bigquery_credentials` | BigQuery SA JSON（Fernet 加密），per tenant |
| `tenant_socialhub_credentials` | SocialHub app_id / app_secret（Fernet 加密），per tenant |
| `tenant_api_keys` | API Key（SHA-256 哈希），支持多 Key per tenant |

### 8.3 关键环境变量

| 变量 | 说明 |
|------|------|
| `MCP_API_KEYS` | 静态 API Key 映射（`sh_xxx:tenant_id`，逗号分隔），作为 DB 的 fallback |
| `CREDENTIAL_ENCRYPT_KEY` | Fernet 加密密钥（生成：`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` ）|
| `PORTAL_JWT_SECRET` | Portal JWT 签名密钥 |
| `DATABASE_URL` | PostgreSQL 连接串（asyncpg 驱动） |
| `SOCIALHUB_AUTH_URL` | SocialHub Auth 服务地址，门户登录用 |
| `DAS_TABLES` / `DATANOW_TABLES` | 数据库路由：`tenant_id:db_name` 格式 |

### 8.4 本地/自托管 Docker Compose 部署

```bash
cp .env.docker.example .env.docker  # 填写敏感变量
docker compose up -d
# MCP Server: http://localhost:8091
# Portal UI:  http://localhost:8091/ui
# Health:     http://localhost:8091/health
```

---

## 9. 实施 Checklist

### 9.1 新增租户 Checklist

**企业侧准备：**

- [ ] 签署 SAP Emarsys Open Data Service Order
- [ ] 获取 Emarsys Customer ID
- [ ] 获取 GCP Service Account 凭证文件
- [ ] 准备 SocialHub 账号（tenantId + account + password）

**门户配置（企业用户操作）：**

- [ ] 访问 `https://socialhub-mcp.onrender.com/ui` 登录
- [ ] 上传 BigQuery Service Account 凭证，验证通过
- [ ] 配置 SocialHub MCP 凭证（auth_url + app_id + app_secret）
- [ ] 创建 API Key，保存明文 Key（仅显示一次）

**平台侧配置：**

- [ ] 在 SAP BTP Cockpit 创建 Destination `socialhub-mcp`（配置 `URL.headers.X-API-Key`）
- [ ] 在 Joule Studio 添加 MCP Server，Path 填 `/mcp`
- [ ] 验证 Joule 可正常调用 MCP 工具

**数据同步启动：**

- [ ] 首次全量同步历史数据
- [ ] 配置定时同步任务
- [ ] 验证同步日志正常

### 9.2 日常运维检查项

| 检查项 | 检查方法 | 检查频率 |
|--------|----------|----------|
| MCP Server 健康状态 | `GET /health` | 实时监控（Render 内置）|
| 数据同步任务状态 | 查看同步日志表 | 每日 |
| API Key 有效性 | 门户 UI `/api-keys` 列表 | 按需 |
| BigQuery 凭证有效期 | 检查 Service Account 过期时间 | 每周 |
| 存储空间 | 监控数据仓库磁盘使用率 | 每日 |

---

## 10. 待确认事项

### 10.1 数据字段映射（待确认）

BigQuery 数据表到内部数据仓库的映射关系，需根据实际 Emarsys 数据结构确认：

| 数据视图 | 状态 | 关键字段待确认 |
|----------|------|----------------|
| **email_sends** | 待确认 | 发送时间、活动 ID、联系人 ID、发送状态 |
| **email_opens** | 待确认 | 打开时间、设备类型、邮件客户端 |
| **email_clicks** | 待确认 | 点击时间、点击链接 |
| **email_bounces** | 待确认 | 退回类型（硬退回/软退回）、退回原因 |
| **email_unsubscribes** | 待确认 | 退订时间、退订渠道 |
| **contacts** | 待确认 | 联系人属性、标签、生命周期状态 |

> **下一步行动**：使用测试 Service Account 连接 BigQuery，验证实际 Schema，确认字段映射规则。

### 10.2 高可用与生产部署

| 确认项 | 当前状态 | 说明 |
|--------|----------|------|
| **高可用要求** | 待确认 | 生产环境 SLA 要求、故障转移策略 |
| **SAP Kyma 部署** | 待规划 | 生产环境推荐部署在 SAP Kyma，深度融合 BTP 生态 |
| **数据同步频率** | 待确认 | 实际生产环境所需的同步频率（30min / 60min） |

---

## 11. 附录

### 11.1 相关文档

| 文档 | 说明 |
|------|------|
| [data-integration.md](./data-integration.md) | BigQuery 数据同步详细方案（技术） |
| [app-integration.md](./app-integration.md) | Joule 集成方案（技术） |
| [sap-emarsys-api-overview.md](../emarsys/sap-emarsys-api-overview.md) | Emarsys API 概览 |
| [sap-emarsys-bigquery-guide.md](../emarsys/sap-emarsys-bigquery-guide.md) | BigQuery 操作指南 |

### 11.2 流程图文件

- [mcp-data-sync-flow.drawio](./mcp-data-sync-flow.drawio) — 完整数据同步与认证流程图（SAP BTP 规范）

### 11.3 参考链接

- [SAP Emarsys - Open Data 官方文档](https://help.sap.com/docs/SAP_EMARSYS/f8e2fafeea804018a954a8857d9dfff3/fdf6cde274c110148af791106924f905.html)
- [SAP Emarsys - Open Data Data Views](https://help.sap.com/docs/SAP_EMARSYS/5d44574160f44536b0130abf58cb87cc/fdf6d4bf74c11014ae96c7b0f36a39d7.html)
- [Add MCP Servers to Your Joule Agent](https://help.sap.com/docs/Joule_Studio/45f9d2b8914b4f0ba731570ff9a85313/3d9dfad0bc39468292d508f0808a12fe.html)
