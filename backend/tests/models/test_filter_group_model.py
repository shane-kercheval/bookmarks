"""
Tests for FilterGroup model.

Tests model instantiation, relationships, constraints, and cascade behavior
for the normalized filter expression storage.
"""
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.content_filter import ContentFilter
from models.filter_group import FilterGroup
from models.tag import Tag, filter_group_tags
from models.user import User
from core.tier_limits import Tier


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(external_auth_id="test-user-filter-group-123", email="filter-group@example.com", tier=Tier.FREE.value)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_filter(db_session: AsyncSession, test_user: User) -> ContentFilter:
    """Create a test content filter."""
    content_filter = ContentFilter(
        user_id=test_user.id,
        name="Test Filter",
        content_types=["bookmark", "note"],
        group_operator="OR",
    )
    db_session.add(content_filter)
    await db_session.flush()
    await db_session.refresh(content_filter)
    return content_filter


@pytest.fixture
async def test_tag(db_session: AsyncSession, test_user: User) -> Tag:
    """Create a test tag."""
    tag = Tag(user_id=test_user.id, name="test-tag")
    db_session.add(tag)
    await db_session.flush()
    await db_session.refresh(tag)
    return tag


# =============================================================================
# Model Instantiation Tests
# =============================================================================


async def test__filter_group_model__creates_with_required_fields(
    db_session: AsyncSession,
    test_filter: ContentFilter,
) -> None:
    """Test that FilterGroup can be created with required fields."""
    group = FilterGroup(
        filter_id=test_filter.id,
        position=0,
    )
    db_session.add(group)
    await db_session.flush()
    await db_session.refresh(group)

    assert group.id is not None
    assert group.filter_id == test_filter.id
    assert group.position == 0
    assert group.operator == "AND"  # Default value


async def test__filter_group_model__creates_with_custom_operator(
    db_session: AsyncSession,
    test_filter: ContentFilter,
) -> None:
    """Test that FilterGroup can be created with custom operator."""
    group = FilterGroup(
        filter_id=test_filter.id,
        position=0,
        operator="AND",
    )
    db_session.add(group)
    await db_session.flush()
    await db_session.refresh(group)

    assert group.operator == "AND"


async def test__filter_group_model__multiple_groups_with_positions(
    db_session: AsyncSession,
    test_filter: ContentFilter,
) -> None:
    """Test that multiple groups can be created with different positions."""
    group0 = FilterGroup(filter_id=test_filter.id, position=0)
    group1 = FilterGroup(filter_id=test_filter.id, position=1)
    group2 = FilterGroup(filter_id=test_filter.id, position=2)

    db_session.add_all([group0, group1, group2])
    await db_session.flush()

    assert group0.id is not None
    assert group1.id is not None
    assert group2.id is not None
    assert group0.position == 0
    assert group1.position == 1
    assert group2.position == 2


# =============================================================================
# Relationship Tests
# =============================================================================


async def test__filter_group_model__content_filter_relationship(
    db_session: AsyncSession,
    test_filter: ContentFilter,
) -> None:
    """Test that filter_group.content_filter returns the associated filter."""
    group = FilterGroup(filter_id=test_filter.id, position=0)
    db_session.add(group)
    await db_session.flush()
    await db_session.refresh(group, attribute_names=["content_filter"])

    assert group.content_filter is not None
    assert group.content_filter.id == test_filter.id
    assert group.content_filter.name == "Test Filter"


async def test__filter_group_model__tag_objects_relationship(
    db_session: AsyncSession,
    test_filter: ContentFilter,
    test_user: User,
) -> None:
    """Test that filter_group.tag_objects returns associated tags."""
    # Create tags
    tag1 = Tag(user_id=test_user.id, name="work")
    tag2 = Tag(user_id=test_user.id, name="priority")
    db_session.add_all([tag1, tag2])
    await db_session.flush()

    # Create group with tags
    group = FilterGroup(
        filter_id=test_filter.id,
        position=0,
        tag_objects=[tag1, tag2],
    )
    db_session.add(group)
    await db_session.flush()
    await db_session.refresh(group, attribute_names=["tag_objects"])

    assert len(group.tag_objects) == 2
    tag_names = [t.name for t in group.tag_objects]
    assert "work" in tag_names
    assert "priority" in tag_names


