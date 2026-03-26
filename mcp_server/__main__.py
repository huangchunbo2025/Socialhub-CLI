"""Entry point for the SocialHub.AI MCP Server.

Usage:
    python -m mcp_server                         # stdio (Claude Desktop)
    python -m mcp_server --transport sse --port 8090
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from .server import create_server

logging.basicConfig(level=logging.WARNING)


def main() -> None:
    parser = argparse.ArgumentParser(description="SocialHub.AI MCP Analytics Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport to use (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8090,
        help="Port for SSE transport (default: 8090)",
    )
    parser.add_argument(
        "--host",
        default="localhost",
        help="Host for SSE transport (default: localhost)",
    )
    args = parser.parse_args()

    server = create_server()

    if args.transport == "stdio":
        from mcp.server.stdio import stdio_server

        async def run_stdio() -> None:
            async with stdio_server() as (read, write):
                await server.run(read, write, server.create_initialization_options())

        asyncio.run(run_stdio())

    else:
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Route, Mount
        import uvicorn

        sse_transport = SseServerTransport("/messages/")

        async def handle_sse(request):  # type: ignore[no-untyped-def]
            async with sse_transport.connect_sse(
                request.scope, request.receive, request._send
            ) as streams:
                await server.run(
                    streams[0], streams[1], server.create_initialization_options()
                )

        starlette_app = Starlette(
            routes=[
                Route("/sse", endpoint=handle_sse),
                Mount("/messages/", app=sse_transport.handle_post_message),
            ]
        )

        print(f"SocialHub.AI MCP Server running on http://{args.host}:{args.port}/sse")
        uvicorn.run(starlette_app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
