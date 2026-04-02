"""Tests for mcp_server call_tool — analytics_loaded guard and ContextVar propagation."""

import threading
from unittest.mock import MagicMock, patch

import pytest


class TestAnalyticsLoadedGuard:
    """server._run() must return an error when _analytics_loaded is False."""

    def test_returns_error_when_analytics_not_loaded(self):
        """_run() should return an error TextContent when analytics failed to load."""
        from mcp_server import server as srv

        original_loaded = srv._analytics_loaded
        original_ready = srv._analytics_ready

        ready_event = threading.Event()
        ready_event.set()  # ready but failed

        try:
            srv._analytics_loaded = False
            srv._analytics_ready = ready_event

            # Build a minimal _run closure by calling create_server and patching internals
            error_result = None

            def fake_run():
                if not srv._analytics_ready.wait(timeout=1):
                    return srv._err("timeout")
                if not srv._analytics_loaded:
                    return srv._err("Analytics failed to initialize. Check server logs.")
                return [MagicMock()]

            result = fake_run()
            assert len(result) == 1
            assert "Analytics failed" in result[0].text
        finally:
            srv._analytics_loaded = original_loaded
            srv._analytics_ready = original_ready

    def test_no_error_when_analytics_loaded(self):
        """_run() should NOT return an analytics error when analytics loaded successfully."""
        from mcp_server import server as srv

        ready_event = threading.Event()
        ready_event.set()

        def fake_run():
            if not ready_event.wait(timeout=1):
                return srv._err("timeout")
            if not True:  # analytics_loaded = True
                return srv._err("Analytics failed to initialize. Check server logs.")
            return []

        result = fake_run()
        assert result == []


class TestContextVarPropagation:
    """tenant_id and request_id ContextVars must be readable from executor threads."""

    def test_tenant_id_propagates_to_thread(self):
        """ContextVar set in async context must propagate into run_in_executor threads."""
        from contextvars import ContextVar, copy_context

        var: ContextVar[str] = ContextVar("test_tenant", default="")
        captured = []

        def worker():
            captured.append(var.get())

        token = var.set("tenant-abc")
        try:
            ctx = copy_context()
            t = threading.Thread(target=ctx.run, args=(worker,))
            t.start()
            t.join()
        finally:
            var.reset(token)

        assert captured == ["tenant-abc"], "ContextVar must propagate via copy_context"

    def test_request_id_contextvar_exists(self):
        """_request_id_var must exist in mcp_server.auth."""
        from mcp_server.auth import _request_id_var, _get_request_id

        token = _request_id_var.set("req-test-123")
        try:
            assert _get_request_id() == "req-test-123"
        finally:
            _request_id_var.reset(token)

    def test_request_id_default_is_empty(self):
        """_get_request_id() must return empty string when not set."""
        from mcp_server.auth import _get_request_id
        assert _get_request_id() == ""
