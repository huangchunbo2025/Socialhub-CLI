"""Tests for database connection module."""
import os
from unittest.mock import patch

import pytest


def test_db_module_imports():
    """db.py 可以正常导入，关键函数存在。"""
    from mcp_server.db import get_session, init_db, close_db
    assert callable(get_session)
    assert callable(init_db)
    assert callable(close_db)


def test_database_url_from_env():
    """DATABASE_URL 从环境变量读取。"""
    with patch.dict(os.environ, {"DATABASE_URL": "postgresql+asyncpg://user:pw@host/db"}):
        import importlib
        import mcp_server.db as db_module
        importlib.reload(db_module)
        assert "host" in db_module.DATABASE_URL
