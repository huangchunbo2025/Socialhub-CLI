"""Entry point for socialhub-sync-emarsys daemon."""

from __future__ import annotations

import asyncio
import logging
import os
import time

import asyncpg

from emarsys_sync.runner import Runner
from emarsys_sync.scheduler import Scheduler
from emarsys_sync.summary import SummaryWriter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


async def _main() -> None:
    pg_url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    pg_pool = await asyncpg.create_pool(pg_url, min_size=1, max_size=5)

    interval = int(os.environ.get("SYNC_INTERVAL_MINUTES", "60")) * 60
    max_concurrent = int(os.environ.get("SYNC_MAX_CONCURRENT_TENANTS", "3"))
    batch_size = int(os.environ.get("SYNC_BATCH_SIZE", "10000"))
    state_path = os.environ.get("SYNC_STATE_PATH", "/data/emarsys_sync")

    runner = Runner(pg_pool=pg_pool, max_concurrent=max_concurrent, batch_size=batch_size)
    summary_writer = SummaryWriter(state_path=state_path)

    async def _sync_cycle() -> None:
        start = time.monotonic()
        results = await runner.sync_all()
        duration = time.monotonic() - start
        summary_writer.write(results, duration)

    scheduler = Scheduler(sync_fn=_sync_cycle, interval_seconds=interval)

    try:
        await scheduler.run_forever()
    finally:
        await pg_pool.close()


def main() -> None:
    """CLI entry point: socialhub-sync-emarsys."""
    asyncio.run(_main())


if __name__ == "__main__":
    main()
