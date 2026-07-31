"""Tests for history API endpoints."""
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from httpx import AsyncClient as HttpxAsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from models.content_history import SOURCE_MAX_LENGTH, ContentHistory
from models.user import User
from core.tier_limits import Tier, get_tier_limits
from schemas.token import TokenCreate
from services.token_service import create_token
from tests.api.conftest import add_consent_for_user

_DEV_LIMITS = get_tier_limits(Tier.DEV)


# --- Test data for parametrized tests ---

ENTITY_TEST_DATA = [
    pytest.param(
        "bookmark",
        "/bookmarks/",
        {"url": "https://example.com", "content": "Initial content", "title": "Test Title"},
        {"content": "Updated content"},
        id="bookmark",
    ),
    pytest.param(
        "note",
        "/notes/",
        {"title": "Test Note", "content": "Initial content"},
        {"content": "Updated content"},
        id="note",
    ),
    pytest.param(
        "prompt",
        "/prompts/",
        {"name": "test-prompt", "content": "Initial content", "arguments": []},
        {"content": "Updated content"},
        id="prompt",
    ),
]

# Test data without update_payload for tests that don't need it
ENTITY_CREATE_DATA = [
    pytest.param(
        "bookmark",
        "/bookmarks/",
        {"url": "https://example.com", "content": "Initial content", "title": "Test Title"},
        id="bookmark",
    ),
    pytest.param(
        "note",
        "/notes/",
        {"title": "Test Note", "content": "Initial content"},
        id="note",
    ),
    pytest.param(
        "prompt",
        "/prompts/",
        {"name": "test-prompt", "content": "Initial content", "arguments": []},
        id="prompt",
    ),
]


# --- /history/ endpoint tests ---


async def test_get_user_history_empty(client: AsyncClient) -> None:
    """Test getting user history when no history exists."""
    response = await client.get("/history/")
    assert response.status_code == 200

    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["offset"] == 0
    assert data["limit"] == 50
    assert data["has_more"] is False


async def test_get_user_history_with_all_content_types(client: AsyncClient) -> None:
    """Test getting user history includes all content types."""
    # Create one of each content type
    await client.post("/bookmarks/", json={"url": "https://example.com"})
    await client.post("/notes/", json={"title": "Test", "content": "Content"})
    await client.post(
        "/prompts/",
        json={"name": "test-prompt", "content": "Hello", "arguments": []},
    )

    # Get all history
    response = await client.get("/history/")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 3

    # Verify all content types are present
    content_types = {item["content_type"] for item in data["items"]}
    assert content_types == {"bookmark", "note", "prompt"}


@pytest.mark.parametrize("content_type", ["bookmark", "note", "prompt"])
async def test_get_user_history_filter_by_content_type(
    client: AsyncClient,
    content_type: str,
) -> None:
    """Test filtering user history by content type."""
    # Create one of each content type
    await client.post("/bookmarks/", json={"url": "https://example.com"})
    await client.post("/notes/", json={"title": "Test", "content": "Content"})
    await client.post(
        "/prompts/",
        json={"name": "test-prompt", "content": "Hello", "arguments": []},
    )

    # Filter by specific content type
    response = await client.get("/history/", params={"content_type": content_type})
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["content_type"] == content_type


async def test_get_user_history_filter_by_multiple_content_types(
    client: AsyncClient,
) -> None:
    """Test filtering user history by multiple content types (OR logic)."""
    # Create one of each content type
    await client.post("/bookmarks/", json={"url": "https://example.com"})
    await client.post("/notes/", json={"title": "Test", "content": "Content"})
    await client.post(
        "/prompts/",
        json={"name": "test-multi-entity", "content": "Hello", "arguments": []},
    )

    # Filter by bookmark and note (should return 2)
    response = await client.get(
        "/history/",
        params=[("content_type", "bookmark"), ("content_type", "note")],
    )
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 2
    content_types = {item["content_type"] for item in data["items"]}
    assert content_types == {"bookmark", "note"}


