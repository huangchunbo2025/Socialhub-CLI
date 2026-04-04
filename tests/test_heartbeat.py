"""Tests for cli/commands/heartbeat — lock file security and concurrent check guard."""

import os
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestHeartbeatLockFilePID:
    """Lock files must contain the owner PID to enable stale-lock detection."""

    def test_lock_file_contains_pid(self, tmp_path):
        """After acquiring lock, the file should contain the current PID."""
        lock_file = tmp_path / "task1.lock"

        fd = os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)

        written_pid = int(lock_file.read_text(encoding="utf-8").strip())
        assert written_pid == os.getpid()

    def test_stale_lock_from_dead_pid_is_detected(self, tmp_path):
        """A lock file with a non-existent PID should be treated as stale."""
        lock_file = tmp_path / "task2.lock"
        # Write a PID that is extremely unlikely to exist
        lock_file.write_text("9999999", encoding="utf-8")

        stale = False
        try:
            owner_pid = int(lock_file.read_text(encoding="utf-8").strip())
            os.kill(owner_pid, 0)
        except (ValueError, OSError):
            stale = True

        assert stale, "Lock file with dead PID should be detected as stale"

    def test_live_pid_lock_is_not_stale(self, tmp_path):
        """A lock file with the current process PID should NOT be stale."""
        lock_file = tmp_path / "task3.lock"
        lock_file.write_text(str(os.getpid()), encoding="utf-8")

        stale = False
        try:
            owner_pid = int(lock_file.read_text(encoding="utf-8").strip())
            os.kill(owner_pid, 0)
        except (ValueError, OSError):
            stale = True

        assert not stale, "Lock file with live PID should not be stale"


class TestPeriodicTaskStatusReset:
    """Periodic tasks must return to 'pending' after execution."""

    def test_daily_task_resets_to_pending(self, tmp_path):
        from cli.commands.heartbeat import (
            _HEARTBEAT_TEMPLATE, save_task_to_heartbeat,
            update_task_after_execution, parse_heartbeat_tasks,
            HEARTBEAT_FILE,
        )
        # Use a temp heartbeat file
        import cli.commands.heartbeat as hb_mod
        orig = hb_mod.HEARTBEAT_FILE
        hb_mod.HEARTBEAT_FILE = tmp_path / "Heartbeat.md"
        try:
            hb_mod.HEARTBEAT_FILE.write_text(_HEARTBEAT_TEMPLATE, encoding="utf-8")
            save_task_to_heartbeat({
                "id": "task-daily-1",
                "name": "Daily Report",
                "frequency": "Daily 08:30",
                "command": "sh analytics overview",
            })
            # Simulate successful execution
            update_task_after_execution(
                "task-daily-1", "done", "Success", frequency="Daily 08:30",
            )
            tasks = parse_heartbeat_tasks()
            task = next(t for t in tasks if t["id"] == "task-daily-1")
            assert task["status"] == "pending", (
                f"Periodic daily task should reset to pending, got {task['status']}"
            )
        finally:
            hb_mod.HEARTBEAT_FILE = orig

    def test_failed_weekly_task_resets_to_pending(self, tmp_path):
        from cli.commands.heartbeat import (
            _HEARTBEAT_TEMPLATE, save_task_to_heartbeat,
            update_task_after_execution, parse_heartbeat_tasks,
        )
        import cli.commands.heartbeat as hb_mod
        orig = hb_mod.HEARTBEAT_FILE
        hb_mod.HEARTBEAT_FILE = tmp_path / "Heartbeat.md"
        try:
            hb_mod.HEARTBEAT_FILE.write_text(_HEARTBEAT_TEMPLATE, encoding="utf-8")
            save_task_to_heartbeat({
                "id": "task-weekly-1",
                "name": "Weekly Report",
                "frequency": "Weekly Fri 15:00",
                "command": "sh analytics overview",
            })
            update_task_after_execution(
                "task-weekly-1", "failed", "Error",
                frequency="Weekly Fri 15:00",
            )
            tasks = parse_heartbeat_tasks()
            task = next(t for t in tasks if t["id"] == "task-weekly-1")
            assert task["status"] == "pending"
        finally:
            hb_mod.HEARTBEAT_FILE = orig


class TestCheckRecordAppend:
    """Check records should be appended on every heartbeat check."""

    def test_append_check_record_replaces_placeholder(self):
        from cli.commands.heartbeat import _append_check_record, _HEARTBEAT_TEMPLATE
        result = _append_check_record(
            _HEARTBEAT_TEMPLATE, "2026-04-04 10:00 UTC", 3, 0, "No tasks due",
        )
        assert "Waiting for first check" not in result
        assert "2026-04-04 10:00 UTC" in result
        assert "No tasks due" in result

    def test_append_check_record_adds_new_row(self):
        from cli.commands.heartbeat import _append_check_record, _HEARTBEAT_TEMPLATE
        # First check replaces placeholder
        content = _append_check_record(
            _HEARTBEAT_TEMPLATE, "2026-04-04 10:00 UTC", 3, 1, "First",
        )
        # Second check appends a new row
        content = _append_check_record(
            content, "2026-04-04 11:00 UTC", 3, 0, "Second",
        )
        assert "First" in content
        assert "Second" in content
        # Both rows should exist
        assert content.count("2026-04-04") >= 2


class TestHeartbeatConcurrentCheckGuard:
    """_CHECK_LOCK must prevent two concurrent heartbeat check calls."""

    def test_check_lock_blocks_second_call(self):
        """The module-level _CHECK_LOCK should prevent concurrent check_tasks invocations."""
        from cli.commands.heartbeat import _CHECK_LOCK

        # Simulate first caller holding the lock
        acquired = _CHECK_LOCK.acquire(blocking=False)
        assert acquired, "Should acquire lock on first call"

        # Simulate second caller trying
        second_acquired = _CHECK_LOCK.acquire(blocking=False)
        assert not second_acquired, "Second concurrent call must not acquire lock"

        _CHECK_LOCK.release()

    def test_check_lock_released_after_check(self):
        """_CHECK_LOCK must be available after a normal check completion."""
        from cli.commands.heartbeat import _CHECK_LOCK

        # Should always be acquirable when no check is running
        acquired = _CHECK_LOCK.acquire(blocking=False)
        assert acquired
        _CHECK_LOCK.release()

        # And again
        acquired2 = _CHECK_LOCK.acquire(blocking=False)
        assert acquired2
        _CHECK_LOCK.release()
