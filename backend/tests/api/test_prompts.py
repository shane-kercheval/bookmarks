"""Tests for prompt CRUD endpoints."""
import asyncio
from datetime import datetime, timedelta, UTC
from uuid import UUID

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.tier_limits import TierLimits
from models.prompt import Prompt
from models.user import User

from tests.api.conftest import create_user2_client


# =============================================================================
# Create Prompt Tests
# =============================================================================


async def test__create_prompt__success(client: AsyncClient, db_session: AsyncSession) -> None:
    """Test creating a new prompt with all fields."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "test-prompt",
            "title": "Test Prompt",
            "description": "A test description",
            "content": "Hello {{ user_name }}!",
            "arguments": [
                {"name": "user_name", "description": "The user's name", "required": True},
            ],
            "tags": ["example", "test"],
        },
    )
    assert response.status_code == 201

    data = response.json()
    # Verify all response fields
    assert data["name"] == "test-prompt"
    assert data["title"] == "Test Prompt"
    assert data["description"] == "A test description"
    assert data["content"] == "Hello {{ user_name }}!"
    assert data["arguments"] == [
        {"name": "user_name", "description": "The user's name", "required": True},
    ]
    assert data["tags"] == ["example", "test"]
    assert data["deleted_at"] is None
    assert data["archived_at"] is None
    assert isinstance(data["id"], str)
    assert "created_at" in data
    assert "updated_at" in data
    assert "last_used_at" in data

    # Verify in database
    result = await db_session.execute(select(Prompt).where(Prompt.id == UUID(data["id"])))
    prompt = result.scalar_one()
    assert prompt.name == "test-prompt"
    assert prompt.title == "Test Prompt"


async def test__create_prompt__minimal(client: AsyncClient) -> None:
    """Test creating a prompt with name and content (minimal required data)."""
    response = await client.post(
        "/prompts/",
        json={"name": "minimal-prompt", "content": "Hello world"},
    )
    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "minimal-prompt"
    assert data["title"] is None
    assert data["description"] is None
    assert data["content"] == "Hello world"
    assert data["arguments"] == []
    assert data["tags"] == []


async def test__create_prompt__content_required(client: AsyncClient) -> None:
    """Test that content is required for prompt creation."""
    response = await client.post(
        "/prompts/",
        json={"name": "no-content-prompt"},
    )
    # Content is required by Pydantic schema, returns 422 with validation error
    assert response.status_code == 422
    detail = response.json()["detail"]
    # Pydantic validation error format
    assert any("content" in str(err.get("loc", [])) for err in detail)


async def test__create_prompt__with_tags(client: AsyncClient) -> None:
    """Test creating a prompt with tags."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "tagged-prompt",
            "content": "Test content",
            "tags": ["code-review", "testing"],
        },
    )
    assert response.status_code == 201
    assert response.json()["tags"] == ["code-review", "testing"]


async def test__create_prompt__validation_error_invalid_name(client: AsyncClient) -> None:
    """Test that invalid prompt name is rejected."""
    # Name with underscore (should use hyphens)
    response = await client.post(
        "/prompts/",
        json={"name": "invalid_name"},
    )
    assert response.status_code == 422


async def test__create_prompt__validation_error_uppercase_name(client: AsyncClient) -> None:
    """Test that uppercase prompt name is rejected."""
    response = await client.post(
        "/prompts/",
        json={"name": "InvalidName"},
    )
    assert response.status_code == 422


async def test__create_prompt__validation_error_duplicate_arguments(client: AsyncClient) -> None:
    """Test that duplicate argument names are rejected."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "dup-args",
            "arguments": [
                {"name": "user_name"},
                {"name": "user_name"},  # Duplicate
            ],
        },
    )
    assert response.status_code == 422


async def test__create_prompt__template_syntax_error(client: AsyncClient) -> None:
    """Test that invalid Jinja2 syntax is rejected."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "bad-template",
            "content": "Hello {{ unclosed",  # Invalid syntax
        },
    )
    assert response.status_code == 400
    assert "Invalid Jinja2 syntax" in response.json()["detail"]


async def test__create_prompt__template_undefined_variable(client: AsyncClient) -> None:
    """Test that undefined template variables are rejected."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "undefined-var",
            "content": "Hello {{ user_name }}!",
            "arguments": [],  # No arguments defined
        },
    )
    assert response.status_code == 400
    assert "undefined variable" in response.json()["detail"].lower()


async def test__create_prompt__template_with_defined_arguments(client: AsyncClient) -> None:
    """Test that templates with defined arguments are accepted."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "valid-template",
            "content": "Hello {{ user_name }}, welcome to {{ project }}!",
            "arguments": [
                {"name": "user_name", "required": True},
                {"name": "project"},
            ],
        },
    )
    assert response.status_code == 201


