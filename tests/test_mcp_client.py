"""Tests for cli.api.mcp_client — MCPClient and MCPError."""

import queue
import threading
import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

from cli.api.mcp_client import MCPClient, MCPConfig, MCPError


# ---------------------------------------------------------------------------
# MCPError
# ---------------------------------------------------------------------------

class TestMCPError:
    def test_is_exception_subclass(self):
        """MCPError must be a proper Exception subclass."""
        assert issubclass(MCPError, Exception)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(MCPError, match="something went wrong"):
            raise MCPError("something went wrong")

    def test_message_is_preserved(self):
        err = MCPError("detail message")
        assert str(err) == "detail message"


# ---------------------------------------------------------------------------
# MCPConfig / constructor validation
# ---------------------------------------------------------------------------

class TestMCPConfigValidation:
    def test_validate_config_missing_all_fields(self):
        """_validate_config raises MCPError when sse_url, post_url, tenant_id are empty."""
        client = MCPClient(MCPConfig())  # all fields default to ""
        with pytest.raises(MCPError) as exc_info:
            client._validate_config()
        msg = str(exc_info.value)
        assert "sse_url" in msg
        assert "post_url" in msg
        assert "tenant_id" in msg

    def test_validate_config_missing_sse_url(self):
        cfg = MCPConfig(post_url="http://post", tenant_id="t1")
        client = MCPClient(cfg)
        with pytest.raises(MCPError) as exc_info:
            client._validate_config()
        assert "sse_url" in str(exc_info.value)

    def test_validate_config_missing_post_url(self):
        cfg = MCPConfig(sse_url="http://sse", tenant_id="t1")
        client = MCPClient(cfg)
        with pytest.raises(MCPError) as exc_info:
            client._validate_config()
        assert "post_url" in str(exc_info.value)

    def test_validate_config_missing_tenant_id(self):
        cfg = MCPConfig(sse_url="http://sse", post_url="http://post")
        client = MCPClient(cfg)
        with pytest.raises(MCPError) as exc_info:
            client._validate_config()
        assert "tenant_id" in str(exc_info.value)

    def test_validate_config_all_fields_present(self):
        """_validate_config must not raise when all required fields are provided."""
        cfg = MCPConfig(sse_url="http://sse", post_url="http://post", tenant_id="t1")
        client = MCPClient(cfg)
        # Should not raise
        client._validate_config()


# ---------------------------------------------------------------------------
# Helper: build a connected MCPClient with a mocked POST
# ---------------------------------------------------------------------------

def _make_client(sse_alive: bool, queue_data=None, timeout: int = 2) -> MCPClient:
    """
    Return an MCPClient that:
    - Has a valid config (no real network calls).
    - Has _connected = True and _session_id set.
    - Has _sse_thread replaced with a mock whose is_alive() is controlled.
    - Has httpx.post patched to return HTTP 202 (accepted; response comes via SSE).
    The caller controls whether the response queue ever gets data.
    """
    cfg = MCPConfig(
        sse_url="http://sse.example.com",
        post_url="http://post.example.com",
        tenant_id="test-tenant",
        timeout=timeout,
    )
    client = MCPClient(cfg)
    client._connected = True
    client._session_id = "sess-0001"

    # Mock SSE thread
    mock_thread = MagicMock(spec=threading.Thread)
    mock_thread.is_alive.return_value = sse_alive
    client._sse_thread = mock_thread

    # If caller wants to pre-fill a response, wire it up via a side-effect on
    # httpx.post that also places the message in the right response queue.
    if queue_data is not None:
        original_post = httpx.post

        def _fake_post(url, **kwargs):
            # After the POST is "sent", put the response into the waiting queue.
            # The request_id is embedded in the JSON body.
            body = kwargs.get("json", {})
            req_id = body.get("id")
            if req_id and req_id in client._responses:
                client._responses[req_id].put(queue_data)
            resp = MagicMock(spec=httpx.Response)
            resp.status_code = 202
            return resp

        return client, _fake_post

    return client, None


