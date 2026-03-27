"""Entry point for the SocialHub.AI MCP Server (stdio, Claude Desktop)."""

from __future__ import annotations

import logging
import threading

logging.basicConfig(level=logging.WARNING)


def main() -> None:
    import anyio
    from mcp.server.stdio import stdio_server
    from .server import create_server, _load_analytics

    # Pre-warm heavy analytics imports on a regular thread so tool calls
    # do not pay the import cost and Windows event-loop executors are avoided.
    threading.Thread(target=_load_analytics, daemon=True).start()

    async def run_stdio() -> None:
        server = create_server()
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    anyio.run(run_stdio)


if __name__ == "__main__":
    main()
