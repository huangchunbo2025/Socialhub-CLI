"""MCP (Model Context Protocol) client for SocialHub analytics database."""

import json
import logging
import queue
import threading
import os
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
from rich.console import Console

console = Console(stderr=True)
logger = logging.getLogger(__name__)


@dataclass
class MCPConnectionConfig:
    """MCP service connection configuration (for the SSE/HTTP client).

    Distinct from ``cli.config.MCPConfig`` (the Pydantic settings model).

    SECURITY: No default URLs - must be explicitly configured via:
    1. Config file (~/.socialhub/config.json)
    2. Environment variables (MCP_SSE_URL, MCP_POST_URL, MCP_TENANT_ID, MCP_API_KEY)
    """
    sse_url: str = ""  # Required - no hardcoded default
    post_url: str = ""  # Required - no hardcoded default
    tenant_id: str = ""  # Required - no hardcoded default
    timeout: int = 120
    api_key: str = ""  # Optional: sent as Authorization: Bearer <api_key>
    token: str = ""  # SocialHub Bearer token，由 TokenManager 注入（HTTP 模式）
    das_database: str = ""  # dwd/ads/dws/dim 表所在库，由 server.py 按租户注入
    dts_database: str = ""  # vdm_ 表所在库
    datanow_database: str = ""  # t_/v_ 表所在库


# Backward-compatibility alias — existing code importing ``MCPConfig`` continues to work.
MCPConfig = MCPConnectionConfig


