"""Tests for tag service layer functionality."""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.tier_limits import Tier
from models.bookmark import Bookmark
from models.prompt import Prompt
from models.tag import Tag
from models.user import User
from services.tag_service import (
    TagAlreadyExistsError,
    TagNotFoundError,
    delete_tag,
    get_or_create_tags,
    get_tag_by_name,
    get_user_tags_with_counts,
    rename_tag,
    update_prompt_tags,
)


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(external_auth_id="test-tag-user-123", email="tags@example.com", tier=Tier.FREE.value)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def other_user(db_session: AsyncSession) -> User:
    """Create another test user for isolation tests."""
    user = User(external_auth_id="other-tag-user-456", email="other-tags@example.com", tier=Tier.FREE.value)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


# =============================================================================
# get_or_create_tags Tests
# =============================================================================


async def test__get_or_create_tags__creates_new_tags(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that get_or_create_tags creates tags that don't exist."""
    tags = await get_or_create_tags(db_session, test_user.id, ["python", "web"])
    await db_session.flush()

    assert len(tags) == 2
    tag_names = {t.name for t in tags}
    assert tag_names == {"python", "web"}
    for tag in tags:
        assert tag.user_id == test_user.id
        assert tag.id is not None


async def test__get_or_create_tags__returns_existing_tags(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that get_or_create_tags returns existing tags without duplicating."""
    # Create tags first
    existing = await get_or_create_tags(db_session, test_user.id, ["python"])
    await db_session.flush()
    existing_id = existing[0].id

    # Get same tag again
    tags = await get_or_create_tags(db_session, test_user.id, ["python"])

    assert len(tags) == 1
    assert tags[0].id == existing_id


async def test__get_or_create_tags__normalizes_names(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that get_or_create_tags normalizes tag names."""
    tags = await get_or_create_tags(db_session, test_user.id, ["  Python  ", "WEB"])
    await db_session.flush()

    tag_names = {t.name for t in tags}
    assert tag_names == {"python", "web"}


async def test__get_or_create_tags__empty_list_returns_empty(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that empty tag list returns empty result."""
    tags = await get_or_create_tags(db_session, test_user.id, [])
    assert tags == []


async def test__get_or_create_tags__users_have_separate_tags(
    db_session: AsyncSession,
    test_user: User,
    other_user: User,
) -> None:
    """Test that tags are scoped to users."""
    tags1 = await get_or_create_tags(db_session, test_user.id, ["python"])
    tags2 = await get_or_create_tags(db_session, other_user.id, ["python"])
    await db_session.flush()

    # Same name, different tag records
    assert tags1[0].id != tags2[0].id
    assert tags1[0].user_id == test_user.id
    assert tags2[0].user_id == other_user.id


# =============================================================================
# get_user_tags_with_counts Tests
# =============================================================================


async def test__get_user_tags_with_counts__counts_only_active_bookmarks(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that tag counts exclude archived and deleted bookmarks."""
    # Create tags first
    shared_tag = (await get_or_create_tags(db_session, test_user.id, ["shared"]))[0]
    active_only_tag = (await get_or_create_tags(db_session, test_user.id, ["active-only"]))[0]
    await db_session.flush()

    # Create bookmarks with tags set at creation (like create_bookmark does)
    # This avoids lazy loading issues
    active = Bookmark(user_id=test_user.id, url="https://active.com/")
    active.tag_objects = [shared_tag, active_only_tag]

    archived = Bookmark(user_id=test_user.id, url="https://archived.com/")
    archived.tag_objects = [shared_tag]
    # Use a clearly past time to avoid any timing issues
    archived.archived_at = datetime.now(UTC) - timedelta(hours=1)

    deleted = Bookmark(user_id=test_user.id, url="https://deleted.com/")
    deleted.tag_objects = [shared_tag]
    deleted.deleted_at = datetime.now(UTC)

    db_session.add_all([active, archived, deleted])
    await db_session.flush()

    # Get counts
    counts = await get_user_tags_with_counts(db_session, test_user.id)

    count_dict = {c.name: c.content_count for c in counts}
    # shared: 1 (only active bookmark)
    assert count_dict["shared"] == 1
    # active-only: 1
    assert count_dict["active-only"] == 1


async def test__get_user_tags_with_counts__includes_future_scheduled_bookmarks(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """
    Test that future-scheduled bookmarks count as active in tag counts.

    Bookmarks with archived_at in the future are still "active" (not yet archived),
    so they should be included in tag counts.
    """
    # Create a tag
    scheduled_tag = (await get_or_create_tags(db_session, test_user.id, ["scheduled"]))[0]
    await db_session.flush()

    # Create a bookmark with future archived_at (scheduled but not yet archived)
    scheduled_bookmark = Bookmark(user_id=test_user.id, url="https://scheduled.com/")
    scheduled_bookmark.tag_objects = [scheduled_tag]
    scheduled_bookmark.archived_at = datetime.now(UTC) + timedelta(days=7)

    db_session.add(scheduled_bookmark)
    await db_session.flush()

    # Get counts - future-scheduled bookmark should be counted
    counts = await get_user_tags_with_counts(db_session, test_user.id)

    count_dict = {c.name: c.content_count for c in counts}
    assert count_dict["scheduled"] == 1  # Future-scheduled counts as active


async def test__get_user_tags_with_counts__excludes_orphan_tags_by_default(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that tags with no active content are excluded by default."""
    # Create orphan tag (no associated content)
    orphan = Tag(user_id=test_user.id, name="orphan-tag")
    db_session.add(orphan)

    # Create tag with active bookmark
    active_tag = (await get_or_create_tags(db_session, test_user.id, ["active-tag"]))[0]
    await db_session.flush()

    bookmark = Bookmark(user_id=test_user.id, url="https://example.com/")
    bookmark.tag_objects = [active_tag]
    db_session.add(bookmark)
    await db_session.flush()

    counts = await get_user_tags_with_counts(db_session, test_user.id)

    tag_names = {c.name for c in counts}
    assert "active-tag" in tag_names
    assert "orphan-tag" not in tag_names


async def test__get_user_tags_with_counts__include_inactive_shows_orphan_tags(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that include_inactive=True includes tags with no active content."""
    # Create orphan tag (no associated content)
    orphan = Tag(user_id=test_user.id, name="orphan-tag")
    db_session.add(orphan)

    # Create tag with active bookmark
    active_tag = (await get_or_create_tags(db_session, test_user.id, ["active-tag"]))[0]
    await db_session.flush()

    bookmark = Bookmark(user_id=test_user.id, url="https://example.com/")
    bookmark.tag_objects = [active_tag]
    db_session.add(bookmark)
    await db_session.flush()

    counts = await get_user_tags_with_counts(db_session, test_user.id, include_inactive=True)

    tag_names = {c.name for c in counts}
    assert "active-tag" in tag_names
    assert "orphan-tag" in tag_names

    # Verify orphan tag has count 0
    orphan_count = next(c for c in counts if c.name == "orphan-tag")
    assert orphan_count.content_count == 0


async def test__get_user_tags_with_counts__include_inactive_shows_tags_from_deleted_content(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that include_inactive=True shows tags whose only content is deleted."""
    # Create tag and bookmark, then soft-delete the bookmark
    tag = (await get_or_create_tags(db_session, test_user.id, ["deleted-content-tag"]))[0]
    await db_session.flush()

    bookmark = Bookmark(user_id=test_user.id, url="https://example.com/")
    bookmark.tag_objects = [tag]
    bookmark.deleted_at = datetime.now(UTC)  # Soft delete
    db_session.add(bookmark)
    await db_session.flush()

    # Without include_inactive, tag should not appear
    counts_default = await get_user_tags_with_counts(db_session, test_user.id)
    assert len(counts_default) == 0

    # With include_inactive, tag should appear with count 0
    counts_with_inactive = await get_user_tags_with_counts(
        db_session, test_user.id, include_inactive=True,
    )
    assert len(counts_with_inactive) == 1
    assert counts_with_inactive[0].name == "deleted-content-tag"
    assert counts_with_inactive[0].content_count == 0


async def test__get_user_tags_with_counts__include_inactive_shows_tags_from_archived_content(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that include_inactive=True shows tags whose only content is archived."""
    # Create tag and bookmark, then archive the bookmark
    tag = (await get_or_create_tags(db_session, test_user.id, ["archived-content-tag"]))[0]
    await db_session.flush()

    bookmark = Bookmark(user_id=test_user.id, url="https://example.com/")
    bookmark.tag_objects = [tag]
    bookmark.archived_at = datetime.now(UTC) - timedelta(hours=1)  # Already archived
    db_session.add(bookmark)
    await db_session.flush()

    # Without include_inactive, tag should not appear
    counts_default = await get_user_tags_with_counts(db_session, test_user.id)
    assert len(counts_default) == 0

    # With include_inactive, tag should appear with count 0
    counts_with_inactive = await get_user_tags_with_counts(
        db_session, test_user.id, include_inactive=True,
    )
    assert len(counts_with_inactive) == 1
    assert counts_with_inactive[0].name == "archived-content-tag"
    assert counts_with_inactive[0].content_count == 0


async def test__get_user_tags_with_counts__include_inactive_mixed_active_and_inactive(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test include_inactive with a mix of active and inactive tags."""
    # Create active tag with active bookmark
    active_tag = (await get_or_create_tags(db_session, test_user.id, ["active-tag"]))[0]
    await db_session.flush()

    active_bookmark = Bookmark(user_id=test_user.id, url="https://active.com/")
    active_bookmark.tag_objects = [active_tag]
    db_session.add(active_bookmark)

    # Create inactive tag with deleted bookmark
    inactive_tag = (await get_or_create_tags(db_session, test_user.id, ["inactive-tag"]))[0]
    await db_session.flush()

    deleted_bookmark = Bookmark(user_id=test_user.id, url="https://deleted.com/")
    deleted_bookmark.tag_objects = [inactive_tag]
    deleted_bookmark.deleted_at = datetime.now(UTC)
    db_session.add(deleted_bookmark)

    # Create orphan tag (never associated with any content)
    orphan_tag = Tag(user_id=test_user.id, name="orphan-tag")
    db_session.add(orphan_tag)

    await db_session.flush()

    # Without include_inactive: only active-tag
    counts_default = await get_user_tags_with_counts(db_session, test_user.id)
    assert len(counts_default) == 1
    assert counts_default[0].name == "active-tag"
    assert counts_default[0].content_count == 1

    # With include_inactive: all three tags
    counts_with_inactive = await get_user_tags_with_counts(
        db_session, test_user.id, include_inactive=True,
    )
    assert len(counts_with_inactive) == 3

    tag_counts = {c.name: c.content_count for c in counts_with_inactive}
    assert tag_counts["active-tag"] == 1
    assert tag_counts["inactive-tag"] == 0
    assert tag_counts["orphan-tag"] == 0


async def test__get_user_tags_with_counts__sorted_by_count_then_name(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that results are sorted by count desc, then alphabetically."""
    # Create tags
    tags = await get_or_create_tags(db_session, test_user.id, ["zebra", "apple", "common"])
    await db_session.flush()
    tag_dict = {t.name: t for t in tags}

    # Create bookmarks with various tag combinations
    b1 = Bookmark(user_id=test_user.id, url="https://ex1.com/")
    b1.tag_objects = [tag_dict["zebra"], tag_dict["common"]]

    b2 = Bookmark(user_id=test_user.id, url="https://ex2.com/")
    b2.tag_objects = [tag_dict["apple"], tag_dict["common"]]

    b3 = Bookmark(user_id=test_user.id, url="https://ex3.com/")
    b3.tag_objects = [tag_dict["common"]]

    db_session.add_all([b1, b2, b3])
    await db_session.flush()

    counts = await get_user_tags_with_counts(db_session, test_user.id)

    # common: 3, apple: 1, zebra: 1
    assert counts[0].name == "common"
    assert counts[0].content_count == 3
    # apple and zebra both have count 1, should be alphabetical
    assert counts[1].name == "apple"
    assert counts[2].name == "zebra"


async def test__get_user_tags_with_counts__includes_prompt_tags(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that tag counts include prompts along with bookmarks."""
    # Create a shared tag
    shared_tag = (await get_or_create_tags(db_session, test_user.id, ["shared"]))[0]
    prompt_only_tag = (await get_or_create_tags(db_session, test_user.id, ["prompt-only"]))[0]
    await db_session.flush()

    # Create an active bookmark with the shared tag
    bookmark = Bookmark(user_id=test_user.id, url="https://example.com/")
    bookmark.tag_objects = [shared_tag]
    db_session.add(bookmark)

    # Create an active prompt with both tags
    prompt = Prompt(
        user_id=test_user.id,
        name="test-prompt",
        arguments=[],
    )
    prompt.tag_objects = [shared_tag, prompt_only_tag]
    db_session.add(prompt)
    await db_session.flush()

    # Get counts
    counts = await get_user_tags_with_counts(db_session, test_user.id)

    count_dict = {c.name: c.content_count for c in counts}
    # shared: 2 (1 bookmark + 1 prompt)
    assert count_dict["shared"] == 2
    # prompt-only: 1 (1 prompt)
    assert count_dict["prompt-only"] == 1


async def test__get_user_tags_with_counts__excludes_archived_and_deleted_prompts(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that tag counts exclude archived and deleted prompts."""
    # Create tags
    shared_tag = (await get_or_create_tags(db_session, test_user.id, ["prompt-shared"]))[0]
    await db_session.flush()

    # Create active prompt
    active_prompt = Prompt(
        user_id=test_user.id,
        name="active-prompt",
        arguments=[],
    )
    active_prompt.tag_objects = [shared_tag]

    # Create archived prompt
    archived_prompt = Prompt(
        user_id=test_user.id,
        name="archived-prompt",
        arguments=[],
    )
    archived_prompt.tag_objects = [shared_tag]
    archived_prompt.archived_at = datetime.now(UTC) - timedelta(hours=1)

    # Create deleted prompt
    deleted_prompt = Prompt(
        user_id=test_user.id,
        name="deleted-prompt",
        arguments=[],
    )
    deleted_prompt.tag_objects = [shared_tag]
    deleted_prompt.deleted_at = datetime.now(UTC)

    db_session.add_all([active_prompt, archived_prompt, deleted_prompt])
    await db_session.flush()

    # Get counts - only active prompt should be counted
    counts = await get_user_tags_with_counts(db_session, test_user.id)

    count_dict = {c.name: c.content_count for c in counts}
    # Only the active prompt should count
    assert count_dict["prompt-shared"] == 1


async def test__update_prompt_tags__updates_tags(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that update_prompt_tags correctly updates a prompt's tags."""
    # Create a prompt
    prompt = Prompt(
        user_id=test_user.id,
        name="taggable-prompt",
        arguments=[],
    )
    prompt.tag_objects = []  # Initialize to avoid lazy load on assignment
    db_session.add(prompt)
    await db_session.flush()

    # Re-fetch with eager loading before updating
    result = await db_session.execute(
        select(Prompt)
        .options(selectinload(Prompt.tag_objects))
        .where(Prompt.id == prompt.id),
    )
    prompt = result.scalar_one()

    # Update tags
    await update_prompt_tags(db_session, prompt, ["new-tag-1", "new-tag-2"])
    await db_session.flush()

    # Re-fetch with eager loading to verify
    result = await db_session.execute(
        select(Prompt)
        .options(selectinload(Prompt.tag_objects))
        .where(Prompt.id == prompt.id),
    )
    fetched_prompt = result.scalar_one()

    tag_names = [t.name for t in fetched_prompt.tag_objects]
    assert "new-tag-1" in tag_names
    assert "new-tag-2" in tag_names
    assert len(tag_names) == 2


async def test__update_prompt_tags__clears_tags_with_empty_list(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that update_prompt_tags can clear tags with an empty list."""
    # Create a prompt with tags
    tags = await get_or_create_tags(db_session, test_user.id, ["initial-tag"])
    prompt = Prompt(
        user_id=test_user.id,
        name="prompt-to-clear",
        arguments=[],
    )
    prompt.tag_objects = tags
    db_session.add(prompt)
    await db_session.flush()

    # Verify initial state with eager loading
    result = await db_session.execute(
        select(Prompt)
        .options(selectinload(Prompt.tag_objects))
        .where(Prompt.id == prompt.id),
    )
    fetched_prompt = result.scalar_one()
    assert len(fetched_prompt.tag_objects) == 1

    # Clear tags
    await update_prompt_tags(db_session, fetched_prompt, [])
    await db_session.flush()

    # Re-fetch with eager loading
    result = await db_session.execute(
        select(Prompt)
        .options(selectinload(Prompt.tag_objects))
        .where(Prompt.id == prompt.id),
    )
    fetched_prompt = result.scalar_one()

    assert len(fetched_prompt.tag_objects) == 0


# =============================================================================
# rename_tag Tests
# =============================================================================


async def test__rename_tag__updates_tag_name(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that rename_tag updates the tag name."""
    await get_or_create_tags(db_session, test_user.id, ["old-name"])
    await db_session.flush()

    result = await rename_tag(db_session, test_user.id, "old-name", "new-name")

    assert result.name == "new-name"


async def test__rename_tag__raises_not_found_for_nonexistent_tag(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that rename_tag raises TagNotFoundError for missing tag."""
    with pytest.raises(TagNotFoundError) as exc_info:
        await rename_tag(db_session, test_user.id, "nonexistent", "new-name")

    assert "nonexistent" in str(exc_info.value)


async def test__rename_tag__raises_already_exists_for_conflict(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that rename_tag raises TagAlreadyExistsError when target exists."""
    await get_or_create_tags(db_session, test_user.id, ["tag-a", "tag-b"])
    await db_session.flush()

    with pytest.raises(TagAlreadyExistsError) as exc_info:
        await rename_tag(db_session, test_user.id, "tag-a", "tag-b")

    assert "tag-b" in str(exc_info.value)


async def test__rename_tag__no_op_for_same_name(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that renaming to same name (case-insensitive) is a no-op."""
    tags = await get_or_create_tags(db_session, test_user.id, ["my-tag"])
    await db_session.flush()
    original_id = tags[0].id

    result = await rename_tag(db_session, test_user.id, "my-tag", "MY-TAG")

    assert result.id == original_id
    assert result.name == "my-tag"  # Unchanged


async def test__rename_tag__normalizes_new_name(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that rename_tag normalizes the new name."""
    await get_or_create_tags(db_session, test_user.id, ["old-name"])
    await db_session.flush()

    result = await rename_tag(db_session, test_user.id, "old-name", "  NEW-NAME  ")

    assert result.name == "new-name"


# =============================================================================
# delete_tag Tests
# =============================================================================


async def test__delete_tag__removes_tag(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that delete_tag removes the tag."""
    await get_or_create_tags(db_session, test_user.id, ["to-delete"])
    await db_session.flush()

    await delete_tag(db_session, test_user.id, "to-delete")
    await db_session.flush()

    result = await get_tag_by_name(db_session, test_user.id, "to-delete")
    assert result is None


async def test__delete_tag__raises_not_found_for_nonexistent(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that delete_tag raises TagNotFoundError for missing tag."""
    with pytest.raises(TagNotFoundError) as exc_info:
        await delete_tag(db_session, test_user.id, "nonexistent")

    assert "nonexistent" in str(exc_info.value)


# =============================================================================
# Cascade Delete Tests
# =============================================================================


async def test__user_delete__cascades_to_tags(
    db_session: AsyncSession,
) -> None:
    """Test that deleting a user cascades to delete their tags."""
    user = User(external_auth_id="cascade-tag-user", email="cascade-tags@example.com", tier=Tier.FREE.value)
    db_session.add(user)
    await db_session.flush()

    # Create tags for the user
    tags = await get_or_create_tags(db_session, user.id, ["tag1", "tag2"])
    await db_session.flush()
    tag_ids = [t.id for t in tags]

    # Delete user
    await db_session.delete(user)
    await db_session.flush()

    # Tags should be gone (use raw query to check without user scope)
    result = await db_session.execute(
        select(Tag).where(Tag.id.in_(tag_ids)),
    )
    remaining = result.scalars().all()
    assert len(remaining) == 0


async def test__bookmark_delete__removes_from_junction_but_preserves_tag(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that deleting a bookmark removes junction entries but keeps the tag."""
    # Create tag first
    persist_tag = (await get_or_create_tags(db_session, test_user.id, ["persist-tag"]))[0]
    tag_id = persist_tag.id
    await db_session.flush()

    # Create bookmark with tag set at creation
    bookmark = Bookmark(user_id=test_user.id, url="https://example.com/")
    bookmark.tag_objects = [persist_tag]
    db_session.add(bookmark)
    await db_session.flush()

    # Verify tag exists with count 1
    counts = await get_user_tags_with_counts(db_session, test_user.id)
    assert counts[0].content_count == 1

    # Permanently delete the bookmark
    await db_session.delete(bookmark)
    await db_session.flush()

    # Tag should still exist in database (orphaned)
    result = await db_session.execute(select(Tag).where(Tag.id == tag_id))
    tag = result.scalar_one_or_none()
    assert tag is not None
    assert tag.name == "persist-tag"

    # But it should not appear in get_user_tags_with_counts (zero active content)
    counts = await get_user_tags_with_counts(db_session, test_user.id)
    assert len(counts) == 0
