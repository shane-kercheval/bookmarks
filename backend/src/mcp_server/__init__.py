"""MCP server for the Bookmarks API."""

from .auth import AuthenticationError, get_bearer_token
from .server import mcp

__all__ = ["AuthenticationError", "get_bearer_token", "mcp"]
