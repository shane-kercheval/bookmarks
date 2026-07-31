"""Tests for content filter service layer functionality."""
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.content_filter import ContentFilter
from models.filter_group import FilterGroup as FilterGroupModel
from models.tag import Tag, filter_group_tags
from models.user import User
from schemas.content_filter import (
    ContentFilterCreate,
    ContentFilterUpdate,
    FilterExpression,
    FilterGroup,
)
from services.content_filter_service import (
    create_filter,
    delete_filter,
    get_filter,
    get_filters,
    update_filter,
)
from core.tier_limits import Tier
from services.settings_service import get_settings


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(external_auth_id="test-filter-user-123", email="filter@example.com", tier=Tier.FREE.value)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def other_user(db_session: AsyncSession) -> User:
    """Create another test user for isolation tests."""
    user = User(external_auth_id="other-filter-user-456", email="other@example.com", tier=Tier.FREE.value)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


def make_filter_expression(tags_groups: list[list[str]]) -> FilterExpression:
    """Helper to create filter expressions."""
    return FilterExpression(
        groups=[FilterGroup(tags=tags) for tags in tags_groups],
        group_operator="OR",
    )


async def load_filter_with_groups(
    db_session: AsyncSession,
    filter_id: str,
) -> ContentFilter:
    """Load a filter with its groups and tags eagerly loaded."""
    query = (
        select(ContentFilter)
        .options(
            selectinload(ContentFilter.groups).selectinload(FilterGroupModel.tag_objects),
        )
        .where(ContentFilter.id == filter_id)
    )
    result = await db_session.execute(query)
    return result.scalar_one()


def extract_filter_expression(content_filter: ContentFilter) -> dict:
    """
    Extract filter expression dict from a ContentFilter ORM model.

    The filter must have groups eagerly loaded (use load_filter_with_groups).
    Returns a dict matching the API response format:
    {
        "groups": [{"tags": [...], "operator": "AND"}, ...],
        "group_operator": "OR"
    }
    """
    groups = [
        {
            "tags": sorted(tag.name for tag in group.tag_objects),
            "operator": group.operator,
        }
        for group in sorted(content_filter.groups, key=lambda g: g.position)
    ]
    return {
        "groups": groups,
        "group_operator": content_filter.group_operator,
    }


# =============================================================================
# create_filter Tests
# =============================================================================