async def test__content_filter_model__groups_relationship(
    db_session: AsyncSession,
    test_filter: ContentFilter,
) -> None:
    """Test that content_filter.groups returns associated groups in order."""
    # Create groups in non-sequential order
    group2 = FilterGroup(filter_id=test_filter.id, position=2)
    group0 = FilterGroup(filter_id=test_filter.id, position=0)
    group1 = FilterGroup(filter_id=test_filter.id, position=1)

    db_session.add_all([group2, group0, group1])
    await db_session.flush()
    await db_session.refresh(test_filter, attribute_names=["groups"])

    # Groups should be ordered by position
    assert len(test_filter.groups) == 3
    assert test_filter.groups[0].position == 0
    assert test_filter.groups[1].position == 1
    assert test_filter.groups[2].position == 2


# =============================================================================
# Constraint Tests
# =============================================================================


async def test__filter_group_model__unique_position_per_filter(
    db_session: AsyncSession,
    test_filter: ContentFilter,
) -> None:
    """Test that duplicate position for same filter raises IntegrityError."""
    group1 = FilterGroup(filter_id=test_filter.id, position=0)
    db_session.add(group1)
    await db_session.flush()

    # Try to create another group with same position
    group2 = FilterGroup(filter_id=test_filter.id, position=0)
    db_session.add(group2)

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test__filter_group_model__same_position_different_filters(
    db_session: AsyncSession,
    test_user: User,
    test_filter: ContentFilter,
) -> None:
    """Test that different filters can have groups with the same position."""
    # Create another filter
    other_filter = ContentFilter(
        user_id=test_user.id,
        name="Other Filter",
        content_types=["bookmark"],
        group_operator="OR",
    )
    db_session.add(other_filter)
    await db_session.flush()

    # Both filters can have position 0
    group1 = FilterGroup(filter_id=test_filter.id, position=0)
    group2 = FilterGroup(filter_id=other_filter.id, position=0)

    db_session.add_all([group1, group2])
    await db_session.flush()

    assert group1.id is not None
    assert group2.id is not None


# =============================================================================
# CASCADE Delete Tests
# =============================================================================


