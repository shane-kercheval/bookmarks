"""
Tests for bookmark service layer functionality.

Tests the soft delete, archive, restore, and view filtering functionality
that was added to support the trash/archive features.
"""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.bookmark import Bookmark
from models.user import User
from schemas.bookmark import BookmarkCreate, BookmarkUpdate
from services.bookmark_service import (
    ArchivedUrlExistsError,
    DuplicateUrlError,
    InvalidStateError,
    _check_url_exists,
    archive_bookmark,
    build_filter_from_expression,
    create_bookmark,
    delete_bookmark,
    escape_ilike,
    get_bookmark,
    restore_bookmark,
    search_bookmarks,
    unarchive_bookmark,
    update_bookmark,
)
from datetime import UTC


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(auth0_id='test-user-123', email='test@example.com')
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_bookmark(db_session: AsyncSession, test_user: User) -> Bookmark:
    """Create a test bookmark."""
    bookmark = Bookmark(
        user_id=test_user.id,
        url='https://example.com/',
        title='Example',
        description='An example site',
    )
    db_session.add(bookmark)
    await db_session.flush()
    await db_session.refresh(bookmark)
    return bookmark


# =============================================================================
# Soft Delete Tests
# =============================================================================


async def test__delete_bookmark__soft_delete_sets_deleted_at(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that soft delete sets deleted_at timestamp instead of removing."""
    bookmark_id = test_bookmark.id

    result = await delete_bookmark(db_session, test_user.id, bookmark_id)

    assert result is True

    # Verify bookmark still exists in DB with deleted_at set
    query = select(Bookmark).where(Bookmark.id == bookmark_id)
    db_result = await db_session.execute(query)
    bookmark = db_result.scalar_one()
    assert bookmark.deleted_at is not None


async def test__delete_bookmark__soft_delete_hides_from_get(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that soft-deleted bookmark is hidden from get_bookmark by default."""
    bookmark_id = test_bookmark.id
    await delete_bookmark(db_session, test_user.id, bookmark_id)

    # Should not find the deleted bookmark
    result = await get_bookmark(db_session, test_user.id, bookmark_id)
    assert result is None


async def test__delete_bookmark__soft_delete_visible_with_include_deleted(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that soft-deleted bookmark is visible with include_deleted=True."""
    bookmark_id = test_bookmark.id
    await delete_bookmark(db_session, test_user.id, bookmark_id)

    result = await get_bookmark(
        db_session, test_user.id, bookmark_id, include_deleted=True,
    )
    assert result is not None
    assert result.deleted_at is not None


async def test__delete_bookmark__permanent_removes_from_db(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that permanent delete removes bookmark from database."""
    bookmark_id = test_bookmark.id

    # First soft-delete it (simulating it being in trash)
    await delete_bookmark(db_session, test_user.id, bookmark_id)
    await db_session.flush()

    # Then permanently delete
    result = await delete_bookmark(
        db_session, test_user.id, bookmark_id, permanent=True,
    )

    assert result is True

    # Verify bookmark is completely gone
    query = select(Bookmark).where(Bookmark.id == bookmark_id)
    db_result = await db_session.execute(query)
    assert db_result.scalar_one_or_none() is None


async def test__delete_bookmark__soft_delete_archived_bookmark(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that soft-deleting an archived bookmark sets deleted_at."""
    bookmark_id = test_bookmark.id

    # Archive first
    await archive_bookmark(db_session, test_user.id, bookmark_id)
    await db_session.flush()

    # Then soft-delete
    result = await delete_bookmark(db_session, test_user.id, bookmark_id)

    assert result is True

    # Verify both timestamps are set
    query = select(Bookmark).where(Bookmark.id == bookmark_id)
    db_result = await db_session.execute(query)
    bookmark = db_result.scalar_one()
    assert bookmark.deleted_at is not None
    assert bookmark.archived_at is not None


# =============================================================================
# View Filtering Tests
# =============================================================================


async def test__search_bookmarks__view_active_excludes_deleted(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that view='active' excludes deleted bookmarks."""
    # Create two bookmarks
    b1 = Bookmark(user_id=test_user.id, url='https://active.com/')
    b2 = Bookmark(user_id=test_user.id, url='https://deleted.com/')
    db_session.add_all([b1, b2])
    await db_session.flush()

    # Delete one
    await delete_bookmark(db_session, test_user.id, b2.id)
    await db_session.flush()

    # Search should only return active
    bookmarks, total = await search_bookmarks(
        db_session, test_user.id, view='active',
    )

    assert total == 1
    assert len(bookmarks) == 1
    assert bookmarks[0].url == 'https://active.com/'


async def test__search_bookmarks__view_active_excludes_archived(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that view='active' excludes archived bookmarks."""
    b1 = Bookmark(user_id=test_user.id, url='https://active.com/')
    b2 = Bookmark(user_id=test_user.id, url='https://archived.com/')
    db_session.add_all([b1, b2])
    await db_session.flush()

    await archive_bookmark(db_session, test_user.id, b2.id)
    await db_session.flush()

    bookmarks, total = await search_bookmarks(
        db_session, test_user.id, view='active',
    )

    assert total == 1
    assert bookmarks[0].url == 'https://active.com/'


async def test__search_bookmarks__view_archived_returns_only_archived(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that view='archived' returns only archived (not deleted) bookmarks."""
    b1 = Bookmark(user_id=test_user.id, url='https://active.com/')
    b2 = Bookmark(user_id=test_user.id, url='https://archived.com/')
    b3 = Bookmark(user_id=test_user.id, url='https://deleted.com/')
    db_session.add_all([b1, b2, b3])
    await db_session.flush()

    await archive_bookmark(db_session, test_user.id, b2.id)
    await delete_bookmark(db_session, test_user.id, b3.id)
    await db_session.flush()

    bookmarks, total = await search_bookmarks(
        db_session, test_user.id, view='archived',
    )

    assert total == 1
    assert bookmarks[0].url == 'https://archived.com/'


async def test__search_bookmarks__view_deleted_returns_all_deleted(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that view='deleted' returns all deleted bookmarks including deleted+archived."""
    b1 = Bookmark(user_id=test_user.id, url='https://active.com/')
    b2 = Bookmark(user_id=test_user.id, url='https://deleted.com/')
    b3 = Bookmark(user_id=test_user.id, url='https://deleted-archived.com/')
    db_session.add_all([b1, b2, b3])
    await db_session.flush()

    await delete_bookmark(db_session, test_user.id, b2.id)
    await archive_bookmark(db_session, test_user.id, b3.id)
    await delete_bookmark(db_session, test_user.id, b3.id)
    await db_session.flush()

    bookmarks, total = await search_bookmarks(
        db_session, test_user.id, view='deleted',
    )

    assert total == 2
    urls = {b.url for b in bookmarks}
    assert 'https://deleted.com/' in urls
    assert 'https://deleted-archived.com/' in urls


async def test__search_bookmarks__view_with_query_filter(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that search query works with view filtering."""
    b1 = Bookmark(
        user_id=test_user.id, url='https://example.com/', title='Python Guide',
    )
    b2 = Bookmark(
        user_id=test_user.id, url='https://archived.com/', title='Python Tutorial',
    )
    db_session.add_all([b1, b2])
    await db_session.flush()

    await archive_bookmark(db_session, test_user.id, b2.id)
    await db_session.flush()

    # Search for "Python" in archived view
    bookmarks, total = await search_bookmarks(
        db_session, test_user.id, query='Python', view='archived',
    )

    assert total == 1
    assert bookmarks[0].title == 'Python Tutorial'


# =============================================================================
# Restore Tests
# =============================================================================


async def test__restore_bookmark__clears_deleted_at(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that restore clears deleted_at timestamp."""
    bookmark_id = test_bookmark.id

    await delete_bookmark(db_session, test_user.id, bookmark_id)
    await db_session.flush()

    restored = await restore_bookmark(db_session, test_user.id, bookmark_id)

    assert restored is not None
    assert restored.deleted_at is None


async def test__restore_bookmark__clears_both_timestamps(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that restoring deleted+archived bookmark clears BOTH timestamps."""
    bookmark_id = test_bookmark.id

    await archive_bookmark(db_session, test_user.id, bookmark_id)
    await delete_bookmark(db_session, test_user.id, bookmark_id)
    await db_session.flush()

    restored = await restore_bookmark(db_session, test_user.id, bookmark_id)

    assert restored is not None
    assert restored.deleted_at is None
    assert restored.archived_at is None


async def test__restore_bookmark__appears_in_active_list(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that restored bookmark appears in active list."""
    bookmark_id = test_bookmark.id

    await delete_bookmark(db_session, test_user.id, bookmark_id)
    await db_session.flush()

    await restore_bookmark(db_session, test_user.id, bookmark_id)
    await db_session.flush()

    bookmarks, total = await search_bookmarks(
        db_session, test_user.id, view='active',
    )

    assert total == 1
    assert bookmarks[0].id == bookmark_id


async def test__restore_bookmark__returns_none_for_nonexistent(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that restore returns None for non-existent bookmark."""
    result = await restore_bookmark(db_session, test_user.id, 99999)
    assert result is None


async def test__restore_bookmark__raises_error_if_not_deleted(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that restoring a non-deleted bookmark raises InvalidStateError."""
    with pytest.raises(InvalidStateError) as exc_info:
        await restore_bookmark(db_session, test_user.id, test_bookmark.id)

    assert "not deleted" in str(exc_info.value)


async def test__restore_bookmark__raises_error_on_url_conflict(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that restore fails if URL already exists as active bookmark."""
    # Create and delete a bookmark
    b1 = Bookmark(user_id=test_user.id, url='https://duplicate.com/')
    db_session.add(b1)
    await db_session.flush()

    await delete_bookmark(db_session, test_user.id, b1.id)
    await db_session.flush()

    # Create another bookmark with same URL
    b2 = Bookmark(user_id=test_user.id, url='https://duplicate.com/')
    db_session.add(b2)
    await db_session.flush()

    # Try to restore the deleted one
    with pytest.raises(DuplicateUrlError):
        await restore_bookmark(db_session, test_user.id, b1.id)


async def test__restore_bookmark__raises_error_when_url_exists_as_archived(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that restore fails if URL already exists as archived bookmark."""
    # Create and delete a bookmark
    b1 = Bookmark(user_id=test_user.id, url='https://archived-conflict.com/')
    db_session.add(b1)
    await db_session.flush()

    await delete_bookmark(db_session, test_user.id, b1.id)
    await db_session.flush()

    # Create another bookmark with same URL and archive it
    b2 = Bookmark(user_id=test_user.id, url='https://archived-conflict.com/')
    db_session.add(b2)
    await db_session.flush()

    await archive_bookmark(db_session, test_user.id, b2.id)
    await db_session.flush()

    # Try to restore the deleted one - should fail because archived bookmark exists
    with pytest.raises(DuplicateUrlError):
        await restore_bookmark(db_session, test_user.id, b1.id)


# =============================================================================
# Archive Tests
# =============================================================================


async def test__archive_bookmark__sets_archived_at(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that archive sets archived_at timestamp."""
    bookmark_id = test_bookmark.id

    archived = await archive_bookmark(db_session, test_user.id, bookmark_id)

    assert archived is not None
    assert archived.archived_at is not None


async def test__archive_bookmark__is_idempotent(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that archiving an already-archived bookmark is idempotent."""
    bookmark_id = test_bookmark.id

    await archive_bookmark(db_session, test_user.id, bookmark_id)
    await db_session.flush()

    # Archive again - should succeed
    archived = await archive_bookmark(db_session, test_user.id, bookmark_id)

    assert archived is not None
    assert archived.archived_at is not None


async def test__archive_bookmark__hides_from_active_list(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that archived bookmark is hidden from active list."""
    bookmark_id = test_bookmark.id

    await archive_bookmark(db_session, test_user.id, bookmark_id)
    await db_session.flush()

    bookmarks, total = await search_bookmarks(
        db_session, test_user.id, view='active',
    )

    assert total == 0


async def test__archive_bookmark__returns_none_for_nonexistent(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that archive returns None for non-existent bookmark."""
    result = await archive_bookmark(db_session, test_user.id, 99999)
    assert result is None


# =============================================================================
# Unarchive Tests
# =============================================================================


async def test__unarchive_bookmark__clears_archived_at(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that unarchive clears archived_at timestamp."""
    bookmark_id = test_bookmark.id

    await archive_bookmark(db_session, test_user.id, bookmark_id)
    await db_session.flush()

    unarchived = await unarchive_bookmark(db_session, test_user.id, bookmark_id)

    assert unarchived is not None
    assert unarchived.archived_at is None


async def test__unarchive_bookmark__appears_in_active_list(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that unarchived bookmark appears in active list."""
    bookmark_id = test_bookmark.id

    await archive_bookmark(db_session, test_user.id, bookmark_id)
    await db_session.flush()

    await unarchive_bookmark(db_session, test_user.id, bookmark_id)
    await db_session.flush()

    bookmarks, total = await search_bookmarks(
        db_session, test_user.id, view='active',
    )

    assert total == 1
    assert bookmarks[0].id == bookmark_id


async def test__unarchive_bookmark__returns_none_for_nonexistent(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that unarchive returns None for non-existent bookmark."""
    result = await unarchive_bookmark(db_session, test_user.id, 99999)
    assert result is None


async def test__unarchive_bookmark__raises_error_for_non_archived(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that unarchiving a non-archived bookmark raises InvalidStateError."""
    with pytest.raises(InvalidStateError) as exc_info:
        await unarchive_bookmark(db_session, test_user.id, test_bookmark.id)

    assert "not archived" in str(exc_info.value)


# =============================================================================
# URL Uniqueness Edge Cases
# =============================================================================


async def test__create_bookmark__succeeds_when_url_exists_as_soft_deleted(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that creating bookmark succeeds when same URL exists only as soft-deleted."""
    # Create and delete a bookmark
    data = BookmarkCreate(url='https://reusable.com/')  # type: ignore[call-arg]
    first = await create_bookmark(db_session, test_user.id, data)
    await db_session.flush()

    await delete_bookmark(db_session, test_user.id, first.id)
    await db_session.flush()

    # Should be able to create new bookmark with same URL
    data2 = BookmarkCreate(url='https://reusable.com/')  # type: ignore[call-arg]
    second = await create_bookmark(db_session, test_user.id, data2)

    assert second is not None
    assert second.id != first.id
    assert second.url == 'https://reusable.com/'


async def test__create_bookmark__fails_when_url_exists_as_archived(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that creating bookmark fails when same URL exists as archived."""
    # Create and archive a bookmark
    data = BookmarkCreate(url='https://archived.com/')  # type: ignore[call-arg]
    first = await create_bookmark(db_session, test_user.id, data)
    await db_session.flush()

    await archive_bookmark(db_session, test_user.id, first.id)
    await db_session.flush()

    # Should fail with ArchivedUrlExistsError
    data2 = BookmarkCreate(url='https://archived.com/')  # type: ignore[call-arg]
    with pytest.raises(ArchivedUrlExistsError) as exc_info:
        await create_bookmark(db_session, test_user.id, data2)

    assert exc_info.value.existing_bookmark_id == first.id


async def test__create_bookmark__fails_when_url_exists_as_active(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that creating bookmark fails when same URL exists as active."""
    data = BookmarkCreate(url='https://active.com/')  # type: ignore[call-arg]
    await create_bookmark(db_session, test_user.id, data)
    await db_session.flush()

    data2 = BookmarkCreate(url='https://active.com/')  # type: ignore[call-arg]
    with pytest.raises(DuplicateUrlError):
        await create_bookmark(db_session, test_user.id, data2)


# =============================================================================
# get_bookmark Include Flags Tests
# =============================================================================


async def test__get_bookmark__excludes_archived_by_default(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that get_bookmark excludes archived bookmarks by default."""
    bookmark_id = test_bookmark.id

    await archive_bookmark(db_session, test_user.id, bookmark_id)
    await db_session.flush()

    result = await get_bookmark(db_session, test_user.id, bookmark_id)
    assert result is None


async def test__get_bookmark__includes_archived_when_requested(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that get_bookmark includes archived when include_archived=True."""
    bookmark_id = test_bookmark.id

    await archive_bookmark(db_session, test_user.id, bookmark_id)
    await db_session.flush()

    result = await get_bookmark(
        db_session, test_user.id, bookmark_id, include_archived=True,
    )
    assert result is not None
    assert result.archived_at is not None


# =============================================================================
# Track Usage Tests
# =============================================================================


async def test__track_bookmark_usage__updates_last_used_at(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that track_bookmark_usage updates the last_used_at timestamp."""
    import asyncio

    from services.bookmark_service import track_bookmark_usage

    original_last_used = test_bookmark.last_used_at

    # Small delay to ensure different timestamp
    await asyncio.sleep(0.01)

    result = await track_bookmark_usage(db_session, test_user.id, test_bookmark.id)
    await db_session.flush()
    await db_session.refresh(test_bookmark)

    assert result is True
    assert test_bookmark.last_used_at > original_last_used


async def test__track_bookmark_usage__returns_false_for_nonexistent(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that track_bookmark_usage returns False for non-existent bookmark."""
    from services.bookmark_service import track_bookmark_usage

    result = await track_bookmark_usage(db_session, test_user.id, 99999)
    assert result is False


async def test__track_bookmark_usage__works_on_archived_bookmark(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that track_bookmark_usage works on archived bookmarks."""
    import asyncio

    from services.bookmark_service import track_bookmark_usage

    await archive_bookmark(db_session, test_user.id, test_bookmark.id)
    await db_session.flush()

    original_last_used = test_bookmark.last_used_at

    # Small delay to ensure different timestamp
    await asyncio.sleep(0.01)

    result = await track_bookmark_usage(db_session, test_user.id, test_bookmark.id)
    await db_session.flush()
    await db_session.refresh(test_bookmark)

    assert result is True
    assert test_bookmark.last_used_at > original_last_used


async def test__track_bookmark_usage__works_on_deleted_bookmark(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that track_bookmark_usage works on soft-deleted bookmarks."""
    import asyncio

    from services.bookmark_service import track_bookmark_usage

    await delete_bookmark(db_session, test_user.id, test_bookmark.id)
    await db_session.flush()

    original_last_used = test_bookmark.last_used_at

    # Small delay to ensure different timestamp
    await asyncio.sleep(0.01)

    result = await track_bookmark_usage(db_session, test_user.id, test_bookmark.id)
    await db_session.flush()
    await db_session.refresh(test_bookmark)

    assert result is True
    assert test_bookmark.last_used_at > original_last_used


async def test__track_bookmark_usage__does_not_update_updated_at(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that track_bookmark_usage does NOT update updated_at."""
    import asyncio

    from services.bookmark_service import track_bookmark_usage

    original_updated_at = test_bookmark.updated_at

    # Small delay to ensure different timestamp if it were to change
    await asyncio.sleep(0.01)

    result = await track_bookmark_usage(db_session, test_user.id, test_bookmark.id)
    await db_session.flush()
    await db_session.refresh(test_bookmark)

    assert result is True
    # updated_at should remain unchanged
    assert test_bookmark.updated_at == original_updated_at


# =============================================================================
# Create Bookmark - last_used_at Tests
# =============================================================================


async def test__create_bookmark__last_used_at_equals_created_at(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that new bookmarks have last_used_at exactly equal to created_at."""
    data = BookmarkCreate(url='https://new-bookmark.com/')  # type: ignore[call-arg]
    bookmark = await create_bookmark(db_session, test_user.id, data)

    assert bookmark.last_used_at == bookmark.created_at


# =============================================================================
# Sort by last_used_at and updated_at Tests
# =============================================================================


async def test__search_bookmarks__sort_by_last_used_at_desc(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test sorting by last_used_at descending (most recently used first)."""
    import asyncio

    from services.bookmark_service import track_bookmark_usage

    # Create bookmarks
    data1 = BookmarkCreate(url='https://first.com/')  # type: ignore[call-arg]
    b1 = await create_bookmark(db_session, test_user.id, data1)
    await db_session.flush()

    await asyncio.sleep(0.01)  # Small delay to ensure different timestamps

    data2 = BookmarkCreate(url='https://second.com/')  # type: ignore[call-arg]
    b2 = await create_bookmark(db_session, test_user.id, data2)
    await db_session.flush()

    await asyncio.sleep(0.01)  # Small delay before tracking usage

    # Track usage on first bookmark (makes it most recently used)
    await track_bookmark_usage(db_session, test_user.id, b1.id)
    await db_session.flush()

    bookmarks, total = await search_bookmarks(
        db_session, test_user.id, sort_by='last_used_at', sort_order='desc',
    )

    assert total == 2
    assert bookmarks[0].id == b1.id  # Most recently used
    assert bookmarks[1].id == b2.id


async def test__search_bookmarks__sort_by_last_used_at_asc(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test sorting by last_used_at ascending (least recently used first)."""
    import asyncio

    from services.bookmark_service import track_bookmark_usage

    # Create bookmarks
    data1 = BookmarkCreate(url='https://first.com/')  # type: ignore[call-arg]
    b1 = await create_bookmark(db_session, test_user.id, data1)
    await db_session.flush()

    await asyncio.sleep(0.01)

    data2 = BookmarkCreate(url='https://second.com/')  # type: ignore[call-arg]
    b2 = await create_bookmark(db_session, test_user.id, data2)
    await db_session.flush()

    await asyncio.sleep(0.01)  # Small delay before tracking usage

    # Track usage on first bookmark
    await track_bookmark_usage(db_session, test_user.id, b1.id)
    await db_session.flush()

    bookmarks, total = await search_bookmarks(
        db_session, test_user.id, sort_by='last_used_at', sort_order='asc',
    )

    assert total == 2
    assert bookmarks[0].id == b2.id  # Least recently used
    assert bookmarks[1].id == b1.id


async def test__search_bookmarks__sort_by_updated_at_desc(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test sorting by updated_at descending (most recently modified first)."""
    import asyncio

    # Create bookmarks
    data1 = BookmarkCreate(url='https://first.com/')  # type: ignore[call-arg]
    b1 = await create_bookmark(db_session, test_user.id, data1)
    await db_session.flush()

    await asyncio.sleep(0.01)

    data2 = BookmarkCreate(url='https://second.com/')  # type: ignore[call-arg]
    b2 = await create_bookmark(db_session, test_user.id, data2)
    await db_session.flush()

    await asyncio.sleep(0.01)  # Small delay before updating

    # Update first bookmark via service (makes it most recently modified)
    await update_bookmark(
        db_session, test_user.id, b1.id, BookmarkUpdate(title='Updated Title'),
    )
    await db_session.flush()

    bookmarks, total = await search_bookmarks(
        db_session, test_user.id, sort_by='updated_at', sort_order='desc',
    )

    assert total == 2
    assert bookmarks[0].id == b1.id  # Most recently modified
    assert bookmarks[1].id == b2.id


async def test__search_bookmarks__sort_by_updated_at_asc(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test sorting by updated_at ascending (least recently modified first)."""
    import asyncio

    # Create bookmarks
    data1 = BookmarkCreate(url='https://first.com/')  # type: ignore[call-arg]
    b1 = await create_bookmark(db_session, test_user.id, data1)
    await db_session.flush()

    await asyncio.sleep(0.01)

    data2 = BookmarkCreate(url='https://second.com/')  # type: ignore[call-arg]
    b2 = await create_bookmark(db_session, test_user.id, data2)
    await db_session.flush()

    await asyncio.sleep(0.01)  # Small delay before updating

    # Update first bookmark via service
    await update_bookmark(
        db_session, test_user.id, b1.id, BookmarkUpdate(title='Updated Title'),
    )
    await db_session.flush()

    bookmarks, total = await search_bookmarks(
        db_session, test_user.id, sort_by='updated_at', sort_order='asc',
    )

    assert total == 2
    assert bookmarks[0].id == b2.id  # Least recently modified
    assert bookmarks[1].id == b1.id


async def test__search_bookmarks__sort_by_archived_at_desc(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test sorting by archived_at descending (most recently archived first)."""
    import asyncio

    # Create bookmarks and archive them at different times
    data1 = BookmarkCreate(url='https://archived-first.com/')  # type: ignore[call-arg]
    b1 = await create_bookmark(db_session, test_user.id, data1)
    await db_session.flush()

    await asyncio.sleep(0.01)

    data2 = BookmarkCreate(url='https://archived-second.com/')  # type: ignore[call-arg]
    b2 = await create_bookmark(db_session, test_user.id, data2)
    await db_session.flush()

    # Archive first bookmark
    await archive_bookmark(db_session, test_user.id, b1.id)
    await db_session.flush()

    await asyncio.sleep(0.01)

    # Archive second bookmark (more recent)
    await archive_bookmark(db_session, test_user.id, b2.id)
    await db_session.flush()

    # Search archived bookmarks, sorted by archived_at desc
    bookmarks, total = await search_bookmarks(
        db_session, test_user.id,
        view='archived',
        sort_by='archived_at',
        sort_order='desc',
    )

    assert total == 2
    assert bookmarks[0].id == b2.id  # Most recently archived
    assert bookmarks[1].id == b1.id


async def test__search_bookmarks__sort_by_archived_at_asc(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test sorting by archived_at ascending (least recently archived first)."""
    import asyncio

    # Create bookmarks and archive them at different times
    data1 = BookmarkCreate(url='https://archived-asc-first.com/')  # type: ignore[call-arg]
    b1 = await create_bookmark(db_session, test_user.id, data1)
    await db_session.flush()

    await asyncio.sleep(0.01)

    data2 = BookmarkCreate(url='https://archived-asc-second.com/')  # type: ignore[call-arg]
    b2 = await create_bookmark(db_session, test_user.id, data2)
    await db_session.flush()

    # Archive first bookmark
    await archive_bookmark(db_session, test_user.id, b1.id)
    await db_session.flush()

    await asyncio.sleep(0.01)

    # Archive second bookmark (more recent)
    await archive_bookmark(db_session, test_user.id, b2.id)
    await db_session.flush()

    # Search archived bookmarks, sorted by archived_at asc
    bookmarks, total = await search_bookmarks(
        db_session, test_user.id,
        view='archived',
        sort_by='archived_at',
        sort_order='asc',
    )

    assert total == 2
    assert bookmarks[0].id == b1.id  # Least recently archived
    assert bookmarks[1].id == b2.id


async def test__search_bookmarks__sort_by_deleted_at_desc(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test sorting by deleted_at descending (most recently deleted first)."""
    import asyncio

    # Create bookmarks and soft-delete them at different times
    data1 = BookmarkCreate(url='https://deleted-first.com/')  # type: ignore[call-arg]
    b1 = await create_bookmark(db_session, test_user.id, data1)
    await db_session.flush()

    await asyncio.sleep(0.01)

    data2 = BookmarkCreate(url='https://deleted-second.com/')  # type: ignore[call-arg]
    b2 = await create_bookmark(db_session, test_user.id, data2)
    await db_session.flush()

    # Soft-delete first bookmark
    await delete_bookmark(db_session, test_user.id, b1.id)
    await db_session.flush()

    await asyncio.sleep(0.01)

    # Soft-delete second bookmark (more recent)
    await delete_bookmark(db_session, test_user.id, b2.id)
    await db_session.flush()

    # Search deleted bookmarks, sorted by deleted_at desc
    bookmarks, total = await search_bookmarks(
        db_session, test_user.id,
        view='deleted',
        sort_by='deleted_at',
        sort_order='desc',
    )

    assert total == 2
    assert bookmarks[0].id == b2.id  # Most recently deleted
    assert bookmarks[1].id == b1.id


async def test__search_bookmarks__sort_by_deleted_at_asc(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test sorting by deleted_at ascending (least recently deleted first)."""
    import asyncio

    # Create bookmarks and soft-delete them at different times
    data1 = BookmarkCreate(url='https://deleted-asc-first.com/')  # type: ignore[call-arg]
    b1 = await create_bookmark(db_session, test_user.id, data1)
    await db_session.flush()

    await asyncio.sleep(0.01)

    data2 = BookmarkCreate(url='https://deleted-asc-second.com/')  # type: ignore[call-arg]
    b2 = await create_bookmark(db_session, test_user.id, data2)
    await db_session.flush()

    # Soft-delete first bookmark
    await delete_bookmark(db_session, test_user.id, b1.id)
    await db_session.flush()

    await asyncio.sleep(0.01)

    # Soft-delete second bookmark (more recent)
    await delete_bookmark(db_session, test_user.id, b2.id)
    await db_session.flush()

    # Search deleted bookmarks, sorted by deleted_at asc
    bookmarks, total = await search_bookmarks(
        db_session, test_user.id,
        view='deleted',
        sort_by='deleted_at',
        sort_order='asc',
    )

    assert total == 2
    assert bookmarks[0].id == b1.id  # Least recently deleted
    assert bookmarks[1].id == b2.id


# =============================================================================
# Filter Expression Tests (for BookmarkList filtering)
# =============================================================================


async def test__search_bookmarks__filter_expression_single_group_and(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test filter expression with single group (AND logic)."""
    # Create bookmarks with different tag combinations
    data1 = BookmarkCreate(
        url='https://work-priority.com/',
        tags=['work', 'priority'],
    )  # type: ignore[call-arg]
    b1 = await create_bookmark(db_session, test_user.id, data1)

    data2 = BookmarkCreate(
        url='https://work-only.com/',
        tags=['work'],
    )  # type: ignore[call-arg]
    await create_bookmark(db_session, test_user.id, data2)

    data3 = BookmarkCreate(
        url='https://priority-only.com/',
        tags=['priority'],
    )  # type: ignore[call-arg]
    await create_bookmark(db_session, test_user.id, data3)

    await db_session.flush()

    # Filter: must have BOTH work AND priority
    filter_expression = {
        'groups': [{'tags': ['work', 'priority'], 'operator': 'AND'}],
        'group_operator': 'OR',
    }

    bookmarks, total = await search_bookmarks(
        db_session, test_user.id, filter_expression=filter_expression,
    )

    assert total == 1
    assert bookmarks[0].id == b1.id


async def test__search_bookmarks__filter_expression_multiple_groups_or(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test filter expression with multiple groups (OR logic between groups)."""
    # Create bookmarks
    data1 = BookmarkCreate(
        url='https://work-priority.com/',
        tags=['work', 'priority'],
    )  # type: ignore[call-arg]
    b1 = await create_bookmark(db_session, test_user.id, data1)

    data2 = BookmarkCreate(
        url='https://urgent.com/',
        tags=['urgent'],
    )  # type: ignore[call-arg]
    b2 = await create_bookmark(db_session, test_user.id, data2)

    data3 = BookmarkCreate(
        url='https://personal.com/',
        tags=['personal'],
    )  # type: ignore[call-arg]
    await create_bookmark(db_session, test_user.id, data3)

    await db_session.flush()

    # Filter: (work AND priority) OR (urgent)
    filter_expression = {
        'groups': [
            {'tags': ['work', 'priority'], 'operator': 'AND'},
            {'tags': ['urgent'], 'operator': 'AND'},
        ],
        'group_operator': 'OR',
    }

    bookmarks, total = await search_bookmarks(
        db_session, test_user.id, filter_expression=filter_expression,
    )

    assert total == 2
    ids = [b.id for b in bookmarks]
    assert b1.id in ids
    assert b2.id in ids


async def test__search_bookmarks__filter_expression_complex(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test complex filter expression: (work AND high-priority) OR (urgent) OR (critical AND deadline)."""
    # Create bookmarks
    data1 = BookmarkCreate(
        url='https://work-high-priority.com/',
        tags=['work', 'high-priority'],
    )  # type: ignore[call-arg]
    b1 = await create_bookmark(db_session, test_user.id, data1)

    data2 = BookmarkCreate(
        url='https://urgent.com/',
        tags=['urgent'],
    )  # type: ignore[call-arg]
    b2 = await create_bookmark(db_session, test_user.id, data2)

    data3 = BookmarkCreate(
        url='https://critical-deadline.com/',
        tags=['critical', 'deadline'],
    )  # type: ignore[call-arg]
    b3 = await create_bookmark(db_session, test_user.id, data3)

    data4 = BookmarkCreate(
        url='https://work-only.com/',
        tags=['work'],
    )  # type: ignore[call-arg]
    await create_bookmark(db_session, test_user.id, data4)

    data5 = BookmarkCreate(
        url='https://critical-only.com/',
        tags=['critical'],
    )  # type: ignore[call-arg]
    await create_bookmark(db_session, test_user.id, data5)

    await db_session.flush()

    filter_expression = {
        'groups': [
            {'tags': ['work', 'high-priority'], 'operator': 'AND'},
            {'tags': ['urgent'], 'operator': 'AND'},
            {'tags': ['critical', 'deadline'], 'operator': 'AND'},
        ],
        'group_operator': 'OR',
    }

    bookmarks, total = await search_bookmarks(
        db_session, test_user.id, filter_expression=filter_expression,
    )

    assert total == 3
    ids = [b.id for b in bookmarks]
    assert b1.id in ids
    assert b2.id in ids
    assert b3.id in ids


async def test__search_bookmarks__filter_expression_no_matches(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test filter expression with no matching bookmarks."""
    data = BookmarkCreate(
        url='https://example.com/',
        tags=['something'],
    )  # type: ignore[call-arg]
    await create_bookmark(db_session, test_user.id, data)
    await db_session.flush()

    filter_expression = {
        'groups': [{'tags': ['nonexistent-tag'], 'operator': 'AND'}],
        'group_operator': 'OR',
    }

    bookmarks, total = await search_bookmarks(
        db_session, test_user.id, filter_expression=filter_expression,
    )

    assert total == 0
    assert bookmarks == []


async def test__search_bookmarks__filter_expression_with_text_search(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test filter expression combined with text search."""
    data1 = BookmarkCreate(
        url='https://python-work.com/',
        title='Python Guide',
        tags=['work', 'coding'],
    )  # type: ignore[call-arg]
    b1 = await create_bookmark(db_session, test_user.id, data1)

    data2 = BookmarkCreate(
        url='https://javascript-work.com/',
        title='JavaScript Guide',
        tags=['work', 'coding'],
    )  # type: ignore[call-arg]
    await create_bookmark(db_session, test_user.id, data2)

    await db_session.flush()

    # Filter by tags AND text search
    filter_expression = {
        'groups': [{'tags': ['work', 'coding'], 'operator': 'AND'}],
        'group_operator': 'OR',
    }

    bookmarks, total = await search_bookmarks(
        db_session, test_user.id, query='python', filter_expression=filter_expression,
    )

    assert total == 1
    assert bookmarks[0].id == b1.id


async def test__search_bookmarks__filter_expression_combines_with_tags(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that filter_expression and tags parameter are combined with AND logic."""
    # Bookmark with work tag only
    data1 = BookmarkCreate(
        url='https://work.com/',
        tags=['work'],
    )  # type: ignore[call-arg]
    await create_bookmark(db_session, test_user.id, data1)

    # Bookmark with both work and urgent tags
    data2 = BookmarkCreate(
        url='https://work-urgent.com/',
        tags=['work', 'urgent'],
    )  # type: ignore[call-arg]
    b2 = await create_bookmark(db_session, test_user.id, data2)

    # Bookmark with personal tag only
    data3 = BookmarkCreate(
        url='https://personal.com/',
        tags=['personal'],
    )  # type: ignore[call-arg]
    await create_bookmark(db_session, test_user.id, data3)

    await db_session.flush()

    # List filter matches 'work' tags, additional tag filter for 'urgent'
    # Should only return bookmarks matching BOTH conditions
    filter_expression = {
        'groups': [{'tags': ['work'], 'operator': 'AND'}],
        'group_operator': 'OR',
    }

    bookmarks, total = await search_bookmarks(
        db_session,
        test_user.id,
        tags=['urgent'],  # Additional filter - must ALSO have this tag
        filter_expression=filter_expression,
    )

    # Only b2 has both 'work' (from filter_expression) AND 'urgent' (from tags)
    assert total == 1
    assert bookmarks[0].id == b2.id


# =============================================================================
# Update Bookmark Tests
# =============================================================================


async def test__update_bookmark__updates_title(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that update_bookmark updates the title."""
    bookmark_id = test_bookmark.id

    updated = await update_bookmark(
        db_session, test_user.id, bookmark_id, BookmarkUpdate(title='New Title'),
    )

    assert updated is not None
    assert updated.title == 'New Title'


async def test__update_bookmark__updates_description(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that update_bookmark updates the description."""
    bookmark_id = test_bookmark.id

    updated = await update_bookmark(
        db_session, test_user.id, bookmark_id,
        BookmarkUpdate(description='New description'),
    )

    assert updated is not None
    assert updated.description == 'New description'


async def test__update_bookmark__partial_update_preserves_other_fields(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that partial update only changes specified fields."""
    bookmark_id = test_bookmark.id
    original_title = test_bookmark.title
    original_url = test_bookmark.url

    updated = await update_bookmark(
        db_session, test_user.id, bookmark_id,
        BookmarkUpdate(description='Only description changed'),
    )

    assert updated is not None
    assert updated.description == 'Only description changed'
    assert updated.title == original_title
    assert updated.url == original_url


async def test__update_bookmark__updates_tags(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that update_bookmark updates tags."""
    data = BookmarkCreate(
        url='https://tag-update-test.com/',
        tags=['original-tag'],
    )  # type: ignore[call-arg]
    bookmark = await create_bookmark(db_session, test_user.id, data)
    await db_session.flush()

    updated = await update_bookmark(
        db_session, test_user.id, bookmark.id,
        BookmarkUpdate(tags=['new-tag-1', 'new-tag-2']),
    )

    assert updated is not None
    tag_names = [t.name for t in updated.tag_objects]
    assert 'new-tag-1' in tag_names
    assert 'new-tag-2' in tag_names
    assert 'original-tag' not in tag_names


async def test__update_bookmark__updates_url_to_unique_url(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that update_bookmark can update URL to a new unique URL."""
    bookmark_id = test_bookmark.id

    updated = await update_bookmark(
        db_session, test_user.id, bookmark_id,
        BookmarkUpdate(url='https://new-unique-url.com/'),  # type: ignore[arg-type]
    )

    assert updated is not None
    assert updated.url == 'https://new-unique-url.com/'


async def test__update_bookmark__url_to_duplicate_raises_error(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that updating URL to an existing URL raises DuplicateUrlError."""
    # Create two bookmarks
    data1 = BookmarkCreate(url='https://existing-url.com/')  # type: ignore[call-arg]
    await create_bookmark(db_session, test_user.id, data1)
    await db_session.flush()

    data2 = BookmarkCreate(url='https://will-change.com/')  # type: ignore[call-arg]
    bookmark2 = await create_bookmark(db_session, test_user.id, data2)
    await db_session.flush()

    # Try to update second bookmark to have same URL as first
    with pytest.raises(DuplicateUrlError):
        await update_bookmark(
            db_session, test_user.id, bookmark2.id,
            BookmarkUpdate(url='https://existing-url.com/'),  # type: ignore[arg-type]
        )


async def test__update_bookmark__url_to_same_url_succeeds(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that updating URL to the same URL succeeds (no-op)."""
    bookmark_id = test_bookmark.id
    original_url = test_bookmark.url

    updated = await update_bookmark(
        db_session, test_user.id, bookmark_id,
        BookmarkUpdate(url=original_url),  # type: ignore[arg-type]
    )

    assert updated is not None
    assert updated.url == original_url


async def test__update_bookmark__returns_none_for_nonexistent(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that update_bookmark returns None for non-existent bookmark."""
    result = await update_bookmark(
        db_session, test_user.id, 99999,
        BookmarkUpdate(title='Will not work'),
    )
    assert result is None


async def test__update_bookmark__updates_updated_at(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that update_bookmark updates the updated_at timestamp."""
    import asyncio

    bookmark_id = test_bookmark.id
    original_updated_at = test_bookmark.updated_at

    await asyncio.sleep(0.01)

    await update_bookmark(
        db_session, test_user.id, bookmark_id,
        BookmarkUpdate(title='Updated Title'),
    )
    await db_session.flush()
    await db_session.refresh(test_bookmark)

    assert test_bookmark.updated_at > original_updated_at


async def test__update_bookmark__does_not_update_last_used_at(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that update_bookmark does NOT update last_used_at."""
    import asyncio

    bookmark_id = test_bookmark.id
    original_last_used_at = test_bookmark.last_used_at

    await asyncio.sleep(0.01)

    await update_bookmark(
        db_session, test_user.id, bookmark_id,
        BookmarkUpdate(title='Updated Title'),
    )
    await db_session.flush()
    await db_session.refresh(test_bookmark)

    assert test_bookmark.last_used_at == original_last_used_at


async def test__update_bookmark__updates_content(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that update_bookmark updates the content field."""
    bookmark_id = test_bookmark.id

    updated = await update_bookmark(
        db_session, test_user.id, bookmark_id,
        BookmarkUpdate(content='New page content for searching'),
    )

    assert updated is not None
    assert updated.content == 'New page content for searching'


async def test__update_bookmark__wrong_user_returns_none(
    db_session: AsyncSession,
    test_bookmark: Bookmark,
) -> None:
    """Test that update_bookmark returns None for wrong user."""
    # Create another user
    other_user = User(auth0_id='other-user-456', email='other@example.com')
    db_session.add(other_user)
    await db_session.flush()

    # Try to update test_user's bookmark as other_user
    result = await update_bookmark(
        db_session, other_user.id, test_bookmark.id,
        BookmarkUpdate(title='Hacked Title'),
    )

    assert result is None

    # Verify original bookmark unchanged
    await db_session.refresh(test_bookmark)
    assert test_bookmark.title == 'Example'


async def test__update_bookmark__can_update_archived_bookmark(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """
    Test that update_bookmark can update an already-archived bookmark.

    This is important because the UI shows an edit button in the archived view,
    so users expect to be able to edit archived bookmark metadata.
    """
    # Archive the bookmark
    await archive_bookmark(db_session, test_user.id, test_bookmark.id)
    await db_session.flush()
    await db_session.refresh(test_bookmark)

    # Verify it's archived
    assert test_bookmark.is_archived is True

    # Try to update the archived bookmark's title
    updated = await update_bookmark(
        db_session, test_user.id, test_bookmark.id,
        BookmarkUpdate(title='Updated Archived Title'),
    )

    # Should succeed - archived bookmarks should be editable
    assert updated is not None
    assert updated.title == 'Updated Archived Title'


# =============================================================================
# escape_ilike Tests
# =============================================================================


def test__escape_ilike__escapes_percent() -> None:
    """Test that escape_ilike escapes percent character."""
    result = escape_ilike('100% complete')
    assert result == '100\\% complete'


def test__escape_ilike__escapes_underscore() -> None:
    """Test that escape_ilike escapes underscore character."""
    result = escape_ilike('snake_case')
    assert result == 'snake\\_case'


def test__escape_ilike__escapes_backslash() -> None:
    """Test that escape_ilike escapes backslash character."""
    result = escape_ilike('path\\to\\file')
    assert result == 'path\\\\to\\\\file'


def test__escape_ilike__escapes_all_special_chars() -> None:
    """Test that escape_ilike escapes all special characters together."""
    result = escape_ilike('100%_test\\path')
    assert result == '100\\%\\_test\\\\path'


def test__escape_ilike__no_special_chars_unchanged() -> None:
    """Test that escape_ilike returns unchanged string with no special chars."""
    result = escape_ilike('normal search term')
    assert result == 'normal search term'


def test__escape_ilike__empty_string() -> None:
    """Test that escape_ilike handles empty string."""
    result = escape_ilike('')
    assert result == ''


def test__escape_ilike__only_special_chars() -> None:
    """Test that escape_ilike handles string with only special chars."""
    result = escape_ilike('%_\\')
    assert result == '\\%\\_\\\\'


# =============================================================================
# build_filter_from_expression Tests
# =============================================================================


def test__build_filter_from_expression__empty_groups_returns_empty() -> None:
    """Test that empty groups returns empty filter list."""
    filter_expression = {'groups': [], 'group_operator': 'OR'}
    result = build_filter_from_expression(filter_expression, user_id=1)
    assert result == []


def test__build_filter_from_expression__missing_groups_returns_empty() -> None:
    """Test that missing groups key returns empty filter list."""
    filter_expression = {'group_operator': 'OR'}
    result = build_filter_from_expression(filter_expression, user_id=1)
    assert result == []


def test__build_filter_from_expression__single_group_single_tag() -> None:
    """Test filter with single group containing single tag."""
    filter_expression = {
        'groups': [{'tags': ['python'], 'operator': 'AND'}],
        'group_operator': 'OR',
    }
    result = build_filter_from_expression(filter_expression, user_id=1)
    assert len(result) == 1
    # Result should be an EXISTS clause (can't easily inspect, but should be truthy)
    assert result[0] is not None


def test__build_filter_from_expression__single_group_multiple_tags() -> None:
    """Test filter with single group containing multiple tags (AND)."""
    filter_expression = {
        'groups': [{'tags': ['python', 'web'], 'operator': 'AND'}],
        'group_operator': 'OR',
    }
    result = build_filter_from_expression(filter_expression, user_id=1)
    assert len(result) == 1
    # Result should be an AND clause combining EXISTS for each tag
    assert result[0] is not None


def test__build_filter_from_expression__multiple_groups() -> None:
    """Test filter with multiple groups (OR between groups)."""
    filter_expression = {
        'groups': [
            {'tags': ['python'], 'operator': 'AND'},
            {'tags': ['javascript'], 'operator': 'AND'},
        ],
        'group_operator': 'OR',
    }
    result = build_filter_from_expression(filter_expression, user_id=1)
    assert len(result) == 1
    # Result should be an OR clause combining the two groups
    assert result[0] is not None


def test__build_filter_from_expression__group_with_empty_tags_skipped() -> None:
    """Test that groups with empty tags are skipped."""
    filter_expression = {
        'groups': [
            {'tags': [], 'operator': 'AND'},
            {'tags': ['python'], 'operator': 'AND'},
        ],
        'group_operator': 'OR',
    }
    result = build_filter_from_expression(filter_expression, user_id=1)
    # Should only have one condition (from the python tag group)
    assert len(result) == 1


def test__build_filter_from_expression__all_groups_empty_returns_empty() -> None:
    """Test that if all groups have empty tags, empty list is returned."""
    filter_expression = {
        'groups': [
            {'tags': [], 'operator': 'AND'},
            {'tags': [], 'operator': 'AND'},
        ],
        'group_operator': 'OR',
    }
    result = build_filter_from_expression(filter_expression, user_id=1)
    assert result == []


# =============================================================================
# _check_url_exists Tests
# =============================================================================


async def test__check_url_exists__returns_bookmark_when_active(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that _check_url_exists returns bookmark when URL exists as active."""
    result = await _check_url_exists(db_session, test_user.id, test_bookmark.url)

    assert result is not None
    assert result.id == test_bookmark.id


async def test__check_url_exists__returns_bookmark_when_archived(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that _check_url_exists returns bookmark when URL exists as archived."""
    await archive_bookmark(db_session, test_user.id, test_bookmark.id)
    await db_session.flush()

    result = await _check_url_exists(db_session, test_user.id, test_bookmark.url)

    assert result is not None
    assert result.id == test_bookmark.id
    assert result.archived_at is not None


async def test__check_url_exists__returns_none_when_soft_deleted(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that _check_url_exists returns None when URL exists only as soft-deleted."""
    await delete_bookmark(db_session, test_user.id, test_bookmark.id)
    await db_session.flush()

    result = await _check_url_exists(db_session, test_user.id, test_bookmark.url)

    assert result is None


async def test__check_url_exists__returns_none_when_not_exists(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that _check_url_exists returns None when URL doesn't exist."""
    result = await _check_url_exists(
        db_session, test_user.id, 'https://nonexistent.com/',
    )

    assert result is None


async def test__check_url_exists__scoped_to_user(
    db_session: AsyncSession,
    test_bookmark: Bookmark,
) -> None:
    """Test that _check_url_exists only finds URLs for the given user."""
    # Create another user
    other_user = User(auth0_id='other-user-check', email='other-check@example.com')
    db_session.add(other_user)
    await db_session.flush()

    # Check for test_user's URL as other_user - should not find it
    result = await _check_url_exists(db_session, other_user.id, test_bookmark.url)

    assert result is None


# =============================================================================
# is_archived Hybrid Property Tests
# =============================================================================


async def test__is_archived__returns_false_when_archived_at_is_none(
    db_session: AsyncSession,  # noqa: ARG001
    test_user: User,  # noqa: ARG001
    test_bookmark: Bookmark,
) -> None:
    """Test that is_archived returns False when archived_at is None."""
    assert test_bookmark.archived_at is None
    assert test_bookmark.is_archived is False


async def test__is_archived__returns_true_when_archived_at_is_past(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that is_archived returns True when archived_at is in the past."""
    await archive_bookmark(db_session, test_user.id, test_bookmark.id)
    await db_session.flush()
    await db_session.refresh(test_bookmark)

    assert test_bookmark.archived_at is not None
    assert test_bookmark.is_archived is True


async def test__is_archived__returns_false_when_archived_at_is_future(
    db_session: AsyncSession,
    test_user: User,  # noqa: ARG001
    test_bookmark: Bookmark,
) -> None:
    """Test that is_archived returns False when archived_at is in the future (scheduled)."""
    from datetime import datetime, timedelta

    # Set archived_at to 1 day in the future
    future_time = datetime.now(UTC) + timedelta(days=1)
    test_bookmark.archived_at = future_time
    await db_session.flush()
    await db_session.refresh(test_bookmark)

    assert test_bookmark.archived_at is not None
    assert test_bookmark.is_archived is False


async def test__is_archived__sql_expression_filters_past_archived(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that is_archived SQL expression correctly filters archived bookmarks."""
    from sqlalchemy import select

    # Create bookmarks: active, archived (past), scheduled (future)
    active = Bookmark(user_id=test_user.id, url='https://active.com/')
    past_archived = Bookmark(user_id=test_user.id, url='https://past-archived.com/')
    future_scheduled = Bookmark(user_id=test_user.id, url='https://future-scheduled.com/')

    db_session.add_all([active, past_archived, future_scheduled])
    await db_session.flush()

    # Archive one bookmark (sets to now/past)
    await archive_bookmark(db_session, test_user.id, past_archived.id)
    await db_session.flush()

    # Set future archive date on another
    from datetime import datetime, timedelta

    future_time = datetime.now(UTC) + timedelta(days=7)
    future_scheduled.archived_at = future_time
    await db_session.flush()

    # Query for archived bookmarks using the hybrid property
    result = await db_session.execute(
        select(Bookmark).where(
            Bookmark.user_id == test_user.id,
            Bookmark.is_archived,
        ),
    )
    archived_bookmarks = list(result.scalars().all())

    # Only past_archived should be returned
    assert len(archived_bookmarks) == 1
    assert archived_bookmarks[0].url == 'https://past-archived.com/'


async def test__is_archived__sql_expression_filters_not_archived(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that ~is_archived returns active AND future-scheduled bookmarks."""
    from sqlalchemy import select

    # Create bookmarks: active, archived (past), scheduled (future)
    active = Bookmark(user_id=test_user.id, url='https://active.com/')
    past_archived = Bookmark(user_id=test_user.id, url='https://past-archived.com/')
    future_scheduled = Bookmark(user_id=test_user.id, url='https://future-scheduled.com/')

    db_session.add_all([active, past_archived, future_scheduled])
    await db_session.flush()

    # Archive one bookmark (sets to now/past)
    await archive_bookmark(db_session, test_user.id, past_archived.id)
    await db_session.flush()

    # Set future archive date on another
    from datetime import datetime, timedelta

    future_time = datetime.now(UTC) + timedelta(days=7)
    future_scheduled.archived_at = future_time
    await db_session.flush()

    # Query for non-archived bookmarks using the hybrid property with NOT operator
    result = await db_session.execute(
        select(Bookmark).where(
            Bookmark.user_id == test_user.id,
            ~Bookmark.is_archived,
        ),
    )
    not_archived_bookmarks = list(result.scalars().all())

    # Both active and future_scheduled should be returned
    assert len(not_archived_bookmarks) == 2
    urls = {b.url for b in not_archived_bookmarks}
    assert 'https://active.com/' in urls
    assert 'https://future-scheduled.com/' in urls
    assert 'https://past-archived.com/' not in urls


# =============================================================================
# Auto-Archive (Future-Dated archived_at) Tests
# =============================================================================


async def test__search_bookmarks__future_scheduled_appears_in_active_view(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that bookmarks with future archived_at appear in active view."""
    from datetime import datetime, timedelta

    # Create a bookmark with future archived_at
    bookmark = Bookmark(user_id=test_user.id, url='https://future-scheduled.com/')
    bookmark.archived_at = datetime.now(UTC) + timedelta(days=7)
    db_session.add(bookmark)
    await db_session.flush()

    # Search active view
    bookmarks, total = await search_bookmarks(db_session, test_user.id, view='active')

    assert total == 1
    assert bookmarks[0].url == 'https://future-scheduled.com/'


async def test__search_bookmarks__future_scheduled_not_in_archived_view(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that bookmarks with future archived_at do NOT appear in archived view."""
    from datetime import datetime, timedelta

    # Create a bookmark with future archived_at
    bookmark = Bookmark(user_id=test_user.id, url='https://future-scheduled.com/')
    bookmark.archived_at = datetime.now(UTC) + timedelta(days=7)
    db_session.add(bookmark)
    await db_session.flush()

    # Search archived view
    bookmarks, total = await search_bookmarks(db_session, test_user.id, view='archived')

    assert total == 0
    assert bookmarks == []


async def test__archive_bookmark__overrides_future_scheduled_date(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that archive_bookmark on future-scheduled bookmark sets to now."""
    from datetime import datetime, timedelta

    # Create a bookmark with future archived_at
    bookmark = Bookmark(user_id=test_user.id, url='https://future-scheduled.com/')
    future_date = datetime.now(UTC) + timedelta(days=7)
    bookmark.archived_at = future_date
    db_session.add(bookmark)
    await db_session.flush()

    # Archive it (should set to now, overriding the future date)
    archived = await archive_bookmark(db_session, test_user.id, bookmark.id)
    await db_session.flush()
    await db_session.refresh(archived)

    # Should now be archived (is_archived == True)
    assert archived.is_archived is True
    # archived_at should be different from the future date
    assert archived.archived_at < future_date


async def test__unarchive_bookmark__fails_on_future_scheduled(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that unarchive_bookmark fails on future-scheduled bookmark."""
    from datetime import datetime, timedelta

    # Create a bookmark with future archived_at
    bookmark = Bookmark(user_id=test_user.id, url='https://future-scheduled.com/')
    bookmark.archived_at = datetime.now(UTC) + timedelta(days=7)
    db_session.add(bookmark)
    await db_session.flush()

    # Try to unarchive - should raise InvalidStateError because it's not archived yet
    with pytest.raises(InvalidStateError) as exc_info:
        await unarchive_bookmark(db_session, test_user.id, bookmark.id)

    assert "not archived" in str(exc_info.value)


async def test__create_bookmark__future_scheduled_url_raises_duplicate_not_archived_error(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that creating bookmark when URL exists as future-scheduled raises DuplicateUrlError."""
    from datetime import datetime, timedelta

    # Create a bookmark with future archived_at
    bookmark = Bookmark(user_id=test_user.id, url='https://future-scheduled.com/')
    bookmark.archived_at = datetime.now(UTC) + timedelta(days=7)
    db_session.add(bookmark)
    await db_session.flush()

    # Try to create another bookmark with same URL
    # Since it's scheduled but not yet archived, should raise DuplicateUrlError (not ArchivedUrlExistsError)
    data = BookmarkCreate(url='https://future-scheduled.com/')  # type: ignore[call-arg]
    with pytest.raises(DuplicateUrlError):
        await create_bookmark(db_session, test_user.id, data)


async def test__get_bookmark__future_scheduled_visible_by_default(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that get_bookmark returns future-scheduled bookmark by default."""
    from datetime import datetime, timedelta

    # Create a bookmark with future archived_at
    bookmark = Bookmark(user_id=test_user.id, url='https://future-scheduled.com/')
    bookmark.archived_at = datetime.now(UTC) + timedelta(days=7)
    db_session.add(bookmark)
    await db_session.flush()

    # get_bookmark without include_archived should still return it
    # because it's not currently archived (archived_at is in the future)
    result = await get_bookmark(db_session, test_user.id, bookmark.id)

    assert result is not None
    assert result.url == 'https://future-scheduled.com/'


async def test__create_bookmark__with_archived_at_future_date(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that create_bookmark accepts archived_at for scheduling."""
    from datetime import datetime, timedelta

    future_date = datetime.now(UTC) + timedelta(days=7)
    data = BookmarkCreate(
        url='https://scheduled.com/',  # type: ignore[call-arg]
        archived_at=future_date,
    )
    bookmark = await create_bookmark(db_session, test_user.id, data)

    assert bookmark.archived_at is not None
    assert bookmark.is_archived is False  # Not yet archived
    # Should appear in active view
    bookmarks, total = await search_bookmarks(db_session, test_user.id, view='active')
    assert total == 1


async def test__create_bookmark__with_archived_at_past_date(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that create_bookmark with past archived_at creates immediately archived bookmark."""
    from datetime import datetime, timedelta

    past_date = datetime.now(UTC) - timedelta(hours=1)
    data = BookmarkCreate(
        url='https://immediately-archived.com/',  # type: ignore[call-arg]
        archived_at=past_date,
    )
    bookmark = await create_bookmark(db_session, test_user.id, data)

    assert bookmark.archived_at is not None
    assert bookmark.is_archived is True  # Already archived
    # Should appear in archived view
    bookmarks, total = await search_bookmarks(db_session, test_user.id, view='archived')
    assert total == 1


async def test__update_bookmark__can_set_archived_at(
    db_session: AsyncSession,
    test_user: User,
    test_bookmark: Bookmark,
) -> None:
    """Test that update_bookmark can set archived_at for scheduling."""
    from datetime import datetime, timedelta

    future_date = datetime.now(UTC) + timedelta(days=7)
    updated = await update_bookmark(
        db_session, test_user.id, test_bookmark.id,
        BookmarkUpdate(archived_at=future_date),
    )

    assert updated is not None
    assert updated.archived_at is not None
    assert updated.is_archived is False  # Not yet archived


async def test__update_bookmark__can_clear_archived_at(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that update_bookmark can clear archived_at to cancel schedule."""
    from datetime import datetime, timedelta

    # Create a bookmark with future archived_at
    future_date = datetime.now(UTC) + timedelta(days=7)
    data = BookmarkCreate(
        url='https://scheduled-then-cleared.com/',  # type: ignore[call-arg]
        archived_at=future_date,
    )
    bookmark = await create_bookmark(db_session, test_user.id, data)
    await db_session.flush()

    # Clear the scheduled date
    updated = await update_bookmark(
        db_session, test_user.id, bookmark.id,
        BookmarkUpdate(archived_at=None),
    )

    assert updated is not None
    assert updated.archived_at is None
    assert updated.is_archived is False
