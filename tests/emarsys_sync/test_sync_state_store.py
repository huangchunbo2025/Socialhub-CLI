"""Tests for PostgreSQL-backed SyncStateStore."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_server.sync.models import SyncStateStore


@pytest.fixture
def mock_pool():
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


@pytest.mark.asyncio
async def test_get_watermark_returns_none_when_no_row(mock_pool):
    pool, conn = mock_pool
    conn.fetchrow.return_value = None

    store = SyncStateStore(pool)
    result = await store.get_watermark("uat", "emarsys_12345", "email_sends")

    assert result is None
    conn.fetchrow.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_watermark_returns_datetime_from_row(mock_pool):
    pool, conn = mock_pool
    ts = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    conn.fetchrow.return_value = {"last_sync_time": ts}

    store = SyncStateStore(pool)
    result = await store.get_watermark("uat", "emarsys_12345", "email_sends")

    assert result == ts


@pytest.mark.asyncio
async def test_update_watermark_upserts_row(mock_pool):
    pool, conn = mock_pool
    ts = datetime(2026, 1, 2, tzinfo=timezone.utc)

    store = SyncStateStore(pool)
    await store.update_watermark("uat", "emarsys_12345", "email_sends", ts, rows_delta=500)

    conn.execute.assert_awaited_once()
    call_args = conn.execute.call_args[0]
    assert "INSERT INTO emarsys_sync_state" in call_args[0]
    assert "ON CONFLICT" in call_args[0]
