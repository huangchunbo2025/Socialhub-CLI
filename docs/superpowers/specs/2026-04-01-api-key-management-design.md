# API Key 管理 + 统一认证 设计文档

**日期：** 2026-04-01
**状态：** 已批准，实现中
**关联 Plan：** `docs/superpowers/plans/2026-04-01-api-key-management.md`
**前置 Spec：** `2026-03-31-bigquery-credentials-portal-design.md`（认证方案已在本期变更）

---

## 背景与动机

上一期（2026-03-31）实现的 BigQuery 凭证门户，API Key 写死在 `MCP_API_KEYS` 环境变量中，每次新增/吊销 Key 都需要修改 env 并重启服务，无法动态管理。

本期目标：
1. 管理员通过 SocialHub 账号密码登录门户
2. 在门户中动态创建/吊销 API Key（存入 DB）
3. MCP 客户端使用这些 Key 调用服务
4. `MCP_API_KEYS` env var 保留作为 bootstrap 兜底（向后兼容）

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│  管理员（浏览器）                                                  │
│                                                                  │
│  GET /ui → 管理门户（SocialHub 登录 + API Key 管理 + 凭证管理）     │
│                                                                  │
│  认证流程：                                                        │
│  POST /auth/login                                                │
│    body: {tenantId, account, pwd}                                │
│    → 调用 SocialHub Auth API 验证                                  │
│    → 签发 JWT（8小时有效期）                                        │
│    → 前端存入 localStorage                                         │
│                                                                  │
│  门户 API（需 X-Portal-Token: <JWT>）                              │
│  POST   /api-keys          → 创建 API Key                         │
│  GET    /api-keys          → 列出 API Keys                        │
│  DELETE /api-keys/{id}     → 吊销 API Key                         │
│  GET    /credentials/bigquery  → 查看凭证（也接受 JWT）             │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  MCP 客户端（Claude Desktop / M365 Copilot）                      │
│                                                                  │
│  POST /mcp  →  Authorization: Bearer <api_key>                   │
│  POST /credentials/bigquery  →  Authorization: Bearer <api_key>  │
│                                                                  │
│  APIKeyMiddleware 验证：                                          │
│  1. 查 tenant_api_keys 表（SHA-256 哈希匹配）                      │
│  2. 若未找到，fallback 到 MCP_API_KEYS env var（向后兼容）           │
└─────────────────────────────────────────────────────────────────┘

PostgreSQL
  ├── tenant_bigquery_credentials   ← 已有
  └── tenant_api_keys               ← 本期新增
