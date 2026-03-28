"""MCP (Model Context Protocol) client for SocialHub analytics database."""

import json
import logging
import time
import uuid
import threading
import queue
from typing import Any, Optional
from dataclasses import dataclass

import httpx
from rich.console import Console

console = Console(stderr=True)
logger = logging.getLogger(__name__)


@dataclass
class MCPConfig:
    """MCP service configuration.

    SECURITY: No default URLs - must be explicitly configured via:
    1. Config file (~/.socialhub/config.json)
    2. Environment variables (MCP_SSE_URL, MCP_POST_URL, MCP_TENANT_ID)
    """
    sse_url: str = ""  # Required - no hardcoded default
    post_url: str = ""  # Required - no hardcoded default
    tenant_id: str = ""  # Required - no hardcoded default
    timeout: int = 120


class MCPClient:
    """Client for MCP analytics database service."""

    def __init__(self, config: Optional[MCPConfig] = None):
        self.config = config or MCPConfig()
        self._session_id: Optional[str] = None
        self._sse_thread: Optional[threading.Thread] = None
        self._running = False
        self._responses: dict[str, queue.Queue] = {}
        self._tools: list[dict] = []
        self._connected = False
        self._initialized = False
        self._session_ready = threading.Event()
        self._last_error: Optional[str] = None

    def _validate_config(self) -> None:
        """Validate that required configuration is provided.

        Raises MCPError if configuration is missing.
        """
        missing = []
        if not self.config.sse_url:
            missing.append("sse_url (or MCP_SSE_URL env var)")
        if not self.config.post_url:
            missing.append("post_url (or MCP_POST_URL env var)")
        if not self.config.tenant_id:
            missing.append("tenant_id (or MCP_TENANT_ID env var)")

        if missing:
            raise MCPError(
                f"MCP configuration missing: {', '.join(missing)}. "
                "Please configure via 'sh config set mcp.<field>' or environment variables."
            )

    def connect(self, show_status: bool = True) -> bool:
        """Connect to MCP service via SSE."""
        if self._connected:
            return True

        # Validate configuration before attempting connection
        self._validate_config()

        self._running = True
        self._last_error = None
        self._session_ready.clear()
        logger.info(
            "Connecting to upstream MCP via SSE",
            extra={
                "sse_url": self.config.sse_url,
                "post_url": self.config.post_url,
                "tenant_id": self.config.tenant_id,
            },
        )
        self._sse_thread = threading.Thread(target=self._sse_listener, daemon=True)
        self._sse_thread.start()

        # Wait for session ID via event (no busy-wait)
        self._session_ready.wait(timeout=10.0)

        if self._session_id:
            self._connected = True
            logger.info("Upstream MCP connected: session established", extra={"session_id": self._session_id})
            if show_status:
                console.print(f"[green]MCP Connected[/green] Session: {self._session_id[:8]}...")
            return True
        else:
            reason = self._last_error or "no session established"
            logger.error(
                "Upstream MCP connection failed",
                extra={
                    "sse_url": self.config.sse_url,
                    "post_url": self.config.post_url,
                    "tenant_id": self.config.tenant_id,
                    "reason": reason,
                },
            )
            if show_status:
                console.print(f"[red]MCP Connection failed[/red]: {reason}")
            raise MCPError(
                "Unable to reach upstream MCP analytics service. "
                f"SSE URL: {self.config.sse_url}. "
                f"Reason: {reason}"
            )

    def _sse_listener(self):
        """Listen for SSE events from MCP server."""
        try:
            with httpx.stream(
                "GET",
                self.config.sse_url,
                headers={"tenant_id": self.config.tenant_id},
                timeout=None,
            ) as response:
                if response.status_code >= 400:
                    self._last_error = f"SSE connect failed: HTTP {response.status_code}"
                    logger.error(
                        "SSE connect returned error status",
                        extra={
                            "status_code": response.status_code,
                            "sse_url": self.config.sse_url,
                            "tenant_id": self.config.tenant_id,
                        },
                    )
                    self._session_ready.set()
                    return

                logger.info(
                    "SSE stream opened",
                    extra={
                        "status_code": response.status_code,
                        "sse_url": self.config.sse_url,
                        "tenant_id": self.config.tenant_id,
                    },
                )
                event_type = None
                event_data = []

                for line in response.iter_lines():
                    if not self._running:
                        break

                    line = line.strip()
                    if not line:
                        if event_data:
                            self._handle_sse_event(event_type, "\n".join(event_data))
                            event_data = []
                            event_type = None
                        continue

                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                    elif line.startswith("data:"):
                        event_data.append(line[5:].strip())

        except Exception as e:
            if self._running:
                self._last_error = f"SSE connect failed: {e}"
                logger.exception(
                    "SSE listener failed",
                    extra={
                        "sse_url": self.config.sse_url,
                        "tenant_id": self.config.tenant_id,
                    },
                )
                console.print(f"[red]SSE Error: {e}[/red]")
                self._session_ready.set()

    def _handle_sse_event(self, event_type: Optional[str], data: str):
        """Handle incoming SSE event."""
        try:
            if event_type == "endpoint":
                if "sessionId=" in data:
                    self._session_id = data.split("sessionId=")[1].split("&")[0].split()[0]
                    self._session_ready.set()
            elif event_type == "message":
                message = json.loads(data)
                msg_id = message.get("id")
                if msg_id and msg_id in self._responses:
                    self._responses[msg_id].put(message)
        except json.JSONDecodeError:
            pass

    def _send_request(self, method: str, params: Optional[dict] = None, timeout: Optional[int] = None) -> dict:
        """Send MCP request and wait for response via SSE."""
        request_id = str(uuid.uuid4())[:8]
        timeout = timeout or self.config.timeout

        message = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params:
            message["params"] = params

        # Create response queue
        response_queue: queue.Queue = queue.Queue()
        self._responses[request_id] = response_queue

        try:
            url = self.config.post_url
            if self._session_id:
                url = f"{url}?sessionId={self._session_id}"

            started = time.time()
            logger.info(
                "Sending upstream MCP request",
                extra={
                    "request_id": request_id,
                    "method": method,
                    "url": url,
                    "tenant_id": self.config.tenant_id,
                },
            )

            # Send POST (response comes via SSE)
            response = httpx.post(
                url,
                headers={"tenant_id": self.config.tenant_id, "Content-Type": "application/json"},
                json=message,
                timeout=5,
            )
            if response.status_code >= 400:
                logger.error(
                    "Upstream MCP POST returned error status",
                    extra={
                        "request_id": request_id,
                        "method": method,
                        "status_code": response.status_code,
                        "url": url,
                    },
                )
                return {"error": {"code": -1, "message": f"Upstream POST failed with HTTP {response.status_code}"}}

            # Wait for response via SSE
            try:
                result = response_queue.get(timeout=timeout)
                logger.info(
                    "Received upstream MCP response",
                    extra={
                        "request_id": request_id,
                        "method": method,
                        "elapsed_ms": int((time.time() - started) * 1000),
                    },
                )
                return result
            except queue.Empty:
                logger.error(
                    "Timed out waiting for upstream MCP SSE response",
                    extra={
                        "request_id": request_id,
                        "method": method,
                        "timeout": timeout,
                        "url": url,
                    },
                )
                return {"error": {"code": -1, "message": f"Request timed out after {timeout}s"}}
        except (httpx.HTTPError, httpx.TimeoutException, OSError) as e:
            logger.exception(
                "Failed to send upstream MCP request",
                extra={
                    "request_id": request_id,
                    "method": method,
                    "post_url": self.config.post_url,
                    "tenant_id": self.config.tenant_id,
                },
            )
            raise MCPError(
                "Unable to reach upstream MCP analytics service. "
                f"POST URL: {self.config.post_url}. "
                f"Reason: {e}"
            ) from e

        finally:
            del self._responses[request_id]

    def _send_notification(self, method: str, params: Optional[dict] = None):
        """Send MCP notification (no response expected)."""
        message = {"jsonrpc": "2.0", "method": method}
        if params:
            message["params"] = params

        url = self.config.post_url
        if self._session_id:
            url = f"{url}?sessionId={self._session_id}"

        try:
            httpx.post(
                url,
                headers={"tenant_id": self.config.tenant_id, "Content-Type": "application/json"},
                json=message,
                timeout=5,
            )
        except (httpx.HTTPError, httpx.TimeoutException, OSError):
            # Notifications are fire-and-forget, ignore failures
            pass

    def initialize(self) -> dict:
        """Initialize MCP session."""
        if self._initialized:
            return {"result": "already initialized"}

        result = self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {"listChanged": True}},
            "clientInfo": {"name": "SocialHub-CLI", "version": "1.0.0"},
        }, timeout=30)

        if "result" in result:
            self._initialized = True
            # Send initialized notification
            self._send_notification("notifications/initialized")

        return result

    def list_tools(self) -> list[dict]:
        """List available MCP tools."""
        result = self._send_request("tools/list", {}, timeout=60)
        if "result" in result:
            self._tools = result["result"].get("tools", [])
            return self._tools
        return []

    def call_tool(self, tool_name: str, arguments: Optional[dict] = None, timeout: int = 60) -> Any:
        """Call an MCP tool."""
        result = self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments or {},
        }, timeout=timeout)

        if "error" in result:
            raise MCPError(result["error"].get("message", str(result["error"])))

        if "result" in result:
            content = result["result"].get("content", [])
            for item in content:
                if item.get("type") == "text":
                    text = item.get("text", "")
                    # Try to parse as JSON first
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        pass
                    # Try to parse as tab-separated values
                    parsed = self._parse_tsv(text)
                    if parsed:
                        return parsed
                    return text
            return content

        return result

    def _parse_tsv(self, text: str) -> Optional[list[dict]]:
        """Parse tab-separated values into list of dictionaries."""
        lines = text.strip().split("\n")
        if len(lines) < 2:
            return None

        # First line is headers
        headers = lines[0].split("\t")

        # Rest are data rows
        result = []
        for line in lines[1:]:
            if not line.strip():
                continue
            values = line.split("\t")
            row = {}
            for i, header in enumerate(headers):
                value = values[i] if i < len(values) else None
                # Try to convert to number
                if value is not None:
                    try:
                        if "." in value:
                            row[header] = float(value)
                        else:
                            row[header] = int(value)
                    except (ValueError, TypeError):
                        row[header] = value if value != "null" else None
            result.append(row)

        return result if result else None

    def query(self, sql: str, timeout: int = 60, database: Optional[str] = None) -> Any:
        """Execute SQL query via analytics_executeQuery tool."""
        args = {"sql": sql}  # Note: parameter name is 'sql', not 'query'
        if database:
            args["database"] = database
        return self.call_tool("analytics_executeQuery", args, timeout=timeout)

    def list_tables(self, database: Optional[str] = None, timeout: int = 30) -> Any:
        """List tables via analytics_listTables tool."""
        args = {}
        if database:
            args["database"] = database
        return self.call_tool("analytics_listTables", args, timeout=timeout)

    def get_table_schema(self, table_name: str, database: Optional[str] = None, timeout: int = 30) -> Any:
        """Get table schema via analytics_getTableSchema tool."""
        args = {"table": table_name}
        if database:
            args["database"] = database
        return self.call_tool("analytics_getTableSchema", args, timeout=timeout)

    def list_databases(self, timeout: int = 30) -> Any:
        """List available databases via analytics_listDatabases tool."""
        return self.call_tool("analytics_listDatabases", {}, timeout=timeout)

    def get_database_stats(self, timeout: int = 30) -> Any:
        """Get database stats via analytics_getDatabaseStats tool."""
        return self.call_tool("analytics_getDatabaseStats", {}, timeout=timeout)

    def disconnect(self):
        """Disconnect from MCP service."""
        logger.info("Disconnecting MCP client", extra={"session_id": self._session_id})
        self._running = False
        self._connected = False
        self._initialized = False
        self._session_ready.clear()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()


class MCPError(Exception):
    """MCP error exception."""
    pass