async def test_get_user_history_filter_by_action(client: AsyncClient) -> None:
    """Test filtering user history by action type."""
    # Create bookmark (create action)
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://action-test.com", "content": "Initial"},
    )
    bookmark_id = response.json()["id"]

    # Update bookmark (update action)
    await client.patch(f"/bookmarks/{bookmark_id}", json={"content": "Updated"})

    # Filter by create action only
    response = await client.get("/history/", params={"action": "create"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["action"] == "create"

    # Filter by update action only
    response = await client.get("/history/", params={"action": "update"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["action"] == "update"


async def test_get_user_history_filter_by_multiple_actions(client: AsyncClient) -> None:
    """Test filtering user history by multiple action types (OR logic)."""
    # Create and update bookmark
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://multi-action-test.com", "content": "Initial"},
    )
    bookmark_id = response.json()["id"]
    await client.patch(f"/bookmarks/{bookmark_id}", json={"content": "Updated"})

    # Delete to add delete action
    await client.delete(f"/bookmarks/{bookmark_id}")

    # Filter by create and delete (should return 2)
    response = await client.get(
        "/history/",
        params=[("action", "create"), ("action", "delete")],
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    actions = {item["action"] for item in data["items"]}
    assert actions == {"create", "delete"}


async def test_get_user_history_filter_by_source(client: AsyncClient) -> None:
    """Test filtering user history by source."""
    # Create bookmark (source will be 'unknown' in test client without header)
    await client.post("/bookmarks/", json={"url": "https://source-test.com"})

    # Filter by unknown source
    response = await client.get("/history/", params={"source": "unknown"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["source"] == "unknown"

    # Filter by web source (should return 0 since we didn't set header)
    response = await client.get("/history/", params={"source": "web"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0


async def test_history_source__x_request_source_header_maps_to_stored_source(
    client: AsyncClient,
) -> None:
    """
    End-to-end: the X-Request-Source HTTP header flows through FastAPI's Header
    dependency into the stored audit source. Guards the parameter-name -> header
    mapping (x_request_source -> X-Request-Source) that the unit tests (which call
    get_request_source directly) and the OpenAPI schema test do not exercise.
    """
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://header-source-test.com"},
        headers={"X-Request-Source": "chrome-extension"},
    )
    assert response.status_code == 201

    history = await client.get("/history/", params={"source": "chrome-extension"})
    assert history.status_code == 200
    data = history.json()
    assert data["total"] == 1
    assert data["items"][0]["source"] == "chrome-extension"


async def test_history_source__over_length_header_is_truncated_not_500(
    client: AsyncClient,
) -> None:
    """
    An over-length X-Request-Source is truncated to SOURCE_MAX_LENGTH server-side
    rather than overflowing the history column and failing the write with a 500.
    """
    long_source = "a-really-long-third-party-client-name"
    assert len(long_source) > SOURCE_MAX_LENGTH

    response = await client.post(
        "/bookmarks/",
        json={"url": "https://truncation-test.com"},
        headers={"X-Request-Source": long_source},
    )
    assert response.status_code == 201

    expected = long_source[:SOURCE_MAX_LENGTH]
    history = await client.get("/history/", params={"source": expected})
    assert history.status_code == 200
    data = history.json()
    assert data["total"] == 1
    assert data["items"][0]["source"] == expected
    assert len(data["items"][0]["source"]) == SOURCE_MAX_LENGTH


async def test_get_user_history_filter_by_date_range(client: AsyncClient) -> None:
    """Test filtering user history by date range."""
    # Create bookmark
    await client.post("/bookmarks/", json={"url": "https://date-test.com"})

    # Get all history to find the created_at timestamp
    response = await client.get("/history/")
    data = response.json()
    assert data["total"] == 1
    created_at = datetime.fromisoformat(data["items"][0]["created_at"].replace("Z", "+00:00"))

    # Filter with start_date before creation (should return 1)
    start_before = (created_at - timedelta(hours=1)).isoformat()
    response = await client.get("/history/", params={"start_date": start_before})
    assert response.status_code == 200
    assert response.json()["total"] == 1

    # Filter with start_date after creation (should return 0)
    start_after = (created_at + timedelta(hours=1)).isoformat()
    response = await client.get("/history/", params={"start_date": start_after})
    assert response.status_code == 200
    assert response.json()["total"] == 0

    # Filter with end_date after creation (should return 1)
    end_after = (created_at + timedelta(hours=1)).isoformat()
    response = await client.get("/history/", params={"end_date": end_after})
    assert response.status_code == 200
    assert response.json()["total"] == 1

    # Filter with end_date before creation (should return 0)
    end_before = (created_at - timedelta(hours=1)).isoformat()
    response = await client.get("/history/", params={"end_date": end_before})
    assert response.status_code == 200
    assert response.json()["total"] == 0


async def test_get_user_history_filter_combined(client: AsyncClient) -> None:
    """Test combining multiple filters (AND logic between categories)."""
    # Create bookmark
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://combined-filter-test.com", "content": "Initial"},
    )
    bookmark_id = response.json()["id"]

    # Update bookmark
    await client.patch(f"/bookmarks/{bookmark_id}", json={"content": "Updated"})

    # Create note
    await client.post("/notes/", json={"title": "Test", "content": "Content"})

    # Filter by bookmark content_type AND update action (should return 1)
    response = await client.get(
        "/history/",
        params={"content_type": "bookmark", "action": "update"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["content_type"] == "bookmark"
    assert data["items"][0]["action"] == "update"


async def test_get_user_history_invalid_content_type_returns_422(
    client: AsyncClient,
) -> None:
    """Test that invalid content_type value returns 422."""
    response = await client.get("/history/", params={"content_type": "invalid"})
    assert response.status_code == 422


async def test_get_user_history_invalid_action_returns_422(client: AsyncClient) -> None:
    """Test that invalid action value returns 422."""
    response = await client.get("/history/", params={"action": "invalid"})
    assert response.status_code == 422


async def test_get_user_history_unrecognized_source_returns_empty(client: AsyncClient) -> None:
    """Test that unrecognized source value is accepted (returns empty results)."""
    response = await client.get("/history/", params={"source": "some-new-source"})
    assert response.status_code == 200
    assert response.json()["items"] == []


async def test_get_user_history_invalid_date_format_returns_422(
    client: AsyncClient,
) -> None:
    """Test that invalid date format returns 422."""
    response = await client.get("/history/", params={"start_date": "not-a-date"})
    assert response.status_code == 422


async def test_get_user_history_start_date_after_end_date_returns_422(
    client: AsyncClient,
) -> None:
    """Test that start_date > end_date returns 422."""
    response = await client.get(
        "/history/",
        params={
            "start_date": "2024-01-20T00:00:00Z",
            "end_date": "2024-01-10T00:00:00Z",
        },
    )
    assert response.status_code == 422
    assert "start_date must be before or equal to end_date" in response.json()["detail"]


async def test_get_user_history_mixed_naive_aware_datetime_returns_422(
    client: AsyncClient,
) -> None:
    """Test that mixing naive and aware datetimes returns 422."""
    # start_date is naive (no Z or offset), end_date is aware (has Z)
    response = await client.get(
        "/history/",
        params={
            "start_date": "2024-01-01T00:00:00",
            "end_date": "2024-01-10T00:00:00Z",
        },
    )
    assert response.status_code == 422
    assert "timezone-aware" in response.json()["detail"]


async def test_get_user_history_empty_filter_returns_all(client: AsyncClient) -> None:
    """Test that empty filter arrays return all records."""
    # Create entities
    await client.post("/bookmarks/", json={"url": "https://empty-filter-test.com"})
    await client.post("/notes/", json={"title": "Test", "content": "Content"})

    # No filters - should return all
    response = await client.get("/history/")
    assert response.status_code == 200
    assert response.json()["total"] == 2


async def test_get_user_history_filter_by_multiple_sources(client: AsyncClient) -> None:
    """Test filtering by multiple sources (OR logic)."""
    # In test client without X-Request-Source header, source defaults to 'unknown'
    await client.post("/bookmarks/", json={"url": "https://multi-source-test.com"})

    # Filter by unknown and web (only unknown exists, should return 1)
    response = await client.get(
        "/history/",
        params=[("source", "unknown"), ("source", "web")],
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["source"] == "unknown"


async def test_get_user_history_pagination_with_filters(client: AsyncClient) -> None:
    """Test that pagination works correctly with filters applied."""
    # Create 3 bookmarks and 2 notes
    for i in range(3):
        await client.post("/bookmarks/", json={"url": f"https://pagination-filter-{i}.com"})
    for i in range(2):
        await client.post("/notes/", json={"title": f"Note {i}", "content": "Content"})

    # Filter by bookmark only, with pagination
    response = await client.get(
        "/history/",
        params={"content_type": "bookmark", "limit": 2, "offset": 0},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3  # Total matching filter, not total in DB
    assert len(data["items"]) == 2
    assert data["has_more"] is True
    assert all(item["content_type"] == "bookmark" for item in data["items"])

    # Get second page
    response = await client.get(
        "/history/",
        params={"content_type": "bookmark", "limit": 2, "offset": 2},
    )
    data = response.json()
    assert data["total"] == 3
    assert len(data["items"]) == 1
    assert data["has_more"] is False


async def test_get_user_history_date_boundary_inclusive(client: AsyncClient) -> None:
    """Test that date filtering is inclusive at boundaries."""
    # Create bookmark
    await client.post("/bookmarks/", json={"url": "https://boundary-test.com"})

    # Get the exact created_at timestamp
    response = await client.get("/history/")
    data = response.json()
    created_at_str = data["items"][0]["created_at"]
    created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))

    # Filter with start_date exactly equal to created_at (should include it)
    response = await client.get(
        "/history/",
        params={"start_date": created_at.isoformat()},
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1

    # Filter with end_date exactly equal to created_at (should include it)
    response = await client.get(
        "/history/",
        params={"end_date": created_at.isoformat()},
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1

    # Filter with both boundaries exactly equal to created_at (should include it)
    response = await client.get(
        "/history/",
        params={
            "start_date": created_at.isoformat(),
            "end_date": created_at.isoformat(),
        },
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1


async def test_get_user_history_pagination(client: AsyncClient) -> None:
    """Test pagination of user history."""
    # Create multiple entities to generate history
    for i in range(5):
        await client.post("/bookmarks/", json={"url": f"https://example{i}.com"})

    # Get first page
    response = await client.get("/history/", params={"limit": 2, "offset": 0})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["has_more"] is True

    # Get second page
    response = await client.get("/history/", params={"limit": 2, "offset": 2})
    data = response.json()
    assert len(data["items"]) == 2
    assert data["has_more"] is True

    # Get last page
    response = await client.get("/history/", params={"limit": 2, "offset": 4})
    data = response.json()
    assert len(data["items"]) == 1
    assert data["has_more"] is False


async def test_get_user_history_offset_beyond_total(client: AsyncClient) -> None:
    """Test user history with offset beyond total count."""
    await client.post("/bookmarks/", json={"url": "https://example.com"})

    response = await client.get("/history/", params={"offset": 100})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 0
    assert data["has_more"] is False


# --- /history/{content_type}/{content_id} endpoint tests (parametrized) ---


@pytest.mark.parametrize(
    ("content_type", "create_endpoint", "create_payload", "update_payload"),
    ENTITY_TEST_DATA,
)
async def test_get_entity_history(
    client: AsyncClient,
    content_type: str,
    create_endpoint: str,
    create_payload: dict,
    update_payload: dict,
) -> None:
    """Test getting history for a specific entity."""
    # Create entity
    response = await client.post(create_endpoint, json=create_payload)
    assert response.status_code == 201, f"Failed to create {content_type}: {response.json()}"
    content_id = response.json()["id"]

    # Update to create more history
    await client.patch(f"{create_endpoint}{content_id}", json=update_payload)

    # Get entity history
    response = await client.get(f"/history/{content_type}/{content_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2

    # Items should be sorted by created_at descending (most recent first)
    assert data["items"][0]["version"] == 2
    assert data["items"][0]["content_type"] == content_type
    assert data["items"][1]["version"] == 1


@pytest.mark.parametrize("content_type", ["bookmark", "note", "prompt"])
async def test_get_entity_history_empty_for_nonexistent(
    client: AsyncClient,
    content_type: str,
) -> None:
    """Test getting history for non-existent entity returns empty list."""
    fake_uuid = "00000000-0000-0000-0000-000000000000"

    response = await client.get(f"/history/{content_type}/{fake_uuid}")
    assert response.status_code == 200

    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.parametrize(
    ("content_type", "create_endpoint", "create_payload"),
    ENTITY_CREATE_DATA,
)
async def test_get_entity_history_soft_deleted(
    client: AsyncClient,
    content_type: str,
    create_endpoint: str,
    create_payload: dict,
) -> None:
    """Test getting history for soft-deleted entity returns history."""
    # Create entity
    response = await client.post(create_endpoint, json=create_payload)
    content_id = response.json()["id"]

    # Soft delete
    await client.delete(f"{create_endpoint}{content_id}")

    # Get entity history - should still return history
    response = await client.get(f"/history/{content_type}/{content_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 2  # CREATE + DELETE
    assert data["items"][0]["action"] == "delete"
    assert data["items"][1]["action"] == "create"


@pytest.mark.parametrize(
    ("content_type", "create_endpoint", "create_payload"),
    ENTITY_CREATE_DATA,
)
async def test_get_entity_history_hard_deleted(
    client: AsyncClient,
    content_type: str,
    create_endpoint: str,
    create_payload: dict,
) -> None:
    """Test getting history for hard-deleted entity returns empty list."""
    # Create entity
    response = await client.post(create_endpoint, json=create_payload)
    content_id = response.json()["id"]

    # Soft delete first
    await client.delete(f"{create_endpoint}{content_id}")

    # Hard delete
    await client.delete(f"{create_endpoint}{content_id}", params={"permanent": True})

    # Get entity history - should return empty (history cascade-deleted)
    response = await client.get(f"/history/{content_type}/{content_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.parametrize(
    ("content_type", "create_endpoint", "create_payload"),
    ENTITY_CREATE_DATA,
)
async def test_get_entity_history_pagination(
    client: AsyncClient,
    content_type: str,
    create_endpoint: str,
    create_payload: dict,
) -> None:
    """Test pagination of entity history."""
    # Create entity and update multiple times
    response = await client.post(create_endpoint, json=create_payload)
    content_id = response.json()["id"]

    for i in range(4):
        await client.patch(
            f"{create_endpoint}{content_id}",
            json={"content": f"Version {i + 2}"},
        )

    # Get first page
    response = await client.get(
        f"/history/{content_type}/{content_id}",
        params={"limit": 2, "offset": 0},
    )
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["has_more"] is True


# --- /history/{content_type}/{content_id}/version/{version} endpoint tests (parametrized) ---


@pytest.mark.parametrize(
    ("content_type", "create_endpoint", "create_payload", "update_payload"),
    ENTITY_TEST_DATA,
)
async def test_get_content_at_version(
    client: AsyncClient,
    content_type: str,
    create_endpoint: str,
    create_payload: dict,
    update_payload: dict,
) -> None:
    """Test getting content at a specific version."""
    # Create entity
    response = await client.post(create_endpoint, json=create_payload)
    content_id = response.json()["id"]

    # Update the entity
    await client.patch(f"{create_endpoint}{content_id}", json=update_payload)

    # Get content at version 1 (original)
    response = await client.get(f"/history/{content_type}/{content_id}/version/1")
    assert response.status_code == 200

    data = response.json()
    assert data["content_id"] == content_id
    assert data["version"] == 1
    assert data["content"] == "Initial content"
    assert data["metadata"] is not None
    assert data["warnings"] is None


@pytest.mark.parametrize(
    ("content_type", "create_endpoint", "create_payload"),
    ENTITY_CREATE_DATA,
)
async def test_get_content_at_version_latest(
    client: AsyncClient,
    content_type: str,
    create_endpoint: str,
    create_payload: dict,
) -> None:
    """Test getting content at the latest version."""
    # Create entity
    response = await client.post(create_endpoint, json=create_payload)
    content_id = response.json()["id"]

    # Get content at version 1 (latest and only version)
    response = await client.get(f"/history/{content_type}/{content_id}/version/1")
    assert response.status_code == 200

    data = response.json()
    assert data["content"] == "Initial content"


@pytest.mark.parametrize(
    ("content_type", "create_endpoint", "create_payload"),
    ENTITY_CREATE_DATA,
)
async def test_get_content_at_version_not_found(
    client: AsyncClient,
    content_type: str,
    create_endpoint: str,
    create_payload: dict,
) -> None:
    """Test getting content at non-existent version returns 404."""
    # Create entity
    response = await client.post(create_endpoint, json=create_payload)
    content_id = response.json()["id"]

    # Try to get version 999
    response = await client.get(f"/history/{content_type}/{content_id}/version/999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Version not found"


@pytest.mark.parametrize(
    ("content_type", "create_endpoint", "create_payload"),
    ENTITY_CREATE_DATA,
)
async def test_get_content_at_version_hard_deleted(
    client: AsyncClient,
    content_type: str,
    create_endpoint: str,
    create_payload: dict,
) -> None:
    """Test getting content at version for hard-deleted entity returns 404."""
    # Create entity
    response = await client.post(create_endpoint, json=create_payload)
    content_id = response.json()["id"]

    # Soft delete
    await client.delete(f"{create_endpoint}{content_id}")

    # Hard delete
    await client.delete(f"{create_endpoint}{content_id}", params={"permanent": True})

    # Try to get version
    response = await client.get(f"/history/{content_type}/{content_id}/version/1")
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("content_type", "create_endpoint", "create_payload"),
    ENTITY_CREATE_DATA,
)
async def test_get_content_at_version_after_delete(
    client: AsyncClient,
    content_type: str,
    create_endpoint: str,
    create_payload: dict,
) -> None:
    """Test that DELETE is an audit event (no version) and v1 is still retrievable."""
    # Create entity
    response = await client.post(create_endpoint, json=create_payload)
    content_id = response.json()["id"]

    # Soft delete (creates audit record with NULL version)
    await client.delete(f"{create_endpoint}{content_id}")

    # v1 (CREATE) should still be retrievable
    response = await client.get(f"/history/{content_type}/{content_id}/version/1")
    assert response.status_code == 200
    data = response.json()
    assert data["content"] == "Initial content"

    # v2 should not exist (DELETE has NULL version, not v2)
    response = await client.get(f"/history/{content_type}/{content_id}/version/2")
    assert response.status_code == 404


# --- Per-entity /history convenience endpoint tests ---


async def test_bookmark_history_endpoint(client: AsyncClient) -> None:
    """Test /bookmarks/{id}/history convenience endpoint."""
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://example.com", "title": "Test"},
    )
    bookmark_id = response.json()["id"]

    response = await client.get(f"/bookmarks/{bookmark_id}/history")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["content_type"] == "bookmark"
    assert data["items"][0]["metadata_snapshot"]["url"] == "https://example.com/"


async def test_note_history_endpoint(client: AsyncClient) -> None:
    """Test /notes/{id}/history convenience endpoint."""
    response = await client.post(
        "/notes/",
        json={"title": "Test Note", "content": "Content"},
    )
    note_id = response.json()["id"]

    response = await client.get(f"/notes/{note_id}/history")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["content_type"] == "note"
    assert data["items"][0]["metadata_snapshot"]["title"] == "Test Note"


async def test_prompt_history_endpoint(client: AsyncClient) -> None:
    """Test /prompts/{id}/history convenience endpoint."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "my-prompt",
            "content": "Hello {{ name }}",
            "arguments": [{"name": "name", "description": "The name"}],
        },
    )
    assert response.status_code == 201, f"Failed to create prompt: {response.json()}"
    prompt_id = response.json()["id"]

    response = await client.get(f"/prompts/{prompt_id}/history")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["content_type"] == "prompt"
    assert data["items"][0]["metadata_snapshot"]["name"] == "my-prompt"
    assert data["items"][0]["metadata_snapshot"]["arguments"] == [
        {"name": "name", "description": "The name", "required": None},
    ]


# --- Response schema validation tests ---


async def test_history_response_includes_all_fields(client: AsyncClient) -> None:
    """Test that history response includes all expected fields."""
    response = await client.post(
        "/bookmarks/",
        json={
            "url": "https://example.com",
            "title": "Test",
            "description": "Desc",
            "tags": ["tag1"],
        },
    )
    bookmark_id = response.json()["id"]

    response = await client.get(f"/history/bookmark/{bookmark_id}")
    assert response.status_code == 200

    item = response.json()["items"][0]

    # Verify all expected fields are present
    assert "id" in item
    assert "content_type" in item
    assert "content_id" in item
    assert "action" in item
    assert "version" in item
    assert "diff_type" not in item
    assert "metadata_snapshot" in item
    assert "source" in item
    assert "auth_type" in item
    assert "token_prefix" in item
    assert "created_at" in item

    # Verify UUID formats
    UUID(item["id"])
    UUID(item["content_id"])


async def test_content_at_version_response_includes_all_fields(client: AsyncClient) -> None:
    """Test that content at version response includes all expected fields."""
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://example.com", "content": "Content", "title": "Test"},
    )
    bookmark_id = response.json()["id"]

    response = await client.get(f"/history/bookmark/{bookmark_id}/version/1")
    assert response.status_code == 200

    data = response.json()

    # Verify all expected fields
    assert "content_id" in data
    assert "version" in data
    assert "content" in data
    assert "metadata" in data
    assert "warnings" in data

    # Verify values
    assert data["content_id"] == bookmark_id
    assert data["version"] == 1
    assert data["content"] == "Content"
    assert data["metadata"]["title"] == "Test"
    assert data["warnings"] is None


# --- Invalid entity type tests ---


async def test_get_entity_history_invalid_content_type(client: AsyncClient) -> None:
    """Test getting history with invalid content type returns 422."""
    fake_uuid = "00000000-0000-0000-0000-000000000000"

    response = await client.get(f"/history/invalid/{fake_uuid}")
    assert response.status_code == 422  # Validation error


async def test_get_content_at_version_invalid_content_type(client: AsyncClient) -> None:
    """Test getting content at version with invalid content type returns 422."""
    fake_uuid = "00000000-0000-0000-0000-000000000000"

    response = await client.get(f"/history/invalid/{fake_uuid}/version/1")
    assert response.status_code == 422  # Validation error


# --- Authorization tests ---


async def test_get_user_history_requires_auth(
    db_session: AsyncSession,
    redis_client,  # noqa: ARG001
) -> None:
    """Test that user history requires authentication (works in dev mode)."""
    from api.main import app  # noqa: PLC0415
    from db.session import get_async_session  # noqa: PLC0415

    get_settings.cache_clear()

    async def override_get_async_session():
        yield db_session

    app.dependency_overrides[get_async_session] = override_get_async_session

    async with HttpxAsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        # In dev mode, should work (dev user is auto-created)
        response = await test_client.get("/history/")
        assert response.status_code == 200

    app.dependency_overrides.clear()


async def test_user_cannot_access_another_users_history(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test that a user cannot access another user's history (returns empty list)."""
    from api.main import app  # noqa: PLC0415
    from db.session import get_async_session  # noqa: PLC0415

    # Create a bookmark as the dev user (user1) - this creates history
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://user1-history-test.com", "title": "User 1 Bookmark"},
    )
    assert response.status_code == 201
    user1_bookmark_id = response.json()["id"]

    # Verify user1 has history
    response = await client.get("/history/")
    assert response.status_code == 200
    user1_history = response.json()
    assert user1_history["total"] > 0

    # Create a second user and a PAT for them
    user2 = User(external_auth_id="auth0|user2-history-test", email="user2-history@example.com", tier=Tier.FREE.value)
    db_session.add(user2)
    await db_session.flush()

    # Add consent for user2 (required when dev_mode=False)
    await add_consent_for_user(db_session, user2)

    _, user2_token = await create_token(
        db_session, user2.id, TokenCreate(name="Test Token"), _DEV_LIMITS,
    )
    await db_session.flush()

    get_settings.cache_clear()

    async def override_get_async_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    def override_get_settings() -> Settings:
        return Settings(
            database_url="postgresql://test",
            dev_mode=False,
            auth0_custom_claim_namespace="https://test.example.com",
            clerk_frontend_api="test-instance.clerk.accounts.dev",
            clerk_authorized_parties_str="http://localhost:5173",
        )

    app.dependency_overrides[get_async_session] = override_get_async_session
    app.dependency_overrides[get_settings] = override_get_settings

    async with HttpxAsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {user2_token}"},
    ) as user2_client:
        # User2 should see empty history (their own, not user1's)
        response = await user2_client.get("/history/")
        assert response.status_code == 200
        user2_history = response.json()
        assert user2_history["total"] == 0
        assert user2_history["items"] == []

        # User2 should see empty history for user1's specific entity
        response = await user2_client.get(f"/history/bookmark/{user1_bookmark_id}")
        assert response.status_code == 200
        entity_history = response.json()
        assert entity_history["total"] == 0
        assert entity_history["items"] == []

        # User2 should get 404 for content at version (version doesn't exist for them)
        response = await user2_client.get(
            f"/history/bookmark/{user1_bookmark_id}/version/1",
        )
        assert response.status_code == 404

        # User2 should not be able to restore user1's entity (404 - entity not found)
        response = await user2_client.post(
            f"/history/bookmark/{user1_bookmark_id}/restore/1",
        )
        assert response.status_code == 404

    app.dependency_overrides.clear()


async def test_pat_can_access_history(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test that PAT authentication can access history endpoints (read operation)."""
    from api.main import app  # noqa: PLC0415
    from db.session import get_async_session  # noqa: PLC0415

    # Create a bookmark as the dev user first (so there's history to read)
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://pat-history-test.com", "title": "PAT History Test"},
    )
    assert response.status_code == 201
    bookmark_id = response.json()["id"]

    # Get the dev user from the database to create a PAT for them

    result = await db_session.execute(
        select(User).where(User.email == "dev@localhost"),
    )
    dev_user = result.scalar_one()

    # Ensure dev user has consent
    await add_consent_for_user(db_session, dev_user)

    # Create a PAT for the dev user
    _, pat_token = await create_token(
        db_session, dev_user.id, TokenCreate(name="History PAT"), _DEV_LIMITS,
    )
    await db_session.flush()

    get_settings.cache_clear()

    async def override_get_async_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    def override_get_settings() -> Settings:
        return Settings(
            database_url="postgresql://test",
            dev_mode=False,
            auth0_custom_claim_namespace="https://test.example.com",
            clerk_frontend_api="test-instance.clerk.accounts.dev",
            clerk_authorized_parties_str="http://localhost:5173",
        )

    app.dependency_overrides[get_async_session] = override_get_async_session
    app.dependency_overrides[get_settings] = override_get_settings

    async with HttpxAsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {pat_token}"},
    ) as pat_client:
        # PAT should be able to access user history
        response = await pat_client.get("/history/")
        assert response.status_code == 200
        history = response.json()
        assert history["total"] > 0

        # PAT should be able to access entity history
        response = await pat_client.get(f"/history/bookmark/{bookmark_id}")
        assert response.status_code == 200
        entity_history = response.json()
        assert entity_history["total"] > 0

        # PAT should be able to access content at version
        response = await pat_client.get(f"/history/bookmark/{bookmark_id}/version/1")
        assert response.status_code == 200
        content = response.json()
        assert content["version"] == 1

        # PAT should be able to access per-entity convenience endpoint
        response = await pat_client.get(f"/bookmarks/{bookmark_id}/history")
        assert response.status_code == 200

        # PAT should be able to restore (write operation)
        # First update to create v2, then restore to v1
        response = await pat_client.patch(
            f"/bookmarks/{bookmark_id}",
            json={"content": "Updated via PAT"},
        )
        assert response.status_code == 200

        response = await pat_client.post(f"/history/bookmark/{bookmark_id}/restore/1")
        assert response.status_code == 200
        assert response.json()["message"] == "Restored successfully"

    app.dependency_overrides.clear()


# --- Restore endpoint tests ---


@pytest.mark.parametrize(
    ("content_type", "create_endpoint", "create_payload", "update_payload"),
    ENTITY_TEST_DATA,
)
async def test_restore_to_version_basic(
    client: AsyncClient,
    content_type: str,
    create_endpoint: str,
    create_payload: dict,
    update_payload: dict,
) -> None:
    """Test basic restore to a previous version restores content."""
    # Create entity (v1)
    response = await client.post(create_endpoint, json=create_payload)
    assert response.status_code == 201
    content_id = response.json()["id"]

    # Update to create v2
    await client.patch(f"{create_endpoint}{content_id}", json=update_payload)

    # Verify current content is updated
    response = await client.get(f"{create_endpoint}{content_id}")
    assert response.json()["content"] == "Updated content"

    # Restore to v1
    response = await client.post(f"/history/{content_type}/{content_id}/restore/1")
    assert response.status_code == 200

    data = response.json()
    assert data["message"] == "Restored successfully"
    assert data["version"] == 1
    assert data["warnings"] is None

    # Verify content is restored to v1
    response = await client.get(f"{create_endpoint}{content_id}")
    assert response.json()["content"] == "Initial content"


@pytest.mark.parametrize(
    ("content_type", "create_endpoint", "create_payload", "update_payload"),
    ENTITY_TEST_DATA,
)
async def test_restore_creates_new_history_entry(
    client: AsyncClient,
    content_type: str,
    create_endpoint: str,
    create_payload: dict,
    update_payload: dict,
) -> None:
    """Test that restore creates a new RESTORE history entry."""
    # Create entity (v1)
    response = await client.post(create_endpoint, json=create_payload)
    content_id = response.json()["id"]

    # Update to create v2
    await client.patch(f"{create_endpoint}{content_id}", json=update_payload)

    # Restore to v1 (creates v3)
    response = await client.post(f"/history/{content_type}/{content_id}/restore/1")
    assert response.status_code == 200

    # Verify history now has 3 entries
    response = await client.get(f"/history/{content_type}/{content_id}")
    data = response.json()
    assert data["total"] == 3

    # Latest entry (v3) should be a RESTORE action
    latest = data["items"][0]
    assert latest["version"] == 3
    assert latest["action"] == "restore"


@pytest.mark.parametrize(
    ("content_type", "create_endpoint", "create_payload"),
    ENTITY_CREATE_DATA,
)
async def test_restore_to_current_version_returns_400(
    client: AsyncClient,
    content_type: str,
    create_endpoint: str,
    create_payload: dict,
) -> None:
    """Test that restoring to the current version returns 400."""
    # Create entity (v1)
    response = await client.post(create_endpoint, json=create_payload)
    content_id = response.json()["id"]

    # Try to restore to v1 (current version)
    response = await client.post(f"/history/{content_type}/{content_id}/restore/1")
    assert response.status_code == 400
    assert response.json()["detail"] == "Cannot restore to current version"


@pytest.mark.parametrize(
    ("content_type", "create_endpoint", "create_payload"),
    ENTITY_CREATE_DATA,
)
async def test_restore_nonexistent_version_returns_404(
    client: AsyncClient,
    content_type: str,
    create_endpoint: str,
    create_payload: dict,
) -> None:
    """Test that restoring to a non-existent version returns 404."""
    # Create entity (v1)
    response = await client.post(create_endpoint, json=create_payload)
    content_id = response.json()["id"]

    # Try to restore to v999
    response = await client.post(f"/history/{content_type}/{content_id}/restore/999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Version not found"


@pytest.mark.parametrize("content_type", ["bookmark", "note", "prompt"])
async def test_restore_nonexistent_entity_returns_404(
    client: AsyncClient,
    content_type: str,
) -> None:
    """Test that restoring a non-existent entity returns 404."""
    fake_uuid = "00000000-0000-0000-0000-000000000000"

    response = await client.post(f"/history/{content_type}/{fake_uuid}/restore/1")
    assert response.status_code == 404
    assert response.json()["detail"] == "Content not found"


@pytest.mark.parametrize(
    ("content_type", "create_endpoint", "create_payload"),
    ENTITY_CREATE_DATA,
)
async def test_restore_soft_deleted_entity_returns_404(
    client: AsyncClient,
    content_type: str,
    create_endpoint: str,
    create_payload: dict,
) -> None:
    """Test that restoring a soft-deleted entity returns 404 (must undelete first)."""
    # Create entity (v1)
    response = await client.post(create_endpoint, json=create_payload)
    content_id = response.json()["id"]

    # Update to create v2
    await client.patch(f"{create_endpoint}{content_id}", json={"content": "Updated"})

    # Soft delete (audit event, NULL version)
    await client.delete(f"{create_endpoint}{content_id}")

    # Try to restore to v1 - should fail because entity is soft-deleted
    response = await client.post(f"/history/{content_type}/{content_id}/restore/1")
    assert response.status_code == 404
    assert response.json()["detail"] == "Content not found"


@pytest.mark.parametrize("audit_action", ["delete", "undelete", "archive", "unarchive"])
async def test_restore_to_audit_version_returns_400(
    client: AsyncClient,
    db_session: AsyncSession,
    audit_action: str,
) -> None:
    """
    Test that the audit action check blocks restoring to audit records.

    Audit versions normally have NULL version numbers and can't be targeted by the
    restore endpoint (which requires version >= 1). This test directly manipulates
    the database to set an audit action on a versioned record to verify the
    defense-in-depth check works for all audit action types.
    """
    # Create note with v1, v2
    response = await client.post(
        "/notes/", json={"title": "Audit Test", "content": "v1"},
    )
    note_id = response.json()["id"]
    await client.patch(f"/notes/{note_id}", json={"content": "v2"})

    # Set v1's action to an audit action (simulates edge case)
    stmt = (
        update(ContentHistory)
        .where(
            ContentHistory.entity_id == note_id,
            ContentHistory.version == 1,
        )
        .values(action=audit_action)
    )
    await db_session.execute(stmt)
    await db_session.flush()

    # Try to restore to v1 (now an audit action) - should get 400
    response = await client.post(f"/history/note/{note_id}/restore/1")
    assert response.status_code == 400
    assert "audit version" in response.json()["detail"]


@pytest.mark.parametrize(
    ("content_type", "create_endpoint", "create_payload"),
    ENTITY_CREATE_DATA,
)
async def test_restore_to_version_records_restore_action(
    client: AsyncClient,
    content_type: str,
    create_endpoint: str,
    create_payload: dict,
) -> None:
    """Test that restoring to a version records a RESTORE action (not UPDATE)."""
    # Create entity (v1)
    response = await client.post(create_endpoint, json=create_payload)
    content_id = response.json()["id"]

    # Update to create v2
    await client.patch(f"{create_endpoint}{content_id}", json={"content": "Updated"})

    # Restore to v1 (creates v3)
    response = await client.post(f"/history/{content_type}/{content_id}/restore/1")
    assert response.status_code == 200

    # Verify the latest history entry is a RESTORE action
    response = await client.get(f"/history/{content_type}/{content_id}")
    data = response.json()
    assert data["total"] == 3

    latest = data["items"][0]
    assert latest["version"] == 3
    assert latest["action"] == "restore"


@pytest.mark.parametrize(
    ("content_type", "create_endpoint", "create_payload", "update_payload"),
    [
        pytest.param(
            "bookmark", "/bookmarks/",
            {"url": "https://archived-test.com", "content": "Initial content"},
            {"content": "Updated content"},
            id="bookmark",
        ),
        pytest.param(
            "note", "/notes/",
            {"title": "Test", "content": "Initial content"},
            {"content": "Updated content"},
            id="note",
        ),
        pytest.param(
            "prompt", "/prompts/",
            {"name": "archived-test-prompt", "content": "Initial content", "arguments": []},
            {"content": "Updated content"},
            id="prompt",
        ),
    ],
)
async def test_restore_archived_entity_preserves_archive_state(
    client: AsyncClient,
    content_type: str,
    create_endpoint: str,
    create_payload: dict,
    update_payload: dict,
) -> None:
    """Test that restoring an archived entity preserves archive state."""
    # Create entity (v1)
    response = await client.post(create_endpoint, json=create_payload)
    assert response.status_code == 201
    content_id = response.json()["id"]

    # Update to create v2
    await client.patch(f"{create_endpoint}{content_id}", json=update_payload)

    # Archive the entity
    past_time = datetime(2020, 1, 1, tzinfo=UTC).isoformat()
    await client.patch(f"{create_endpoint}{content_id}", json={"archived_at": past_time})

    # Restore to v1
    response = await client.post(f"/history/{content_type}/{content_id}/restore/1")
    assert response.status_code == 200

    # Verify content is restored but still archived
    response = await client.get(
        f"{create_endpoint}{content_id}", params={"include_archived": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["content"] == "Initial content"
    assert data["archived_at"] is not None


@pytest.mark.parametrize(
    ("content_type", "create_endpoint", "base_payload", "original_tags", "new_tags"),
    [
        pytest.param(
            "bookmark", "/bookmarks/",
            {"url": "https://metadata-test.com", "content": "Content"},
            ["metadata-tag1-bm", "metadata-tag2-bm"],
            ["metadata-tag3-bm"],
            id="bookmark",
        ),
        pytest.param(
            "note", "/notes/",
            {"content": "Content"},
            ["metadata-tag1-note", "metadata-tag2-note"],
            ["metadata-tag3-note"],
            id="note",
        ),
        pytest.param(
            "prompt", "/prompts/",
            {"name": "metadata-test-prompt", "content": "Content", "arguments": []},
            ["metadata-tag1-prompt", "metadata-tag2-prompt"],
            ["metadata-tag3-prompt"],
            id="prompt",
        ),
    ],
)
async def test_restore_restores_metadata(
    client: AsyncClient,
    content_type: str,
    create_endpoint: str,
    base_payload: dict,
    original_tags: list[str],
    new_tags: list[str],
) -> None:
    """Test that restore restores metadata (title, description, tags)."""
    # Create entity with metadata
    create_payload = {
        **base_payload,
        "title": "Original Title",
        "description": "Original Description",
        "tags": original_tags,
    }
    response = await client.post(create_endpoint, json=create_payload)
    assert response.status_code == 201
    content_id = response.json()["id"]

    # Update metadata
    await client.patch(
        f"{create_endpoint}{content_id}",
        json={
            "title": "New Title",
            "description": "New Description",
            "tags": new_tags,
        },
    )

    # Verify metadata changed
    response = await client.get(f"{create_endpoint}{content_id}")
    assert response.json()["title"] == "New Title"
    assert response.json()["description"] == "New Description"
    assert set(response.json()["tags"]) == set(new_tags)

    # Restore to v1
    response = await client.post(f"/history/{content_type}/{content_id}/restore/1")
    assert response.status_code == 200

    # Verify metadata is restored
    response = await client.get(f"{create_endpoint}{content_id}")
    data = response.json()
    assert data["title"] == "Original Title"
    assert data["description"] == "Original Description"
    assert set(data["tags"]) == set(original_tags)


async def test_restore_bookmark_restores_url(client: AsyncClient) -> None:
    """Test that restoring a bookmark restores the URL."""
    # Create bookmark
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://original.com", "content": "Content"},
    )
    bookmark_id = response.json()["id"]

    # Update URL
    await client.patch(f"/bookmarks/{bookmark_id}", json={"url": "https://new.com"})

    # Verify URL changed
    response = await client.get(f"/bookmarks/{bookmark_id}")
    assert response.json()["url"] == "https://new.com/"

    # Restore to v1
    response = await client.post(f"/history/bookmark/{bookmark_id}/restore/1")
    assert response.status_code == 200

    # Verify URL is restored
    response = await client.get(f"/bookmarks/{bookmark_id}")
    assert response.json()["url"] == "https://original.com/"


async def test_restore_bookmark_url_conflict_returns_409(client: AsyncClient) -> None:
    """Test that restoring to a URL that now conflicts returns 409."""
    # Create bookmark with URL A
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://url-a.com", "content": "Content"},
    )
    bookmark_id = response.json()["id"]

    # Update URL to B (v2)
    await client.patch(f"/bookmarks/{bookmark_id}", json={"url": "https://url-b.com"})

    # Create another bookmark with URL A (now takes the original URL)
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://url-a.com", "content": "Other"},
    )
    assert response.status_code == 201

    # Try to restore first bookmark to v1 (URL A) - should conflict
    response = await client.post(f"/history/bookmark/{bookmark_id}/restore/1")
    assert response.status_code == 409
    assert "URL already exists" in response.json()["detail"]


async def test_restore_prompt_restores_name_and_arguments(client: AsyncClient) -> None:
    """Test that restoring a prompt restores name and arguments."""
    # Create prompt
    response = await client.post(
        "/prompts/",
        json={
            "name": "original-name",
            "content": "Hello {{ name }}",
            "arguments": [{"name": "name", "description": "User name", "required": True}],
        },
    )
    prompt_id = response.json()["id"]

    # Update name and arguments
    await client.patch(
        f"/prompts/{prompt_id}",
        json={
            "name": "new-name",
            "content": "Goodbye",
            "arguments": [],
        },
    )

    # Verify changes
    response = await client.get(f"/prompts/{prompt_id}")
    assert response.json()["name"] == "new-name"
    assert response.json()["arguments"] == []

    # Restore to v1
    response = await client.post(f"/history/prompt/{prompt_id}/restore/1")
    assert response.status_code == 200

    # Verify prompt is restored
    response = await client.get(f"/prompts/{prompt_id}")
    data = response.json()
    assert data["name"] == "original-name"
    assert data["content"] == "Hello {{ name }}"
    assert len(data["arguments"]) == 1
    assert data["arguments"][0]["name"] == "name"


async def test_restore_prompt_name_conflict_returns_409(client: AsyncClient) -> None:
    """Test that restoring to a name that now conflicts returns 409."""
    # Create prompt with name A
    response = await client.post(
        "/prompts/",
        json={"name": "name-a", "content": "Content", "arguments": []},
    )
    prompt_id = response.json()["id"]

    # Update name to B (v2)
    await client.patch(f"/prompts/{prompt_id}", json={"name": "name-b"})

    # Create another prompt with name A (now takes the original name)
    response = await client.post(
        "/prompts/",
        json={"name": "name-a", "content": "Other", "arguments": []},
    )
    assert response.status_code == 201

    # Try to restore first prompt to v1 (name A) - should conflict
    response = await client.post(f"/history/prompt/{prompt_id}/restore/1")
    assert response.status_code == 409
    assert "name already exists" in response.json()["detail"]


@pytest.mark.parametrize(
    ("content_type", "create_endpoint", "create_payload"),
    [
        pytest.param(
            "bookmark", "/bookmarks/",
            {"url": "https://hard-delete-test.com", "content": "Content"},
            id="bookmark",
        ),
        pytest.param(
            "note", "/notes/",
            {"title": "Test", "content": "Content"},
            id="note",
        ),
        pytest.param(
            "prompt", "/prompts/",
            {"name": "hard-delete-test-prompt", "content": "Content", "arguments": []},
            id="prompt",
        ),
    ],
)
async def test_restore_hard_deleted_entity_returns_404(
    client: AsyncClient,
    content_type: str,
    create_endpoint: str,
    create_payload: dict,
) -> None:
    """Test that restoring a hard-deleted entity returns 404."""
    # Create entity
    response = await client.post(create_endpoint, json=create_payload)
    assert response.status_code == 201
    content_id = response.json()["id"]

    # Soft delete
    await client.delete(f"{create_endpoint}{content_id}")

    # Hard delete
    await client.delete(f"{create_endpoint}{content_id}", params={"permanent": True})

    # Try to restore - should fail with 404
    response = await client.post(f"/history/{content_type}/{content_id}/restore/1")
    assert response.status_code == 404
    assert response.json()["detail"] == "Content not found"


@pytest.mark.parametrize(
    ("content_type", "create_endpoint", "create_payload"),
    [
        pytest.param(
            "bookmark", "/bookmarks/",
            {"url": "https://sequential-restore-test.com", "content": "A"},
            id="bookmark",
        ),
        pytest.param(
            "note", "/notes/",
            {"title": "Test", "content": "A"},
            id="note",
        ),
        pytest.param(
            "prompt", "/prompts/",
            {"name": "sequential-restore-test", "content": "A", "arguments": []},
            id="prompt",
        ),
    ],
)
async def test_sequential_restores_maintain_chain_integrity(
    client: AsyncClient,
    content_type: str,
    create_endpoint: str,
    create_payload: dict,
) -> None:
    """Test that sequential restores maintain history chain integrity."""
    # Create entity: v1 = "A"
    response = await client.post(create_endpoint, json=create_payload)
    assert response.status_code == 201
    content_id = response.json()["id"]

    # v2 = "B"
    await client.patch(f"{create_endpoint}{content_id}", json={"content": "B"})

    # v3 = "C"
    await client.patch(f"{create_endpoint}{content_id}", json={"content": "C"})

    # Restore to v1 -> creates v4 = "A"
    response = await client.post(f"/history/{content_type}/{content_id}/restore/1")
    assert response.status_code == 200

    # Restore to v2 -> creates v5 = "B"
    response = await client.post(f"/history/{content_type}/{content_id}/restore/2")
    assert response.status_code == 200

    # Restore to v4 -> creates v6 = "A"
    response = await client.post(f"/history/{content_type}/{content_id}/restore/4")
    assert response.status_code == 200

    # Verify history has 6 entries
    response = await client.get(f"/history/{content_type}/{content_id}")
    assert response.json()["total"] == 6

    # Verify all versions are independently reconstructable
    for version in range(1, 7):
        response = await client.get(f"/history/{content_type}/{content_id}/version/{version}")
        assert response.status_code == 200
        content = response.json()["content"]
        if version in [1, 4, 6]:
            assert content == "A", f"Version {version} should be 'A'"
        elif version in [2, 5]:
            assert content == "B", f"Version {version} should be 'B'"
        elif version == 3:
            assert content == "C", f"Version {version} should be 'C'"


@pytest.mark.parametrize(
    ("content_type", "create_endpoint", "create_payload"),
    [
        pytest.param(
            "bookmark", "/bookmarks/",
            {"url": "https://invalid-version-test.com", "content": "Content"},
            id="bookmark",
        ),
        pytest.param(
            "note", "/notes/",
            {"title": "Test", "content": "Content"},
            id="note",
        ),
        pytest.param(
            "prompt", "/prompts/",
            {"name": "invalid-version-test", "content": "Content", "arguments": []},
            id="prompt",
        ),
    ],
)
async def test_restore_invalid_version_zero_returns_422(
    client: AsyncClient,
    content_type: str,
    create_endpoint: str,
    create_payload: dict,
) -> None:
    """Test that restoring to version 0 returns 422 (validation error)."""
    # Create entity
    response = await client.post(create_endpoint, json=create_payload)
    assert response.status_code == 201
    content_id = response.json()["id"]

    # Try to restore to v0 (invalid)
    response = await client.post(f"/history/{content_type}/{content_id}/restore/0")
    assert response.status_code == 422  # FastAPI validation error


@pytest.mark.parametrize(
    ("content_type", "create_endpoint", "create_payload", "tag_name"),
    [
        pytest.param(
            "bookmark", "/bookmarks/",
            {"url": "https://tag-restore-test.com", "content": "Content"},
            "tag-restore-bookmark",
            id="bookmark",
        ),
        pytest.param(
            "note", "/notes/",
            {"title": "Test", "content": "Content"},
            "tag-restore-note",
            id="note",
        ),
        pytest.param(
            "prompt", "/prompts/",
            {"name": "tag-restore-test", "content": "Content", "arguments": []},
            "tag-restore-prompt",
            id="prompt",
        ),
    ],
)
async def test_restore_creates_tags_if_missing(
    client: AsyncClient,
    content_type: str,
    create_endpoint: str,
    create_payload: dict,
    tag_name: str,
) -> None:
    """Test that restoring recreates tags that were deleted."""
    # Create entity with tag
    payload_with_tag = {**create_payload, "tags": [tag_name]}
    response = await client.post(create_endpoint, json=payload_with_tag)
    assert response.status_code == 201
    content_id = response.json()["id"]

    # Remove tag
    await client.patch(f"{create_endpoint}{content_id}", json={"tags": []})

    # Verify tag is removed
    response = await client.get(f"{create_endpoint}{content_id}")
    assert response.json()["tags"] == []

    # Restore to v1 - tag should be restored
    response = await client.post(f"/history/{content_type}/{content_id}/restore/1")
    assert response.status_code == 200

    # Verify tag is back
    response = await client.get(f"{create_endpoint}{content_id}")
    assert tag_name in response.json()["tags"]


# --- Schema evolution tests ---


async def test_restore_preserves_fields_missing_from_old_metadata(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Test that restoring to an old version with missing metadata fields
    preserves the current values for those fields.

    This simulates schema evolution: an old history record may lack fields
    that were added later. Those missing fields should NOT be overwritten.
    """
    # Create note with description (v1)
    response = await client.post(
        "/notes/",
        json={
            "title": "Original Title",
            "description": "Original Description",
            "content": "Original Content",
        },
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    # Update to create v2
    await client.patch(
        f"/notes/{note_id}",
        json={"content": "Updated Content", "description": "Updated Description"},
    )

    # Manually modify v1's metadata_snapshot to remove "description" field
    # This simulates an old record from before the description field existed
    result = await db_session.execute(
        select(ContentHistory).where(
            ContentHistory.entity_id == note_id,
            ContentHistory.version == 1,
        ),
    )
    v1_history = result.scalar_one()

    # Remove description from metadata snapshot
    modified_metadata = dict(v1_history.metadata_snapshot)
    del modified_metadata["description"]
    v1_history.metadata_snapshot = modified_metadata
    await db_session.flush()

    # Restore to v1 (which now lacks description in metadata)
    response = await client.post(f"/history/note/{note_id}/restore/1")
    assert response.status_code == 200

    # Verify: title and content restored from v1, but description PRESERVED from v2
    response = await client.get(f"/notes/{note_id}")
    data = response.json()
    assert data["title"] == "Original Title"
    assert data["content"] == "Original Content"
    assert data["description"] == "Updated Description"  # Preserved, not wiped!


async def test_restore_preserves_tags_missing_from_old_metadata(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Test that restoring to an old version with missing tags field
    preserves current tags (doesn't wipe them to empty list).
    """
    # Create note without tags (v1)
    response = await client.post(
        "/notes/",
        json={"title": "Test", "content": "Content"},
    )
    note_id = response.json()["id"]

    # Update to add tags (v2)
    await client.patch(f"/notes/{note_id}", json={"tags": ["important", "keep-me"]})

    # Modify v1's metadata to remove the tags field entirely
    result = await db_session.execute(
        select(ContentHistory).where(
            ContentHistory.entity_id == note_id,
            ContentHistory.version == 1,
        ),
    )
    v1_history = result.scalar_one()
    modified_metadata = dict(v1_history.metadata_snapshot)
    modified_metadata.pop("tags", None)
    v1_history.metadata_snapshot = modified_metadata
    await db_session.flush()

    # Restore to v1
    response = await client.post(f"/history/note/{note_id}/restore/1")
    assert response.status_code == 200

    # Verify tags are preserved (not wiped to empty)
    response = await client.get(f"/notes/{note_id}")
    tags = response.json()["tags"]
    assert set(tags) == {"important", "keep-me"}


async def test_restore_preserves_prompt_name_missing_from_old_metadata(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Test that restoring to an old version with missing 'name' field
    preserves the current name.

    Note: We test 'name' instead of 'arguments' because arguments and content
    are validated together (all arguments must be used in template). This makes
    arguments unsuitable for isolated schema evolution testing.
    """
    # Create prompt (v1)
    unique_name = f"test-schema-evolution-{uuid.uuid4().hex[:8]}"
    response = await client.post(
        "/prompts/",
        json={
            "name": unique_name,
            "content": "Hello {{ greeting }}",
            "arguments": [{"name": "greeting", "description": "A greeting"}],
        },
    )
    assert response.status_code == 201, f"Failed to create prompt: {response.json()}"
    prompt_id = response.json()["id"]

    # Update content (v2)
    await client.patch(f"/prompts/{prompt_id}", json={"content": "Goodbye {{ greeting }}"})

    # Update name (v3)
    new_name = f"updated-name-{uuid.uuid4().hex[:8]}"
    await client.patch(f"/prompts/{prompt_id}", json={"name": new_name})

    # Modify v1's metadata to remove 'name' field (simulating old schema)
    result = await db_session.execute(
        select(ContentHistory).where(
            ContentHistory.entity_id == prompt_id,
            ContentHistory.version == 1,
        ),
    )
    v1_history = result.scalar_one()
    modified_metadata = dict(v1_history.metadata_snapshot)
    modified_metadata.pop("name", None)
    v1_history.metadata_snapshot = modified_metadata
    await db_session.flush()

    # Restore to v1
    response = await client.post(f"/history/prompt/{prompt_id}/restore/1")
    assert response.status_code == 200

    # Verify name is preserved from v3, content restored from v1
    response = await client.get(f"/prompts/{prompt_id}")
    data = response.json()
    assert data["content"] == "Hello {{ greeting }}"  # Restored from v1
    assert data["name"] == new_name  # Preserved from v3, not wiped


async def test_restore_bookmark_preserves_url_missing_from_old_metadata(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Test that restoring to an old version with missing url field
    preserves current url (edge case - url should always be present).
    """
    # Create bookmark (v1)
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://original.com", "content": "Original"},
    )
    bookmark_id = response.json()["id"]

    # Update URL and content (v2)
    await client.patch(
        f"/bookmarks/{bookmark_id}",
        json={"url": "https://updated.com", "content": "Updated"},
    )

    # Modify v1's metadata to remove url field (simulating corrupted/old record)
    result = await db_session.execute(
        select(ContentHistory).where(
            ContentHistory.entity_id == bookmark_id,
            ContentHistory.version == 1,
        ),
    )
    v1_history = result.scalar_one()
    modified_metadata = dict(v1_history.metadata_snapshot)
    modified_metadata.pop("url", None)
    v1_history.metadata_snapshot = modified_metadata
    await db_session.flush()

    # Restore to v1
    response = await client.post(f"/history/bookmark/{bookmark_id}/restore/1")
    assert response.status_code == 200

    # Verify content restored but URL preserved
    response = await client.get(f"/bookmarks/{bookmark_id}")
    data = response.json()
    assert data["content"] == "Original"  # Restored from v1
    assert data["url"] == "https://updated.com/"  # Preserved from v2


# --- Restore to DELETE version tests ---


async def test_delete_is_audit_event_no_version(
    client: AsyncClient,
) -> None:
    """
    Test that DELETE is an audit event with null version.

    Scenario:
    1. Create entity (v1) with content A
    2. Delete entity (audit, version=NULL)
    3. History shows DELETE with null version
    4. Restoring to v1 (the only content version) after undelete works
    """
    # v1: Create note
    response = await client.post(
        "/notes/",
        json={
            "title": "Delete Test",
            "description": "Will be deleted",
            "content": "Pre-delete content",
            "tags": ["test-tag"],
        },
    )
    note_id = response.json()["id"]

    # Soft delete (audit event, NULL version)
    await client.delete(f"/notes/{note_id}")

    # Verify history shows DELETE with null version
    response = await client.get(f"/history/note/{note_id}")
    history = response.json()["items"]
    assert history[0]["action"] == "delete"
    assert history[0]["version"] is None

    # v1 content is still retrievable
    response = await client.get(f"/history/note/{note_id}/version/1")
    assert response.status_code == 200
    assert response.json()["content"] == "Pre-delete content"

    # Restore the entity (audit event, NULL version)
    await client.post(f"/notes/{note_id}/restore")

    # Modify the entity (v2)
    await client.patch(f"/notes/{note_id}", json={"content": "Post-restore content"})

    # Restore to v1 (original content)
    response = await client.post(f"/history/note/{note_id}/restore/1")
    assert response.status_code == 200

    # Verify entity has original content restored
    response = await client.get(f"/notes/{note_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["content"] == "Pre-delete content"
    assert data["title"] == "Delete Test"
    assert data["description"] == "Will be deleted"
    assert data["deleted_at"] is None


async def test_audit_events_dont_consume_versions(
    client: AsyncClient,
) -> None:
    """
    Test that audit events (DELETE/UNDELETE) don't consume version numbers.

    Scenario:
    1. Create entity (v1) with content A
    2. Delete entity (audit, NULL version)
    3. Restore entity (audit, NULL version)
    4. Modify entity (v2) with content B
    5. Restore to v1 → should get content A (v2 is the second content version)
    """
    # v1: Create bookmark
    response = await client.post(
        "/bookmarks/",
        json={"url": "https://delete-test.com", "content": "Version 1"},
    )
    bookmark_id = response.json()["id"]

    # Delete (audit, NULL version)
    await client.delete(f"/bookmarks/{bookmark_id}")

    # Restore (audit, NULL version)
    await client.post(f"/bookmarks/{bookmark_id}/restore")

    # v2: Modify
    await client.patch(f"/bookmarks/{bookmark_id}", json={"content": "Version 2"})

    # Verify current content
    response = await client.get(f"/bookmarks/{bookmark_id}")
    assert response.json()["content"] == "Version 2"

    # Restore to v1 (first content version)
    response = await client.post(f"/history/bookmark/{bookmark_id}/restore/1")
    assert response.status_code == 200

    # Verify content is restored to v1
    response = await client.get(f"/bookmarks/{bookmark_id}")
    assert response.json()["content"] == "Version 1"


# --- Reconstruction warnings tests ---


async def test_restore_with_reconstruction_warnings_propagates_to_response(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Test that reconstruction warnings are included in the restore response.

    When diff application encounters issues (partial patch failures),
    warnings should be propagated to help diagnose problems.
    """
    # Create note (v1) - CREATE action stores snapshot
    response = await client.post(
        "/notes/",
        json={"title": "Warning Test", "content": "AAAA\nBBBB\nCCCC\nDDDD"},
    )
    note_id = response.json()["id"]

    # Update to create v2 - stores diff from v2→v1
    await client.patch(f"/notes/{note_id}", json={"content": "EEEE\nFFFF\nGGGG\nHHHH"})

    # Update to create v3 - stores diff from v3→v2
    await client.patch(f"/notes/{note_id}", json={"content": "IIII\nJJJJ\nKKKK\nLLLL"})

    # Corrupt v3's diff. When we restore to v1:
    # - v1 is a SNAPSHOT, so we return directly (no traversal needed)
    # When we restore to v2:
    # - v2 is a DIFF record, so we need to traverse from v3 down
    # - We start with entity.content (v3's content) and apply v3's diff
    # - The corrupted diff should fail to apply
    result = await db_session.execute(
        select(ContentHistory).where(
            ContentHistory.entity_id == note_id,
            ContentHistory.version == 3,
        ),
    )
    v3_history = result.scalar_one()

    # This diff has mismatched line counts (claims 100 lines but only has 1)
    # This causes patch_apply to return [False], triggering a warning
    v3_history.content_diff = "@@ -1,100 +1,100 @@\n-NONEXISTENT\n+REPLACEMENT\n"
    await db_session.flush()

    # Restore to v2 - reconstruction should encounter the corrupted diff
    response = await client.post(f"/history/note/{note_id}/restore/2")
    assert response.status_code == 200

    data = response.json()
    assert data["message"] == "Restored successfully"
    assert data["version"] == 2
    # Warnings should be present due to diff application failure
    assert data["warnings"] is not None, f"Expected warnings but got None. Response: {data}"
    assert len(data["warnings"]) > 0
    # Warning should mention patch failure or version number
    assert any(
        "patch" in w.lower() or "v3" in w.lower() or "failure" in w.lower()
        for w in data["warnings"]
    ), f"Unexpected warning format: {data['warnings']}"


# --- Version Diff Endpoint Tests ---


@pytest.mark.parametrize(("content_type", "create_url", "create_payload", "update_payload"), ENTITY_TEST_DATA)
async def test_get_version_diff__returns_before_and_after_content(
    client: AsyncClient,
    content_type: str,
    create_url: str,
    create_payload: dict,
    update_payload: dict,
) -> None:
    """Diff at v2 returns original content as before and updated content as after."""
    # Create entity (v1)
    response = await client.post(create_url, json=create_payload)
    assert response.status_code == 201
    content_id = response.json()["id"]

    # Update content (v2)
    if content_type == "prompt":
        response = await client.patch(
            f"{create_url}name/test-prompt", json=update_payload,
        )
    else:
        response = await client.patch(f"{create_url}{content_id}", json=update_payload)
    assert response.status_code == 200

    # Get diff at v2
    response = await client.get(f"/history/{content_type}/{content_id}/version/2/diff")
    assert response.status_code == 200

    data = response.json()
    assert data["content_id"] == content_id
    assert data["version"] == 2
    assert data["after_content"] == "Updated content"
    assert data["before_content"] == "Initial content"
    assert data["after_metadata"] is not None
    assert data["before_metadata"] is not None
    assert data["warnings"] is None


@pytest.mark.parametrize(("content_type", "create_url", "create_payload"), ENTITY_CREATE_DATA)
async def test_get_version_diff__version_1_create(
    client: AsyncClient,
    content_type: str,
    create_url: str,
    create_payload: dict,
) -> None:
    """Version 1 (CREATE) has null before fields and populated after fields."""
    response = await client.post(create_url, json=create_payload)
    assert response.status_code == 201
    content_id = response.json()["id"]

    response = await client.get(f"/history/{content_type}/{content_id}/version/1/diff")
    assert response.status_code == 200

    data = response.json()
    assert data["version"] == 1
    assert data["after_content"] == create_payload["content"]
    assert data["before_content"] is None
    assert data["after_metadata"] is not None
    assert data["before_metadata"] is None


async def test_get_version_diff__metadata_only_change(client: AsyncClient) -> None:
    """Metadata-only change returns null content fields and differing metadata."""
    # Create note (v1)
    response = await client.post(
        "/notes/",
        json={"title": "Original Title", "content": "Stable content"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    # Update only title (v2) - content unchanged
    response = await client.patch(f"/notes/{note_id}", json={"title": "New Title"})
    assert response.status_code == 200

    response = await client.get(f"/history/note/{note_id}/version/2/diff")
    assert response.status_code == 200

    data = response.json()
    assert data["before_content"] is None
    assert data["after_content"] is None
    assert data["before_metadata"]["title"] == "Original Title"
    assert data["after_metadata"]["title"] == "New Title"


async def test_get_version_diff__content_and_metadata_change(client: AsyncClient) -> None:
    """Update with both content and metadata changes returns both diff pairs."""
    response = await client.post(
        "/notes/",
        json={"title": "Old Title", "content": "Old content"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    response = await client.patch(
        f"/notes/{note_id}",
        json={"title": "New Title", "content": "New content"},
    )
    assert response.status_code == 200

    response = await client.get(f"/history/note/{note_id}/version/2/diff")
    assert response.status_code == 200

    data = response.json()
    assert data["before_content"] == "Old content"
    assert data["after_content"] == "New content"
    assert data["before_metadata"]["title"] == "Old Title"
    assert data["after_metadata"]["title"] == "New Title"


async def test_get_version_diff__version_not_found(client: AsyncClient) -> None:
    """Non-existent version returns 404."""
    response = await client.post(
        "/notes/",
        json={"title": "Test", "content": "Content"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    response = await client.get(f"/history/note/{note_id}/version/99/diff")
    assert response.status_code == 404


async def test_get_version_diff__hard_deleted_entity(
    client: AsyncClient,
) -> None:
    """Hard-deleted entity returns 404."""
    fake_id = str(uuid4())
    response = await client.get(f"/history/note/{fake_id}/version/1/diff")
    assert response.status_code == 404


async def test_get_version_diff__reconstruction_warnings_propagated(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Reconstruction warnings are propagated in the diff response."""
    # Create note with 3 versions
    response = await client.post(
        "/notes/",
        json={"title": "Warning Test", "content": "v1 content"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    await client.patch(f"/notes/{note_id}", json={"content": "v2 content"})
    await client.patch(f"/notes/{note_id}", json={"content": "v3 content"})

    # Corrupt v3's diff to trigger a warning during reconstruction
    result = await db_session.execute(
        select(ContentHistory).where(
            ContentHistory.entity_id == UUID(note_id),
            ContentHistory.version == 3,
        ),
    )
    v3_history = result.scalar_one()
    v3_history.content_diff = "@@ -1,100 +1,100 @@\n-NONEXISTENT\n+REPLACEMENT\n"
    await db_session.flush()

    response = await client.get(f"/history/note/{note_id}/version/3/diff")
    assert response.status_code == 200

    data = response.json()
    assert data["warnings"] is not None
    assert len(data["warnings"]) > 0


async def test_get_version_diff__multiple_versions_chain(client: AsyncClient) -> None:
    """Diff at each version returns correct before/after pairs throughout the chain."""
    response = await client.post(
        "/notes/",
        json={"title": "Chain Test", "content": "v1 content"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    contents = ["v1 content", "v2 content", "v3 content", "v4 content"]
    for content in contents[1:]:
        await client.patch(f"/notes/{note_id}", json={"content": content})

    prev_after = None
    for v in range(1, 5):
        response = await client.get(f"/history/note/{note_id}/version/{v}/diff")
        assert response.status_code == 200
        data = response.json()

        assert data["after_content"] == contents[v - 1]

        if v == 1:
            assert data["before_content"] is None
        else:
            assert data["before_content"] == contents[v - 2]
            assert data["before_content"] == prev_after

        prev_after = data["after_content"]


async def test_get_version_diff__cross_user_isolation(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """User 2 cannot access User 1's entity diff."""
    from api.main import app  # noqa: PLC0415
    from db.session import get_async_session  # noqa: PLC0415

    # Create a note as user1
    response = await client.post(
        "/notes/",
        json={"title": "User 1 Note", "content": "User 1 content"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    # Create user2 with PAT
    user2 = User(external_auth_id="auth0|diff-cross-user", email="diff-cross@example.com", tier=Tier.FREE.value)
    db_session.add(user2)
    await db_session.flush()

    await add_consent_for_user(db_session, user2)

    _, user2_token = await create_token(
        db_session, user2.id, TokenCreate(name="Diff Test Token"), _DEV_LIMITS,
    )
    await db_session.flush()

    get_settings.cache_clear()

    async def override_get_async_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    def override_get_settings() -> Settings:
        return Settings(
            database_url="postgresql://test",
            dev_mode=False,
            auth0_custom_claim_namespace="https://test.example.com",
            clerk_frontend_api="test-instance.clerk.accounts.dev",
            clerk_authorized_parties_str="http://localhost:5173",
        )

    app.dependency_overrides[get_async_session] = override_get_async_session
    app.dependency_overrides[get_settings] = override_get_settings

    async with HttpxAsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {user2_token}"},
    ) as user2_client:
        response = await user2_client.get(f"/history/note/{note_id}/version/1/diff")
        assert response.status_code == 404

    app.dependency_overrides.clear()


async def test_get_version_diff__corrupted_diff_returns_warning_not_500(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Garbage diff text returns 200 with warning and null before_content, not 500."""
    response = await client.post(
        "/notes/",
        json={"title": "Corrupt Test", "content": "v1 content"},
    )
    assert response.status_code == 201
    note_id = response.json()["id"]

    await client.patch(f"/notes/{note_id}", json={"content": "v2 content"})

    # Corrupt v2's diff with unparseable garbage
    result = await db_session.execute(
        select(ContentHistory).where(
            ContentHistory.entity_id == UUID(note_id),
            ContentHistory.version == 2,
        ),
    )
    v2_history = result.scalar_one()
    v2_history.content_diff = "TOTALLY_INVALID_GARBAGE"
    await db_session.flush()

    response = await client.get(f"/history/note/{note_id}/version/2/diff")
    assert response.status_code == 200

    data = response.json()
    assert data["after_content"] is not None
    assert data["before_content"] is None
    assert data["warnings"] is not None
    assert len(data["warnings"]) > 0
