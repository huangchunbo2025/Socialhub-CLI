# MCP Server HTTP API 集成测试用例

**测试目标**：`http://localhost:8091`（本地 Docker）
**测试文件**：`tests/test_integration_mcp_http.py`
**执行命令**：`conda run -n dev pytest tests/test_integration_mcp_http.py -v`
**最近执行**：2026-04-01 | **结果：32/32 通过 ✅**

---

## 前提条件

| 项目 | 值 |
|------|-----|
| Docker 镜像 | `socialhub-mcp:local` |
| 容器端口 | `8091 → 8090` |
| API Key | `sh_a2d8db3b7011a3e4a4dbf56b49203abf`（租户 `uat`） |
| JWT 签名密钥 | `local-dev-secret-2026`（`.env.local` 中配置） |
| 数据库 | `postgresql://host.docker.internal:5432/socialhub_mcp` |

---

## T1 — 基础设施

| 编号 | 测试名称 | 请求 | 预期结果 | 状态 |
|------|----------|------|----------|------|
| T1-01 | /health 返回 200 | `GET /health` | HTTP 200 | ✅ |
| T1-02 | /health 响应包含 status 字段 | `GET /health` | body 含 `status` | ✅ |

---

## T2 — 认证中间件

| 编号 | 测试名称 | 请求 | 预期结果 | 状态 |
|------|----------|------|----------|------|
| T2-01 | 无 API Key → 401 | `GET /mcp/`（无认证头） | HTTP 401 | ✅ |
| T2-02 | 错误 API Key → 401 | `GET /mcp/` + `Bearer sh_wrong` | HTTP 401 | ✅ |
| T2-03 | 401 响应含 reference_id | `GET /mcp/` + 错误 Key | body 含 `reference_id` | ✅ |
| T2-04 | 有效 API Key 通过认证 | `POST /mcp/` + 有效 Key | 非 401 | ✅ |
| T2-05 | /health 无需认证 | `GET /health`（无认证头） | HTTP 200 | ✅ |
| T2-06 | /ui 无需认证 | `GET /ui`（无认证头） | HTTP 200 | ✅ |
| T2-07 | X-Portal-Token 绕过 API Key 校验 | `GET /api-keys` + JWT 头 | 非 401 | ✅ |

---

## T3 — 门户登录（/auth/login）

| 编号 | 测试名称 | 请求 | 预期结果 | 状态 |
|------|----------|------|----------|------|
| T3-01 | 缺少必填字段 → 422 | `POST /auth/login` `{"tenantId":"x"}` | HTTP 422 | ✅ |
| T3-02 | 空 body → 422 | `POST /auth/login` `{}` | HTTP 422 | ✅ |
| T3-03 | 凭证错误 → 401 或 503 | 完整 body + 错误密码 | HTTP 401/503（非 200） | ✅ |

> **说明**：T3-03 返回 401（UAT 服务可达但凭证无效）或 503（UAT 服务不可达），均属预期。

---

## T4 — API Key 管理（需 JWT 认证）

| 编号 | 测试名称 | 请求 | 预期结果 | 状态 |
|------|----------|------|----------|------|
| T4-01 | 无 JWT 访问 → 401 | `GET /api-keys`（无认证头） | HTTP 401 | ✅ |
| T4-02 | 有效 JWT 列出 Keys | `GET /api-keys` + JWT | HTTP 200，body 含 `keys[]` | ✅ |
| T4-03 | 创建 Key 缺少 name → 422 | `POST /api-keys` `{}` | HTTP 422 | ✅ |
| T4-04 | 成功创建 API Key | `POST /api-keys` `{"name":"test"}` | HTTP 201，body 含 `key`（`sh_` 前缀） | ✅ |
| T4-05 | 新建 Key 出现在列表 | `GET /api-keys` | keys 列表包含刚创建的 id | ✅ |
| T4-06 | 列表包含 key_raw 字段 | `GET /api-keys` | 每条记录含 `key_raw`（`sh_` 前缀） | ✅ |
| T4-07 | 吊销 API Key | `DELETE /api-keys/{id}` | HTTP 200，status=ok | ✅ |
| T4-08 | 已吊销 Key 不再列出 | `GET /api-keys` | 被吊销 id 不在列表 | ✅ |
| T4-09 | 吊销不存在的 Key → 404 | `DELETE /api-keys/999999` | HTTP 404 | ✅ |

---

## T5 — 凭证管理

| 编号 | 测试名称 | 请求 | 预期结果 | 状态 |
|------|----------|------|----------|------|
| T5-01 | API Key 认证访问凭证 | `GET /credentials/bigquery` + API Key | HTTP 200 | ✅ |
| T5-02 | JWT 认证访问凭证 | `GET /credentials/bigquery` + JWT | HTTP 200 | ✅ |
| T5-03 | 响应含 configured 字段 | `GET /credentials/bigquery` | body 含 `configured`（bool） | ✅ |
| T5-04 | 无认证 → 401 | `GET /credentials/bigquery`（无头） | HTTP 401 | ✅ |

---

## T6 — MCP 协议

> **端点**：`POST /mcp/`（含尾部斜杠，避免 307 重定向）
> **必要请求头**：`Accept: application/json, text/event-stream`

| 编号 | 测试名称 | 方法 | 预期结果 | 状态 |
|------|----------|------|----------|------|
| T6-01 | initialize 握手 | `initialize` | HTTP 200，result 含 `serverInfo` | ✅ |
| T6-02 | 列出工具 | `tools/list` | HTTP 200，tools 列表非空 | ✅ |
| T6-03 | 工具字段完整性 | `tools/list` | 每个工具含 name/description/inputSchema | ✅ |
| T6-04 | 调用不存在工具 | `tools/call` name=nonexistent | HTTP 200，返回 error content（不崩溃） | ✅ |
| T6-05 | 调用 customer_overview | `tools/call` name=customer_overview | HTTP 200，content 非空文本（无凭证时返回配置错误） | ✅ |
| T6-06 | 调用 order_trends | `tools/call` name=order_trends days=7 | HTTP 200，result 存在 | ✅ |
| T6-07 | 非法 JSON-RPC 请求 | 发送 `{"invalid":"payload"}` | 非 HTTP 500 | ✅ |

---

## 已发现并修复的问题

| 问题 | 原因 | 修复 |
|------|------|------|
| T6 全部失败（307） | `POST /mcp` → 307 重定向到 `/mcp/` | 测试改用 `/mcp/` 端点 |
| T6 返回"Not Acceptable" | 缺少 `Accept` 请求头 | 增加 `Accept: application/json, text/event-stream` |

---

## 补充说明

**关于 JWT 绕过登录**：测试工具通过已知的 `PORTAL_JWT_SECRET` 直接生成 JWT，无需走 `/auth/login`。这在测试环境合理，因为 secret 保存在 `.env.local` 中未对外暴露。**生产环境**应使用随机生成的 secret（不设置 `PORTAL_JWT_SECRET` 环境变量时服务会自动生成随机值）。

**MCP 工具无 BigQuery 凭证时的行为**：T6-05/T6-06 在未配置 BigQuery 时仍能通过，因为工具返回的是业务层错误消息（`isError: true` content），HTTP 层正常返回 200。这是期望行为。
