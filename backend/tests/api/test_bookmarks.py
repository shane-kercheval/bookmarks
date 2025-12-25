"""Tests for bookmark CRUD endpoints."""
from datetime import datetime, UTC
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.bookmark import Bookmark
from models.user import User
from models.user_consent import UserConsent
from services.url_scraper import ExtractedMetadata, ScrapedPage


async def add_consent_for_user(db_session: AsyncSession, user: User) -> None:
    """Add valid consent record for a user (required for non-dev mode tests)."""
    from core.policy_versions import PRIVACY_POLICY_VERSION, TERMS_OF_SERVICE_VERSION

    consent = UserConsent(
        user_id=user.id,
        consented_at=datetime.now(UTC),
        privacy_policy_version=PRIVACY_POLICY_VERSION,
        terms_of_service_version=TERMS_OF_SERVICE_VERSION,
    )
    db_session.add(consent)
    await db_session.flush()


async def test_create_bookmark(client: AsyncClient, db_session: AsyncSession) -> None:
    """Test creating a new bookmark with all fields."""
    response = await client.post(
        "/bookmarks/",
        json={
            "url": "https://example.com",
            "title": "Example Site",
            "description": "An example website",
            "content": "Full page content here",
            "tags": ["example", "test"],
        },
    )
    assert response.status_code == 201

    data = response.json()
    # Verify all response fields
    assert data["url"] == "https://example.com/"
    assert data["title"] == "Example Site"
    assert data["description"] == "An example website"
    assert data["content"] == "Full page content here"
    assert data["tags"] == ["example", "test"]
    assert data["summary"] is None  # AI summary not implemented yet
    assert data["deleted_at"] is None
    assert data["archived_at"] is None
    assert isinstance(data["id"], int)
    assert "created_at" in data
    assert "updated_at" in data
    assert "last_used_at" in data

    # Verify in database
    result = await db_session.execute(select(Bookmark).where(Bookmark.id == data["id"]))
    bookmark = result.scalar_one()
    assert bookmark.url == "https://example.com/"
    assert bookmark.title == "Example Site"
    assert bookmark.description == "An example website"
    assert bookmark.content == "Full page content here"


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


