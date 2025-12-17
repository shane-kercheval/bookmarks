"""Tests for bookmark list service layer functionality."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from models.bookmark_list import BookmarkList
from models.user import User
from schemas.bookmark_list import (
    BookmarkListCreate,
    BookmarkListUpdate,
    FilterExpression,
    FilterGroup,
)
from services.bookmark_list_service import (
    create_list,
    delete_list,
    get_list,
    get_lists,
    update_list,
)
from services.settings_service import get_settings


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(auth0_id="test-list-user-123", email="list@example.com")
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def other_user(db_session: AsyncSession) -> User:
    """Create another test user for isolation tests."""
    user = User(auth0_id="other-list-user-456", email="other@example.com")
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


# =============================================================================
# create_list Tests
# =============================================================================


async def test__create_list__creates_list_with_filter_expression(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test creating a bookmark list stores filter expression correctly."""
    data = BookmarkListCreate(
        name="Work Tasks",
        filter_expression=make_filter_expression([["work", "priority"]]),
    )

    result = await create_list(db_session, test_user.id, data)

    assert result.id is not None
    assert result.name == "Work Tasks"
    assert result.user_id == test_user.id
    assert result.filter_expression == {
        "groups": [{"tags": ["work", "priority"], "operator": "AND"}],
        "group_operator": "OR",
    }


