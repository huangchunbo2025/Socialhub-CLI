"""Tests for cli.ai.session (SessionStore)."""

import json
import os
import time
from pathlib import Path

import pytest

from cli.ai.session import Session, SessionStore
from cli.config import SessionConfig


@pytest.fixture
def tmp_config(tmp_path):
    return SessionConfig(
        ttl_hours=24,
        max_history=10,
        sessions_dir=str(tmp_path / "sessions"),
    )


@pytest.fixture
def store(tmp_config):
    return SessionStore(tmp_config)


def test_new_session_creates_file(store, tmp_config):
    session = store.new_session()
    assert session.session_id
    path = Path(tmp_config.sessions_dir) / f"{session.session_id}.json"
    assert path.exists()


def test_load_session(store):
    session = store.new_session()
    loaded = store.load(session.session_id)
    assert loaded is not None
    assert loaded.session_id == session.session_id


def test_load_missing_returns_none(store):
    assert store.load("nonexistent-session-id") is None


def test_add_turn_persists(store):
    session = store.new_session()
    session.add_turn("hello", "world", max_history=10)
    store.save(session)
    loaded = store.load(session.session_id)
    assert loaded is not None
    assert len(loaded.messages) == 2
    assert loaded.messages[0]["role"] == "user"
    assert loaded.messages[0]["content"] == "hello"


def test_max_history_trim(store):
    session = store.new_session()
    for i in range(15):
        session.add_turn(f"user{i}", f"asst{i}", max_history=10)
    # max_history=10 => max 20 messages
    assert len(session.messages) == 20


def test_expired_session_returns_none(tmp_path):
    config = SessionConfig(ttl_hours=0, max_history=10, sessions_dir=str(tmp_path / "s"))
    store = SessionStore(config)
    session = store.new_session()
    # Force expired by backdating both created_at and last_active
    session.created_at = time.time() - 7200  # 2 hours ago
    session.last_active = time.time() - 7200
    store.save(session)
    time.sleep(0.01)
    loaded = store.load(session.session_id)
    assert loaded is None


def test_list_sessions(store):
    s1 = store.new_session()
    s2 = store.new_session()
    sessions = store.list_sessions()
    ids = [s["session_id"] for s in sessions]
    assert s1.session_id in ids
    assert s2.session_id in ids


def test_clear_single(store):
    s = store.new_session()
    count = store.clear(s.session_id)
    assert count == 1
    assert store.load(s.session_id) is None


def test_clear_all(store):
    store.new_session()
    store.new_session()
    count = store.clear()
    assert count == 2
    assert store.list_sessions() == []


def test_purge_expired(tmp_path):
    config = SessionConfig(ttl_hours=1, max_history=10, sessions_dir=str(tmp_path / "s"))
    store = SessionStore(config)
    s = store.new_session()
    # Backdate both created_at and last_active so the session is expired under
    # the activity-based TTL check (max(created_at, last_active) > ttl_hours ago).
    s.created_at = time.time() - 7200
    s.last_active = time.time() - 7200
    store.save(s)
    removed = store.purge_expired()
    assert removed >= 1


def test_session_file_permissions(store, tmp_config):
    """Verify session files are created with mode 0o600 (POSIX only)."""
    import sys
    if sys.platform == "win32":
        pytest.skip("POSIX permissions not applicable on Windows")
    session = store.new_session()
    path = Path(tmp_config.sessions_dir) / f"{session.session_id}.json"
    mode = oct(path.stat().st_mode)[-3:]
    assert mode == "600"


def test_path_traversal_protection(store):
    """Session IDs with traversal chars/special chars are rejected by allowlist."""
    assert store.load("../../etc/passwd") is None
    assert store.load("..\\..\\windows\\system32") is None
    assert store.load("session%2Fpath") is None


def test_valid_session_id_format(store):
    """Valid session IDs (alphanumeric + dash + underscore) work normally."""
    session = store.new_session()
    loaded = store.load(session.session_id)
    assert loaded is not None
    assert loaded.session_id == session.session_id


def test_get_history_returns_copy(store):
    session = store.new_session()
    session.add_turn("a", "b", max_history=10)
    history = session.get_history()
    history.clear()
    assert len(session.messages) == 2


def test_list_sessions_excludes_expired(tmp_path):
    """list_sessions must delete and exclude sessions past TTL."""
    config = SessionConfig(ttl_hours=1, max_history=10, sessions_dir=str(tmp_path / "s"))
    store = SessionStore(config)
    live = store.new_session()
    expired = store.new_session()
    # Backdate expired session beyond TTL (both fields for activity-based expiry)
    expired.created_at = time.time() - 7200
    expired.last_active = time.time() - 7200
    store.save(expired)
    sessions = store.list_sessions()
    ids = [s["session_id"] for s in sessions]
    assert live.session_id in ids
    assert expired.session_id not in ids


def test_list_sessions_corrupt_file_skipped(tmp_path):
    """list_sessions must silently skip corrupt JSON files."""
    config = SessionConfig(ttl_hours=24, max_history=10, sessions_dir=str(tmp_path / "s"))
    store = SessionStore(config)
    live = store.new_session()
    # Write a corrupt JSON file
    corrupt_path = Path(config.sessions_dir) / "corrupt.json"
    corrupt_path.write_text("{invalid json", encoding="utf-8")
    sessions = store.list_sessions()
    ids = [s["session_id"] for s in sessions]
    assert live.session_id in ids
    assert all(s["session_id"] != "corrupt" for s in sessions)