```

---

## 认证方案

### 两类身份 + 两套认证

| 身份 | 认证方式 | Header | 用途 |
|------|---------|--------|------|
| 管理员（人） | SocialHub 账密 → JWT | `X-Portal-Token: <jwt>` | 门户操作（创建/吊销 Key、查看凭证） |
| MCP 客户端（机器） | API Key | `Authorization: Bearer <key>` | 调用 /mcp 工具、上传凭证 |

### JWT 实现

- 算法：HMAC-SHA256（stdlib 实现，无外部依赖）
- 格式：`base64url(header).base64url(payload).base64url(sig)`
- Payload：`{"sub": tenant_id, "exp": unix_ts, "iat": unix_ts}`
- TTL：8 小时
- Secret：`PORTAL_JWT_SECRET` 环境变量（未设置则随机生成，重启失效）

### `/credentials/bigquery` 双认证支持

该接口同时接受两种认证（`resolve_tenant_id()` 函数处理）：
- API Key（MCP 客户端上传凭证用）
- JWT（管理员在门户查看凭证状态用）

---

## 数据库设计

### tenant_api_keys 表（新增）

```sql
CREATE TABLE tenant_api_keys (
    id            SERIAL PRIMARY KEY,
    tenant_id     VARCHAR(255) NOT NULL,
    name          VARCHAR(100) NOT NULL,           -- 备注名，如"Claude Desktop 生产环境"
    key_prefix    VARCHAR(10)  NOT NULL,           -- 原始 key 前8位，用于页面显示
    key_hash      VARCHAR(64)  NOT NULL UNIQUE,    -- SHA-256(raw_key)，用于验证
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_used_at  TIMESTAMP WITH TIME ZONE,        -- 每次认证成功后更新（可选，本期不实现）
    revoked_at    TIMESTAMP WITH TIME ZONE         -- 不为空表示已吊销
);
CREATE INDEX ix_tenant_api_keys_tenant_id ON tenant_api_keys(tenant_id);
```

**API Key 格式：** `sh_` + 32位十六进制随机字符 = 35字符总长（如 `sh_a1b2c3d4e5f6...`）

**安全要求：**
- 原始 key 只在创建响应中返回一次，之后不可查
- 数据库只存 SHA-256 哈希，永远不存原始 key
- 吊销用 `revoked_at` 标记（软删除），不物理删除

### tenant_bigquery_credentials 表变更（上期实现，本期无变更）

已在上期迁移中完成：
- `customer_id` 改为可选（nullable）
- `dataset_id` 改为可选（nullable）
- 新增 `datasets_found` 字段（JSON array）
- 新增 `credential_type` 字段

---

## API 接口详情

### POST /auth/login — 门户登录

无需认证。

**Request Body：**
```json
{
  "tenantId": "democn",
  "account": "admin",
  "pwd": "password"
}
```

**处理流程：**
1. 调用 SocialHub Auth API：`POST {SOCIALHUB_AUTH_URL}/v1/user/auth/token`
2. 验证成功 → 签发 JWT（payload 含 tenant_id）
3. 返回 JWT

**Response 200：**
```json
{
  "token": "eyJ...（JWT）",
  "tenant_id": "democn"
}
```

**Response 401（认证失败）：**
```json
{ "error": "登录失败：invalid credentials" }
```

**Response 503（未配置 SOCIALHUB_AUTH_URL）：**
```json
{ "error": "SOCIALHUB_AUTH_URL 未配置，无法登录" }
```

---

### POST /api-keys — 创建 API Key

需要 `X-Portal-Token: <JWT>`。

**Request Body：**
```json
{ "name": "Claude Desktop 生产环境" }
```

**Response 201：**
```json
{
  "id": 1,
  "name": "Claude Desktop 生产环境",
  "key": "sh_a1b2c3d4e5f6...",
  "key_prefix": "sh_a1b2c3",
  "created_at": "2026-04-01T10:00:00Z"
}
```

> ⚠️ `key` 字段只在此响应中返回一次，之后不可查。

**Response 401：** JWT 无效或过期

---

### GET /api-keys — 列出 API Keys

需要 `X-Portal-Token: <JWT>`。返回当前租户所有未吊销的 Key（不含 hash）。

**Response 200：**
```json
{
  "keys": [
    {
      "id": 1,
      "name": "Claude Desktop 生产环境",
      "key_prefix": "sh_a1b2c3",
      "created_at": "2026-04-01T10:00:00Z",
      "last_used_at": null
    }
  ]
}
```

---

### DELETE /api-keys/{key_id} — 吊销 API Key

需要 `X-Portal-Token: <JWT>`。只能吊销当前租户的 Key。

**Response 200：** `{ "status": "ok" }`
**Response 404：** Key 不存在或不属于当前租户

---

### /credentials/bigquery — 变更说明

接口签名不变（见旧 spec），本期变更：
- 认证方式扩展：除 API Key 外，也接受 `X-Portal-Token: <JWT>`
- 实现：`resolve_tenant_id(request)` 函数统一处理两种认证

---

## 前端门户（`/ui`）

单页 HTML + 原生 JS，无外部依赖。

### 登录页
- 字段：租户 ID（tenantId）+ 账号 + 密码
- 登录成功：JWT 存入 `localStorage('mcp_portal_token')`，自动进入主界面
- 刷新页面：读取 localStorage，有效则免登录

### 主界面（登录后）
- 左侧导航：「🔑 API Key 管理」「🗄️ 凭证管理」
- 左下角：租户名 + 退出登录按钮

### API Key 管理页
- 表格：名称 / Key 前缀 / 创建时间 / 最后使用时间 / 吊销按钮
- 新建按钮 → 弹窗输入名称 → 创建成功后弹窗展示完整 Key（含复制按钮）
- 吊销按钮：二次确认后调 DELETE 接口

### 凭证管理页
- 未配置：空状态 + 新建按钮
- 已配置：显示 GCP Project / 发现的数据集 / 表数量 / 最后校验时间 + 更新/删除按钮
- 新建/更新弹窗：拖拽上传 SA JSON（自动填充 GCP Project ID）+ 可选 Dataset ID

---

## 新增/修改文件

| 动作 | 文件 | 职责 |
|------|------|------|
| 新建 | `mcp_server/services/jwt_service.py` | HMAC-SHA256 JWT 签发/验证 |
| 新建 | `mcp_server/routers/auth_portal.py` | `POST /auth/login` |
| 新建 | `mcp_server/routers/api_keys.py` | API Key CRUD |
| 新建 | `alembic_mcp/versions/xxxx_add_tenant_api_keys.py` | DB migration |
| 修改 | `mcp_server/models.py` | 新增 `TenantApiKey` 模型 |
| 修改 | `mcp_server/db.py` | `init_db()` 注册新模型 |
| 修改 | `mcp_server/auth.py` | DB API Key 查询 + `resolve_tenant_id()` |
| 修改 | `mcp_server/routers/credentials.py` | 改用 `resolve_tenant_id()` |
| 修改 | `mcp_server/http_app.py` | 注册新路由，`/auth/login` 免认证 |
| 修改 | `mcp_server/static/ui.html` | 完全重写（SocialHub 登录 + 双页导航） |
| 修改 | `alembic_mcp/env.py` | 注册新模型供 autogenerate 使用 |

---

## 新增环境变量

| 变量 | 说明 | 必填 |
|------|------|------|
| `SOCIALHUB_AUTH_URL` | SocialHub 认证 API 地址（如 `https://api.socialhub.io`）| 是 |
| `PORTAL_JWT_SECRET` | JWT 签名密钥（未设置则随机，重启失效）| 建议设置 |

---

## 向后兼容说明

- `MCP_API_KEYS` env var **继续有效**：`APIKeyMiddleware` 先查 DB，找不到再查 env var
- 现有 MCP 客户端无需修改，使用原有 key 继续工作
- 新客户端通过门户创建 key 后使用

---

## HTTP 状态码

| 场景 | 状态码 |
|------|--------|
| JWT 无效或过期 | 401 |
| API Key 无效 | 401 |
| 缺少必填字段 | 422 |
| 资源不存在 | 404 |
| SOCIALHUB_AUTH_URL 未配置 | 503 |
| 内部错误 | 500 |

---

## 不在本期范围

- API Key 使用量统计（`last_used_at` 字段已预留，但本期不更新）
- JWT Refresh Token（8小时过期后重新登录）
- 多管理员账号权限隔离
- API Key 权限范围（Scope）控制
- 审计日志
