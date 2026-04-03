# Emarsys Sync 设计文档

> 日期：2026-04-03
> 状态：已审批，待实现

---

## 背景

将 SAP Emarsys BigQuery Open Data（29 张表）增量同步到 StarRocks：
- `dts_{tenant_id}` — 业务维度表（vdm_t_message_record / vdm_t_activity 等）
- `datanow_{tenant_id}.t_retailevent` — 通用事件 EAV 表（所有含 contact_id 的 21 张表）

凭证来源：`mcp_server.tenant_bigquery_credentials`（PostgreSQL，Fernet 加密）。

字段映射规则详见：`docs/emarsys-integration/sync-mapping.md`

---

## 部署形态

独立 Docker 镜像，通过 entry point `socialhub-sync-emarsys` 启动，与 `socialhub-mcp` 完全隔离。

---

## 架构方案

采用**纯 asyncio 调度循环**（方案三），零额外依赖，逻辑完全可控：

- 主循环：`while True: await sync_all(); await asyncio.sleep(interval)`
- skip-if-running：`asyncio.Lock` 保护，获取失败直接跳过本轮
- 有限并发：`asyncio.Semaphore(N)` 控制 tenant 并发数
- 手动触发：监听 `SIGUSR1` 信号立即触发一次

---

## 目录结构

```
src/socialhub-cli/
├── emarsys_sync/                  # 新增顶层包
│   ├── __init__.py
│   ├── __main__.py                # 入口：daemon 模式 / 手动触发
│   ├── scheduler.py               # asyncio 调度循环 + skip-if-running + SIGUSR1
│   ├── runner.py                  # 单次全量同步协调器（所有 tenant）
│   ├── tenant_syncer.py           # 单 tenant 同步逻辑
│   ├── bq_reader.py               # BigQuery 增量读取（watermark 查询）
│   ├── dts_writer.py              # StarRocks dts_ 写入
│   ├── datanow_writer.py          # StarRocks datanow_.t_retailevent 写入
│   ├── view_manager.py            # CREATE OR REPLACE VIEW（每次 sync 后执行）
│   ├── summary.py                 # 运行汇总写入 run_summary.json
│   └── mapping/
│       ├── __init__.py
│       ├── dts_mappings.py        # BigQuery → dts_ 映射规则（纯数据）
│       └── datanow_mappings.py    # BigQuery → t_retailevent slot 映射 + view DDL（纯数据）
│
└── mcp_server/
    └── sync/
        ├── __init__.py
        └── models.py              # 共享数据模型（已有）
```

---

## 数据流

```
Scheduler（每隔 SYNC_INTERVAL_MINUTES 触发）
    │  skip-if-running: asyncio.Lock
    └─► Runner.sync_all()
            │  asyncio.Semaphore(SYNC_MAX_CONCURRENT_TENANTS)
            ├─► TenantSyncer.sync(tenant_1)
            ├─► TenantSyncer.sync(tenant_2)
            └─► TenantSyncer.sync(tenant_3)

TenantSyncer.sync(tenant)
    │
    ├─ 1. 从 PostgreSQL 读取凭证（Fernet 解密 SA JSON）
    ├─ 2. 遍历 29 张 BQ 表，每张表：
    │       ├─ BqReader.read_incremental(table, watermark)
    │       │       └─ SELECT ... WHERE event_time > last_sync_time ORDER BY event_time LIMIT batch_size
    │       ├─ DtsWriter.write(rows)        # 有 dts_ 映射的表
    │       ├─ DatanowWriter.write(rows)    # 有 contact_id 的 21 张表
    │       └─ SyncStateStore.update(watermark, rows_count)  # 两个写入都成功后更新
    │
    ├─ 3. ViewManager.refresh_views(tenant)
    │       └─ CREATE OR REPLACE VIEW t_retailevent_{event_key}（每个 event_key，从 mapping 动态生成）
    │
    └─ 4. Summary.record(results) → run_summary.json
```

---

## 增量 Watermark

- **所有 29 张表统一使用 `event_time`** 作为增量 watermark
- **`engagement_events` 特殊处理**：`partitiontime` 过滤为 BigQuery 强制要求，封装在 `bq_reader.py` 内：

```python
if table_name == "engagement_events":
    query += f" AND partitiontime = DATE('{watermark_date}')"
```

### Watermark 持久化

watermark 状态保存在 **PostgreSQL `emarsys_sync_state` 表**（复用现有 `DATABASE_URL`），容器重启不丢失：

```sql
CREATE TABLE emarsys_sync_state (
    tenant_id         VARCHAR(64)   NOT NULL,
    dataset_id        VARCHAR(128)  NOT NULL,
    table_name        VARCHAR(128)  NOT NULL,
    last_sync_time    TIMESTAMPTZ,
    rows_synced_total BIGINT        NOT NULL DEFAULT 0,
    last_synced_at    TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, dataset_id, table_name)
);
```

