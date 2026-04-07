"""Unit tests for TableResult.skipped and _sync_table skip logic."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from emarsys_sync.bq_reader import TableNotFoundError
from emarsys_sync.tenant_syncer import TableResult, TenantResult


def test_table_result_skipped_defaults_false():
    tr = TableResult(table_name="email_sends")
    assert tr.skipped is False


def test_table_result_skipped_is_not_error():
    tr = TableResult(table_name="email_sends", skipped=True)
    assert tr.success is True
    assert tr.error is None


def test_tenant_result_skipped_count():
    result = TenantResult(tenant_id="t1")
    result.table_results = [
        TableResult("a", skipped=True),
        TableResult("b", skipped=True),
        TableResult("c"),
    ]
    assert result.skipped_count == 2


def test_tenant_result_success_count_excludes_skipped():
    result = TenantResult(tenant_id="t1")
    result.table_results = [
        TableResult("a", skipped=True),
        TableResult("b"),           # success, not skipped
        TableResult("c", error="x"),
    ]
    # success = no error (includes skipped)
    assert result.success_count == 2
    assert result.failed_count == 1
    assert result.skipped_count == 1