# ---------------------------------------------------------------------------
# _send_request: fast-fail when SSE thread dies
# ---------------------------------------------------------------------------

class TestSendRequestSSEFastFail:
    def test_raises_mcp_error_when_sse_thread_dead(self):
        """_send_request must raise MCPError quickly when _sse_thread.is_alive() is False."""
        client, _ = _make_client(sse_alive=False, timeout=30)

        # Patch httpx.post to return HTTP 202 (no real network call)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 202

        start = time.monotonic()
        with patch("cli.api.mcp_client.httpx.post", return_value=mock_response):
            with pytest.raises(MCPError) as exc_info:
                client._send_request("tools/list", {})

        elapsed = time.monotonic() - start
        # Should fail fast — well under the 30-second timeout
        assert elapsed < 5.0, f"Fast-fail took too long: {elapsed:.2f}s"
        assert "SSE connection lost" in str(exc_info.value)

    def test_sse_dead_error_message(self):
        """Verify the exact error message fragment for SSE-dead scenario."""
        client, _ = _make_client(sse_alive=False, timeout=5)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 202

        with patch("cli.api.mcp_client.httpx.post", return_value=mock_response):
            with pytest.raises(MCPError, match="SSE connection lost"):
                client._send_request("initialize", {})


# ---------------------------------------------------------------------------
# _send_request: timeout when SSE is alive but queue never gets data
# ---------------------------------------------------------------------------

class TestSendRequestTimeout:
    def test_raises_mcp_error_on_timeout(self):
        """_send_request must raise MCPError with 'timed out' after the deadline passes."""
        # Use a very short timeout (1 s) so the test stays fast
        client, _ = _make_client(sse_alive=True, timeout=1)

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 202

        start = time.monotonic()
        with patch("cli.api.mcp_client.httpx.post", return_value=mock_response):
            with pytest.raises(MCPError) as exc_info:
                client._send_request("tools/list", {}, timeout=1)

        elapsed = time.monotonic() - start
        # Must not take much longer than the configured timeout
        assert elapsed < 5.0, f"Timeout test took unexpectedly long: {elapsed:.2f}s"
        assert "timed out" in str(exc_info.value)

    def test_timeout_error_includes_duration(self):
        """The timeout error message must mention the timeout value."""
        client, _ = _make_client(sse_alive=True, timeout=1)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 202

        with patch("cli.api.mcp_client.httpx.post", return_value=mock_response):
            with pytest.raises(MCPError, match=r"1s"):
                client._send_request("tools/list", {}, timeout=1)


# ---------------------------------------------------------------------------
# _send_request: successful response
# ---------------------------------------------------------------------------

class TestSendRequestSuccess:
    def test_returns_response_when_queue_delivers(self):
        """_send_request returns the dict placed on the response queue."""
        cfg = MCPConfig(
            sse_url="http://sse.example.com",
            post_url="http://post.example.com",
            tenant_id="test-tenant",
            timeout=5,
        )
        client = MCPClient(cfg)
        client._connected = True
        client._session_id = "sess-0002"

        mock_thread = MagicMock(spec=threading.Thread)
        mock_thread.is_alive.return_value = True
        client._sse_thread = mock_thread

        expected_result = {"jsonrpc": "2.0", "id": None, "result": {"tools": []}}

        def _fake_post(url, **kwargs):
            body = kwargs.get("json", {})
            req_id = body.get("id")
            # Simulate SSE message arriving shortly after POST
            def _deliver():
                time.sleep(0.05)
                if req_id and req_id in client._responses:
                    msg = dict(expected_result)
                    msg["id"] = req_id
                    client._responses[req_id].put(msg)
            t = threading.Thread(target=_deliver, daemon=True)
            t.start()

            resp = MagicMock(spec=httpx.Response)
            resp.status_code = 202
            return resp

        with patch("cli.api.mcp_client.httpx.post", side_effect=_fake_post):
            result = client._send_request("tools/list", {}, timeout=5)

        assert "result" in result
        assert result["result"] == {"tools": []}
