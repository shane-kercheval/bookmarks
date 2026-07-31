"""Tests for sidebar service layer functionality."""
import copy
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from models.content_filter import ContentFilter
from models.user import User
from models.user_settings import UserSettings
from schemas.sidebar import (
    SIDEBAR_VERSION,
    SidebarBuiltinItem,
    SidebarCollection,
    SidebarFilterItem,
    SidebarOrder,
)
from services.exceptions import (
    SidebarDuplicateItemError,
    SidebarFilterNotFoundError,
)
from core.tier_limits import Tier
from services.sidebar_service import (
    _ensure_sidebar_order_structure,
    _extract_builtin_keys_from_items,
    _extract_collection_ids_from_items,
    _extract_filter_ids_from_items,
    _remove_filter_from_items,
    _validate_sidebar_order,
    add_filter_to_sidebar,
    get_computed_sidebar,
    get_default_sidebar_order,
    remove_filter_from_sidebar,
    update_sidebar_order,
)


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(external_auth_id="test-sidebar-user-123", email="sidebar@example.com", tier=Tier.FREE.value)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_filter(db_session: AsyncSession, test_user: User) -> ContentFilter:
    """Create a test content filter."""
    content_filter = ContentFilter(
        user_id=test_user.id,
        name="Test List",
        content_types=["bookmark"],
        group_operator="OR",
    )
    db_session.add(content_filter)
    await db_session.flush()
    await db_session.refresh(content_filter)
    return content_filter


# =============================================================================
# get_default_sidebar_order Tests
# =============================================================================


def test__get_default_sidebar_order__returns_correct_structure() -> None:
    """Test that get_default_sidebar_order returns the correct default structure."""
    result = get_default_sidebar_order()

    assert result["version"] == SIDEBAR_VERSION
    assert len(result["items"]) == 4

    # Check builtin items
    assert result["items"][0] == {"type": "builtin", "key": "command-palette"}
    assert result["items"][1] == {"type": "builtin", "key": "all"}
    assert result["items"][2] == {"type": "builtin", "key": "archived"}
    assert result["items"][3] == {"type": "builtin", "key": "trash"}


# =============================================================================
# _ensure_sidebar_order_structure Tests
# =============================================================================


def test__ensure_sidebar_order_structure__returns_default_for_none() -> None:
    """Test that None input returns default structure."""
    result = _ensure_sidebar_order_structure(None)
    assert result == get_default_sidebar_order()


def test__ensure_sidebar_order_structure__does_not_mutate_input() -> None:
    """Test that the function does not mutate its input dict."""
    original = {"version": 1, "items": [{"type": "builtin", "key": "all"}]}
    original_copy = copy.deepcopy(original)

    _ensure_sidebar_order_structure(original)

    assert original == original_copy


def test__ensure_sidebar_order_structure__adds_missing_version() -> None:
    """Test that missing version is added."""
    result = _ensure_sidebar_order_structure({"items": []})
    assert result["version"] == SIDEBAR_VERSION


def test__ensure_sidebar_order_structure__adds_missing_items() -> None:
    """Test that missing items key is filled with defaults."""
    result = _ensure_sidebar_order_structure({"version": 1})
    assert "items" in result
    assert len(result["items"]) == 4  # Default builtins


# =============================================================================
# Helper extraction function tests
# =============================================================================


def test__extract_filter_ids_from_items__extracts_from_root() -> None:
    """Test extracting filter IDs from root items."""
    id1 = "550e8400-e29b-41d4-a716-446655440001"
    id2 = "550e8400-e29b-41d4-a716-446655440002"
    items = [
        {"type": "filter", "id": id1},
        {"type": "builtin", "key": "all"},
        {"type": "filter", "id": id2},
    ]
    result = _extract_filter_ids_from_items(items)
    assert result == {UUID(id1), UUID(id2)}


def test__extract_filter_ids_from_items__extracts_from_groups() -> None:
    """Test extracting filter IDs from groups."""
    id3 = "550e8400-e29b-41d4-a716-446655440003"
    id4 = "550e8400-e29b-41d4-a716-446655440004"
    id5 = "550e8400-e29b-41d4-a716-446655440005"
    items = [
        {
            "type": "collection",
            "id": "uuid-1",
            "name": "Group",
            "items": [
                {"type": "filter", "id": id3},
                {"type": "filter", "id": id4},
            ],
        },
        {"type": "filter", "id": id5},
    ]
    result = _extract_filter_ids_from_items(items)
    assert result == {UUID(id3), UUID(id4), UUID(id5)}