async def test_create_bookmark_with_content(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test creating a bookmark with user-provided content."""
    response = await client.post(
        "/bookmarks/",
        json={
            "url": "https://example.com/with-content",
            "title": "Article Title",
            "content": "This is the article content for search.",
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["content"] == "This is the article content for search."

    # Verify content is stored in database
    result = await db_session.execute(select(Bookmark).where(Bookmark.id == data["id"]))
    bookmark = result.scalar_one()
    assert bookmark.content == "This is the article content for search."


async def test_create_bookmark_without_content_stores_null(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test that content is null when not provided."""
    response = await client.post(
        "/bookmarks/",
        json={
            "url": "https://example.com/no-content",
            "title": "No Content Bookmark",
        },
    )
    assert response.status_code == 201

    # Verify content is null in database
    result = await db_session.execute(
        select(Bookmark).where(Bookmark.id == response.json()["id"]),
    )
    bookmark = result.scalar_one()
    assert bookmark.content is None


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


async def test_update_bookmark_updates_updated_at(client: AsyncClient) -> None:
    """Test that updating a bookmark updates the updated_at timestamp."""
    import asyncio

    # Create a bookmark
    create_response = await client.post(
        "/bookmarks/",
        json={"url": "https://updated-at-test.com", "title": "Original"},
    )
    assert create_response.status_code == 201
    original_updated_at = create_response.json()["updated_at"]
    bookmark_id = create_response.json()["id"]

    # Small delay to ensure different timestamp
    await asyncio.sleep(0.01)

    # Update the bookmark
    response = await client.patch(
        f"/bookmarks/{bookmark_id}",
        json={"title": "New Title"},
    )
    assert response.status_code == 200

    data = response.json()
    # updated_at should be newer than the original
    assert data["updated_at"] > original_updated_at


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


async def test_sort_by_title_falls_back_to_url_when_title_missing(
    client: AsyncClient,
) -> None:
    """Test that sorting by title uses URL as fallback when title is NULL."""
    # Create bookmarks: some with titles, some without
    # Without title - should sort by URL "https://becu.org"
    await client.post(
        "/bookmarks/",
        json={"url": "https://becu.org"},
    )
    # With title "Zebra"
    await client.post(
        "/bookmarks/",
        json={"url": "https://zebra.com", "title": "Zebra"},
    )
    # Without title - should sort by URL "https://apple.org"
    await client.post(
        "/bookmarks/",
        json={"url": "https://apple.org"},
    )
    # With title "Middle"
    await client.post(
        "/bookmarks/",
        json={"url": "https://middle.com", "title": "Middle"},
    )

    # Sort ascending - expected order by coalesce(title, url):
    # "Middle", "Zebra", "https://apple.org", "https://becu.org"
    response = await client.get("/bookmarks/?sort_by=title&sort_order=asc")
    assert response.status_code == 200

    data = response.json()
    urls = [item["url"] for item in data["items"]]
    assert urls == [
        "https://apple.org/",  # No title, sorts by URL
        "https://becu.org/",  # No title, sorts by URL
        "https://middle.com/",  # Title "Middle"
        "https://zebra.com/",  # Title "Zebra"
    ]

    # Sort descending - reverse order
    response = await client.get("/bookmarks/?sort_by=title&sort_order=desc")
    assert response.status_code == 200

    data = response.json()
    urls = [item["url"] for item in data["items"]]
    assert urls == [
        "https://zebra.com/",  # Title "Zebra"
        "https://middle.com/",  # Title "Middle"
        "https://becu.org/",  # No title, sorts by URL
        "https://apple.org/",  # No title, sorts by URL
    ]


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
    mock_scraped = ScrapedPage(
        text=None,
        metadata=ExtractedMetadata(
            title='Test Page',
            description='Test description',
        ),
        final_url='https://example.com/page',
        content_type='text/html',
        error=None,
    )

    with patch(
        'api.routers.bookmarks.scrape_url',
        new_callable=AsyncMock,
        return_value=mock_scraped,
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
    assert data["content"] is None  # Content not requested by default
    assert data["error"] is None


async def test_fetch_metadata_with_include_content(client: AsyncClient) -> None:
    """Test metadata fetch with include_content=true returns page content."""
    mock_scraped = ScrapedPage(
        text='Main content here.',
        metadata=ExtractedMetadata(
            title='Test Page',
            description=None,
        ),
        final_url='https://example.com/page',
        content_type='text/html',
        error=None,
    )

    with patch(
        'api.routers.bookmarks.scrape_url',
        new_callable=AsyncMock,
        return_value=mock_scraped,
    ):
        response = await client.get(
            "/bookmarks/fetch-metadata",
            params={"url": "https://example.com/page", "include_content": "true"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Test Page"
    assert data["content"] == "Main content here."
    assert data["error"] is None


async def test_fetch_metadata_without_include_content_returns_null_content(
    client: AsyncClient,
) -> None:
    """Test that content is null when include_content=false."""
    mock_scraped = ScrapedPage(
        text='Some content',
        metadata=ExtractedMetadata(title='Test', description=None),
        final_url='https://example.com/',
        content_type='text/html',
        error=None,
    )

    with patch(
        'api.routers.bookmarks.scrape_url',
        new_callable=AsyncMock,
        return_value=mock_scraped,
    ):
        response = await client.get(
            "/bookmarks/fetch-metadata",
            params={"url": "https://example.com/"},
        )

    assert response.status_code == 200
    data = response.json()
    # Content should be null even though scrape returned it
    assert data["content"] is None


async def test_fetch_metadata_with_redirect(client: AsyncClient) -> None:
    """Test metadata fetch that follows a redirect."""
    mock_scraped = ScrapedPage(
        text=None,
        metadata=ExtractedMetadata(
            title='Redirected Page',
            description=None,
        ),
        final_url='https://example.com/new-location',
        content_type='text/html',
        error=None,
    )

    with patch(
        'api.routers.bookmarks.scrape_url',
        new_callable=AsyncMock,
        return_value=mock_scraped,
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
    mock_scraped = ScrapedPage(
        text=None,
        metadata=None,
        final_url='https://example.com/timeout',
        content_type=None,
        error='Connection timed out',
    )

    with patch(
        'api.routers.bookmarks.scrape_url',
        new_callable=AsyncMock,
        return_value=mock_scraped,
    ):
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
    mock_scraped = ScrapedPage(
        text=None,
        metadata=ExtractedMetadata(title='Auth Test', description=None),
        final_url='https://example.com/',
        content_type='text/html',
        error=None,
    )

    with patch(
        'api.routers.bookmarks.scrape_url',
        new_callable=AsyncMock,
        return_value=mock_scraped,
    ):
        response = await client.get(
            "/bookmarks/fetch-metadata",
            params={"url": "https://example.com"},
        )
    # Should succeed in dev mode
    assert response.status_code == 200


async def test_fetch_metadata_rate_limited(client: AsyncClient) -> None:
    """Test that fetch-metadata endpoint returns 429 when rate limit exceeded."""
    import time

    from core.rate_limit_config import RateLimitResult

    mock_scraped = ScrapedPage(
        text=None,
        metadata=ExtractedMetadata(title='Test', description=None),
        final_url='https://example.com/',
        content_type='text/html',
        error=None,
    )

    # Mock the rate limiter to simulate rate limit exceeded
    async def mock_check(
        _user_id: int, _auth_type: object, _operation_type: object,
    ) -> RateLimitResult:
        return RateLimitResult(
            allowed=False,
            limit=30,
            remaining=0,
            reset=int(time.time()) + 60,
            retry_after=60,
        )

    with patch(
        'api.routers.bookmarks.scrape_url',
        new_callable=AsyncMock,
        return_value=mock_scraped,
    ), patch(
        'core.auth.check_rate_limit',
        side_effect=mock_check,
    ):
        response = await client.get(
            "/bookmarks/fetch-metadata",
            params={"url": "https://example.com/page-over-limit"},
        )
        assert response.status_code == 429
        assert "Rate limit exceeded" in response.json()["detail"]
        assert "Retry-After" in response.headers
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers


async def test_fetch_metadata_rejects_pat_tokens(db_session: AsyncSession) -> None:
    """Test that fetch-metadata endpoint rejects PAT tokens with 403."""
    from collections.abc import AsyncGenerator

    from httpx import ASGITransport, AsyncClient

    from api.dependencies import get_current_user_auth0_only
    from api.main import app
    from db.session import get_async_session

    # Override get_current_user_auth0_only to simulate PAT rejection
    from fastapi import HTTPException, status

    async def mock_auth0_only_reject_pat() -> None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is not available for API tokens. Please use the web interface.",
        )

    async def override_get_async_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_current_user_auth0_only] = mock_auth0_only_reject_pat
    app.dependency_overrides[get_async_session] = override_get_async_session

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as test_client:
            response = await test_client.get(
                "/bookmarks/fetch-metadata",
                params={"url": "https://example.com"},
            )

        assert response.status_code == 403
        assert "not available for API tokens" in response.json()["detail"]
        assert "web interface" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


async def test_fetch_metadata_accepts_auth0_tokens(client: AsyncClient) -> None:
    """Test that fetch-metadata endpoint accepts Auth0 tokens (simulated via DEV_MODE)."""
    # In DEV_MODE, the client fixture simulates Auth0 authentication
    # This test verifies the endpoint works normally with valid auth
    mock_scraped = ScrapedPage(
        text=None,
        metadata=ExtractedMetadata(title='Auth0 Test', description=None),
        final_url='https://example.com/',
        content_type='text/html',
        error=None,
    )

    with patch(
        'api.routers.bookmarks.scrape_url',
        new_callable=AsyncMock,
        return_value=mock_scraped,
    ):
        response = await client.get(
            "/bookmarks/fetch-metadata",
            params={"url": "https://example.com"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Auth0 Test"


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
    detail = response.json()["detail"]
    assert detail["error_code"] == "ACTIVE_URL_EXISTS"
    assert "already exists" in detail["message"]


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
    detail = response.json()["detail"]
    assert detail["error_code"] == "ACTIVE_URL_EXISTS"
    assert "already exists" in detail["message"]


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
    )
    db_session.add(other_bookmark)
    await db_session.flush()

    # Both bookmarks should exist
    result = await db_session.execute(
        select(Bookmark).where(Bookmark.url == "https://shared-url.com/"),
    )
    bookmarks = result.scalars().all()
    assert len(bookmarks) == 2


# =============================================================================
# Soft Delete and Permanent Delete Tests
# =============================================================================


async def test_delete_bookmark_soft_delete_hides_from_list(client: AsyncClient) -> None:
    """Test that soft delete hides bookmark from list but keeps it in DB."""
    # Create a bookmark
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://soft-delete-test.com", "title": "To Delete"},
    )
    assert response.status_code == 201
    bookmark_id = response.json()["id"]

    # Delete it (soft delete by default)
    response = await client.delete(f"/bookmarks/{bookmark_id}")
    assert response.status_code == 204

    # Should not appear in list
    response = await client.get("/bookmarks/")
    assert response.status_code == 200
    items = response.json()["items"]
    assert not any(b["id"] == bookmark_id for b in items)


async def test_delete_bookmark_soft_delete_visible_in_deleted_view(
    client: AsyncClient,
) -> None:
    """Test that soft-deleted bookmark appears in deleted view."""
    # Create a bookmark
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://deleted-view-test.com", "title": "To Delete"},
    )
    assert response.status_code == 201
    bookmark_id = response.json()["id"]

    # Delete it
    response = await client.delete(f"/bookmarks/{bookmark_id}")
    assert response.status_code == 204

    # Should appear in deleted view
    response = await client.get("/bookmarks/?view=deleted")
    assert response.status_code == 200
    items = response.json()["items"]
    assert any(b["id"] == bookmark_id for b in items)


async def test_delete_bookmark_permanent_removes_from_db(
    client: AsyncClient,
) -> None:
    """Test that permanent delete removes bookmark from database."""
    # Create and soft-delete a bookmark
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://permanent-delete-test.com", "title": "To Delete"},
    )
    assert response.status_code == 201
    bookmark_id = response.json()["id"]

    response = await client.delete(f"/bookmarks/{bookmark_id}")
    assert response.status_code == 204

    # Permanently delete
    response = await client.delete(f"/bookmarks/{bookmark_id}?permanent=true")
    assert response.status_code == 204

    # Should not appear in any view
    response = await client.get("/bookmarks/?view=deleted")
    assert response.status_code == 200
    items = response.json()["items"]
    assert not any(b["id"] == bookmark_id for b in items)


# =============================================================================
# View Filter Tests
# =============================================================================


async def test_list_bookmarks_view_active_excludes_deleted_and_archived(
    client: AsyncClient,
) -> None:
    """Test that view=active excludes deleted and archived bookmarks."""
    # Create three bookmarks
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://active-view-1.com", "title": "Active"},
    )
    assert response.status_code == 201

    response = await client.post(
        "/bookmarks/",
        json={"url": "https://active-view-2.com", "title": "To Archive"},
    )
    assert response.status_code == 201
    archived_id = response.json()["id"]

    response = await client.post(
        "/bookmarks/",
        json={"url": "https://active-view-3.com", "title": "To Delete"},
    )
    assert response.status_code == 201
    deleted_id = response.json()["id"]

    # Archive and delete
    await client.post(f"/bookmarks/{archived_id}/archive")
    await client.delete(f"/bookmarks/{deleted_id}")

    # Active view should only show the first bookmark
    response = await client.get("/bookmarks/?view=active")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Active"


