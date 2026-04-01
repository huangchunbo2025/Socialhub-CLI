# BigQuery 凭据管理门户设计文档

**日期：** 2026-03-31
**状态：** 已批准，待实现

---

## 背景

在 MCP Server 中新增 BigQuery 凭据管理功能，支持客户通过 Web 界面上传、查看和删除 Emarsys Open Data（BigQuery）Service Account 凭据，系统自动校验凭据可用性。

---

## 系统架构

```
浏览器
  └── GET /ui   → 客户门户（Token 登录 + BigQuery 凭据管理）

API（Customer Token 鉴权，复用 APIKeyMiddleware）
  ├── POST   /credentials/bigquery  → 上传凭据 + 校验
  ├── GET    /credentials/bigquery  → 获取凭据状态
  └── DELETE /credentials/bigquery  → 删除凭据

PostgreSQL
  └── tenant_bigquery_credentials

Token 管理（本期）
  └── 写死在 MCP_API_KEYS 环境变量（如 xx:democn）
```

---

## 认证方案

- 复用现有 `APIKeyMiddleware`（`MCP_API_KEYS` env var）
- Token 写死，如 `MCP_API_KEYS=xx:democn`
- 所有 `/credentials/*` 接口需要 `Authorization: Bearer <token>`
- `tenant_id` 由中间件注入，接口无需传

---

## 数据库设计

### tenant_bigquery_credentials 表

```sql
CREATE TABLE tenant_bigquery_credentials (
    id                   SERIAL PRIMARY KEY,
    tenant_id            VARCHAR(255) NOT NULL UNIQUE,
    customer_id          VARCHAR(255) NOT NULL,      -- Emarsys Customer ID（表名后缀）
    gcp_project_id       VARCHAR(255) NOT NULL,      -- SAP 托管的 GCP 项目 ID
    dataset_id           VARCHAR(255) NOT NULL,      -- BigQuery 数据集（通常 emarsys_{customer_id}）
    service_account_json TEXT         NOT NULL,      -- Fernet 加密存储
    tables_found         TEXT,                       -- 校验时发现的表列表（JSON 数组字符串）
    validated_at         TIMESTAMP,                  -- 最后一次校验通过时间
    created_at           TIMESTAMP DEFAULT NOW(),
    updated_at           TIMESTAMP DEFAULT NOW()
);
```

---

## API 接口详情

### POST /credentials/bigquery — 上传凭据

需要 Customer Token。

**Request Body：**
```json
{
  "customer_id": "12345",
  "gcp_project_id": "sap-emarsys-project",
  "dataset_id": "emarsys_12345",
  "service_account_json": {
    "type": "service_account",
    "project_id": "...",
    "private_key": "...",
    "client_email": "...",
    ...
  }
}
```

**校验步骤：**
1. 解析 `service_account_json`（格式校验）
2. 初始化 Google BigQuery 客户端（使用 `gcp_project_id`）
3. 调用 `list_tables(dataset_id)` 获取表列表
4. 检查是否存在 `email_sends_{customer_id}`（核心表）
5. 校验通过 → Fernet 加密 SA JSON → 写入数据库

**Response 200：**
```json
{
  "status": "ok",
  "tenant_id": "democn",
  "customer_id": "12345",
  "tables_found": ["email_sends_12345", "email_opens_12345", "email_clicks_12345"],
  "validated_at": "2026-03-31T10:00:00Z"
}
```

**Response 422（校验失败）：**
```json
{
  "status": "error",
  "message": "BigQuery 校验失败：数据集 emarsys_12345 中未找到 email_sends_12345 表，请检查 Customer ID 和权限"
}
```

**Response 422（格式错误）：**
```json
{
  "status": "error",
  "message": "service_account_json 格式无效：缺少 private_key 字段"
}
```

---

### GET /credentials/bigquery — 获取凭据状态

需要 Customer Token。**不返回** SA JSON 原文。

**Response 200（已配置）：**
```json
{
  "status": "ok",
  "configured": true,
  "customer_id": "12345",
  "gcp_project_id": "sap-emarsys-project",
  "dataset_id": "emarsys_12345",
  "tables_found": ["email_sends_12345", "email_opens_12345"],
  "validated_at": "2026-03-31T10:00:00Z",
  "created_at": "2026-03-31T09:00:00Z"
}
```

**Response 200（未配置）：**
```json
{
  "status": "ok",
  "configured": false
}
```

---

### DELETE /credentials/bigquery — 删除凭据

需要 Customer Token。

**Response 200：**
```json
{ "status": "ok" }
```

**Response 404：**
```json
{ "status": "error", "message": "凭据不存在" }
```

---

## 前端页面（`/ui`）

单页 HTML + 原生 JS，两个状态：

### 未登录状态
- Token 输入框 + 登录按钮
- 登录成功后 Token 存入 `localStorage`，刷新免登录

### 已登录状态
- 顶部显示租户 ID + 退出登录按钮
- **凭据状态卡片**
  - 未配置：显示上传表单
  - 已配置：显示 Customer ID / GCP Project / Dataset / 已发现表列表 / 最后校验时间
- **上传表单**（未配置时显示）
  - 拖拽或点击上传 SA JSON 文件
  - 输入 Emarsys Customer ID
  - 输入 GCP Project ID
  - 输入 Dataset ID
  - 提交按钮（提交时显示校验进度）
  - 校验结果：成功（绿色 + 表列表）/ 失败（红色 + 错误原因）
- **删除按钮**（已配置时显示，需二次确认）

---

## 新增文件结构

```
mcp_server/
├── http_app.py              ← 注册 /credentials/bigquery 路由 + /ui 路由
├── db.py                    ← 新建，PostgreSQL 异步连接（SQLAlchemy async）
├── models.py                ← 新建，TenantBigQueryCredential ORM 模型
├── routers/
│   ├── __init__.py
│   └── credentials.py       ← 三个凭据接口
├── services/
│   ├── __init__.py
│   ├── bigquery_validator.py ← list_tables 校验逻辑
│   └── crypto.py            ← Fernet 加解密
└── static/
    └── ui.html              ← 客户门户
```

---

## 新增依赖

```toml
"sqlalchemy[asyncio]>=2.0.0",
"asyncpg>=0.29.0",
"alembic>=1.13.0",
"google-cloud-bigquery>=3.0.0",
```

## 新增环境变量

| 变量 | 说明 |
|------|------|
| `DATABASE_URL` | PostgreSQL 连接串（`postgresql+asyncpg://...`） |
| `CREDENTIAL_ENCRYPT_KEY` | Fernet 加密密钥（`Fernet.generate_key()` 生成，base64） |

---

## HTTP 状态码

| 场景 | 状态码 |
|------|--------|
| Token 无效 | 401 |
| 缺少必填字段 / 格式错误 | 422 |
| BigQuery 校验失败 | 422 |
| 资源不存在 | 404 |
| 服务内部错误 | 500 |

---

## 不在本期范围

- Token 申请 / 审批流程
- 管理员门户
- 邮件通知
- 后台 BigQuery → StarRocks 同步任务
- BigQuery 凭据定期重新校验
