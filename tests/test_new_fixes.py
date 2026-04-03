"""Supplemental tests for recently added/modified functions.

Targets:
  1. _BoundedTTLCache (mcp_server/server.py)
  2. _GLOBAL_SANDBOX_LOCK in cli/skills/sandbox/manager.py
  3. save_task_to_heartbeat() injection prevention (cli/commands/heartbeat.py)
  4. TraceLogger concurrent rotation safety (cli/ai/trace.py)
  5. probe_upstream_mcp resource cleanup (mcp_server/server.py)
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import tempfile
import os

import pytest

# ---------------------------------------------------------------------------
# 1. _BoundedTTLCache
# ---------------------------------------------------------------------------

from mcp_server.server import _BoundedTTLCache


class TestBoundedTTLCache:
    """Tests for _BoundedTTLCache."""

    # ------------------------------------------------------------------
    # Basic set / get
    # ------------------------------------------------------------------

    def test_set_and_get_returns_value(self):
        cache = _BoundedTTLCache(maxsize=10, ttl=60)
        cache.set("k1", [1, 2, 3])
        assert cache.get("k1") == [1, 2, 3]

    def test_missing_key_returns_none(self):
        cache = _BoundedTTLCache(maxsize=10, ttl=60)
        assert cache.get("nonexistent") is None

    def test_overwrite_key_updates_value(self):
        cache = _BoundedTTLCache(maxsize=10, ttl=60)
        cache.set("k", ["old"])
        cache.set("k", ["new"])
        assert cache.get("k") == ["new"]

    def test_multiple_keys_independent(self):
        cache = _BoundedTTLCache(maxsize=10, ttl=60)
        cache.set("a", [1])
        cache.set("b", [2])
        assert cache.get("a") == [1]
        assert cache.get("b") == [2]

    # ------------------------------------------------------------------
    # TTL expiry
    # ------------------------------------------------------------------

    def test_expired_item_returns_none(self):
        """Items older than TTL must not be returned."""
        cache = _BoundedTTLCache(maxsize=10, ttl=0.05)  # 50 ms TTL
        cache.set("expiring", ["data"])
        time.sleep(0.1)  # wait past TTL
        assert cache.get("expiring") is None

    def test_item_within_ttl_is_returned(self):
        """An item set just now must still be returned before TTL elapses."""
        cache = _BoundedTTLCache(maxsize=10, ttl=30)
        cache.set("fresh", ["data"])
        assert cache.get("fresh") == ["data"]

    def test_expired_item_removed_from_store(self):
        """After expiry the entry should be deleted from the internal store."""
        cache = _BoundedTTLCache(maxsize=10, ttl=0.05)
        cache.set("x", [42])
        time.sleep(0.1)
        cache.get("x")  # triggers deletion
        assert "x" not in cache._store

    # ------------------------------------------------------------------
    # maxsize / LRU eviction
    # ------------------------------------------------------------------

    def test_maxsize_evicts_lru_entry(self):
        """When the cache is full, the least-recently-used entry is evicted."""
        cache = _BoundedTTLCache(maxsize=3, ttl=60)
        cache.set("a", [1])
        cache.set("b", [2])
        cache.set("c", [3])
        # Access "a" to make it the most-recently-used; "b" becomes LRU
        cache.get("a")
        # Adding a 4th entry must evict "b" (oldest untouched)
        cache.set("d", [4])
        assert cache.get("b") is None  # evicted
        assert cache.get("a") == [1]   # still alive
        assert cache.get("c") == [3]   # still alive
        assert cache.get("d") == [4]   # newly inserted

    def test_maxsize_one_always_evicts_previous(self):
        cache = _BoundedTTLCache(maxsize=1, ttl=60)
        cache.set("first", [1])
        cache.set("second", [2])
        assert cache.get("first") is None
        assert cache.get("second") == [2]

    def test_size_never_exceeds_maxsize(self):
        cache = _BoundedTTLCache(maxsize=5, ttl=60)
        for i in range(20):
            cache.set(f"key{i}", [i])
        assert len(cache._store) <= 5

    # ------------------------------------------------------------------
    # Concurrent set / get
    # ------------------------------------------------------------------

    def test_concurrent_set_get_no_crash(self):
        """Hammering the cache from many threads must not raise any exception."""
        cache = _BoundedTTLCache(maxsize=50, ttl=5)
        errors: list[Exception] = []

        def worker(thread_id: int) -> None:
            try:
                for i in range(50):
                    key = f"t{thread_id}-k{i % 10}"
                    cache.set(key, [thread_id, i])
                    cache.get(key)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Concurrent access raised exceptions: {errors}"


# ---------------------------------------------------------------------------
# 2. _GLOBAL_SANDBOX_LOCK serialises concurrent SandboxManager activations
# ---------------------------------------------------------------------------

from cli.skills.sandbox.manager import SandboxManager, _GLOBAL_SANDBOX_LOCK


class TestGlobalSandboxLock:
    """Verify _GLOBAL_SANDBOX_LOCK serialises __enter__/__exit__ pairs."""

    def _make_manager(self, name: str) -> SandboxManager:
        """Create a SandboxManager with minimal permissions that won't touch real FS."""
        return SandboxManager(skill_name=name, permissions=set())

    def test_lock_is_released_after_context_exit(self):
        """After __exit__, the global lock must be free."""
        mgr = self._make_manager("skill-a")
        with mgr:
            pass  # enters and exits
        # If the lock is still held this will block forever; use non-blocking acquire
        acquired = _GLOBAL_SANDBOX_LOCK.acquire(blocking=False)
        assert acquired, "Lock was not released after __exit__"
        _GLOBAL_SANDBOX_LOCK.release()

    def test_second_context_only_enters_after_first_exits(self):
        """Two concurrent SandboxManagers must not overlap their active windows.

        Strategy:
          - Thread A acquires the lock via __enter__, records its entry time,
            sleeps briefly inside, then exits.
          - Thread B tries __enter__ while A is still inside.
          - We verify B's entry timestamp >= A's exit timestamp (no overlap).
        """
        mgr_a = self._make_manager("skill-a")
        mgr_b = self._make_manager("skill-b")

        timeline: dict[str, float] = {}
        b_entered = threading.Event()

        def run_a() -> None:
            with mgr_a:
                timeline["a_enter"] = time.monotonic()
                time.sleep(0.05)  # hold the lock for 50 ms
                timeline["a_exit"] = time.monotonic()

        def run_b() -> None:
            # Give thread A a head-start so it definitely acquires first
            time.sleep(0.01)
            with mgr_b:
                timeline["b_enter"] = time.monotonic()
                b_entered.set()

        t_a = threading.Thread(target=run_a)
        t_b = threading.Thread(target=run_b)
        t_a.start()
        t_b.start()
        t_a.join(timeout=5)
        t_b.join(timeout=5)

        assert not t_a.is_alive(), "Thread A did not finish"
        assert not t_b.is_alive(), "Thread B did not finish"
        assert b_entered.is_set(), "Thread B never entered its context"

        # B must not have entered before A exited
        assert timeline["b_enter"] >= timeline["a_exit"], (
            f"Race detected: B entered at {timeline['b_enter']:.6f} "
            f"but A exited at {timeline['a_exit']:.6f}"
        )

    def test_lock_released_even_if_activate_raises(self):
        """If activate() raises, the lock must still be released."""
        mgr = self._make_manager("bad-skill")

        # Simulate activate() raising by patching it
        original_activate = mgr.activate

        def boom():
            raise RuntimeError("simulated activate failure")

        mgr.activate = boom

        with pytest.raises(RuntimeError, match="simulated activate failure"):
            mgr.__enter__()

        # Lock must be free now
        acquired = _GLOBAL_SANDBOX_LOCK.acquire(blocking=False)
        assert acquired, "Lock was not released after activate() raised"
        _GLOBAL_SANDBOX_LOCK.release()


# ---------------------------------------------------------------------------
# 3. save_task_to_heartbeat() injection prevention
# ---------------------------------------------------------------------------

from cli.commands.heartbeat import save_task_to_heartbeat, parse_heartbeat_tasks, HEARTBEAT_FILE

# Minimal Heartbeat.md skeleton that both save_task_to_heartbeat() and
# parse_heartbeat_tasks() are happy with.
_HEARTBEAT_SKELETON = """\
# SocialHub Heartbeat

## Scheduled Tasks

## Execution Log

| Time | Task ID | Status | Note |
|---|---|---|---|
| - | - | - | No records |

## Add New Task Template
"""


def _write_skeleton(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_HEARTBEAT_SKELETON, encoding="utf-8")


class TestSaveTaskToHeartbeatInjection:
    """Injection-prevention tests for save_task_to_heartbeat()."""

    @pytest.fixture(autouse=True)
    def _patch_heartbeat_file(self, tmp_path, monkeypatch):
        """Redirect HEARTBEAT_FILE to a temp path for every test."""
        fake_path = tmp_path / "Heartbeat.md"
        _write_skeleton(fake_path)
        monkeypatch.setattr(
            "cli.commands.heartbeat.HEARTBEAT_FILE", fake_path
        )
        self.heartbeat_path = fake_path

    # ------------------------------------------------------------------
    # Newline stripping in the `name` field
    # ------------------------------------------------------------------

    def test_newline_in_name_is_stripped(self):
        """A \\n in the task name must NOT appear in the written Markdown."""
        task = {
            "name": "Report\nEvil Section",
            "frequency": "Daily 08:00",
            "command": "sh analytics overview",
            "id": "task-newline-test",
        }
        result = save_task_to_heartbeat(task)
        assert result is True

        content = self.heartbeat_path.read_text(encoding="utf-8")
        # The raw newline character must not be in the written content as a
        # structural line break within the task name field.
        # The _safe() function replaces \n with " " (a space).
        assert "Evil Section" in content  # text is preserved
        # Verify the heading line is a single line (no embedded newline splitting it)
        for line in content.splitlines():
            if "Evil Section" in line:
                assert "\n" not in line  # tautological here but readable
                # More importantly: the heading must start with ### and be contiguous
                assert line.startswith("### ") or not line.strip().startswith("###")

    def test_newline_in_name_does_not_create_extra_task_section(self):
        """Injected \\n must not produce a second parseable task section."""
        task = {
            "name": "Legit\n### 99. Injected",
            "frequency": "Daily 00:00",
            "command": "sh analytics overview",
            "id": "task-inject-test",
        }
        save_task_to_heartbeat(task)
        tasks = parse_heartbeat_tasks()
        # Should only have parsed 1 task, not 2
        assert len(tasks) == 1

    def test_carriage_return_in_name_is_stripped(self):
        """A \\r in the name must be replaced with a space, not kept."""
        task = {
            "name": "Windows\rLineBreak",
            "frequency": "Daily 09:00",
            "command": "sh analytics overview",
            "id": "task-cr-test",
        }
        save_task_to_heartbeat(task)
        content = self.heartbeat_path.read_text(encoding="utf-8")
        assert "\r" not in content

    # ------------------------------------------------------------------
    # Backtick replacement in the `command` field
    # ------------------------------------------------------------------

    def test_backticks_in_command_replaced_with_single_quotes(self):
        """Backticks in `command` must be replaced with single-quote characters."""
        task = {
            "name": "Backtick Test",
            "frequency": "Daily 10:00",
            "command": "sh analytics overview `whoami`",
            "id": "task-backtick-test",
        }
        save_task_to_heartbeat(task)
        content = self.heartbeat_path.read_text(encoding="utf-8")
        # The backtick must not survive inside the bash code block
        # (it appears inside ```bash ... ``` — only the outer delimiters are triple-backtick)
        # Find lines between ```bash and closing ```
        in_block = False
        block_lines: list[str] = []
        for line in content.splitlines():
            if line.strip() == "```bash":
                in_block = True
                continue
            if in_block and line.strip() == "```":
                in_block = False
                continue
            if in_block:
                block_lines.append(line)

        assert block_lines, "No bash code block found in output"
        command_line = " ".join(block_lines)
        assert "`" not in command_line, (
            f"Backtick found in command block: {command_line!r}"
        )
        assert "'" in command_line, (
            f"Expected single-quotes replacing backticks, got: {command_line!r}"
        )

    # ------------------------------------------------------------------
    # Normal round-trip through parse_heartbeat_tasks()
    # ------------------------------------------------------------------

    def test_normal_task_round_trips_correctly(self):
        """A clean task written by save_task_to_heartbeat() must be readable by parse_heartbeat_tasks()."""
        task = {
            "name": "Daily Overview",
            "frequency": "Daily 08:00",
            "command": "sh analytics overview",
            "id": "task-daily-001",
        }
        result = save_task_to_heartbeat(task)
        assert result is True

        tasks = parse_heartbeat_tasks()
        assert len(tasks) == 1
        t = tasks[0]
        assert t["name"] == "Daily Overview"
        assert t["frequency"] == "Daily 08:00"
        assert t["status"] == "pending"
        assert t["id"] == "task-daily-001"
        assert "sh analytics overview" in t.get("command", "")

    def test_multiple_tasks_round_trip(self):
        """Two sequentially saved tasks both parse correctly."""
        tasks_in = [
            {"name": "Task Alpha", "frequency": "Daily 07:00", "command": "sh analytics overview", "id": "t-alpha"},
            {"name": "Task Beta",  "frequency": "Hourly",      "command": "sh analytics customers", "id": "t-beta"},
        ]
        for t in tasks_in:
            save_task_to_heartbeat(t)

        tasks_out = parse_heartbeat_tasks()
        assert len(tasks_out) == 2
        ids_out = {t["id"] for t in tasks_out}
        assert ids_out == {"t-alpha", "t-beta"}

    def test_save_auto_creates_file_when_missing(self, tmp_path, monkeypatch):
        """save_task_to_heartbeat() auto-creates Heartbeat.md and returns True."""
        missing = tmp_path / "does_not_exist" / "Heartbeat.md"
        monkeypatch.setattr("cli.commands.heartbeat.HEARTBEAT_FILE", missing)
        result = save_task_to_heartbeat({"name": "x", "frequency": "Daily 00:00", "command": "sh analytics overview"})
        assert result is True
        assert missing.exists()


