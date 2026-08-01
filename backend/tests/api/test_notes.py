"""Tests for note CRUD endpoints."""
import asyncio
from datetime import datetime, timedelta, UTC
from uuid import UUID

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.tier_limits import TierLimits
from models.note import Note

from tests.api.conftest import create_user2_client


# =============================================================================
# Create Note Tests
# =============================================================================


async def test_create_note(client: AsyncClient, db_session: AsyncSession) -> None:
    """Test creating a new note with all fields."""
    response = await client.post(
        "/notes/",
        json={
            "title": "My Test Note",
            "description": "A test description",
            "content": "This is the **markdown** content of the note.",
            "tags": ["example", "test"],
        },
    )
    assert response.status_code == 201

    data = response.json()
    # Verify all response fields
    assert data["title"] == "My Test Note"
    assert data["description"] == "A test description"
    assert data["content"] == "This is the **markdown** content of the note."
    assert data["tags"] == ["example", "test"]
    assert data["deleted_at"] is None
    assert data["archived_at"] is None
    assert isinstance(data["id"], str)
    assert "created_at" in data
    assert "updated_at" in data
    assert "last_used_at" in data

    # Verify in database
    result = await db_session.execute(select(Note).where(Note.id == UUID(data["id"])))
    note = result.scalar_one()
    assert note.title == "My Test Note"
    assert note.description == "A test description"
    assert note.content == "This is the **markdown** content of the note."


async def test_create_note_minimal(client: AsyncClient) -> None:
    """Test creating a note with only title (minimal required data)."""
    response = await client.post(
        "/notes/",
        json={"title": "Minimal Note"},
    )
    assert response.status_code == 201

    data = response.json()
    assert data["title"] == "Minimal Note"
    assert data["description"] is None
    assert data["content"] is None
    assert data["tags"] == []


async def test_create_note_requires_title(client: AsyncClient) -> None:
    """Test that creating a note without title fails."""
    response = await client.post(
        "/notes/",
        json={"content": "Some content without a title"},
    )
    assert response.status_code == 422
    assert "title" in response.text.lower()


async def test_create_note_empty_title_rejected(client: AsyncClient) -> None:
    """Test that empty title is rejected."""
    response = await client.post(
        "/notes/",
        json={"title": ""},
    )
    assert response.status_code == 422


async def test_create_note_whitespace_only_title_rejected(client: AsyncClient) -> None:
    """Test that whitespace-only title is rejected."""
    response = await client.post(
        "/notes/",
        json={"title": "   "},
    )
    assert response.status_code == 422


