"""Tests for asyncio scheduler skip-if-running behaviour."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from emarsys_sync.scheduler import Scheduler


@pytest.mark.asyncio
async def test_scheduler_skips_when_lock_held():
    mock_run = AsyncMock()
    scheduler = Scheduler(sync_fn=mock_run, interval_seconds=60)

    # Acquire lock to simulate running task
    acquired = await scheduler._lock.acquire()
    assert acquired

    await scheduler._trigger_once()

    # sync_fn should NOT have been called
    mock_run.assert_not_awaited()
    scheduler._lock.release()


@pytest.mark.asyncio
async def test_scheduler_runs_when_lock_free():
    mock_run = AsyncMock()
    scheduler = Scheduler(sync_fn=mock_run, interval_seconds=60)

    await scheduler._trigger_once()

    mock_run.assert_awaited_once()