async def test__create_filter__creates_filter_with_filter_expression(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test creating a content filter stores filter expression correctly."""
    data = ContentFilterCreate(
        name="Work Tasks",
        filter_expression=make_filter_expression([["work", "priority"]]),
    )

    result = await create_filter(db_session, test_user.id, data)

    assert result.id is not None
    assert result.name == "Work Tasks"
    assert result.user_id == test_user.id
    # Load with groups to verify normalized structure
    loaded = await load_filter_with_groups(db_session, result.id)
    expression = extract_filter_expression(loaded)
    assert expression == {
        "groups": [{"tags": ["priority", "work"], "operator": "AND"}],
        "group_operator": "OR",
    }
    # Default content_types should be ["bookmark", "note"]
    assert result.content_types == ["bookmark", "note"]


async def test__create_filter__adds_to_sidebar_order(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test creating a filter adds it to the user's sidebar_order."""
    data = ContentFilterCreate(
        name="My Filter",
        filter_expression=make_filter_expression([["tag1"]]),
    )

    result = await create_filter(db_session, test_user.id, data)

    settings = await get_settings(db_session, test_user.id)
    assert settings is not None
    assert settings.sidebar_order is not None
    # Filter should be in the sidebar items (IDs stored as strings in JSON)
    filter_ids = [
        item["id"] for item in settings.sidebar_order["items"]
        if item.get("type") == "filter"
    ]
    assert str(result.id) in filter_ids


async def test__create_filter__multiple_filters_append_in_order(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test creating multiple filters appends each to sidebar_order."""
    data1 = ContentFilterCreate(
        name="First",
        filter_expression=make_filter_expression([["tag1"]]),
    )
    data2 = ContentFilterCreate(
        name="Second",
        filter_expression=make_filter_expression([["tag2"]]),
    )

    filter1 = await create_filter(db_session, test_user.id, data1)
    filter2 = await create_filter(db_session, test_user.id, data2)

    settings = await get_settings(db_session, test_user.id)
    assert settings is not None
    assert settings.sidebar_order is not None
    # Both filters should be in sidebar items (IDs stored as strings in JSON)
    filter_ids = [
        item["id"] for item in settings.sidebar_order["items"]
        if item.get("type") == "filter"
    ]
    assert str(filter1.id) in filter_ids
    assert str(filter2.id) in filter_ids


async def test__create_filter__normalizes_tags(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that tags in filter expression are normalized to lowercase."""
    data = ContentFilterCreate(
        name="Normalized",
        filter_expression=FilterExpression(
            groups=[FilterGroup(tags=["WORK", "Priority"])],
            group_operator="OR",
        ),
    )

    result = await create_filter(db_session, test_user.id, data)

    # Load with groups to verify normalized structure
    loaded = await load_filter_with_groups(db_session, result.id)
    expression = extract_filter_expression(loaded)
    # Tags are sorted alphabetically in extract_filter_expression
    assert expression["groups"][0]["tags"] == ["priority", "work"]


async def test__create_filter__with_custom_content_types(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test creating a filter with custom content_types."""
    data = ContentFilterCreate(
        name="Notes Only",
        filter_expression=make_filter_expression([["notes"]]),
        content_types=["note"],
    )

    result = await create_filter(db_session, test_user.id, data)

    assert result.content_types == ["note"]


async def test__create_filter__with_single_content_type(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test creating a filter with a single content type (bookmarks only)."""
    data = ContentFilterCreate(
        name="Bookmarks Only",
        filter_expression=make_filter_expression([["bookmarks"]]),
        content_types=["bookmark"],
    )

    result = await create_filter(db_session, test_user.id, data)

    assert result.content_types == ["bookmark"]


# =============================================================================
# get_filters Tests
# =============================================================================


async def test__get_filters__returns_empty_when_no_filters(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test get_filters returns empty list when user has no filters."""
    result = await get_filters(db_session, test_user.id)
    assert result == []


async def test__get_filters__returns_user_filters_ordered_by_created_at(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test get_filters returns filters ordered by creation date."""
    # Create filters in order
    for i, name in enumerate(["First", "Second", "Third"]):
        data = ContentFilterCreate(
            name=name,
            filter_expression=make_filter_expression([[f"tag{i}"]]),
        )
        await create_filter(db_session, test_user.id, data)

    result = await get_filters(db_session, test_user.id)

    assert len(result) == 3
    assert result[0].name == "First"
    assert result[1].name == "Second"
    assert result[2].name == "Third"


async def test__get_filters__user_isolation(
    db_session: AsyncSession,
    test_user: User,
    other_user: User,
) -> None:
    """Test get_filters only returns filters belonging to the user."""
    # Create filter for test_user
    data1 = ContentFilterCreate(
        name="User1 Filter",
        filter_expression=make_filter_expression([["tag1"]]),
    )
    await create_filter(db_session, test_user.id, data1)

    # Create filter for other_user
    data2 = ContentFilterCreate(
        name="User2 Filter",
        filter_expression=make_filter_expression([["tag2"]]),
    )
    await create_filter(db_session, other_user.id, data2)

    # Each user should only see their own filters
    user1_filters = await get_filters(db_session, test_user.id)
    user2_filters = await get_filters(db_session, other_user.id)

    assert len(user1_filters) == 1
    assert user1_filters[0].name == "User1 Filter"
    assert len(user2_filters) == 1
    assert user2_filters[0].name == "User2 Filter"


# =============================================================================
# get_filter Tests
# =============================================================================


async def test__get_filter__returns_filter_by_id(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test get_filter returns the correct filter by ID."""
    data = ContentFilterCreate(
        name="Target Filter",
        filter_expression=make_filter_expression([["target"]]),
    )
    created = await create_filter(db_session, test_user.id, data)

    result = await get_filter(db_session, test_user.id, created.id)

    assert result is not None
    assert result.id == created.id
    assert result.name == "Target Filter"


async def test__get_filter__returns_none_for_nonexistent(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test get_filter returns None for non-existent filter."""
    result = await get_filter(db_session, test_user.id, uuid4())
    assert result is None


async def test__get_filter__returns_none_for_other_users_filter(
    db_session: AsyncSession,
    test_user: User,
    other_user: User,
) -> None:
    """Test get_filter returns None when trying to access another user's filter."""
    # Create filter for other_user
    data = ContentFilterCreate(
        name="Other's Filter",
        filter_expression=make_filter_expression([["other"]]),
    )
    other_filter = await create_filter(db_session, other_user.id, data)

    # Try to access with test_user
    result = await get_filter(db_session, test_user.id, other_filter.id)

    assert result is None


# =============================================================================
# update_filter Tests
# =============================================================================


async def test__update_filter__updates_name(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test update_filter updates the name."""
    data = ContentFilterCreate(
        name="Original Name",
        filter_expression=make_filter_expression([["tag"]]),
    )
    created = await create_filter(db_session, test_user.id, data)

    update_data = ContentFilterUpdate(name="New Name")
    result = await update_filter(db_session, test_user.id, created.id, update_data)

    assert result is not None
    assert result.name == "New Name"


async def test__update_filter__updates_filter_expression(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test update_filter updates the filter expression."""
    data = ContentFilterCreate(
        name="Test Filter",
        filter_expression=make_filter_expression([["old-tag"]]),
    )
    created = await create_filter(db_session, test_user.id, data)

    update_data = ContentFilterUpdate(
        filter_expression=make_filter_expression([["new-tag1"], ["new-tag2"]]),
    )
    result = await update_filter(db_session, test_user.id, created.id, update_data)

    assert result is not None
    # Load with groups to verify normalized structure
    loaded = await load_filter_with_groups(db_session, result.id)
    expression = extract_filter_expression(loaded)
    assert len(expression["groups"]) == 2
    assert expression["groups"][0]["tags"] == ["new-tag1"]
    assert expression["groups"][1]["tags"] == ["new-tag2"]


async def test__update_filter__updates_content_types(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test update_filter updates the content_types."""
    data = ContentFilterCreate(
        name="Test Filter",
        filter_expression=make_filter_expression([["tag"]]),
        content_types=["bookmark", "note"],
    )
    created = await create_filter(db_session, test_user.id, data)

    update_data = ContentFilterUpdate(content_types=["note"])
    result = await update_filter(db_session, test_user.id, created.id, update_data)

    assert result is not None
    assert result.content_types == ["note"]


async def test__update_filter__ignores_unset_fields(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test update_filter only updates fields that are set."""
    data = ContentFilterCreate(
        name="Keep This Name",
        filter_expression=make_filter_expression([["keep-tag"]]),
    )
    created = await create_filter(db_session, test_user.id, data)

    # Update with empty data should not change anything
    update_data = ContentFilterUpdate()
    result = await update_filter(db_session, test_user.id, created.id, update_data)

    assert result is not None
    assert result.name == "Keep This Name"
    # Load with groups to verify normalized structure
    loaded = await load_filter_with_groups(db_session, result.id)
    expression = extract_filter_expression(loaded)
    assert expression["groups"][0]["tags"] == ["keep-tag"]


async def test__update_filter__returns_none_for_nonexistent(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test update_filter returns None for non-existent filter."""
    update_data = ContentFilterUpdate(name="New Name")
    result = await update_filter(db_session, test_user.id, uuid4(), update_data)
    assert result is None


async def test__update_filter__returns_none_for_other_users_filter(
    db_session: AsyncSession,
    test_user: User,
    other_user: User,
) -> None:
    """Test update_filter returns None when trying to update another user's filter."""
    # Create filter for other_user
    data = ContentFilterCreate(
        name="Other's Filter",
        filter_expression=make_filter_expression([["other"]]),
    )
    other_filter = await create_filter(db_session, other_user.id, data)

    # Try to update with test_user
    update_data = ContentFilterUpdate(name="Hijacked")
    result = await update_filter(db_session, test_user.id, other_filter.id, update_data)

    assert result is None

    # Verify original unchanged
    original = await get_filter(db_session, other_user.id, other_filter.id)
    assert original is not None
    assert original.name == "Other's Filter"


# =============================================================================
# delete_filter Tests
# =============================================================================


async def test__delete_filter__deletes_filter(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test delete_filter removes the filter."""
    data = ContentFilterCreate(
        name="To Delete",
        filter_expression=make_filter_expression([["delete"]]),
    )
    created = await create_filter(db_session, test_user.id, data)

    result = await delete_filter(db_session, test_user.id, created.id)

    assert result is True
    # Verify deleted
    fetched = await get_filter(db_session, test_user.id, created.id)
    assert fetched is None


async def test__delete_filter__removes_from_sidebar_order(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test delete_filter removes the filter from sidebar_order."""
    data = ContentFilterCreate(
        name="To Delete",
        filter_expression=make_filter_expression([["delete"]]),
    )
    created = await create_filter(db_session, test_user.id, data)

    # Verify it's in sidebar_order (IDs stored as strings in JSON)
    settings = await get_settings(db_session, test_user.id)
    assert settings is not None
    assert settings.sidebar_order is not None
    filter_ids = [
        item["id"] for item in settings.sidebar_order["items"]
        if item.get("type") == "filter"
    ]
    assert str(created.id) in filter_ids

    # Delete
    await delete_filter(db_session, test_user.id, created.id)

    # Verify removed from sidebar_order
    await db_session.refresh(settings)
    filter_ids = [
        item["id"] for item in settings.sidebar_order["items"]
        if item.get("type") == "filter"
    ]
    assert str(created.id) not in filter_ids


async def test__delete_filter__returns_false_for_nonexistent(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test delete_filter returns False for non-existent filter."""
    result = await delete_filter(db_session, test_user.id, uuid4())
    assert result is False


async def test__delete_filter__returns_false_for_other_users_filter(
    db_session: AsyncSession,
    test_user: User,
    other_user: User,
) -> None:
    """Test delete_filter returns False when trying to delete another user's filter."""
    # Create filter for other_user
    data = ContentFilterCreate(
        name="Other's Filter",
        filter_expression=make_filter_expression([["other"]]),
    )
    other_filter = await create_filter(db_session, other_user.id, data)

    # Try to delete with test_user
    result = await delete_filter(db_session, test_user.id, other_filter.id)

    assert result is False

    # Verify not deleted
    original = await get_filter(db_session, other_user.id, other_filter.id)
    assert original is not None


# =============================================================================
# updated_at Timestamp Tests
# =============================================================================


async def test__update_filter__updates_timestamp(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that update_filter updates the updated_at timestamp."""
    data = ContentFilterCreate(
        name="Original",
        filter_expression=make_filter_expression([["tag"]]),
    )
    created = await create_filter(db_session, test_user.id, data)
    await db_session.refresh(created)
    original_updated_at = created.updated_at

    # Update the filter
    update_data = ContentFilterUpdate(name="Updated Name")
    result = await update_filter(db_session, test_user.id, created.id, update_data)

    assert result is not None
    assert result.updated_at > original_updated_at


async def test__update_filter__updates_timestamp_for_filter_changes(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that update_filter updates timestamp when filter expression changes."""
    data = ContentFilterCreate(
        name="Filter Test",
        filter_expression=make_filter_expression([["old-tag"]]),
    )
    created = await create_filter(db_session, test_user.id, data)
    await db_session.refresh(created)
    original_updated_at = created.updated_at

    # Update filter expression
    update_data = ContentFilterUpdate(
        filter_expression=make_filter_expression([["new-tag"]]),
    )
    result = await update_filter(db_session, test_user.id, created.id, update_data)

    assert result is not None
    assert result.updated_at > original_updated_at


async def test__update_filter__updates_timestamp_even_with_no_field_changes(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """
    Test that update_filter updates timestamp even when no fields are actually changed.

    Note: This tests the current implementation behavior where updated_at is always
    set on update, even if the model_dump(exclude_unset=True) returns empty data.
    This is intentional to track when an update operation occurred.
    """
    data = ContentFilterCreate(
        name="No Change",
        filter_expression=make_filter_expression([["tag"]]),
    )
    created = await create_filter(db_session, test_user.id, data)
    await db_session.refresh(created)
    original_updated_at = created.updated_at

    # Update with empty data
    update_data = ContentFilterUpdate()
    result = await update_filter(db_session, test_user.id, created.id, update_data)

    assert result is not None
    # Timestamp is updated because we explicitly set it in the service
    assert result.updated_at > original_updated_at


# =============================================================================
# Cascade Delete Tests
# =============================================================================


async def test__user_delete__cascades_to_filters(
    db_session: AsyncSession,
) -> None:
    """
    Deleting a user removes their filters — via the account-deletion service,
    which is the only sanctioned user-deletion path: it bulk-deletes the
    filter chain before the user row, because a bare user delete would trip
    the filter_group_tags.tag_id RESTRICT constraint when a filter group
    references a tag (see models/user.py passive_deletes notes).
    """
    from services.user_service import (  # noqa: PLC0415
        delete_user_by_external_auth_id,
    )

    user = User(
        external_auth_id="user_cascade_filter",
        email="cascade@example.com",
        tier=Tier.FREE.value,
    )
    db_session.add(user)
    await db_session.flush()

    data = ContentFilterCreate(
        name="User's Filter",
        filter_expression=make_filter_expression([["cascade"]]),
    )
    created = await create_filter(db_session, user.id, data)
    filter_id = created.id

    result = await delete_user_by_external_auth_id(db_session, "user_cascade_filter")
    assert result.deleted is True

    # Filter should be gone (use raw query to check without user scope)
    query = select(ContentFilter).where(ContentFilter.id == filter_id)
    result = await db_session.execute(query)
    assert result.scalar_one_or_none() is None


# =============================================================================
# Filter Expression Validation Tests
# =============================================================================


async def test__create_filter__complex_filter_expression(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test creating a filter with a complex filter expression."""
    # (work AND high-priority) OR (urgent) OR (critical AND deadline)
    data = ContentFilterCreate(
        name="Complex Filter",
        filter_expression=FilterExpression(
            groups=[
                FilterGroup(tags=["work", "high-priority"]),
                FilterGroup(tags=["urgent"]),
                FilterGroup(tags=["critical", "deadline"]),
            ],
            group_operator="OR",
        ),
    )

    result = await create_filter(db_session, test_user.id, data)

    # Load with groups to verify normalized structure
    loaded = await load_filter_with_groups(db_session, result.id)
    expression = extract_filter_expression(loaded)
    assert len(expression["groups"]) == 3
    # Tags are sorted alphabetically within each group
    assert expression["groups"][0]["tags"] == ["high-priority", "work"]
    assert expression["groups"][1]["tags"] == ["urgent"]
    assert expression["groups"][2]["tags"] == ["critical", "deadline"]


# =============================================================================
# Default Sort Field Tests
# =============================================================================


async def test__create_filter__creates_filter_with_sort_defaults(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test creating a filter with default sort configuration."""
    data = ContentFilterCreate(
        name="Sorted Filter",
        filter_expression=make_filter_expression([["work"]]),
        default_sort_by="created_at",
        default_sort_ascending=True,
    )

    result = await create_filter(db_session, test_user.id, data)

    assert result.default_sort_by == "created_at"
    assert result.default_sort_ascending is True


async def test__create_filter__creates_filter_without_sort_defaults(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test creating a filter without sort configuration uses NULL values."""
    data = ContentFilterCreate(
        name="No Sort Config",
        filter_expression=make_filter_expression([["work"]]),
    )

    result = await create_filter(db_session, test_user.id, data)

    assert result.default_sort_by is None
    assert result.default_sort_ascending is None


async def test__create_filter__creates_filter_with_sort_by_only(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test creating a filter with only sort_by (ascending defaults to None/False)."""
    data = ContentFilterCreate(
        name="Sort By Only",
        filter_expression=make_filter_expression([["work"]]),
        default_sort_by="last_used_at",
    )

    result = await create_filter(db_session, test_user.id, data)

    assert result.default_sort_by == "last_used_at"
    assert result.default_sort_ascending is None


async def test__create_filter__creates_filter_with_all_sort_options(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test creating filters with all valid sort options."""
    sort_options = ["created_at", "updated_at", "last_used_at", "title"]

    for i, sort_by in enumerate(sort_options):
        data = ContentFilterCreate(
            name=f"Filter sorted by {sort_by}",
            filter_expression=make_filter_expression([[f"tag-sort-{i}"]]),
            default_sort_by=sort_by,  # type: ignore[arg-type]
            default_sort_ascending=False,
        )

        result = await create_filter(db_session, test_user.id, data)

        assert result.default_sort_by == sort_by
        assert result.default_sort_ascending is False


async def test__update_filter__updates_sort_fields(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test updating a filter's sort configuration."""
    # Create without sort config
    data = ContentFilterCreate(
        name="To Update Sort",
        filter_expression=make_filter_expression([["tag"]]),
    )
    created = await create_filter(db_session, test_user.id, data)
    assert created.default_sort_by is None

    # Update with sort config
    update_data = ContentFilterUpdate(
        default_sort_by="title",
        default_sort_ascending=True,
    )
    result = await update_filter(db_session, test_user.id, created.id, update_data)

    assert result is not None
    assert result.default_sort_by == "title"
    assert result.default_sort_ascending is True


async def test__update_filter__updates_sort_by_only(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test updating only the sort_by field."""
    data = ContentFilterCreate(
        name="Partial Update",
        filter_expression=make_filter_expression([["tag"]]),
        default_sort_by="created_at",
        default_sort_ascending=True,
    )
    created = await create_filter(db_session, test_user.id, data)

    # Update only sort_by, ascending should remain unchanged
    update_data = ContentFilterUpdate(default_sort_by="updated_at")
    result = await update_filter(db_session, test_user.id, created.id, update_data)

    assert result is not None
    assert result.default_sort_by == "updated_at"
    # ascending should remain unchanged since exclude_unset=True
    assert result.default_sort_ascending is True


async def test__update_filter__clears_sort_config_with_none(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that setting sort fields to None clears them."""
    data = ContentFilterCreate(
        name="Clear Sort",
        filter_expression=make_filter_expression([["tag"]]),
        default_sort_by="created_at",
        default_sort_ascending=True,
    )
    created = await create_filter(db_session, test_user.id, data)

    # Note: To actually clear values, we need to explicitly set them to None
    # and they need to be included in the update. With exclude_unset=True,
    # we can only clear by explicitly setting to None if the field is provided.
    update_data = ContentFilterUpdate(
        default_sort_by=None,
        default_sort_ascending=None,
    )
    result = await update_filter(db_session, test_user.id, created.id, update_data)

    assert result is not None
    # Values are explicitly set to None
    assert result.default_sort_by is None
    assert result.default_sort_ascending is None


async def test__get_filter__returns_sort_fields(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that get_filter returns sort configuration."""
    data = ContentFilterCreate(
        name="Get With Sort",
        filter_expression=make_filter_expression([["tag"]]),
        default_sort_by="last_used_at",
        default_sort_ascending=False,
    )
    created = await create_filter(db_session, test_user.id, data)

    result = await get_filter(db_session, test_user.id, created.id)

    assert result is not None
    assert result.default_sort_by == "last_used_at"
    assert result.default_sort_ascending is False


async def test__get_filters__returns_sort_fields(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that get_filters returns sort configuration for all filters."""
    # Create filter with sort config
    data1 = ContentFilterCreate(
        name="With Sort",
        filter_expression=make_filter_expression([["tag1"]]),
        default_sort_by="title",
        default_sort_ascending=True,
    )
    # Create filter without sort config
    data2 = ContentFilterCreate(
        name="Without Sort",
        filter_expression=make_filter_expression([["tag2"]]),
    )

    await create_filter(db_session, test_user.id, data1)
    await create_filter(db_session, test_user.id, data2)

    results = await get_filters(db_session, test_user.id)

    assert len(results) == 2
    # First filter (created first)
    assert results[0].default_sort_by == "title"
    assert results[0].default_sort_ascending is True
    # Second filter
    assert results[1].default_sort_by is None
    assert results[1].default_sort_ascending is None


# =============================================================================
# FilterGroup and Tag Tests
# =============================================================================


async def test__create_filter__creates_filter_groups(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that creating a filter creates FilterGroup records with correct positions."""
    data = ContentFilterCreate(
        name="Multi Group Filter",
        filter_expression=FilterExpression(
            groups=[
                FilterGroup(tags=["tag-a"]),
                FilterGroup(tags=["tag-b"]),
                FilterGroup(tags=["tag-c"]),
            ],
            group_operator="OR",
        ),
    )

    result = await create_filter(db_session, test_user.id, data)

    # Load filter with groups
    loaded = await load_filter_with_groups(db_session, result.id)
    assert len(loaded.groups) == 3
    # Verify positions
    positions = sorted(g.position for g in loaded.groups)
    assert positions == [0, 1, 2]


async def test__create_filter__creates_tags_for_new_tag_names(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that creating a filter creates Tag records for new tag names."""
    data = ContentFilterCreate(
        name="New Tags Filter",
        filter_expression=make_filter_expression([["brand-new-tag"]]),
    )

    await create_filter(db_session, test_user.id, data)

    # Verify tag was created in tags table
    tag_query = select(Tag).where(
        Tag.user_id == test_user.id,
        Tag.name == "brand-new-tag",
    )
    tag_result = await db_session.execute(tag_query)
    tag = tag_result.scalar_one_or_none()
    assert tag is not None
    assert tag.name == "brand-new-tag"


async def test__create_filter__reuses_existing_tags(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that creating a filter reuses existing tags instead of duplicating."""
    # Create a tag first
    existing_tag = Tag(user_id=test_user.id, name="existing-tag")
    db_session.add(existing_tag)
    await db_session.flush()
    original_tag_id = existing_tag.id

    # Create filter with same tag name
    data = ContentFilterCreate(
        name="Reuse Tag Filter",
        filter_expression=make_filter_expression([["existing-tag"]]),
    )
    await create_filter(db_session, test_user.id, data)

    # Verify no duplicate tag was created
    tag_query = select(Tag).where(
        Tag.user_id == test_user.id,
        Tag.name == "existing-tag",
    )
    tag_result = await db_session.execute(tag_query)
    tags = list(tag_result.scalars().all())
    assert len(tags) == 1
    assert tags[0].id == original_tag_id


async def test__create_filter__links_tags_to_groups(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that creating a filter links tags to groups via junction table."""
    data = ContentFilterCreate(
        name="Linked Filter",
        filter_expression=make_filter_expression([["linked-tag-1", "linked-tag-2"]]),
    )

    result = await create_filter(db_session, test_user.id, data)

    # Load filter with groups and tags
    loaded = await load_filter_with_groups(db_session, result.id)
    assert len(loaded.groups) == 1
    group = loaded.groups[0]
    tag_names = sorted(t.name for t in group.tag_objects)
    assert tag_names == ["linked-tag-1", "linked-tag-2"]


async def test__create_filter__empty_groups_skipped(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that groups with empty tag lists are not created."""
    data = ContentFilterCreate(
        name="Empty Groups Filter",
        filter_expression=FilterExpression(
            groups=[
                FilterGroup(tags=[]),  # Should be skipped
                FilterGroup(tags=["real-tag"]),
                FilterGroup(tags=[]),  # Should be skipped
            ],
            group_operator="OR",
        ),
    )

    result = await create_filter(db_session, test_user.id, data)

    # Only one group should be created (the one with real-tag)
    loaded = await load_filter_with_groups(db_session, result.id)
    assert len(loaded.groups) == 1
    assert loaded.groups[0].tag_objects[0].name == "real-tag"


async def test__create_filter__multiple_groups_correct_positions(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that multiple groups preserve position ordering."""
    data = ContentFilterCreate(
        name="Positioned Filter",
        filter_expression=FilterExpression(
            groups=[
                FilterGroup(tags=["first"]),
                FilterGroup(tags=["second"]),
                FilterGroup(tags=["third"]),
            ],
            group_operator="OR",
        ),
    )

    result = await create_filter(db_session, test_user.id, data)

    loaded = await load_filter_with_groups(db_session, result.id)
    # Sort by position and verify tag order matches input order
    sorted_groups = sorted(loaded.groups, key=lambda g: g.position)
    assert sorted_groups[0].tag_objects[0].name == "first"
    assert sorted_groups[1].tag_objects[0].name == "second"
    assert sorted_groups[2].tag_objects[0].name == "third"


async def test__update_filter__replaces_groups(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that updating filter expression replaces all groups."""
    data = ContentFilterCreate(
        name="Replace Groups Filter",
        filter_expression=make_filter_expression([["old-group-tag"]]),
    )
    created = await create_filter(db_session, test_user.id, data)

    # Get original group ID
    loaded_before = await load_filter_with_groups(db_session, created.id)
    old_group_id = loaded_before.groups[0].id

    # Update with new groups
    update_data = ContentFilterUpdate(
        filter_expression=make_filter_expression([["new-group-tag"]]),
    )
    await update_filter(db_session, test_user.id, created.id, update_data)

    # Verify old group is gone and new group exists
    loaded_after = await load_filter_with_groups(db_session, created.id)
    assert len(loaded_after.groups) == 1
    assert loaded_after.groups[0].id != old_group_id
    assert loaded_after.groups[0].tag_objects[0].name == "new-group-tag"


async def test__update_filter__preserves_groups_when_expression_not_provided(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that partial update without filter_expression preserves groups."""
    data = ContentFilterCreate(
        name="Preserve Groups Filter",
        filter_expression=make_filter_expression([["preserved-tag"]]),
    )
    created = await create_filter(db_session, test_user.id, data)

    # Update only name, not filter_expression
    update_data = ContentFilterUpdate(name="Updated Name")
    await update_filter(db_session, test_user.id, created.id, update_data)

    # Verify groups are unchanged
    loaded = await load_filter_with_groups(db_session, created.id)
    assert len(loaded.groups) == 1
    assert loaded.groups[0].tag_objects[0].name == "preserved-tag"


async def test__update_filter__updates_group_operator(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that updating filter expression updates group_operator."""
    data = ContentFilterCreate(
        name="Operator Filter",
        filter_expression=FilterExpression(
            groups=[FilterGroup(tags=["tag"])],
            group_operator="OR",
        ),
    )
    created = await create_filter(db_session, test_user.id, data)
    assert created.group_operator == "OR"

    # Update filter expression (group_operator stays "OR" since that's the only option)
    update_data = ContentFilterUpdate(
        filter_expression=FilterExpression(
            groups=[FilterGroup(tags=["new-tag"])],
            group_operator="OR",
        ),
    )
    result = await update_filter(db_session, test_user.id, created.id, update_data)

    assert result is not None
    assert result.group_operator == "OR"


async def test__update_filter__removes_tag_from_filter(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that updating filter to remove a tag removes it from filter but not from tags table."""
    data = ContentFilterCreate(
        name="Remove Tag Filter",
        filter_expression=make_filter_expression([["keep-tag", "remove-tag"]]),
    )
    created = await create_filter(db_session, test_user.id, data)

    # Update to remove "remove-tag"
    update_data = ContentFilterUpdate(
        filter_expression=make_filter_expression([["keep-tag"]]),
    )
    await update_filter(db_session, test_user.id, created.id, update_data)

    # Verify filter only has "keep-tag"
    loaded = await load_filter_with_groups(db_session, created.id)
    tag_names = [t.name for t in loaded.groups[0].tag_objects]
    assert tag_names == ["keep-tag"]

    # Verify "remove-tag" still exists in tags table
    tag_query = select(Tag).where(
        Tag.user_id == test_user.id,
        Tag.name == "remove-tag",
    )
    tag_result = await db_session.execute(tag_query)
    tag = tag_result.scalar_one_or_none()
    assert tag is not None


async def test__update_filter__adds_existing_tag(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that updating filter to add an existing tag reuses it."""
    # Create a tag first
    existing_tag = Tag(user_id=test_user.id, name="add-existing")
    db_session.add(existing_tag)
    await db_session.flush()
    original_tag_id = existing_tag.id

    # Create filter without the tag
    data = ContentFilterCreate(
        name="Add Existing Filter",
        filter_expression=make_filter_expression([["initial-tag"]]),
    )
    created = await create_filter(db_session, test_user.id, data)

    # Update to add the existing tag
    update_data = ContentFilterUpdate(
        filter_expression=make_filter_expression([["initial-tag", "add-existing"]]),
    )
    await update_filter(db_session, test_user.id, created.id, update_data)

    # Verify the filter uses the existing tag (same ID)
    loaded = await load_filter_with_groups(db_session, created.id)
    tag_ids = {t.id for t in loaded.groups[0].tag_objects}
    assert original_tag_id in tag_ids


async def test__update_filter__adds_new_tag(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that updating filter to add a new tag creates it in tags table."""
    data = ContentFilterCreate(
        name="Add New Filter",
        filter_expression=make_filter_expression([["initial"]]),
    )
    created = await create_filter(db_session, test_user.id, data)

    # Update to add a brand new tag
    update_data = ContentFilterUpdate(
        filter_expression=make_filter_expression([["initial", "brand-new"]]),
    )
    await update_filter(db_session, test_user.id, created.id, update_data)

    # Verify new tag was created
    tag_query = select(Tag).where(
        Tag.user_id == test_user.id,
        Tag.name == "brand-new",
    )
    tag_result = await db_session.execute(tag_query)
    tag = tag_result.scalar_one_or_none()
    assert tag is not None


async def test__update_filter__mixed_existing_and_new_tags(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test updating filter with mix of existing and new tags."""
    # Create an existing tag
    existing_tag = Tag(user_id=test_user.id, name="existing")
    db_session.add(existing_tag)
    await db_session.flush()

    # Create filter
    data = ContentFilterCreate(
        name="Mixed Filter",
        filter_expression=make_filter_expression([["old"]]),
    )
    created = await create_filter(db_session, test_user.id, data)

    # Update with mix of existing and new
    update_data = ContentFilterUpdate(
        filter_expression=make_filter_expression([["existing", "new-one", "new-two"]]),
    )
    await update_filter(db_session, test_user.id, created.id, update_data)

    # Verify all tags exist
    tag_query = select(Tag.name).where(
        Tag.user_id == test_user.id,
        Tag.name.in_(["existing", "new-one", "new-two"]),
    )
    tag_result = await db_session.execute(tag_query)
    tag_names = set(tag_result.scalars().all())
    assert tag_names == {"existing", "new-one", "new-two"}


async def test__update_filter__to_empty_expression(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test updating filter to have no groups."""
    data = ContentFilterCreate(
        name="Clear Groups Filter",
        filter_expression=make_filter_expression([["tag-to-remove"]]),
    )
    created = await create_filter(db_session, test_user.id, data)

    # Update to empty expression
    update_data = ContentFilterUpdate(
        filter_expression=FilterExpression(groups=[], group_operator="OR"),
    )
    await update_filter(db_session, test_user.id, created.id, update_data)

    # Verify filter has no groups
    loaded = await load_filter_with_groups(db_session, created.id)
    assert len(loaded.groups) == 0


async def test__update_filter__reorders_groups(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test updating filter with same tags but different group positions."""
    data = ContentFilterCreate(
        name="Reorder Filter",
        filter_expression=FilterExpression(
            groups=[
                FilterGroup(tags=["first"]),
                FilterGroup(tags=["second"]),
            ],
            group_operator="OR",
        ),
    )
    created = await create_filter(db_session, test_user.id, data)

    # Update with reversed order
    update_data = ContentFilterUpdate(
        filter_expression=FilterExpression(
            groups=[
                FilterGroup(tags=["second"]),
                FilterGroup(tags=["first"]),
            ],
            group_operator="OR",
        ),
    )
    await update_filter(db_session, test_user.id, created.id, update_data)

    # Verify new order
    loaded = await load_filter_with_groups(db_session, created.id)
    sorted_groups = sorted(loaded.groups, key=lambda g: g.position)
    assert sorted_groups[0].tag_objects[0].name == "second"
    assert sorted_groups[1].tag_objects[0].name == "first"


async def test__update_filter__same_tags_different_grouping(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test updating filter with same tags split across groups differently."""
    data = ContentFilterCreate(
        name="Regrouped Filter",
        filter_expression=FilterExpression(
            groups=[
                FilterGroup(tags=["a", "b", "c"]),
            ],
            group_operator="OR",
        ),
    )
    created = await create_filter(db_session, test_user.id, data)

    # Update to split into multiple groups
    update_data = ContentFilterUpdate(
        filter_expression=FilterExpression(
            groups=[
                FilterGroup(tags=["a"]),
                FilterGroup(tags=["b", "c"]),
            ],
            group_operator="OR",
        ),
    )
    await update_filter(db_session, test_user.id, created.id, update_data)

    loaded = await load_filter_with_groups(db_session, created.id)
    assert len(loaded.groups) == 2


async def test__update_filter__adds_group(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test updating filter to add an additional group."""
    data = ContentFilterCreate(
        name="Add Group Filter",
        filter_expression=FilterExpression(
            groups=[FilterGroup(tags=["original"])],
            group_operator="OR",
        ),
    )
    created = await create_filter(db_session, test_user.id, data)

    # Add another group
    update_data = ContentFilterUpdate(
        filter_expression=FilterExpression(
            groups=[
                FilterGroup(tags=["original"]),
                FilterGroup(tags=["added"]),
            ],
            group_operator="OR",
        ),
    )
    await update_filter(db_session, test_user.id, created.id, update_data)

    loaded = await load_filter_with_groups(db_session, created.id)
    assert len(loaded.groups) == 2


async def test__update_filter__removes_group(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test updating filter to remove a group while keeping others."""
    data = ContentFilterCreate(
        name="Remove Group Filter",
        filter_expression=FilterExpression(
            groups=[
                FilterGroup(tags=["keep"]),
                FilterGroup(tags=["remove"]),
            ],
            group_operator="OR",
        ),
    )
    created = await create_filter(db_session, test_user.id, data)

    # Remove second group
    update_data = ContentFilterUpdate(
        filter_expression=FilterExpression(
            groups=[FilterGroup(tags=["keep"])],
            group_operator="OR",
        ),
    )
    await update_filter(db_session, test_user.id, created.id, update_data)

    loaded = await load_filter_with_groups(db_session, created.id)
    assert len(loaded.groups) == 1
    assert loaded.groups[0].tag_objects[0].name == "keep"


async def test__update_filter__cleans_up_old_junction_entries(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that updating filter removes old filter_group_tags entries."""
    data = ContentFilterCreate(
        name="Cleanup Filter",
        filter_expression=make_filter_expression([["cleanup-tag"]]),
    )
    created = await create_filter(db_session, test_user.id, data)

    # Get original group ID
    loaded_before = await load_filter_with_groups(db_session, created.id)
    old_group_id = loaded_before.groups[0].id

    # Update to different tags
    update_data = ContentFilterUpdate(
        filter_expression=make_filter_expression([["new-cleanup-tag"]]),
    )
    await update_filter(db_session, test_user.id, created.id, update_data)

    # Verify old junction entries are gone
    junction_query = select(filter_group_tags).where(
        filter_group_tags.c.group_id == old_group_id,
    )
    junction_result = await db_session.execute(junction_query)
    assert len(list(junction_result)) == 0


async def test__update_filter__orphaned_tags_remain_in_db(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that tags removed from filter still exist in tags table."""
    data = ContentFilterCreate(
        name="Orphan Tag Filter",
        filter_expression=make_filter_expression([["will-be-orphaned"]]),
    )
    created = await create_filter(db_session, test_user.id, data)

    # Update to completely different tags
    update_data = ContentFilterUpdate(
        filter_expression=make_filter_expression([["completely-different"]]),
    )
    await update_filter(db_session, test_user.id, created.id, update_data)

    # Verify original tag still exists (orphaned but not deleted)
    tag_query = select(Tag).where(
        Tag.user_id == test_user.id,
        Tag.name == "will-be-orphaned",
    )
    tag_result = await db_session.execute(tag_query)
    tag = tag_result.scalar_one_or_none()
    assert tag is not None


async def test__delete_filter__cascades_to_groups(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that deleting a filter cascades to delete its groups."""
    data = ContentFilterCreate(
        name="Cascade Delete Filter",
        filter_expression=make_filter_expression([["cascade-delete-tag"]]),
    )
    created = await create_filter(db_session, test_user.id, data)

    # Get group ID before deletion
    loaded = await load_filter_with_groups(db_session, created.id)
    group_id = loaded.groups[0].id

    # Delete the filter
    await delete_filter(db_session, test_user.id, created.id)

    # Verify group is also deleted
    group_query = select(FilterGroupModel).where(FilterGroupModel.id == group_id)
    group_result = await db_session.execute(group_query)
    assert group_result.scalar_one_or_none() is None


async def test__delete_filter__does_not_delete_tags(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that deleting a filter does not delete the associated tags."""
    data = ContentFilterCreate(
        name="Keep Tags Filter",
        filter_expression=make_filter_expression([["tag-should-remain"]]),
    )
    created = await create_filter(db_session, test_user.id, data)

    # Delete the filter
    await delete_filter(db_session, test_user.id, created.id)

    # Verify tag still exists
    tag_query = select(Tag).where(
        Tag.user_id == test_user.id,
        Tag.name == "tag-should-remain",
    )
    tag_result = await db_session.execute(tag_query)
    tag = tag_result.scalar_one_or_none()
    assert tag is not None


async def test__create_filter__handles_duplicate_tags_in_group(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that duplicate tag names (case-insensitive) are deduplicated."""
    # Create filter with duplicate tags (different cases)
    data = ContentFilterCreate(
        name="Duplicate Tags Filter",
        filter_expression=FilterExpression(
            groups=[FilterGroup(tags=["Work", "work", "WORK", "priority"])],
            group_operator="OR",
        ),
    )

    result = await create_filter(db_session, test_user.id, data)

    # Verify only unique tags are linked (work should appear once, not three times)
    loaded = await load_filter_with_groups(db_session, result.id)
    assert len(loaded.groups) == 1
    tag_names = sorted(t.name for t in loaded.groups[0].tag_objects)
    # Should have exactly 2 unique tags: "priority" and "work"
    assert tag_names == ["priority", "work"]


async def test__update_filter__handles_duplicate_tags_in_group(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that updating with duplicate tags deduplicates them."""
    data = ContentFilterCreate(
        name="Update Dup Filter",
        filter_expression=make_filter_expression([["initial"]]),
    )
    created = await create_filter(db_session, test_user.id, data)

    # Update with duplicates
    update_data = ContentFilterUpdate(
        filter_expression=FilterExpression(
            groups=[FilterGroup(tags=["Tag", "TAG", "tag", "other"])],
            group_operator="OR",
        ),
    )
    await update_filter(db_session, test_user.id, created.id, update_data)

    loaded = await load_filter_with_groups(db_session, created.id)
    tag_names = sorted(t.name for t in loaded.groups[0].tag_objects)
    assert tag_names == ["other", "tag"]
