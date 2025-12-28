"""Tests for note CRUD endpoints."""
import asyncio
from datetime import datetime, timedelta, UTC

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.note import Note


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
    assert data["version"] == 1
    assert isinstance(data["id"], int)
    assert "created_at" in data
    assert "updated_at" in data
    assert "last_used_at" in data

    # Verify in database
    result = await db_session.execute(select(Note).where(Note.id == data["id"]))
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


async def test_list_notes_view_active_excludes_deleted_and_archived(
    client: AsyncClient,
) -> None:
    """Test that active view excludes deleted and archived notes."""
    # Create notes in different states
    active_resp = await client.post("/notes/", json={"title": "Active Note"})
    active_id = active_resp.json()["id"]

    archived_resp = await client.post("/notes/", json={"title": "To Archive"})
    archived_id = archived_resp.json()["id"]
    await client.post(f"/notes/{archived_id}/archive")

    deleted_resp = await client.post("/notes/", json={"title": "To Delete"})
    deleted_id = deleted_resp.json()["id"]
    await client.delete(f"/notes/{deleted_id}")

    # Active view should only show active note
    response = await client.get("/notes/", params={"view": "active"})
    assert response.status_code == 200
    items = response.json()["items"]
    ids = [item["id"] for item in items]
    assert active_id in ids
    assert archived_id not in ids
    assert deleted_id not in ids


async def test_list_notes_view_archived(client: AsyncClient) -> None:
    """Test that archived view returns only archived notes."""
    # Create and archive some notes
    for i in range(2):
        response = await client.post("/notes/", json={"title": f"Archive Note {i}"})
        await client.post(f"/notes/{response.json()['id']}/archive")

    # Create an active note
    await client.post("/notes/", json={"title": "Active Note"})

    response = await client.get("/notes/", params={"view": "archived"})
    assert response.status_code == 200
    assert response.json()["total"] == 2
    for item in response.json()["items"]:
        assert item["archived_at"] is not None


async def test_list_notes_view_deleted(client: AsyncClient) -> None:
    """Test that deleted view returns only soft-deleted notes."""
    # Create and delete some notes
    for i in range(2):
        response = await client.post("/notes/", json={"title": f"Delete Note {i}"})
        await client.delete(f"/notes/{response.json()['id']}")

    # Create an active note
    await client.post("/notes/", json={"title": "Active Note"})

    response = await client.get("/notes/", params={"view": "deleted"})
    assert response.status_code == 200
    assert response.json()["total"] == 2
    for item in response.json()["items"]:
        assert item["deleted_at"] is not None


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