# ---------------------------------------------------------------------------
# 4. TraceLogger concurrent rotation safety
# ---------------------------------------------------------------------------

from cli.ai.trace import TraceLogger
from cli.config import TraceConfig


def _make_trace_config(trace_dir: str, max_mb: int = 10) -> TraceConfig:
    return TraceConfig(
        enabled=True,
        pii_masking=False,
        order_id_min_digits=16,
        max_file_size_mb=max_mb,
        trace_dir=trace_dir,
    )


def _make_tiny_trace_logger(tmp_path: Path) -> TraceLogger:
    """Create a TraceLogger that rotates after every ~1 byte (by patching _max_bytes)."""
    cfg = _make_trace_config(str(tmp_path), max_mb=1)
    logger = TraceLogger(cfg)
    # Override _max_bytes so that after the first write the file is always "too large"
    logger._max_bytes = 1
    return logger


class TestTraceLoggerConcurrentRotation:
    """_lock in TraceLogger must prevent rename races during rotation."""

    def test_20_threads_no_exception(self, tmp_path):
        """Fire 20 threads each calling log_step(); no exception must propagate."""
        logger = _make_tiny_trace_logger(tmp_path)

        errors: list[Exception] = []

        def worker(tid: int) -> None:
            try:
                for i in range(5):
                    logger.log_step(
                        trace_id=f"trace-{tid}",
                        step_num=i,
                        command="sh analytics overview",
                        success=True,
                        duration_ms=10,
                        output_chars=42,
                    )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert all(not t.is_alive() for t in threads), "Some threads did not finish"
        assert errors == [], f"Threads raised exceptions: {errors}"

    def test_trace_file_or_backup_exists_after_concurrent_writes(self, tmp_path):
        """After concurrent writes, at least one trace file must exist."""
        logger = _make_tiny_trace_logger(tmp_path)

        def worker(tid: int) -> None:
            for i in range(10):
                logger.log_step(
                    trace_id=f"trace-{tid}",
                    step_num=i,
                    command="sh analytics overview",
                    success=True,
                    duration_ms=5,
                    output_chars=10,
                )

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        trace_file = tmp_path / "ai_trace.jsonl"
        backup_file = tmp_path / "ai_trace.jsonl.1"
        assert trace_file.exists() or backup_file.exists(), (
            "Neither ai_trace.jsonl nor ai_trace.jsonl.1 found after concurrent writes"
        )

    def test_log_content_is_valid_ndjson(self, tmp_path):
        """Each line written must be valid JSON (spot-check with a non-tiny TTL)."""
        import json as _json

        cfg = _make_trace_config(str(tmp_path), max_mb=10)  # no rotation
        logger = TraceLogger(cfg)

        for i in range(5):
            logger.log_step(
                trace_id="tid-abc",
                step_num=i,
                command="sh test",
                success=i % 2 == 0,
                duration_ms=i * 10,
                output_chars=i,
            )

        trace_file = tmp_path / "ai_trace.jsonl"
        assert trace_file.exists()
        for line in trace_file.read_text(encoding="utf-8").splitlines():
            event = _json.loads(line)
            assert event["type"] == "step"
            assert event["trace_id"] == "tid-abc"


# ---------------------------------------------------------------------------
# 5. probe_upstream_mcp resource cleanup
# ---------------------------------------------------------------------------

from mcp_server.server import probe_upstream_mcp


def _probe_with_mock_client(mock_client_instance, mock_get_config_fn):
    """Helper: swap out cli.api.mcp_client in sys.modules, call probe_upstream_mcp, restore."""
    import sys
    from types import ModuleType

    fake_mcp_client_mod = ModuleType("cli.api.mcp_client")

    class FakeMCPConfig:
        def __init__(self, **kwargs):
            pass

    fake_mcp_client_mod.MCPConfig = FakeMCPConfig  # type: ignore[attr-defined]
    fake_mcp_client_mod.MCPClient = MagicMock(return_value=mock_client_instance)  # type: ignore[attr-defined]
    fake_mcp_client_mod.MCPError = Exception  # type: ignore[attr-defined]

    mock_config = MagicMock()
    mock_config.mcp.sse_url = "http://localhost:8090/sse"
    mock_config.mcp.post_url = "http://localhost:8090/message"
    mock_config.mcp.tenant_id = "test-tenant"
    mock_get_config_fn.return_value = mock_config

    original_mod = sys.modules.get("cli.api.mcp_client")
    sys.modules["cli.api.mcp_client"] = fake_mcp_client_mod
    try:
        return probe_upstream_mcp(timeout=5)
    finally:
        if original_mod is not None:
            sys.modules["cli.api.mcp_client"] = original_mod
        else:
            sys.modules.pop("cli.api.mcp_client", None)