def test__extract_builtin_keys_from_items__extracts_all() -> None:
    """Test extracting builtin keys."""
    items = [
        {"type": "builtin", "key": "all"},
        {"type": "builtin", "key": "archived"},
        {"type": "collection", "items": [{"type": "builtin", "key": "trash"}]},
    ]
    result = _extract_builtin_keys_from_items(items)
    assert result == {"all", "archived", "trash"}


def test__extract_collection_ids_from_items__extracts_ids() -> None:
    """Test extracting collection IDs."""
    items = [
        {"type": "collection", "id": "uuid-1", "items": []},
        {"type": "collection", "id": "uuid-2", "items": []},
        {"type": "filter", "id": "550e8400-e29b-41d4-a716-446655440001"},
    ]
    result = _extract_collection_ids_from_items(items)
    assert result == {"uuid-1", "uuid-2"}


# =============================================================================
# _remove_filter_from_items Tests
# =============================================================================


def test__remove_filter_from_items__removes_from_root() -> None:
    """Test removing a filter from root items."""
    id1 = uuid4()
    id2 = uuid4()
    items = [
        {"type": "filter", "id": str(id1)},
        {"type": "filter", "id": str(id2)},
        {"type": "builtin", "key": "all"},
    ]
    new_items, was_removed = _remove_filter_from_items(items, id1)

    assert was_removed is True
    assert len(new_items) == 2
    assert {"type": "filter", "id": str(id1)} not in new_items


def test__remove_filter_from_items__removes_from_group() -> None:
    """Test removing a filter from within a group."""
    id1 = uuid4()
    id2 = uuid4()
    items = [
        {
            "type": "collection",
            "id": "uuid-1",
            "name": "Group",
            "items": [
                {"type": "filter", "id": str(id1)},
                {"type": "filter", "id": str(id2)},
            ],
        },
    ]
    new_items, was_removed = _remove_filter_from_items(items, id1)

    assert was_removed is True
    assert len(new_items[0]["items"]) == 1
    assert new_items[0]["items"][0]["id"] == str(id2)


def test__remove_filter_from_items__returns_false_when_not_found() -> None:
    """Test that removing a nonexistent list returns False."""
    id1 = uuid4()
    items = [{"type": "filter", "id": str(id1)}]
    new_items, was_removed = _remove_filter_from_items(items, uuid4())  # Different UUID

    assert was_removed is False
    assert new_items == items


# =============================================================================
# _validate_sidebar_order Tests
# =============================================================================


def test__validate_sidebar_order__accepts_valid_structure() -> None:
    """Test that a valid structure passes validation."""
    filter_id = uuid4()
    order = SidebarOrder(
        items=[
            SidebarBuiltinItem(type="builtin", key="all"),
            SidebarFilterItem(type="filter", id=filter_id),
        ],
    )
    # Should not raise
    _validate_sidebar_order(order, {filter_id})


def test__validate_sidebar_order__rejects_duplicate_list() -> None:
    """Test that duplicate filter IDs are rejected."""
    filter_id = uuid4()
    order = SidebarOrder(
        items=[
            SidebarFilterItem(type="filter", id=filter_id),
            SidebarFilterItem(type="filter", id=filter_id),
        ],
    )
    with pytest.raises(SidebarDuplicateItemError) as exc_info:
        _validate_sidebar_order(order, {filter_id})

    assert exc_info.value.item_type == "filter"
    assert exc_info.value.item_id == filter_id
    assert "Duplicate filter item" in str(exc_info.value)


def test__validate_sidebar_order__rejects_duplicate_builtin() -> None:
    """Test that duplicate builtin keys are rejected."""
    order = SidebarOrder(
        items=[
            SidebarBuiltinItem(type="builtin", key="all"),
            SidebarBuiltinItem(type="builtin", key="all"),
        ],
    )
    with pytest.raises(SidebarDuplicateItemError) as exc_info:
        _validate_sidebar_order(order, set())

    assert exc_info.value.item_type == "builtin"
    assert exc_info.value.item_id == "all"
    assert "Duplicate builtin item" in str(exc_info.value)


