# Emarsys Sync 集成测试计划

## 运行方式

```bash
# 启动所有服务（含 postgres、mcp-server、emarsys-sync）
docker compose up -d

# 运行集成测试（test-runner 容器会自动等待 postgres 健康）
docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm test-runner
```

---

## 测试用例列表

### 一、连通性测试

| TC-ID | 名称 | 文件 | 前置条件 | 步骤 | 预期结果 |
|-------|------|------|----------|------|----------|
| TC-01 | PostgreSQL 可连接 | test_sync_flow.py | postgres 容器健康 | asyncpg 连接 DATABASE_URL，查询 emarsys_sync_state 表是否存在 | 表存在，无异常 |
| TC-02 | StarRocks 可连接 | test_sync_flow.py | VPN 已连 192.168.1.51 | pymysql 连接 STARROCKS_HOST:9030，执行 SELECT 1 | 返回 (1,)，无异常 |
| TC-03 | StarRocks 目标库存在 | test_sync_flow.py | TC-02 通过 | SHOW DATABASES，验证 dts_test 和 datanow_test 库存在 | 两库均存在 |

### 二、配置加载测试

| TC-ID | 名称 | 文件 | 前置条件 | 步骤 | 预期结果 |
|-------|------|------|----------|------|----------|
| TC-04 | BQ 凭证加载 | test_sync_flow.py | PostgreSQL 中已有 TenantBigQueryCredential 记录 | 用 CREDENTIAL_ENCRYPT_KEY 解密 SA JSON，构造 TenantSyncConfig | tenant_id、gcp_project_id、dataset_id 非空，sa_json 含 "type" 字段 |

### 三、同步流程测试

| TC-ID | 名称 | 文件 | 前置条件 | 步骤 | 预期结果 |
|-------|------|------|----------|------|----------|
| TC-05 | 全量同步无失败表 | test_sync_flow.py | TC-04 通过，BQ 有数据 | 调用 TenantSyncer.sync(batch_size=500)，收集 TenantResult | failed_tables 为空，rows_read > 0 |
| TC-06 | watermark 持久化 | test_sync_flow.py | TC-05 通过 | 查询 emarsys_sync_state：email_sends / email_opens / email_clicks 任一表 watermark 不为 NULL | 至少一个表有 last_sync_time |
| TC-07 | 增量同步 | test_sync_flow.py | TC-06 通过（有 watermark） | 再次调用 TenantSyncer.sync(batch_size=100) | 每表 rows_read ≤ 100（增量模式不超 batch_size） |

### 四、数据对比测试

| TC-ID | 名称 | 文件 | 前置条件 | 步骤 | 预期结果 |
|-------|------|------|----------|------|----------|
| TC-08 | email_sends 行数对比 | test_data_compare.py | TC-05 通过 | BQ: COUNT(*) FROM email_sends；SR: COUNT(*) FROM dts_test.vdm_t_message_record WHERE tenant_id=uat | SR 行数 ≤ BQ 行数（增量，不能多） |
| TC-09 | email_opens 同步有数据 | test_data_compare.py | BQ email_opens 有数据 | BQ COUNT > 0 时检查 SR vdm_t_message_record 行数 | SR 行数 > 0 |
| TC-10 | vdm_t_message_record 表结构 | test_data_compare.py | TC-03 通过 | DESCRIBE dts_test.vdm_t_message_record | 含字段：id, tenant_id, consumer_code, send_time, message_id, activity_code, business_type, template_type, status |
| TC-11 | t_retailevent 表结构 | test_data_compare.py | TC-03 通过 | DESCRIBE datanow_test.t_retailevent | 含字段：tenant_id, event_time |

### 五、回归测试（其他模块）

| TC-ID | 名称 | 文件 | 前置条件 | 步骤 | 预期结果 |
|-------|------|------|----------|------|----------|
| TC-12 | MCP Server 健康检查 | test_regression.py | mcp-server 容器运行 | GET http://mcp-server:8090/health | 返回 200 |
| TC-13 | 无 API Key 返回 401 | test_regression.py | mcp-server 容器运行 | POST http://mcp-server:8090/mcp（无 X-API-Key） | 返回 401 |
| TC-14 | 有效 API Key 初始化 MCP | test_regression.py | mcp-server 容器运行，MCP_API_KEYS 已设置 | POST /mcp 携带 X-API-Key，body 为 MCP initialize | 返回 200，含 serverInfo |
| TC-15 | Runner 多租户并发 | test_regression.py | TC-01、TC-04 通过 | Runner(max_concurrent=2, batch_size=100).sync_all() | 返回 list，无 Exception 抛出 |

---

## 环境变量（.env.docker 中配置）

| 变量 | 说明 |
|------|------|
| `DATABASE_URL` | PostgreSQL 连接串（容器内指向 postgres:5432） |
| `CREDENTIAL_ENCRYPT_KEY` | Fernet 密钥，解密 BQ SA JSON |
| `STARROCKS_HOST` | StarRocks FE 地址（192.168.1.51） |
| `STARROCKS_PORT` | MySQL 协议端口（9030） |
| `STARROCKS_HTTP_PORT` | Stream Load HTTP 端口（8030） |
| `STARROCKS_USER` | StarRocks 用户名 |
| `STARROCKS_PASSWORD` | StarRocks 密码 |
| `DTS_DATABASE` | dts 库映射（uat:dts_test） |
| `DATANOW_DATABASE` | datanow 库映射（uat:datanow_test） |
| `MCP_API_KEYS` | MCP API Key 映射（TC-13/14 回归用） |

---

## 通过标准

| 类别 | 标准 |
|------|------|
| 连通性（TC-01~03） | 全部通过，否则后续 TC 无意义 |
| 同步流程（TC-05~07） | TC-05 零失败表；TC-06 有 watermark；TC-07 增量不超 batch |
| 数据对比（TC-08~11） | SR 行数不超 BQ；BQ 有数据 SR 必须有 |
| 回归（TC-12~15） | MCP Server 正常；多租户并发无崩溃 |