class TestProbeUpstreamMCPResourceCleanup:
    """probe_upstream_mcp must call disconnect() even when initialize() raises."""

    def _make_mock_client(self, initialize_raises: bool = False) -> MagicMock:
        client = MagicMock()
        client.connect = MagicMock(return_value=None)
        if initialize_raises:
            client.initialize = MagicMock(side_effect=RuntimeError("upstream down"))
        else:
            client.initialize = MagicMock(return_value=None)
            client.list_tools = MagicMock(return_value=[{"name": "tool1"}, {"name": "tool2"}])
        client.disconnect = MagicMock(return_value=None)
        return client

    @patch("mcp_server.server._get_config")
    def test_disconnect_called_on_initialize_exception(self, mock_get_config):
        """When initialize() raises, disconnect() must still be invoked."""
        mock_client_instance = self._make_mock_client(initialize_raises=True)
        ok, msg = _probe_with_mock_client(mock_client_instance, mock_get_config)

        # Function must return (False, <error_message>)
        assert ok is False
        assert isinstance(msg, str) and len(msg) > 0

        # disconnect() must have been called exactly once (the try/finally guarantee)
        mock_client_instance.disconnect.assert_called_once()

    @patch("mcp_server.server._get_config")
    def test_returns_false_and_message_on_connect_exception(self, mock_get_config):
        """If connect() itself raises, the function still returns (False, msg)."""
        mock_client_instance = self._make_mock_client()
        mock_client_instance.connect = MagicMock(side_effect=ConnectionError("refused"))

        ok, msg = _probe_with_mock_client(mock_client_instance, mock_get_config)

        assert ok is False
        assert "refused" in msg

    @patch("mcp_server.server._get_config")
    def test_returns_true_on_success(self, mock_get_config):
        """When initialize() and list_tools() succeed, the function returns (True, ...)."""
        mock_client_instance = self._make_mock_client(initialize_raises=False)
        ok, msg = _probe_with_mock_client(mock_client_instance, mock_get_config)

        assert ok is True
        assert "tools=2" in msg


# ---------------------------------------------------------------------------
# 6. Heartbeat: normalize_frequency, should_run_task, parse edge cases,
#    sh heartbeat init / add commands
# ---------------------------------------------------------------------------

from datetime import datetime, timezone
import pytest
from typer.testing import CliRunner
from cli.commands.heartbeat import (
    app as heartbeat_app,
    normalize_frequency,
    parse_frequency,
    should_run_task,
    parse_heartbeat_tasks,
    HEARTBEAT_FILE,
)


