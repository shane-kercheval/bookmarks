"""
Tests for unified content service layer.

Tests the search_all_content function that combines bookmarks and notes
into a unified list with proper pagination and sorting.
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import User
from schemas.bookmark import BookmarkCreate
from schemas.note import NoteCreate
from services.bookmark_service import BookmarkService
from services.content_service import search_all_content
from services.note_service import NoteService


bookmark_service = BookmarkService()
note_service = NoteService()


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(auth0_id='test-user-content-123', email='test-content@example.com')
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def other_user(db_session: AsyncSession) -> User:
    """Create another test user for isolation tests."""
    user = User(auth0_id='other-user-content-456', email='other-content@example.com')
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


# =============================================================================
# Basic Search Tests
# =============================================================================


async def test__search_all_content__returns_both_bookmarks_and_notes(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that search returns both bookmarks and notes."""
    # Create a bookmark
    bookmark_data = BookmarkCreate(
        url='https://example.com',
        title='Example Bookmark',
    )
    await bookmark_service.create(db_session, test_user.id, bookmark_data)

    # Create a note
    note_data = NoteCreate(title='Example Note')
    await note_service.create(db_session, test_user.id, note_data)

    await db_session.flush()

    # Search all content
    items, total = await search_all_content(db_session, test_user.id)

    assert total == 2
    assert len(items) == 2

    types = {item.type for item in items}
    assert types == {'bookmark', 'note'}


