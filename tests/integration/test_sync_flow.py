"""TC-01 ~ TC-07: Emarsys Sync 端到端集成测试.

TC-01  PostgreSQL 可连接，emarsys_sync_state 表存在
TC-02  StarRocks 可连接
TC-03  StarRocks dts_test / datanow_test 库存在
TC-04  从 PostgreSQL 成功加载 BQ 凭证
TC-05  TenantSyncer.sync() 全量同步，无失败表
TC-06  同步后 watermark 写入 PostgreSQL
TC-07  二次同步增量模式，rows_read 不超过 batch_size
"""

from __future__ import annotations

import os

import asyncpg
import pymysql
import pytest

# 所有 async 测试使用 session 级别 event loop，与 session fixture pg_pool 共享同一 loop
pytestmark = pytest.mark.asyncio(loop_scope="session")

from emarsys_sync.tenant_syncer import TenantSyncer
from mcp_server.sync.models import SyncStateStore, TenantSyncConfig


def _make_syncer(cfg: TenantSyncConfig, pg_pool: asyncpg.Pool, batch_size: int = 500) -> TenantSyncer:
    return TenantSyncer(
        config=cfg,
        sr_host=os.environ["STARROCKS_HOST"],
        sr_port=int(os.environ.get("STARROCKS_PORT", "9030")),
        sr_http_port=int(os.environ.get("STARROCKS_HTTP_PORT", "8030")),
        sr_user=os.environ["STARROCKS_USER"],
        sr_password=os.environ.get("STARROCKS_PASSWORD", ""),
        state_store=SyncStateStore(pg_pool),
        batch_size=batch_size,
    )


# ---------------------------------------------------------------------------
# TC-01: PostgreSQL 连通性
# ---------------------------------------------------------------------------


async def test_tc01_postgres_connectivity(pg_pool: asyncpg.Pool) -> None:
    """PostgreSQL 可连接，emarsys_sync_state 表存在."""
    async with pg_pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT EXISTS ("
            "  SELECT 1 FROM information_schema.tables"
            "  WHERE table_name = 'emarsys_sync_state'"
            ")"
        )
    assert exists, "emarsys_sync_state 表不存在 — 请先执行 alembic upgrade head"


# ---------------------------------------------------------------------------
# TC-02: StarRocks 连通性
# ---------------------------------------------------------------------------


def test_tc02_starrocks_connectivity(sr_conn: pymysql.Connection) -> None:
    """StarRocks MySQL 协议可连接."""
    with sr_conn.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone() == (1,)


# ---------------------------------------------------------------------------
# TC-03: StarRocks 目标库存在
# ---------------------------------------------------------------------------


def test_tc03_starrocks_databases_exist(
    sr_conn: pymysql.Connection, first_tenant: TenantSyncConfig
) -> None:
    """dts_test / datanow_test 库在 StarRocks 中存在."""
    with sr_conn.cursor() as cur:
        cur.execute("SHOW DATABASES")
        dbs = {row[0] for row in cur.fetchall()}

    assert first_tenant.dts_database in dbs, (
        f"StarRocks 缺少 dts 库: '{first_tenant.dts_database}'"
    )
    assert first_tenant.datanow_database in dbs, (
        f"StarRocks 缺少 datanow 库: '{first_tenant.datanow_database}'"
    )


# ---------------------------------------------------------------------------
# TC-04: BQ 凭证加载
# ---------------------------------------------------------------------------


async def test_tc04_tenant_config_loaded(first_tenant: TenantSyncConfig) -> None:
    """从 PostgreSQL 成功解密并加载 BQ Service Account 凭证."""
    assert first_tenant.tenant_id, "tenant_id 为空"
    assert first_tenant.gcp_project_id, "gcp_project_id 为空"
    assert isinstance(first_tenant.sa_json, dict), "sa_json 解密失败或格式错误"
    assert "type" in first_tenant.sa_json, "sa_json 缺少 'type' 字段，可能不是有效的 SA JSON"


# ---------------------------------------------------------------------------
# TC-05: 全量同步
# ---------------------------------------------------------------------------


async def test_tc05_full_sync_no_failed_tables(
    first_tenant: TenantSyncConfig, pg_pool: asyncpg.Pool, clear_watermarks: None
) -> None:
    """TenantSyncer.sync() 全量同步（清空 watermark），所有表无错误且读到行."""
    syncer = _make_syncer(first_tenant, pg_pool, batch_size=500)
    result = await syncer.sync()

    assert result is not None
    assert result.tenant_id == first_tenant.tenant_id

    if result.failed_tables:
        details = [
            f"{t.table_name}: {t.error}"
            for t in result.table_results
            if not t.success
        ]
        pytest.fail("以下表同步失败:\n" + "\n".join(details))

    assert result.rows_read > 0, (
        "BQ 中未读到任何行 — 确认 BQ 数据集中有数据且 SA 有读权限"
    )


# ---------------------------------------------------------------------------
# TC-06: watermark 持久化
# ---------------------------------------------------------------------------


async def test_tc06_watermark_persisted_after_sync(
    first_tenant: TenantSyncConfig, pg_pool: asyncpg.Pool
) -> None:
    """tc05 同步后 emarsys_sync_state 中至少一个表有 watermark.

    依赖 tc05（已清空 watermark 并完成一次全量同步），
    验证 watermark 确实被持久化到 PostgreSQL。
    """
    async with pg_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt FROM emarsys_sync_state "
            "WHERE tenant_id=$1 AND last_sync_time IS NOT NULL",
            first_tenant.tenant_id,
        )
    assert row and row["cnt"] > 0, (
        "emarsys_sync_state 中无任何 watermark — tc05 同步后应写入 watermark，"
        "请确认 BQ 表有数据且时间字段有值"
    )


# ---------------------------------------------------------------------------
# TC-07: 增量同步
# ---------------------------------------------------------------------------


async def test_tc07_second_sync_is_incremental(
    first_tenant: TenantSyncConfig, pg_pool: asyncpg.Pool
) -> None:
    """二次同步（有 watermark）每表读取行数 ≤ batch_size."""
    batch_size = 100
    syncer = _make_syncer(first_tenant, pg_pool, batch_size=batch_size)
    result = await syncer.sync()

    over_batch = [
        f"{t.table_name}: rows_read={t.rows_read}"
        for t in result.table_results
        if t.rows_read > batch_size
    ]
    assert not over_batch, (
        "以下表在增量模式下超出 batch_size:\n" + "\n".join(over_batch)
    )