async def test__create_list__adds_to_tab_order(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test creating a list adds it to the user's tab_order."""
    data = BookmarkListCreate(
        name="My List",
        filter_expression=make_filter_expression([["tag1"]]),
    )

    result = await create_list(db_session, test_user.id, data)

    settings = await get_settings(db_session, test_user.id)
    assert settings is not None
    assert f"list:{result.id}" in settings.tab_order
    # Should be prepended
    assert settings.tab_order[0] == f"list:{result.id}"


async def test__create_list__multiple_lists_prepend_in_order(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test creating multiple lists prepends each to tab_order."""
    data1 = BookmarkListCreate(
        name="First",
        filter_expression=make_filter_expression([["tag1"]]),
    )
    data2 = BookmarkListCreate(
        name="Second",
        filter_expression=make_filter_expression([["tag2"]]),
    )

    list1 = await create_list(db_session, test_user.id, data1)
    list2 = await create_list(db_session, test_user.id, data2)

    settings = await get_settings(db_session, test_user.id)
    assert settings is not None
    # Second list should be at the front
    assert settings.tab_order[0] == f"list:{list2.id}"
    assert f"list:{list1.id}" in settings.tab_order


async def test__create_list__normalizes_tags(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that tags in filter expression are normalized to lowercase."""
    data = BookmarkListCreate(
        name="Normalized",
        filter_expression=FilterExpression(
            groups=[FilterGroup(tags=["WORK", "Priority"])],
            group_operator="OR",
        ),
    )

    result = await create_list(db_session, test_user.id, data)

    assert result.filter_expression["groups"][0]["tags"] == ["work", "priority"]


# =============================================================================
# get_lists Tests
# =============================================================================


async def test__get_lists__returns_empty_when_no_lists(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test get_lists returns empty list when user has no lists."""
    result = await get_lists(db_session, test_user.id)
    assert result == []


async def test__get_lists__returns_user_lists_ordered_by_created_at(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test get_lists returns lists ordered by creation date."""
    # Create lists in order
    for i, name in enumerate(["First", "Second", "Third"]):
        data = BookmarkListCreate(
            name=name,
            filter_expression=make_filter_expression([[f"tag{i}"]]),
        )
        await create_list(db_session, test_user.id, data)

    result = await get_lists(db_session, test_user.id)

    assert len(result) == 3
    assert result[0].name == "First"
    assert result[1].name == "Second"
    assert result[2].name == "Third"


async def test__get_lists__user_isolation(
    db_session: AsyncSession,
    test_user: User,
    other_user: User,
) -> None:
    """Test get_lists only returns lists belonging to the user."""
    # Create list for test_user
    data1 = BookmarkListCreate(
        name="User1 List",
        filter_expression=make_filter_expression([["tag1"]]),
    )
    await create_list(db_session, test_user.id, data1)

    # Create list for other_user
    data2 = BookmarkListCreate(
        name="User2 List",
        filter_expression=make_filter_expression([["tag2"]]),
    )
    await create_list(db_session, other_user.id, data2)

    # Each user should only see their own lists
    user1_lists = await get_lists(db_session, test_user.id)
    user2_lists = await get_lists(db_session, other_user.id)

    assert len(user1_lists) == 1
    assert user1_lists[0].name == "User1 List"
    assert len(user2_lists) == 1
    assert user2_lists[0].name == "User2 List"


# =============================================================================
# get_list Tests
# =============================================================================


async def test__get_list__returns_list_by_id(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test get_list returns the correct list by ID."""
    data = BookmarkListCreate(
        name="Target List",
        filter_expression=make_filter_expression([["target"]]),
    )
    created = await create_list(db_session, test_user.id, data)

    result = await get_list(db_session, test_user.id, created.id)

    assert result is not None
    assert result.id == created.id
    assert result.name == "Target List"


async def test__get_list__returns_none_for_nonexistent(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test get_list returns None for non-existent list."""
    result = await get_list(db_session, test_user.id, 99999)
    assert result is None


async def test__get_list__returns_none_for_other_users_list(
    db_session: AsyncSession,
    test_user: User,
    other_user: User,
) -> None:
    """Test get_list returns None when trying to access another user's list."""
    # Create list for other_user
    data = BookmarkListCreate(
        name="Other's List",
        filter_expression=make_filter_expression([["other"]]),
    )
    other_list = await create_list(db_session, other_user.id, data)

    # Try to access with test_user
    result = await get_list(db_session, test_user.id, other_list.id)

    assert result is None


# =============================================================================
# update_list Tests
# =============================================================================


async def test__update_list__updates_name(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test update_list updates the name."""
    data = BookmarkListCreate(
        name="Original Name",
        filter_expression=make_filter_expression([["tag"]]),
    )
    created = await create_list(db_session, test_user.id, data)

    update_data = BookmarkListUpdate(name="New Name")
    result = await update_list(db_session, test_user.id, created.id, update_data)

    assert result is not None
    assert result.name == "New Name"


async def test__update_list__updates_filter_expression(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test update_list updates the filter expression."""
    data = BookmarkListCreate(
        name="Test List",
        filter_expression=make_filter_expression([["old-tag"]]),
    )
    created = await create_list(db_session, test_user.id, data)

    update_data = BookmarkListUpdate(
        filter_expression=make_filter_expression([["new-tag1"], ["new-tag2"]]),
    )
    result = await update_list(db_session, test_user.id, created.id, update_data)

    assert result is not None
    assert len(result.filter_expression["groups"]) == 2
    assert result.filter_expression["groups"][0]["tags"] == ["new-tag1"]
    assert result.filter_expression["groups"][1]["tags"] == ["new-tag2"]


async def test__update_list__ignores_unset_fields(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test update_list only updates fields that are set."""
    data = BookmarkListCreate(
        name="Keep This Name",
        filter_expression=make_filter_expression([["keep-tag"]]),
    )
    created = await create_list(db_session, test_user.id, data)

    # Update with empty data should not change anything
    update_data = BookmarkListUpdate()
    result = await update_list(db_session, test_user.id, created.id, update_data)

    assert result is not None
    assert result.name == "Keep This Name"
    assert result.filter_expression["groups"][0]["tags"] == ["keep-tag"]


async def test__update_list__returns_none_for_nonexistent(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test update_list returns None for non-existent list."""
    update_data = BookmarkListUpdate(name="New Name")
    result = await update_list(db_session, test_user.id, 99999, update_data)
    assert result is None


async def test__update_list__returns_none_for_other_users_list(
    db_session: AsyncSession,
    test_user: User,
    other_user: User,
) -> None:
    """Test update_list returns None when trying to update another user's list."""
    # Create list for other_user
    data = BookmarkListCreate(
        name="Other's List",
        filter_expression=make_filter_expression([["other"]]),
    )
    other_list = await create_list(db_session, other_user.id, data)

    # Try to update with test_user
    update_data = BookmarkListUpdate(name="Hijacked")
    result = await update_list(db_session, test_user.id, other_list.id, update_data)

    assert result is None

    # Verify original unchanged
    original = await get_list(db_session, other_user.id, other_list.id)
    assert original is not None
    assert original.name == "Other's List"


# =============================================================================
# delete_list Tests
# =============================================================================


async def test__delete_list__deletes_list(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test delete_list removes the list."""
    data = BookmarkListCreate(
        name="To Delete",
        filter_expression=make_filter_expression([["delete"]]),
    )
    created = await create_list(db_session, test_user.id, data)

    result = await delete_list(db_session, test_user.id, created.id)

    assert result is True
    # Verify deleted
    fetched = await get_list(db_session, test_user.id, created.id)
    assert fetched is None


async def test__delete_list__removes_from_tab_order(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test delete_list removes the list from tab_order."""
    data = BookmarkListCreate(
        name="To Delete",
        filter_expression=make_filter_expression([["delete"]]),
    )
    created = await create_list(db_session, test_user.id, data)
    list_key = f"list:{created.id}"

    # Verify it's in tab_order
    settings = await get_settings(db_session, test_user.id)
    assert settings is not None
    assert list_key in settings.tab_order

    # Delete
    await delete_list(db_session, test_user.id, created.id)

    # Verify removed from tab_order
    await db_session.refresh(settings)
    assert list_key not in settings.tab_order


async def test__delete_list__returns_false_for_nonexistent(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test delete_list returns False for non-existent list."""
    result = await delete_list(db_session, test_user.id, 99999)
    assert result is False


async def test__delete_list__returns_false_for_other_users_list(
    db_session: AsyncSession,
    test_user: User,
    other_user: User,
) -> None:
    """Test delete_list returns False when trying to delete another user's list."""
    # Create list for other_user
    data = BookmarkListCreate(
        name="Other's List",
        filter_expression=make_filter_expression([["other"]]),
    )
    other_list = await create_list(db_session, other_user.id, data)

    # Try to delete with test_user
    result = await delete_list(db_session, test_user.id, other_list.id)

    assert result is False

    # Verify not deleted
    original = await get_list(db_session, other_user.id, other_list.id)
    assert original is not None


# =============================================================================
# updated_at Timestamp Tests
# =============================================================================


async def test__update_list__updates_timestamp(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that update_list updates the updated_at timestamp."""
    data = BookmarkListCreate(
        name="Original",
        filter_expression=make_filter_expression([["tag"]]),
    )
    created = await create_list(db_session, test_user.id, data)
    await db_session.refresh(created)
    original_updated_at = created.updated_at

    # Update the list
    update_data = BookmarkListUpdate(name="Updated Name")
    result = await update_list(db_session, test_user.id, created.id, update_data)

    assert result is not None
    assert result.updated_at > original_updated_at


async def test__update_list__updates_timestamp_for_filter_changes(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that update_list updates timestamp when filter expression changes."""
    data = BookmarkListCreate(
        name="Filter Test",
        filter_expression=make_filter_expression([["old-tag"]]),
    )
    created = await create_list(db_session, test_user.id, data)
    await db_session.refresh(created)
    original_updated_at = created.updated_at

    # Update filter expression
    update_data = BookmarkListUpdate(
        filter_expression=make_filter_expression([["new-tag"]]),
    )
    result = await update_list(db_session, test_user.id, created.id, update_data)

    assert result is not None
    assert result.updated_at > original_updated_at


async def test__update_list__updates_timestamp_even_with_no_field_changes(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """
    Test that update_list updates timestamp even when no fields are actually changed.

    Note: This tests the current implementation behavior where updated_at is always
    set on update, even if the model_dump(exclude_unset=True) returns empty data.
    This is intentional to track when an update operation occurred.
    """
    data = BookmarkListCreate(
        name="No Change",
        filter_expression=make_filter_expression([["tag"]]),
    )
    created = await create_list(db_session, test_user.id, data)
    await db_session.refresh(created)
    original_updated_at = created.updated_at

    # Update with empty data
    update_data = BookmarkListUpdate()
    result = await update_list(db_session, test_user.id, created.id, update_data)

    assert result is not None
    # Timestamp is updated because we explicitly set it in the service
    assert result.updated_at > original_updated_at


# =============================================================================
# Cascade Delete Tests
# =============================================================================


async def test__user_delete__cascades_to_lists(
    db_session: AsyncSession,
) -> None:
    """Test that deleting a user cascades to delete their lists."""
    user = User(auth0_id="cascade-list-user", email="cascade@example.com")
    db_session.add(user)
    await db_session.flush()

    data = BookmarkListCreate(
        name="User's List",
        filter_expression=make_filter_expression([["cascade"]]),
    )
    created = await create_list(db_session, user.id, data)
    list_id = created.id

    # Delete user
    await db_session.delete(user)
    await db_session.flush()

    # List should be gone (use raw query to check without user scope)
    from sqlalchemy import select
    query = select(BookmarkList).where(BookmarkList.id == list_id)
    result = await db_session.execute(query)
    assert result.scalar_one_or_none() is None


# =============================================================================
# Filter Expression Validation Tests
# =============================================================================


async def test__create_list__complex_filter_expression(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test creating a list with a complex filter expression."""
    # (work AND high-priority) OR (urgent) OR (critical AND deadline)
    data = BookmarkListCreate(
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

    result = await create_list(db_session, test_user.id, data)

    assert len(result.filter_expression["groups"]) == 3
    assert result.filter_expression["groups"][0]["tags"] == ["work", "high-priority"]
    assert result.filter_expression["groups"][1]["tags"] == ["urgent"]
    assert result.filter_expression["groups"][2]["tags"] == ["critical", "deadline"]