def test__validate_sidebar_order__rejects_duplicate_group_id() -> None:
    """Test that duplicate collection IDs are rejected."""
    order = SidebarOrder(
        items=[
            SidebarCollection(
                type="collection",
                id="550e8400-e29b-41d4-a716-446655440000",
                name="Group 1",
                items=[],
            ),
            SidebarCollection(
                type="collection",
                id="550e8400-e29b-41d4-a716-446655440000",
                name="Group 2",
                items=[],
            ),
        ],
    )
    with pytest.raises(SidebarDuplicateItemError) as exc_info:
        _validate_sidebar_order(order, set())

    assert exc_info.value.item_type == "collection"
    assert exc_info.value.item_id == "550e8400-e29b-41d4-a716-446655440000"
    assert "Duplicate collection item" in str(exc_info.value)


def test__validate_sidebar_order__rejects_nonexistent_list() -> None:
    """Test that filter IDs not belonging to user are rejected."""
    missing_id = uuid4()
    user_ids = {uuid4(), uuid4(), uuid4()}
    order = SidebarOrder(
        items=[
            SidebarFilterItem(type="filter", id=missing_id),
        ],
    )
    with pytest.raises(SidebarFilterNotFoundError) as exc_info:
        _validate_sidebar_order(order, user_ids)  # missing_id not in set

    assert exc_info.value.filter_id == missing_id
    assert "Filter not found" in str(exc_info.value)


def test__validate_sidebar_order__allows_duplicate_group_names() -> None:
    """Test that groups with same name but different IDs are allowed."""
    order = SidebarOrder(
        items=[
            SidebarCollection(
                type="collection",
                id="550e8400-e29b-41d4-a716-446655440000",
                name="Work",
                items=[],
            ),
            SidebarCollection(
                type="collection",
                id="660e8400-e29b-41d4-a716-446655440001",
                name="Work",  # Same name, different ID - allowed
                items=[],
            ),
        ],
    )
    # Should not raise
    _validate_sidebar_order(order, set())


def test__validate_sidebar_order__rejects_duplicate_list_across_root_and_group() -> None:
    """Test that a filter appearing both at root and inside a group is rejected."""
    filter_id = uuid4()
    order = SidebarOrder(
        items=[
            SidebarFilterItem(type="filter", id=filter_id),
            SidebarCollection(
                type="collection",
                id="550e8400-e29b-41d4-a716-446655440000",
                name="Work",
                items=[
                    SidebarFilterItem(type="filter", id=filter_id),  # Duplicate of root list
                ],
            ),
        ],
    )
    with pytest.raises(SidebarDuplicateItemError) as exc_info:
        _validate_sidebar_order(order, {filter_id})

    assert exc_info.value.item_type == "filter"
    assert exc_info.value.item_id == filter_id
    assert "Duplicate filter item" in str(exc_info.value)


# =============================================================================
# get_computed_sidebar Tests
# =============================================================================