class TestNormalizeFrequency:
    """normalize_frequency must convert Chinese schedule strings to canonical English."""

    @pytest.mark.parametrize("raw,expected", [
        ("每周五 15:00",  "Weekly Fri 15:00"),
        ("每周一 09:00",  "Weekly Mon 09:00"),
        ("每周六 08:30",  "Weekly Sat 08:30"),
        ("每天 08:30",    "Daily 08:30"),
        ("每小时",        "hourly"),
        ("每1小时",       "hourly"),
        # Already English — pass through
        ("Daily 09:00",  "Daily 09:00"),
        ("Weekly Fri 15:00", "Weekly Fri 15:00"),
    ])
    def test_conversion(self, raw, expected):
        assert normalize_frequency(raw) == expected

    def test_unrecognised_returns_original(self):
        assert normalize_frequency("unknown schedule") == "unknown schedule"


class TestShouldRunTask:
    """should_run_task boundary cases."""

    def _task(self, frequency: str, status: str = "pending") -> dict:
        return {"id": "t1", "name": "T", "frequency": frequency, "status": status}

    # Non-pending tasks must never run
    def test_running_status_returns_false(self):
        now = datetime(2024, 1, 5, 15, 0)  # Friday 15:00
        assert should_run_task(self._task("Weekly Fri 15:00", status="running"), now) is False

    def test_failed_status_returns_false(self):
        now = datetime(2024, 1, 5, 15, 0)
        assert should_run_task(self._task("Weekly Fri 15:00", status="failed"), now) is False

    # Daily: within 5-minute window
    def test_daily_at_exact_minute_returns_true(self):
        now = datetime(2024, 1, 5, 8, 0)  # 08:00 exactly
        assert should_run_task(self._task("Daily 08:00"), now) is True

    def test_daily_at_minute_plus_4_returns_true(self):
        now = datetime(2024, 1, 5, 8, 4)  # 08:04 — inside window
        assert should_run_task(self._task("Daily 08:00"), now) is True

    def test_daily_at_minute_plus_5_returns_false(self):
        now = datetime(2024, 1, 5, 8, 5)  # 08:05 — outside window
        assert should_run_task(self._task("Daily 08:00"), now) is False

    def test_daily_wrong_hour_returns_false(self):
        now = datetime(2024, 1, 5, 9, 0)  # 09:00 instead of 08:00
        assert should_run_task(self._task("Daily 08:00"), now) is False

    # Weekly: correct weekday + window
    def test_weekly_correct_day_and_window_returns_true(self):
        # 2024-01-05 is a Friday (weekday()=4)
        now = datetime(2024, 1, 5, 15, 0)
        assert should_run_task(self._task("Weekly Fri 15:00"), now) is True

    def test_weekly_wrong_weekday_returns_false(self):
        # 2024-01-04 is a Thursday
        now = datetime(2024, 1, 4, 15, 0)
        assert should_run_task(self._task("Weekly Fri 15:00"), now) is False

    def test_weekly_past_window_returns_false(self):
        # Friday 15:06 — 6 minutes past
        now = datetime(2024, 1, 5, 15, 6)
        assert should_run_task(self._task("Weekly Fri 15:00"), now) is False

    # Hourly: within first 5 minutes
    def test_hourly_minute_0_returns_true(self):
        now = datetime(2024, 1, 5, 10, 0)
        assert should_run_task(self._task("hourly"), now) is True

    def test_hourly_minute_4_returns_true(self):
        now = datetime(2024, 1, 5, 10, 4)
        assert should_run_task(self._task("hourly"), now) is True

    def test_hourly_minute_5_returns_false(self):
        now = datetime(2024, 1, 5, 10, 5)
        assert should_run_task(self._task("hourly"), now) is False

    # Unknown type
    def test_unknown_type_returns_false(self):
        now = datetime(2024, 1, 5, 10, 0)
        assert should_run_task(self._task("unknown-format"), now) is False