`SyncStateStore` 从原 JSON 文件改为读写此表（asyncpg），`mcp_server/sync/models.py` 中原文件实现废弃。

---

## 视图管理

每次 sync 完成后执行 `CREATE OR REPLACE VIEW`（幂等，纯 DDL，无数据扫描）：

- **视图位置**：`datanow_{tenant_id}`
- **视图命名**：`t_retailevent_emarsys_email_send`（去掉 `$`，下划线连接）
- **视图内容**：从 `datanow_mappings.py` 动态生成，slot 字段自动映射为语义名

```python
def build_view_ddl(event_key: str, slot_map: dict[str, str]) -> str:
    columns = ", ".join(f"{slot} AS {name}" for slot, name in slot_map.items())
    view_name = event_key.lstrip("$").replace("-", "_")
    return (
        f"CREATE OR REPLACE VIEW t_retailevent_{view_name} AS\n"
        f"SELECT event_time, customer_code, tenant_id, {columns}\n"
        f"FROM t_retailevent WHERE event_key = '{event_key}'"
    )
```

mapping 代码变更后，下一次 sync 自动生效。

---

## 错误处理

| 场景 | 处理方式 |
|------|---------|
| BQ 读取失败（限速/网络） | 跳过该表，watermark 不更新，记录 error |
| dts_ 写入失败 | 跳过 dts_，datanow 继续，watermark 不更新 |
| datanow 写入失败 | 记录 error，watermark 不更新 |
| 两个写入都成功 | 更新 watermark |
| tenant 凭证无效 | 跳过该 tenant 所有表，记录 tenant 级错误 |
| 上轮 sync 未完成 | skip-if-running，丢弃本轮调度 |

---

## 运行汇总

每次 sync 完成后写入 `$SYNC_STATE_PATH/run_summary.json`（仅汇总统计，非关键状态，容器重启可丢弃）：

```json
{
  "last_run_at": "2026-04-03T10:00:00Z",
  "duration_seconds": 42.3,
  "tenants": {
    "uat": {
      "success": 27,
      "failed": 2,
      "failed_tables": ["engagement_events", "conversation_deliveries"],
      "rows_read": 15420,
      "rows_written_dts": 8900,
      "rows_written_datanow": 14200
    }
  }
}
```

---

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SYNC_INTERVAL_MINUTES` | `60` | 同步间隔（分钟） |
| `SYNC_MAX_CONCURRENT_TENANTS` | `3` | 最大并发 tenant 数 |
| `SYNC_BATCH_SIZE` | `10000` | 每次 BQ 读取行数上限 |
| `SYNC_STATE_PATH` | `/data/emarsys_sync` | 状态文件目录 |
| `STARROCKS_HOST` | 必填 | StarRocks FE 地址 |
| `STARROCKS_USER` | 必填 | StarRocks 用户名 |
| `STARROCKS_PASSWORD` | 必填 | StarRocks 密码 |
| `STARROCKS_PORT` | `9030` | StarRocks 端口 |
| `DATABASE_URL` | 必填 | PostgreSQL 连接串（读租户凭证） |
| `DTS_DATABASE` | `dts_{tenant_id}` | DTS 库路由映射 |
| `DATANOW_DATABASE` | `datanow_{tenant_id}` | DataNow 库路由映射 |

---

## 模块依赖

```
emarsys_sync（新增）
    ├── mcp_server.sync.models      共享数据模型
    ├── mcp_server.models           TenantBigQueryCredential
    ├── mcp_server.crypto           Fernet 解密
    ├── google-cloud-bigquery       BQ 读取
    └── pymysql                     StarRocks 写入（新增依赖）
```

`pyproject.toml` 新增：

```toml
[project.optional-dependencies]
sync = [
    "pymysql>=1.1.0",
]

[project.scripts]
socialhub-sync-emarsys = "emarsys_sync.__main__:main"
```

---

## 测试策略

```
tests/emarsys_sync/
├── test_dts_mappings.py       # 映射规则：输入行 → 期望输出字段（无 mock）
├── test_datanow_mappings.py   # slot 映射 + view DDL 生成（无 mock）
├── test_bq_reader.py          # BQ 查询构造（mock BigQuery client）
├── test_dts_writer.py         # INSERT SQL 构造（mock pymysql）
├── test_datanow_writer.py     # t_retailevent 写入（mock pymysql）
├── test_view_manager.py       # DDL 生成正确性（mock pymysql）
└── test_scheduler.py          # skip-if-running（asyncio + AsyncMock）
```

- mapping 模块为纯函数，直接断言，无 mock
- IO 模块 mock 外部客户端，测构造逻辑和错误分支
- 不做集成测试（CI 环境无真实 BQ/StarRocks）
