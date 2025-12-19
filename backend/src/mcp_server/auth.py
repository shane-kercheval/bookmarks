"""Authentication utilities for MCP server."""

from fastmcp.server.dependencies import get_http_headers


class AuthenticationError(Exception):
    """Raised when authentication fails."""

    pass


def get_bearer_token() -> str:
    """
    Extract Bearer token from the Authorization header.

    Returns:
        The token string (without 'Bearer ' prefix).

    Raises:
        AuthenticationError: If no valid Bearer token is present.
    """
    headers = get_http_headers()
    auth_header = headers.get("authorization", "")

    parts = auth_header.split(maxsplit=1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthenticationError("Missing or invalid Authorization header")

    token = parts[1]
    if not token:
        raise AuthenticationError("Empty Bearer token")

    return token