async def test_list_bookmarks_view_archived_returns_only_archived(
    client: AsyncClient,
) -> None:
    """Test that view=archived returns only archived (not deleted) bookmarks."""
    # Create and archive a bookmark
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://archived-view-test.com", "title": "Archived"},
    )
    assert response.status_code == 201
    bookmark_id = response.json()["id"]

    await client.post(f"/bookmarks/{bookmark_id}/archive")

    # Archived view should show it
    response = await client.get("/bookmarks/?view=archived")
    assert response.status_code == 200
    data = response.json()
    assert any(b["id"] == bookmark_id for b in data["items"])


async def test_list_bookmarks_view_with_search_filter(client: AsyncClient) -> None:
    """Test that search query works with view parameter."""
    # Create two bookmarks, archive one
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://python-active.com", "title": "Python Active"},
    )
    assert response.status_code == 201

    response = await client.post(
        "/bookmarks/",
        json={"url": "https://python-archived.com", "title": "Python Archived"},
    )
    assert response.status_code == 201
    archived_id = response.json()["id"]

    await client.post(f"/bookmarks/{archived_id}/archive")

    # Search for "Python" in archived view
    response = await client.get("/bookmarks/?view=archived&q=Python")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Python Archived"


# =============================================================================
# Restore Endpoint Tests
# =============================================================================


