"""
Tests for unified content service layer.

Tests the search_all_content function that combines bookmarks, notes, and prompts
into a unified list with proper pagination and sorting.
"""
import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.tier_limits import Tier, get_tier_limits
from models.user import User
from schemas.bookmark import BookmarkCreate
from schemas.note import NoteCreate
from schemas.prompt import PromptCreate
from services.bookmark_service import BookmarkService
from services.content_service import search_all_content
from services.note_service import NoteService
from services.prompt_service import PromptService


bookmark_service = BookmarkService()
note_service = NoteService()
prompt_service = PromptService()
DEFAULT_LIMITS = get_tier_limits(Tier.DEV)


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(external_auth_id='test-user-content-123', email='test-content@example.com', tier=Tier.FREE.value)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def other_user(db_session: AsyncSession) -> User:
    """Create another test user for isolation tests."""
    user = User(external_auth_id='other-user-content-456', email='other-content@example.com', tier=Tier.FREE.value)
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
    await bookmark_service.create(db_session, test_user.id, bookmark_data, DEFAULT_LIMITS)

    # Create a note
    note_data = NoteCreate(title='Example Note')
    await note_service.create(db_session, test_user.id, note_data, DEFAULT_LIMITS)

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
    bookmark = await bookmark_service.create(db_session, test_user.id, bookmark_data, DEFAULT_LIMITS)

    note_data = NoteCreate(title='Note')
    note = await note_service.create(db_session, test_user.id, note_data, DEFAULT_LIMITS)

    await db_session.flush()

    items, _ = await search_all_content(db_session, test_user.id)

    # Filter by type AND id since bookmarks and notes can have the same ID
    bookmark_item = next(item for item in items if item.type == 'bookmark')
    note_item = next(item for item in items if item.type == 'note')

    assert bookmark_item.type == 'bookmark'
    assert bookmark_item.id == bookmark.id
    assert bookmark_item.url == 'https://test.com/'

    assert note_item.type == 'note'
    assert note_item.id == note.id
    assert note_item.url is None


# =============================================================================
# View Filtering Tests
# =============================================================================


