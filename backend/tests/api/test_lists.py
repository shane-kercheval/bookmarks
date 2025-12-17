"""
Tests for bookmark list API endpoints.

Tests cover list creation, retrieval, update, deletion, and user isolation.
"""
from httpx import AsyncClient


async def test_create_list(client: AsyncClient) -> None:
    """Test creating a new bookmark list."""
    response = await client.post(
        "/lists/",
        json={
            "name": "Work Tasks",
            "filter_expression": {
                "groups": [{"tags": ["work", "priority"]}],
                "group_operator": "OR",
            },
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "Work Tasks"
    assert data["filter_expression"]["groups"][0]["tags"] == ["work", "priority"]
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


async def test_create_list_normalizes_tags(client: AsyncClient) -> None:
    """Test that tags are normalized to lowercase."""
    response = await client.post(
        "/lists/",
        json={
            "name": "Mixed Case",
            "filter_expression": {
                "groups": [{"tags": ["WORK", "Priority"]}],
                "group_operator": "OR",
            },
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["filter_expression"]["groups"][0]["tags"] == ["work", "priority"]


async def test_create_list_validates_name(client: AsyncClient) -> None:
    """Test that list name is required and validated."""
    # Empty name
    response = await client.post(
        "/lists/",
        json={
            "name": "",
            "filter_expression": {
                "groups": [{"tags": ["tag"]}],
                "group_operator": "OR",
            },
        },
    )
    assert response.status_code == 422

    # Missing name
    response = await client.post(
        "/lists/",
        json={
            "filter_expression": {
                "groups": [{"tags": ["tag"]}],
                "group_operator": "OR",
            },
        },
    )
    assert response.status_code == 422


async def test_create_list_validates_filter_expression(client: AsyncClient) -> None:
    """Test that filter expression must have at least one group with tags."""
    # Empty groups
    response = await client.post(
        "/lists/",
        json={
            "name": "Invalid",
            "filter_expression": {
                "groups": [],
                "group_operator": "OR",
            },
        },
    )
    assert response.status_code == 422

    # Empty tags in group
    response = await client.post(
        "/lists/",
        json={
            "name": "Invalid",
            "filter_expression": {
                "groups": [{"tags": []}],
                "group_operator": "OR",
            },
        },
    )
    assert response.status_code == 422


async def test_create_list_validates_tag_format(client: AsyncClient) -> None:
    """Test that tags are validated for proper format."""
    # Invalid tag with special characters
    response = await client.post(
        "/lists/",
        json={
            "name": "Invalid Tags",
            "filter_expression": {
                "groups": [{"tags": ["invalid@tag"]}],
                "group_operator": "OR",
            },
        },
    )
    assert response.status_code == 422


async def test_get_lists_empty(client: AsyncClient) -> None:
    """Test getting lists when user has none."""
    response = await client.get("/lists/")
    assert response.status_code == 200
    assert response.json() == []


async def test_get_lists(client: AsyncClient) -> None:
    """Test getting all lists for a user."""
    # Create two lists
    await client.post(
        "/lists/",
        json={
            "name": "First",
            "filter_expression": {"groups": [{"tags": ["tag1"]}], "group_operator": "OR"},
        },
    )
    await client.post(
        "/lists/",
        json={
            "name": "Second",
            "filter_expression": {"groups": [{"tags": ["tag2"]}], "group_operator": "OR"},
        },
    )

    response = await client.get("/lists/")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 2
    # Should be ordered by created_at
    assert data[0]["name"] == "First"
    assert data[1]["name"] == "Second"


async def test_get_list_by_id(client: AsyncClient) -> None:
    """Test getting a specific list by ID."""
    # Create a list
    create_response = await client.post(
        "/lists/",
        json={
            "name": "Target",
            "filter_expression": {"groups": [{"tags": ["target"]}], "group_operator": "OR"},
        },
    )
    list_id = create_response.json()["id"]

    response = await client.get(f"/lists/{list_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == list_id
    assert data["name"] == "Target"


async def test_get_list_not_found(client: AsyncClient) -> None:
    """Test getting a non-existent list returns 404."""
    response = await client.get("/lists/99999")
    assert response.status_code == 404


async def test_update_list_name(client: AsyncClient) -> None:
    """Test updating a list name."""
    # Create a list
    create_response = await client.post(
        "/lists/",
        json={
            "name": "Original",
            "filter_expression": {"groups": [{"tags": ["tag"]}], "group_operator": "OR"},
        },
    )
    list_id = create_response.json()["id"]

    response = await client.patch(
        f"/lists/{list_id}",
        json={"name": "Updated"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "Updated"


async def test_update_list_filter_expression(client: AsyncClient) -> None:
    """Test updating a list filter expression."""
    # Create a list
    create_response = await client.post(
        "/lists/",
        json={
            "name": "Test",
            "filter_expression": {"groups": [{"tags": ["old"]}], "group_operator": "OR"},
        },
    )
    list_id = create_response.json()["id"]

    response = await client.patch(
        f"/lists/{list_id}",
        json={
            "filter_expression": {
                "groups": [{"tags": ["new1"]}, {"tags": ["new2"]}],
                "group_operator": "OR",
            },
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert len(data["filter_expression"]["groups"]) == 2


async def test_update_list_not_found(client: AsyncClient) -> None:
    """Test updating a non-existent list returns 404."""
    response = await client.patch(
        "/lists/99999",
        json={"name": "New Name"},
    )
    assert response.status_code == 404


async def test_delete_list(client: AsyncClient) -> None:
    """Test deleting a list."""
    # Create a list
    create_response = await client.post(
        "/lists/",
        json={
            "name": "To Delete",
            "filter_expression": {"groups": [{"tags": ["delete"]}], "group_operator": "OR"},
        },
    )
    list_id = create_response.json()["id"]

    response = await client.delete(f"/lists/{list_id}")
    assert response.status_code == 204

    # Verify deleted
    get_response = await client.get(f"/lists/{list_id}")
    assert get_response.status_code == 404


async def test_delete_list_not_found(client: AsyncClient) -> None:
    """Test deleting a non-existent list returns 404."""
    response = await client.delete("/lists/99999")
    assert response.status_code == 404


async def test_create_list_complex_filter(client: AsyncClient) -> None:
    """Test creating a list with a complex filter expression."""
    response = await client.post(
        "/lists/",
        json={
            "name": "Complex",
            "filter_expression": {
                "groups": [
                    {"tags": ["work", "high-priority"]},
                    {"tags": ["urgent"]},
                    {"tags": ["critical", "deadline"]},
                ],
                "group_operator": "OR",
            },
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert len(data["filter_expression"]["groups"]) == 3