class MCPClient:
    """Client for MCP analytics database service."""

    def __init__(self, config: MCPConfig | None = None):
        self.config = config or MCPConfig()
        # 从 thread-local 读取 token / 数据库名（server.py 在进入 executor 前注入）
        import threading as _threading
        _tl = _threading.current_thread().__dict__
        if not self.config.token:
            self.config.token = _tl.get("_sh_mcp_token", "") or ""
        if not self.config.das_database:
            self.config.das_database = _tl.get("_sh_das_database", "") or ""
        if not self.config.dts_database:
            self.config.dts_database = _tl.get("_sh_dts_database", "") or ""
        if not self.config.datanow_database:
            self.config.datanow_database = _tl.get("_sh_datanow_database", "") or ""
        self._session_id: str | None = None
        self._sse_thread: threading.Thread | None = None
        self._running = False
        self._responses: dict[str, queue.Queue] = {}
        self._tools: list[dict] = []
        self._connected = False
        self._initialized = False
        self._session_ready = threading.Event()
        self._last_error: str | None = None
        self._sse_response: httpx.Response | None = None
        self._connect_timeout = 10.0
        self._post_timeout = 5.0
        self._post_retries = 1
        self._auth_token: str | None = None
        self._auth_tenant_id: str | None = None
        self._load_auth_credentials()

    def _load_auth_credentials(self) -> None:
        """Load token and tenant_id from OAuth2 cache."""
        try:
            from ..auth.token_store import load_oauth_token

            cached = load_oauth_token()
            if cached:
                self._auth_token = cached.get("token") or None
                self._auth_tenant_id = cached.get("tenant_id") or None
        except Exception:
            pass

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

    def _auth_headers(self) -> dict[str, str]:
        """Build auth headers shared by every outbound request.

        Token priority:
        1. self._auth_token  — CLI 模式：从 oauth_token.json 缓存读取（最高优先级）
        2. self.config.token — Server 模式：server.py 通过 thread-local 注入的 SocialHub token
        3. self.config.api_key — 兼容旧路径
        """
        # CLI mode: OAuth token from login cache (highest priority)
        if self._auth_token and self._auth_tenant_id:
            return {
                "tenant_id": self._auth_tenant_id,
                "Authorization": f"Bearer {self._auth_token}",
            }

        # Server mode or legacy: config.token (thread-local) or config.api_key
        headers: dict[str, str] = {"tenant_id": self.config.tenant_id}
        token = self.config.token or self.config.api_key
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def connect(self, show_status: bool = True) -> bool:
        """Connect to MCP service via SSE."""
        if self._connected:
            return True

        # Validate configuration before attempting connection
        self._validate_config()

        self._running = True
        self._last_error = None
        self._session_ready.clear()
        _headers = self._auth_headers()
        logger.info(
            "Connecting to upstream MCP via SSE",
            extra={
                "sse_url": self.config.sse_url,
                "post_url": self.config.post_url,
                "tenant_id": _headers.get("tenant_id", ""),
                "has_bearer": "Authorization" in _headers,
            },
        )
        # Debug: print actual headers to stderr so user can verify
        console.print(
            f"[dim]MCP headers: tenant_id={_headers.get('tenant_id', '')}, "
            f"auth={'Bearer ***' + self._auth_token[-8:] if self._auth_token else 'NONE'}[/dim]"
        )
        self._sse_thread = threading.Thread(target=self._sse_listener, daemon=True)
        self._sse_thread.start()

        # Wait for session ID via event (no busy-wait)
        self._session_ready.wait(timeout=self._connect_timeout)

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
                headers=self._auth_headers(),
                timeout=httpx.Timeout(connect=self._connect_timeout, read=None, write=self._connect_timeout, pool=self._connect_timeout),
            ) as response:
                self._sse_response = response
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

    def _handle_sse_event(self, event_type: str | None, data: str):
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

    def _send_request(self, method: str, params: dict | None = None, timeout: int | None = None) -> dict:
        """Send MCP request and wait for response via SSE."""
        request_id = uuid.uuid4().hex
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

            # Send POST (response comes via SSE). Retry once for transient transport failures.
            response = None
            for attempt in range(self._post_retries + 1):
                try:
                    response = httpx.post(
                        url,
                        headers={**self._auth_headers(), "Content-Type": "application/json"},
                        json=message,
                        timeout=self._post_timeout,
                    )
                    if response.status_code < 500:
                        break
                    logger.warning(
                        "Upstream MCP POST returned retryable status",
                        extra={
                            "request_id": request_id,
                            "method": method,
                            "status_code": response.status_code,
                            "attempt": attempt + 1,
                            "url": url,
                        },
                    )
                except (httpx.HTTPError, httpx.TimeoutException, OSError) as e:
                    if attempt >= self._post_retries:
                        raise
                    logger.warning(
                        "Retrying upstream MCP POST after transport error",
                        extra={
                            "request_id": request_id,
                            "method": method,
                            "attempt": attempt + 1,
                            "url": url,
                            "error": str(e),
                        },
                    )
                    time.sleep(0.3 * (attempt + 1))

            if response is None:
                return {"error": {"code": -1, "message": "Upstream POST failed before response"}}
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

            # Wait for response via SSE — poll every 0.5 s so we can fast-fail
            # immediately if the SSE thread dies instead of blocking until the
            # full timeout expires (A6.2 fast-fail fix).
            deadline = time.monotonic() + timeout
            while True:
                try:
                    result = response_queue.get(timeout=0.5)
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
                    pass
                if not self._sse_thread.is_alive():
                    logger.error(
                        "SSE thread died while waiting for upstream MCP response",
                        extra={
                            "request_id": request_id,
                            "method": method,
                            "url": url,
                        },
                    )
                    raise MCPError("SSE connection lost while waiting for response")
                if time.monotonic() >= deadline:
                    logger.error(
                        "Timed out waiting for upstream MCP SSE response",
                        extra={
                            "request_id": request_id,
                            "method": method,
                            "timeout": timeout,
                            "url": url,
                        },
                    )
                    raise MCPError(f"Request timed out after {timeout}s")
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

    def _send_notification(self, method: str, params: dict | None = None):
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
                headers={**self._auth_headers(), "Content-Type": "application/json"},
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

        started = time.time()
        result = self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {"listChanged": True}},
            "clientInfo": {"name": "SocialHub-CLI", "version": "1.0.0"},
        }, timeout=30)
        logger.info("Upstream MCP initialize completed", extra={"elapsed_ms": int((time.time() - started) * 1000)})

        if "result" in result:
            self._initialized = True
            # Send initialized notification
            self._send_notification("notifications/initialized")

        return result

    def list_tools(self) -> list[dict]:
        """List available MCP tools."""
        started = time.time()
        result = self._send_request("tools/list", {}, timeout=60)
        if "result" in result:
            self._tools = result["result"].get("tools", [])
            logger.info(
                "Upstream MCP tools/list completed",
                extra={"elapsed_ms": int((time.time() - started) * 1000), "tools": len(self._tools)},
            )
            return self._tools
        return []

    def call_tool(self, tool_name: str, arguments: dict | None = None, timeout: int = 60) -> Any:
        """Call an MCP tool."""
        started = time.time()
        result = self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments or {},
        }, timeout=timeout)
        logger.info(
            "Upstream MCP tools/call completed",
            extra={
                "tool_name": tool_name,
                "elapsed_ms": int((time.time() - started) * 1000),
            },
        )

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

    def _parse_tsv(self, text: str) -> list[dict] | None:
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

    # Table-prefix → database-slot mapping (must match CLAUDE.md routing rules)
    _TABLE_PREFIX_TO_DB_SLOT: list[tuple[tuple[str, ...], str]] = [
        (("ads_", "dwd_", "dim_", "dws_"), "das_database"),
        (("vdm_",), "dts_database"),
        (("t_", "v_"), "datanow_database"),
    ]

    def _resolve_database(self, sql: str) -> str | None:
        """Determine target database from SQL table prefixes.

        Routing rules (matching CLAUDE.md):
        - ads_ / dwd_ / dim_ / dws_  → das_database
        - vdm_                        → dts_database
        - t_ / v_                     → datanow_database
        - SQL already has db.table    → no rewrite (return None)
        """
        # Extract token(s) immediately after FROM/JOIN keyword.
        # Tokens containing a dot are already fully-qualified (db.table) — skip them.
        raw_tokens = re.findall(r'\b(?:FROM|JOIN)\s+(\S+)', sql, re.IGNORECASE)
        tables: list[str] = []
        for tok in raw_tokens:
            # Strip trailing punctuation (comma, closing paren, etc.)
            tok = re.sub(r'[^a-zA-Z0-9_.]', '', tok)
            if '.' in tok:
                # Already qualified: the whole query needs no auto-routing
                return None
            if tok:
                tables.append(tok)

        for table in tables:
            tl = table.lower()
            for prefixes, slot in self._TABLE_PREFIX_TO_DB_SLOT:
                if any(tl.startswith(p) for p in prefixes):
                    db = getattr(self.config, slot, "") or ""
                    return db or None
        return None

    def query(self, sql: str, timeout: int = 60, database: str | None = None) -> Any:
        """Execute SQL query via analytics_executeQuery tool.

        If *database* is not provided (or is empty), the target database is
        auto-detected from the table prefixes in *sql* using the thread-local
        database names injected by server.py (das_database / dts_database /
        datanow_database).  This implements the routing documented in CLAUDE.md.
        """
        if not database:
            database = self._resolve_database(sql)
        args = {"sql": sql}
        if database:
            args["database"] = database
        return self.call_tool("analytics_executeQuery", args, timeout=timeout)

    def list_tables(self, database: str | None = None, timeout: int = 30) -> Any:
        """List tables via analytics_listTables tool."""
        args = {}
        if database:
            args["database"] = database
        return self.call_tool("analytics_listTables", args, timeout=timeout)

    def get_table_schema(self, table_name: str, database: str | None = None, timeout: int = 30) -> Any:
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
        sse_resp = self._sse_response
        self._sse_response = None
        if sse_resp is not None:
            try:
                sse_resp.close()
            except Exception:
                pass
        if self._sse_thread is not None and self._sse_thread.is_alive():
            self._sse_thread.join(timeout=2)

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()


class MCPError(Exception):
    """MCP error exception."""
    pass


