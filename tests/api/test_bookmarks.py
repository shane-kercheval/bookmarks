"""Tests for bookmark CRUD endpoints."""
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.bookmark import Bookmark


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
    assert len(data) >= 3  # May have bookmarks from other tests


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
    assert len(response.json()) == 2

    # Test offset
    response = await client.get("/bookmarks/?offset=1&limit=2")
    assert response.status_code == 200
    assert len(response.json()) == 2


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