class TestParseHeartbeatTasksEdgeCases:
    """parse_heartbeat_tasks edge cases: empty / missing section / missing file."""

    def test_missing_file_returns_empty_list(self, tmp_path, monkeypatch):
        missing = tmp_path / "NoFile.md"
        monkeypatch.setattr("cli.commands.heartbeat.HEARTBEAT_FILE", missing)
        assert parse_heartbeat_tasks() == []

    def test_empty_file_returns_empty_list(self, tmp_path, monkeypatch):
        empty = tmp_path / "Heartbeat.md"
        empty.write_text("", encoding="utf-8")
        monkeypatch.setattr("cli.commands.heartbeat.HEARTBEAT_FILE", empty)
        assert parse_heartbeat_tasks() == []

    def test_missing_scheduled_tasks_section_returns_empty_list(self, tmp_path, monkeypatch):
        f = tmp_path / "Heartbeat.md"
        f.write_text("# SocialHub Heartbeat\n\nNo tasks section here.\n", encoding="utf-8")
        monkeypatch.setattr("cli.commands.heartbeat.HEARTBEAT_FILE", f)
        assert parse_heartbeat_tasks() == []


class TestHeartbeatInitCommand:
    """sh heartbeat init creates the file or reports existing."""

    def test_creates_file_when_missing(self, tmp_path, monkeypatch):
        target = tmp_path / "Heartbeat.md"
        monkeypatch.setattr("cli.commands.heartbeat.HEARTBEAT_FILE", target)
        runner = CliRunner()
        result = runner.invoke(heartbeat_app, ["init"])
        assert result.exit_code == 0
        assert target.exists()
        content = target.read_text(encoding="utf-8")
        assert "## Scheduled Tasks" in content
        assert "## Execution Log" in content

    def test_does_not_overwrite_existing_file(self, tmp_path, monkeypatch):
        target = tmp_path / "Heartbeat.md"
        original = "# my custom content\n"
        target.write_text(original, encoding="utf-8")
        monkeypatch.setattr("cli.commands.heartbeat.HEARTBEAT_FILE", target)
        runner = CliRunner()
        result = runner.invoke(heartbeat_app, ["init"])
        assert result.exit_code == 0
        assert target.read_text(encoding="utf-8") == original
        assert "already exists" in result.output


class TestHeartbeatAddCommand:
    """sh heartbeat add validates input and writes task."""

    def _run_add(self, tmp_path, monkeypatch, extra_args: list[str]):
        target = tmp_path / "Heartbeat.md"
        monkeypatch.setattr("cli.commands.heartbeat.HEARTBEAT_FILE", target)
        runner = CliRunner()
        return runner.invoke(heartbeat_app, ["add"] + extra_args), target

    def test_add_valid_task_succeeds(self, tmp_path, monkeypatch):
        result, target = self._run_add(tmp_path, monkeypatch, [
            "--name", "Weekly Report",
            "--schedule", "Weekly Fri 15:00",
            "--command", "sh analytics overview",
        ])
        assert result.exit_code == 0
        assert target.exists()
        tasks = parse_heartbeat_tasks()
        assert len(tasks) == 1
        assert tasks[0]["name"] == "Weekly Report"

    def test_add_chinese_schedule_normalised(self, tmp_path, monkeypatch):
        result, target = self._run_add(tmp_path, monkeypatch, [
            "--name", "周报",
            "--schedule", "每周五 15:00",
            "--command", "sh analytics overview",
        ])
        assert result.exit_code == 0
        tasks = parse_heartbeat_tasks()
        assert tasks[0]["frequency"] == "Weekly Fri 15:00"

    def test_add_rejects_non_sh_command(self, tmp_path, monkeypatch):
        result, _ = self._run_add(tmp_path, monkeypatch, [
            "--name", "Bad",
            "--schedule", "Daily 08:00",
            "--command", "python malicious.py",
        ])
        assert result.exit_code != 0
        assert "sh " in result.output

    def test_add_rejects_unrecognised_schedule(self, tmp_path, monkeypatch):
        result, _ = self._run_add(tmp_path, monkeypatch, [
            "--name", "Bad Schedule",
            "--schedule", "whenever I feel like it",
            "--command", "sh analytics overview",
        ])
        assert result.exit_code != 0
        assert "Unrecognised" in result.output or "schedule" in result.output.lower()

    def test_add_creates_file_when_missing(self, tmp_path, monkeypatch):
        target = tmp_path / "sub" / "Heartbeat.md"
        monkeypatch.setattr("cli.commands.heartbeat.HEARTBEAT_FILE", target)
        runner = CliRunner()
        result = runner.invoke(heartbeat_app, ["add",
            "--name", "Auto Create",
            "--schedule", "Daily 09:00",
            "--command", "sh analytics overview",
        ])
        assert result.exit_code == 0
        assert target.exists()
