"""All-tenant sync runner with bounded concurrency."""

from __future__ import annotations

import asyncio
import json
import logging
import os

import asyncpg
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from emarsys_sync.tenant_syncer import TenantResult, TenantSyncer
from mcp_server.models import TenantBigQueryCredential
from mcp_server.sync.models import SyncStateStore, TenantSyncConfig

logger = logging.getLogger(__name__)


async def _load_tenant_configs(
    session: AsyncSession,
    fernet_key: bytes,
) -> list[TenantSyncConfig]:
    """Load all active tenant configs from PostgreSQL.

    Args:
        session: SQLAlchemy async session.
        fernet_key: Fernet key bytes for decrypting service account JSON.

    Returns:
        List of TenantSyncConfig for all valid tenants.
    """
    f = Fernet(fernet_key)
    result = await session.execute(select(TenantBigQueryCredential))
    credentials = result.scalars().all()

    configs = []
    for cred in credentials:
        try:
            sa_json = json.loads(f.decrypt(cred.service_account_json.encode()).decode())
            config = TenantSyncConfig.from_credential(
                tenant_id=cred.tenant_id,
                gcp_project_id=cred.gcp_project_id,
                dataset_id=cred.dataset_id,
                sa_json=sa_json,
                account_id=cred.customer_id,
            )
            configs.append(config)
        except Exception as exc:
            logger.error("Failed to load config for tenant %s: %s", cred.tenant_id, exc)
    return configs


class Runner:
    """Coordinates a full sync cycle across all tenants with bounded concurrency.

    Args:
        pg_pool: asyncpg connection pool for watermark state.
        max_concurrent: Maximum number of tenants syncing in parallel.
        batch_size: Max BQ rows per table read.
    """

    def __init__(
        self,
        pg_pool: asyncpg.Pool,
        max_concurrent: int = 3,
        batch_size: int = 10_000,
    ) -> None:
        self._pg_pool = pg_pool
        self._max_concurrent = max_concurrent
        self._batch_size = batch_size
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def sync_all(self) -> list[TenantResult]:
        """Run one full sync cycle: load tenants, sync concurrently, return results.

        Returns:
            List of TenantResult, one per tenant.
        """
        fernet_key = os.environ["FERNET_KEY"].encode()
        sr_host = os.environ["STARROCKS_HOST"]
        sr_port = int(os.environ.get("STARROCKS_PORT", "9030"))
        sr_http_port = int(os.environ.get("STARROCKS_HTTP_PORT", "8030"))
        sr_user = os.environ["STARROCKS_USER"]
        sr_password = os.environ.get("STARROCKS_PASSWORD", "")
        database_url = os.environ["DATABASE_URL"]

        engine = create_async_engine(database_url, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            tenant_configs = await _load_tenant_configs(session, fernet_key)
        await engine.dispose()

        if not tenant_configs:
            logger.warning("No tenant configs found — nothing to sync")
            return []

        state_store = SyncStateStore(self._pg_pool)

        async def _sync_one(cfg: TenantSyncConfig) -> TenantResult:
            async with self._semaphore:
                syncer = TenantSyncer(
                    config=cfg,
                    sr_host=sr_host,
                    sr_port=sr_port,
                    sr_http_port=sr_http_port,
                    sr_user=sr_user,
                    sr_password=sr_password,
                    state_store=state_store,
                    batch_size=self._batch_size,
                )
                return await syncer.sync()

        tasks = [asyncio.create_task(_sync_one(cfg)) for cfg in tenant_configs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        tenant_results = []
        for cfg, res in zip(tenant_configs, results):
            if isinstance(res, Exception):
                logger.error("Tenant %s sync raised exception: %s", cfg.tenant_id, res)
                tenant_results.append(TenantResult(tenant_id=cfg.tenant_id))
            else:
                tenant_results.append(res)

        return tenant_results