async def test__search_all_content__view_active_excludes_deleted(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that view={'active'} excludes deleted content."""
    # Create content
    bookmark_data = BookmarkCreate(url='https://active.com', title='Active Bookmark')
    active_bookmark = await bookmark_service.create(db_session, test_user.id, bookmark_data, DEFAULT_LIMITS)

    note_data = NoteCreate(title='Deleted Note')
    deleted_note = await note_service.create(db_session, test_user.id, note_data, DEFAULT_LIMITS)
    await db_session.flush()

    # Delete the note
    await note_service.delete(db_session, test_user.id, deleted_note.id)
    await db_session.flush()

    # Search active
    items, total = await search_all_content(db_session, test_user.id, view={'active'})

    assert total == 1
    assert items[0].id == active_bookmark.id
    assert items[0].type == 'bookmark'


async def test__search_all_content__view_active_excludes_archived(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that view={'active'} excludes archived content."""
    # Create content
    bookmark_data = BookmarkCreate(url='https://archived.com', title='Archived Bookmark')
    archived_bookmark = await bookmark_service.create(db_session, test_user.id, bookmark_data, DEFAULT_LIMITS)

    note_data = NoteCreate(title='Active Note')
    active_note = await note_service.create(db_session, test_user.id, note_data, DEFAULT_LIMITS)
    await db_session.flush()

    # Archive the bookmark
    await bookmark_service.archive(db_session, test_user.id, archived_bookmark.id)
    await db_session.flush()

    # Search active
    items, total = await search_all_content(db_session, test_user.id, view={'active'})

    assert total == 1
    assert items[0].id == active_note.id
    assert items[0].type == 'note'


async def test__search_all_content__view_archived_returns_only_archived(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that view={'archived'} returns only archived content."""
    # Create content
    bookmark_data = BookmarkCreate(url='https://archived.com', title='Archived Bookmark')
    archived_bookmark = await bookmark_service.create(db_session, test_user.id, bookmark_data, DEFAULT_LIMITS)

    note_data = NoteCreate(title='Archived Note')
    archived_note = await note_service.create(db_session, test_user.id, note_data, DEFAULT_LIMITS)

    note_data2 = NoteCreate(title='Active Note')
    await note_service.create(db_session, test_user.id, note_data2, DEFAULT_LIMITS)
    await db_session.flush()

    # Archive bookmark and note
    await bookmark_service.archive(db_session, test_user.id, archived_bookmark.id)
    await note_service.archive(db_session, test_user.id, archived_note.id)
    await db_session.flush()

    # Search archived
    items, total = await search_all_content(db_session, test_user.id, view={'archived'})

    assert total == 2
    types = {item.type for item in items}
    assert types == {'bookmark', 'note'}


async def test__search_all_content__view_deleted_returns_all_deleted(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that view={'deleted'} returns all deleted content."""
    # Create content
    bookmark_data = BookmarkCreate(url='https://deleted.com', title='Deleted Bookmark')
    deleted_bookmark = await bookmark_service.create(db_session, test_user.id, bookmark_data, DEFAULT_LIMITS)

    note_data = NoteCreate(title='Deleted Note')
    deleted_note = await note_service.create(db_session, test_user.id, note_data, DEFAULT_LIMITS)

    note_data2 = NoteCreate(title='Active Note')
    await note_service.create(db_session, test_user.id, note_data2, DEFAULT_LIMITS)
    await db_session.flush()

    # Delete bookmark and note
    await bookmark_service.delete(db_session, test_user.id, deleted_bookmark.id)
    await note_service.delete(db_session, test_user.id, deleted_note.id)
    await db_session.flush()

    # Search deleted
    items, total = await search_all_content(db_session, test_user.id, view={'deleted'})

    assert total == 2
    types = {item.type for item in items}
    assert types == {'bookmark', 'note'}


# =============================================================================
# Multi-Value View Tests
# =============================================================================


async def test__search_all_content__view_active_archived_returns_both(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that view={'active', 'archived'} returns both, excludes deleted."""
    bookmark_data = BookmarkCreate(url='https://active.com', title='Active Bookmark')
    active_bm = await bookmark_service.create(db_session, test_user.id, bookmark_data, DEFAULT_LIMITS)

    note_data = NoteCreate(title='Archived Note')
    archived_note = await note_service.create(db_session, test_user.id, note_data, DEFAULT_LIMITS)
    await db_session.flush()
    await note_service.archive(db_session, test_user.id, archived_note.id)

    deleted_data = NoteCreate(title='Deleted Note')
    deleted_note = await note_service.create(db_session, test_user.id, deleted_data, DEFAULT_LIMITS)
    await db_session.flush()
    await note_service.delete(db_session, test_user.id, deleted_note.id)
    await db_session.flush()

    items, total = await search_all_content(
        db_session, test_user.id, view={'active', 'archived'},
    )

    assert total == 2
    ids = {item.id for item in items}
    assert ids == {active_bm.id, archived_note.id}


async def test__search_all_content__view_active_archived_excludes_deleted(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that view={'active', 'archived'} excludes soft-deleted items."""
    note_data = NoteCreate(title='Active Note')
    active_note = await note_service.create(db_session, test_user.id, note_data, DEFAULT_LIMITS)

    deleted_data = BookmarkCreate(url='https://del.com', title='Deleted BM')
    deleted_bm = await bookmark_service.create(db_session, test_user.id, deleted_data, DEFAULT_LIMITS)
    await db_session.flush()
    await bookmark_service.delete(db_session, test_user.id, deleted_bm.id)
    await db_session.flush()

    items, total = await search_all_content(
        db_session, test_user.id, view={'active', 'archived'},
    )

    assert total == 1
    assert items[0].id == active_note.id


async def test__search_all_content__view_active_archived_relevance_penalty(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Active items rank higher than archived with same content when both views included."""
    # Create two bookmarks with identical titles for equal raw relevance
    active_data = BookmarkCreate(url='https://a.com', title='Python Tutorial Guide')
    active_bm = await bookmark_service.create(db_session, test_user.id, active_data, DEFAULT_LIMITS)

    archived_data = BookmarkCreate(url='https://b.com', title='Python Tutorial Guide')
    archived_bm = await bookmark_service.create(db_session, test_user.id, archived_data, DEFAULT_LIMITS)
    await db_session.flush()
    await bookmark_service.archive(db_session, test_user.id, archived_bm.id)
    await db_session.flush()

    items, total = await search_all_content(
        db_session, test_user.id,
        query='Python Tutorial',
        view={'active', 'archived'},
        sort_by='relevance',
    )

    assert total == 2
    assert items[0].id == active_bm.id
    assert items[1].id == archived_bm.id


async def test__search_all_content__view_active_archived_relevance_penalty_ignores_future_scheduled(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Future-scheduled archive items get no penalty (treated as active)."""
    now = datetime.now(UTC)

    # Active item
    active_data = BookmarkCreate(url='https://a.com', title='Unique Test Keyword')
    active_bm = await bookmark_service.create(db_session, test_user.id, active_data, DEFAULT_LIMITS)

    # Future-scheduled archive (archived_at in the future = still active per is_archived)
    future_data = BookmarkCreate(
        url='https://b.com', title='Unique Test Keyword',
        archived_at=now + timedelta(days=30),
    )
    future_bm = await bookmark_service.create(db_session, test_user.id, future_data, DEFAULT_LIMITS)

    # Past-archived item
    past_data = BookmarkCreate(url='https://c.com', title='Unique Test Keyword')
    past_bm = await bookmark_service.create(db_session, test_user.id, past_data, DEFAULT_LIMITS)
    await db_session.flush()
    await bookmark_service.archive(db_session, test_user.id, past_bm.id)
    await db_session.flush()

    items, total = await search_all_content(
        db_session, test_user.id,
        query='Unique Test Keyword',
        view={'active', 'archived'},
        sort_by='relevance',
    )

    assert total == 3
    # Active and future-scheduled should rank above past-archived
    top_two_ids = {items[0].id, items[1].id}
    assert active_bm.id in top_two_ids
    assert future_bm.id in top_two_ids
    assert items[2].id == past_bm.id


async def test__search_all_content__view_active_archived_no_penalty_on_non_relevance_sort(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """No penalty applied when sort_by is not relevance."""
    active_data = BookmarkCreate(url='https://a.com', title='Sort Test')
    await bookmark_service.create(db_session, test_user.id, active_data, DEFAULT_LIMITS)

    archived_data = BookmarkCreate(url='https://b.com', title='Sort Test')
    archived_bm = await bookmark_service.create(db_session, test_user.id, archived_data, DEFAULT_LIMITS)
    await db_session.flush()
    await bookmark_service.archive(db_session, test_user.id, archived_bm.id)
    await db_session.flush()

    # Sort by created_at desc — the second bookmark was created later
    items, total = await search_all_content(
        db_session, test_user.id,
        view={'active', 'archived'},
        sort_by='created_at',
        sort_order='desc',
    )

    assert total == 2
    # Most recently created should be first regardless of archive status
    assert items[0].id == archived_bm.id


async def test__search_all_content__single_view_backward_compatible(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Single-value set behaves identically to old single-value behavior."""
    note_data = NoteCreate(title='Compatible Note')
    note = await note_service.create(db_session, test_user.id, note_data, DEFAULT_LIMITS)
    await db_session.flush()

    items, total = await search_all_content(db_session, test_user.id, view={'active'})

    assert total == 1
    assert items[0].id == note.id


async def test__search_all_content__empty_view_raises_value_error(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Empty view set raises ValueError."""
    with pytest.raises(ValueError, match="at least one option"):
        await search_all_content(db_session, test_user.id, view=set())


async def test__search_all_content__view_archived_deleted(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test view={'archived', 'deleted'} returns archived and deleted, excludes active."""
    active_data = NoteCreate(title='Active Note')
    await note_service.create(db_session, test_user.id, active_data, DEFAULT_LIMITS)

    archived_data = BookmarkCreate(url='https://arch.com', title='Archived BM')
    archived_bm = await bookmark_service.create(db_session, test_user.id, archived_data, DEFAULT_LIMITS)
    await db_session.flush()
    await bookmark_service.archive(db_session, test_user.id, archived_bm.id)

    deleted_data = NoteCreate(title='Deleted Note')
    deleted_note = await note_service.create(db_session, test_user.id, deleted_data, DEFAULT_LIMITS)
    await db_session.flush()
    await note_service.delete(db_session, test_user.id, deleted_note.id)
    await db_session.flush()

    items, total = await search_all_content(
        db_session, test_user.id, view={'archived', 'deleted'},
    )

    assert total == 2
    ids = {item.id for item in items}
    assert ids == {archived_bm.id, deleted_note.id}


async def test__search_all_content__view_active_archived_with_prompts(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Prompts included correctly in combined active+archived view."""
    prompt_data = PromptCreate(name='active-prompt', content='Active content')
    active_prompt = await prompt_service.create(db_session, test_user.id, prompt_data, DEFAULT_LIMITS)

    archived_prompt_data = PromptCreate(name='archived-prompt', content='Archived content')
    archived_prompt = await prompt_service.create(
        db_session, test_user.id, archived_prompt_data, DEFAULT_LIMITS,
    )
    await db_session.flush()
    await prompt_service.archive(db_session, test_user.id, archived_prompt.id)
    await db_session.flush()

    items, total = await search_all_content(
        db_session, test_user.id,
        view={'active', 'archived'},
        content_types=['prompt'],
    )

    assert total == 2
    ids = {item.id for item in items}
    assert ids == {active_prompt.id, archived_prompt.id}


async def test__search_all_content__future_scheduled_archive_appears_in_active_view(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Future-scheduled archive appears in active and active+archived, not archived-only."""
    future_data = BookmarkCreate(
        url='https://future.com', title='Future Archive',
        archived_at=datetime.now(UTC) + timedelta(days=30),
    )
    future_bm = await bookmark_service.create(db_session, test_user.id, future_data, DEFAULT_LIMITS)
    await db_session.flush()

    # Should appear in active view (future-scheduled = not yet archived)
    items_active, total_active = await search_all_content(
        db_session, test_user.id, view={'active'},
    )
    assert total_active == 1
    assert items_active[0].id == future_bm.id

    # Should appear in active+archived view
    items_both, total_both = await search_all_content(
        db_session, test_user.id, view={'active', 'archived'},
    )
    assert total_both == 1
    assert items_both[0].id == future_bm.id

    # Should NOT appear in archived-only view (not yet archived)
    _items_archived, total_archived = await search_all_content(
        db_session, test_user.id, view={'archived'},
    )
    assert total_archived == 0


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
    await bookmark_service.create(db_session, test_user.id, bookmark_data, DEFAULT_LIMITS)

    note_data = NoteCreate(title='JavaScript Tutorial')
    await note_service.create(db_session, test_user.id, note_data, DEFAULT_LIMITS)

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
    await bookmark_service.create(db_session, test_user.id, bookmark_data, DEFAULT_LIMITS)

    note_data = NoteCreate(title='Note', description='JavaScript advanced')
    await note_service.create(db_session, test_user.id, note_data, DEFAULT_LIMITS)

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
    await bookmark_service.create(db_session, test_user.id, bookmark_data, DEFAULT_LIMITS)

    await db_session.flush()

    _items, total = await search_all_content(db_session, test_user.id, query='python')

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
    await bookmark_service.create(db_session, test_user.id, bookmark_data, DEFAULT_LIMITS)

    # Create note with only one tag
    note_data = NoteCreate(title='Python Only', tags=['python'])
    await note_service.create(db_session, test_user.id, note_data, DEFAULT_LIMITS)

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
    await bookmark_service.create(db_session, test_user.id, bookmark_data, DEFAULT_LIMITS)

    note_data = NoteCreate(title='Web', tags=['web'])
    await note_service.create(db_session, test_user.id, note_data, DEFAULT_LIMITS)

    note_data2 = NoteCreate(title='Java', tags=['java'])
    await note_service.create(db_session, test_user.id, note_data2, DEFAULT_LIMITS)

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
    await bookmark_service.create(db_session, test_user.id, bookmark_data, DEFAULT_LIMITS)

    note_data = NoteCreate(title='Tagged Note', tags=['tag-c', 'tag-d'])
    await note_service.create(db_session, test_user.id, note_data, DEFAULT_LIMITS)

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
    # Create content with delays
    bookmark_data = BookmarkCreate(url='https://first.com', title='First')
    await bookmark_service.create(db_session, test_user.id, bookmark_data, DEFAULT_LIMITS)
    await db_session.flush()

    await asyncio.sleep(0.01)

    note_data = NoteCreate(title='Second')
    await note_service.create(db_session, test_user.id, note_data, DEFAULT_LIMITS)
    await db_session.flush()

    await asyncio.sleep(0.01)

    bookmark_data2 = BookmarkCreate(url='https://third.com', title='Third')
    await bookmark_service.create(db_session, test_user.id, bookmark_data2, DEFAULT_LIMITS)
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
    await bookmark_service.create(db_session, test_user.id, bookmark_data, DEFAULT_LIMITS)

    note_data = NoteCreate(title='Apple')
    await note_service.create(db_session, test_user.id, note_data, DEFAULT_LIMITS)

    bookmark_data2 = BookmarkCreate(url='https://m.com', title='Mango')
    await bookmark_service.create(db_session, test_user.id, bookmark_data2, DEFAULT_LIMITS)

    await db_session.flush()

    items, _ = await search_all_content(
        db_session, test_user.id, sort_by='title', sort_order='asc',
    )

    assert items[0].title == 'Apple'
    assert items[1].title == 'Mango'
    assert items[2].title == 'Zebra'


async def test__search_all_content__sort_by_title_uses_name_fallback_for_prompts(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that prompts without titles sort by name and interleave correctly with titled items."""
    # Prompt WITHOUT title - should sort by name "code-review"
    prompt1 = await prompt_service.create(
        db_session, test_user.id,
        PromptCreate(name="code-review", content="Test content"), DEFAULT_LIMITS,
    )
    # Prompt WITH title starting with uppercase 'D'
    prompt2 = await prompt_service.create(
        db_session, test_user.id,
        PromptCreate(name="decision-prompt", title="Decision Clarity", content="Test content"), DEFAULT_LIMITS,
    )
    # Prompt WITH title starting with lowercase 'c'
    prompt3 = await prompt_service.create(
        db_session, test_user.id,
        PromptCreate(name="coding-prompt", title="coding Guidelines", content="Test content"), DEFAULT_LIMITS,
    )
    # Bookmark with title starting with 'B'
    bookmark = await bookmark_service.create(
        db_session, test_user.id,
        BookmarkCreate(url="https://example.com", title="Beta Site"), DEFAULT_LIMITS,
    )
    await db_session.flush()

    items, _ = await search_all_content(
        db_session, test_user.id,
        sort_by='title', sort_order='asc',
        content_types=['prompt', 'bookmark'],
    )

    # Case-insensitive order: "Beta Site" < "code-review" < "coding Guidelines" < "Decision Clarity"
    assert len(items) == 4
    assert items[0].id == bookmark.id  # Beta Site
    assert items[1].id == prompt1.id   # code-review (name, no title)
    assert items[2].id == prompt3.id   # coding Guidelines (title)
    assert items[3].id == prompt2.id   # Decision Clarity (title)


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
        await bookmark_service.create(db_session, test_user.id, bookmark_data, DEFAULT_LIMITS)
    for i in range(2):
        note_data = NoteCreate(title=f'Note {i}')
        await note_service.create(db_session, test_user.id, note_data, DEFAULT_LIMITS)
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
        await bookmark_service.create(db_session, test_user.id, bookmark_data, DEFAULT_LIMITS)
    for i in range(5):
        note_data = NoteCreate(title=f'Note {i}')
        await note_service.create(db_session, test_user.id, note_data, DEFAULT_LIMITS)
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
    await bookmark_service.create(db_session, test_user.id, bookmark_data, DEFAULT_LIMITS)

    note_data = NoteCreate(title='My Note')
    await note_service.create(db_session, test_user.id, note_data, DEFAULT_LIMITS)

    # Create content for other_user
    other_bookmark_data = BookmarkCreate(url='https://other.com', title='Other Bookmark')
    await bookmark_service.create(db_session, other_user.id, other_bookmark_data, DEFAULT_LIMITS)

    other_note_data = NoteCreate(title='Other Note')
    await note_service.create(db_session, other_user.id, other_note_data, DEFAULT_LIMITS)

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
    await bookmark_service.create(db_session, test_user.id, bookmark_data, DEFAULT_LIMITS)
    await db_session.flush()

    _items, total = await search_all_content(
        db_session, test_user.id, tags=[],
    )

    assert total == 1


async def test__search_all_content__handles_special_characters_in_query(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that special characters in query are escaped properly."""
    bookmark_data = BookmarkCreate(url='https://test.com', title='100% Complete')
    await bookmark_service.create(db_session, test_user.id, bookmark_data, DEFAULT_LIMITS)
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
    bookmark = await bookmark_service.create(db_session, test_user.id, bookmark_data, DEFAULT_LIMITS)

    note_data = NoteCreate(
        title='Full Note',
        description='Note description',
        tags=['note-tag'],
    )
    note = await note_service.create(db_session, test_user.id, note_data, DEFAULT_LIMITS)

    await db_session.flush()

    items, _ = await search_all_content(db_session, test_user.id)

    bookmark_item = next(item for item in items if item.type == 'bookmark')
    note_item = next(item for item in items if item.type == 'note')

    # Check bookmark fields
    assert bookmark_item.id == bookmark.id
    assert bookmark_item.title == 'Full Bookmark'
    assert bookmark_item.description == 'A description'
    assert bookmark_item.url == 'https://test.com/'
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
    assert note_item.created_at is not None
    assert 'note-tag' in note_item.tags


# =============================================================================
# Prompt Tests
# =============================================================================


async def test__search_all_content__returns_prompts(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that search returns prompts along with bookmarks and notes."""
    # Create one of each type
    bookmark_data = BookmarkCreate(url='https://example.com', title='Bookmark')
    await bookmark_service.create(db_session, test_user.id, bookmark_data, DEFAULT_LIMITS)

    note_data = NoteCreate(title='Note')
    await note_service.create(db_session, test_user.id, note_data, DEFAULT_LIMITS)

    prompt_data = PromptCreate(name='test-prompt', title='Prompt Title', content='Prompt content')
    await prompt_service.create(db_session, test_user.id, prompt_data, DEFAULT_LIMITS)

    await db_session.flush()

    items, total = await search_all_content(db_session, test_user.id)

    assert total == 3
    types = {item.type for item in items}
    assert types == {'bookmark', 'note', 'prompt'}


async def test__search_all_content__prompt_has_correct_fields(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that prompt-specific fields are populated correctly."""
    prompt_data = PromptCreate(
        name='code-review',
        title='Code Review Prompt',
        description='A prompt for reviewing code',
        content='Review this {{ code }} in {{ language }}',
        arguments=[
            {'name': 'code', 'description': 'Code to review', 'required': True},
            {'name': 'language', 'description': None, 'required': False},
        ],
        tags=['code', 'review'],
    )
    prompt = await prompt_service.create(db_session, test_user.id, prompt_data, DEFAULT_LIMITS)
    await db_session.flush()

    items, _ = await search_all_content(db_session, test_user.id)

    prompt_item = next(item for item in items if item.type == 'prompt')

    assert prompt_item.id == prompt.id
    assert prompt_item.type == 'prompt'
    assert prompt_item.title == 'Code Review Prompt'
    assert prompt_item.description == 'A prompt for reviewing code'
    assert prompt_item.name == 'code-review'
    assert len(prompt_item.arguments) == 2
    assert prompt_item.arguments[0]['name'] == 'code'
    assert prompt_item.arguments[0]['required'] is True
    assert set(prompt_item.tags) == {'code', 'review'}
    # Prompt-specific: no url
    assert prompt_item.url is None


async def test__search_all_content__content_types_filter_prompts_only(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test filtering to only return prompts."""
    bookmark_data = BookmarkCreate(url='https://test.com', title='Bookmark')
    await bookmark_service.create(db_session, test_user.id, bookmark_data, DEFAULT_LIMITS)

    note_data = NoteCreate(title='Note')
    await note_service.create(db_session, test_user.id, note_data, DEFAULT_LIMITS)

    prompt_data = PromptCreate(name='my-prompt', title='My Prompt', content='My prompt content')
    await prompt_service.create(db_session, test_user.id, prompt_data, DEFAULT_LIMITS)

    await db_session.flush()

    # Filter to only prompts
    items, total = await search_all_content(
        db_session, test_user.id, content_types=['prompt'],
    )

    assert total == 1
    assert items[0].type == 'prompt'
    assert items[0].name == 'my-prompt'


async def test__search_all_content__content_types_filter_excludes_prompts(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test filtering to exclude prompts."""
    bookmark_data = BookmarkCreate(url='https://test.com', title='Bookmark')
    await bookmark_service.create(db_session, test_user.id, bookmark_data, DEFAULT_LIMITS)

    note_data = NoteCreate(title='Note')
    await note_service.create(db_session, test_user.id, note_data, DEFAULT_LIMITS)

    prompt_data = PromptCreate(name='my-prompt', content='Prompt content')
    await prompt_service.create(db_session, test_user.id, prompt_data, DEFAULT_LIMITS)

    await db_session.flush()

    # Filter to only bookmarks and notes
    items, total = await search_all_content(
        db_session, test_user.id, content_types=['bookmark', 'note'],
    )

    assert total == 2
    types = {item.type for item in items}
    assert types == {'bookmark', 'note'}


async def test__search_all_content__content_types_multiple_combinations(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test various content_types filter combinations."""
    bookmark_data = BookmarkCreate(url='https://test.com', title='Bookmark')
    await bookmark_service.create(db_session, test_user.id, bookmark_data, DEFAULT_LIMITS)

    note_data = NoteCreate(title='Note')
    await note_service.create(db_session, test_user.id, note_data, DEFAULT_LIMITS)

    prompt_data = PromptCreate(name='prompt', content='Prompt content')
    await prompt_service.create(db_session, test_user.id, prompt_data, DEFAULT_LIMITS)

    await db_session.flush()

    # Test bookmark + prompt
    items, total = await search_all_content(
        db_session, test_user.id, content_types=['bookmark', 'prompt'],
    )
    assert total == 2
    assert {item.type for item in items} == {'bookmark', 'prompt'}

    # Test note + prompt
    items, total = await search_all_content(
        db_session, test_user.id, content_types=['note', 'prompt'],
    )
    assert total == 2
    assert {item.type for item in items} == {'note', 'prompt'}

    # Test all three
    items, total = await search_all_content(
        db_session, test_user.id, content_types=['bookmark', 'note', 'prompt'],
    )
    assert total == 3


async def test__search_all_content__prompt_view_active(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that view={'active'} works correctly for prompts."""
    # Create active, archived, and deleted prompts
    active_prompt = PromptCreate(name='active-prompt', content='Active content')
    await prompt_service.create(db_session, test_user.id, active_prompt, DEFAULT_LIMITS)

    archived_prompt = PromptCreate(name='archived-prompt', content='Archived content')
    archived = await prompt_service.create(db_session, test_user.id, archived_prompt, DEFAULT_LIMITS)

    deleted_prompt = PromptCreate(name='deleted-prompt', content='Deleted content')
    deleted = await prompt_service.create(db_session, test_user.id, deleted_prompt, DEFAULT_LIMITS)

    await db_session.flush()

    # Archive and delete
    await prompt_service.archive(db_session, test_user.id, archived.id)
    await prompt_service.delete(db_session, test_user.id, deleted.id)
    await db_session.flush()

    # Search active prompts
    items, total = await search_all_content(
        db_session, test_user.id, view={'active'}, content_types=['prompt'],
    )

    assert total == 1
    assert items[0].name == 'active-prompt'


async def test__search_all_content__prompt_view_archived(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that view={'archived'} returns archived prompts."""
    active_prompt = PromptCreate(name='active-prompt', content='Active content')
    await prompt_service.create(db_session, test_user.id, active_prompt, DEFAULT_LIMITS)

    archived_prompt = PromptCreate(name='archived-prompt', content='Archived content')
    archived = await prompt_service.create(db_session, test_user.id, archived_prompt, DEFAULT_LIMITS)

    await db_session.flush()
    await prompt_service.archive(db_session, test_user.id, archived.id)
    await db_session.flush()

    items, total = await search_all_content(
        db_session, test_user.id, view={'archived'}, content_types=['prompt'],
    )

    assert total == 1
    assert items[0].name == 'archived-prompt'


async def test__search_all_content__prompt_view_deleted(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that view={'deleted'} returns deleted prompts."""
    active_prompt = PromptCreate(name='active-prompt', content='Active content')
    await prompt_service.create(db_session, test_user.id, active_prompt, DEFAULT_LIMITS)

    deleted_prompt = PromptCreate(name='deleted-prompt', content='Deleted content')
    deleted = await prompt_service.create(db_session, test_user.id, deleted_prompt, DEFAULT_LIMITS)

    await db_session.flush()
    await prompt_service.delete(db_session, test_user.id, deleted.id)
    await db_session.flush()

    items, total = await search_all_content(
        db_session, test_user.id, view={'deleted'}, content_types=['prompt'],
    )

    assert total == 1
    assert items[0].name == 'deleted-prompt'


async def test__search_all_content__prompt_text_search_in_name(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that text search finds prompts by name."""
    prompt1 = PromptCreate(name='code-review-prompt', content='Content 1')
    await prompt_service.create(db_session, test_user.id, prompt1, DEFAULT_LIMITS)

    prompt2 = PromptCreate(name='bug-report-prompt', content='Content 2')
    await prompt_service.create(db_session, test_user.id, prompt2, DEFAULT_LIMITS)

    await db_session.flush()

    items, total = await search_all_content(
        db_session, test_user.id, query='code-review',
    )

    assert total == 1
    assert items[0].name == 'code-review-prompt'


async def test__search_all_content__prompt_text_search_in_content(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that text search finds prompts by content."""
    prompt1 = PromptCreate(
        name='prompt1',
        content='Please review the following Python code',
    )
    await prompt_service.create(db_session, test_user.id, prompt1, DEFAULT_LIMITS)

    prompt2 = PromptCreate(
        name='prompt2',
        content='Write a JavaScript function',
    )
    await prompt_service.create(db_session, test_user.id, prompt2, DEFAULT_LIMITS)

    await db_session.flush()

    items, total = await search_all_content(
        db_session, test_user.id, query='Python',
    )

    assert total == 1
    assert items[0].name == 'prompt1'


async def test__search_all_content__prompt_tag_filter(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that tag filtering works for prompts."""
    prompt1 = PromptCreate(name='prompt1', content='Content 1', tags=['code', 'review'])
    await prompt_service.create(db_session, test_user.id, prompt1, DEFAULT_LIMITS)

    prompt2 = PromptCreate(name='prompt2', content='Content 2', tags=['writing'])
    await prompt_service.create(db_session, test_user.id, prompt2, DEFAULT_LIMITS)

    await db_session.flush()

    # Filter by 'code' tag
    items, total = await search_all_content(
        db_session, test_user.id, tags=['code'], content_types=['prompt'],
    )

    assert total == 1
    assert items[0].name == 'prompt1'


async def test__search_all_content__prompt_excludes_other_users(
    db_session: AsyncSession,
    test_user: User,
    other_user: User,
) -> None:
    """Test that prompts from other users are excluded."""
    my_prompt = PromptCreate(name='my-prompt', content='My content')
    await prompt_service.create(db_session, test_user.id, my_prompt, DEFAULT_LIMITS)

    other_prompt = PromptCreate(name='other-prompt', content='Other content')
    await prompt_service.create(db_session, other_user.id, other_prompt, DEFAULT_LIMITS)

    await db_session.flush()

    items, total = await search_all_content(
        db_session, test_user.id, content_types=['prompt'],
    )

    assert total == 1
    assert items[0].name == 'my-prompt'


async def test__search_all_content__prompt_with_empty_arguments(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that prompts with no arguments work correctly."""
    prompt_data = PromptCreate(name='no-args-prompt', content='Simple content without variables')
    await prompt_service.create(db_session, test_user.id, prompt_data, DEFAULT_LIMITS)
    await db_session.flush()

    items, _ = await search_all_content(db_session, test_user.id)

    prompt_item = next(item for item in items if item.type == 'prompt')
    assert prompt_item.arguments == []


async def test__search_all_content__mixed_content_sorting(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that sorting works correctly across all content types."""
    # Create with delays to ensure different created_at times
    bookmark_data = BookmarkCreate(url='https://first.com', title='First')
    await bookmark_service.create(db_session, test_user.id, bookmark_data, DEFAULT_LIMITS)
    await db_session.flush()

    await asyncio.sleep(0.01)

    note_data = NoteCreate(title='Second')
    await note_service.create(db_session, test_user.id, note_data, DEFAULT_LIMITS)
    await db_session.flush()

    await asyncio.sleep(0.01)

    prompt_data = PromptCreate(name='third', content='Third content')
    await prompt_service.create(db_session, test_user.id, prompt_data, DEFAULT_LIMITS)
    await db_session.flush()

    # Sort by created_at desc (newest first)
    items, _ = await search_all_content(
        db_session, test_user.id, sort_by='created_at', sort_order='desc',
    )

    # Prompt should be first (created last)
    assert items[0].type == 'prompt'
    assert items[1].type == 'note'
    assert items[2].type == 'bookmark'


async def test__search_all_content__prompt_pagination(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test pagination with prompts."""
    # Create 5 prompts
    for i in range(5):
        prompt_data = PromptCreate(name=f'prompt-{i}', content=f'Content {i}')
        await prompt_service.create(db_session, test_user.id, prompt_data, DEFAULT_LIMITS)
    await db_session.flush()

    # Get first page
    items, total = await search_all_content(
        db_session, test_user.id, offset=0, limit=2, content_types=['prompt'],
    )

    assert total == 5
    assert len(items) == 2

    # Get second page
    items2, total = await search_all_content(
        db_session, test_user.id, offset=2, limit=2, content_types=['prompt'],
    )

    assert total == 5
    assert len(items2) == 2
    # Ensure different prompts
    assert items[0].name != items2[0].name
