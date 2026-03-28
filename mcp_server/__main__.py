"""Entry point for the SocialHub.AI MCP Server (stdio, Claude Desktop)."""

from __future__ import annotations

import logging
import threading
from pathlib import Path


def _configure_logging() -> Path:
    log_dir = Path.home() / ".socialhub" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "mcp_server.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )
    return log_file


def main() -> None:
    import anyio
    from mcp.server.stdio import stdio_server
    from .server import create_server, _load_analytics, _warm_cache, probe_upstream_mcp

    log_file = _configure_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting SocialHub MCP server")
    logger.info("Server log file: %s", log_file)

    ok, message = probe_upstream_mcp()
    if ok:
        logger.info("Upstream MCP probe succeeded: %s", message)
    else:
        logger.error("Upstream MCP probe failed: %s", message)

    # Pre-warm heavy analytics imports on a regular thread so tool calls
    # do not pay the import cost and Windows event-loop executors are avoided.
    threading.Thread(target=_load_analytics, daemon=True).start()
    threading.Thread(target=_warm_cache, daemon=True).start()

    async def run_stdio() -> None:
        server = create_server()
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    anyio.run(run_stdio)


if __name__ == "__main__":
    main()
