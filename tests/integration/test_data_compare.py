"""TC-08 ~ TC-11: BQ 与 StarRocks 数据对比.

TC-08  email_sends BQ 行数 ≤ StarRocks vdm_t_message_record（不能多于 BQ）
TC-09  email_opens 写入 StarRocks 后行数 > 0（BQ 有数据则 SR 也必须有）
TC-10  vdm_t_message_record 表结构包含必要字段
TC-11  t_retailevent 表结构包含必要字段（datanow 写入目标）
"""

from __future__ import annotations

import pymysql
import pytest
from google.cloud import bigquery
from google.oauth2 import service_account

from emarsys_sync.bq_reader import BqReader
from mcp_server.sync.models import TenantSyncConfig


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _resolve_dataset(cfg: TenantSyncConfig) -> str:
    """Resolve dataset_id: use explicit value or discover first emarsys_* dataset."""
    if cfg.dataset_id:
        return cfg.dataset_id
    datasets = BqReader.list_emarsys_datasets(sa_json=cfg.sa_json, project=cfg.gcp_project_id)
    assert datasets, f"BQ project {cfg.gcp_project_id} 中未找到 emarsys_* dataset"
    return datasets[0]


def _bq_count(cfg: TenantSyncConfig, table_name: str) -> int:
    """查询 BigQuery 表总行数."""
    creds = service_account.Credentials.from_service_account_info(
        cfg.sa_json,
        scopes=["https://www.googleapis.com/auth/bigquery"],
    )
    client = bigquery.Client(project=cfg.gcp_project_id, credentials=creds)
    dataset_id = _resolve_dataset(cfg)
    account_id = cfg.account_id or ""
    table_full = f"{table_name}_{account_id}" if account_id else table_name
    query = (
        f"SELECT COUNT(*) AS cnt "
        f"FROM `{cfg.gcp_project_id}.{dataset_id}.{table_full}`"
    )
    rows = list(client.query(query).result())
    return int(rows[0]["cnt"]) if rows else 0


def _sr_count(
    sr_conn: pymysql.Connection,
    database: str,
    target_table: str,
    tenant_id: str,
) -> int:
    """查询 StarRocks 表中指定 tenant_id 的行数；表不存在时返回 -1."""
    try:
        with sr_conn.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) FROM {database}.{target_table} WHERE tenant_id = %s",
                (tenant_id,),
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0
    except pymysql.Error:
        return -1


def _sr_columns(
    sr_conn: pymysql.Connection, database: str, table: str
) -> set[str]:
    """返回 StarRocks 表的列名集合；表不存在时返回空集."""
    try:
        with sr_conn.cursor() as cur:
            cur.execute(f"DESCRIBE {database}.{table}")
            return {row[0] for row in cur.fetchall()}
    except pymysql.Error:
        return set()


# ---------------------------------------------------------------------------
# TC-08: email_sends 行数对比
# ---------------------------------------------------------------------------


async def test_tc08_email_sends_count_bq_vs_starrocks(
    first_tenant: TenantSyncConfig, sr_conn: pymysql.Connection
) -> None:
    """email_sends：StarRocks vdm_t_message_record 行数不超过 BQ 总量."""
    bq_count = _bq_count(first_tenant, "email_sends")
    sr_count = _sr_count(
        sr_conn, first_tenant.dts_database, "vdm_t_message_record", first_tenant.tenant_id
    )

    assert sr_count >= 0, (
        f"StarRocks {first_tenant.dts_database}.vdm_t_message_record 不可访问"
    )
    # StarRocks 是增量同步，行数可以少于 BQ，但不能多于 BQ（说明有重复写入或错误）
    assert sr_count <= bq_count, (
        f"StarRocks 行数({sr_count}) 超过 BQ 总量({bq_count})，可能存在重复写入"
    )


# ---------------------------------------------------------------------------
# TC-09: email_opens 同步后有数据
# ---------------------------------------------------------------------------


async def test_tc09_email_opens_synced_to_starrocks(
    first_tenant: TenantSyncConfig, sr_conn: pymysql.Connection
) -> None:
    """email_opens：BQ 有数据时 StarRocks vdm_t_message_record 也必须有数据."""
    bq_count = _bq_count(first_tenant, "email_opens")
    if bq_count == 0:
        pytest.skip("BQ email_opens 表无数据，跳过")

    sr_count = _sr_count(
        sr_conn, first_tenant.dts_database, "vdm_t_message_record", first_tenant.tenant_id
    )
    assert sr_count > 0, (
        f"BQ email_opens 有 {bq_count} 行，但 StarRocks vdm_t_message_record 为空"
    )


# ---------------------------------------------------------------------------
# TC-10: vdm_t_message_record 表结构
# ---------------------------------------------------------------------------


def test_tc10_vdm_message_record_schema(
    sr_conn: pymysql.Connection, first_tenant: TenantSyncConfig
) -> None:
    """vdm_t_message_record 包含 email_sends 映射所需的所有字段."""
    columns = _sr_columns(sr_conn, first_tenant.dts_database, "vdm_t_message_record")
    assert columns, (
        f"表 {first_tenant.dts_database}.vdm_t_message_record 不存在或无列"
    )
    required = {"id", "tenant_id", "consumer_code", "send_time", "message_id",
                "activity_code", "business_type", "template_type", "status"}
    missing = required - columns
    assert not missing, f"vdm_t_message_record 缺少字段: {missing}"


# ---------------------------------------------------------------------------
# TC-11: t_retailevent 表结构（datanow 写入目标）
# ---------------------------------------------------------------------------


def test_tc11_t_retailevent_schema(
    sr_conn: pymysql.Connection, first_tenant: TenantSyncConfig
) -> None:
    """datanow_test.t_retailevent 包含 DatanowWriter 写入所需的基本字段."""
    columns = _sr_columns(sr_conn, first_tenant.datanow_database, "t_retailevent")
    assert columns, (
        f"表 {first_tenant.datanow_database}.t_retailevent 不存在或无列"
    )
    required = {"tenant_id", "event_time"}
    missing = required - columns
    assert not missing, f"t_retailevent 缺少字段: {missing}"
