"""Tests for MCP tools using FastMCP Client."""

from typing import Any
from unittest.mock import patch

import httpx
import pytest
from httpx import Response

from fastmcp import Client


@pytest.fixture
async def mcp_client(mock_auth):  # noqa: ARG001 - mock_auth needed for side effect
    """Create an MCP client connected to the server."""
    from mcp_server.server import mcp

    async with Client(transport=mcp) as client:
        yield client


@pytest.mark.asyncio
async def test__search_bookmarks__basic(
    mock_api,
    mcp_client: Client,
    sample_bookmark_list: dict[str, Any],
) -> None:
    """Test basic bookmark search."""
    mock_api.get("/bookmarks/").mock(
        return_value=Response(200, json=sample_bookmark_list),
    )

    result = await mcp_client.call_tool("search_bookmarks", {})

    assert result.data["total"] == 1
    assert len(result.data["items"]) == 1


@pytest.mark.asyncio
async def test__search_bookmarks__with_query(
    mock_api,
    mcp_client: Client,
    sample_bookmark_list: dict[str, Any],
) -> None:
    """Test search with query parameter."""
    mock_api.get("/bookmarks/").mock(
        return_value=Response(200, json=sample_bookmark_list),
    )

    await mcp_client.call_tool("search_bookmarks", {"query": "example"})

    assert "q" in str(mock_api.calls[0].request.url)


@pytest.mark.asyncio
async def test__search_bookmarks__with_tags(
    mock_api,
    mcp_client: Client,
    sample_bookmark_list: dict[str, Any],
) -> None:
    """Test search with tag filtering."""
    mock_api.get("/bookmarks/").mock(
        return_value=Response(200, json=sample_bookmark_list),
    )

    await mcp_client.call_tool(
        "search_bookmarks",
        {"tags": ["python", "web-dev"], "tag_match": "any"},
    )

    request_url = str(mock_api.calls[0].request.url)
    assert "tags" in request_url
    assert "tag_match=any" in request_url


@pytest.mark.asyncio
async def test__get_bookmark__success(
    mock_api,
    mcp_client: Client,
    sample_bookmark: dict[str, Any],
) -> None:
    """Test getting a bookmark by ID."""
    mock_api.get("/bookmarks/1").mock(
        return_value=Response(200, json=sample_bookmark),
    )

    result = await mcp_client.call_tool("get_bookmark", {"bookmark_id": 1})

    assert result.data["id"] == 1
    assert result.data["url"] == "https://example.com"


@pytest.mark.asyncio
async def test__get_bookmark__not_found(mock_api, mcp_client: Client) -> None:
    """Test 404 error handling."""
    mock_api.get("/bookmarks/999").mock(
        return_value=Response(404, json={"detail": "Not found"}),
    )

    result = await mcp_client.call_tool(
        "get_bookmark", {"bookmark_id": 999}, raise_on_error=False,
    )

    assert result.is_error
    assert "not found" in result.content[0].text.lower()


@pytest.mark.asyncio
async def test__create_bookmark__success(
    mock_api,
    mcp_client: Client,
    sample_bookmark: dict[str, Any],
) -> None:
    """Test creating a bookmark."""
    mock_api.post("/bookmarks/").mock(
        return_value=Response(201, json=sample_bookmark),
    )

    result = await mcp_client.call_tool(
        "create_bookmark",
        {"url": "https://example.com", "title": "Example", "tags": ["test"]},
    )

    assert result.data["id"] == 1


@pytest.mark.asyncio
async def test__create_bookmark__duplicate_active(mock_api, mcp_client: Client) -> None:
    """Test duplicate URL error (active bookmark exists)."""
    mock_api.post("/bookmarks/").mock(
        return_value=Response(
            409,
            json={
                "detail": {
                    "message": "URL already exists",
                    "error_code": "ACTIVE_URL_EXISTS",
                },
            },
        ),
    )

    result = await mcp_client.call_tool(
        "create_bookmark", {"url": "https://example.com"}, raise_on_error=False,
    )

    assert result.is_error
    assert "already exists" in result.content[0].text.lower()


@pytest.mark.asyncio
async def test__create_bookmark__archived_exists(mock_api, mcp_client: Client) -> None:
    """Test duplicate URL error (archived bookmark exists)."""
    mock_api.post("/bookmarks/").mock(
        return_value=Response(
            409,
            json={
                "detail": {
                    "message": "Archived bookmark exists",
                    "error_code": "ARCHIVED_URL_EXISTS",
                    "existing_bookmark_id": 42,
                },
            },
        ),
    )

    result = await mcp_client.call_tool(
        "create_bookmark", {"url": "https://example.com"}, raise_on_error=False,
    )

    assert result.is_error
    error_text = result.content[0].text.lower()
    assert "archived" in error_text
    assert "42" in result.content[0].text


@pytest.mark.asyncio
async def test__list_tags__success(
    mock_api,
    mcp_client: Client,
    sample_tags: dict[str, Any],
) -> None:
    """Test listing tags."""
    mock_api.get("/tags/").mock(
        return_value=Response(200, json=sample_tags),
    )

    result = await mcp_client.call_tool("list_tags", {})

    assert len(result.data["tags"]) == 3
    assert result.data["tags"][0]["name"] == "python"


@pytest.mark.asyncio
async def test__search_bookmarks__api_unavailable(mock_api, mcp_client: Client) -> None:
    """Test network error handling."""
    mock_api.get("/bookmarks/").mock(side_effect=httpx.ConnectError("Connection refused"))

    result = await mcp_client.call_tool("search_bookmarks", {}, raise_on_error=False)

    assert result.is_error
    assert "unavailable" in result.content[0].text.lower()


@pytest.mark.asyncio
async def test__search_bookmarks__invalid_token(mock_api) -> None:
    """Test 401 error handling for invalid token."""
    from mcp_server.server import mcp

    mock_api.get("/bookmarks/").mock(
        return_value=Response(401, json={"detail": "Invalid token"}),
    )

    with patch("mcp_server.server.get_bearer_token") as mock_auth:
        mock_auth.return_value = "invalid_token"
        async with Client(transport=mcp) as client:
            result = await client.call_tool("search_bookmarks", {}, raise_on_error=False)

    assert result.is_error
    error_text = result.content[0].text.lower()
    assert "invalid" in error_text or "expired" in error_text
