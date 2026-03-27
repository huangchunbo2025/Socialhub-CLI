"""Launch the repo-local SocialHub MCP server for Claude Desktop."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp_server.__main__ import main


if __name__ == "__main__":
    main()
