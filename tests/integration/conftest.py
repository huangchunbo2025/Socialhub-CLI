"""集成测试共享 fixtures.

运行前提：
- PostgreSQL 可连接（DATABASE_URL）
- StarRocks 可连接（STARROCKS_HOST / STARROCKS_USER / STARROCKS_PASSWORD）
- PostgreSQL 中已有 TenantBigQueryCredential 记录
"""

from __future__ import annotations

import json
import os

import asyncpg
import pymysql
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from mcp_server.models import TenantBigQueryCredential
from mcp_server.sync.models import SyncStateStore, TenantSyncConfig


# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
async def pg_pool() -> asyncpg.Pool:
    """asyncpg 连接池，指向 socialhub_mcp 库."""
    raw_url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    pool = await asyncpg.create_pool(raw_url, min_size=1, max_size=3)
    yield pool
    await pool.close()


@pytest.fixture(scope="session")
def state_store(pg_pool: asyncpg.Pool) -> SyncStateStore:
    """watermark 状态存储."""
    return SyncStateStore(pg_pool)


# ---------------------------------------------------------------------------
# StarRocks
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def sr_conn() -> pymysql.Connection:
    """pymysql 连接（MySQL 协议），用于 DDL 查询和数据验证."""
    conn = pymysql.connect(
        host=os.environ["STARROCKS_HOST"],
        port=int(os.environ.get("STARROCKS_PORT", "9030")),
        user=os.environ["STARROCKS_USER"],
        password=os.environ.get("STARROCKS_PASSWORD", ""),
        connect_timeout=15,
        autocommit=True,
    )
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Tenant 配置（从 PostgreSQL 加载，解密 BQ SA JSON）
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
async def tenant_configs(pg_pool: asyncpg.Pool) -> list[TenantSyncConfig]:
    """从 PostgreSQL 加载所有租户 BQ 配置（同 Runner._load_tenant_configs 逻辑）."""
    fernet_key = os.environ["CREDENTIAL_ENCRYPT_KEY"].encode()
    f = Fernet(fernet_key)

    database_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    configs: list[TenantSyncConfig] = []
    async with session_factory() as session:
        result = await session.execute(select(TenantBigQueryCredential))
        credentials = result.scalars().all()
        for cred in credentials:
            sa_json = json.loads(f.decrypt(cred.service_account_json.encode()).decode())
            configs.append(
                TenantSyncConfig.from_credential(
                    tenant_id=cred.tenant_id,
                    gcp_project_id=cred.gcp_project_id,
                    dataset_id=cred.dataset_id,
                    sa_json=sa_json,
                    account_id=cred.customer_id,
                )
            )

    await engine.dispose()
    assert configs, "PostgreSQL 中没有 BQ 凭证记录，请先通过 MCP Portal 写入"
    return configs


@pytest.fixture(scope="session")
def first_tenant(tenant_configs: list[TenantSyncConfig]) -> TenantSyncConfig:
    """取第一个租户配置（大多数 TC 只需一个租户）."""
    return tenant_configs[0]


# ---------------------------------------------------------------------------
# Watermark 管理
# ---------------------------------------------------------------------------


@pytest.fixture
async def clear_watermarks(pg_pool: asyncpg.Pool, first_tenant: TenantSyncConfig) -> None:
    """测试前清除该租户的所有 watermark，确保同步从头读取."""
    async with pg_pool.acquire() as conn:
        deleted = await conn.execute(
            "DELETE FROM emarsys_sync_state WHERE tenant_id = $1",
            first_tenant.tenant_id,
        )
    print(f"\n[fixture] cleared watermarks for {first_tenant.tenant_id}: {deleted}")