async def test__create_prompt__name_already_exists(client: AsyncClient) -> None:
    """Test that duplicate prompt name returns 409."""
    # Create first prompt
    await client.post(
        "/prompts/",
        json={"name": "duplicate-name", "content": "First content"},
    )

    # Try to create second with same name
    response = await client.post(
        "/prompts/",
        json={"name": "duplicate-name", "content": "Second content"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["error_code"] == "NAME_CONFLICT"


async def test__create_prompt__normalizes_tags(client: AsyncClient) -> None:
    """Test that tags are normalized to lowercase."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "tag-normalize-test",
            "content": "Test content",
            "tags": ["Python", "FASTAPI", "Web-Dev"],
        },
    )
    assert response.status_code == 201
    assert response.json()["tags"] == ["python", "fastapi", "web-dev"]


async def test__create_prompt__with_future_archived_at(client: AsyncClient) -> None:
    """Test creating a prompt with a scheduled auto-archive date."""
    future_date = (datetime.now(UTC) + timedelta(days=7)).isoformat()

    response = await client.post(
        "/prompts/",
        json={
            "name": "scheduled-prompt",
            "content": "Test content",
            "archived_at": future_date,
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["archived_at"] is not None


# =============================================================================
# List Prompts Tests
# =============================================================================


async def test__list_prompts__returns_paginated_list(client: AsyncClient) -> None:
    """Test listing prompts returns paginated response."""
    # Create some prompts first
    for i in range(3):
        await client.post(
            "/prompts/",
            json={"name": f"list-prompt-{i}", "content": f"Content {i}"},
        )

    response = await client.get("/prompts/")
    assert response.status_code == 200

    data = response.json()
    assert len(data["items"]) == 3
    assert data["total"] == 3
    assert "offset" in data
    assert "limit" in data
    assert "has_more" in data


async def test__list_prompts__excludes_content_in_list_items(client: AsyncClient) -> None:
    """Test that list endpoint doesn't return content field for performance."""
    await client.post(
        "/prompts/",
        json={
            "name": "has-content",
            "content": "This is a long content that should not be in list",
        },
    )

    response = await client.get("/prompts/")
    assert response.status_code == 200
    items = response.json()["items"]
    # List items should not have content field
    for item in items:
        assert "content" not in item


async def test__list_prompts__returns_length_and_preview(client: AsyncClient) -> None:
    """Test that list endpoint returns content_length and content_preview."""
    content = "G" * 1000
    await client.post(
        "/prompts/",
        json={"name": "list-length-test", "content": content},
    )

    response = await client.get("/prompts/")
    assert response.status_code == 200

    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["content_length"] == 1000
    assert items[0]["content_preview"] == "G" * 500
    assert "content" not in items[0]


async def test__list_prompts__null_content_never_exists(client: AsyncClient) -> None:
    """Test that prompts always have content (content is required for prompts)."""
    # Prompts require content, so this test verifies the schema constraint.
    # Unlike bookmarks/notes, prompts cannot have null content.
    response = await client.post(
        "/prompts/",
        json={"name": "no-content-prompt"},  # Missing content
    )
    assert response.status_code == 422  # Content is required


async def test__list_prompts__search_query_filters(client: AsyncClient) -> None:
    """Test prompt search by query."""
    await client.post("/prompts/", json={"name": "python-review", "content": "Content 1"})
    await client.post("/prompts/", json={"name": "javascript-guide", "content": "Content 2"})
    await client.post(
        "/prompts/",
        json={"name": "code-helper", "content": "Content 3", "description": "Helps with Python code"},
    )

    response = await client.get("/prompts/", params={"q": "Python"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2


async def test__list_prompts__tag_filter(client: AsyncClient) -> None:
    """Test prompt filtering by tags."""
    await client.post("/prompts/", json={"name": "tagged-1", "content": "C1", "tags": ["python", "web"]})
    await client.post("/prompts/", json={"name": "tagged-2", "content": "C2", "tags": ["python"]})
    await client.post("/prompts/", json={"name": "untagged", "content": "C3"})

    # Filter by single tag
    response = await client.get("/prompts/", params={"tags": ["python"]})
    assert response.status_code == 200
    assert response.json()["total"] == 2

    # Filter by multiple tags (AND mode)
    response = await client.get("/prompts/", params={"tags": ["python", "web"]})
    assert response.status_code == 200
    assert response.json()["total"] == 1


async def test__list_prompts__tag_match_any(client: AsyncClient) -> None:
    """Test tag filtering with OR mode."""
    await client.post("/prompts/", json={"name": "py", "content": "C1", "tags": ["python"]})
    await client.post("/prompts/", json={"name": "js", "content": "C2", "tags": ["javascript"]})
    await client.post("/prompts/", json={"name": "none", "content": "C3", "tags": []})

    response = await client.get(
        "/prompts/",
        params={"tags": ["python", "javascript"], "tag_match": "any"},
    )
    assert response.status_code == 200
    assert response.json()["total"] == 2


async def test__list_prompts__sort_by_title(client: AsyncClient) -> None:
    """Test sorting prompts by title."""
    await client.post("/prompts/", json={"name": "b-prompt", "content": "C1", "title": "Banana"})
    await client.post("/prompts/", json={"name": "a-prompt", "content": "C2", "title": "Apple"})
    await client.post("/prompts/", json={"name": "c-prompt", "content": "C3", "title": "Cherry"})

    # Sort ascending
    response = await client.get("/prompts/", params={"sort_by": "title", "sort_order": "asc"})
    assert response.status_code == 200
    titles = [item["title"] for item in response.json()["items"]]
    assert titles == ["Apple", "Banana", "Cherry"]


async def test__list_prompts__sort_by_title_uses_name_fallback(client: AsyncClient) -> None:
    """Test that sorting by title uses name as fallback for null titles."""
    await client.post("/prompts/", json={"name": "beta", "content": "C1"})  # No title
    await client.post("/prompts/", json={"name": "alpha", "content": "C2"})  # No title
    await client.post("/prompts/", json={"name": "gamma", "content": "C3", "title": "Gamma Title"})

    response = await client.get("/prompts/", params={"sort_by": "title", "sort_order": "asc"})
    assert response.status_code == 200
    names = [item["name"] for item in response.json()["items"]]
    # Should sort by title, with name as fallback for nulls
    assert names == ["alpha", "beta", "gamma"]


async def test__list_prompts__pagination(client: AsyncClient) -> None:
    """Test prompt listing with pagination."""
    # Create 5 prompts
    for i in range(5):
        await client.post(
            "/prompts/",
            json={"name": f"paginate-{i}", "content": f"Content {i}"},
        )

    # Test limit
    response = await client.get("/prompts/?limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5
    assert data["has_more"] is True

    # Test offset
    response = await client.get("/prompts/?offset=3&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5


# =============================================================================
# View Filtering Tests
# =============================================================================


async def test__list_prompts__view_active_excludes_deleted_and_archived(
    client: AsyncClient,
) -> None:
    """Active view excludes both deleted and archived prompts."""
    r1 = await client.post("/prompts/", json={"name": "active-prompt", "content": "c"})
    r2 = await client.post("/prompts/", json={"name": "deleted-prompt", "content": "c"})
    r3 = await client.post("/prompts/", json={"name": "archived-prompt", "content": "c"})
    await client.delete(f"/prompts/{r2.json()['id']}")
    await client.post(f"/prompts/{r3.json()['id']}/archive")

    response = await client.get("/prompts/")
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == r1.json()["id"]


async def test__list_prompts__view_archived_returns_only_archived(
    client: AsyncClient,
) -> None:
    """Archived view returns only archived prompts."""
    await client.post("/prompts/", json={"name": "active-prompt", "content": "c"})
    r2 = await client.post("/prompts/", json={"name": "archived-prompt", "content": "c"})
    await client.post(f"/prompts/{r2.json()['id']}/archive")

    response = await client.get("/prompts/?view=archived")
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == r2.json()["id"]


async def test__list_prompts__view_deleted_returns_only_deleted(
    client: AsyncClient,
) -> None:
    """Deleted view returns only deleted prompts."""
    await client.post("/prompts/", json={"name": "active-prompt", "content": "c"})
    r2 = await client.post("/prompts/", json={"name": "deleted-prompt", "content": "c"})
    await client.delete(f"/prompts/{r2.json()['id']}")

    response = await client.get("/prompts/?view=deleted")
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == r2.json()["id"]


# =============================================================================
# Sort Tests
# =============================================================================


async def test__list_prompts__sort_by_created_at_desc(client: AsyncClient) -> None:
    """Sorting by created_at descending returns most recently created first."""
    r1 = await client.post("/prompts/", json={"name": "first-prompt", "content": "c"})
    await asyncio.sleep(0.01)
    r2 = await client.post("/prompts/", json={"name": "second-prompt", "content": "c"})

    response = await client.get("/prompts/?sort_by=created_at&sort_order=desc")
    items = response.json()["items"]
    assert items[0]["id"] == r2.json()["id"]
    assert items[1]["id"] == r1.json()["id"]


async def test__list_prompts__sort_by_created_at_asc(client: AsyncClient) -> None:
    """Sorting by created_at ascending returns oldest first."""
    r1 = await client.post("/prompts/", json={"name": "first-prompt", "content": "c"})
    await asyncio.sleep(0.01)
    r2 = await client.post("/prompts/", json={"name": "second-prompt", "content": "c"})

    response = await client.get("/prompts/?sort_by=created_at&sort_order=asc")
    items = response.json()["items"]
    assert items[0]["id"] == r1.json()["id"]
    assert items[1]["id"] == r2.json()["id"]


async def test__list_prompts__sort_by_title_case_insensitive(client: AsyncClient) -> None:
    """Title sorting is case-insensitive, falling back to name for untitled."""
    await client.post("/prompts/", json={"name": "code-review", "content": "c"})
    await client.post("/prompts/", json={
        "name": "decision-prompt", "content": "c", "title": "Decision Clarity",
    })
    await client.post("/prompts/", json={
        "name": "coding-prompt", "content": "c", "title": "coding Guidelines",
    })

    response = await client.get("/prompts/?sort_by=title&sort_order=asc")
    items = response.json()["items"]
    # Case-insensitive: code-review < coding Guidelines < Decision Clarity
    assert items[0]["name"] == "code-review"
    assert items[1]["title"] == "coding Guidelines"
    assert items[2]["title"] == "Decision Clarity"


# =============================================================================
# Text Search Field Coverage
# =============================================================================


async def test__list_prompts__text_search_matches_name(client: AsyncClient) -> None:
    """Text search matches prompts by name."""
    await client.post("/prompts/", json={"name": "python-helper", "content": "c"})
    await client.post("/prompts/", json={"name": "javascript-helper", "content": "c"})

    response = await client.get("/prompts/?q=python")
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["name"] == "python-helper"


async def test__list_prompts__text_search_matches_title(client: AsyncClient) -> None:
    """Text search matches prompts by title."""
    await client.post("/prompts/", json={"name": "p1", "content": "c", "title": "Python Expert"})
    await client.post("/prompts/", json={"name": "p2", "content": "c", "title": "JavaScript Expert"})

    response = await client.get("/prompts/?q=python")
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["name"] == "p1"


async def test__list_prompts__text_search_matches_description(client: AsyncClient) -> None:
    """Text search matches prompts by description."""
    await client.post("/prompts/", json={
        "name": "p1", "content": "c", "description": "Helps with Python code",
    })
    await client.post("/prompts/", json={
        "name": "p2", "content": "c", "description": "Helps with JavaScript code",
    })

    response = await client.get("/prompts/?q=python")
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["name"] == "p1"


async def test__list_prompts__text_search_matches_content(client: AsyncClient) -> None:
    """Text search matches prompts by content."""
    await client.post("/prompts/", json={"name": "p1", "content": "You are a Python expert."})
    await client.post("/prompts/", json={"name": "p2", "content": "You are a JavaScript expert."})

    response = await client.get("/prompts/?q=python")
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["name"] == "p1"


# =============================================================================
# Get Prompt by ID Tests
# =============================================================================


async def test__get_prompt__success(client: AsyncClient) -> None:
    """Test getting a single prompt by ID."""
    create_response = await client.post(
        "/prompts/",
        json={"name": "get-test", "content": "The full content"},
    )
    prompt_id = create_response.json()["id"]

    response = await client.get(f"/prompts/{prompt_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == prompt_id
    assert data["name"] == "get-test"
    assert data["content"] == "The full content"


async def test__get_prompt__includes_content(client: AsyncClient) -> None:
    """Test that GET /prompts/{id} includes content field."""
    create_response = await client.post(
        "/prompts/",
        json={"name": "content-test", "content": "Template content here"},
    )
    prompt_id = create_response.json()["id"]

    response = await client.get(f"/prompts/{prompt_id}")
    assert response.status_code == 200
    assert "content" in response.json()
    assert response.json()["content"] == "Template content here"


# Note: Cross-user isolation (IDOR) tests are in test_live_penetration.py
# Note: Common tests (get not found, archive, unarchive, delete, restore, track-usage)
# are in test_entity_common.py


# =============================================================================
# Get Prompt by Name Tests
# =============================================================================


async def test__get_prompt_by_name__success(client: AsyncClient) -> None:
    """Test getting a prompt by name."""
    await client.post(
        "/prompts/",
        json={"name": "my-prompt", "content": "Hello world"},
    )

    response = await client.get("/prompts/name/my-prompt")
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "my-prompt"
    assert data["content"] == "Hello world"


async def test__get_prompt_by_name__returns_content_length(client: AsyncClient) -> None:
    """Test that GET /prompts/name/{name} returns content_length per API contract."""
    content = "This is the template content for testing."
    await client.post(
        "/prompts/",
        json={"name": "content-length-by-name", "content": content},
    )

    response = await client.get("/prompts/name/content-length-by-name")
    assert response.status_code == 200

    data = response.json()
    assert data["content"] == content
    assert data["content_length"] == len(content)
    assert data.get("content_preview") is None


async def test__get_prompt_by_name__not_found(client: AsyncClient) -> None:
    """Test getting a non-existent prompt by name returns 404."""
    response = await client.get("/prompts/name/nonexistent")
    assert response.status_code == 404
    assert response.json()["detail"] == "Prompt not found"


async def test__get_prompt_by_name__deleted_prompt(client: AsyncClient) -> None:
    """Test that deleted prompts are not returned by name lookup."""
    create_response = await client.post(
        "/prompts/",
        json={"name": "deleted-prompt", "content": "Content"},
    )
    prompt_id = create_response.json()["id"]
    await client.delete(f"/prompts/{prompt_id}")

    response = await client.get("/prompts/name/deleted-prompt")
    assert response.status_code == 404


async def test__get_prompt_by_name__archived_prompt(client: AsyncClient) -> None:
    """Test that archived prompts are not returned by name lookup."""
    create_response = await client.post(
        "/prompts/",
        json={"name": "archived-prompt", "content": "Content"},
    )
    prompt_id = create_response.json()["id"]
    await client.post(f"/prompts/{prompt_id}/archive")

    response = await client.get("/prompts/name/archived-prompt")
    assert response.status_code == 404


async def test__get_prompt__returns_full_content_and_length(client: AsyncClient) -> None:
    """Test that GET /prompts/{id} returns full content and content_length."""
    content = "This is the full prompt template content."
    create_response = await client.post(
        "/prompts/",
        json={"name": "content-length-test", "content": content},
    )
    prompt_id = create_response.json()["id"]

    response = await client.get(f"/prompts/{prompt_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["content"] == content
    assert data["content_length"] == len(content)
    assert data.get("content_preview") is None


async def test__get_prompt_metadata__returns_length_and_preview_no_content(
    client: AsyncClient,
) -> None:
    """Test that GET /prompts/{id}/metadata returns length and preview, no full content."""
    content = "C" * 1000
    create_response = await client.post(
        "/prompts/",
        json={"name": "metadata-test", "content": content},
    )
    prompt_id = create_response.json()["id"]

    response = await client.get(f"/prompts/{prompt_id}/metadata")
    assert response.status_code == 200

    data = response.json()
    assert data["content_length"] == 1000
    assert data["content_preview"] == "C" * 500
    assert data.get("content") is None


async def test__get_prompt_by_name_metadata__returns_length_and_preview(
    client: AsyncClient,
) -> None:
    """Test that GET /prompts/name/{name}/metadata returns length and preview."""
    content = "D" * 800
    await client.post(
        "/prompts/",
        json={"name": "name-metadata-test", "content": content},
    )

    response = await client.get("/prompts/name/name-metadata-test/metadata")
    assert response.status_code == 200

    data = response.json()
    assert data["content_length"] == 800
    assert data["content_preview"] == "D" * 500
    assert data.get("content") is None


async def test__get_prompt_metadata__content_under_500_chars__preview_equals_full(
    client: AsyncClient,
) -> None:
    """Test that metadata endpoint preview equals full content when under 500 chars."""
    content = "Short prompt content"
    create_response = await client.post(
        "/prompts/",
        json={"name": "short-content-test", "content": content},
    )
    prompt_id = create_response.json()["id"]

    response = await client.get(f"/prompts/{prompt_id}/metadata")
    assert response.status_code == 200

    data = response.json()
    assert data["content_length"] == len(content)
    assert data["content_preview"] == content


async def test__get_prompt_metadata__start_line_returns_400(client: AsyncClient) -> None:
    """Test that metadata endpoint returns 400 when start_line is provided."""
    create_response = await client.post(
        "/prompts/",
        json={"name": "line-param-test-1", "content": "Test content"},
    )
    prompt_id = create_response.json()["id"]

    response = await client.get(f"/prompts/{prompt_id}/metadata", params={"start_line": 1})
    assert response.status_code == 400
    assert "start_line/end_line" in response.json()["detail"]


async def test__get_prompt_metadata__end_line_returns_400(client: AsyncClient) -> None:
    """Test that metadata endpoint returns 400 when end_line is provided."""
    create_response = await client.post(
        "/prompts/",
        json={"name": "line-param-test-2", "content": "Test content"},
    )
    prompt_id = create_response.json()["id"]

    response = await client.get(f"/prompts/{prompt_id}/metadata", params={"end_line": 10})
    assert response.status_code == 400
    assert "start_line/end_line" in response.json()["detail"]


async def test__get_prompt_by_name_metadata__start_line_returns_400(
    client: AsyncClient,
) -> None:
    """Test that /prompts/name/{name}/metadata returns 400 when start_line is provided."""
    await client.post(
        "/prompts/",
        json={"name": "name-line-param-1", "content": "Test content"},
    )

    response = await client.get(
        "/prompts/name/name-line-param-1/metadata", params={"start_line": 1},
    )
    assert response.status_code == 400
    assert "start_line/end_line" in response.json()["detail"]


async def test__get_prompt_by_name_metadata__end_line_returns_400(
    client: AsyncClient,
) -> None:
    """Test that /prompts/name/{name}/metadata returns 400 when end_line is provided."""
    await client.post(
        "/prompts/",
        json={"name": "name-line-param-2", "content": "Test content"},
    )

    response = await client.get(
        "/prompts/name/name-line-param-2/metadata", params={"end_line": 10},
    )
    assert response.status_code == 400
    assert "start_line/end_line" in response.json()["detail"]


# =============================================================================
# Update Prompt Tests
# =============================================================================


async def test__update_prompt__success(client: AsyncClient) -> None:
    """Test updating a prompt."""
    create_response = await client.post(
        "/prompts/",
        json={"name": "original", "content": "Original content"},
    )
    prompt_id = create_response.json()["id"]

    response = await client.patch(
        f"/prompts/{prompt_id}",
        json={"title": "Updated Title", "tags": ["updated"]},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["title"] == "Updated Title"
    assert data["tags"] == ["updated"]
    # Name and content should remain unchanged
    assert data["name"] == "original"
    assert data["content"] == "Original content"


async def test__update_prompt__partial_update(client: AsyncClient) -> None:
    """Test partial update only changes specified fields."""
    create_response = await client.post(
        "/prompts/",
        json={
            "name": "partial-test",
            "content": "Content",
            "title": "Original Title",
            "description": "Original description",
        },
    )
    prompt_id = create_response.json()["id"]

    # Update only title
    response = await client.patch(
        f"/prompts/{prompt_id}",
        json={"title": "New Title"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["title"] == "New Title"
    assert data["description"] == "Original description"  # Unchanged


async def test__update_prompt__update_tags(client: AsyncClient) -> None:
    """Test updating prompt tags."""
    create_response = await client.post(
        "/prompts/",
        json={"name": "tag-update", "content": "Content", "tags": ["original"]},
    )
    prompt_id = create_response.json()["id"]

    response = await client.patch(
        f"/prompts/{prompt_id}",
        json={"tags": ["new-tag-1", "new-tag-2"]},
    )
    assert response.status_code == 200
    assert response.json()["tags"] == ["new-tag-1", "new-tag-2"]


async def test__update_prompt__clear_tags_with_empty_list(client: AsyncClient) -> None:
    """Test clearing tags by sending empty list."""
    create_response = await client.post(
        "/prompts/",
        json={"name": "clear-tags", "content": "Content", "tags": ["some-tag"]},
    )
    prompt_id = create_response.json()["id"]

    response = await client.patch(
        f"/prompts/{prompt_id}",
        json={"tags": []},
    )
    assert response.status_code == 200
    assert response.json()["tags"] == []


async def test__update_prompt__validation_error(client: AsyncClient) -> None:
    """Test that invalid update data returns 422."""
    create_response = await client.post(
        "/prompts/",
        json={"name": "validation-test", "content": "Content"},
    )
    prompt_id = create_response.json()["id"]

    # Try to update with invalid name
    response = await client.patch(
        f"/prompts/{prompt_id}",
        json={"name": "invalid_name"},  # Underscores not allowed
    )
    assert response.status_code == 422


async def test__update_prompt__template_syntax_error(client: AsyncClient) -> None:
    """Test that template syntax error on update returns 400."""
    create_response = await client.post(
        "/prompts/",
        json={"name": "template-update", "content": "Original content"},
    )
    prompt_id = create_response.json()["id"]

    response = await client.patch(
        f"/prompts/{prompt_id}",
        json={"content": "{{ unclosed"},
    )
    assert response.status_code == 400
    assert "Invalid Jinja2 syntax" in response.json()["detail"]


async def test__update_prompt__not_found(client: AsyncClient) -> None:
    """Test updating a non-existent prompt returns 404."""
    response = await client.patch(
        "/prompts/00000000-0000-0000-0000-000000000000",
        json={"title": "Won't Work"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Prompt not found"


async def test__update_prompt__name_conflict(client: AsyncClient) -> None:
    """Test that updating to an existing name returns 409."""
    # Create two prompts
    await client.post("/prompts/", json={"name": "existing-name", "content": "C1"})
    create_response = await client.post("/prompts/", json={"name": "other-name", "content": "C2"})
    prompt_id = create_response.json()["id"]

    # Try to rename to existing name
    response = await client.patch(
        f"/prompts/{prompt_id}",
        json={"name": "existing-name"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["error_code"] == "NAME_CONFLICT"


async def test__update_prompt__updates_updated_at(client: AsyncClient) -> None:
    """Test that updating a prompt updates the updated_at timestamp."""
    create_response = await client.post(
        "/prompts/",
        json={"name": "timestamp-test", "content": "Content"},
    )
    original_updated_at = create_response.json()["updated_at"]
    prompt_id = create_response.json()["id"]

    await asyncio.sleep(0.01)

    response = await client.patch(
        f"/prompts/{prompt_id}",
        json={"title": "New Title"},
    )
    assert response.status_code == 200
    assert response.json()["updated_at"] > original_updated_at


async def test__update_prompt__no_op_does_not_update_timestamp(client: AsyncClient) -> None:
    """
    Test that a no-op update (empty payload) does not change updated_at.

    This is important for HTTP caching - ETag/Last-Modified should remain stable
    when no actual changes are made to the prompt.
    """
    create_response = await client.post(
        "/prompts/",
        json={"name": "noop-test", "content": "Content"},
    )
    original_updated_at = create_response.json()["updated_at"]
    prompt_id = create_response.json()["id"]

    await asyncio.sleep(0.01)

    # Send an empty update - no fields provided
    response = await client.patch(
        f"/prompts/{prompt_id}",
        json={},
    )
    assert response.status_code == 200
    # updated_at should remain unchanged
    assert response.json()["updated_at"] == original_updated_at


# =============================================================================
# Restore Prompt Tests (prompt-specific behavior only)
# =============================================================================


async def test__restore_prompt__clears_both_timestamps(client: AsyncClient) -> None:
    """Test that restore clears both deleted_at and archived_at."""
    create_response = await client.post(
        "/prompts/",
        json={"name": "archived-then-deleted", "content": "Content"},
    )
    prompt_id = create_response.json()["id"]

    await client.post(f"/prompts/{prompt_id}/archive")
    await client.delete(f"/prompts/{prompt_id}")

    response = await client.post(f"/prompts/{prompt_id}/restore")
    assert response.status_code == 200
    assert response.json()["deleted_at"] is None
    assert response.json()["archived_at"] is None


# =============================================================================
# Content List Integration Tests
# =============================================================================


async def test__list_prompts__with_filter_id(client: AsyncClient) -> None:
    """Test filtering prompts by filter_id parameter."""
    # Create prompts with different tags
    await client.post(
        "/prompts/",
        json={"name": "work-priority", "content": "C1", "tags": ["work", "priority"]},
    )
    await client.post(
        "/prompts/",
        json={"name": "work-only", "content": "C2", "tags": ["work"]},
    )
    await client.post(
        "/prompts/",
        json={"name": "personal", "content": "C3", "tags": ["personal"]},
    )

    # Create a list that filters for work AND priority
    response = await client.post(
        "/filters/",
        json={
            "name": "Work Priority List",
            "content_types": ["prompt"],
            "filter_expression": {
                "groups": [{"tags": ["work", "priority"]}],
                "group_operator": "OR",
            },
        },
    )
    assert response.status_code == 201
    filter_id = response.json()["id"]

    # Filter prompts by filter_id
    response = await client.get(f"/prompts/?filter_id={filter_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "work-priority"


async def test__list_prompts__with_filter_id_not_found(client: AsyncClient) -> None:
    """Test that non-existent filter_id returns 404."""
    response = await client.get("/prompts/?filter_id=00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["detail"] == "Filter not found"


# =============================================================================
# Template Validation on Update Tests
# =============================================================================


async def test__update_prompt__validates_when_removing_used_argument(
    client: AsyncClient,
) -> None:
    """Test that removing an argument still used in template fails."""
    create_response = await client.post(
        "/prompts/",
        json={
            "name": "arg-removal-test",
            "content": "Hello {{ user_name }}!",
            "arguments": [{"name": "user_name", "required": True}],
        },
    )
    prompt_id = create_response.json()["id"]

    # Try to remove the argument while content still uses it
    response = await client.patch(
        f"/prompts/{prompt_id}",
        json={"arguments": []},  # Remove all arguments
    )
    assert response.status_code == 400
    assert "undefined variable" in response.json()["detail"].lower()


async def test__update_prompt__validates_when_adding_undefined_var(
    client: AsyncClient,
) -> None:
    """Test that adding template var without argument fails."""
    create_response = await client.post(
        "/prompts/",
        json={"name": "var-add-test", "content": "Original content"},
    )
    prompt_id = create_response.json()["id"]

    # Try to add content with undefined variable
    response = await client.patch(
        f"/prompts/{prompt_id}",
        json={"content": "Hello {{ new_var }}!"},
    )
    assert response.status_code == 400
    assert "undefined variable" in response.json()["detail"].lower()


async def test__update_prompt__validates_merged_state(client: AsyncClient) -> None:
    """Test that validation uses merged state of content and arguments."""
    create_response = await client.post(
        "/prompts/",
        json={
            "name": "merged-state-test",
            "content": "Hello {{ user_name }}!",
            "arguments": [{"name": "user_name"}],
        },
    )
    prompt_id = create_response.json()["id"]

    # Update both content and arguments at once - should validate merged state
    response = await client.patch(
        f"/prompts/{prompt_id}",
        json={
            "content": "Hello {{ user_name }} from {{ project }}!",
            "arguments": [
                {"name": "user_name"},
                {"name": "project"},
            ],
        },
    )
    assert response.status_code == 200


# =============================================================================
# Argument Validation Tests
# =============================================================================


async def test__create_prompt__argument_name_with_underscore(client: AsyncClient) -> None:
    """Test that argument names can have underscores."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "underscore-args",
            "content": "Hello {{ user_name }}, here is {{ code_block }}",
            "arguments": [{"name": "user_name"}, {"name": "code_block"}],
        },
    )
    assert response.status_code == 201


async def test__create_prompt__argument_name_with_hyphen_rejected(
    client: AsyncClient,
) -> None:
    """Test that argument names with hyphens are rejected."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "hyphen-arg-test",
            "arguments": [{"name": "user-name"}],  # Invalid - hyphens not allowed
        },
    )
    assert response.status_code == 422


# =============================================================================
# Render Prompt Tests
# =============================================================================


async def test__render_prompt__simple_template(client: AsyncClient) -> None:
    """Test rendering a simple template with one argument."""
    # Create prompt
    create_response = await client.post(
        "/prompts/",
        json={
            "name": "render-simple",
            "content": "Hello, {{ name }}!",
            "arguments": [{"name": "name", "required": True}],
        },
    )
    assert create_response.status_code == 201
    prompt_id = create_response.json()["id"]

    # Render with argument
    response = await client.post(
        f"/prompts/{prompt_id}/render",
        json={"arguments": {"name": "World"}},
    )
    assert response.status_code == 200
    assert response.json()["rendered_content"] == "Hello, World!"


async def test__render_prompt__multiple_arguments(client: AsyncClient) -> None:
    """Test rendering a template with multiple arguments."""
    # Create prompt
    create_response = await client.post(
        "/prompts/",
        json={
            "name": "render-multi",
            "content": "{{ greeting }}, {{ name }}! Welcome to {{ place }}.",
            "arguments": [
                {"name": "greeting", "required": True},
                {"name": "name", "required": True},
                {"name": "place", "required": True},
            ],
        },
    )
    assert create_response.status_code == 201
    prompt_id = create_response.json()["id"]

    # Render with all arguments
    response = await client.post(
        f"/prompts/{prompt_id}/render",
        json={"arguments": {"greeting": "Hello", "name": "Alice", "place": "Python"}},
    )
    assert response.status_code == 200
    assert response.json()["rendered_content"] == "Hello, Alice! Welcome to Python."


async def test__render_prompt__missing_required_argument(client: AsyncClient) -> None:
    """Test that missing required argument returns 400."""
    # Create prompt
    create_response = await client.post(
        "/prompts/",
        json={
            "name": "render-required",
            "content": "Hello, {{ name }}!",
            "arguments": [{"name": "name", "required": True}],
        },
    )
    assert create_response.status_code == 201
    prompt_id = create_response.json()["id"]

    # Render without required argument
    response = await client.post(
        f"/prompts/{prompt_id}/render",
        json={"arguments": {}},
    )
    assert response.status_code == 400
    assert "Missing required argument" in response.json()["detail"]
    assert "name" in response.json()["detail"]


async def test__render_prompt__unknown_argument(client: AsyncClient) -> None:
    """Test that unknown argument returns 400."""
    # Create prompt with one argument
    create_response = await client.post(
        "/prompts/",
        json={
            "name": "render-unknown",
            "content": "Hello, {{ name }}!",
            "arguments": [{"name": "name", "required": True}],
        },
    )
    assert create_response.status_code == 201
    prompt_id = create_response.json()["id"]

    # Render with extra argument
    response = await client.post(
        f"/prompts/{prompt_id}/render",
        json={"arguments": {"name": "World", "extra": "value"}},
    )
    assert response.status_code == 400
    assert "Unknown argument" in response.json()["detail"]
    assert "extra" in response.json()["detail"]


async def test__render_prompt__sandbox_blocks_ssti_escape(client: AsyncClient) -> None:
    """SSTI escape via attribute traversal returns 400, not 500 or a rendered escape."""
    # Declares `x` (optional), so create-time validation passes; the render-time
    # sandbox must block the attribute traversal.
    create_response = await client.post(
        "/prompts/",
        json={
            "name": "render-ssti-escape",
            "content": "{{ x.__class__.__mro__[1].__subclasses__() }}",
            "arguments": [{"name": "x", "required": False}],
        },
    )
    assert create_response.status_code == 201
    prompt_id = create_response.json()["id"]

    response = await client.post(
        f"/prompts/{prompt_id}/render",
        json={"arguments": {}},
    )
    assert response.status_code == 400
    assert "disallowed operation" in response.json()["detail"]


async def test__render_prompt__optional_argument_omitted(client: AsyncClient) -> None:
    """Test that optional arguments default to empty string for conditionals."""
    # Create prompt with optional argument
    create_response = await client.post(
        "/prompts/",
        json={
            "name": "render-optional",
            "content": "Hello{% if suffix %}, {{ suffix }}{% endif %}!",
            "arguments": [{"name": "suffix", "required": False}],
        },
    )
    assert create_response.status_code == 201
    prompt_id = create_response.json()["id"]

    # Render without optional argument
    response = await client.post(
        f"/prompts/{prompt_id}/render",
        json={"arguments": {}},
    )
    assert response.status_code == 200
    assert response.json()["rendered_content"] == "Hello!"


async def test__render_prompt__optional_argument_provided(client: AsyncClient) -> None:
    """Test that optional argument enables conditional block when provided."""
    # Create prompt with optional argument
    create_response = await client.post(
        "/prompts/",
        json={
            "name": "render-optional-provided",
            "content": "Hello{% if suffix %}, {{ suffix }}{% endif %}!",
            "arguments": [{"name": "suffix", "required": False}],
        },
    )
    assert create_response.status_code == 201
    prompt_id = create_response.json()["id"]

    # Render with optional argument
    response = await client.post(
        f"/prompts/{prompt_id}/render",
        json={"arguments": {"suffix": "friend"}},
    )
    assert response.status_code == 200
    assert response.json()["rendered_content"] == "Hello, friend!"


async def test__render_prompt__not_found(client: AsyncClient) -> None:
    """Test that rendering non-existent prompt returns 404."""
    response = await client.post(
        "/prompts/00000000-0000-0000-0000-000000000000/render",
        json={"arguments": {}},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Prompt not found"


async def test__render_prompt__no_content(client: AsyncClient, db_session: AsyncSession) -> None:
    """Test that prompt with no content returns empty string."""
    # Create prompt with content, then update to remove it
    # (content is required on create, so we need to update after)
    create_response = await client.post(
        "/prompts/",
        json={
            "name": "render-no-content",
            "content": "Initial content",
        },
    )
    assert create_response.status_code == 201
    prompt_id = create_response.json()["id"]

    # Directly update in DB to set content to empty (bypass API validation)
    result = await db_session.execute(select(Prompt).where(Prompt.id == UUID(prompt_id)))
    prompt = result.scalar_one()
    prompt.content = ""
    await db_session.commit()

    # Render prompt with empty content
    response = await client.post(
        f"/prompts/{prompt_id}/render",
        json={"arguments": {}},
    )
    assert response.status_code == 200
    assert response.json()["rendered_content"] == ""


async def test__render_prompt__archived_prompt(client: AsyncClient) -> None:
    """Test that archived prompts can be rendered."""
    # Create prompt
    create_response = await client.post(
        "/prompts/",
        json={
            "name": "render-archived",
            "content": "Hello, {{ name }}!",
            "arguments": [{"name": "name", "required": True}],
        },
    )
    assert create_response.status_code == 201
    prompt_id = create_response.json()["id"]

    # Archive it
    archive_response = await client.post(f"/prompts/{prompt_id}/archive")
    assert archive_response.status_code == 200

    # Render should still work
    response = await client.post(
        f"/prompts/{prompt_id}/render",
        json={"arguments": {"name": "World"}},
    )
    assert response.status_code == 200
    assert response.json()["rendered_content"] == "Hello, World!"


async def test__render_prompt__deleted_prompt(client: AsyncClient) -> None:
    """Test that soft-deleted prompts can be rendered."""
    # Create prompt
    create_response = await client.post(
        "/prompts/",
        json={
            "name": "render-deleted",
            "content": "Hello, {{ name }}!",
            "arguments": [{"name": "name", "required": True}],
        },
    )
    assert create_response.status_code == 201
    prompt_id = create_response.json()["id"]

    # Soft delete it
    delete_response = await client.delete(f"/prompts/{prompt_id}")
    assert delete_response.status_code == 204

    # Render should still work
    response = await client.post(
        f"/prompts/{prompt_id}/render",
        json={"arguments": {"name": "World"}},
    )
    assert response.status_code == 200
    assert response.json()["rendered_content"] == "Hello, World!"


async def test__render_prompt__no_arguments_static_content(client: AsyncClient) -> None:
    """Test rendering a prompt with no arguments (static content)."""
    # Create prompt with no arguments
    create_response = await client.post(
        "/prompts/",
        json={
            "name": "render-static",
            "content": "This is static content with no variables.",
        },
    )
    assert create_response.status_code == 201
    prompt_id = create_response.json()["id"]

    # Render with empty arguments
    response = await client.post(
        f"/prompts/{prompt_id}/render",
        json={"arguments": {}},
    )
    assert response.status_code == 200
    assert response.json()["rendered_content"] == "This is static content with no variables."


async def test__render_prompt__complex_jinja_template(client: AsyncClient) -> None:
    """Test rendering complex Jinja2 templates with conditionals and whitespace control."""
    # Create prompt with complex template
    create_response = await client.post(
        "/prompts/",
        json={
            "name": "render-complex",
            "content": """{%- if formal -%}Dear {{ name }},{%- else -%}Hey {{ name }}!{%- endif -%}""",
            "arguments": [
                {"name": "name", "required": True},
                {"name": "formal", "required": False},
            ],
        },
    )
    assert create_response.status_code == 201
    prompt_id = create_response.json()["id"]

    # Render with formal=true
    response = await client.post(
        f"/prompts/{prompt_id}/render",
        json={"arguments": {"name": "Bob", "formal": "true"}},
    )
    assert response.status_code == 200
    assert response.json()["rendered_content"] == "Dear Bob,"

    # Render without formal (defaults to empty, falsy)
    response = await client.post(
        f"/prompts/{prompt_id}/render",
        json={"arguments": {"name": "Bob"}},
    )
    assert response.status_code == 200
    assert response.json()["rendered_content"] == "Hey Bob!"


async def test__render_prompt__preserves_whitespace(client: AsyncClient) -> None:
    """Test that rendering preserves whitespace in content."""
    # Create prompt with intentional whitespace
    create_response = await client.post(
        "/prompts/",
        json={
            "name": "render-whitespace",
            "content": "Line 1\n\nLine 3\n  Indented line\n\n{{ text }}",
            "arguments": [{"name": "text", "required": True}],
        },
    )
    assert create_response.status_code == 201
    prompt_id = create_response.json()["id"]

    # Render and verify whitespace preserved
    response = await client.post(
        f"/prompts/{prompt_id}/render",
        json={"arguments": {"text": "Final line"}},
    )
    assert response.status_code == 200
    assert response.json()["rendered_content"] == "Line 1\n\nLine 3\n  Indented line\n\nFinal line"


async def test__render_prompt__jinja_filter(client: AsyncClient) -> None:
    """Test rendering template with Jinja2 filters."""
    # Create prompt with filter
    create_response = await client.post(
        "/prompts/",
        json={
            "name": "render-filter",
            "content": "{{ name | upper }}",
            "arguments": [{"name": "name", "required": True}],
        },
    )
    assert create_response.status_code == 201
    prompt_id = create_response.json()["id"]

    # Render with filter
    response = await client.post(
        f"/prompts/{prompt_id}/render",
        json={"arguments": {"name": "hello"}},
    )
    assert response.status_code == 200
    assert response.json()["rendered_content"] == "HELLO"


# =============================================================================
# Partial Read Tests
# =============================================================================


async def test__get_prompt__full_read_includes_content_metadata(client: AsyncClient) -> None:
    """Test that full read includes content_metadata with is_partial=false."""
    response = await client.post(
        "/prompts/",
        json={"name": "partial-test-prompt", "content": "line 1\nline 2\nline 3"},
    )
    prompt_id = response.json()["id"]

    response = await client.get(f"/prompts/{prompt_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["content"] == "line 1\nline 2\nline 3"
    assert data["content_metadata"] is not None
    assert data["content_metadata"]["total_lines"] == 3
    assert data["content_metadata"]["is_partial"] is False


async def test__get_prompt__partial_read_with_both_params(client: AsyncClient) -> None:
    """Test partial read with start_line and end_line."""
    response = await client.post(
        "/prompts/",
        json={"name": "partial-test-prompt-2", "content": "line 1\nline 2\nline 3\nline 4"},
    )
    prompt_id = response.json()["id"]

    response = await client.get(
        f"/prompts/{prompt_id}",
        params={"start_line": 2, "end_line": 3},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["content"] == "line 2\nline 3"
    assert data["content_metadata"]["total_lines"] == 4
    assert data["content_metadata"]["start_line"] == 2
    assert data["content_metadata"]["end_line"] == 3
    assert data["content_metadata"]["is_partial"] is True


async def test__get_prompt_by_name__partial_read(client: AsyncClient) -> None:
    """Test partial read via get_prompt_by_name endpoint."""
    response = await client.post(
        "/prompts/",
        json={"name": "partial-name-test", "content": "line 1\nline 2\nline 3"},
    )
    assert response.status_code == 201

    response = await client.get(
        "/prompts/name/partial-name-test",
        params={"start_line": 2, "end_line": 3},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["content"] == "line 2\nline 3"
    assert data["content_metadata"]["total_lines"] == 3
    assert data["content_metadata"]["start_line"] == 2
    assert data["content_metadata"]["end_line"] == 3
    assert data["content_metadata"]["is_partial"] is True


async def test__get_prompt_by_name__full_read_includes_metadata(client: AsyncClient) -> None:
    """Test that get_prompt_by_name includes content_metadata for full reads."""
    response = await client.post(
        "/prompts/",
        json={"name": "full-name-test", "content": "line 1\nline 2"},
    )
    assert response.status_code == 201

    response = await client.get("/prompts/name/full-name-test")
    assert response.status_code == 200

    data = response.json()
    assert data["content_metadata"] is not None
    assert data["content_metadata"]["total_lines"] == 2
    assert data["content_metadata"]["is_partial"] is False


async def test__get_prompt__start_line_exceeds_total_returns_400(client: AsyncClient) -> None:
    """Test that start_line > total_lines returns 400."""
    response = await client.post(
        "/prompts/",
        json={"name": "partial-test-prompt-3", "content": "line 1\nline 2"},
    )
    prompt_id = response.json()["id"]

    response = await client.get(f"/prompts/{prompt_id}", params={"start_line": 10})
    assert response.status_code == 400
    assert "exceeds total lines" in response.json()["detail"]


async def test__get_prompt_by_name__start_line_exceeds_total_returns_400(
    client: AsyncClient,
) -> None:
    """Test that start_line > total_lines returns 400 for get_by_name."""
    response = await client.post(
        "/prompts/",
        json={"name": "partial-name-err-test", "content": "line 1\nline 2"},
    )
    assert response.status_code == 201

    response = await client.get(
        "/prompts/name/partial-name-err-test",
        params={"start_line": 10},
    )
    assert response.status_code == 400
    assert "exceeds total lines" in response.json()["detail"]


# =============================================================================
# Within-Content Search Tests
# =============================================================================


async def test_search_in_prompt_basic(client: AsyncClient) -> None:
    """Test basic search within a prompt's content."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "search-test-prompt",
            "content": "line 1\nline 2 with target\nline 3",
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    response = await client.get(
        f"/prompts/{prompt_id}/search",
        params={"q": "target"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["total_matches"] == 1
    assert len(data["matches"]) == 1
    assert data["matches"][0]["field"] == "content"
    assert data["matches"][0]["line"] == 2
    assert "target" in data["matches"][0]["context"]


async def test_search_in_prompt_no_matches_returns_empty(client: AsyncClient) -> None:
    """Test that no matches returns empty array (not error)."""
    response = await client.post(
        "/prompts/",
        json={"name": "no-matches-prompt", "content": "some content here"},
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    response = await client.get(
        f"/prompts/{prompt_id}/search",
        params={"q": "nonexistent"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["total_matches"] == 0
    assert data["matches"] == []


async def test_search_in_prompt_title_field(client: AsyncClient) -> None:
    """Test searching in title field returns full title as context."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "title-search-prompt",
            "title": "Important Code Review Prompt",
            "content": "content here",
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    response = await client.get(
        f"/prompts/{prompt_id}/search",
        params={"q": "review", "fields": "title"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["total_matches"] == 1
    assert data["matches"][0]["field"] == "title"
    assert data["matches"][0]["line"] is None
    assert data["matches"][0]["context"] == "Important Code Review Prompt"


async def test_search_in_prompt_multiple_fields(client: AsyncClient) -> None:
    """Test searching across multiple fields."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "multi-field-prompt",
            "title": "Python Code Review",
            "description": "Review Python code for best practices",
            "content": "Please review this Python code:\n{{ code }}",
            "arguments": [{"name": "code", "required": True}],
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    response = await client.get(
        f"/prompts/{prompt_id}/search",
        params={"q": "python", "fields": "content,title,description"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["total_matches"] == 3
    fields = {m["field"] for m in data["matches"]}
    assert fields == {"content", "title", "description"}


async def test_search_in_prompt_case_sensitive(client: AsyncClient) -> None:
    """Test case-sensitive search."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "case-sensitive-prompt",
            "content": "Hello World",
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    # Case-sensitive search should not match
    response = await client.get(
        f"/prompts/{prompt_id}/search",
        params={"q": "WORLD", "case_sensitive": True},
    )
    assert response.status_code == 200
    assert response.json()["total_matches"] == 0

    # Exact case should match
    response = await client.get(
        f"/prompts/{prompt_id}/search",
        params={"q": "World", "case_sensitive": True},
    )
    assert response.status_code == 200
    assert response.json()["total_matches"] == 1


async def test_search_in_prompt_not_found(client: AsyncClient) -> None:
    """Test 404 when prompt doesn't exist."""
    response = await client.get(
        "/prompts/00000000-0000-0000-0000-000000000000/search",
        params={"q": "test"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Prompt not found"


async def test_search_in_prompt_invalid_field(client: AsyncClient) -> None:
    """Test 400 when invalid field is specified."""
    response = await client.post(
        "/prompts/",
        json={"name": "invalid-field-prompt", "content": "content"},
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    response = await client.get(
        f"/prompts/{prompt_id}/search",
        params={"q": "test", "fields": "content,invalid"},
    )
    assert response.status_code == 400
    assert "Invalid fields" in response.json()["detail"]


async def test_search_in_prompt_works_on_archived(client: AsyncClient) -> None:
    """Test that search works on archived prompts."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "archived-search-prompt",
            "content": "search target here",
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    # Archive the prompt
    await client.post(f"/prompts/{prompt_id}/archive")

    # Search should still work
    response = await client.get(
        f"/prompts/{prompt_id}/search",
        params={"q": "target"},
    )
    assert response.status_code == 200
    assert response.json()["total_matches"] == 1


async def test_search_in_prompt_works_on_deleted(client: AsyncClient) -> None:
    """Test that search works on soft-deleted prompts."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "deleted-search-prompt",
            "content": "search target here",
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    # Delete the prompt
    await client.delete(f"/prompts/{prompt_id}")

    # Search should still work
    response = await client.get(
        f"/prompts/{prompt_id}/search",
        params={"q": "target"},
    )
    assert response.status_code == 200
    assert response.json()["total_matches"] == 1


async def test_search_in_prompt_jinja_template(client: AsyncClient) -> None:
    """Test searching in a prompt with Jinja2 template syntax."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "jinja-search-prompt",
            "content": "Please review:\n{{ code }}\nProvide feedback:",
            "arguments": [{"name": "code", "required": True}],
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    # Search for Jinja2 variable
    response = await client.get(
        f"/prompts/{prompt_id}/search",
        params={"q": "{{ code }}"},
    )
    assert response.status_code == 200
    assert response.json()["total_matches"] == 1
    assert response.json()["matches"][0]["line"] == 2


# =============================================================================
# Str-Replace Tests
# =============================================================================


async def test_str_replace_prompt_success_minimal(client: AsyncClient) -> None:
    """Test successful str-replace returns minimal response by default."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "str-replace-test-minimal",
            "content": "Hello world",
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    response = await client.patch(
        f"/prompts/{prompt_id}/str-replace",
        json={"old_str": "world", "new_str": "universe"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["response_type"] == "minimal"
    assert data["match_type"] == "exact"
    assert data["line"] == 1
    # Default response is minimal - only id and updated_at
    assert data["data"]["id"] == prompt_id
    assert "updated_at" in data["data"]
    assert "content" not in data["data"]
    assert "name" not in data["data"]


async def test_str_replace_prompt_success_full_entity(client: AsyncClient) -> None:
    """Test str-replace with include_updated_entity=true."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "str-replace-test",
            "content": "Hello world",
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    response = await client.patch(
        f"/prompts/{prompt_id}/str-replace?include_updated_entity=true",
        json={"old_str": "world", "new_str": "universe"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["response_type"] == "full"
    assert data["match_type"] == "exact"
    assert data["line"] == 1
    assert data["data"]["content"] == "Hello universe"
    assert data["data"]["id"] == prompt_id


async def test_str_replace_prompt_multiline(client: AsyncClient) -> None:
    """Test str-replace on multiline prompt content."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "multiline-replace",
            "content": "line 1\nline 2 target\nline 3",
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    response = await client.patch(
        f"/prompts/{prompt_id}/str-replace?include_updated_entity=true",
        json={"old_str": "target", "new_str": "replaced"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["line"] == 2
    assert data["data"]["content"] == "line 1\nline 2 replaced\nline 3"


async def test_str_replace_prompt_multiline_old_str(client: AsyncClient) -> None:
    """Test str-replace with multiline old_str."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "multiline-old-str",
            "content": "line 1\nline 2\nline 3\nline 4",
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    response = await client.patch(
        f"/prompts/{prompt_id}/str-replace?include_updated_entity=true",
        json={"old_str": "line 2\nline 3", "new_str": "replaced"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["line"] == 2
    assert data["data"]["content"] == "line 1\nreplaced\nline 4"


async def test_str_replace_prompt_no_match(client: AsyncClient) -> None:
    """Test str-replace returns 400 when old_str not found."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "no-match-prompt",
            "content": "Hello world",
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    response = await client.patch(
        f"/prompts/{prompt_id}/str-replace",
        json={"old_str": "nonexistent", "new_str": "replaced"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "no_match"


async def test_str_replace_prompt_multiple_matches(client: AsyncClient) -> None:
    """Test str-replace returns 400 when multiple matches found."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "multiple-matches-prompt",
            "content": "foo bar foo baz foo",
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    response = await client.patch(
        f"/prompts/{prompt_id}/str-replace",
        json={"old_str": "foo", "new_str": "replaced"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "multiple_matches"
    assert len(response.json()["detail"]["matches"]) == 3


async def test_str_replace_prompt_deletion(client: AsyncClient) -> None:
    """Test str-replace with empty new_str performs deletion."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "deletion-test-prompt",
            "content": "Hello world",
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    response = await client.patch(
        f"/prompts/{prompt_id}/str-replace?include_updated_entity=true",
        json={"old_str": " world", "new_str": ""},
    )
    assert response.status_code == 200
    assert response.json()["data"]["content"] == "Hello"


async def test_str_replace_prompt_whitespace_normalized(client: AsyncClient) -> None:
    """Test str-replace with whitespace-normalized matching."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "whitespace-norm-prompt",
            "content": "line 1  \nline 2\nline 3",  # Trailing spaces on line 1
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    response = await client.patch(
        f"/prompts/{prompt_id}/str-replace?include_updated_entity=true",
        json={"old_str": "line 1\nline 2", "new_str": "replaced"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["match_type"] == "whitespace_normalized"
    assert "replaced" in data["data"]["content"]


async def test_str_replace_prompt_not_found(client: AsyncClient) -> None:
    """Test str-replace on non-existent prompt returns 404."""
    response = await client.patch(
        "/prompts/00000000-0000-0000-0000-000000000000/str-replace",
        json={"old_str": "test", "new_str": "replaced"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Prompt not found"


async def test_str_replace_prompt_null_content(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test str-replace on prompt with null content returns content_empty error."""
    # First create a prompt via API to ensure user exists
    response = await client.post(
        "/prompts/",
        json={"name": "temp-for-user-creation", "content": "temp"},
    )
    assert response.status_code == 201

    # Get the dev user
    result = await db_session.execute(
        select(User).where(User.external_auth_id == "dev|local-development-user"),
    )
    dev_user = result.scalar_one()

    # Create a prompt directly in DB with null content
    prompt = Prompt(
        user_id=dev_user.id,
        name="null-content-prompt",
        content=None,
    )
    db_session.add(prompt)
    await db_session.flush()

    response = await client.patch(
        f"/prompts/{prompt.id}/str-replace",
        json={"old_str": "test", "new_str": "replaced"},
    )
    assert response.status_code == 400

    data = response.json()["detail"]
    assert data["error"] == "content_empty"
    assert "no content" in data["message"].lower()
    assert "suggestion" in data


async def test_str_replace_prompt_updates_updated_at(client: AsyncClient) -> None:
    """Test that str-replace updates the updated_at timestamp."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "timestamp-test-prompt",
            "content": "Hello world",
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]
    original_updated_at = response.json()["updated_at"]

    await asyncio.sleep(0.01)

    response = await client.patch(
        f"/prompts/{prompt_id}/str-replace",
        json={"old_str": "world", "new_str": "universe"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["updated_at"] > original_updated_at


async def test_str_replace_prompt_no_op_does_not_update_timestamp(client: AsyncClient) -> None:
    """Test that str-replace with old_str == new_str does not update timestamp."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "no-op-timestamp-test-prompt",
            "content": "Hello world",
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]
    original_updated_at = response.json()["updated_at"]

    await asyncio.sleep(0.01)

    # Perform str-replace with identical old and new strings (no-op)
    response = await client.patch(
        f"/prompts/{prompt_id}/str-replace",
        json={"old_str": "world", "new_str": "world"},
    )
    assert response.status_code == 200

    # Timestamp should NOT have changed
    assert response.json()["data"]["updated_at"] == original_updated_at

    # Verify match info is still returned
    assert response.json()["match_type"] == "exact"
    assert "line" in response.json()


async def test_str_replace_prompt_works_on_archived(client: AsyncClient) -> None:
    """Test that str-replace works on archived prompts."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "archived-replace-prompt",
            "content": "Hello world",
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    await client.post(f"/prompts/{prompt_id}/archive")

    response = await client.patch(
        f"/prompts/{prompt_id}/str-replace?include_updated_entity=true",
        json={"old_str": "world", "new_str": "universe"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["content"] == "Hello universe"


async def test_str_replace_prompt_not_on_deleted(client: AsyncClient) -> None:
    """Test that str-replace does not work on soft-deleted prompts."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "deleted-replace-prompt",
            "content": "Hello world",
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    await client.delete(f"/prompts/{prompt_id}")

    response = await client.patch(
        f"/prompts/{prompt_id}/str-replace",
        json={"old_str": "world", "new_str": "universe"},
    )
    assert response.status_code == 404


async def test_str_replace_prompt_preserves_other_fields(client: AsyncClient) -> None:
    """Test that str-replace preserves other prompt fields."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "preserve-fields-prompt",
            "title": "My Title",
            "description": "My Description",
            "content": "Hello {{ name }}!",
            "arguments": [{"name": "name", "required": True}],
            "tags": ["tag1", "tag2"],
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    response = await client.patch(
        f"/prompts/{prompt_id}/str-replace?include_updated_entity=true",
        json={"old_str": "Hello", "new_str": "Hi"},
    )
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["name"] == "preserve-fields-prompt"
    assert data["title"] == "My Title"
    assert data["description"] == "My Description"
    assert data["content"] == "Hi {{ name }}!"
    assert data["arguments"] == [{"name": "name", "description": None, "required": True}]
    assert data["tags"] == ["tag1", "tag2"]


async def test_str_replace_prompt_jinja_valid_template(client: AsyncClient) -> None:
    """Test str-replace validates Jinja2 template after replacement."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "jinja-replace-valid",
            "content": "Hello {{ name }}!",
            "arguments": [{"name": "name", "required": True}],
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    # Replace with valid Jinja2
    response = await client.patch(
        f"/prompts/{prompt_id}/str-replace?include_updated_entity=true",
        json={"old_str": "Hello {{ name }}!", "new_str": "Hi {{ name }}, welcome!"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["content"] == "Hi {{ name }}, welcome!"


async def test_str_replace_prompt_jinja_invalid_syntax(client: AsyncClient) -> None:
    """Test str-replace returns 400 when resulting template has invalid Jinja2 syntax."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "jinja-replace-invalid-syntax",
            "content": "Hello {{ name }}!",
            "arguments": [{"name": "name", "required": True}],
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    # Replace with invalid Jinja2 syntax (unclosed bracket)
    response = await client.patch(
        f"/prompts/{prompt_id}/str-replace",
        json={"old_str": "Hello {{ name }}!", "new_str": "Hi {{ unclosed!"},
    )
    assert response.status_code == 400
    assert "Invalid Jinja2 syntax" in response.json()["detail"]


async def test_str_replace_prompt_jinja_undefined_variable(client: AsyncClient) -> None:
    """Test str-replace returns 400 when resulting template has undefined variable."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "jinja-replace-undefined",
            "content": "Hello {{ name }}!",
            "arguments": [{"name": "name", "required": True}],
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    # Replace with undefined variable
    response = await client.patch(
        f"/prompts/{prompt_id}/str-replace",
        json={"old_str": "{{ name }}", "new_str": "{{ unknown_var }}"},
    )
    assert response.status_code == 400
    assert "undefined variable" in response.json()["detail"].lower()


async def test_str_replace_prompt_jinja_unused_argument_after_replace(client: AsyncClient) -> None:
    """Test that removing variable usage causes unused argument error."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "jinja-replace-remove-var",
            "content": "Hello {{ name }}!",
            "arguments": [{"name": "name", "required": True}],
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    # Replace to remove variable usage entirely - this should fail because
    # the 'name' argument would become unused
    response = await client.patch(
        f"/prompts/{prompt_id}/str-replace",
        json={"old_str": "{{ name }}", "new_str": "World"},
    )
    assert response.status_code == 400
    assert "unused argument" in response.json()["detail"].lower()


async def test_str_replace_prompt_no_arguments_static_replacement(client: AsyncClient) -> None:
    """Test that removing variable in a prompt with no arguments succeeds."""
    # Create a prompt without arguments (static content)
    response = await client.post(
        "/prompts/",
        json={
            "name": "static-content-prompt",
            "content": "Hello World!",
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    # Replace static content - this should succeed
    response = await client.patch(
        f"/prompts/{prompt_id}/str-replace?include_updated_entity=true",
        json={"old_str": "World", "new_str": "Universe"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["content"] == "Hello Universe!"


# =============================================================================
# Str-Replace with Arguments Field (Atomic Updates)
# =============================================================================


async def test_str_replace_prompt_add_variable_with_argument(client: AsyncClient) -> None:
    """Test adding a new variable AND its argument atomically."""
    # Create prompt with one variable
    response = await client.post(
        "/prompts/",
        json={
            "name": "add-var-atomic",
            "content": "Hello {{ name }}!",
            "arguments": [{"name": "name", "required": True}],
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    # Add a new variable AND provide updated arguments list
    response = await client.patch(
        f"/prompts/{prompt_id}/str-replace?include_updated_entity=true",
        json={
            "old_str": "Hello {{ name }}!",
            "new_str": "Hello {{ greeting }}, {{ name }}!",
            "arguments": [
                {"name": "name", "required": True},
                {"name": "greeting", "required": True},
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["content"] == "Hello {{ greeting }}, {{ name }}!"
    assert len(data["arguments"]) == 2
    arg_names = {arg["name"] for arg in data["arguments"]}
    assert arg_names == {"name", "greeting"}


async def test_str_replace_prompt_remove_variable_with_argument(client: AsyncClient) -> None:
    """Test removing a variable AND its argument atomically."""
    # Create prompt with two variables
    response = await client.post(
        "/prompts/",
        json={
            "name": "remove-var-atomic",
            "content": "Hello {{ greeting }}, {{ name }}!",
            "arguments": [
                {"name": "greeting", "required": True},
                {"name": "name", "required": True},
            ],
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    # Remove {{ greeting }} from content AND from arguments (keep only name)
    response = await client.patch(
        f"/prompts/{prompt_id}/str-replace?include_updated_entity=true",
        json={
            "old_str": "{{ greeting }}, ",
            "new_str": "",
            "arguments": [{"name": "name", "required": True}],  # Only keep 'name'
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["content"] == "Hello {{ name }}!"
    assert len(data["arguments"]) == 1
    assert data["arguments"][0]["name"] == "name"


async def test_str_replace_prompt_remove_one_keep_others(client: AsyncClient) -> None:
    """Test removing one argument while keeping others - must provide all to keep."""
    # Create prompt with three variables
    response = await client.post(
        "/prompts/",
        json={
            "name": "remove-one-keep-others",
            "content": "{{ a }} {{ b }} {{ c }}",
            "arguments": [
                {"name": "a", "required": True},
                {"name": "b", "required": True},
                {"name": "c", "required": True},
            ],
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    # Remove {{ b }} from content, keep a and c in arguments
    response = await client.patch(
        f"/prompts/{prompt_id}/str-replace?include_updated_entity=true",
        json={
            "old_str": " {{ b }}",
            "new_str": "",
            "arguments": [
                {"name": "a", "required": True},
                {"name": "c", "required": True},
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["content"] == "{{ a }} {{ c }}"
    assert len(data["arguments"]) == 2
    arg_names = {arg["name"] for arg in data["arguments"]}
    assert arg_names == {"a", "c"}


async def test_str_replace_prompt_accidentally_omit_used_argument(client: AsyncClient) -> None:
    """Test that omitting an argument still used in content fails."""
    # Create prompt with two variables
    response = await client.post(
        "/prompts/",
        json={
            "name": "omit-used-arg",
            "content": "{{ a }} {{ b }}",
            "arguments": [
                {"name": "a", "required": True},
                {"name": "b", "required": True},
            ],
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    # Try to remove {{ a }} but accidentally provide empty arguments
    # This should fail because {{ b }} is still in content but not in new arguments
    response = await client.patch(
        f"/prompts/{prompt_id}/str-replace",
        json={
            "old_str": "{{ a }} ",
            "new_str": "",
            "arguments": [],  # Oops! Forgot to include 'b'
        },
    )
    assert response.status_code == 400
    assert "undefined variable" in response.json()["detail"].lower()


async def test_str_replace_prompt_replace_all_variables(client: AsyncClient) -> None:
    """Test replacing all variables with completely new ones."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "replace-all-vars",
            "content": "Hello {{ old_var }}!",
            "arguments": [{"name": "old_var", "required": True}],
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    # Replace with entirely new content and arguments
    response = await client.patch(
        f"/prompts/{prompt_id}/str-replace?include_updated_entity=true",
        json={
            "old_str": "Hello {{ old_var }}!",
            "new_str": "{{ greeting }} {{ name }}, welcome to {{ place }}!",
            "arguments": [
                {"name": "greeting", "required": True},
                {"name": "name", "required": True},
                {"name": "place", "required": False},
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["content"] == "{{ greeting }} {{ name }}, welcome to {{ place }}!"
    assert len(data["arguments"]) == 3


async def test_str_replace_prompt_empty_arguments_static_content(client: AsyncClient) -> None:
    """Test providing empty arguments with static content (no variables)."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "empty-args-static",
            "content": "Hello {{ name }}!",
            "arguments": [{"name": "name", "required": True}],
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    # Replace with static content and empty arguments
    response = await client.patch(
        f"/prompts/{prompt_id}/str-replace?include_updated_entity=true",
        json={
            "old_str": "{{ name }}",
            "new_str": "World",
            "arguments": [],  # No arguments needed for static content
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["content"] == "Hello World!"
    assert data["arguments"] == []


async def test_str_replace_prompt_duplicate_argument_names(client: AsyncClient) -> None:
    """Test that duplicate argument names in request returns 400."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "duplicate-args",
            "content": "Hello {{ name }}!",
            "arguments": [{"name": "name", "required": True}],
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    # Try to provide arguments with duplicate names
    response = await client.patch(
        f"/prompts/{prompt_id}/str-replace",
        json={
            "old_str": "Hello",
            "new_str": "Hi",
            "arguments": [
                {"name": "name", "required": True},
                {"name": "name", "required": False},  # Duplicate!
            ],
        },
    )
    assert response.status_code == 422  # Pydantic validation error


async def test_str_replace_prompt_no_match_arguments_not_updated(client: AsyncClient) -> None:
    """Test that if str_replace fails (no match), arguments are NOT updated."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "no-match-no-update",
            "content": "Hello {{ name }}!",
            "arguments": [{"name": "name", "required": True}],
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    # Try str_replace with non-existent old_str
    response = await client.patch(
        f"/prompts/{prompt_id}/str-replace",
        json={
            "old_str": "NONEXISTENT",
            "new_str": "new content",
            "arguments": [{"name": "new_arg", "required": True}],
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "no_match"

    # Verify arguments were NOT changed
    response = await client.get(f"/prompts/{prompt_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["content"] == "Hello {{ name }}!"  # Content unchanged
    assert len(data["arguments"]) == 1
    assert data["arguments"][0]["name"] == "name"  # Original argument


async def test_str_replace_prompt_validation_fails_content_not_updated(client: AsyncClient) -> None:
    """Test that if validation fails, neither content nor arguments are updated."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "validation-fail-no-update",
            "content": "Hello {{ name }}!",
            "arguments": [{"name": "name", "required": True}],
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    # Try to add new variable but DON'T include it in arguments (validation will fail)
    response = await client.patch(
        f"/prompts/{prompt_id}/str-replace",
        json={
            "old_str": "Hello {{ name }}!",
            "new_str": "Hello {{ name }} and {{ friend }}!",  # new variable
            "arguments": [{"name": "name", "required": True}],  # Missing 'friend'!
        },
    )
    assert response.status_code == 400
    assert "undefined variable" in response.json()["detail"].lower()

    # Verify NEITHER content NOR arguments were changed
    response = await client.get(f"/prompts/{prompt_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["content"] == "Hello {{ name }}!"  # Original content
    assert len(data["arguments"]) == 1
    assert data["arguments"][0]["name"] == "name"


async def test_str_replace_prompt_arguments_preserved_when_omitted(client: AsyncClient) -> None:
    """Test that existing arguments are preserved when arguments field is omitted."""
    response = await client.post(
        "/prompts/",
        json={
            "name": "preserve-args",
            "content": "Hello {{ name }}!",
            "arguments": [
                {"name": "name", "required": True, "description": "The name"},
            ],
        },
    )
    assert response.status_code == 201
    prompt_id = response.json()["id"]

    # Edit content without providing arguments field
    response = await client.patch(
        f"/prompts/{prompt_id}/str-replace?include_updated_entity=true",
        json={
            "old_str": "Hello",
            "new_str": "Hi",
            # No arguments field - should preserve existing
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["content"] == "Hi {{ name }}!"
    assert len(data["arguments"]) == 1
    assert data["arguments"][0]["name"] == "name"
    assert data["arguments"][0]["description"] == "The name"  # Preserved!


# =============================================================================
# Cross-User Isolation (IDOR) Tests
# =============================================================================


async def test_user_cannot_str_replace_other_users_prompt(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test that a user cannot str-replace another user's prompt (returns 404)."""
    # Create a prompt as the dev user with content
    response = await client.post(
        "/prompts/",
        json={
            "name": "user1-str-replace-test-prompt",
            "content": "Original content that should not be modified",
        },
    )
    assert response.status_code == 201
    user1_prompt_id = response.json()["id"]

    async with create_user2_client(
        db_session, 'auth0|user2-prompt-str-replace-test', 'user2-prompt-str-replace@example.com',
    ) as user2_client:
        # Try to str-replace user1's prompt - should get 404
        response = await user2_client.patch(
            f"/prompts/{user1_prompt_id}/str-replace",
            json={"old_str": "Original", "new_str": "HACKED"},
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Prompt not found"

    # Verify the prompt content was not modified via database query
    result = await db_session.execute(
        select(Prompt).where(Prompt.id == user1_prompt_id),
    )
    prompt = result.scalar_one()
    assert prompt.content == "Original content that should not be modified"


async def test_user_cannot_see_other_users_prompts_in_list(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test that a user's prompt list only shows their own prompts."""
    response = await client.post(
        "/prompts/", json={"name": "user1-private-prompt", "content": "private"},
    )
    assert response.status_code == 201
    user1_prompt_id = response.json()["id"]

    async with create_user2_client(
        db_session, 'auth0|user2-prompt-list-test', 'user2-prompt-list@example.com',
    ) as user2_client:
        response = await user2_client.get("/prompts/")
        assert response.status_code == 200
        prompt_ids = [p["id"] for p in response.json()["items"]]
        assert user1_prompt_id not in prompt_ids


async def test_user_cannot_get_other_users_prompt_by_id(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test that a user cannot access another user's prompt by ID (returns 404)."""
    response = await client.post(
        "/prompts/", json={"name": "user1-get-test-prompt", "content": "content"},
    )
    assert response.status_code == 201
    user1_prompt_id = response.json()["id"]

    async with create_user2_client(
        db_session, 'auth0|user2-prompt-get-test', 'user2-prompt-get@example.com',
    ) as user2_client:
        response = await user2_client.get(f"/prompts/{user1_prompt_id}")
        assert response.status_code == 404
        assert response.json()["detail"] == "Prompt not found"


async def test_user_cannot_update_other_users_prompt(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test that a user cannot update another user's prompt (returns 404)."""
    response = await client.post(
        "/prompts/", json={"name": "user1-update-test-prompt", "content": "original"},
    )
    assert response.status_code == 201
    user1_prompt_id = response.json()["id"]

    async with create_user2_client(
        db_session, 'auth0|user2-prompt-update-test', 'user2-prompt-update@example.com',
    ) as user2_client:
        response = await user2_client.patch(
            f"/prompts/{user1_prompt_id}",
            json={"title": "Hacked Title"},
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Prompt not found"

    result = await db_session.execute(
        select(Prompt).where(Prompt.id == user1_prompt_id),
    )
    prompt = result.scalar_one()
    assert prompt.title is None


async def test_user_cannot_delete_other_users_prompt(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test that a user cannot delete another user's prompt (returns 404)."""
    response = await client.post(
        "/prompts/", json={"name": "user1-delete-test-prompt", "content": "content"},
    )
    assert response.status_code == 201
    user1_prompt_id = response.json()["id"]

    async with create_user2_client(
        db_session, 'auth0|user2-prompt-delete-test', 'user2-prompt-delete@example.com',
    ) as user2_client:
        response = await user2_client.delete(f"/prompts/{user1_prompt_id}")
        assert response.status_code == 404

    result = await db_session.execute(
        select(Prompt).where(Prompt.id == user1_prompt_id),
    )
    prompt = result.scalar_one()
    assert prompt.deleted_at is None


# =============================================================================
# Name-Based Endpoint Tests
# =============================================================================


async def test__update_by_name__success(client: AsyncClient) -> None:
    """Test updating a prompt by name."""
    create_response = await client.post(
        "/prompts/",
        json={"name": "name-update-test", "content": "Original content"},
    )
    assert create_response.status_code == 201

    response = await client.patch(
        "/prompts/name/name-update-test",
        json={"title": "Updated Title", "tags": ["updated"]},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["title"] == "Updated Title"
    assert data["tags"] == ["updated"]
    # Name and content should remain unchanged
    assert data["name"] == "name-update-test"
    assert data["content"] == "Original content"


async def test__update_by_name__not_found(client: AsyncClient) -> None:
    """Test updating a non-existent prompt by name returns 404."""
    response = await client.patch(
        "/prompts/name/nonexistent-prompt-name",
        json={"title": "Won't Work"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Prompt not found"


async def test__update_by_name__name_conflict(client: AsyncClient) -> None:
    """Test that renaming to an existing name returns 409."""
    # Create two prompts
    await client.post("/prompts/", json={"name": "existing-target-name", "content": "C1"})
    await client.post("/prompts/", json={"name": "source-name", "content": "C2"})

    # Try to rename source-name to existing-target-name
    response = await client.patch(
        "/prompts/name/source-name",
        json={"name": "existing-target-name"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["error_code"] == "NAME_CONFLICT"


async def test__update_by_name__archived_returns_404(client: AsyncClient) -> None:
    """Test that name-based update excludes archived prompts."""
    # Create and archive a prompt
    create_response = await client.post(
        "/prompts/",
        json={"name": "archived-update-test", "content": "Original content"},
    )
    prompt_id = create_response.json()["id"]
    await client.post(f"/prompts/{prompt_id}/archive")

    # Try to update by name - should get 404 since name-based lookup excludes archived
    response = await client.patch(
        "/prompts/name/archived-update-test",
        json={"title": "Won't Work"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Prompt not found"


async def test__str_replace_by_name__success(client: AsyncClient) -> None:
    """Test successful str-replace by name."""
    await client.post(
        "/prompts/",
        json={"name": "str-replace-name-test", "content": "Hello world"},
    )

    response = await client.patch(
        "/prompts/name/str-replace-name-test/str-replace?include_updated_entity=true",
        json={"old_str": "world", "new_str": "universe"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["response_type"] == "full"
    assert data["match_type"] == "exact"
    assert data["line"] == 1
    assert data["data"]["content"] == "Hello universe"


async def test__str_replace_by_name__minimal_response(client: AsyncClient) -> None:
    """Test str-replace by name returns minimal response by default."""
    response = await client.post(
        "/prompts/",
        json={"name": "str-replace-name-minimal", "content": "Hello world"},
    )
    prompt_id = response.json()["id"]

    response = await client.patch(
        "/prompts/name/str-replace-name-minimal/str-replace",
        json={"old_str": "world", "new_str": "universe"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["response_type"] == "minimal"
    assert data["data"]["id"] == prompt_id
    assert "updated_at" in data["data"]
    # Minimal response should not include content
    assert "content" not in data["data"]


async def test__str_replace_by_name__not_found(client: AsyncClient) -> None:
    """Test str-replace on non-existent prompt name returns 404."""
    response = await client.patch(
        "/prompts/name/nonexistent-prompt-for-str-replace/str-replace",
        json={"old_str": "any", "new_str": "text"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Prompt not found"


async def test__str_replace_by_name__no_match(client: AsyncClient) -> None:
    """Test str-replace by name returns 400 when old_str not found."""
    await client.post(
        "/prompts/",
        json={"name": "str-replace-no-match-test", "content": "Hello world"},
    )

    response = await client.patch(
        "/prompts/name/str-replace-no-match-test/str-replace",
        json={"old_str": "nonexistent text", "new_str": "replacement"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "no_match"


async def test__str_replace_by_name__multiple_matches(client: AsyncClient) -> None:
    """Test str-replace by name returns 400 with match locations when multiple matches."""
    await client.post(
        "/prompts/",
        json={"name": "str-replace-multi-match", "content": "Hello world, hello again"},
    )

    response = await client.patch(
        "/prompts/name/str-replace-multi-match/str-replace",
        json={"old_str": "ello", "new_str": "i"},  # Matches twice
    )
    assert response.status_code == 400

    data = response.json()["detail"]
    assert data["error"] == "multiple_matches"
    assert len(data["matches"]) == 2


async def test__str_replace_by_name__archived_returns_404(client: AsyncClient) -> None:
    """Test that name-based str-replace excludes archived prompts."""
    # Create and archive a prompt
    create_response = await client.post(
        "/prompts/",
        json={"name": "archived-str-replace-test", "content": "Hello world"},
    )
    prompt_id = create_response.json()["id"]
    await client.post(f"/prompts/{prompt_id}/archive")

    # Try to str-replace by name - should get 404 since name-based lookup excludes archived
    response = await client.patch(
        "/prompts/name/archived-str-replace-test/str-replace",
        json={"old_str": "world", "new_str": "universe"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Prompt not found"


async def test__str_replace_by_name__with_arguments_update(client: AsyncClient) -> None:
    """Test str-replace by name with atomic arguments update."""
    await client.post(
        "/prompts/",
        json={
            "name": "str-replace-args-test",
            "content": "Hello world",
            "arguments": [],
        },
    )

    # Add a variable and its argument atomically
    response = await client.patch(
        "/prompts/name/str-replace-args-test/str-replace?include_updated_entity=true",
        json={
            "old_str": "Hello world",
            "new_str": "Hello {{ name }}",
            "arguments": [{"name": "name", "description": "User's name", "required": True}],
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["data"]["content"] == "Hello {{ name }}"
    assert data["data"]["arguments"] == [
        {"name": "name", "description": "User's name", "required": True},
    ]


async def test__str_replace_by_name__changed_fields_records_content_only(
    client: AsyncClient,
) -> None:
    """Pure content edit (no arguments in payload) records changed_fields=['content']."""
    create = await client.post("/prompts/", json={
        "name": "kan148-changed-fields-content-only",
        "content": "hello world",
    })
    prompt_id = create.json()["id"]

    patch = await client.patch(
        "/prompts/name/kan148-changed-fields-content-only/str-replace",
        json={"old_str": "hello", "new_str": "hi"},
    )
    assert patch.status_code == 200

    hist = await client.get(f"/history/prompt/{prompt_id}")
    updates = [r for r in hist.json()["items"] if r["action"] == "update"]
    assert len(updates) == 1
    assert updates[0]["changed_fields"] == ["content"]


async def test__str_replace_by_name__changed_fields_records_content_and_arguments(
    client: AsyncClient,
) -> None:
    """Atomic content + arguments edit records changed_fields=['content', 'arguments']."""
    create = await client.post("/prompts/", json={
        "name": "kan148-changed-fields-both",
        "content": "hello world",
        "arguments": [],
    })
    prompt_id = create.json()["id"]

    patch = await client.patch(
        "/prompts/name/kan148-changed-fields-both/str-replace",
        json={
            "old_str": "world",
            "new_str": "{{ name }}",
            "arguments": [{"name": "name", "description": "user", "required": True}],
        },
    )
    assert patch.status_code == 200

    hist = await client.get(f"/history/prompt/{prompt_id}")
    updates = [r for r in hist.json()["items"] if r["action"] == "update"]
    assert len(updates) == 1
    assert updates[0]["changed_fields"] == ["content", "arguments"]


async def test__str_replace_by_name__changed_fields_records_arguments_only_when_content_unchanged(
    client: AsyncClient,
) -> None:
    """
    Content unchanged + arguments actually different → changed_fields == ['arguments'].

    Edge case: a str-replace where `old_str == new_str` (or otherwise resolves to identical
    content) AND the supplied `arguments` differ structurally from the existing arguments
    bypasses the no-op early return and records a history row with only 'arguments' as the
    changed field. (See the companion test that confirms identical arguments DO trigger
    the no-op return.)
    """
    create = await client.post("/prompts/", json={
        "name": "kan148-changed-fields-args-only",
        "content": "hello {{ name }}",
        "arguments": [{"name": "name", "required": True}],
    })
    prompt_id = create.json()["id"]

    # Replace a substring with the same value so content is unchanged.
    patch = await client.patch(
        "/prompts/name/kan148-changed-fields-args-only/str-replace",
        json={
            "old_str": "hello",
            "new_str": "hello",
            "arguments": [{"name": "name", "description": "new desc", "required": True}],
        },
    )
    assert patch.status_code == 200

    hist = await client.get(f"/history/prompt/{prompt_id}")
    updates = [r for r in hist.json()["items"] if r["action"] == "update"]
    assert len(updates) == 1
    assert updates[0]["changed_fields"] == ["arguments"]


async def test__str_replace_by_id__changed_fields_records_content_and_arguments(
    client: AsyncClient,
) -> None:
    """
    The id-based prompt str-replace handler shares `_perform_str_replace`
    with the by-name handler. The other `changed_fields` tests exercise the
    by-name path; this one pins that the by-id path doesn't diverge.
    """
    create = await client.post("/prompts/", json={
        "name": "kan148-by-id-changed-fields",
        "content": "hello world",
        "arguments": [],
    })
    prompt_id = create.json()["id"]

    patch = await client.patch(
        f"/prompts/{prompt_id}/str-replace",
        json={
            "old_str": "world",
            "new_str": "{{ name }}",
            "arguments": [{"name": "name", "description": "user", "required": True}],
        },
    )
    assert patch.status_code == 200

    hist = await client.get(f"/history/prompt/{prompt_id}")
    updates = [r for r in hist.json()["items"] if r["action"] == "update"]
    assert len(updates) == 1
    assert updates[0]["changed_fields"] == ["content", "arguments"]


async def test__str_replace_by_name__no_op_when_content_unchanged_and_arguments_identical(
    client: AsyncClient,
) -> None:
    """
    True no-op: content unchanged AND arguments identical to existing → no history row,
    no updated_at bump.

    Without the structural equality check on arguments, sending the same arguments list
    bypasses the no-op early-return and writes a ghost history row + bumps updated_at,
    even though nothing actually changed. This test pins the corrected behavior.
    """
    create = await client.post("/prompts/", json={
        "name": "kan148-no-op-same-args",
        "content": "hello world",
        "arguments": [],
    })
    prompt_id = create.json()["id"]
    original_updated_at = create.json()["updated_at"]

    # Same arguments list (empty), str-replace that resolves to identical content.
    await asyncio.sleep(0.01)  # ensure any new write would have a distinguishable timestamp
    patch = await client.patch(
        "/prompts/name/kan148-no-op-same-args/str-replace",
        json={
            "old_str": "world",
            "new_str": "world",
            "arguments": [],
        },
    )
    assert patch.status_code == 200
    assert patch.json()["data"]["updated_at"] == original_updated_at

    hist = await client.get(f"/history/prompt/{prompt_id}")
    updates = [r for r in hist.json()["items"] if r["action"] == "update"]
    assert updates == [], (
        f"Expected no UPDATE history rows (true no-op), got {len(updates)}: "
        f"{[r['changed_fields'] for r in updates]}"
    )


async def test__str_replace_by_name__template_validation(client: AsyncClient) -> None:
    """Test that str-replace by name validates resulting template."""
    await client.post(
        "/prompts/",
        json={"name": "str-replace-validate-test", "content": "Hello world"},
    )

    # Try to add undefined variable
    response = await client.patch(
        "/prompts/name/str-replace-validate-test/str-replace",
        json={
            "old_str": "Hello world",
            "new_str": "Hello {{ undefined_var }}",
        },
    )
    assert response.status_code == 400
    assert "undefined" in response.json()["detail"].lower()


# =============================================================================
# Embedded Relationships
# =============================================================================


async def test__get_prompt__no_relationships_returns_empty_list(client: AsyncClient) -> None:
    """GET /prompts/{id} returns empty relationships list when none exist."""
    create_resp = await client.post(
        "/prompts/",
        json={"name": "no-rels-prompt", "content": "test", "title": "No Rels"},
    )
    prompt_id = create_resp.json()["id"]

    response = await client.get(f"/prompts/{prompt_id}")
    assert response.status_code == 200
    assert response.json()["relationships"] == []


async def test__get_prompt__with_relationships_returns_enriched(client: AsyncClient) -> None:
    """GET /prompts/{id} returns enriched relationships when they exist."""
    prompt_resp = await client.post(
        "/prompts/",
        json={"name": "rel-test-prompt", "content": "test", "title": "Source Prompt"},
    )
    prompt_id = prompt_resp.json()["id"]

    note_resp = await client.post("/notes/", json={"title": "Linked Note"})
    note_id = note_resp.json()["id"]

    await client.post("/relationships/", json={
        "source_type": "prompt",
        "source_id": prompt_id,
        "target_type": "note",
        "target_id": note_id,
        "relationship_type": "related",
    })

    response = await client.get(f"/prompts/{prompt_id}")
    assert response.status_code == 200

    rels = response.json()["relationships"]
    assert len(rels) == 1
    # Canonical ordering may swap source/target; verify both titles present
    titles = {rels[0]["source_title"], rels[0]["target_title"]}
    assert "Linked Note" in titles
    assert "Source Prompt" in titles


async def test__get_prompt_by_name__with_relationships_returns_enriched(client: AsyncClient) -> None:
    """GET /prompts/name/{name} returns enriched relationships."""
    prompt_resp = await client.post(
        "/prompts/",
        json={"name": "named-rel-prompt", "content": "test", "title": "Named Prompt"},
    )
    prompt_id = prompt_resp.json()["id"]

    note_resp = await client.post("/notes/", json={"title": "Linked Note 2"})
    note_id = note_resp.json()["id"]

    await client.post("/relationships/", json={
        "source_type": "prompt",
        "source_id": prompt_id,
        "target_type": "note",
        "target_id": note_id,
        "relationship_type": "related",
    })

    response = await client.get("/prompts/name/named-rel-prompt")
    assert response.status_code == 200

    rels = response.json()["relationships"]
    assert len(rels) == 1
    titles = {rels[0]["source_title"], rels[0]["target_title"]}
    assert "Linked Note 2" in titles


async def test__list_prompts__no_relationships_field(client: AsyncClient) -> None:
    """GET /prompts/ list items should NOT include relationships field."""
    await client.post(
        "/prompts/",
        json={"name": "list-rel-prompt", "content": "test", "title": "List Item"},
    )

    response = await client.get("/prompts/")
    assert response.status_code == 200

    items = response.json()["items"]
    assert len(items) >= 1
    assert "relationships" not in items[0]


# =============================================================================
# Tier Limits Quota Enforcement Tests (API-level)
# =============================================================================


async def test__create_prompt__quota_exceeded__returns_402(
    client: AsyncClient, low_limits: TierLimits,
) -> None:
    """Test that exceeding max_prompts returns 402 with QUOTA_EXCEEDED error code."""
    for i in range(low_limits.max_prompts):
        r = await client.post(
            "/prompts/", json={"name": f"quota-{i}", "content": f"content {i}"},
        )
        assert r.status_code == 201
    r = await client.post(
        "/prompts/", json={"name": "quota-over", "content": "over"},
    )
    assert r.status_code == 402
    body = r.json()
    assert body["error_code"] == "QUOTA_EXCEEDED"