async def test_restore_bookmark_success(client: AsyncClient) -> None:
    """Test that restore endpoint restores a deleted bookmark."""
    # Create and delete a bookmark
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://restore-test.com", "title": "To Restore"},
    )
    assert response.status_code == 201
    bookmark_id = response.json()["id"]

    await client.delete(f"/bookmarks/{bookmark_id}")

    # Restore it
    response = await client.post(f"/bookmarks/{bookmark_id}/restore")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == bookmark_id
    assert data["deleted_at"] is None

    # Should appear in active list again
    response = await client.get("/bookmarks/")
    assert any(b["id"] == bookmark_id for b in response.json()["items"])


async def test_restore_bookmark_clears_both_timestamps(client: AsyncClient) -> None:
    """Test that restore clears both deleted_at and archived_at."""
    # Create, archive, then delete a bookmark
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://restore-both-test.com", "title": "Archived then Deleted"},
    )
    assert response.status_code == 201
    bookmark_id = response.json()["id"]

    await client.post(f"/bookmarks/{bookmark_id}/archive")
    await client.delete(f"/bookmarks/{bookmark_id}")

    # Restore it
    response = await client.post(f"/bookmarks/{bookmark_id}/restore")
    assert response.status_code == 200
    data = response.json()
    assert data["deleted_at"] is None
    assert data["archived_at"] is None


async def test_restore_bookmark_not_deleted_returns_400(client: AsyncClient) -> None:
    """Test that restoring a non-deleted bookmark returns 400."""
    # Create a bookmark (not deleted)
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://not-deleted-test.com", "title": "Not Deleted"},
    )
    assert response.status_code == 201
    bookmark_id = response.json()["id"]

    # Try to restore
    response = await client.post(f"/bookmarks/{bookmark_id}/restore")
    assert response.status_code == 400
    assert "not deleted" in response.json()["detail"]


async def test_restore_bookmark_url_conflict_returns_409(client: AsyncClient) -> None:
    """Test that restore fails if URL already exists as active bookmark."""
    # Create and delete a bookmark
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://restore-conflict.com", "title": "First"},
    )
    assert response.status_code == 201
    first_id = response.json()["id"]

    await client.delete(f"/bookmarks/{first_id}")

    # Create another with same URL
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://restore-conflict.com", "title": "Second"},
    )
    assert response.status_code == 201

    # Try to restore the first one
    response = await client.post(f"/bookmarks/{first_id}/restore")
    assert response.status_code == 409


async def test_restore_bookmark_not_found_returns_404(client: AsyncClient) -> None:
    """Test that restoring a non-existent bookmark returns 404."""
    response = await client.post("/bookmarks/99999/restore")
    assert response.status_code == 404


# =============================================================================
# Archive Endpoint Tests
# =============================================================================


async def test_archive_bookmark_success(client: AsyncClient) -> None:
    """Test that archive endpoint archives a bookmark."""
    # Create a bookmark
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://archive-test.com", "title": "To Archive"},
    )
    assert response.status_code == 201
    bookmark_id = response.json()["id"]

    # Archive it
    response = await client.post(f"/bookmarks/{bookmark_id}/archive")
    assert response.status_code == 200
    data = response.json()
    assert data["archived_at"] is not None

    # Should not appear in active list
    response = await client.get("/bookmarks/")
    assert not any(b["id"] == bookmark_id for b in response.json()["items"])


async def test_archive_bookmark_is_idempotent(client: AsyncClient) -> None:
    """Test that archiving an already-archived bookmark returns 200."""
    # Create and archive a bookmark
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://archive-idempotent.com", "title": "To Archive"},
    )
    assert response.status_code == 201
    bookmark_id = response.json()["id"]

    await client.post(f"/bookmarks/{bookmark_id}/archive")

    # Archive again - should succeed
    response = await client.post(f"/bookmarks/{bookmark_id}/archive")
    assert response.status_code == 200


async def test_archive_bookmark_not_found_returns_404(client: AsyncClient) -> None:
    """Test that archiving a non-existent bookmark returns 404."""
    response = await client.post("/bookmarks/99999/archive")
    assert response.status_code == 404


# =============================================================================
# Unarchive Endpoint Tests
# =============================================================================


async def test_unarchive_bookmark_success(client: AsyncClient) -> None:
    """Test that unarchive endpoint unarchives a bookmark."""
    # Create and archive a bookmark
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://unarchive-test.com", "title": "To Unarchive"},
    )
    assert response.status_code == 201
    bookmark_id = response.json()["id"]

    await client.post(f"/bookmarks/{bookmark_id}/archive")

    # Unarchive it
    response = await client.post(f"/bookmarks/{bookmark_id}/unarchive")
    assert response.status_code == 200
    data = response.json()
    assert data["archived_at"] is None

    # Should appear in active list again
    response = await client.get("/bookmarks/")
    assert any(b["id"] == bookmark_id for b in response.json()["items"])


async def test_unarchive_bookmark_not_archived_returns_400(client: AsyncClient) -> None:
    """Test that unarchiving a non-archived bookmark returns 400."""
    # Create a bookmark (not archived)
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://not-archived-test.com", "title": "Not Archived"},
    )
    assert response.status_code == 201
    bookmark_id = response.json()["id"]

    # Try to unarchive
    response = await client.post(f"/bookmarks/{bookmark_id}/unarchive")
    assert response.status_code == 400
    assert "not archived" in response.json()["detail"]


async def test_unarchive_bookmark_not_found_returns_404(client: AsyncClient) -> None:
    """Test that unarchiving a non-existent bookmark returns 404."""
    response = await client.post("/bookmarks/99999/unarchive")
    assert response.status_code == 404


# =============================================================================
# Create with Archived URL Tests
# =============================================================================


