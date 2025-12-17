"""Tests for tags endpoint."""
from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from services.url_scraper import FetchResult


@pytest.fixture(autouse=True)
def mock_url_fetch() -> Generator[AsyncMock]:
    """
    Auto-mock fetch_url for all tests to avoid real network calls.

    Returns a "failed fetch" result by default.
    """
    mock_result = FetchResult(
        html=None,
        final_url='',
        status_code=None,
        content_type=None,
        error='Mocked - no network call',
    )
    with patch(
        'services.bookmark_service.fetch_url',
        new_callable=AsyncMock,
        return_value=mock_result,
    ) as mock:
        yield mock


async def test_list_tags_empty(client: AsyncClient) -> None:
    """Test listing tags when no bookmarks exist."""
    response = await client.get("/tags/")
    assert response.status_code == 200

    data = response.json()
    assert "tags" in data
    assert data["tags"] == []


async def test_list_tags_single_bookmark(client: AsyncClient) -> None:
    """Test listing tags from a single bookmark."""
    await client.post(
        "/bookmarks/",
        json={"url": "https://example.com", "title": "Test", "tags": ["python", "web"]},
    )

    response = await client.get("/tags/")
    assert response.status_code == 200

    data = response.json()
    assert len(data["tags"]) == 2
    # Tags should have name and count
    tag_names = {tag["name"] for tag in data["tags"]}
    assert tag_names == {"python", "web"}
    # Each tag has count of 1
    for tag in data["tags"]:
        assert tag["count"] == 1


async def test_list_tags_multiple_bookmarks(client: AsyncClient) -> None:
    """Test listing tags aggregated across multiple bookmarks."""
    await client.post(
        "/bookmarks/",
        json={"url": "https://example1.com", "tags": ["python", "web"]},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://example2.com", "tags": ["python", "api"]},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://example3.com", "tags": ["python"]},
    )

    response = await client.get("/tags/")
    assert response.status_code == 200

    data = response.json()
    tag_counts = {tag["name"]: tag["count"] for tag in data["tags"]}
    assert tag_counts["python"] == 3
    assert tag_counts["web"] == 1
    assert tag_counts["api"] == 1


async def test_list_tags_sorted_by_count(client: AsyncClient) -> None:
    """Test that tags are sorted by count descending."""
    await client.post(
        "/bookmarks/",
        json={"url": "https://ex1.com", "tags": ["rare"]},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://ex2.com", "tags": ["common", "medium"]},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://ex3.com", "tags": ["common", "medium"]},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://ex4.com", "tags": ["common"]},
    )

    response = await client.get("/tags/")
    assert response.status_code == 200

    data = response.json()
    tags = data["tags"]

    # Should be sorted by count descending
    assert tags[0]["name"] == "common"
    assert tags[0]["count"] == 3
    assert tags[1]["name"] == "medium"
    assert tags[1]["count"] == 2
    assert tags[2]["name"] == "rare"
    assert tags[2]["count"] == 1


async def test_list_tags_alphabetical_tiebreak(client: AsyncClient) -> None:
    """Test that tags with same count are sorted alphabetically."""
    await client.post(
        "/bookmarks/",
        json={"url": "https://ex1.com", "tags": ["zebra", "apple", "banana"]},
    )

    response = await client.get("/tags/")
    assert response.status_code == 200

    data = response.json()
    tags = data["tags"]

    # All have count 1, should be sorted alphabetically
    tag_names = [tag["name"] for tag in tags]
    assert tag_names == ["apple", "banana", "zebra"]


async def test_list_tags_response_format(client: AsyncClient) -> None:
    """Test that tags response has correct format."""
    await client.post(
        "/bookmarks/",
        json={"url": "https://example.com", "tags": ["test"]},
    )

    response = await client.get("/tags/")
    assert response.status_code == 200

    data = response.json()
    assert "tags" in data
    assert isinstance(data["tags"], list)
    assert len(data["tags"]) == 1
    assert "name" in data["tags"][0]
    assert "count" in data["tags"][0]
    assert data["tags"][0]["name"] == "test"
    assert data["tags"][0]["count"] == 1


async def test_list_tags_bookmark_without_tags(client: AsyncClient) -> None:
    """Test that bookmarks without tags don't affect tag list."""
    await client.post(
        "/bookmarks/",
        json={"url": "https://no-tags.com", "title": "No tags"},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://with-tags.com", "tags": ["python"]},
    )

    response = await client.get("/tags/")
    assert response.status_code == 200

    data = response.json()
    assert len(data["tags"]) == 1
    assert data["tags"][0]["name"] == "python"
    assert data["tags"][0]["count"] == 1


async def test_list_tags_excludes_archived_and_deleted_bookmarks(client: AsyncClient) -> None:
    """Test that tags from archived and deleted bookmarks are not included."""
    # Create three bookmarks with different tags
    # Active bookmark - tags should be counted
    await client.post(
        "/bookmarks/",
        json={"url": "https://active.com", "tags": ["active-tag", "shared-tag"]},
    )

    # Bookmark to be archived - tags should NOT be counted
    archived_response = await client.post(
        "/bookmarks/",
        json={"url": "https://archived.com", "tags": ["archived-tag", "shared-tag"]},
    )
    archived_id = archived_response.json()["id"]
    await client.post(f"/bookmarks/{archived_id}/archive")

    # Bookmark to be deleted - tags should NOT be counted
    deleted_response = await client.post(
        "/bookmarks/",
        json={"url": "https://deleted.com", "tags": ["deleted-tag", "shared-tag"]},
    )
    deleted_id = deleted_response.json()["id"]
    await client.delete(f"/bookmarks/{deleted_id}")

    # Get tags - should only include tags from active bookmark
    response = await client.get("/tags/")
    assert response.status_code == 200

    data = response.json()
    tag_counts = {tag["name"]: tag["count"] for tag in data["tags"]}

    # Only active bookmark's tags should be present
    assert "active-tag" in tag_counts
    assert tag_counts["active-tag"] == 1

    # shared-tag should only have count of 1 (from active bookmark only)
    assert "shared-tag" in tag_counts
    assert tag_counts["shared-tag"] == 1

    # Tags exclusive to archived/deleted bookmarks should not appear
    assert "archived-tag" not in tag_counts
    assert "deleted-tag" not in tag_counts