async def test__search_all_content__returns_empty_for_new_user(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that search returns empty for user with no content."""
    items, total = await search_all_content(db_session, test_user.id)

    assert total == 0
    assert items == []


async def test__search_all_content__has_correct_type_discriminator(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that items have correct type field."""
    # Create bookmark and note
    bookmark_data = BookmarkCreate(url='https://test.com', title='Bookmark')
    bookmark = await bookmark_service.create(db_session, test_user.id, bookmark_data)

    note_data = NoteCreate(title='Note')
    note = await note_service.create(db_session, test_user.id, note_data)

    await db_session.flush()

    items, _ = await search_all_content(db_session, test_user.id)

    # Filter by type AND id since bookmarks and notes can have the same ID
    bookmark_item = next(item for item in items if item.type == 'bookmark')
    note_item = next(item for item in items if item.type == 'note')

    assert bookmark_item.type == 'bookmark'
    assert bookmark_item.id == bookmark.id
    assert bookmark_item.url == 'https://test.com/'
    assert bookmark_item.version is None

    assert note_item.type == 'note'
    assert note_item.id == note.id
    assert note_item.url is None
    assert note_item.version == 1


# =============================================================================
# View Filtering Tests
# =============================================================================


async def test__search_all_content__view_active_excludes_deleted(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that view='active' excludes deleted content."""
    # Create content
    bookmark_data = BookmarkCreate(url='https://active.com', title='Active Bookmark')
    active_bookmark = await bookmark_service.create(db_session, test_user.id, bookmark_data)

    note_data = NoteCreate(title='Deleted Note')
    deleted_note = await note_service.create(db_session, test_user.id, note_data)
    await db_session.flush()

    # Delete the note
    await note_service.delete(db_session, test_user.id, deleted_note.id)
    await db_session.flush()

    # Search active
    items, total = await search_all_content(db_session, test_user.id, view='active')

    assert total == 1
    assert items[0].id == active_bookmark.id
    assert items[0].type == 'bookmark'


async def test__search_all_content__view_active_excludes_archived(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that view='active' excludes archived content."""
    # Create content
    bookmark_data = BookmarkCreate(url='https://archived.com', title='Archived Bookmark')
    archived_bookmark = await bookmark_service.create(db_session, test_user.id, bookmark_data)

    note_data = NoteCreate(title='Active Note')
    active_note = await note_service.create(db_session, test_user.id, note_data)
    await db_session.flush()

    # Archive the bookmark
    await bookmark_service.archive(db_session, test_user.id, archived_bookmark.id)
    await db_session.flush()

    # Search active
    items, total = await search_all_content(db_session, test_user.id, view='active')

    assert total == 1
    assert items[0].id == active_note.id
    assert items[0].type == 'note'


async def test__search_all_content__view_archived_returns_only_archived(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that view='archived' returns only archived content."""
    # Create content
    bookmark_data = BookmarkCreate(url='https://archived.com', title='Archived Bookmark')
    archived_bookmark = await bookmark_service.create(db_session, test_user.id, bookmark_data)

    note_data = NoteCreate(title='Archived Note')
    archived_note = await note_service.create(db_session, test_user.id, note_data)

    note_data2 = NoteCreate(title='Active Note')
    await note_service.create(db_session, test_user.id, note_data2)
    await db_session.flush()

    # Archive bookmark and note
    await bookmark_service.archive(db_session, test_user.id, archived_bookmark.id)
    await note_service.archive(db_session, test_user.id, archived_note.id)
    await db_session.flush()

    # Search archived
    items, total = await search_all_content(db_session, test_user.id, view='archived')

    assert total == 2
    types = {item.type for item in items}
    assert types == {'bookmark', 'note'}


async def test__search_all_content__view_deleted_returns_all_deleted(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that view='deleted' returns all deleted content."""
    # Create content
    bookmark_data = BookmarkCreate(url='https://deleted.com', title='Deleted Bookmark')
    deleted_bookmark = await bookmark_service.create(db_session, test_user.id, bookmark_data)

    note_data = NoteCreate(title='Deleted Note')
    deleted_note = await note_service.create(db_session, test_user.id, note_data)

    note_data2 = NoteCreate(title='Active Note')
    await note_service.create(db_session, test_user.id, note_data2)
    await db_session.flush()

    # Delete bookmark and note
    await bookmark_service.delete(db_session, test_user.id, deleted_bookmark.id)
    await note_service.delete(db_session, test_user.id, deleted_note.id)
    await db_session.flush()

    # Search deleted
    items, total = await search_all_content(db_session, test_user.id, view='deleted')

    assert total == 2
    types = {item.type for item in items}
    assert types == {'bookmark', 'note'}


# =============================================================================
# Text Search Tests
# =============================================================================


async def test__search_all_content__text_search_finds_in_title(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that text search finds matches in title."""
    # Create content with different titles
    bookmark_data = BookmarkCreate(url='https://python.com', title='Python Guide')
    await bookmark_service.create(db_session, test_user.id, bookmark_data)

    note_data = NoteCreate(title='JavaScript Tutorial')
    await note_service.create(db_session, test_user.id, note_data)

    await db_session.flush()

    # Search for "python"
    items, total = await search_all_content(db_session, test_user.id, query='python')

    assert total == 1
    assert items[0].title == 'Python Guide'
    assert items[0].type == 'bookmark'


async def test__search_all_content__text_search_finds_in_description(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that text search finds matches in description."""
    # Create content with different descriptions
    bookmark_data = BookmarkCreate(
        url='https://test.com',
        title='Test',
        description='Learn Python basics',
    )
    await bookmark_service.create(db_session, test_user.id, bookmark_data)

    note_data = NoteCreate(title='Note', description='JavaScript advanced')
    await note_service.create(db_session, test_user.id, note_data)

    await db_session.flush()

    # Search for "python"
    items, total = await search_all_content(db_session, test_user.id, query='python')

    assert total == 1
    assert items[0].type == 'bookmark'


async def test__search_all_content__text_search_is_case_insensitive(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that text search is case insensitive."""
    bookmark_data = BookmarkCreate(url='https://test.com', title='PYTHON GUIDE')
    await bookmark_service.create(db_session, test_user.id, bookmark_data)

    await db_session.flush()

    items, total = await search_all_content(db_session, test_user.id, query='python')

    assert total == 1


# =============================================================================
# Tag Filtering Tests
# =============================================================================


async def test__search_all_content__tag_filter_all_mode(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test tag filtering with tag_match='all' (must have ALL tags)."""
    # Create bookmark with both tags
    bookmark_data = BookmarkCreate(
        url='https://both.com',
        title='Both Tags',
        tags=['python', 'web'],
    )
    await bookmark_service.create(db_session, test_user.id, bookmark_data)

    # Create note with only one tag
    note_data = NoteCreate(title='Python Only', tags=['python'])
    await note_service.create(db_session, test_user.id, note_data)

    await db_session.flush()

    # Filter by both tags (ALL mode)
    items, total = await search_all_content(
        db_session, test_user.id, tags=['python', 'web'], tag_match='all',
    )

    assert total == 1
    assert items[0].title == 'Both Tags'


async def test__search_all_content__tag_filter_any_mode(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test tag filtering with tag_match='any' (must have ANY tag)."""
    # Create content with different tags
    bookmark_data = BookmarkCreate(url='https://python.com', title='Python', tags=['python'])
    await bookmark_service.create(db_session, test_user.id, bookmark_data)

    note_data = NoteCreate(title='Web', tags=['web'])
    await note_service.create(db_session, test_user.id, note_data)

    note_data2 = NoteCreate(title='Java', tags=['java'])
    await note_service.create(db_session, test_user.id, note_data2)

    await db_session.flush()

    # Filter by python or web (ANY mode)
    items, total = await search_all_content(
        db_session, test_user.id, tags=['python', 'web'], tag_match='any',
    )

    assert total == 2
    titles = {item.title for item in items}
    assert titles == {'Python', 'Web'}


async def test__search_all_content__includes_tags_in_response(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that tags are included in the response items."""
    bookmark_data = BookmarkCreate(
        url='https://test.com',
        title='Tagged Bookmark',
        tags=['tag-a', 'tag-b'],
    )
    await bookmark_service.create(db_session, test_user.id, bookmark_data)

    note_data = NoteCreate(title='Tagged Note', tags=['tag-c', 'tag-d'])
    await note_service.create(db_session, test_user.id, note_data)

    await db_session.flush()

    items, _ = await search_all_content(db_session, test_user.id)

    bookmark_item = next(item for item in items if item.type == 'bookmark')
    note_item = next(item for item in items if item.type == 'note')

    assert set(bookmark_item.tags) == {'tag-a', 'tag-b'}
    assert set(note_item.tags) == {'tag-c', 'tag-d'}


# =============================================================================
# Sorting Tests
# =============================================================================


async def test__search_all_content__sort_by_created_at_desc(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test sorting by created_at descending (newest first)."""
    import asyncio

    # Create content with delays
    bookmark_data = BookmarkCreate(url='https://first.com', title='First')
    await bookmark_service.create(db_session, test_user.id, bookmark_data)
    await db_session.flush()

    await asyncio.sleep(0.01)

    note_data = NoteCreate(title='Second')
    await note_service.create(db_session, test_user.id, note_data)
    await db_session.flush()

    await asyncio.sleep(0.01)

    bookmark_data2 = BookmarkCreate(url='https://third.com', title='Third')
    await bookmark_service.create(db_session, test_user.id, bookmark_data2)
    await db_session.flush()

    items, _ = await search_all_content(
        db_session, test_user.id, sort_by='created_at', sort_order='desc',
    )

    assert items[0].title == 'Third'
    assert items[1].title == 'Second'
    assert items[2].title == 'First'


async def test__search_all_content__sort_by_title_asc(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test sorting by title ascending (alphabetical)."""
    bookmark_data = BookmarkCreate(url='https://z.com', title='Zebra')
    await bookmark_service.create(db_session, test_user.id, bookmark_data)

    note_data = NoteCreate(title='Apple')
    await note_service.create(db_session, test_user.id, note_data)

    bookmark_data2 = BookmarkCreate(url='https://m.com', title='Mango')
    await bookmark_service.create(db_session, test_user.id, bookmark_data2)

    await db_session.flush()

    items, _ = await search_all_content(
        db_session, test_user.id, sort_by='title', sort_order='asc',
    )

    assert items[0].title == 'Apple'
    assert items[1].title == 'Mango'
    assert items[2].title == 'Zebra'


# =============================================================================
# Pagination Tests
# =============================================================================


async def test__search_all_content__pagination_offset_and_limit(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test pagination with offset and limit."""
    # Create 5 items (mix of bookmarks and notes)
    for i in range(3):
        bookmark_data = BookmarkCreate(url=f'https://test{i}.com', title=f'Bookmark {i}')
        await bookmark_service.create(db_session, test_user.id, bookmark_data)
    for i in range(2):
        note_data = NoteCreate(title=f'Note {i}')
        await note_service.create(db_session, test_user.id, note_data)
    await db_session.flush()

    # Get first page
    items, total = await search_all_content(
        db_session, test_user.id, offset=0, limit=2,
    )

    assert total == 5
    assert len(items) == 2

    # Get second page
    items, total = await search_all_content(
        db_session, test_user.id, offset=2, limit=2,
    )

    assert total == 5
    assert len(items) == 2


async def test__search_all_content__returns_total_before_pagination(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that total count is before pagination is applied."""
    # Create 10 items
    for i in range(5):
        bookmark_data = BookmarkCreate(url=f'https://test{i}.com', title=f'Bookmark {i}')
        await bookmark_service.create(db_session, test_user.id, bookmark_data)
    for i in range(5):
        note_data = NoteCreate(title=f'Note {i}')
        await note_service.create(db_session, test_user.id, note_data)
    await db_session.flush()

    # Get only 3 items
    items, total = await search_all_content(
        db_session, test_user.id, offset=0, limit=3,
    )

    # Total should be 10, not 3
    assert total == 10
    assert len(items) == 3


# =============================================================================
# User Isolation Tests
# =============================================================================


async def test__search_all_content__excludes_other_users_content(
    db_session: AsyncSession,
    test_user: User,
    other_user: User,
) -> None:
    """Test that search only returns the current user's content."""
    # Create content for test_user
    bookmark_data = BookmarkCreate(url='https://mysite.com', title='My Bookmark')
    await bookmark_service.create(db_session, test_user.id, bookmark_data)

    note_data = NoteCreate(title='My Note')
    await note_service.create(db_session, test_user.id, note_data)

    # Create content for other_user
    other_bookmark_data = BookmarkCreate(url='https://other.com', title='Other Bookmark')
    await bookmark_service.create(db_session, other_user.id, other_bookmark_data)

    other_note_data = NoteCreate(title='Other Note')
    await note_service.create(db_session, other_user.id, other_note_data)

    await db_session.flush()

    # Search should only return test_user's content
    items, total = await search_all_content(db_session, test_user.id)

    assert total == 2
    titles = {item.title for item in items}
    assert titles == {'My Bookmark', 'My Note'}


# =============================================================================
# Edge Cases
# =============================================================================


async def test__search_all_content__handles_empty_tags_gracefully(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that empty tags list doesn't filter anything."""
    bookmark_data = BookmarkCreate(url='https://test.com', title='Test')
    await bookmark_service.create(db_session, test_user.id, bookmark_data)
    await db_session.flush()

    items, total = await search_all_content(
        db_session, test_user.id, tags=[],
    )

    assert total == 1


async def test__search_all_content__handles_special_characters_in_query(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that special characters in query are escaped properly."""
    bookmark_data = BookmarkCreate(url='https://test.com', title='100% Complete')
    await bookmark_service.create(db_session, test_user.id, bookmark_data)
    await db_session.flush()

    # Search with % which is a SQL wildcard
    items, total = await search_all_content(
        db_session, test_user.id, query='100%',
    )

    assert total == 1
    assert items[0].title == '100% Complete'


async def test__search_all_content__content_item_fields_are_populated(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that all ContentListItem fields are correctly populated."""
    bookmark_data = BookmarkCreate(
        url='https://test.com',
        title='Full Bookmark',
        description='A description',
        tags=['test'],
    )
    bookmark = await bookmark_service.create(db_session, test_user.id, bookmark_data)

    note_data = NoteCreate(
        title='Full Note',
        description='Note description',
        tags=['note-tag'],
    )
    note = await note_service.create(db_session, test_user.id, note_data)

    await db_session.flush()

    items, _ = await search_all_content(db_session, test_user.id)

    bookmark_item = next(item for item in items if item.type == 'bookmark')
    note_item = next(item for item in items if item.type == 'note')

    # Check bookmark fields
    assert bookmark_item.id == bookmark.id
    assert bookmark_item.title == 'Full Bookmark'
    assert bookmark_item.description == 'A description'
    assert bookmark_item.url == 'https://test.com/'
    assert bookmark_item.version is None
    assert bookmark_item.created_at is not None
    assert bookmark_item.updated_at is not None
    assert bookmark_item.last_used_at is not None
    assert bookmark_item.deleted_at is None
    assert bookmark_item.archived_at is None
    assert 'test' in bookmark_item.tags

    # Check note fields
    assert note_item.id == note.id
    assert note_item.title == 'Full Note'
    assert note_item.description == 'Note description'
    assert note_item.url is None
    assert note_item.version == 1
    assert note_item.created_at is not None
    assert 'note-tag' in note_item.tags
