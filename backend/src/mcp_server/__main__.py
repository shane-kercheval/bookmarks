"""Entry point for running the MCP server."""

import os

from .server import mcp

if __name__ == "__main__":
    host = os.getenv("MCP_HOST", "0.0.0.0")
    # MCP_PORT for local dev (.env), PORT for PaaS platforms (Railway, Heroku, etc.)
    port = int(os.getenv("MCP_PORT") or os.getenv("PORT") or "8001")
    mcp.run(transport="http", host=host, port=port, stateless_http=True)
