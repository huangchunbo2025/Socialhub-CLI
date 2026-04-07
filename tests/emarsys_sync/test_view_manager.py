"""Tests for semantic view manager."""
from __future__ import annotations

from unittest.mock import MagicMock

from emarsys_sync.view_manager import ViewManager


def _make_manager():
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    manager = ViewManager(conn=conn, database="datanow_uat")
    return manager, cursor


def test_refresh_views_executes_ddl_for_each_event_key():
    manager, cursor = _make_manager()
    manager.refresh_all_views()
    # 48 event keys → 48 DDL executions + 1 USE statement = 49 total
    # But the test checks for DDL executions (excluding USE):
    # Actually let's check total calls >= 48
    assert cursor.execute.call_count >= 48


def test_refresh_views_ddl_contains_create_or_replace():
    manager, cursor = _make_manager()
    manager.refresh_all_views()
    ddl_calls = [
        call_args[0][0]
        for call_args in cursor.execute.call_args_list
        if "CREATE OR REPLACE VIEW" in call_args[0][0]
    ]
    assert len(ddl_calls) == 48


def test_refresh_views_uses_correct_database():
    manager, cursor = _make_manager()
    manager.refresh_all_views()
    ddl_calls = [
        call_args[0][0]
        for call_args in cursor.execute.call_args_list
        if "CREATE OR REPLACE VIEW" in call_args[0][0]
    ]
    assert all("datanow_uat" in sql for sql in ddl_calls)
