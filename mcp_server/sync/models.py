"""Data models for Emarsys sync configuration and state tracking."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Emarsys table categories recognised by this sync job
# ---------------------------------------------------------------------------
EMARSYS_EMAIL_TABLES = frozenset(
    [
        "email_sends",
        "email_opens",
        "email_clicks",
        "email_bounces",
        "email_unsubscribes",
    ]
)


def _resolve_database(env_var: str, tenant_id: str, prefix: str) -> str:
    """Resolve database name for a tenant using environment-variable mapping.

    Replicates the same logic used in ``mcp_server/server.py``.

    Args:
        env_var: Name of the environment variable (e.g. ``DTS_DATABASE``).
        tenant_id: Tenant identifier.
        prefix: Default prefix when no mapping found (e.g. ``dts``).

    Returns:
        Resolved database name.
    """
    mapping_str = os.getenv(env_var, "")
    mapping: dict[str, str] = dict(
        pair.split(":", 1) for pair in mapping_str.split(",") if ":" in pair
    )
    return mapping.get(tenant_id, f"{prefix}_{tenant_id}")


@dataclass
class StarRocksConfig:
    """Connection settings for StarRocks (MySQL-compatible protocol).

    Attributes:
        host: StarRocks FE host.
        port: StarRocks FE query port (default 9030).
        user: Database user.
        password: Database password.
        connect_timeout: TCP connect timeout in seconds.
    """

    host: str
    port: int
    user: str
    password: str
    connect_timeout: int = 10

    @classmethod
    def from_env(cls) -> "StarRocksConfig":
        """Build config from environment variables.

        Required env vars:
            STARROCKS_HOST, STARROCKS_USER, STARROCKS_PASSWORD

        Optional env vars:
            STARROCKS_PORT (default 9030)
            STARROCKS_CONNECT_TIMEOUT (default 10)

        Returns:
            StarRocksConfig instance.

        Raises:
            ValueError: If a required env var is missing.
        """
        host = os.environ.get("STARROCKS_HOST", "").strip()
        user = os.environ.get("STARROCKS_USER", "").strip()
        password = os.environ.get("STARROCKS_PASSWORD", "").strip()
        if not host:
            raise ValueError("Missing required env var: STARROCKS_HOST")
        if not user:
            raise ValueError("Missing required env var: STARROCKS_USER")
        return cls(
            host=host,
            port=int(os.environ.get("STARROCKS_PORT", "9030")),
            user=user,
            password=password,
            connect_timeout=int(os.environ.get("STARROCKS_CONNECT_TIMEOUT", "10")),
        )


@dataclass
class TenantSyncConfig:
    """Per-tenant sync configuration derived from BigQuery credentials + env mapping.

    Attributes:
        tenant_id: Tenant identifier.
        gcp_project_id: GCP project containing the Emarsys BigQuery dataset.
        dataset_id: BigQuery dataset ID (emarsys_*).
        sa_json: Service Account JSON dict (decrypted).
        dts_database: StarRocks database name for raw data (dts_{tenant_id}).
        datanow_database: StarRocks database name for DataNow (datanow_{tenant_id}).
        account_id: Emarsys customer/account ID (used in table name suffix).
    """

    tenant_id: str
    gcp_project_id: str
    dataset_id: str
    sa_json: dict[str, Any]
    dts_database: str
    datanow_database: str
    account_id: str | None = None

    @classmethod
    def from_credential(
        cls,
        tenant_id: str,
        gcp_project_id: str,
        dataset_id: str,
        sa_json: dict[str, Any],
        account_id: str | None = None,
    ) -> "TenantSyncConfig":
        """Construct config, resolving database names via env-variable mapping.

        Args:
            tenant_id: Tenant identifier.
            gcp_project_id: GCP project ID.
            dataset_id: BigQuery dataset ID.
            sa_json: Decrypted service account JSON dict.
            account_id: Emarsys account/customer ID (optional).

        Returns:
            TenantSyncConfig with resolved database names.
        """
        return cls(
            tenant_id=tenant_id,
            gcp_project_id=gcp_project_id,
            dataset_id=dataset_id,
            sa_json=sa_json,
            dts_database=_resolve_database("DTS_DATABASE", tenant_id, "dts"),
            datanow_database=_resolve_database("DATANOW_DATABASE", tenant_id, "datanow"),
            account_id=account_id,
        )


@dataclass
class TableSyncState:
    """Watermark state for a single BigQuery table.

    Attributes:
        tenant_id: Tenant identifier.
        dataset_id: BigQuery dataset ID.
        table_name: BigQuery table name.
        last_sync_time: ISO-8601 UTC timestamp of last successfully synced row.
        rows_synced_total: Cumulative rows synced across all runs.
        last_synced_at: ISO-8601 UTC timestamp of when this state was saved.
    """

    tenant_id: str
    dataset_id: str
    table_name: str
    last_sync_time: str | None = None
    rows_synced_total: int = 0
    last_synced_at: str | None = None

    def update(self, new_max_time: str | None, rows_count: int) -> None:
        """Update watermark after a successful sync batch.

        Args:
            new_max_time: ISO-8601 UTC string of the maximum event_time seen.
            rows_count: Number of rows written in this batch.
        """
        if new_max_time:
            self.last_sync_time = new_max_time
        self.rows_synced_total += rows_count
        self.last_synced_at = datetime.now(timezone.utc).isoformat()


class SyncStateStore:
    """PostgreSQL-backed watermark store for Emarsys sync jobs.

    Args:
        pool: asyncpg connection pool.
    """

    def __init__(self, pool: "asyncpg.Pool") -> None:
        self._pool = pool

    async def get_watermark(
        self, tenant_id: str, dataset_id: str, table_name: str
    ) -> "datetime | None":
        """Return last synced timestamp for a table, or None if never synced.

        Args:
            tenant_id: Tenant identifier.
            dataset_id: BigQuery dataset ID.
            table_name: BigQuery table name (without customer_id suffix).

        Returns:
            Last sync time as timezone-aware datetime, or None.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT last_sync_time FROM emarsys_sync_state "
                "WHERE tenant_id=$1 AND dataset_id=$2 AND table_name=$3",
                tenant_id,
                dataset_id,
                table_name,
            )
        return row["last_sync_time"] if row else None

    async def update_watermark(
        self,
        tenant_id: str,
        dataset_id: str,
        table_name: str,
        last_sync_time: "datetime",
        rows_delta: int = 0,
    ) -> None:
        """Upsert watermark after a successful sync batch.

        Args:
            tenant_id: Tenant identifier.
            dataset_id: BigQuery dataset ID.
            table_name: BigQuery table name.
            last_sync_time: Max event_time from the batch just written.
            rows_delta: Number of rows written in this batch.
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO emarsys_sync_state
                    (tenant_id, dataset_id, table_name, last_sync_time,
                     rows_synced_total, last_synced_at)
                VALUES ($1, $2, $3, $4, $5, NOW())
                ON CONFLICT (tenant_id, dataset_id, table_name) DO UPDATE SET
                    last_sync_time   = EXCLUDED.last_sync_time,
                    rows_synced_total = emarsys_sync_state.rows_synced_total + EXCLUDED.rows_synced_total,
                    last_synced_at   = EXCLUDED.last_synced_at
                """,
                tenant_id,
                dataset_id,
                table_name,
                last_sync_time,
                rows_delta,
            )


@dataclass
class SyncResult:
    """Result of syncing a single BigQuery table for one tenant.

    Attributes:
        tenant_id: Tenant identifier.
        table_name: Source BigQuery table name.
        rows_read: Rows fetched from BigQuery.
        rows_written_dts: Rows inserted into dts_* (StarRocks).
        rows_written_datanow: Rows inserted into datanow_*.t_retailevent.
        success: Whether the sync completed without error.
        error: Error message if ``success`` is False.
        duration_seconds: Wall-clock time for this table sync.
    """

    tenant_id: str
    table_name: str
    rows_read: int = 0
    rows_written_dts: int = 0
    rows_written_datanow: int = 0
    success: bool = True
    error: str | None = None
    duration_seconds: float = 0.0