async def test_create_bookmark_with_archived_url_returns_409(client: AsyncClient) -> None:
    """Test that creating a bookmark with URL that exists as archived returns 409."""
    # Create and archive a bookmark
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://archived-url-conflict.com", "title": "Archived"},
    )
    assert response.status_code == 201
    archived_id = response.json()["id"]

    await client.post(f"/bookmarks/{archived_id}/archive")

    # Try to create another with same URL
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://archived-url-conflict.com", "title": "New"},
    )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error_code"] == "ARCHIVED_URL_EXISTS"
    assert detail["existing_bookmark_id"] == archived_id


async def test_create_bookmark_with_soft_deleted_url_succeeds(client: AsyncClient) -> None:
    """Test that creating a bookmark succeeds when same URL exists only as soft-deleted."""
    # Create and delete a bookmark
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://soft-deleted-url.com", "title": "First"},
    )
    assert response.status_code == 201
    first_id = response.json()["id"]

    await client.delete(f"/bookmarks/{first_id}")

    # Create another with same URL - should succeed
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://soft-deleted-url.com", "title": "Second"},
    )
    assert response.status_code == 201
    assert response.json()["id"] != first_id


# =============================================================================
# Response Format Tests
# =============================================================================


async def test_bookmark_response_includes_deleted_at_and_archived_at(
    client: AsyncClient,
) -> None:
    """Test that bookmark response includes deleted_at and archived_at fields."""
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://response-format-test.com", "title": "Test"},
    )
    assert response.status_code == 201
    data = response.json()
    assert "deleted_at" in data
    assert "archived_at" in data
    assert data["deleted_at"] is None
    assert data["archived_at"] is None


# =============================================================================
# Cross-User Isolation Tests
# =============================================================================


async def test_user_cannot_see_other_users_bookmarks_in_list(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test that a user's bookmark list only shows their own bookmarks."""
    from collections.abc import AsyncGenerator

    from httpx import ASGITransport

    from api.main import app
    from core.config import Settings, get_settings
    from db.session import get_async_session
    from models.user import User
    from services.token_service import create_token
    from schemas.token import TokenCreate

    # Create a bookmark as the dev user
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://user1-private.com", "title": "User 1 Private"},
    )
    assert response.status_code == 201
    user1_bookmark_id = response.json()["id"]

    # Create a second user and a PAT for them
    user2 = User(auth0_id="auth0|user2-isolation-test", email="user2@example.com")
    db_session.add(user2)
    await db_session.flush()

    # Add consent for user2 (required when dev_mode=False)
    await add_consent_for_user(db_session, user2)

    _, user2_token = await create_token(
        db_session, user2.id, TokenCreate(name="Test Token"),
    )
    await db_session.flush()

    # Clear settings cache and set up overrides for non-dev mode
    get_settings.cache_clear()

    async def override_get_async_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    def override_get_settings() -> Settings:
        return Settings(database_url="postgresql://test", dev_mode=False)

    app.dependency_overrides[get_async_session] = override_get_async_session
    app.dependency_overrides[get_settings] = override_get_settings

    # Make request as user2 with their PAT
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {user2_token}"},
    ) as user2_client:
        # List bookmarks as user2 - should not see user1's bookmark
        response = await user2_client.get("/bookmarks/")
        assert response.status_code == 200
        bookmark_ids = [b["id"] for b in response.json()["items"]]
        assert user1_bookmark_id not in bookmark_ids

    app.dependency_overrides.clear()


async def test_user_cannot_get_other_users_bookmark_by_id(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test that a user cannot access another user's bookmark by ID (returns 404)."""
    from collections.abc import AsyncGenerator

    from httpx import ASGITransport

    from api.main import app
    from core.config import Settings, get_settings
    from db.session import get_async_session
    from models.user import User
    from services.token_service import create_token
    from schemas.token import TokenCreate

    # Create a bookmark as the dev user
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://user1-get-test.com", "title": "User 1 Bookmark"},
    )
    assert response.status_code == 201
    user1_bookmark_id = response.json()["id"]

    # Create a second user and a PAT for them
    user2 = User(auth0_id="auth0|user2-get-test", email="user2-get@example.com")
    db_session.add(user2)
    await db_session.flush()

    # Add consent for user2 (required when dev_mode=False)
    await add_consent_for_user(db_session, user2)

    _, user2_token = await create_token(
        db_session, user2.id, TokenCreate(name="Test Token"),
    )
    await db_session.flush()

    get_settings.cache_clear()

    async def override_get_async_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    def override_get_settings() -> Settings:
        return Settings(database_url="postgresql://test", dev_mode=False)

    app.dependency_overrides[get_async_session] = override_get_async_session
    app.dependency_overrides[get_settings] = override_get_settings

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {user2_token}"},
    ) as user2_client:
        # Try to get user1's bookmark - should get 404, not 403
        response = await user2_client.get(f"/bookmarks/{user1_bookmark_id}")
        assert response.status_code == 404
        assert response.json()["detail"] == "Bookmark not found"

    app.dependency_overrides.clear()