async def test_create_note_with_future_archived_at(client: AsyncClient) -> None:
    """Test creating a note with a scheduled auto-archive date."""
    future_date = (datetime.now(UTC) + timedelta(days=7)).isoformat()

    response = await client.post(
        "/notes/",
        json={
            "title": "Scheduled Note",
            "archived_at": future_date,
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["archived_at"] is not None
    # Should appear in active view (not yet archived)
    list_response = await client.get("/notes/", params={"view": "active"})
    assert any(n["id"] == data["id"] for n in list_response.json()["items"])


async def test_create_note_normalizes_tags(client: AsyncClient) -> None:
    """Test that tags are normalized to lowercase."""
    response = await client.post(
        "/notes/",
        json={
            "title": "Tag Normalization Test",
            "tags": ["Python", "FASTAPI", "Web-Dev"],
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["tags"] == ["python", "fastapi", "web-dev"]


async def test_create_note_invalid_tag_with_underscore(client: AsyncClient) -> None:
    """Test that tags with underscores are rejected."""
    response = await client.post(
        "/notes/",
        json={
            "title": "Invalid Tag Note",
            "tags": ["invalid_tag"],
        },
    )
    assert response.status_code == 422
    assert "Invalid tag format" in response.text


async def test_create_note_valid_tag_with_numbers(client: AsyncClient) -> None:
    """Test that tags with numbers are valid."""
    response = await client.post(
        "/notes/",
        json={
            "title": "Note with Numbers",
            "tags": ["web-dev-2024", "python3"],
        },
    )
    assert response.status_code == 201
    assert response.json()["tags"] == ["web-dev-2024", "python3"]


# =============================================================================
# List Notes Tests
# =============================================================================


async def test_list_notes(client: AsyncClient) -> None:
    """Test listing notes."""
    # Create some notes first
    for i in range(3):
        await client.post(
            "/notes/",
            json={"title": f"List Note {i}"},
        )

    response = await client.get("/notes/")
    assert response.status_code == 200

    data = response.json()
    assert len(data["items"]) == 3
    assert data["total"] == 3


async def test_list_notes_pagination(client: AsyncClient) -> None:
    """Test note listing with pagination."""
    # Create 5 notes
    for i in range(5):
        await client.post(
            "/notes/",
            json={"title": f"Paginate Note {i}"},
        )

    # Test limit
    response = await client.get("/notes/?limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5
    assert data["has_more"] is True

    # Test offset
    response = await client.get("/notes/?offset=1&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5


async def test_list_notes_excludes_content(client: AsyncClient) -> None:
    """Test that list endpoint doesn't return content field for performance."""
    await client.post(
        "/notes/",
        json={
            "title": "Note with Content",
            "content": "This is a long content that should not be in list",
        },
    )

    response = await client.get("/notes/")
    assert response.status_code == 200
    items = response.json()["items"]
    # List items should not have content field
    for item in items:
        assert "content" not in item


async def test__list_notes__returns_length_and_preview(client: AsyncClient) -> None:
    """Test that list endpoint returns content_length and content_preview."""
    content = "F" * 1000
    await client.post(
        "/notes/",
        json={"title": "List Length Test", "content": content},
    )

    response = await client.get("/notes/")
    assert response.status_code == 200

    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["content_length"] == 1000
    assert items[0]["content_preview"] == "F" * 500
    assert "content" not in items[0]


async def test__list_notes__null_content__returns_null_metrics(client: AsyncClient) -> None:
    """Test that list endpoint returns null metrics when content is null."""
    await client.post(
        "/notes/",
        json={"title": "No Content"},
    )

    response = await client.get("/notes/")
    assert response.status_code == 200

    items = response.json()["items"]
    assert items[0]["content_length"] is None
    assert items[0]["content_preview"] is None


async def test_list_notes_search(client: AsyncClient) -> None:
    """Test note search by query."""
    await client.post("/notes/", json={"title": "Python Tutorial"})
    await client.post("/notes/", json={"title": "JavaScript Guide"})
    await client.post("/notes/", json={"title": "Python Reference", "content": "Python content here"})

    response = await client.get("/notes/", params={"q": "Python"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    titles = [item["title"] for item in data["items"]]
    assert "Python Tutorial" in titles
    assert "Python Reference" in titles


async def test_list_notes_filter_by_tags(client: AsyncClient) -> None:
    """Test note filtering by tags."""
    await client.post("/notes/", json={"title": "Tagged Note 1", "tags": ["python", "web"]})
    await client.post("/notes/", json={"title": "Tagged Note 2", "tags": ["python"]})
    await client.post("/notes/", json={"title": "Untagged Note"})

    # Filter by single tag
    response = await client.get("/notes/", params={"tags": ["python"]})
    assert response.status_code == 200
    assert response.json()["total"] == 2

    # Filter by multiple tags (AND mode)
    response = await client.get("/notes/", params={"tags": ["python", "web"]})
    assert response.status_code == 200
    assert response.json()["total"] == 1

    # Filter by multiple tags (OR mode)
    response = await client.get("/notes/", params={"tags": ["python", "web"], "tag_match": "any"})
    assert response.status_code == 200
    assert response.json()["total"] == 2


# =============================================================================
# Get Single Note Tests
# =============================================================================


async def test_get_note(client: AsyncClient) -> None:
    """Test getting a single note."""
    # Create a note
    create_response = await client.post(
        "/notes/",
        json={"title": "Get Test", "content": "The full content"},
    )
    note_id = create_response.json()["id"]

    # Get it
    response = await client.get(f"/notes/{note_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == note_id
    assert data["title"] == "Get Test"
    assert data["content"] == "The full content"


async def test__get_note__returns_full_content_and_length(client: AsyncClient) -> None:
    """Test that GET /notes/{id} returns full content and content_length."""
    content = "This is the full content of the note for testing."
    create_response = await client.post(
        "/notes/",
        json={"title": "Content Length Test", "content": content},
    )
    note_id = create_response.json()["id"]

    response = await client.get(f"/notes/{note_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["content"] == content
    assert data["content_length"] == len(content)
    assert data.get("content_preview") is None


async def test__get_note_metadata__returns_length_and_preview_no_content(
    client: AsyncClient,
) -> None:
    """Test that GET /notes/{id}/metadata returns length and preview, no full content."""
    content = "B" * 1000
    create_response = await client.post(
        "/notes/",
        json={"title": "Metadata Test", "content": content},
    )
    note_id = create_response.json()["id"]

    response = await client.get(f"/notes/{note_id}/metadata")
    assert response.status_code == 200

    data = response.json()
    assert data["content_length"] == 1000
    assert data["content_preview"] == "B" * 500
    assert data.get("content") is None


async def test__get_note_metadata__content_under_500_chars__preview_equals_full(
    client: AsyncClient,
) -> None:
    """Test that metadata endpoint preview equals full content when under 500 chars."""
    content = "Short note content"
    create_response = await client.post(
        "/notes/",
        json={"title": "Short Content Test", "content": content},
    )
    note_id = create_response.json()["id"]

    response = await client.get(f"/notes/{note_id}/metadata")
    assert response.status_code == 200

    data = response.json()
    assert data["content_length"] == len(content)
    assert data["content_preview"] == content


async def test__get_note_metadata__null_content__returns_null_metrics(
    client: AsyncClient,
) -> None:
    """Test that metadata endpoint returns null metrics when content is null."""
    create_response = await client.post(
        "/notes/",
        json={"title": "No Content Test"},
    )
    note_id = create_response.json()["id"]

    response = await client.get(f"/notes/{note_id}/metadata")
    assert response.status_code == 200

    data = response.json()
    assert data["content_length"] is None
    assert data["content_preview"] is None


async def test__get_note_metadata__start_line_returns_400(client: AsyncClient) -> None:
    """Test that metadata endpoint returns 400 when start_line is provided."""
    create_response = await client.post(
        "/notes/",
        json={"title": "Line Param Test"},
    )
    note_id = create_response.json()["id"]

    response = await client.get(f"/notes/{note_id}/metadata", params={"start_line": 1})
    assert response.status_code == 400
    assert "start_line/end_line" in response.json()["detail"]


async def test__get_note_metadata__end_line_returns_400(client: AsyncClient) -> None:
    """Test that metadata endpoint returns 400 when end_line is provided."""
    create_response = await client.post(
        "/notes/",
        json={"title": "Line Param Test 2"},
    )
    note_id = create_response.json()["id"]

    response = await client.get(f"/notes/{note_id}/metadata", params={"end_line": 10})
    assert response.status_code == 400
    assert "start_line/end_line" in response.json()["detail"]


# =============================================================================
# Update Note Tests
# =============================================================================


async def test_update_note(client: AsyncClient) -> None:
    """Test updating a note."""
    # Create a note
    create_response = await client.post(
        "/notes/",
        json={"title": "Original Title", "content": "Original content"},
    )
    note_id = create_response.json()["id"]

    # Update it
    response = await client.patch(
        f"/notes/{note_id}",
        json={"title": "Updated Title", "tags": ["updated"]},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["title"] == "Updated Title"
    assert data["tags"] == ["updated"]
    # Content should remain unchanged
    assert data["content"] == "Original content"


async def test_update_note_partial(client: AsyncClient) -> None:
    """Test partial update only changes specified fields."""
    # Create a note with description
    create_response = await client.post(
        "/notes/",
        json={
            "title": "Original",
            "description": "Original description",
            "content": "Original content",
        },
    )
    note_id = create_response.json()["id"]

    # Update only title
    response = await client.patch(
        f"/notes/{note_id}",
        json={"title": "New Title"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["title"] == "New Title"
    assert data["description"] == "Original description"  # Unchanged
    assert data["content"] == "Original content"  # Unchanged


async def test_update_note_updates_updated_at(client: AsyncClient) -> None:
    """Test that updating a note updates the updated_at timestamp."""
    # Create a note
    create_response = await client.post(
        "/notes/",
        json={"title": "Timestamp Test"},
    )
    assert create_response.status_code == 201
    original_updated_at = create_response.json()["updated_at"]
    note_id = create_response.json()["id"]

    # Small delay to ensure different timestamp
    await asyncio.sleep(0.01)

    # Update the note
    response = await client.patch(
        f"/notes/{note_id}",
        json={"title": "New Title"},
    )
    assert response.status_code == 200

    data = response.json()
    # updated_at should be newer than the original
    assert data["updated_at"] > original_updated_at


async def test_update_note_not_found(client: AsyncClient) -> None:
    """Test updating a non-existent note returns 404."""
    response = await client.patch(
        "/notes/00000000-0000-0000-0000-000000000000",
        json={"title": "Won't Work"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Note not found"


async def test_update_note_set_archived_at(client: AsyncClient) -> None:
    """Test updating a note to schedule auto-archive."""
    # Create a note
    create_response = await client.post(
        "/notes/",
        json={"title": "Will Schedule"},
    )
    assert create_response.status_code == 201
    note_id = create_response.json()["id"]

    # Update to add scheduled archive
    future_date = (datetime.now(UTC) + timedelta(days=14)).isoformat()
    update_response = await client.patch(
        f"/notes/{note_id}",
        json={"archived_at": future_date},
    )
    assert update_response.status_code == 200
    assert update_response.json()["archived_at"] is not None


async def test_update_note_clear_archived_at(client: AsyncClient) -> None:
    """Test clearing a scheduled archive date by setting archived_at to null."""
    # Create a note with scheduled archive
    future_date = (datetime.now(UTC) + timedelta(days=7)).isoformat()
    create_response = await client.post(
        "/notes/",
        json={
            "title": "To Clear Schedule",
            "archived_at": future_date,
        },
    )
    assert create_response.status_code == 201
    note_id = create_response.json()["id"]
    assert create_response.json()["archived_at"] is not None

    # Clear the scheduled archive
    update_response = await client.patch(
        f"/notes/{note_id}",
        json={"archived_at": None},
    )
    assert update_response.status_code == 200
    assert update_response.json()["archived_at"] is None


# =============================================================================
# Restore Note Tests (entity-specific)
# =============================================================================


async def test_restore_note_clears_both_timestamps(client: AsyncClient) -> None:
    """Test that restore clears both deleted_at and archived_at."""
    # Create, archive, then delete a note
    response = await client.post(
        "/notes/",
        json={"title": "Archived then Deleted"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    await client.post(f"/notes/{note_id}/archive")
    await client.delete(f"/notes/{note_id}")

    # Restore it
    response = await client.post(f"/notes/{note_id}/restore")
    assert response.status_code == 200
    data = response.json()
    assert data["deleted_at"] is None
    assert data["archived_at"] is None




# =============================================================================
# Sort Tests
# =============================================================================


async def test_list_notes_sort_by_title(client: AsyncClient) -> None:
    """Test sorting notes by title."""
    await client.post("/notes/", json={"title": "Banana"})
    await client.post("/notes/", json={"title": "Apple"})
    await client.post("/notes/", json={"title": "Cherry"})

    # Sort ascending
    response = await client.get("/notes/", params={"sort_by": "title", "sort_order": "asc"})
    assert response.status_code == 200
    titles = [item["title"] for item in response.json()["items"]]
    assert titles == ["Apple", "Banana", "Cherry"]

    # Sort descending
    response = await client.get("/notes/", params={"sort_by": "title", "sort_order": "desc"})
    assert response.status_code == 200
    titles = [item["title"] for item in response.json()["items"]]
    assert titles == ["Cherry", "Banana", "Apple"]


async def test_list_notes_sort_by_title_case_insensitive(client: AsyncClient) -> None:
    """Test that title sorting is case-insensitive."""
    await client.post("/notes/", json={"title": "banana"})   # lowercase
    await client.post("/notes/", json={"title": "Apple"})    # capitalized
    await client.post("/notes/", json={"title": "CHERRY"})   # uppercase

    response = await client.get("/notes/", params={"sort_by": "title", "sort_order": "asc"})
    assert response.status_code == 200
    titles = [item["title"] for item in response.json()["items"]]
    # Case-insensitive order: Apple < banana < CHERRY
    assert titles == ["Apple", "banana", "CHERRY"]


async def test_list_notes_sort_by_created_at(client: AsyncClient) -> None:
    """Test sorting notes by created_at (default)."""
    await client.post("/notes/", json={"title": "First"})
    await client.post("/notes/", json={"title": "Second"})
    await client.post("/notes/", json={"title": "Third"})

    # Default is created_at desc (newest first)
    response = await client.get("/notes/")
    assert response.status_code == 200
    titles = [item["title"] for item in response.json()["items"]]
    assert titles == ["Third", "Second", "First"]


# =============================================================================
# View Filtering Tests
# =============================================================================


async def test__list_notes__view_active_excludes_deleted(client: AsyncClient) -> None:
    """Active view excludes deleted notes."""
    r1 = await client.post("/notes/", json={"title": "Active Note"})
    r2 = await client.post("/notes/", json={"title": "Deleted Note"})
    await client.delete(f"/notes/{r2.json()['id']}")

    response = await client.get("/notes/")
    ids = {item["id"] for item in response.json()["items"]}
    assert r1.json()["id"] in ids
    assert r2.json()["id"] not in ids


async def test__list_notes__view_active_excludes_archived(client: AsyncClient) -> None:
    """Active view excludes archived notes."""
    r1 = await client.post("/notes/", json={"title": "Active Note"})
    r2 = await client.post("/notes/", json={"title": "Archived Note"})
    await client.post(f"/notes/{r2.json()['id']}/archive")

    response = await client.get("/notes/")
    ids = {item["id"] for item in response.json()["items"]}
    assert r1.json()["id"] in ids
    assert r2.json()["id"] not in ids


async def test__list_notes__view_archived_returns_only_archived(client: AsyncClient) -> None:
    """Archived view returns only archived (not deleted) notes."""
    await client.post("/notes/", json={"title": "Active Note"})
    r2 = await client.post("/notes/", json={"title": "Archived Note"})
    r3 = await client.post("/notes/", json={"title": "Deleted Note"})
    await client.post(f"/notes/{r2.json()['id']}/archive")
    await client.delete(f"/notes/{r3.json()['id']}")

    response = await client.get("/notes/?view=archived")
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == r2.json()["id"]


async def test__list_notes__view_deleted_returns_all_deleted(client: AsyncClient) -> None:
    """Deleted view returns all deleted notes including archived+deleted."""
    await client.post("/notes/", json={"title": "Active Note"})
    r2 = await client.post("/notes/", json={"title": "Deleted Note"})
    r3 = await client.post("/notes/", json={"title": "Archived Then Deleted"})
    await client.post(f"/notes/{r3.json()['id']}/archive")
    await client.delete(f"/notes/{r2.json()['id']}")
    await client.delete(f"/notes/{r3.json()['id']}")

    response = await client.get("/notes/?view=deleted")
    ids = {item["id"] for item in response.json()["items"]}
    assert len(ids) == 2
    assert r2.json()["id"] in ids
    assert r3.json()["id"] in ids


async def test__list_notes__view_with_query_filter(client: AsyncClient) -> None:
    """Text search works together with view filtering."""
    r1 = await client.post("/notes/", json={"title": "Python Guide"})
    await client.post("/notes/", json={"title": "Python Tutorial"})
    await client.post(f"/notes/{r1.json()['id']}/archive")

    response = await client.get("/notes/?q=python&view=archived")
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["title"] == "Python Guide"


# =============================================================================
# Sort by updated_at and last_used_at Tests
# =============================================================================


async def test__list_notes__sort_by_updated_at_desc(client: AsyncClient) -> None:
    """Sorting by updated_at descending returns most recently modified first."""
    r1 = await client.post("/notes/", json={"title": "First Note"})
    await asyncio.sleep(0.01)
    r2 = await client.post("/notes/", json={"title": "Second Note"})
    await asyncio.sleep(0.01)
    await client.patch(f"/notes/{r1.json()['id']}", json={"title": "Updated Note"})

    response = await client.get("/notes/?sort_by=updated_at&sort_order=desc")
    items = response.json()["items"]
    assert items[0]["id"] == r1.json()["id"]
    assert items[1]["id"] == r2.json()["id"]


async def test__list_notes__sort_by_last_used_at_desc(client: AsyncClient) -> None:
    """Sorting by last_used_at descending returns most recently used first."""
    r1 = await client.post("/notes/", json={"title": "First Note"})
    await asyncio.sleep(0.01)
    r2 = await client.post("/notes/", json={"title": "Second Note"})
    await asyncio.sleep(0.01)
    await client.post(f"/notes/{r1.json()['id']}/track-usage")

    response = await client.get("/notes/?sort_by=last_used_at&sort_order=desc")
    items = response.json()["items"]
    assert items[0]["id"] == r1.json()["id"]
    assert items[1]["id"] == r2.json()["id"]


# =============================================================================
# Text Search Field Coverage
# =============================================================================


async def test__list_notes__text_search_in_title(client: AsyncClient) -> None:
    """Text search matches notes by title."""
    await client.post("/notes/", json={"title": "Python Tutorial"})
    await client.post("/notes/", json={"title": "JavaScript Guide"})

    response = await client.get("/notes/?q=python")
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["title"] == "Python Tutorial"


async def test__list_notes__text_search_in_description(client: AsyncClient) -> None:
    """Text search matches notes by description."""
    await client.post("/notes/", json={"title": "Note 1", "description": "About Python"})
    await client.post("/notes/", json={"title": "Note 2", "description": "About JavaScript"})

    response = await client.get("/notes/?q=python")
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["title"] == "Note 1"


async def test__list_notes__text_search_in_content(client: AsyncClient) -> None:
    """Text search matches notes by content."""
    await client.post("/notes/", json={"title": "Note 1", "content": "Contains searchterm here"})
    await client.post("/notes/", json={"title": "Note 2", "content": "Nothing relevant"})

    response = await client.get("/notes/?q=searchterm")
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["title"] == "Note 1"


async def test__list_notes__text_search_case_insensitive(client: AsyncClient) -> None:
    """Text search is case insensitive."""
    await client.post("/notes/", json={"title": "PYTHON Tutorial"})
    await client.post("/notes/", json={"title": "JavaScript Guide"})

    response = await client.get("/notes/?q=python")
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["title"] == "PYTHON Tutorial"


# =============================================================================
# Response Format Tests
# =============================================================================


async def test_note_response_includes_all_fields(client: AsyncClient) -> None:
    """Test that note response includes all expected fields."""
    response = await client.post(
        "/notes/",
        json={
            "title": "Complete Note",
            "description": "Description",
            "content": "Content",
            "tags": ["test"],
        },
    )
    assert response.status_code == 201
    data = response.json()

    expected_fields = [
        "id", "title", "description", "content", "tags",
        "created_at", "updated_at", "last_used_at",
        "deleted_at", "archived_at",
    ]
    for field in expected_fields:
        assert field in data, f"Missing field: {field}"


async def test_note_list_item_excludes_content(client: AsyncClient) -> None:
    """Test that list item response excludes content field."""
    await client.post(
        "/notes/",
        json={"title": "Has Content", "content": "Lots of content here"},
    )

    response = await client.get("/notes/")
    assert response.status_code == 200

    for item in response.json()["items"]:
        assert "content" not in item


# =============================================================================
# List ID Filter Tests (ContentList integration)
# =============================================================================


async def test_list_notes_with_filter_id(client: AsyncClient) -> None:
    """Test filtering notes by filter_id parameter."""
    # Create notes with different tags
    await client.post(
        "/notes/",
        json={"title": "Work Priority", "content": "Content", "tags": ["work", "priority"]},
    )
    await client.post(
        "/notes/",
        json={"title": "Work Only", "content": "Content", "tags": ["work"]},
    )
    await client.post(
        "/notes/",
        json={"title": "Personal", "content": "Content", "tags": ["personal"]},
    )

    # Create a list that filters for work AND priority
    response = await client.post(
        "/filters/",
        json={
            "name": "Work Priority List",
            "filter_expression": {
                "groups": [{"tags": ["work", "priority"]}],
                "group_operator": "OR",
            },
        },
    )
    assert response.status_code == 201
    filter_id = response.json()["id"]

    # Filter notes by filter_id
    response = await client.get(f"/notes/?filter_id={filter_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Work Priority"


async def test_list_notes_with_filter_id_complex_filter(client: AsyncClient) -> None:
    """Test filtering with complex list expression: (work AND priority) OR (urgent)."""
    # Create notes
    await client.post(
        "/notes/",
        json={"title": "Work Priority", "content": "Content", "tags": ["work", "priority"]},
    )
    await client.post(
        "/notes/",
        json={"title": "Urgent", "content": "Content", "tags": ["urgent"]},
    )
    await client.post(
        "/notes/",
        json={"title": "Personal", "content": "Content", "tags": ["personal"]},
    )

    # Create a list with complex filter
    response = await client.post(
        "/filters/",
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
    filter_id = response.json()["id"]

    # Filter notes by filter_id
    response = await client.get(f"/notes/?filter_id={filter_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 2
    titles = [n["title"] for n in data["items"]]
    assert "Work Priority" in titles
    assert "Urgent" in titles
    assert "Personal" not in titles


async def test_list_notes_with_filter_id_not_found(client: AsyncClient) -> None:
    """Test that non-existent filter_id returns 404."""
    response = await client.get("/notes/?filter_id=00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["detail"] == "Filter not found"


async def test_list_notes_with_filter_id_and_search(client: AsyncClient) -> None:
    """Test combining filter_id filter with text search."""
    # Create notes
    await client.post(
        "/notes/",
        json={"title": "Python Work", "content": "Content", "tags": ["work", "coding"]},
    )
    await client.post(
        "/notes/",
        json={"title": "JavaScript Work", "content": "Content", "tags": ["work", "coding"]},
    )
    await client.post(
        "/notes/",
        json={"title": "Python Personal", "content": "Content", "tags": ["personal", "coding"]},
    )

    # Create a list for work+coding
    response = await client.post(
        "/filters/",
        json={
            "name": "Work Coding",
            "filter_expression": {
                "groups": [{"tags": ["work", "coding"]}],
                "group_operator": "OR",
            },
        },
    )
    assert response.status_code == 201
    filter_id = response.json()["id"]

    # Filter by list AND search for "Python"
    response = await client.get(f"/notes/?filter_id={filter_id}&q=python")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Python Work"


async def test_list_notes_filter_id_combines_with_tags(client: AsyncClient) -> None:
    """Test that filter_id filter and tags parameter are combined with AND logic."""
    # Create notes
    await client.post(
        "/notes/",
        json={"title": "Work", "content": "Content", "tags": ["work"]},
    )
    await client.post(
        "/notes/",
        json={"title": "Work Urgent", "content": "Content", "tags": ["work", "urgent"]},
    )
    await client.post(
        "/notes/",
        json={"title": "Personal", "content": "Content", "tags": ["personal"]},
    )

    # Create a list for work
    response = await client.post(
        "/filters/",
        json={
            "name": "Work List",
            "filter_expression": {
                "groups": [{"tags": ["work"]}],
                "group_operator": "OR",
            },
        },
    )
    assert response.status_code == 201
    filter_id = response.json()["id"]

    # Pass both filter_id AND tags - should combine with AND logic
    response = await client.get(f"/notes/?filter_id={filter_id}&tags=urgent")
    assert response.status_code == 200

    data = response.json()
    # Should return only notes matching BOTH work list AND urgent tag
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Work Urgent"


async def test_list_notes_filter_id_and_tags_no_overlap(client: AsyncClient) -> None:
    """Test that combining list filter and tags with no overlap returns empty."""
    # Note in work list
    await client.post(
        "/notes/",
        json={"title": "Work", "content": "Content", "tags": ["work"]},
    )
    # Note with personal tag (not in work list)
    await client.post(
        "/notes/",
        json={"title": "Personal", "content": "Content", "tags": ["personal"]},
    )

    # Create work list
    response = await client.post(
        "/filters/",
        json={
            "name": "Work",
            "filter_expression": {"groups": [{"tags": ["work"]}], "group_operator": "OR"},
        },
    )
    assert response.status_code == 201
    filter_id = response.json()["id"]

    # Filter work list by 'personal' tag - no note has both
    response = await client.get(f"/notes/?filter_id={filter_id}&tags=personal")
    assert response.status_code == 200
    assert response.json()["total"] == 0


async def test_list_notes_filter_id_empty_results(client: AsyncClient) -> None:
    """Test filter_id filter with no matching notes."""
    # Create a note
    await client.post(
        "/notes/",
        json={"title": "Something", "content": "Content", "tags": ["other"]},
    )

    # Create a list for non-existent tags
    response = await client.post(
        "/filters/",
        json={
            "name": "Empty List",
            "filter_expression": {
                "groups": [{"tags": ["nonexistent"]}],
                "group_operator": "OR",
            },
        },
    )
    assert response.status_code == 201
    filter_id = response.json()["id"]

    # Filter by list - should return empty
    response = await client.get(f"/notes/?filter_id={filter_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


# =============================================================================
# Partial Read Tests
# =============================================================================


async def test__get_note__full_read_includes_content_metadata(client: AsyncClient) -> None:
    """Test that full read includes content_metadata with is_partial=false."""
    response = await client.post(
        "/notes/",
        json={"title": "Test", "content": "line 1\nline 2\nline 3"},
    )
    note_id = response.json()["id"]

    response = await client.get(f"/notes/{note_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["content"] == "line 1\nline 2\nline 3"
    assert data["content_metadata"] is not None
    assert data["content_metadata"]["total_lines"] == 3
    assert data["content_metadata"]["start_line"] == 1
    assert data["content_metadata"]["end_line"] == 3
    assert data["content_metadata"]["is_partial"] is False


async def test__get_note__partial_read_with_both_params(client: AsyncClient) -> None:
    """Test partial read with start_line and end_line."""
    response = await client.post(
        "/notes/",
        json={"title": "Test", "content": "line 1\nline 2\nline 3\nline 4\nline 5"},
    )
    note_id = response.json()["id"]

    response = await client.get(f"/notes/{note_id}", params={"start_line": 2, "end_line": 4})
    assert response.status_code == 200

    data = response.json()
    assert data["content"] == "line 2\nline 3\nline 4"
    assert data["content_metadata"]["total_lines"] == 5
    assert data["content_metadata"]["start_line"] == 2
    assert data["content_metadata"]["end_line"] == 4
    assert data["content_metadata"]["is_partial"] is True


async def test__get_note__partial_read_start_line_only(client: AsyncClient) -> None:
    """Test partial read with only start_line (reads to end)."""
    response = await client.post(
        "/notes/",
        json={"title": "Test", "content": "line 1\nline 2\nline 3"},
    )
    note_id = response.json()["id"]

    response = await client.get(f"/notes/{note_id}", params={"start_line": 2})
    assert response.status_code == 200

    data = response.json()
    assert data["content"] == "line 2\nline 3"
    assert data["content_metadata"]["total_lines"] == 3
    assert data["content_metadata"]["start_line"] == 2
    assert data["content_metadata"]["end_line"] == 3
    assert data["content_metadata"]["is_partial"] is True


async def test__get_note__partial_read_end_line_only(client: AsyncClient) -> None:
    """Test partial read with only end_line (reads from line 1)."""
    response = await client.post(
        "/notes/",
        json={"title": "Test", "content": "line 1\nline 2\nline 3"},
    )
    note_id = response.json()["id"]

    response = await client.get(f"/notes/{note_id}", params={"end_line": 2})
    assert response.status_code == 200

    data = response.json()
    assert data["content"] == "line 1\nline 2"
    assert data["content_metadata"]["total_lines"] == 3
    assert data["content_metadata"]["start_line"] == 1
    assert data["content_metadata"]["end_line"] == 2
    assert data["content_metadata"]["is_partial"] is True


async def test__get_note__start_line_exceeds_total_returns_400(client: AsyncClient) -> None:
    """Test that start_line > total_lines returns 400."""
    response = await client.post(
        "/notes/",
        json={"title": "Test", "content": "line 1\nline 2"},
    )
    note_id = response.json()["id"]

    response = await client.get(f"/notes/{note_id}", params={"start_line": 10})
    assert response.status_code == 400
    assert "exceeds total lines" in response.json()["detail"]


async def test__get_note__end_line_clamped_to_total(client: AsyncClient) -> None:
    """Test that end_line > total_lines is clamped (no error)."""
    response = await client.post(
        "/notes/",
        json={"title": "Test", "content": "line 1\nline 2"},
    )
    note_id = response.json()["id"]

    response = await client.get(f"/notes/{note_id}", params={"start_line": 1, "end_line": 100})
    assert response.status_code == 200

    data = response.json()
    assert data["content"] == "line 1\nline 2"
    assert data["content_metadata"]["end_line"] == 2  # Clamped to total


async def test__get_note__start_greater_than_end_returns_400(client: AsyncClient) -> None:
    """Test that start_line > end_line returns 400."""
    response = await client.post(
        "/notes/",
        json={"title": "Test", "content": "line 1\nline 2\nline 3"},
    )
    note_id = response.json()["id"]

    response = await client.get(f"/notes/{note_id}", params={"start_line": 3, "end_line": 2})
    assert response.status_code == 400
    assert "must be <=" in response.json()["detail"]


async def test__get_note__null_content_no_params_omits_metadata(client: AsyncClient) -> None:
    """Test that null content with no line params omits content_metadata."""
    response = await client.post(
        "/notes/",
        json={"title": "No Content Note"},  # No content
    )
    note_id = response.json()["id"]

    response = await client.get(f"/notes/{note_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["content"] is None
    assert data["content_metadata"] is None


async def test__get_note__null_content_with_line_params_returns_400(client: AsyncClient) -> None:
    """Test that null content with line params returns 400."""
    response = await client.post(
        "/notes/",
        json={"title": "No Content Note"},  # No content
    )
    note_id = response.json()["id"]

    response = await client.get(f"/notes/{note_id}", params={"start_line": 1})
    assert response.status_code == 400
    assert "Content is empty" in response.json()["detail"]


async def test__get_note__empty_string_content_is_valid(client: AsyncClient) -> None:
    """Test that empty string content with no params shows 1 line."""
    response = await client.post(
        "/notes/",
        json={"title": "Empty Content", "content": ""},
    )
    note_id = response.json()["id"]

    response = await client.get(f"/notes/{note_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["content"] == ""
    assert data["content_metadata"]["total_lines"] == 1
    assert data["content_metadata"]["is_partial"] is False


async def test__get_note__empty_string_content_length_is_zero(client: AsyncClient) -> None:
    """Test that empty string content returns content_length=0, not None."""
    response = await client.post(
        "/notes/",
        json={"title": "Empty String Test", "content": ""},
    )
    note_id = response.json()["id"]

    response = await client.get(f"/notes/{note_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["content"] == ""
    assert data["content_length"] == 0  # Empty string = length 0, not None


async def test__get_note__empty_string_content_with_start_line(client: AsyncClient) -> None:
    """Test that empty string content with start_line=1 succeeds."""
    response = await client.post(
        "/notes/",
        json={"title": "Empty Content", "content": ""},
    )
    note_id = response.json()["id"]

    response = await client.get(f"/notes/{note_id}", params={"start_line": 1})
    assert response.status_code == 200

    data = response.json()
    assert data["content"] == ""
    assert data["content_metadata"]["total_lines"] == 1
    assert data["content_metadata"]["is_partial"] is True


async def test__get_note__trailing_newline_line_count(client: AsyncClient) -> None:
    r"""Test that trailing newline is counted correctly (hello\\n = 2 lines)."""
    response = await client.post(
        "/notes/",
        json={"title": "Trailing Newline", "content": "hello\n"},
    )
    note_id = response.json()["id"]

    response = await client.get(f"/notes/{note_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["content_metadata"]["total_lines"] == 2


async def test__get_note__other_fields_unaffected_by_line_params(client: AsyncClient) -> None:
    """Test that title, description, tags are returned in full regardless of line params."""
    response = await client.post(
        "/notes/",
        json={
            "title": "Full Title Here",
            "description": "Full description text",
            "content": "line 1\nline 2\nline 3",
            "tags": ["tag1", "tag2"],
        },
    )
    note_id = response.json()["id"]

    response = await client.get(f"/notes/{note_id}", params={"start_line": 2, "end_line": 2})
    assert response.status_code == 200

    data = response.json()
    # Content is partial
    assert data["content"] == "line 2"
    assert data["content_metadata"]["is_partial"] is True
    # Other fields are complete
    assert data["title"] == "Full Title Here"
    assert data["description"] == "Full description text"
    assert data["tags"] == ["tag1", "tag2"]


# =============================================================================
# Within-Content Search Tests
# =============================================================================


async def test_search_in_note_basic(client: AsyncClient) -> None:
    """Test basic search within a note's content."""
    response = await client.post(
        "/notes/",
        json={
            "title": "Test Note",
            "content": "line 1\nline 2 with target\nline 3",
        },
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    response = await client.get(f"/notes/{note_id}/search", params={"q": "target"})
    assert response.status_code == 200

    data = response.json()
    assert data["total_matches"] == 1
    assert len(data["matches"]) == 1
    assert data["matches"][0]["field"] == "content"
    assert data["matches"][0]["line"] == 2
    assert "target" in data["matches"][0]["context"]


async def test_search_in_note_no_matches_returns_empty(client: AsyncClient) -> None:
    """Test that no matches returns empty array (not error)."""
    response = await client.post(
        "/notes/",
        json={"title": "Test Note", "content": "some content here"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    response = await client.get(f"/notes/{note_id}/search", params={"q": "nonexistent"})
    assert response.status_code == 200

    data = response.json()
    assert data["total_matches"] == 0
    assert data["matches"] == []


async def test_search_in_note_title_field(client: AsyncClient) -> None:
    """Test searching in title field returns full title as context."""
    response = await client.post(
        "/notes/",
        json={"title": "Important Meeting Notes", "content": "content here"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    response = await client.get(
        f"/notes/{note_id}/search",
        params={"q": "meeting", "fields": "title"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["total_matches"] == 1
    assert data["matches"][0]["field"] == "title"
    assert data["matches"][0]["line"] is None
    assert data["matches"][0]["context"] == "Important Meeting Notes"


async def test_search_in_note_description_field(client: AsyncClient) -> None:
    """Test searching in description field."""
    response = await client.post(
        "/notes/",
        json={
            "title": "Test Note",
            "description": "A detailed description for searching",
            "content": "content",
        },
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    response = await client.get(
        f"/notes/{note_id}/search",
        params={"q": "detailed", "fields": "description"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["total_matches"] == 1
    assert data["matches"][0]["field"] == "description"
    assert data["matches"][0]["line"] is None
    assert data["matches"][0]["context"] == "A detailed description for searching"


async def test_search_in_note_multiple_fields(client: AsyncClient) -> None:
    """Test searching across multiple fields."""
    response = await client.post(
        "/notes/",
        json={
            "title": "Python Tutorial",
            "description": "Learn Python basics",
            "content": "Python is a programming language",
        },
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    response = await client.get(
        f"/notes/{note_id}/search",
        params={"q": "python", "fields": "content,title,description"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["total_matches"] == 3
    fields = {m["field"] for m in data["matches"]}
    assert fields == {"content", "title", "description"}


async def test_search_in_note_case_insensitive_default(client: AsyncClient) -> None:
    """Test that search is case-insensitive by default."""
    response = await client.post(
        "/notes/",
        json={"title": "Test", "content": "Hello World"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    response = await client.get(f"/notes/{note_id}/search", params={"q": "WORLD"})
    assert response.status_code == 200
    assert response.json()["total_matches"] == 1


async def test_search_in_note_case_sensitive(client: AsyncClient) -> None:
    """Test case-sensitive search."""
    response = await client.post(
        "/notes/",
        json={"title": "Test", "content": "Hello World"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    # Case-sensitive search should not match
    response = await client.get(
        f"/notes/{note_id}/search",
        params={"q": "WORLD", "case_sensitive": True},
    )
    assert response.status_code == 200
    assert response.json()["total_matches"] == 0

    # Exact case should match
    response = await client.get(
        f"/notes/{note_id}/search",
        params={"q": "World", "case_sensitive": True},
    )
    assert response.status_code == 200
    assert response.json()["total_matches"] == 1


async def test_search_in_note_context_lines(client: AsyncClient) -> None:
    """Test context_lines parameter."""
    content = "line 1\nline 2\nline 3 target\nline 4\nline 5"
    response = await client.post(
        "/notes/",
        json={"title": "Test", "content": content},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    # With context_lines=1
    response = await client.get(
        f"/notes/{note_id}/search",
        params={"q": "target", "context_lines": 1},
    )
    assert response.status_code == 200
    context = response.json()["matches"][0]["context"]
    assert "line 2" in context
    assert "line 3 target" in context
    assert "line 4" in context
    # Should not include line 1 or line 5
    assert "line 1" not in context
    assert "line 5" not in context


async def test_search_in_note_multiple_matches_in_content(client: AsyncClient) -> None:
    """Test multiple matches in content field."""
    response = await client.post(
        "/notes/",
        json={"title": "Test", "content": "foo bar\nbar baz\nqux bar"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    response = await client.get(
        f"/notes/{note_id}/search",
        params={"q": "bar", "context_lines": 0},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["total_matches"] == 3
    lines = [m["line"] for m in data["matches"]]
    assert lines == [1, 2, 3]


async def test_search_in_note_not_found(client: AsyncClient) -> None:
    """Test 404 when note doesn't exist."""
    response = await client.get(
        "/notes/00000000-0000-0000-0000-000000000000/search",
        params={"q": "test"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Note not found"


async def test_search_in_note_invalid_field(client: AsyncClient) -> None:
    """Test 400 when invalid field is specified."""
    response = await client.post(
        "/notes/",
        json={"title": "Test", "content": "content"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    response = await client.get(
        f"/notes/{note_id}/search",
        params={"q": "test", "fields": "content,invalid"},
    )
    assert response.status_code == 400
    assert "Invalid fields" in response.json()["detail"]


async def test_search_in_note_works_on_archived(client: AsyncClient) -> None:
    """Test that search works on archived notes."""
    response = await client.post(
        "/notes/",
        json={"title": "Test", "content": "search target here"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    # Archive the note
    await client.post(f"/notes/{note_id}/archive")

    # Search should still work
    response = await client.get(f"/notes/{note_id}/search", params={"q": "target"})
    assert response.status_code == 200
    assert response.json()["total_matches"] == 1


async def test_search_in_note_works_on_deleted(client: AsyncClient) -> None:
    """Test that search works on soft-deleted notes."""
    response = await client.post(
        "/notes/",
        json={"title": "Test", "content": "search target here"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    # Delete the note
    await client.delete(f"/notes/{note_id}")

    # Search should still work
    response = await client.get(f"/notes/{note_id}/search", params={"q": "target"})
    assert response.status_code == 200
    assert response.json()["total_matches"] == 1


async def test_search_in_note_empty_content(client: AsyncClient) -> None:
    """Test searching in note with empty/null content."""
    response = await client.post(
        "/notes/",
        json={"title": "No Content Note"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    response = await client.get(f"/notes/{note_id}/search", params={"q": "anything"})
    assert response.status_code == 200
    assert response.json()["total_matches"] == 0
    assert response.json()["matches"] == []


# =============================================================================
# String Replace Tests
# =============================================================================


async def test_str_replace_note_success_minimal(client: AsyncClient) -> None:
    """Test successful string replacement returns minimal response by default."""
    response = await client.post(
        "/notes/",
        json={"title": "Test Note", "content": "Hello world"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    response = await client.patch(
        f"/notes/{note_id}/str-replace",
        json={"old_str": "world", "new_str": "universe"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["response_type"] == "minimal"
    assert data["match_type"] == "exact"
    assert data["line"] == 1
    # Default response is minimal - only id and updated_at
    assert data["data"]["id"] == note_id
    assert "updated_at" in data["data"]
    assert "content" not in data["data"]
    assert "title" not in data["data"]


async def test_str_replace_note_success_full_entity(client: AsyncClient) -> None:
    """Test successful string replacement with include_updated_entity=true."""
    response = await client.post(
        "/notes/",
        json={"title": "Test Note", "content": "Hello world"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    response = await client.patch(
        f"/notes/{note_id}/str-replace?include_updated_entity=true",
        json={"old_str": "world", "new_str": "universe"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["response_type"] == "full"
    assert data["match_type"] == "exact"
    assert data["line"] == 1
    assert data["data"]["content"] == "Hello universe"
    assert data["data"]["id"] == note_id


async def test_str_replace_note_multiline(client: AsyncClient) -> None:
    """Test string replacement with multiline content."""
    response = await client.post(
        "/notes/",
        json={"title": "Test", "content": "line 1\nline 2 target\nline 3"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    response = await client.patch(
        f"/notes/{note_id}/str-replace?include_updated_entity=true",
        json={"old_str": "target", "new_str": "replaced"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["match_type"] == "exact"
    assert data["line"] == 2
    assert data["data"]["content"] == "line 1\nline 2 replaced\nline 3"


async def test_str_replace_note_multiline_old_str(client: AsyncClient) -> None:
    """Test replacement with multiline old_str."""
    response = await client.post(
        "/notes/",
        json={"title": "Test", "content": "line 1\nline 2\nline 3\nline 4"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    response = await client.patch(
        f"/notes/{note_id}/str-replace?include_updated_entity=true",
        json={"old_str": "line 2\nline 3", "new_str": "replaced"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["data"]["content"] == "line 1\nreplaced\nline 4"
    assert data["line"] == 2


async def test_str_replace_note_no_match(client: AsyncClient) -> None:
    """Test string replacement when old_str is not found."""
    response = await client.post(
        "/notes/",
        json={"title": "Test", "content": "Hello world"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    response = await client.patch(
        f"/notes/{note_id}/str-replace",
        json={"old_str": "nonexistent", "new_str": "replaced"},
    )
    assert response.status_code == 400

    data = response.json()["detail"]
    assert data["error"] == "no_match"
    assert "not found" in data["message"]


async def test_str_replace_note_multiple_matches(client: AsyncClient) -> None:
    """Test string replacement when old_str matches multiple locations."""
    response = await client.post(
        "/notes/",
        json={"title": "Test", "content": "foo here\nbar baz\nfoo again"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    response = await client.patch(
        f"/notes/{note_id}/str-replace",
        json={"old_str": "foo", "new_str": "replaced"},
    )
    assert response.status_code == 400

    data = response.json()["detail"]
    assert data["error"] == "multiple_matches"
    assert len(data["matches"]) == 2
    assert data["matches"][0]["line"] == 1
    assert data["matches"][1]["line"] == 3
    # Check context is provided
    assert "foo here" in data["matches"][0]["context"]
    assert "foo again" in data["matches"][1]["context"]


async def test_str_replace_note_deletion(client: AsyncClient) -> None:
    """Test deletion using empty new_str."""
    response = await client.post(
        "/notes/",
        json={"title": "Test", "content": "Hello world"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    response = await client.patch(
        f"/notes/{note_id}/str-replace?include_updated_entity=true",
        json={"old_str": " world", "new_str": ""},
    )
    assert response.status_code == 200
    assert response.json()["data"]["content"] == "Hello"


async def test_str_replace_note_whitespace_normalized(client: AsyncClient) -> None:
    """Test whitespace-normalized matching."""
    # Content has trailing spaces on line 1
    response = await client.post(
        "/notes/",
        json={"title": "Test", "content": "line 1  \nline 2"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    # old_str without trailing spaces
    response = await client.patch(
        f"/notes/{note_id}/str-replace",
        json={"old_str": "line 1\nline 2", "new_str": "replaced"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["match_type"] == "whitespace_normalized"


async def test_str_replace_note_null_content(client: AsyncClient) -> None:
    """Test str-replace on note with null content returns content_empty error."""
    response = await client.post(
        "/notes/",
        json={"title": "No Content Note"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    response = await client.patch(
        f"/notes/{note_id}/str-replace",
        json={"old_str": "anything", "new_str": "replaced"},
    )
    assert response.status_code == 400

    data = response.json()["detail"]
    assert data["error"] == "content_empty"
    assert "no content" in data["message"].lower()
    assert "suggestion" in data


async def test_str_replace_note_not_found(client: AsyncClient) -> None:
    """Test str-replace on non-existent note."""
    response = await client.patch(
        "/notes/00000000-0000-0000-0000-000000000000/str-replace",
        json={"old_str": "anything", "new_str": "replaced"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Note not found"


async def test_str_replace_note_updates_updated_at(client: AsyncClient) -> None:
    """Test that str-replace updates the updated_at timestamp."""
    response = await client.post(
        "/notes/",
        json={"title": "Test", "content": "Hello world"},
    )
    assert response.status_code == 201
    original_updated_at = response.json()["updated_at"]
    note_id = response.json()["id"]

    await asyncio.sleep(0.01)

    response = await client.patch(
        f"/notes/{note_id}/str-replace",
        json={"old_str": "world", "new_str": "universe"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["updated_at"] > original_updated_at


async def test_str_replace_note_no_op_does_not_update_timestamp(client: AsyncClient) -> None:
    """Test that str-replace with old_str == new_str does not update timestamp."""
    response = await client.post(
        "/notes/",
        json={"title": "Test", "content": "Hello world"},
    )
    assert response.status_code == 201
    original_updated_at = response.json()["updated_at"]
    note_id = response.json()["id"]

    await asyncio.sleep(0.01)

    # Perform str-replace with identical old and new strings (no-op)
    response = await client.patch(
        f"/notes/{note_id}/str-replace",
        json={"old_str": "world", "new_str": "world"},
    )
    assert response.status_code == 200

    # Timestamp should NOT have changed
    assert response.json()["data"]["updated_at"] == original_updated_at

    # Verify match info is still returned
    assert response.json()["match_type"] == "exact"
    assert "line" in response.json()


async def test_str_replace_note_works_on_archived(client: AsyncClient) -> None:
    """Test that str-replace works on archived notes."""
    response = await client.post(
        "/notes/",
        json={"title": "Test", "content": "Hello world"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    # Archive the note
    await client.post(f"/notes/{note_id}/archive")

    # str-replace should still work
    response = await client.patch(
        f"/notes/{note_id}/str-replace?include_updated_entity=true",
        json={"old_str": "world", "new_str": "universe"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["content"] == "Hello universe"


async def test_str_replace_note_not_on_deleted(client: AsyncClient) -> None:
    """Test that str-replace does not work on soft-deleted notes."""
    response = await client.post(
        "/notes/",
        json={"title": "Test", "content": "Hello world"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    # Delete the note
    await client.delete(f"/notes/{note_id}")

    # str-replace should return 404
    response = await client.patch(
        f"/notes/{note_id}/str-replace",
        json={"old_str": "world", "new_str": "universe"},
    )
    assert response.status_code == 404


async def test_str_replace_note_preserves_other_fields(client: AsyncClient) -> None:
    """Test that str-replace preserves title, description, tags."""
    response = await client.post(
        "/notes/",
        json={
            "title": "My Title",
            "description": "My Description",
            "content": "Hello world",
            "tags": ["tag1", "tag2"],
        },
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    response = await client.patch(
        f"/notes/{note_id}/str-replace?include_updated_entity=true",
        json={"old_str": "world", "new_str": "universe"},
    )
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["title"] == "My Title"
    assert data["description"] == "My Description"
    assert data["tags"] == ["tag1", "tag2"]
    assert data["content"] == "Hello universe"


# =============================================================================
# Cross-User Isolation (IDOR) Tests
# =============================================================================


async def test_user_cannot_str_replace_other_users_note(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test that a user cannot str-replace another user's note (returns 404)."""
    # Create a note as the dev user with content
    response = await client.post(
        "/notes/",
        json={
            "title": "Test",
            "content": "Original content that should not be modified",
        },
    )
    assert response.status_code == 201
    user1_note_id = response.json()["id"]

    async with create_user2_client(
        db_session, 'legacy|user2-note-str-replace-test', 'user2-note-str-replace@example.com',
    ) as user2_client:
        # Try to str-replace user1's note - should get 404
        response = await user2_client.patch(
            f"/notes/{user1_note_id}/str-replace",
            json={"old_str": "Original", "new_str": "HACKED"},
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Note not found"

    # Verify the note content was not modified via database query
    result = await db_session.execute(
        select(Note).where(Note.id == user1_note_id),
    )
    note = result.scalar_one()
    assert note.content == "Original content that should not be modified"


async def test_user_cannot_see_other_users_notes_in_list(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test that a user's note list only shows their own notes."""
    response = await client.post("/notes/", json={"title": "User 1 Private Note"})
    assert response.status_code == 201
    user1_note_id = response.json()["id"]

    async with create_user2_client(
        db_session, 'legacy|user2-note-list-test', 'user2-note-list@example.com',
    ) as user2_client:
        response = await user2_client.get("/notes/")
        assert response.status_code == 200
        note_ids = [n["id"] for n in response.json()["items"]]
        assert user1_note_id not in note_ids


async def test_user_cannot_get_other_users_note_by_id(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test that a user cannot access another user's note by ID (returns 404)."""
    response = await client.post("/notes/", json={"title": "User 1 Note"})
    assert response.status_code == 201
    user1_note_id = response.json()["id"]

    async with create_user2_client(
        db_session, 'legacy|user2-note-get-test', 'user2-note-get@example.com',
    ) as user2_client:
        response = await user2_client.get(f"/notes/{user1_note_id}")
        assert response.status_code == 404
        assert response.json()["detail"] == "Note not found"


async def test_user_cannot_update_other_users_note(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test that a user cannot update another user's note (returns 404)."""
    response = await client.post("/notes/", json={"title": "Original Title"})
    assert response.status_code == 201
    user1_note_id = response.json()["id"]

    async with create_user2_client(
        db_session, 'legacy|user2-note-update-test', 'user2-note-update@example.com',
    ) as user2_client:
        response = await user2_client.patch(
            f"/notes/{user1_note_id}",
            json={"title": "Hacked Title"},
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Note not found"

    result = await db_session.execute(
        select(Note).where(Note.id == user1_note_id),
    )
    note = result.scalar_one()
    assert note.title == "Original Title"


async def test_user_cannot_delete_other_users_note(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test that a user cannot delete another user's note (returns 404)."""
    response = await client.post("/notes/", json={"title": "User 1 Note"})
    assert response.status_code == 201
    user1_note_id = response.json()["id"]

    async with create_user2_client(
        db_session, 'legacy|user2-note-delete-test', 'user2-note-delete@example.com',
    ) as user2_client:
        response = await user2_client.delete(f"/notes/{user1_note_id}")
        assert response.status_code == 404

    result = await db_session.execute(
        select(Note).where(Note.id == user1_note_id),
    )
    note = result.scalar_one()
    assert note.deleted_at is None


# =============================================================================
# Embedded Relationships
# =============================================================================


async def test__get_note__no_relationships_returns_empty_list(client: AsyncClient) -> None:
    """GET /notes/{id} returns empty relationships list when none exist."""
    create_resp = await client.post("/notes/", json={"title": "No Rels Note"})
    note_id = create_resp.json()["id"]

    response = await client.get(f"/notes/{note_id}")
    assert response.status_code == 200
    assert response.json()["relationships"] == []


async def test__get_note__with_relationships_returns_enriched(client: AsyncClient) -> None:
    """GET /notes/{id} returns enriched relationships when they exist."""
    note_resp = await client.post("/notes/", json={"title": "Source Note"})
    note_id = note_resp.json()["id"]

    bm_resp = await client.post(
        "/bookmarks/",
        json={"url": "https://note-rel-test.com", "title": "Linked BM"},
    )
    bm_id = bm_resp.json()["id"]

    await client.post("/relationships/", json={
        "source_type": "note",
        "source_id": note_id,
        "target_type": "bookmark",
        "target_id": bm_id,
        "relationship_type": "related",
    })

    response = await client.get(f"/notes/{note_id}")
    assert response.status_code == 200

    rels = response.json()["relationships"]
    assert len(rels) == 1
    # Canonical ordering may swap source/target; verify both titles present
    titles = {rels[0]["source_title"], rels[0]["target_title"]}
    assert "Linked BM" in titles
    assert "Source Note" in titles


async def test__list_notes__no_relationships_field(client: AsyncClient) -> None:
    """GET /notes/ list items should NOT include relationships field."""
    await client.post("/notes/", json={"title": "List Note"})

    response = await client.get("/notes/")
    assert response.status_code == 200

    items = response.json()["items"]
    assert len(items) >= 1
    assert "relationships" not in items[0]


# =============================================================================
# Tier Limits Quota Enforcement Tests (API-level)
# =============================================================================


async def test__create_note__quota_exceeded__returns_402(
    client: AsyncClient, low_limits: TierLimits,
) -> None:
    """Test that exceeding max_notes returns 402 with QUOTA_EXCEEDED error code."""
    for i in range(low_limits.max_notes):
        r = await client.post("/notes/", json={"title": f"Note {i}", "content": "c"})
        assert r.status_code == 201
    r = await client.post("/notes/", json={"title": "Over", "content": "c"})
    assert r.status_code == 402
    body = r.json()
    assert body["error_code"] == "QUOTA_EXCEEDED"
