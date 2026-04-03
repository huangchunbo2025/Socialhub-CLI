"""asyncio daemon scheduler with skip-if-running and SIGUSR1 manual trigger."""

from __future__ import annotations

import asyncio
import logging
import signal
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


class Scheduler:
    """Long-running asyncio scheduler.

    Runs ``sync_fn`` on a fixed interval. If the previous run is still in
    progress when the next interval fires, the new run is skipped.

    Sends SIGUSR1 to trigger an immediate run outside the normal schedule.

    Args:
        sync_fn: Async callable that performs one sync cycle.
        interval_seconds: Seconds between scheduled runs.
    """

    def __init__(
        self,
        sync_fn: Callable[[], Awaitable[None]],
        interval_seconds: int = 3600,
    ) -> None:
        self._sync_fn = sync_fn
        self._interval = interval_seconds
        self._lock = asyncio.Lock()
        self._manual_trigger = asyncio.Event()

    async def _trigger_once(self) -> None:
        """Run sync_fn if the lock is free; skip otherwise."""
        if self._lock.locked():
            logger.info("Scheduler: previous sync still running — skipping")
            return
        async with self._lock:
            try:
                await self._sync_fn()
            except Exception as exc:
                logger.error("Scheduler: sync cycle raised: %s", exc)

    def _install_sigusr1(self) -> None:
        """Install SIGUSR1 handler to trigger an immediate run."""

        def _handle(_sig: int, _frame: object) -> None:
            logger.info("Scheduler: SIGUSR1 received — triggering manual run")
            asyncio.get_event_loop().call_soon_threadsafe(self._manual_trigger.set)

        signal.signal(signal.SIGUSR1, _handle)

    async def run_forever(self) -> None:
        """Start the scheduler loop. Never returns under normal conditions."""
        self._install_sigusr1()
        logger.info("Scheduler started: interval=%ds", self._interval)

        # Run immediately on startup
        await self._trigger_once()

        while True:
            try:
                await asyncio.wait_for(
                    self._manual_trigger.wait(),
                    timeout=float(self._interval),
                )
                self._manual_trigger.clear()
                logger.info("Scheduler: manual trigger fired")
            except asyncio.TimeoutError:
                logger.info("Scheduler: interval elapsed, triggering sync")

            await self._trigger_once()
