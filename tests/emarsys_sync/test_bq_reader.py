"""Tests for BigQuery incremental reader."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from emarsys_sync.bq_reader import BqReader, build_incremental_query


def test_build_query_with_watermark():
    sql = build_incremental_query(
        project="my-project",
        dataset="emarsys_12345",
        table_full="email_sends_99",
        watermark=datetime(2026, 1, 1, tzinfo=timezone.utc),
        batch_size=1000,
    )
    assert "FROM `my-project.emarsys_12345.email_sends_99`" in sql
    assert "WHERE event_time > '2026-01-01" in sql
    assert "ORDER BY event_time" in sql
    assert "LIMIT 1000" in sql


def test_build_query_without_watermark_reads_all():
    sql = build_incremental_query(
        project="my-project",
        dataset="emarsys_12345",
        table_full="email_sends_99",
        watermark=None,
        batch_size=500,
    )
    assert "WHERE" not in sql
    assert "LIMIT 500" in sql


def test_build_query_engagement_events_adds_partition_filter():
    sql = build_incremental_query(
        project="my-project",
        dataset="emarsys_12345",
        table_full="engagement_events_99",
        watermark=datetime(2026, 3, 15, tzinfo=timezone.utc),
        batch_size=1000,
    )
    assert "partitiontime = DATE(" in sql


def test_bq_reader_read_incremental_calls_query():
    mock_client = MagicMock()
    mock_result = MagicMock()
    mock_result.__iter__ = MagicMock(return_value=iter([
        {"contact_id": 1, "event_time": "2026-01-01T00:00:00Z"},
    ]))
    mock_client.query.return_value.result.return_value = mock_result

    reader = BqReader(client=mock_client, project="proj", dataset="emarsys_12345", batch_size=100)
    rows = reader.read_incremental("email_sends", account_id="99", watermark=None)

    assert len(rows) == 1
    mock_client.query.assert_called_once()