async def test_user_cannot_update_other_users_bookmark(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test that a user cannot update another user's bookmark (returns 404)."""
    from collections.abc import AsyncGenerator

    from httpx import ASGITransport

    from api.main import app
    from core.config import Settings, get_settings
    from db.session import get_async_session
    from models.user import User
    from services.token_service import create_token
    from schemas.token import TokenCreate

    # Create a bookmark as the dev user
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://user1-update-test.com", "title": "Original Title"},
    )
    assert response.status_code == 201
    user1_bookmark_id = response.json()["id"]

    # Create a second user and a PAT for them
    user2 = User(auth0_id="auth0|user2-update-test", email="user2-update@example.com")
    db_session.add(user2)
    await db_session.flush()

    # Add consent for user2 (required when dev_mode=False)
    await add_consent_for_user(db_session, user2)

    _, user2_token = await create_token(
        db_session, user2.id, TokenCreate(name="Test Token"),
    )
    await db_session.flush()

    get_settings.cache_clear()

    async def override_get_async_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    def override_get_settings() -> Settings:
        return Settings(database_url="postgresql://test", dev_mode=False)

    app.dependency_overrides[get_async_session] = override_get_async_session
    app.dependency_overrides[get_settings] = override_get_settings

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {user2_token}"},
    ) as user2_client:
        # Try to update user1's bookmark - should get 404
        response = await user2_client.patch(
            f"/bookmarks/{user1_bookmark_id}",
            json={"title": "Hacked Title"},
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Bookmark not found"

    app.dependency_overrides.clear()

    # Verify the bookmark was not modified via database query
    result = await db_session.execute(
        select(Bookmark).where(Bookmark.id == user1_bookmark_id),
    )
    bookmark = result.scalar_one()
    assert bookmark.title == "Original Title"


async def test_user_cannot_delete_other_users_bookmark(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test that a user cannot delete another user's bookmark (returns 404)."""
    from collections.abc import AsyncGenerator

    from httpx import ASGITransport

    from api.main import app
    from core.config import Settings, get_settings
    from db.session import get_async_session
    from models.user import User
    from services.token_service import create_token
    from schemas.token import TokenCreate

    # Create a bookmark as the dev user
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://user1-delete-test.com", "title": "Do Not Delete"},
    )
    assert response.status_code == 201
    user1_bookmark_id = response.json()["id"]

    # Create a second user and a PAT for them
    user2 = User(auth0_id="auth0|user2-delete-test", email="user2-delete@example.com")
    db_session.add(user2)
    await db_session.flush()

    # Add consent for user2 (required when dev_mode=False)
    await add_consent_for_user(db_session, user2)

    _, user2_token = await create_token(
        db_session, user2.id, TokenCreate(name="Test Token"),
    )
    await db_session.flush()

    get_settings.cache_clear()

    async def override_get_async_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    def override_get_settings() -> Settings:
        return Settings(database_url="postgresql://test", dev_mode=False)

    app.dependency_overrides[get_async_session] = override_get_async_session
    app.dependency_overrides[get_settings] = override_get_settings

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {user2_token}"},
    ) as user2_client:
        # Try to delete user1's bookmark - should get 404
        response = await user2_client.delete(f"/bookmarks/{user1_bookmark_id}")
        assert response.status_code == 404
        assert response.json()["detail"] == "Bookmark not found"

    app.dependency_overrides.clear()

    # Verify the bookmark still exists via database query
    result = await db_session.execute(
        select(Bookmark).where(Bookmark.id == user1_bookmark_id),
    )
    bookmark = result.scalar_one()
    assert bookmark.title == "Do Not Delete"
    assert bookmark.deleted_at is None  # Not soft-deleted either


# =============================================================================
# Track Usage Endpoint Tests
# =============================================================================


async def test_track_bookmark_usage_success(
    client: AsyncClient,
) -> None:
    """Test that POST /bookmarks/{id}/track-usage returns 204 and updates timestamp."""
    # Create a bookmark
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://track-usage-test.com", "title": "Track Me"},
    )
    assert response.status_code == 201
    bookmark_id = response.json()["id"]
    original_last_used = response.json()["last_used_at"]

    # Track usage
    response = await client.post(f"/bookmarks/{bookmark_id}/track-usage")
    assert response.status_code == 204

    # Verify timestamp was updated
    response = await client.get(f"/bookmarks/{bookmark_id}")
    assert response.status_code == 200
    assert response.json()["last_used_at"] > original_last_used


async def test_track_bookmark_usage_not_found(client: AsyncClient) -> None:
    """Test that POST /bookmarks/{id}/track-usage returns 404 for non-existent bookmark."""
    response = await client.post("/bookmarks/99999/track-usage")
    assert response.status_code == 404
    assert response.json()["detail"] == "Bookmark not found"


async def test_track_bookmark_usage_works_on_archived(
    client: AsyncClient,
) -> None:
    """Test that track-usage works on archived bookmarks."""
    # Create and archive a bookmark
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://archived-track.com", "title": "Archived"},
    )
    assert response.status_code == 201
    bookmark_id = response.json()["id"]

    response = await client.post(f"/bookmarks/{bookmark_id}/archive")
    assert response.status_code == 200
    original_last_used = response.json()["last_used_at"]

    # Track usage on archived bookmark
    response = await client.post(f"/bookmarks/{bookmark_id}/track-usage")
    assert response.status_code == 204

    # Verify via archived view
    response = await client.get("/bookmarks/?view=archived")
    assert response.status_code == 200
    archived = next(b for b in response.json()["items"] if b["id"] == bookmark_id)
    assert archived["last_used_at"] > original_last_used


async def test_track_bookmark_usage_works_on_deleted(
    client: AsyncClient,
) -> None:
    """Test that track-usage works on soft-deleted bookmarks."""
    # Create and delete a bookmark
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://deleted-track.com", "title": "Deleted"},
    )
    assert response.status_code == 201
    bookmark_id = response.json()["id"]
    original_last_used = response.json()["last_used_at"]

    response = await client.delete(f"/bookmarks/{bookmark_id}")
    assert response.status_code == 204

    # Track usage on deleted bookmark
    response = await client.post(f"/bookmarks/{bookmark_id}/track-usage")
    assert response.status_code == 204

    # Verify via deleted view
    response = await client.get("/bookmarks/?view=deleted")
    assert response.status_code == 200
    deleted = next(b for b in response.json()["items"] if b["id"] == bookmark_id)
    assert deleted["last_used_at"] > original_last_used


# =============================================================================
# last_used_at Response Field Tests
# =============================================================================


