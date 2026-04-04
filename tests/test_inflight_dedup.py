"""Tests for MCP server _run_with_cache inflight dedup logic."""

import threading
import time


def _reset_cache_state():
    """Reset module-level cache state between tests."""
    from mcp_server.server import (
        _cache, _inflight, _inflight_lock, _inflight_errors, _inflight_errors_lock,
    )
    with _inflight_lock:
        _inflight.clear()
    with _inflight_errors_lock:
        _inflight_errors.clear()
    # Clear the cache by replacing internal store
    with _cache._lock:
        _cache._store.clear()


class TestInflightDedup:
    """Test _run_with_cache concurrent dedup behavior."""

    def setup_method(self):
        _reset_cache_state()

    def teardown_method(self):
        _reset_cache_state()

    def test_single_call_computes_and_caches(self):
        """A single call should compute the result and cache it."""
        from mcp_server.server import _run_with_cache

        call_count = 0
        def compute():
            nonlocal call_count
            call_count += 1
            return [{"text": "result"}]

        result = _run_with_cache("test_tool", {"a": 1}, "tenant1", compute)
        assert result == [{"text": "result"}]
        assert call_count == 1

        # Second call should hit cache, not recompute
        result2 = _run_with_cache("test_tool", {"a": 1}, "tenant1", compute)
        assert result2 == [{"text": "result"}]
        assert call_count == 1  # Still 1 — cache hit

    def test_different_tenants_no_cache_sharing(self):
        """Different tenant_ids should not share cached results."""
        from mcp_server.server import _run_with_cache

        call_count = 0
        def compute():
            nonlocal call_count
            call_count += 1
            return [{"text": f"result-{call_count}"}]

        r1 = _run_with_cache("tool", {}, "tenantA", compute)
        r2 = _run_with_cache("tool", {}, "tenantB", compute)
        assert call_count == 2
        assert r1 != r2

    def test_concurrent_calls_dedup(self):
        """Concurrent identical calls should only compute once (owner/follower)."""
        from mcp_server.server import _run_with_cache

        call_count = 0
        entered = threading.Event()

        def slow_compute():
            nonlocal call_count
            call_count += 1
            entered.set()  # Signal that compute has started
            time.sleep(0.5)  # Simulate slow computation
            return [{"text": "shared-result"}]

        results = [None, None]
        errors = [None, None]

        def run_owner():
            try:
                results[0] = _run_with_cache("tool", {"k": "v"}, "t1", slow_compute)
            except Exception as e:
                errors[0] = e

        def run_follower():
            entered.wait(timeout=5)  # Wait until owner's compute starts
            try:
                results[1] = _run_with_cache("tool", {"k": "v"}, "t1", slow_compute)
            except Exception as e:
                errors[1] = e

        t1 = threading.Thread(target=run_owner)
        t2 = threading.Thread(target=run_follower)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        # Only the owner should have computed; follower waits on inflight event
        assert call_count == 1, f"Expected 1 computation (owner only), got {call_count}"
        assert errors == [None, None], f"Unexpected errors: {errors}"
        # Both should get the same result
        assert results[0] == [{"text": "shared-result"}]
        assert results[1] == [{"text": "shared-result"}]

    def test_owner_failure_propagates_to_follower(self):
        """When owner fails, follower should get the error, not stale data."""
        from mcp_server.server import _run_with_cache
        from cli.api.mcp_client import MCPError

        started = threading.Event()

        def failing_compute():
            started.set()
            time.sleep(0.1)
            raise MCPError("compute failed")

        results = [None, None]
        errors = [None, None]

        def run_owner():
            try:
                results[0] = _run_with_cache("fail_tool", {}, "t1", failing_compute)
            except Exception as e:
                errors[0] = e

        def run_follower():
            started.wait(timeout=5)
            time.sleep(0.05)  # Ensure owner registers first
            try:
                results[1] = _run_with_cache("fail_tool", {}, "t1", failing_compute)
            except Exception as e:
                errors[1] = e

        t1 = threading.Thread(target=run_owner)
        t2 = threading.Thread(target=run_follower)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        # Owner should have raised
        assert errors[0] is not None
        assert "compute failed" in str(errors[0])
        # Follower should also get an error (either propagated or from its own retry)
        assert errors[1] is not None or results[1] is None, (
            f"Follower should not silently succeed: results[1]={results[1]}"
        )
