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
    archive_bookmark,
    create_bookmark,
    delete_bookmark,
    get_bookmark,
    restore_bookmark,
    search_bookmarks,
    unarchive_bookmark,
    update_bookmark,
)


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
