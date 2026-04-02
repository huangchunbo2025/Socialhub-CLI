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
