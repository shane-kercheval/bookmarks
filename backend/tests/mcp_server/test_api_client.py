"""Tests for the MCP API client helper functions."""

import httpx
import pytest
from httpx import Response

from mcp_server.api_client import api_get, api_post


@pytest.mark.asyncio
async def test__api_get__success(mock_api) -> None:
    """Test successful GET request."""
    mock_api.get("/bookmarks/1").mock(
        return_value=Response(200, json={"id": 1, "url": "https://example.com"}),
    )

    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        result = await api_get(client, "/bookmarks/1", "bm_test_token")

    assert result["id"] == 1
    assert result["url"] == "https://example.com"


@pytest.mark.asyncio
async def test__api_get__with_params(mock_api) -> None:
    """Test GET request with query parameters."""
    mock_api.get("/bookmarks/").mock(
        return_value=Response(200, json={"items": [], "total": 0}),
    )

    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        result = await api_get(
            client,
            "/bookmarks/",
            "bm_test_token",
            params={"q": "test", "limit": 10},
        )

    assert result["total"] == 0


@pytest.mark.asyncio
async def test__api_post__success(mock_api) -> None:
    """Test successful POST request."""
    mock_api.post("/bookmarks/").mock(
        return_value=Response(201, json={"id": 1, "url": "https://example.com"}),
    )

    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        result = await api_post(
            client,
            "/bookmarks/",
            "bm_test_token",
            {"url": "https://example.com"},
        )

    assert result["id"] == 1


@pytest.mark.asyncio
async def test__api_get__http_error(mock_api) -> None:
    """Test HTTP error handling."""
    mock_api.get("/bookmarks/999").mock(
        return_value=Response(404, json={"detail": "Not found"}),
    )

    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        with pytest.raises(httpx.HTTPStatusError):
            await api_get(client, "/bookmarks/999", "bm_test_token")


@pytest.mark.asyncio
async def test__api_get__authorization_header_set(mock_api) -> None:
    """Test that Authorization header is correctly set."""
    mock_api.get("/test").mock(return_value=Response(200, json={}))

    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        await api_get(client, "/test", "bm_test_token_12345")

    assert (
        mock_api.calls[0].request.headers["authorization"] == "Bearer bm_test_token_12345"
    )