async def test__filter_group_model__cascade_delete_filter_removes_groups(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that deleting a filter cascades to delete its groups."""
    # Create filter and groups
    content_filter = ContentFilter(
        user_id=test_user.id,
        name="Cascade Test Filter",
        content_types=["bookmark"],
        group_operator="OR",
    )
    db_session.add(content_filter)
    await db_session.flush()

    group1 = FilterGroup(filter_id=content_filter.id, position=0)
    group2 = FilterGroup(filter_id=content_filter.id, position=1)
    db_session.add_all([group1, group2])
    await db_session.flush()

    group1_id = group1.id
    group2_id = group2.id

    # Delete filter
    await db_session.delete(content_filter)
    await db_session.flush()

    # Verify groups are gone
    result = await db_session.execute(
        select(FilterGroup).where(FilterGroup.id.in_([group1_id, group2_id])),
    )
    assert result.scalars().all() == []


async def test__filter_group_model__cascade_delete_group_removes_junction_entries(
    db_session: AsyncSession,
    test_filter: ContentFilter,
    test_user: User,
) -> None:
    """Test that deleting a group cascades to remove filter_group_tags entries."""
    # Create tag
    tag = Tag(user_id=test_user.id, name="cascade-test-tag")
    db_session.add(tag)
    await db_session.flush()

    # Create group with tag
    group = FilterGroup(filter_id=test_filter.id, position=0)
    group.tag_objects = [tag]
    db_session.add(group)
    await db_session.flush()
    group_id = group.id

    # Verify junction entry exists
    result = await db_session.execute(
        select(filter_group_tags).where(filter_group_tags.c.group_id == group_id),
    )
    assert result.first() is not None

    # Delete group
    await db_session.delete(group)
    await db_session.flush()

    # Verify junction entry is gone
    result = await db_session.execute(
        select(filter_group_tags).where(filter_group_tags.c.group_id == group_id),
    )
    assert result.first() is None


async def test__filter_group_model__cascade_delete_user_removes_filters_and_groups(
    db_session: AsyncSession,
) -> None:
    """Test that deleting a user cascades to delete filters and groups."""
    # Create user, filter, and group
    user = User(external_auth_id="cascade-user-test", email="cascade-user@example.com", tier=Tier.FREE.value)
    db_session.add(user)
    await db_session.flush()

    content_filter = ContentFilter(
        user_id=user.id,
        name="User Cascade Filter",
        content_types=["note"],
        group_operator="OR",
    )
    db_session.add(content_filter)
    await db_session.flush()

    group = FilterGroup(filter_id=content_filter.id, position=0)
    db_session.add(group)
    await db_session.flush()

    filter_id = content_filter.id
    group_id = group.id

    # Delete user
    await db_session.delete(user)
    await db_session.flush()

    # Verify filter and group are gone
    filter_result = await db_session.execute(
        select(ContentFilter).where(ContentFilter.id == filter_id),
    )
    assert filter_result.scalar_one_or_none() is None

    group_result = await db_session.execute(
        select(FilterGroup).where(FilterGroup.id == group_id),
    )
    assert group_result.scalar_one_or_none() is None


# =============================================================================
# RESTRICT Delete Tests (Tag deletion blocked when used in filters)
# =============================================================================


async def test__filter_group_tags__restrict_delete_tag_used_in_filter(
    db_session: AsyncSession,
    test_filter: ContentFilter,
    test_user: User,
) -> None:
    """Test that deleting a tag used in a filter group raises IntegrityError."""
    # Create tag
    tag = Tag(user_id=test_user.id, name="restricted-tag")
    db_session.add(tag)
    await db_session.flush()

    # Create group with tag
    group = FilterGroup(filter_id=test_filter.id, position=0)
    group.tag_objects = [tag]
    db_session.add(group)
    await db_session.flush()

    # Try to delete the tag - should fail due to RESTRICT
    await db_session.delete(tag)

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test__filter_group_tags__delete_tag_succeeds_when_not_in_filter(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that deleting a tag not used in any filter succeeds."""
    # Create tag not used in any filter
    tag = Tag(user_id=test_user.id, name="unused-tag")
    db_session.add(tag)
    await db_session.flush()
    tag_id = tag.id

    # Delete should succeed
    await db_session.delete(tag)
    await db_session.flush()

    # Verify tag is gone
    result = await db_session.execute(select(Tag).where(Tag.id == tag_id))
    assert result.scalar_one_or_none() is None


async def test__filter_group_tags__delete_tag_succeeds_after_removing_from_filter(
    db_session: AsyncSession,
    test_filter: ContentFilter,
    test_user: User,
) -> None:
    """Test that tag can be deleted after removing it from all filter groups."""
    # Create tag
    tag = Tag(user_id=test_user.id, name="removable-tag")
    db_session.add(tag)
    await db_session.flush()

    # Create group with tag
    group = FilterGroup(filter_id=test_filter.id, position=0)
    group.tag_objects = [tag]
    db_session.add(group)
    await db_session.flush()

    # Remove tag from group
    group.tag_objects = []
    await db_session.flush()

    # Now deletion should succeed
    await db_session.delete(tag)
    await db_session.flush()

    # Verify tag is gone
    result = await db_session.execute(
        select(Tag).where(Tag.name == "removable-tag", Tag.user_id == test_user.id),
    )
    assert result.scalar_one_or_none() is None