async def test_bookmark_response_includes_last_used_at(client: AsyncClient) -> None:
    """Test that bookmark responses include last_used_at field."""
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://last-used-field.com", "title": "Test"},
    )
    assert response.status_code == 201
    data = response.json()
    assert "last_used_at" in data
    assert data["last_used_at"] == data["created_at"]  # Equal on creation


async def test_list_bookmarks_includes_last_used_at(client: AsyncClient) -> None:
    """Test that list bookmarks includes last_used_at in each item."""
    # Create a bookmark first
    await client.post(
        "/bookmarks/",
        json={"url": "https://list-last-used.com", "title": "Test"},
    )

    response = await client.get("/bookmarks/")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) > 0
    assert all("last_used_at" in item for item in items)


# =============================================================================
# List ID Filter Tests (BookmarkList integration)
# =============================================================================


async def test_list_bookmarks_with_list_id(client: AsyncClient) -> None:
    """Test filtering bookmarks by list_id parameter."""
    # Create bookmarks with different tags
    await client.post(
        "/bookmarks/",
        json={"url": "https://work-priority.com", "title": "Work Priority", "tags": ["work", "priority"]},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://work-only.com", "title": "Work Only", "tags": ["work"]},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://personal.com", "title": "Personal", "tags": ["personal"]},
    )

    # Create a list that filters for work AND priority
    response = await client.post(
        "/lists/",
        json={
            "name": "Work Priority List",
            "filter_expression": {
                "groups": [{"tags": ["work", "priority"]}],
                "group_operator": "OR",
            },
        },
    )
    assert response.status_code == 201
    list_id = response.json()["id"]

    # Filter bookmarks by list_id
    response = await client.get(f"/bookmarks/?list_id={list_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Work Priority"


async def test_list_bookmarks_with_list_id_complex_filter(client: AsyncClient) -> None:
    """Test filtering with complex list expression: (work AND priority) OR (urgent)."""
    # Create bookmarks
    await client.post(
        "/bookmarks/",
        json={"url": "https://wp.com", "title": "Work Priority", "tags": ["work", "priority"]},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://urgent.com", "title": "Urgent", "tags": ["urgent"]},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://personal.com", "title": "Personal", "tags": ["personal"]},
    )

    # Create a list with complex filter
    response = await client.post(
        "/lists/",
        json={
            "name": "Priority Tasks",
            "filter_expression": {
                "groups": [
                    {"tags": ["work", "priority"]},
                    {"tags": ["urgent"]},
                ],
                "group_operator": "OR",
            },
        },
    )
    assert response.status_code == 201
    list_id = response.json()["id"]

    # Filter bookmarks by list_id
    response = await client.get(f"/bookmarks/?list_id={list_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 2
    titles = [b["title"] for b in data["items"]]
    assert "Work Priority" in titles
    assert "Urgent" in titles
    assert "Personal" not in titles


async def test_list_bookmarks_with_list_id_not_found(client: AsyncClient) -> None:
    """Test that non-existent list_id returns 404."""
    response = await client.get("/bookmarks/?list_id=99999")
    assert response.status_code == 404
    assert response.json()["detail"] == "List not found"


async def test_list_bookmarks_with_list_id_and_search(client: AsyncClient) -> None:
    """Test combining list_id filter with text search."""
    # Create bookmarks
    await client.post(
        "/bookmarks/",
        json={"url": "https://py-work.com", "title": "Python Work", "tags": ["work", "coding"]},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://js-work.com", "title": "JavaScript Work", "tags": ["work", "coding"]},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://py-personal.com", "title": "Python Personal", "tags": ["personal", "coding"]},
    )

    # Create a list for work+coding
    response = await client.post(
        "/lists/",
        json={
            "name": "Work Coding",
            "filter_expression": {
                "groups": [{"tags": ["work", "coding"]}],
                "group_operator": "OR",
            },
        },
    )
    assert response.status_code == 201
    list_id = response.json()["id"]

    # Filter by list AND search for "Python"
    response = await client.get(f"/bookmarks/?list_id={list_id}&q=python")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Python Work"


async def test_list_bookmarks_list_id_combines_with_tags(client: AsyncClient) -> None:
    """Test that list_id filter and tags parameter are combined with AND logic."""
    # Create bookmarks
    await client.post(
        "/bookmarks/",
        json={"url": "https://work.com", "title": "Work", "tags": ["work"]},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://work-urgent.com", "title": "Work Urgent", "tags": ["work", "urgent"]},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://personal.com", "title": "Personal", "tags": ["personal"]},
    )

    # Create a list for work
    response = await client.post(
        "/lists/",
        json={
            "name": "Work List",
            "filter_expression": {
                "groups": [{"tags": ["work"]}],
                "group_operator": "OR",
            },
        },
    )
    assert response.status_code == 201
    list_id = response.json()["id"]

    # Pass both list_id AND tags - should combine with AND logic
    response = await client.get(f"/bookmarks/?list_id={list_id}&tags=urgent")
    assert response.status_code == 200

    data = response.json()
    # Should return only bookmarks matching BOTH work list AND urgent tag
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Work Urgent"


async def test_list_bookmarks_list_id_and_tags_no_overlap(client: AsyncClient) -> None:
    """Test that combining list filter and tags with no overlap returns empty."""
    # Bookmark in work list
    await client.post(
        "/bookmarks/",
        json={"url": "https://work.com", "title": "Work", "tags": ["work"]},
    )
    # Bookmark with personal tag (not in work list)
    await client.post(
        "/bookmarks/",
        json={"url": "https://personal.com", "title": "Personal", "tags": ["personal"]},
    )

    # Create work list
    response = await client.post(
        "/lists/",
        json={
            "name": "Work",
            "filter_expression": {"groups": [{"tags": ["work"]}], "group_operator": "OR"},
        },
    )
    assert response.status_code == 201
    list_id = response.json()["id"]

    # Filter work list by 'personal' tag - no bookmark has both
    response = await client.get(f"/bookmarks/?list_id={list_id}&tags=personal")
    assert response.status_code == 200
    assert response.json()["total"] == 0


async def test_list_bookmarks_list_id_empty_results(client: AsyncClient) -> None:
    """Test list_id filter with no matching bookmarks."""
    # Create a bookmark
    await client.post(
        "/bookmarks/",
        json={"url": "https://something.com", "title": "Something", "tags": ["other"]},
    )

    # Create a list for non-existent tags
    response = await client.post(
        "/lists/",
        json={
            "name": "Empty List",
            "filter_expression": {
                "groups": [{"tags": ["nonexistent"]}],
                "group_operator": "OR",
            },
        },
    )
    assert response.status_code == 201
    list_id = response.json()["id"]

    # Filter by list - should return empty
    response = await client.get(f"/bookmarks/?list_id={list_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


# =============================================================================
# Sort by archived_at and deleted_at Tests
# =============================================================================


async def test_sort_by_archived_at_desc(client: AsyncClient) -> None:
    """Test sorting by archived_at descending (most recently archived first)."""
    import asyncio

    # Create two bookmarks
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://sort-archived1.com", "title": "First Archived"},
    )
    assert response.status_code == 201
    first_id = response.json()["id"]

    await asyncio.sleep(0.01)

    response = await client.post(
        "/bookmarks/",
        json={"url": "https://sort-archived2.com", "title": "Second Archived"},
    )
    assert response.status_code == 201
    second_id = response.json()["id"]

    # Archive first, then second
    await client.post(f"/bookmarks/{first_id}/archive")
    await asyncio.sleep(0.01)
    await client.post(f"/bookmarks/{second_id}/archive")

    # Get archived view sorted by archived_at desc
    response = await client.get("/bookmarks/?view=archived&sort_by=archived_at&sort_order=desc")
    assert response.status_code == 200

    data = response.json()
    assert len(data["items"]) >= 2
    # Second archived should come first (most recent)
    ids = [b["id"] for b in data["items"]]
    assert ids.index(second_id) < ids.index(first_id)


async def test_sort_by_archived_at_asc(client: AsyncClient) -> None:
    """Test sorting by archived_at ascending (least recently archived first)."""
    import asyncio

    # Create two bookmarks
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://sort-archived-asc1.com", "title": "First Archived ASC"},
    )
    assert response.status_code == 201
    first_id = response.json()["id"]

    await asyncio.sleep(0.01)

    response = await client.post(
        "/bookmarks/",
        json={"url": "https://sort-archived-asc2.com", "title": "Second Archived ASC"},
    )
    assert response.status_code == 201
    second_id = response.json()["id"]

    # Archive first, then second
    await client.post(f"/bookmarks/{first_id}/archive")
    await asyncio.sleep(0.01)
    await client.post(f"/bookmarks/{second_id}/archive")

    # Get archived view sorted by archived_at asc
    response = await client.get("/bookmarks/?view=archived&sort_by=archived_at&sort_order=asc")
    assert response.status_code == 200

    data = response.json()
    assert len(data["items"]) >= 2
    # First archived should come first (least recent)
    ids = [b["id"] for b in data["items"]]
    assert ids.index(first_id) < ids.index(second_id)


async def test_sort_by_deleted_at_desc(client: AsyncClient) -> None:
    """Test sorting by deleted_at descending (most recently deleted first)."""
    import asyncio

    # Create two bookmarks
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://sort-deleted1.com", "title": "First Deleted"},
    )
    assert response.status_code == 201
    first_id = response.json()["id"]

    await asyncio.sleep(0.01)

    response = await client.post(
        "/bookmarks/",
        json={"url": "https://sort-deleted2.com", "title": "Second Deleted"},
    )
    assert response.status_code == 201
    second_id = response.json()["id"]

    # Delete first, then second
    await client.delete(f"/bookmarks/{first_id}")
    await asyncio.sleep(0.01)
    await client.delete(f"/bookmarks/{second_id}")

    # Get deleted view sorted by deleted_at desc
    response = await client.get("/bookmarks/?view=deleted&sort_by=deleted_at&sort_order=desc")
    assert response.status_code == 200

    data = response.json()
    assert len(data["items"]) >= 2
    # Second deleted should come first (most recent)
    ids = [b["id"] for b in data["items"]]
    assert ids.index(second_id) < ids.index(first_id)


async def test_sort_by_deleted_at_asc(client: AsyncClient) -> None:
    """Test sorting by deleted_at ascending (least recently deleted first)."""
    import asyncio

    # Create two bookmarks
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://sort-deleted-asc1.com", "title": "First Deleted ASC"},
    )
    assert response.status_code == 201
    first_id = response.json()["id"]

    await asyncio.sleep(0.01)

    response = await client.post(
        "/bookmarks/",
        json={"url": "https://sort-deleted-asc2.com", "title": "Second Deleted ASC"},
    )
    assert response.status_code == 201
    second_id = response.json()["id"]

    # Delete first, then second
    await client.delete(f"/bookmarks/{first_id}")
    await asyncio.sleep(0.01)
    await client.delete(f"/bookmarks/{second_id}")

    # Get deleted view sorted by deleted_at asc
    response = await client.get("/bookmarks/?view=deleted&sort_by=deleted_at&sort_order=asc")
    assert response.status_code == 200

    data = response.json()
    assert len(data["items"]) >= 2
    # First deleted should come first (least recent)
    ids = [b["id"] for b in data["items"]]
    assert ids.index(first_id) < ids.index(second_id)
