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
    """Test updating tab order with new section format."""
    response = await client.patch(
        "/settings/",
        json={
            "tab_order": {
                "sections": {
                    "shared": ["trash", "all", "archived"],
                    "bookmarks": ["all-bookmarks"],
                    "notes": ["all-notes"],
                },
                "section_order": ["shared", "bookmarks", "notes"],
            },
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["tab_order"]["sections"]["shared"] == ["trash", "all", "archived"]


async def test_update_settings_preserves_unset_fields(client: AsyncClient) -> None:
    """Test that updating settings only changes provided fields."""
    # First set tab_order
    await client.patch(
        "/settings/",
        json={
            "tab_order": {
                "sections": {
                    "shared": ["all", "archived", "trash"],
                    "bookmarks": ["all-bookmarks"],
                    "notes": ["all-notes"],
                },
                "section_order": ["shared", "bookmarks", "notes"],
            },
        },
    )

    # Update with empty body
    response = await client.patch("/settings/", json={})
    assert response.status_code == 200

    data = response.json()
    assert data["tab_order"]["sections"]["shared"] == ["all", "archived", "trash"]


async def test_get_tab_order_default(client: AsyncClient) -> None:
    """Test getting computed tab order returns defaults when no custom order."""
    response = await client.get("/settings/tab-order")
    assert response.status_code == 200

    data = response.json()

    # Check we have 3 sections
    assert len(data["sections"]) == 3
    assert data["section_order"] == ["shared", "bookmarks", "notes"]

    # Find sections by name
    sections_by_name = {s["name"]: s for s in data["sections"]}

    # Check shared section
    shared = sections_by_name["shared"]
    assert shared["label"] == "Shared"
    assert shared["collapsible"] is False
    shared_keys = [item["key"] for item in shared["items"]]
    assert "all" in shared_keys
    assert "archived" in shared_keys
    assert "trash" in shared_keys

    # Check bookmarks section
    bookmarks = sections_by_name["bookmarks"]
    assert bookmarks["label"] == "Bookmarks"
    assert bookmarks["collapsible"] is True
    bookmark_keys = [item["key"] for item in bookmarks["items"]]
    assert "all-bookmarks" in bookmark_keys

    # Check notes section
    notes = sections_by_name["notes"]
    assert notes["label"] == "Notes"
    assert notes["collapsible"] is True
    note_keys = [item["key"] for item in notes["items"]]
    assert "all-notes" in note_keys


async def test_get_tab_order_with_bookmark_only_list(client: AsyncClient) -> None:
    """Test getting tab order includes bookmark-only list in bookmarks section."""
    # Create a bookmark-only list
    create_response = await client.post(
        "/lists/",
        json={
            "name": "Work Items",
            "content_types": ["bookmark"],
            "filter_expression": {"groups": [{"tags": ["work"]}], "group_operator": "OR"},
        },
    )
    list_id = create_response.json()["id"]

    response = await client.get("/settings/tab-order")
    assert response.status_code == 200

    data = response.json()
    sections_by_name = {s["name"]: s for s in data["sections"]}

    # List should be in bookmarks section (prepended before all-bookmarks)
    bookmarks = sections_by_name["bookmarks"]
    assert bookmarks["items"][0]["key"] == f"list:{list_id}"
    assert bookmarks["items"][0]["label"] == "Work Items"
    assert bookmarks["items"][0]["type"] == "list"


async def test_get_tab_order_with_mixed_list(client: AsyncClient) -> None:
    """Test getting tab order includes mixed list in shared section."""
    # Create a mixed content type list (default is both)
    create_response = await client.post(
        "/lists/",
        json={
            "name": "Research",
            "content_types": ["bookmark", "note"],
            "filter_expression": {"groups": [{"tags": ["research"]}], "group_operator": "OR"},
        },
    )
    list_id = create_response.json()["id"]

    response = await client.get("/settings/tab-order")
    assert response.status_code == 200

    data = response.json()
    sections_by_name = {s["name"]: s for s in data["sections"]}

    # List should be in shared section
    shared = sections_by_name["shared"]
    list_keys = [item["key"] for item in shared["items"]]
    assert f"list:{list_id}" in list_keys


async def test_get_tab_order_respects_custom_order(client: AsyncClient) -> None:
    """Test that tab order respects user's custom ordering."""
    # Create a list first
    create_response = await client.post(
        "/lists/",
        json={
            "name": "My List",
            "content_types": ["bookmark"],
            "filter_expression": {"groups": [{"tags": ["test"]}], "group_operator": "OR"},
        },
    )
    list_id = create_response.json()["id"]

    # Set custom order with list in a different position
    await client.patch(
        "/settings/",
        json={
            "tab_order": {
                "sections": {
                    "shared": ["trash", "all", "archived"],
                    "bookmarks": ["all-bookmarks", f"list:{list_id}"],
                    "notes": ["all-notes"],
                },
                "section_order": ["bookmarks", "shared", "notes"],
            },
        },
    )

    response = await client.get("/settings/tab-order")
    assert response.status_code == 200

    data = response.json()
    # Check section order is respected
    assert data["section_order"] == ["bookmarks", "shared", "notes"]

    # Check bookmarks section has list after all-bookmarks
    sections_by_name = {s["name"]: s for s in data["sections"]}
    bookmarks = sections_by_name["bookmarks"]
    assert bookmarks["items"][0]["key"] == "all-bookmarks"
    assert bookmarks["items"][1]["key"] == f"list:{list_id}"


async def test_get_tab_order_filters_deleted_lists(client: AsyncClient) -> None:
    """Test that tab order filters out deleted list references."""
    # Create and delete a list
    create_response = await client.post(
        "/lists/",
        json={
            "name": "To Delete",
            "content_types": ["bookmark"],
            "filter_expression": {"groups": [{"tags": ["delete"]}], "group_operator": "OR"},
        },
    )
    list_id = create_response.json()["id"]

    # Delete the list
    await client.delete(f"/lists/{list_id}")

    # Get tab order - deleted list should be filtered out
    response = await client.get("/settings/tab-order")
    assert response.status_code == 200

    data = response.json()
    # Check no section contains the deleted list
    for section in data["sections"]:
        keys = [item["key"] for item in section["items"]]
        assert f"list:{list_id}" not in keys


async def test_get_tab_order_appends_orphaned_lists(client: AsyncClient) -> None:
    """Test that lists not in tab_order are appended to the appropriate section."""
    # Create a list - it will be added to tab_order
    create_response = await client.post(
        "/lists/",
        json={
            "name": "New List",
            "content_types": ["bookmark"],
            "filter_expression": {"groups": [{"tags": ["new"]}], "group_operator": "OR"},
        },
    )
    list_id = create_response.json()["id"]

    # Override tab_order to NOT include the list (simulating an edge case)
    await client.patch(
        "/settings/",
        json={
            "tab_order": {
                "sections": {
                    "shared": ["all", "archived", "trash"],
                    "bookmarks": ["all-bookmarks"],
                    "notes": ["all-notes"],
                },
                "section_order": ["shared", "bookmarks", "notes"],
            },
        },
    )

    # Get tab order - the orphaned list should be appended to bookmarks section
    response = await client.get("/settings/tab-order")
    assert response.status_code == 200

    data = response.json()
    sections_by_name = {s["name"]: s for s in data["sections"]}

    # List should be appended to bookmarks section
    bookmarks = sections_by_name["bookmarks"]
    assert bookmarks["items"][-1]["key"] == f"list:{list_id}"
    assert bookmarks["items"][-1]["label"] == "New List"


async def test_get_raw_tab_order(client: AsyncClient) -> None:
    """Test getting raw tab order structure."""
    response = await client.get("/settings/tab-order/raw")
    assert response.status_code == 200

    data = response.json()
    assert "sections" in data
    assert "section_order" in data
    assert data["sections"]["shared"] == ["all", "archived", "trash"]
    assert data["sections"]["bookmarks"] == ["all-bookmarks"]
    assert data["sections"]["notes"] == ["all-notes"]


async def test_update_raw_tab_order(client: AsyncClient) -> None:
    """Test updating raw tab order structure via PUT."""
    response = await client.put(
        "/settings/tab-order",
        json={
            "sections": {
                "shared": ["archived", "all", "trash"],
                "bookmarks": ["all-bookmarks"],
                "notes": ["all-notes"],
            },
            "section_order": ["notes", "shared", "bookmarks"],
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["sections"]["shared"] == ["archived", "all", "trash"]
    assert data["section_order"] == ["notes", "shared", "bookmarks"]

    # Verify it persisted
    get_response = await client.get("/settings/tab-order/raw")
    assert get_response.status_code == 200
    get_data = get_response.json()
    assert get_data["section_order"] == ["notes", "shared", "bookmarks"]
