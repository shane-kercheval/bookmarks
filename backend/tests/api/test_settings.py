"""
Tests for user settings API endpoints.

Tests cover settings retrieval, update, and tab order computation.
"""
from httpx import AsyncClient


async def test_get_settings_creates_default(client: AsyncClient) -> None:
    """Test getting settings creates default when none exist."""
    response = await client.get("/settings/")
    assert response.status_code == 200

    data = response.json()
    assert data["tab_order"] is None  # Default is null
    assert "updated_at" in data


async def test_update_settings_tab_order(client: AsyncClient) -> None:
    """Test updating tab order."""
    response = await client.patch(
        "/settings/",
        json={"tab_order": ["trash", "all", "archived"]},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["tab_order"] == ["trash", "all", "archived"]


async def test_update_settings_preserves_unset_fields(client: AsyncClient) -> None:
    """Test that updating settings only changes provided fields."""
    # First set tab_order
    await client.patch(
        "/settings/",
        json={"tab_order": ["all", "archived", "trash"]},
    )

    # Update with empty body
    response = await client.patch("/settings/", json={})
    assert response.status_code == 200

    data = response.json()
    assert data["tab_order"] == ["all", "archived", "trash"]


async def test_get_tab_order_default(client: AsyncClient) -> None:
    """Test getting computed tab order returns defaults when no custom order."""
    response = await client.get("/settings/tab-order")
    assert response.status_code == 200

    data = response.json()
    assert len(data["items"]) == 3

    # Check default order
    assert data["items"][0]["key"] == "all"
    assert data["items"][0]["label"] == "All Bookmarks"
    assert data["items"][0]["type"] == "builtin"

    assert data["items"][1]["key"] == "archived"
    assert data["items"][1]["label"] == "Archived"

    assert data["items"][2]["key"] == "trash"
    assert data["items"][2]["label"] == "Trash"


async def test_get_tab_order_with_lists(client: AsyncClient) -> None:
    """Test getting tab order includes custom lists."""
    # Create a list
    create_response = await client.post(
        "/lists/",
        json={
            "name": "Work Items",
            "filter_expression": {"groups": [{"tags": ["work"]}], "group_operator": "OR"},
        },
    )
    list_id = create_response.json()["id"]

    response = await client.get("/settings/tab-order")
    assert response.status_code == 200

    data = response.json()
    # List should be first (prepended)
    assert data["items"][0]["key"] == f"list:{list_id}"
    assert data["items"][0]["label"] == "Work Items"
    assert data["items"][0]["type"] == "list"


async def test_get_tab_order_respects_custom_order(client: AsyncClient) -> None:
    """Test that tab order respects user's custom ordering."""
    # Create a list first
    create_response = await client.post(
        "/lists/",
        json={
            "name": "My List",
            "filter_expression": {"groups": [{"tags": ["test"]}], "group_operator": "OR"},
        },
    )
    list_id = create_response.json()["id"]

    # Set custom order with list in the middle
    await client.patch(
        "/settings/",
        json={"tab_order": ["all", f"list:{list_id}", "archived", "trash"]},
    )

    response = await client.get("/settings/tab-order")
    assert response.status_code == 200

    data = response.json()
    assert data["items"][0]["key"] == "all"
    assert data["items"][1]["key"] == f"list:{list_id}"
    assert data["items"][2]["key"] == "archived"
    assert data["items"][3]["key"] == "trash"


async def test_get_tab_order_filters_deleted_lists(client: AsyncClient) -> None:
    """Test that tab order filters out deleted list references."""
    # Create and delete a list
    create_response = await client.post(
        "/lists/",
        json={
            "name": "To Delete",
            "filter_expression": {"groups": [{"tags": ["delete"]}], "group_operator": "OR"},
        },
    )
    list_id = create_response.json()["id"]

    # Manually set tab order with the list
    await client.patch(
        "/settings/",
        json={"tab_order": ["all", f"list:{list_id}", "archived", "trash"]},
    )

    # Delete the list
    await client.delete(f"/lists/{list_id}")

    # Get tab order - deleted list should be filtered out
    response = await client.get("/settings/tab-order")
    assert response.status_code == 200

    data = response.json()
    keys = [item["key"] for item in data["items"]]
    assert f"list:{list_id}" not in keys
    assert "all" in keys
    assert "archived" in keys
    assert "trash" in keys


async def test_get_tab_order_appends_new_lists(client: AsyncClient) -> None:
    """Test that lists not in tab_order are appended at the end."""
    # Set a custom tab order without lists
    await client.patch(
        "/settings/",
        json={"tab_order": ["all", "archived", "trash"]},
    )

    # Create a new list (this normally prepends, but we've overridden tab_order)
    # Due to create_list calling add_list_to_tab_order, the list will be prepended
    # So let's test the edge case where a list somehow isn't in tab_order
    # by directly manipulating settings after creation

    create_response = await client.post(
        "/lists/",
        json={
            "name": "New List",
            "filter_expression": {"groups": [{"tags": ["new"]}], "group_operator": "OR"},
        },
    )
    list_id = create_response.json()["id"]

    # Override tab_order to NOT include the list (simulating an edge case)
    await client.patch(
        "/settings/",
        json={"tab_order": ["all", "archived", "trash"]},
    )

    # Get tab order - the orphaned list should be appended
    response = await client.get("/settings/tab-order")
    assert response.status_code == 200

    data = response.json()
    # List should be at the end
    assert data["items"][-1]["key"] == f"list:{list_id}"
    assert data["items"][-1]["label"] == "New List"