async def test__get_computed_sidebar__returns_default_for_new_user(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that new users get default sidebar."""
    result = await get_computed_sidebar(db_session, test_user.id, [])

    assert result.version == SIDEBAR_VERSION
    assert len(result.items) == 4

    # Check builtin names are resolved
    builtin_keys = [
        item.key for item in result.items if hasattr(item, "key")
    ]
    assert "command-palette" in builtin_keys
    assert "all" in builtin_keys
    assert "archived" in builtin_keys
    assert "trash" in builtin_keys


async def test__get_computed_sidebar__injects_command_palette_for_existing_users(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that command-palette is injected at top for existing users missing it."""
    # Simulate an existing user's saved sidebar without command-palette
    settings = UserSettings(
        user_id=test_user.id,
        sidebar_order={
            "version": 1,
            "items": [
                {"type": "builtin", "key": "all"},
                {"type": "builtin", "key": "archived"},
                {"type": "builtin", "key": "trash"},
            ],
        },
    )
    db_session.add(settings)
    await db_session.flush()

    result = await get_computed_sidebar(db_session, test_user.id, [])

    # Should have 4 items: command-palette prepended + existing 3
    assert len(result.items) == 4
    assert result.items[0].key == "command-palette"  # type: ignore[union-attr]
    assert result.items[1].key == "all"  # type: ignore[union-attr]


async def test__get_computed_sidebar__does_not_duplicate_command_palette(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that command-palette is not duplicated if already present."""
    settings = UserSettings(
        user_id=test_user.id,
        sidebar_order={
            "version": 1,
            "items": [
                {"type": "builtin", "key": "all"},
                {"type": "builtin", "key": "command-palette"},
                {"type": "builtin", "key": "trash"},
            ],
        },
    )
    db_session.add(settings)
    await db_session.flush()

    result = await get_computed_sidebar(db_session, test_user.id, [])

    # Should remain 3 items, command-palette not duplicated
    assert len(result.items) == 3
    command_palette_count = sum(
        1 for item in result.items
        if hasattr(item, "key") and item.key == "command-palette"
    )
    assert command_palette_count == 1


async def test__get_computed_sidebar__resolves_list_names(
    db_session: AsyncSession,
    test_user: User,
    test_filter: ContentFilter,
) -> None:
    """Test that filter names are resolved from database."""
    # Set up sidebar with the list (ID stored as string in JSON)
    settings = UserSettings(
        user_id=test_user.id,
        sidebar_order={
            "version": 1,
            "items": [
                {"type": "builtin", "key": "all"},
                {"type": "filter", "id": str(test_filter.id)},
            ],
        },
    )
    db_session.add(settings)
    await db_session.flush()

    result = await get_computed_sidebar(db_session, test_user.id, [test_filter])

    # Find the list item
    list_items = [item for item in result.items if hasattr(item, "name") and hasattr(item, "content_types")]
    assert len(list_items) == 1
    assert list_items[0].name == "Test List"
    assert list_items[0].content_types == ["bookmark"]


async def test__get_computed_sidebar__filters_deleted_list_references(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that references to deleted filters are filtered out."""
    # Set up sidebar with a nonexistent list
    nonexistent_id = str(uuid4())
    settings = UserSettings(
        user_id=test_user.id,
        sidebar_order={
            "version": 1,
            "items": [
                {"type": "builtin", "key": "all"},
                {"type": "filter", "id": nonexistent_id},  # Doesn't exist
            ],
        },
    )
    db_session.add(settings)
    await db_session.flush()

    result = await get_computed_sidebar(db_session, test_user.id, [])

    # Should have command-palette (injected) + the builtin
    assert len(result.items) == 2
    assert result.items[0].key == "command-palette"  # type: ignore[union-attr]
    assert result.items[1].key == "all"  # type: ignore[union-attr]


async def test__get_computed_sidebar__prepends_orphan_lists_to_root(
    db_session: AsyncSession,
    test_user: User,
    test_filter: ContentFilter,
) -> None:
    """Test that lists in DB but not in sidebar are prepended to root."""
    # Set up sidebar WITHOUT the list
    settings = UserSettings(
        user_id=test_user.id,
        sidebar_order={
            "version": 1,
            "items": [
                {"type": "builtin", "key": "all"},
            ],
        },
    )
    db_session.add(settings)
    await db_session.flush()

    result = await get_computed_sidebar(db_session, test_user.id, [test_filter])

    # Should have orphan list + command-palette (injected) + builtin
    assert len(result.items) == 3

    # First item should be the orphaned list (prepended before command-palette)
    first_item = result.items[0]
    assert hasattr(first_item, "id")
    assert first_item.id == test_filter.id  # type: ignore[union-attr]


async def test__get_computed_sidebar__preserves_group_structure(
    db_session: AsyncSession,
    test_user: User,
    test_filter: ContentFilter,
) -> None:
    """Test that group structure is preserved in computed sidebar."""
    settings = UserSettings(
        user_id=test_user.id,
        sidebar_order={
            "version": 1,
            "items": [
                {
                    "type": "collection",
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "name": "Work",
                    "items": [
                        {"type": "filter", "id": str(test_filter.id)},
                    ],
                },
            ],
        },
    )
    db_session.add(settings)
    await db_session.flush()

    result = await get_computed_sidebar(db_session, test_user.id, [test_filter])

    # command-palette injected + the collection
    assert len(result.items) == 2
    assert result.items[0].key == "command-palette"  # type: ignore[union-attr]
    group = result.items[1]
    assert group.type == "collection"
    assert group.name == "Work"  # type: ignore[union-attr]
    assert len(group.items) == 1  # type: ignore[union-attr]


# =============================================================================
# update_sidebar_order Tests
# =============================================================================


async def test__update_sidebar_order__saves_valid_structure(
    db_session: AsyncSession,
    test_user: User,
    test_filter: ContentFilter,
) -> None:
    """Test that a valid sidebar order is saved."""
    order = SidebarOrder(
        items=[
            SidebarBuiltinItem(type="builtin", key="all"),
            SidebarFilterItem(type="filter", id=test_filter.id),
        ],
    )

    result = await update_sidebar_order(
        db_session, test_user.id, order, {test_filter.id},
    )

    assert result.sidebar_order is not None
    assert len(result.sidebar_order["items"]) == 2


async def test__update_sidebar_order__rejects_other_users_list(
    db_session: AsyncSession,
    test_user: User,
    test_filter: ContentFilter,
) -> None:
    """Test that lists not belonging to user are rejected."""
    order = SidebarOrder(
        items=[
            SidebarFilterItem(type="filter", id=test_filter.id),
        ],
    )

    with pytest.raises(SidebarFilterNotFoundError) as exc_info:
        await update_sidebar_order(
            db_session, test_user.id, order, set(),  # Empty set = no lists belong to user
        )

    assert exc_info.value.filter_id == test_filter.id


# =============================================================================
# add_filter_to_sidebar Tests
# =============================================================================


async def test__add_filter_to_sidebar__creates_default_with_list(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test adding filter when no settings exist creates default with list."""
    filter_id = uuid4()
    result = await add_filter_to_sidebar(db_session, test_user.id, filter_id)

    assert result.sidebar_order is not None
    filter_ids = _extract_filter_ids_from_items(result.sidebar_order["items"])
    assert filter_id in filter_ids


async def test__add_filter_to_sidebar__appends_to_existing(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that list is appended to end of existing sidebar."""
    filter_id = uuid4()
    # Create initial sidebar
    settings = UserSettings(
        user_id=test_user.id,
        sidebar_order={
            "version": 1,
            "items": [
                {"type": "builtin", "key": "all"},
            ],
        },
    )
    db_session.add(settings)
    await db_session.flush()

    result = await add_filter_to_sidebar(db_session, test_user.id, filter_id)

    # List should be at the end (stored as string in JSON)
    items = result.sidebar_order["items"]
    assert items[-1] == {"type": "filter", "id": str(filter_id)}


async def test__add_filter_to_sidebar__does_not_duplicate(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that adding existing list does not create duplicate."""
    filter_id = uuid4()
    settings = UserSettings(
        user_id=test_user.id,
        sidebar_order={
            "version": 1,
            "items": [
                {"type": "filter", "id": str(filter_id)},
            ],
        },
    )
    db_session.add(settings)
    await db_session.flush()

    result = await add_filter_to_sidebar(db_session, test_user.id, filter_id)

    filter_ids = _extract_filter_ids_from_items(result.sidebar_order["items"])
    # Should only appear once
    assert filter_ids == {filter_id}


# =============================================================================
# remove_filter_from_sidebar Tests
# =============================================================================


async def test__remove_filter_from_sidebar__returns_none_when_no_settings(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that removing list when no settings exist returns None."""
    result = await remove_filter_from_sidebar(db_session, test_user.id, uuid4())
    assert result is None


async def test__remove_filter_from_sidebar__removes_from_root(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test removing list from root level."""
    filter_id = uuid4()
    settings = UserSettings(
        user_id=test_user.id,
        sidebar_order={
            "version": 1,
            "items": [
                {"type": "builtin", "key": "all"},
                {"type": "filter", "id": str(filter_id)},
            ],
        },
    )
    db_session.add(settings)
    await db_session.flush()

    result = await remove_filter_from_sidebar(db_session, test_user.id, filter_id)

    assert result is not None
    filter_ids = _extract_filter_ids_from_items(result.sidebar_order["items"])
    assert filter_id not in filter_ids


async def test__remove_filter_from_sidebar__removes_from_group(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test removing list from within a group."""
    filter_id = uuid4()
    settings = UserSettings(
        user_id=test_user.id,
        sidebar_order={
            "version": 1,
            "items": [
                {
                    "type": "collection",
                    "id": "uuid-1",
                    "name": "Work",
                    "items": [
                        {"type": "filter", "id": str(filter_id)},
                    ],
                },
            ],
        },
    )
    db_session.add(settings)
    await db_session.flush()

    result = await remove_filter_from_sidebar(db_session, test_user.id, filter_id)

    assert result is not None
    filter_ids = _extract_filter_ids_from_items(result.sidebar_order["items"])
    assert filter_id not in filter_ids


async def test__remove_filter_from_sidebar__handles_nonexistent_list(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test removing list that doesn't exist in sidebar is a no-op."""
    settings = UserSettings(
        user_id=test_user.id,
        sidebar_order={
            "version": 1,
            "items": [
                {"type": "builtin", "key": "all"},
            ],
        },
    )
    db_session.add(settings)
    await db_session.flush()
    original_order = copy.deepcopy(settings.sidebar_order)

    result = await remove_filter_from_sidebar(db_session, test_user.id, uuid4())

    assert result is not None
    assert result.sidebar_order == original_order
