"""FastMCP server for the Bookmarks API."""

from typing import Annotated, Any, Literal, NoReturn

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from .api_client import api_get, api_post, get_api_base_url, get_default_timeout
from .auth import AuthenticationError, get_bearer_token

mcp = FastMCP(name="Bookmarks MCP Server")


# Module-level client for connection reuse (can be overridden in tests)
_http_client: httpx.AsyncClient | None = None


async def _get_http_client() -> httpx.AsyncClient:
    """Get or create the HTTP client for API requests."""
    global _http_client  # noqa: PLW0603
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            base_url=get_api_base_url(),
            timeout=get_default_timeout(),
        )
    return _http_client


def _get_token() -> str:
    """Get Bearer token, raising ToolError on failure."""
    try:
        return get_bearer_token()
    except AuthenticationError as e:
        raise ToolError(str(e))


def _handle_api_error(e: httpx.HTTPStatusError, context: str = "") -> NoReturn:
    """Translate API errors to meaningful MCP ToolErrors. Always raises."""
    status = e.response.status_code

    if status == 401:
        raise ToolError("Invalid or expired token")
    if status == 403:
        raise ToolError("Access denied")

    # Try to extract detailed error message from API response
    try:
        detail = e.response.json().get("detail", {})
        if isinstance(detail, dict):
            message = detail.get("message", str(detail))
            error_code = detail.get("error_code", "")
            if error_code:
                raise ToolError(f"{message} (code: {error_code})")
            raise ToolError(message)
        raise ToolError(str(detail))
    except (ValueError, KeyError):
        raise ToolError(f"API error {status}{': ' + context if context else ''}")


@mcp.tool(
    description=(
        "Search bookmarks with optional text query and tag filtering. "
        "Returns active bookmarks only."
    ),
    annotations={"readOnlyHint": True},
)
async def search_bookmarks(
    query: Annotated[
        str | None,
        Field(description="Text to search in title, URL, description, and content"),
    ] = None,
    tags: Annotated[list[str] | None, Field(description="Filter by tags")] = None,
    tag_match: Annotated[
        Literal["all", "any"],
        Field(description="Tag matching: 'all' requires ALL tags, 'any' requires ANY tag"),
    ] = "all",
    sort_by: Annotated[
        Literal["created_at", "updated_at", "last_used_at", "title"],
        Field(description="Field to sort by"),
    ] = "created_at",
    sort_order: Annotated[Literal["asc", "desc"], Field(description="Sort direction")] = "desc",
    limit: Annotated[int, Field(ge=1, le=100, description="Maximum results to return")] = 50,
    offset: Annotated[
        int, Field(ge=0, description="Number of results to skip for pagination"),
    ] = 0,
) -> dict[str, Any]:
    """
    Search and filter bookmarks.

    Examples:
    - Search for "python": query="python"
    - Filter by tag: tags=["programming"]
    - Combine: query="tutorial", tags=["python", "beginner"], tag_match="all"
    """
    client = await _get_http_client()
    token = _get_token()

    params: dict[str, Any] = {
        "limit": limit,
        "offset": offset,
        "tag_match": tag_match,
        "sort_by": sort_by,
        "sort_order": sort_order,
    }
    if query:
        params["q"] = query
    if tags:
        params["tags"] = tags

    try:
        return await api_get(client, "/bookmarks/", token, params)
    except httpx.HTTPStatusError as e:
        _handle_api_error(e, "searching bookmarks")
        raise  # Unreachable but satisfies type checker
    except httpx.RequestError as e:
        raise ToolError(f"API unavailable: {e}")


@mcp.tool(
    description="Get the full details of a specific bookmark including stored content",
    annotations={"readOnlyHint": True},
)
async def get_bookmark(
    bookmark_id: Annotated[int, Field(description="The ID of the bookmark to retrieve")],
) -> dict[str, Any]:
    """Get a bookmark by ID. Returns full details including content if stored."""
    client = await _get_http_client()
    token = _get_token()

    try:
        return await api_get(client, f"/bookmarks/{bookmark_id}", token)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise ToolError(f"Bookmark with ID {bookmark_id} not found")
        _handle_api_error(e, f"getting bookmark {bookmark_id}")
        raise
    except httpx.RequestError as e:
        raise ToolError(f"API unavailable: {e}")


@mcp.tool(
    description=(
        "Create a new bookmark. URL metadata (title, description) "
        "will be auto-fetched if not provided."
    ),
    annotations={"readOnlyHint": False},
)
async def create_bookmark(
    url: Annotated[str, Field(description="The URL to bookmark")],
    title: Annotated[
        str | None, Field(description="Title (auto-fetched from URL if not provided)"),
    ] = None,
    description: Annotated[
        str | None, Field(description="Description (auto-fetched from URL if not provided)"),
    ] = None,
    tags: Annotated[
        list[str] | None,
        Field(description="Tags to assign (lowercase with hyphens, e.g., 'machine-learning')"),
    ] = None,
    store_content: Annotated[
        bool, Field(description="Whether to store the page content for search"),
    ] = True,
) -> dict[str, Any]:
    """
    Create a new bookmark.

    If title and description are not provided, they will be automatically
    fetched from the URL. Tags should be lowercase with hyphens (e.g., 'web-dev').
    """
    client = await _get_http_client()
    token = _get_token()

    payload: dict[str, Any] = {"url": url, "store_content": store_content}
    if title is not None:
        payload["title"] = title
    if description is not None:
        payload["description"] = description
    if tags is not None:
        payload["tags"] = tags

    try:
        return await api_post(client, "/bookmarks/", token, payload)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 409:
            # Extract rich error details for duplicate URL
            try:
                detail = e.response.json().get("detail", {})
                error_code = detail.get("error_code", "")
                if error_code == "ARCHIVED_URL_EXISTS":
                    bookmark_id = detail.get("existing_bookmark_id")
                    raise ToolError(
                        f"An archived bookmark exists with this URL (ID: {bookmark_id}). "
                        "Use the web UI to restore or permanently delete it first.",
                    )
                raise ToolError("A bookmark with this URL already exists")
            except (ValueError, KeyError, TypeError):
                raise ToolError("A bookmark with this URL already exists")
        _handle_api_error(e, "creating bookmark")
        raise
    except httpx.RequestError as e:
        raise ToolError(f"API unavailable: {e}")


@mcp.tool(
    description="List all tags with their usage counts",
    annotations={"readOnlyHint": True},
)
async def list_tags() -> dict[str, Any]:
    """
    Get all tags for the authenticated user.

    Returns tags sorted by usage count (most used first), then alphabetically.
    Includes tags with zero active bookmarks.
    """
    client = await _get_http_client()
    token = _get_token()

    try:
        return await api_get(client, "/tags/", token)
    except httpx.HTTPStatusError as e:
        _handle_api_error(e, "listing tags")
        raise
    except httpx.RequestError as e:
        raise ToolError(f"API unavailable: {e}")
