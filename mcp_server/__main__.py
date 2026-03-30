"""Entry point for the SocialHub.AI MCP Server.

stdio 模式（默认，Claude Desktop / GitHub Copilot）：
    python -m mcp_server
    python -m mcp_server --transport stdio

HTTP 模式（M365 Copilot / 远程部署）：
    python -m mcp_server --transport http --port 8090
    uvicorn mcp_server.http_app:app --host 0.0.0.0 --port $PORT  # 等价
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
from pathlib import Path


def _configure_logging() -> Path:
    """配置日志：文件 + stderr 双输出。
    两种传输模式（stdio/HTTP）均使用 stderr，不污染 MCP 协议通道（stdin/stdout）。
    """
    log_dir = Path.home() / ".socialhub" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "mcp_server.log"

    handlers: list[logging.Handler] = [
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stderr),
    ]

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=handlers,
        force=True,
    )
    return log_file


def _run_stdio() -> None:
    """stdio transport（Claude Desktop / GitHub Copilot）。"""
    import anyio
    from mcp.server.stdio import stdio_server
    from .server import create_server, _load_analytics, _warm_cache, probe_upstream_mcp

    log_file = _configure_logging()
    logger = logging.getLogger(__name__)
    pid = os.getpid()
    logger.info("Starting SocialHub MCP server (stdio) pid=%s", pid)
    logger.info("Server log file: %s", log_file)

    ok, message = probe_upstream_mcp()
    if ok:
        logger.info("Upstream MCP probe succeeded: %s", message)
    else:
        logger.error("Upstream MCP probe failed: %s", message)

    threading.Thread(target=_load_analytics, daemon=True).start()
    threading.Thread(target=_warm_cache, daemon=True).start()

    async def run() -> None:
        server = create_server()
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    anyio.run(run)


def _run_http(port: int) -> None:
    """HTTP Streamable Transport（M365 Copilot 远程部署）。
    lifespan 在 http_app 中管理 probe 和 analytics 加载，此处只启动 uvicorn。
    """
    import uvicorn
    from .http_app import app

    _configure_logging()
    logger = logging.getLogger(__name__)
    pid = os.getpid()
    logger.info("Starting SocialHub MCP server (HTTP) pid=%s port=%s", pid, port)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SocialHub MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m mcp_server                      # stdio（Claude Desktop）
  python -m mcp_server --transport http     # HTTP（M365 Copilot）
  python -m mcp_server --transport http --port 9000
        """,
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport mode: stdio (default) or http",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", "8090")),
        help="HTTP server port (default: 8090, or $PORT env var)",
    )

    args = parser.parse_args()

    if args.transport == "stdio":
        _run_stdio()
    elif args.transport == "http":
        _run_http(args.port)


if __name__ == "__main__":
    main()
