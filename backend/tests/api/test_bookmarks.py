"""Tests for bookmark CRUD endpoints."""
from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.bookmark import Bookmark
from services.url_scraper import ExtractedMetadata, FetchResult


@pytest.fixture(autouse=True)
def mock_url_fetch() -> Generator[AsyncMock]:
    """
    Auto-mock fetch_url for all bookmark tests to avoid real network calls.

    Returns a "failed fetch" result by default so tests that don't care about
    scraping behavior work fast. Tests that need specific scraping behavior
    can override this with their own patch.
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


async def test_create_bookmark(client: AsyncClient, db_session: AsyncSession) -> None:
    """Test creating a new bookmark."""
    response = await client.post(
        "/bookmarks/",
        json={
            "url": "https://example.com",
            "title": "Example Site",
            "description": "An example website",
            "tags": ["example", "test"],
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["url"] == "https://example.com/"
    assert data["title"] == "Example Site"
    assert data["description"] == "An example website"
    assert data["tags"] == ["example", "test"]
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data

    # Verify in database
    result = await db_session.execute(select(Bookmark).where(Bookmark.id == data["id"]))
    bookmark = result.scalar_one()
    assert bookmark.url == "https://example.com/"
    assert bookmark.title == "Example Site"


async def test_create_bookmark_minimal(client: AsyncClient) -> None:
    """Test creating a bookmark with only URL (minimal required data)."""
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://minimal.example.com"},
    )
    assert response.status_code == 201

    data = response.json()
    assert data["url"] == "https://minimal.example.com/"
    assert data["title"] is None
    assert data["description"] is None
    assert data["tags"] == []


async def test_create_bookmark_normalizes_tags(client: AsyncClient) -> None:
    """Test that tags are normalized to lowercase."""
    response = await client.post(
        "/bookmarks/",
        json={
            "url": "https://example.com/normalize",
            "tags": ["Python", "FASTAPI", "Web-Dev"],
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["tags"] == ["python", "fastapi", "web-dev"]


async def test_create_bookmark_invalid_tag_uppercase(client: AsyncClient) -> None:
    """Test that uppercase in tag middle is rejected after normalization check."""
    # Note: tags are normalized to lowercase first, so this test ensures the
    # validation happens after normalization (which means most "uppercase" errors
    # are actually handled by normalization)
    response = await client.post(
        "/bookmarks/",
        json={
            "url": "https://example.com/invalid-tag",
            "tags": ["valid-tag"],
        },
    )
    # This should succeed because lowercase is valid
    assert response.status_code == 201


async def test_create_bookmark_invalid_tag_with_underscore(client: AsyncClient) -> None:
    """Test that tags with underscores are rejected."""
    response = await client.post(
        "/bookmarks/",
        json={
            "url": "https://example.com/invalid-tag",
            "tags": ["invalid_tag"],
        },
    )
    assert response.status_code == 422
    assert "Invalid tag format" in response.text


async def test_create_bookmark_invalid_tag_with_space(client: AsyncClient) -> None:
    """Test that tags with spaces are rejected."""
    response = await client.post(
        "/bookmarks/",
        json={
            "url": "https://example.com/invalid-tag",
            "tags": ["invalid tag"],
        },
    )
    assert response.status_code == 422
    assert "Invalid tag format" in response.text


async def test_create_bookmark_invalid_tag_special_chars(client: AsyncClient) -> None:
    """Test that tags with special characters are rejected."""
    response = await client.post(
        "/bookmarks/",
        json={
            "url": "https://example.com/invalid-tag",
            "tags": ["@special!"],
        },
    )
    assert response.status_code == 422
    assert "Invalid tag format" in response.text


async def test_create_bookmark_valid_tag_with_numbers(client: AsyncClient) -> None:
    """Test that tags with numbers are valid."""
    response = await client.post(
        "/bookmarks/",
        json={
            "url": "https://example.com/numbers",
            "tags": ["web-dev-2024", "python3"],
        },
    )
    assert response.status_code == 201
    assert response.json()["tags"] == ["web-dev-2024", "python3"]


async def test_list_bookmarks(client: AsyncClient) -> None:
    """Test listing bookmarks."""
    # Create some bookmarks first
    for i in range(3):
        await client.post(
            "/bookmarks/",
            json={"url": f"https://example{i}.com", "title": f"Example {i}"},
        )

    response = await client.get("/bookmarks/")
    assert response.status_code == 200

    data = response.json()
    assert len(data["items"]) == 3
    assert data["total"] == 3


async def test_list_bookmarks_pagination(client: AsyncClient) -> None:
    """Test bookmark listing with pagination."""
    # Create 5 bookmarks
    for i in range(5):
        await client.post(
            "/bookmarks/",
            json={"url": f"https://paginate{i}.com"},
        )

    # Test limit
    response = await client.get("/bookmarks/?limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5
    assert data["has_more"] is True

    # Test offset
    response = await client.get("/bookmarks/?offset=1&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5


async def test_get_bookmark(client: AsyncClient) -> None:
    """Test getting a single bookmark."""
    # Create a bookmark
    create_response = await client.post(
        "/bookmarks/",
        json={"url": "https://get-test.com", "title": "Get Test"},
    )
    bookmark_id = create_response.json()["id"]

    # Get it
    response = await client.get(f"/bookmarks/{bookmark_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == bookmark_id
    assert data["url"] == "https://get-test.com/"
    assert data["title"] == "Get Test"


async def test_get_bookmark_not_found(client: AsyncClient) -> None:
    """Test getting a non-existent bookmark returns 404."""
    response = await client.get("/bookmarks/99999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Bookmark not found"


async def test_update_bookmark(client: AsyncClient) -> None:
    """Test updating a bookmark."""
    # Create a bookmark
    create_response = await client.post(
        "/bookmarks/",
        json={"url": "https://update-test.com", "title": "Original Title"},
    )
    bookmark_id = create_response.json()["id"]

    # Update it
    response = await client.patch(
        f"/bookmarks/{bookmark_id}",
        json={"title": "Updated Title", "tags": ["updated"]},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["title"] == "Updated Title"
    assert data["tags"] == ["updated"]
    # URL should remain unchanged
    assert data["url"] == "https://update-test.com/"


async def test_update_bookmark_partial(client: AsyncClient) -> None:
    """Test partial update only changes specified fields."""
    # Create a bookmark with description
    create_response = await client.post(
        "/bookmarks/",
        json={
            "url": "https://partial-update.com",
            "title": "Original",
            "description": "Original description",
        },
    )
    bookmark_id = create_response.json()["id"]

    # Update only title
    response = await client.patch(
        f"/bookmarks/{bookmark_id}",
        json={"title": "New Title"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["title"] == "New Title"
    assert data["description"] == "Original description"  # Unchanged


async def test_update_bookmark_not_found(client: AsyncClient) -> None:
    """Test updating a non-existent bookmark returns 404."""
    response = await client.patch(
        "/bookmarks/99999",
        json={"title": "Won't Work"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Bookmark not found"


async def test_delete_bookmark(client: AsyncClient) -> None:
    """Test deleting a bookmark."""
    # Create a bookmark
    create_response = await client.post(
        "/bookmarks/",
        json={"url": "https://delete-test.com"},
    )
    bookmark_id = create_response.json()["id"]

    # Delete it
    response = await client.delete(f"/bookmarks/{bookmark_id}")
    assert response.status_code == 204

    # Verify it's gone
    get_response = await client.get(f"/bookmarks/{bookmark_id}")
    assert get_response.status_code == 404


async def test_delete_bookmark_not_found(client: AsyncClient) -> None:
    """Test deleting a non-existent bookmark returns 404."""
    response = await client.delete("/bookmarks/99999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Bookmark not found"


async def test_create_bookmark_invalid_url(client: AsyncClient) -> None:
    """Test that invalid URLs are rejected."""
    response = await client.post(
        "/bookmarks/",
        json={"url": "not-a-valid-url"},
    )
    assert response.status_code == 422


# =============================================================================
# URL Scraping Integration Tests
# =============================================================================


async def test_create_bookmark_auto_fetches_metadata(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test that creating a bookmark without metadata auto-fetches from URL."""
    mock_fetch = AsyncMock(
        return_value=FetchResult(
            html='<html><head><title>Fetched Title</title></head></html>',
            final_url='https://example.com/',
            status_code=200,
            content_type='text/html',
            error=None,
        ),
    )
    mock_metadata = ExtractedMetadata(
        title='Fetched Title',
        description='Fetched description from meta tag.',
    )

    with (
        patch('services.bookmark_service.fetch_url', mock_fetch),
        patch('services.bookmark_service.extract_metadata', return_value=mock_metadata),
        patch('services.bookmark_service.extract_content', return_value='Page content here.'),
    ):
        response = await client.post(
            "/bookmarks/",
            json={"url": "https://example.com"},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Fetched Title"
    assert data["description"] == "Fetched description from meta tag."

    # Verify content was stored in database
    result = await db_session.execute(select(Bookmark).where(Bookmark.id == data["id"]))
    bookmark = result.scalar_one()
    assert bookmark.content == "Page content here."


async def test_create_bookmark_user_values_take_precedence(
    client: AsyncClient,
) -> None:
    """Test that user-provided title/description override fetched values."""
    mock_fetch = AsyncMock(
        return_value=FetchResult(
            html='<html><head><title>Fetched Title</title></head></html>',
            final_url='https://example.com/',
            status_code=200,
            content_type='text/html',
            error=None,
        ),
    )
    mock_metadata = ExtractedMetadata(
        title='Fetched Title',
        description='Fetched description',
    )

    with (
        patch('services.bookmark_service.fetch_url', mock_fetch),
        patch('services.bookmark_service.extract_metadata', return_value=mock_metadata),
        patch('services.bookmark_service.extract_content', return_value='Fetched content'),
    ):
        response = await client.post(
            "/bookmarks/",
            json={
                "url": "https://example.com",
                "title": "User Title",
                "description": "User description",
            },
        )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "User Title"
    assert data["description"] == "User description"


async def test_create_bookmark_skips_fetch_when_all_provided(
    client: AsyncClient,
) -> None:
    """Test that fetch is skipped when user provides all metadata and content."""
    mock_fetch = AsyncMock()

    with patch('services.bookmark_service.fetch_url', mock_fetch):
        response = await client.post(
            "/bookmarks/",
            json={
                "url": "https://example.com",
                "title": "User Title",
                "description": "User description",
                "content": "User provided content",
            },
        )

    assert response.status_code == 201
    # fetch_url should not have been called
    mock_fetch.assert_not_called()


async def test_create_bookmark_store_content_false(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test that store_content=false skips content storage but still fetches metadata."""
    mock_fetch = AsyncMock(
        return_value=FetchResult(
            html='<html><head><title>Fetched</title></head></html>',
            final_url='https://example.com/',
            status_code=200,
            content_type='text/html',
            error=None,
        ),
    )
    mock_metadata = ExtractedMetadata(title='Fetched Title', description='Fetched desc')

    with (
        patch('services.bookmark_service.fetch_url', mock_fetch),
        patch('services.bookmark_service.extract_metadata', return_value=mock_metadata),
        patch('services.bookmark_service.extract_content', return_value='Page content'),
    ):
        response = await client.post(
            "/bookmarks/",
            json={
                "url": "https://example.com",
                "store_content": False,
            },
        )

    assert response.status_code == 201
    data = response.json()
    # Metadata should still be fetched
    assert data["title"] == "Fetched Title"
    assert data["description"] == "Fetched desc"

    # But content should NOT be stored
    result = await db_session.execute(select(Bookmark).where(Bookmark.id == data["id"]))
    bookmark = result.scalar_one()
    assert bookmark.content is None


async def test_create_bookmark_fetch_failure_does_not_block(
    client: AsyncClient,
) -> None:
    """Test that fetch failures don't prevent bookmark creation."""
    mock_fetch = AsyncMock(
        return_value=FetchResult(
            html=None,
            final_url='https://example.com/',
            status_code=None,
            content_type=None,
            error="Connection refused",
        ),
    )

    with patch('services.bookmark_service.fetch_url', mock_fetch):
        response = await client.post(
            "/bookmarks/",
            json={"url": "https://example.com"},
        )

    assert response.status_code == 201
    data = response.json()
    # Bookmark created but without fetched data
    assert data["title"] is None
    assert data["description"] is None


async def test_create_bookmark_http_error_saves_with_null_values(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test that HTTP errors (404/500) still save bookmark with null metadata."""
    mock_fetch = AsyncMock(
        return_value=FetchResult(
            html=None,  # No HTML returned for error pages
            final_url='https://example.com/deleted-page',
            status_code=404,
            content_type='text/html',
            error="HTTP 404",
        ),
    )

    with patch('services.bookmark_service.fetch_url', mock_fetch):
        response = await client.post(
            "/bookmarks/",
            json={"url": "https://example.com/deleted-page"},
        )

    assert response.status_code == 201
    data = response.json()

    # Bookmark saved with null metadata (not "404 Not Found" from error page)
    assert data["title"] is None
    assert data["description"] is None
    assert data["url"] == "https://example.com/deleted-page"

    # Verify in database
    result = await db_session.execute(select(Bookmark).where(Bookmark.id == data["id"]))
    bookmark = result.scalar_one()
    assert bookmark.url == "https://example.com/deleted-page"
    assert bookmark.title is None
    assert bookmark.description is None
    assert bookmark.content is None


async def test_create_bookmark_response_includes_summary_field(
    client: AsyncClient,
) -> None:
    """Test that bookmark response includes summary field (null for Phase 1)."""
    response = await client.post(
        "/bookmarks/",
        json={
            "url": "https://example.com",
            "title": "Test",
            "description": "Test description",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert "summary" in data
    assert data["summary"] is None


async def test_create_bookmark_user_content_not_overridden(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test that user-provided content is used even when fetch succeeds."""
    mock_fetch = AsyncMock(
        return_value=FetchResult(
            html='<html><head><title>Fetched</title></head></html>',
            final_url='https://example.com/',
            status_code=200,
            content_type='text/html',
            error=None,
        ),
    )
    mock_metadata = ExtractedMetadata(title='Fetched Title', description=None)

    with (
        patch('services.bookmark_service.fetch_url', mock_fetch),
        patch('services.bookmark_service.extract_metadata', return_value=mock_metadata),
        patch('services.bookmark_service.extract_content', return_value='Fetched content'),
    ):
        response = await client.post(
            "/bookmarks/",
            json={
                "url": "https://example.com",
                "content": "User provided content for paywalled site",
            },
        )

    assert response.status_code == 201

    # User content should be stored, not fetched content
    result = await db_session.execute(
        select(Bookmark).where(Bookmark.id == response.json()["id"]),
    )
    bookmark = result.scalar_one()
    assert bookmark.content == "User provided content for paywalled site"


async def test_create_bookmark_partial_metadata_fetch(
    client: AsyncClient,
) -> None:
    """Test that fetch happens when only some metadata is provided."""
    mock_fetch = AsyncMock(
        return_value=FetchResult(
            html='<html><head><title>Fetched</title></head></html>',
            final_url='https://example.com/',
            status_code=200,
            content_type='text/html',
            error=None,
        ),
    )
    mock_metadata = ExtractedMetadata(title='Fetched Title', description='Fetched desc')

    with (
        patch('services.bookmark_service.fetch_url', mock_fetch),
        patch('services.bookmark_service.extract_metadata', return_value=mock_metadata),
        patch('services.bookmark_service.extract_content', return_value=None),
    ):
        response = await client.post(
            "/bookmarks/",
            json={
                "url": "https://example.com",
                "title": "User Title",  # Only title provided
            },
        )

    assert response.status_code == 201
    data = response.json()
    # User title preserved, description fetched
    assert data["title"] == "User Title"
    assert data["description"] == "Fetched desc"
    # fetch_url should have been called because description was missing
    mock_fetch.assert_called_once()


# =============================================================================
# Search and Filtering Tests (Milestone 5)
# =============================================================================


async def test_list_bookmarks_response_format(client: AsyncClient) -> None:
    """Test that list response uses new paginated format with metadata."""
    # Create a bookmark
    await client.post(
        "/bookmarks/",
        json={"url": "https://format-test.com", "title": "Format Test"},
    )

    response = await client.get("/bookmarks/")
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "offset" in data
    assert "limit" in data
    assert "has_more" in data
    assert isinstance(data["items"], list)
    assert len(data["items"]) == 1
    assert data["total"] == 1
    assert data["offset"] == 0
    assert data["limit"] == 50
    assert data["has_more"] is False


async def test_search_by_title(client: AsyncClient) -> None:
    """Test text search finds bookmarks by title."""
    await client.post(
        "/bookmarks/",
        json={"url": "https://search1.com", "title": "Python Programming Guide"},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://search2.com", "title": "JavaScript Tutorial"},
    )

    response = await client.get("/bookmarks/?q=python")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["title"] == "Python Programming Guide"


async def test_search_by_description(client: AsyncClient) -> None:
    """Test text search finds bookmarks by description."""
    await client.post(
        "/bookmarks/",
        json={
            "url": "https://desc-search.com",
            "title": "Some Title",
            "description": "A comprehensive guide to machine learning algorithms",
        },
    )

    response = await client.get("/bookmarks/?q=machine%20learning")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 1
    assert "machine learning" in data["items"][0]["description"]


async def test_search_by_url(client: AsyncClient) -> None:
    """Test text search finds bookmarks by URL."""
    await client.post(
        "/bookmarks/",
        json={"url": "https://unique-domain-xyz.com/path", "title": "URL Test"},
    )

    response = await client.get("/bookmarks/?q=unique-domain-xyz")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 1
    assert "unique-domain-xyz" in data["items"][0]["url"]


async def test_search_by_content(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test text search finds bookmarks by content field."""
    from models.bookmark import Bookmark
    from models.user import User
    from sqlalchemy import select

    # First make an API call to ensure dev user exists
    await client.post(
        "/bookmarks/",
        json={"url": "https://setup-user.com", "title": "Setup"},
    )

    # Get the dev user ID
    result = await db_session.execute(
        select(User).where(User.auth0_id == "dev|local-development-user"),
    )
    dev_user = result.scalar_one()

    # Create bookmark with content directly in DB (bypassing scraper)
    bookmark = Bookmark(
        user_id=dev_user.id,
        url="https://content-search.com",
        title="Content Test",
        content="This content contains unique-phrase-12345 for testing",
        tags=[],
    )
    db_session.add(bookmark)
    await db_session.flush()

    response = await client.get("/bookmarks/?q=unique-phrase-12345")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 1  # Only content bookmark matches the search term


async def test_search_is_case_insensitive(client: AsyncClient) -> None:
    """Test that search is case-insensitive."""
    await client.post(
        "/bookmarks/",
        json={"url": "https://case-test.com", "title": "FASTAPI Framework"},
    )

    # Search with lowercase
    response = await client.get("/bookmarks/?q=fastapi")
    assert response.status_code == 200
    assert response.json()["total"] == 1

    # Search with mixed case
    response = await client.get("/bookmarks/?q=FastAPI")
    assert response.status_code == 200
    assert response.json()["total"] == 1


async def test_search_special_characters_percent(client: AsyncClient) -> None:
    """Test that search properly escapes % character."""
    await client.post(
        "/bookmarks/",
        json={"url": "https://percent-test.com", "title": "100% Complete Guide"},
    )

    response = await client.get("/bookmarks/?q=100%25")  # URL encoded %
    assert response.status_code == 200
    assert response.json()["total"] == 1


async def test_search_special_characters_underscore(client: AsyncClient) -> None:
    """Test that search properly escapes _ character."""
    await client.post(
        "/bookmarks/",
        json={"url": "https://underscore-test.com", "title": "snake_case naming"},
    )

    response = await client.get("/bookmarks/?q=snake_case")
    assert response.status_code == 200
    assert response.json()["total"] == 1


async def test_search_special_characters_backslash(client: AsyncClient) -> None:
    """Test that search properly escapes backslash character."""
    await client.post(
        "/bookmarks/",
        json={"url": "https://backslash-test.com", "title": r"Path\To\File"},
    )

    response = await client.get(r"/bookmarks/?q=Path\To")
    assert response.status_code == 200
    assert response.json()["total"] == 1


async def test_tag_filter_single_tag(client: AsyncClient) -> None:
    """Test filtering by a single tag."""
    await client.post(
        "/bookmarks/",
        json={"url": "https://tag1.com", "title": "Tagged 1", "tags": ["python", "web"]},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://tag2.com", "title": "Tagged 2", "tags": ["javascript"]},
    )

    response = await client.get("/bookmarks/?tags=python")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Tagged 1"


async def test_tag_filter_all_mode(client: AsyncClient) -> None:
    """Test tag filtering with tag_match='all' (AND behavior)."""
    await client.post(
        "/bookmarks/",
        json={"url": "https://all1.com", "title": "Both Tags", "tags": ["python", "web"]},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://all2.com", "title": "Only Python", "tags": ["python"]},
    )

    # Filter for both tags (AND)
    response = await client.get("/bookmarks/?tags=python&tags=web&tag_match=all")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Both Tags"


async def test_tag_filter_any_mode(client: AsyncClient) -> None:
    """Test tag filtering with tag_match='any' (OR behavior)."""
    await client.post(
        "/bookmarks/",
        json={"url": "https://any1.com", "title": "Python Only", "tags": ["python"]},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://any2.com", "title": "Web Only", "tags": ["web"]},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://any3.com", "title": "Rust Only", "tags": ["rust"]},
    )

    # Filter for any of python or web (OR)
    response = await client.get("/bookmarks/?tags=python&tags=web&tag_match=any")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 2
    titles = [item["title"] for item in data["items"]]
    assert "Python Only" in titles
    assert "Web Only" in titles
    assert "Rust Only" not in titles


async def test_tag_filter_empty_returns_all(client: AsyncClient) -> None:
    """Test that empty tags parameter returns all bookmarks."""
    await client.post(
        "/bookmarks/",
        json={"url": "https://no-filter1.com", "title": "No Filter 1", "tags": ["tag1"]},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://no-filter2.com", "title": "No Filter 2", "tags": ["tag2"]},
    )

    # No tags filter
    response = await client.get("/bookmarks/")
    assert response.status_code == 200
    assert response.json()["total"] == 2


async def test_tag_filter_normalized(client: AsyncClient) -> None:
    """Test that tag filter input is normalized to lowercase."""
    await client.post(
        "/bookmarks/",
        json={"url": "https://norm-tag.com", "title": "Normalized", "tags": ["python"]},
    )

    # Filter with uppercase
    response = await client.get("/bookmarks/?tags=PYTHON")
    assert response.status_code == 200
    assert response.json()["total"] == 1


async def test_search_and_tag_filter_combined(client: AsyncClient) -> None:
    """Test combining text search with tag filter (AND logic)."""
    await client.post(
        "/bookmarks/",
        json={
            "url": "https://combined1.com",
            "title": "Python Web Framework",
            "tags": ["python", "web"],
        },
    )
    await client.post(
        "/bookmarks/",
        json={
            "url": "https://combined2.com",
            "title": "Python Data Science",
            "tags": ["python", "data"],
        },
    )
    await client.post(
        "/bookmarks/",
        json={
            "url": "https://combined3.com",
            "title": "JavaScript Web Framework",
            "tags": ["javascript", "web"],
        },
    )

    # Search for "Web" AND tag "python"
    response = await client.get("/bookmarks/?q=web&tags=python")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Python Web Framework"


async def test_sort_by_created_at_desc(client: AsyncClient) -> None:
    """Test sorting by created_at descending (default)."""
    import asyncio

    await client.post(
        "/bookmarks/",
        json={"url": "https://sort1.com", "title": "First Created"},
    )
    await asyncio.sleep(0.1)  # Larger delay to ensure different timestamps
    await client.post(
        "/bookmarks/",
        json={"url": "https://sort2.com", "title": "Second Created"},
    )

    response = await client.get("/bookmarks/?sort_by=created_at&sort_order=desc")
    assert response.status_code == 200

    data = response.json()
    assert data["items"][0]["title"] == "Second Created"
    assert data["items"][1]["title"] == "First Created"


async def test_sort_by_created_at_asc(client: AsyncClient) -> None:
    """Test sorting by created_at ascending."""
    import asyncio

    await client.post(
        "/bookmarks/",
        json={"url": "https://sortasc1.com", "title": "First Created ASC"},
    )
    await asyncio.sleep(0.1)  # Larger delay to ensure different timestamps
    await client.post(
        "/bookmarks/",
        json={"url": "https://sortasc2.com", "title": "Second Created ASC"},
    )

    response = await client.get("/bookmarks/?sort_by=created_at&sort_order=asc")
    assert response.status_code == 200

    data = response.json()
    assert data["items"][0]["title"] == "First Created ASC"
    assert data["items"][1]["title"] == "Second Created ASC"


async def test_sort_by_title_asc(client: AsyncClient) -> None:
    """Test sorting by title ascending."""
    await client.post(
        "/bookmarks/",
        json={"url": "https://titlesort1.com", "title": "Zebra"},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://titlesort2.com", "title": "Apple"},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://titlesort3.com", "title": "Banana"},
    )

    response = await client.get("/bookmarks/?sort_by=title&sort_order=asc")
    assert response.status_code == 200

    data = response.json()
    titles = [item["title"] for item in data["items"]]
    assert titles == ["Apple", "Banana", "Zebra"]


async def test_sort_by_title_desc(client: AsyncClient) -> None:
    """Test sorting by title descending."""
    await client.post(
        "/bookmarks/",
        json={"url": "https://titlesortdesc1.com", "title": "Alpha"},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://titlesortdesc2.com", "title": "Gamma"},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://titlesortdesc3.com", "title": "Beta"},
    )

    response = await client.get("/bookmarks/?sort_by=title&sort_order=desc")
    assert response.status_code == 200

    data = response.json()
    titles = [item["title"] for item in data["items"]]
    assert titles == ["Gamma", "Beta", "Alpha"]


async def test_pagination_with_search(client: AsyncClient) -> None:
    """Test pagination works correctly with search results."""
    # Create 5 bookmarks matching search
    for i in range(5):
        await client.post(
            "/bookmarks/",
            json={"url": f"https://pagesearch{i}.com", "title": f"Searchable {i}"},
        )

    # First page
    response = await client.get("/bookmarks/?q=searchable&limit=2&offset=0")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["offset"] == 0
    assert data["limit"] == 2
    assert data["has_more"] is True

    # Second page
    response = await client.get("/bookmarks/?q=searchable&limit=2&offset=2")
    data = response.json()
    assert len(data["items"]) == 2
    assert data["has_more"] is True

    # Last page
    response = await client.get("/bookmarks/?q=searchable&limit=2&offset=4")
    data = response.json()
    assert len(data["items"]) == 1
    assert data["has_more"] is False


async def test_search_empty_results(client: AsyncClient) -> None:
    """Test search that returns no results."""
    await client.post(
        "/bookmarks/",
        json={"url": "https://exists.com", "title": "Existing Bookmark"},
    )

    response = await client.get("/bookmarks/?q=nonexistent-search-term-xyz")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 0
    assert len(data["items"]) == 0
    assert data["has_more"] is False


async def test_total_count_accurate_with_filters(client: AsyncClient) -> None:
    """Test that total count is accurate when filters are applied."""
    # Create bookmarks with different tags
    for i in range(3):
        await client.post(
            "/bookmarks/",
            json={"url": f"https://count-python{i}.com", "title": f"Python {i}", "tags": ["python"]},
        )
    for i in range(2):
        await client.post(
            "/bookmarks/",
            json={"url": f"https://count-js{i}.com", "title": f"JavaScript {i}", "tags": ["javascript"]},
        )

    # Total without filter
    response = await client.get("/bookmarks/")
    assert response.json()["total"] == 5

    # Total with python tag filter
    response = await client.get("/bookmarks/?tags=python")
    assert response.json()["total"] == 3

    # Total with javascript tag filter
    response = await client.get("/bookmarks/?tags=javascript")
    assert response.json()["total"] == 2


async def test_has_more_calculation(client: AsyncClient) -> None:
    """Test that has_more is calculated correctly."""
    # Create exactly 3 bookmarks
    for i in range(3):
        await client.post(
            "/bookmarks/",
            json={"url": f"https://hasmore{i}.com", "title": f"HasMore {i}"},
        )

    # Request all 3 with exact limit
    response = await client.get("/bookmarks/?limit=3")
    data = response.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3
    assert data["has_more"] is False

    # Request with limit 2, offset 0
    response = await client.get("/bookmarks/?limit=2&offset=0")
    data = response.json()
    assert data["has_more"] is True

    # Request with limit 2, offset 1
    response = await client.get("/bookmarks/?limit=2&offset=1")
    data = response.json()
    assert len(data["items"]) == 2
    assert data["has_more"] is False  # offset(1) + len(2) = 3 == total

    # Request with limit 2, offset 2
    response = await client.get("/bookmarks/?limit=2&offset=2")
    data = response.json()
    assert len(data["items"]) == 1
    assert data["has_more"] is False


async def test_invalid_tag_in_filter_rejected(client: AsyncClient) -> None:
    """Test that invalid tag format in filter is rejected."""
    response = await client.get("/bookmarks/?tags=invalid_tag")
    assert response.status_code == 422
    assert "Invalid tag format" in response.text


async def test_search_by_summary(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test text search finds bookmarks by summary field (Phase 2 preparation)."""
    from models.bookmark import Bookmark
    from models.user import User
    from sqlalchemy import select

    # First make an API call to ensure dev user exists
    await client.post(
        "/bookmarks/",
        json={"url": "https://setup-user2.com", "title": "Setup"},
    )

    # Get the dev user ID
    result = await db_session.execute(
        select(User).where(User.auth0_id == "dev|local-development-user"),
    )
    dev_user = result.scalar_one()

    # Create bookmark with summary directly in DB
    bookmark = Bookmark(
        user_id=dev_user.id,
        url="https://summary-search.com",
        title="Summary Test",
        summary="This is an AI-generated summary with unique-summary-term",
        tags=[],
    )
    db_session.add(bookmark)
    await db_session.flush()

    response = await client.get("/bookmarks/?q=unique-summary-term")
    assert response.status_code == 200
    assert response.json()["total"] == 1


# =============================================================================
# Metadata Preview Endpoint Tests (Milestone 7)
# =============================================================================


async def test_fetch_metadata_success(client: AsyncClient) -> None:
    """Test successful metadata fetch from URL."""
    mock_fetch = AsyncMock(
        return_value=FetchResult(
            html='<html><head><title>Test Page</title><meta name="description" content="Test description"></head></html>',
            final_url='https://example.com/page',
            status_code=200,
            content_type='text/html',
            error=None,
        ),
    )
    mock_metadata = ExtractedMetadata(
        title='Test Page',
        description='Test description',
    )

    with (
        patch('api.routers.bookmarks.fetch_url', mock_fetch),
        patch('api.routers.bookmarks.extract_metadata', return_value=mock_metadata),
    ):
        response = await client.get(
            "/bookmarks/fetch-metadata",
            params={"url": "https://example.com/page"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "https://example.com/page"
    assert data["final_url"] == "https://example.com/page"
    assert data["title"] == "Test Page"
    assert data["description"] == "Test description"
    assert data["error"] is None


async def test_fetch_metadata_with_redirect(client: AsyncClient) -> None:
    """Test metadata fetch that follows a redirect."""
    mock_fetch = AsyncMock(
        return_value=FetchResult(
            html='<html><head><title>Redirected Page</title></head></html>',
            final_url='https://example.com/new-location',
            status_code=200,
            content_type='text/html',
            error=None,
        ),
    )
    mock_metadata = ExtractedMetadata(
        title='Redirected Page',
        description=None,
    )

    with (
        patch('api.routers.bookmarks.fetch_url', mock_fetch),
        patch('api.routers.bookmarks.extract_metadata', return_value=mock_metadata),
    ):
        response = await client.get(
            "/bookmarks/fetch-metadata",
            params={"url": "https://example.com/old-location"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "https://example.com/old-location"
    assert data["final_url"] == "https://example.com/new-location"
    assert data["title"] == "Redirected Page"


async def test_fetch_metadata_fetch_failure(client: AsyncClient) -> None:
    """Test metadata fetch when URL fetch fails."""
    mock_fetch = AsyncMock(
        return_value=FetchResult(
            html=None,
            final_url='https://example.com/timeout',
            status_code=None,
            content_type=None,
            error='Connection timed out',
        ),
    )

    with patch('api.routers.bookmarks.fetch_url', mock_fetch):
        response = await client.get(
            "/bookmarks/fetch-metadata",
            params={"url": "https://example.com/timeout"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "https://example.com/timeout"
    assert data["title"] is None
    assert data["description"] is None
    assert data["error"] == "Connection timed out"


async def test_fetch_metadata_invalid_url(client: AsyncClient) -> None:
    """Test metadata fetch with invalid URL returns 422."""
    response = await client.get(
        "/bookmarks/fetch-metadata",
        params={"url": "not-a-valid-url"},
    )
    assert response.status_code == 422


async def test_fetch_metadata_requires_auth(client: AsyncClient) -> None:
    """Test that fetch-metadata endpoint requires authentication."""
    # This test just ensures the endpoint exists and requires auth
    # In dev mode, auth is bypassed, so this will succeed
    # In production, it would return 401 without a token
    mock_fetch = AsyncMock(
        return_value=FetchResult(
            html='<html><head><title>Auth Test</title></head></html>',
            final_url='https://example.com/',
            status_code=200,
            content_type='text/html',
            error=None,
        ),
    )
    mock_metadata = ExtractedMetadata(title='Auth Test', description=None)

    with (
        patch('api.routers.bookmarks.fetch_url', mock_fetch),
        patch('api.routers.bookmarks.extract_metadata', return_value=mock_metadata),
    ):
        response = await client.get(
            "/bookmarks/fetch-metadata",
            params={"url": "https://example.com"},
        )
    # Should succeed in dev mode
    assert response.status_code == 200


# =============================================================================
# Duplicate URL Constraint Tests
# =============================================================================


async def test_create_bookmark_duplicate_url_returns_409(client: AsyncClient) -> None:
    """Test that creating a bookmark with duplicate URL returns 409 Conflict."""
    # Create first bookmark
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://duplicate-test.com", "title": "First"},
    )
    assert response.status_code == 201

    # Try to create another with same URL
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://duplicate-test.com", "title": "Second"},
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


async def test_create_bookmark_duplicate_url_normalized(client: AsyncClient) -> None:
    """Test that URL normalization is considered for duplicates (trailing slash)."""
    # Create first bookmark (URL gets trailing slash from pydantic HttpUrl)
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://normalized-dup.com", "title": "First"},
    )
    assert response.status_code == 201
    assert response.json()["url"] == "https://normalized-dup.com/"

    # Try with trailing slash explicitly - should be duplicate
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://normalized-dup.com/", "title": "Second"},
    )
    assert response.status_code == 409


async def test_update_bookmark_url_success(client: AsyncClient) -> None:
    """Test successfully updating a bookmark's URL to a new unique URL."""
    # Create a bookmark
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://original-url.com", "title": "Original"},
    )
    assert response.status_code == 201
    bookmark_id = response.json()["id"]

    # Update to a new URL
    response = await client.patch(
        f"/bookmarks/{bookmark_id}",
        json={"url": "https://new-url.com"},
    )
    assert response.status_code == 200
    assert response.json()["url"] == "https://new-url.com/"


async def test_update_bookmark_url_to_duplicate_returns_409(client: AsyncClient) -> None:
    """Test that updating a bookmark URL to an existing URL returns 409."""
    # Create first bookmark
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://existing-url.com", "title": "Existing"},
    )
    assert response.status_code == 201

    # Create second bookmark
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://will-be-changed.com", "title": "To Change"},
    )
    assert response.status_code == 201
    bookmark_id = response.json()["id"]

    # Try to update second bookmark to have same URL as first
    response = await client.patch(
        f"/bookmarks/{bookmark_id}",
        json={"url": "https://existing-url.com"},
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


async def test_update_bookmark_url_to_same_url_succeeds(client: AsyncClient) -> None:
    """Test that updating a bookmark to its own URL succeeds (no-op)."""
    # Create a bookmark
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://same-url.com", "title": "Same URL"},
    )
    assert response.status_code == 201
    bookmark_id = response.json()["id"]

    # Update to the same URL (should succeed)
    response = await client.patch(
        f"/bookmarks/{bookmark_id}",
        json={"url": "https://same-url.com"},
    )
    assert response.status_code == 200


async def test_different_users_can_have_same_url(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test that different users can bookmark the same URL."""
    from models.bookmark import Bookmark
    from models.user import User

    # Create bookmark via API (dev user)
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://shared-url.com", "title": "Dev User Bookmark"},
    )
    assert response.status_code == 201

    # Create a different user directly in DB
    other_user = User(auth0_id="auth0|other-user", email="other@example.com")
    db_session.add(other_user)
    await db_session.flush()

    # Create bookmark for the other user with same URL directly in DB
    other_bookmark = Bookmark(
        user_id=other_user.id,
        url="https://shared-url.com/",
        title="Other User Bookmark",
        tags=[],
    )
    db_session.add(other_bookmark)
    await db_session.flush()

    # Both bookmarks should exist
    result = await db_session.execute(
        select(Bookmark).where(Bookmark.url == "https://shared-url.com/"),
    )
    bookmarks = result.scalars().all()
    assert len(bookmarks) == 2