async def test_get_note_not_found(client: AsyncClient) -> None:
    """Test getting a non-existent note returns 404."""
    response = await client.get("/notes/99999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Note not found"


async def test_get_archived_note_by_id(client: AsyncClient) -> None:
    """Test that GET /notes/{id} returns archived notes."""
    # Create and archive a note
    create_response = await client.post(
        "/notes/",
        json={"title": "Archived Note"},
    )
    note_id = create_response.json()["id"]
    await client.post(f"/notes/{note_id}/archive")

    # Fetch the archived note by ID - should succeed
    get_response = await client.get(f"/notes/{note_id}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == note_id
    assert get_response.json()["archived_at"] is not None


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
        "/notes/99999",
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
# Delete Note Tests
# =============================================================================


async def test_delete_note(client: AsyncClient) -> None:
    """Test soft deleting a note."""
    # Create a note
    create_response = await client.post(
        "/notes/",
        json={"title": "To Delete"},
    )
    note_id = create_response.json()["id"]

    # Delete it (soft delete)
    response = await client.delete(f"/notes/{note_id}")
    assert response.status_code == 204

    # Verify it's not in active view
    get_response = await client.get(f"/notes/{note_id}")
    assert get_response.status_code == 404


async def test_delete_note_permanent(client: AsyncClient, db_session: AsyncSession) -> None:
    """Test permanently deleting a note."""
    # Create and soft delete a note
    create_response = await client.post(
        "/notes/",
        json={"title": "To Delete Permanently"},
    )
    note_id = create_response.json()["id"]
    await client.delete(f"/notes/{note_id}")

    # Permanently delete
    response = await client.delete(f"/notes/{note_id}", params={"permanent": True})
    assert response.status_code == 204

    # Verify it's gone from database
    result = await db_session.execute(select(Note).where(Note.id == note_id))
    assert result.scalar_one_or_none() is None


async def test_delete_note_not_found(client: AsyncClient) -> None:
    """Test deleting a non-existent note returns 404."""
    response = await client.delete("/notes/99999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Note not found"


# =============================================================================
# Restore Note Tests
# =============================================================================


async def test_restore_note_success(client: AsyncClient) -> None:
    """Test that restore endpoint restores a deleted note."""
    # Create and delete a note
    response = await client.post(
        "/notes/",
        json={"title": "To Restore"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    await client.delete(f"/notes/{note_id}")

    # Restore it
    response = await client.post(f"/notes/{note_id}/restore")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == note_id
    assert data["deleted_at"] is None

    # Should appear in active list again
    response = await client.get("/notes/")
    assert any(n["id"] == note_id for n in response.json()["items"])


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


async def test_restore_note_not_deleted_returns_400(client: AsyncClient) -> None:
    """Test that restoring a non-deleted note returns 400."""
    # Create a note (not deleted)
    response = await client.post(
        "/notes/",
        json={"title": "Not Deleted"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    # Try to restore
    response = await client.post(f"/notes/{note_id}/restore")
    assert response.status_code == 400
    assert "not deleted" in response.json()["detail"]


async def test_restore_note_not_found_returns_404(client: AsyncClient) -> None:
    """Test that restoring a non-existent note returns 404."""
    response = await client.post("/notes/99999/restore")
    assert response.status_code == 404


# =============================================================================
# Archive Note Tests
# =============================================================================


async def test_archive_note_success(client: AsyncClient) -> None:
    """Test that archive endpoint archives a note."""
    # Create a note
    response = await client.post(
        "/notes/",
        json={"title": "To Archive"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    # Archive it
    response = await client.post(f"/notes/{note_id}/archive")
    assert response.status_code == 200
    data = response.json()
    assert data["archived_at"] is not None

    # Should not appear in active list
    response = await client.get("/notes/")
    assert not any(n["id"] == note_id for n in response.json()["items"])


async def test_archive_note_is_idempotent(client: AsyncClient) -> None:
    """Test that archiving an already-archived note returns 200."""
    # Create and archive a note
    response = await client.post(
        "/notes/",
        json={"title": "To Archive"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    await client.post(f"/notes/{note_id}/archive")

    # Archive again - should succeed
    response = await client.post(f"/notes/{note_id}/archive")
    assert response.status_code == 200


async def test_archive_note_not_found_returns_404(client: AsyncClient) -> None:
    """Test that archiving a non-existent note returns 404."""
    response = await client.post("/notes/99999/archive")
    assert response.status_code == 404


# =============================================================================
# Unarchive Note Tests
# =============================================================================


async def test_unarchive_note_success(client: AsyncClient) -> None:
    """Test that unarchive endpoint unarchives a note."""
    # Create and archive a note
    response = await client.post(
        "/notes/",
        json={"title": "To Unarchive"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    await client.post(f"/notes/{note_id}/archive")

    # Unarchive it
    response = await client.post(f"/notes/{note_id}/unarchive")
    assert response.status_code == 200
    data = response.json()
    assert data["archived_at"] is None

    # Should appear in active list again
    response = await client.get("/notes/")
    assert any(n["id"] == note_id for n in response.json()["items"])


async def test_unarchive_note_not_archived_returns_400(client: AsyncClient) -> None:
    """Test that unarchiving a non-archived note returns 400."""
    # Create a note (not archived)
    response = await client.post(
        "/notes/",
        json={"title": "Not Archived"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    # Try to unarchive
    response = await client.post(f"/notes/{note_id}/unarchive")
    assert response.status_code == 400
    assert "not archived" in response.json()["detail"]


async def test_unarchive_note_not_found_returns_404(client: AsyncClient) -> None:
    """Test that unarchiving a non-existent note returns 404."""
    response = await client.post("/notes/99999/unarchive")
    assert response.status_code == 404


# =============================================================================
# Track Usage Tests
# =============================================================================


async def test_track_note_usage_success(client: AsyncClient) -> None:
    """Test that POST /notes/{id}/track-usage returns 204 and updates timestamp."""
    # Create a note
    response = await client.post(
        "/notes/",
        json={"title": "Track Me"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]
    original_last_used = response.json()["last_used_at"]

    # Small delay to ensure different timestamp
    await asyncio.sleep(0.01)

    # Track usage
    response = await client.post(f"/notes/{note_id}/track-usage")
    assert response.status_code == 204

    # Verify timestamp was updated
    response = await client.get(f"/notes/{note_id}")
    assert response.status_code == 200
    assert response.json()["last_used_at"] > original_last_used


async def test_track_note_usage_not_found(client: AsyncClient) -> None:
    """Test that POST /notes/{id}/track-usage returns 404 for non-existent note."""
    response = await client.post("/notes/99999/track-usage")
    assert response.status_code == 404
    assert response.json()["detail"] == "Note not found"


async def test_track_note_usage_works_on_archived(client: AsyncClient) -> None:
    """Test that track-usage works on archived notes."""
    # Create and archive a note
    response = await client.post(
        "/notes/",
        json={"title": "Archived"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    response = await client.post(f"/notes/{note_id}/archive")
    assert response.status_code == 200
    original_last_used = response.json()["last_used_at"]

    # Small delay to ensure different timestamp
    await asyncio.sleep(0.01)

    # Track usage on archived note
    response = await client.post(f"/notes/{note_id}/track-usage")
    assert response.status_code == 204

    # Verify via archived view
    response = await client.get("/notes/", params={"view": "archived"})
    assert response.status_code == 200
    note = next(n for n in response.json()["items"] if n["id"] == note_id)
    assert note["last_used_at"] > original_last_used


async def test_track_note_usage_works_on_deleted(client: AsyncClient) -> None:
    """Test that track-usage works on soft-deleted notes."""
    # Create and delete a note
    response = await client.post(
        "/notes/",
        json={"title": "Deleted"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]
    original_last_used = response.json()["last_used_at"]

    response = await client.delete(f"/notes/{note_id}")
    assert response.status_code == 204

    # Small delay to ensure different timestamp
    await asyncio.sleep(0.01)

    # Track usage on deleted note
    response = await client.post(f"/notes/{note_id}/track-usage")
    assert response.status_code == 204

    # Verify via deleted view
    response = await client.get("/notes/", params={"view": "deleted"})
    assert response.status_code == 200
    note = next(n for n in response.json()["items"] if n["id"] == note_id)
    assert note["last_used_at"] > original_last_used


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
        "deleted_at", "archived_at", "version",
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


async def test_list_notes_with_list_id(client: AsyncClient) -> None:
    """Test filtering notes by list_id parameter."""
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

    # Filter notes by list_id
    response = await client.get(f"/notes/?list_id={list_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Work Priority"


async def test_list_notes_with_list_id_complex_filter(client: AsyncClient) -> None:
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

    # Filter notes by list_id
    response = await client.get(f"/notes/?list_id={list_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 2
    titles = [n["title"] for n in data["items"]]
    assert "Work Priority" in titles
    assert "Urgent" in titles
    assert "Personal" not in titles


async def test_list_notes_with_list_id_not_found(client: AsyncClient) -> None:
    """Test that non-existent list_id returns 404."""
    response = await client.get("/notes/?list_id=99999")
    assert response.status_code == 404
    assert response.json()["detail"] == "List not found"


async def test_list_notes_with_list_id_and_search(client: AsyncClient) -> None:
    """Test combining list_id filter with text search."""
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
    response = await client.get(f"/notes/?list_id={list_id}&q=python")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Python Work"


async def test_list_notes_list_id_combines_with_tags(client: AsyncClient) -> None:
    """Test that list_id filter and tags parameter are combined with AND logic."""
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
    response = await client.get(f"/notes/?list_id={list_id}&tags=urgent")
    assert response.status_code == 200

    data = response.json()
    # Should return only notes matching BOTH work list AND urgent tag
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Work Urgent"


async def test_list_notes_list_id_and_tags_no_overlap(client: AsyncClient) -> None:
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
        "/lists/",
        json={
            "name": "Work",
            "filter_expression": {"groups": [{"tags": ["work"]}], "group_operator": "OR"},
        },
    )
    assert response.status_code == 201
    list_id = response.json()["id"]

    # Filter work list by 'personal' tag - no note has both
    response = await client.get(f"/notes/?list_id={list_id}&tags=personal")
    assert response.status_code == 200
    assert response.json()["total"] == 0


async def test_list_notes_list_id_empty_results(client: AsyncClient) -> None:
    """Test list_id filter with no matching notes."""
    # Create a note
    await client.post(
        "/notes/",
        json={"title": "Something", "content": "Content", "tags": ["other"]},
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
    response = await client.get(f"/notes/?list_id={list_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []
