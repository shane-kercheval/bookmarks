"""
Tests for note service layer functionality.

Tests the soft delete, archive, restore, and view filtering functionality
that was added to support the trash/archive features.
"""
from datetime import UTC

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.note import Note
from models.tag import note_tags
from models.user import User
from schemas.note import NoteCreate, NoteUpdate
from services.exceptions import InvalidStateError
from services.note_service import NoteService
from services.utils import build_tag_filter_from_expression, escape_ilike


note_service = NoteService()


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(auth0_id='test-user-notes-123', email='test-notes@example.com')
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_note(db_session: AsyncSession, test_user: User) -> Note:
    """Create a test note."""
    note = Note(
        user_id=test_user.id,
        title='Example Note',
        description='An example note',
        content='# Heading\n\nSome markdown content.',
    )
    db_session.add(note)
    await db_session.flush()
    await db_session.refresh(note)
    return note


# =============================================================================
# Soft Delete Tests
# =============================================================================


async def test__delete_note__soft_delete_sets_deleted_at(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that soft delete sets deleted_at timestamp instead of removing."""
    note_id = test_note.id

    result = await note_service.delete(db_session, test_user.id, note_id)

    assert result is True

    # Verify note still exists in DB with deleted_at set
    query = select(Note).where(Note.id == note_id)
    db_result = await db_session.execute(query)
    note = db_result.scalar_one()
    assert note.deleted_at is not None


async def test__delete_note__soft_delete_hides_from_get(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that soft-deleted note is hidden from get_note by default."""
    note_id = test_note.id
    await note_service.delete(db_session, test_user.id, note_id)

    # Should not find the deleted note
    result = await note_service.get(db_session, test_user.id, note_id)
    assert result is None


async def test__delete_note__soft_delete_visible_with_include_deleted(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that soft-deleted note is visible with include_deleted=True."""
    note_id = test_note.id
    await note_service.delete(db_session, test_user.id, note_id)

    result = await note_service.get(
        db_session, test_user.id, note_id, include_deleted=True,
    )
    assert result is not None
    assert result.deleted_at is not None


async def test__delete_note__permanent_removes_from_db(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that permanent delete removes note from database."""
    note_id = test_note.id

    # First soft-delete it (simulating it being in trash)
    await note_service.delete(db_session, test_user.id, note_id)
    await db_session.flush()

    # Then permanently delete
    result = await note_service.delete(
        db_session, test_user.id, note_id, permanent=True,
    )

    assert result is True

    # Verify note is completely gone
    query = select(Note).where(Note.id == note_id)
    db_result = await db_session.execute(query)
    assert db_result.scalar_one_or_none() is None


async def test__delete_note__soft_delete_archived_note(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that soft-deleting an archived note sets deleted_at."""
    note_id = test_note.id

    # Archive first
    await note_service.archive(db_session, test_user.id, note_id)
    await db_session.flush()

    # Then soft-delete
    result = await note_service.delete(db_session, test_user.id, note_id)

    assert result is True

    # Verify both timestamps are set
    query = select(Note).where(Note.id == note_id)
    db_result = await db_session.execute(query)
    note = db_result.scalar_one()
    assert note.deleted_at is not None
    assert note.archived_at is not None


# =============================================================================
# View Filtering Tests
# =============================================================================


async def test__search_notes__view_active_excludes_deleted(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that view='active' excludes deleted notes."""
    # Create two notes
    n1 = Note(user_id=test_user.id, title='Active Note')
    n2 = Note(user_id=test_user.id, title='Deleted Note')
    db_session.add_all([n1, n2])
    await db_session.flush()

    # Delete one
    await note_service.delete(db_session, test_user.id, n2.id)
    await db_session.flush()

    # Search should only return active
    notes, total = await note_service.search(
        db_session, test_user.id, view='active',
    )

    assert total == 1
    assert len(notes) == 1
    assert notes[0].title == 'Active Note'


async def test__search_notes__view_active_excludes_archived(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that view='active' excludes archived notes."""
    n1 = Note(user_id=test_user.id, title='Active Note')
    n2 = Note(user_id=test_user.id, title='Archived Note')
    db_session.add_all([n1, n2])
    await db_session.flush()

    await note_service.archive(db_session, test_user.id, n2.id)
    await db_session.flush()

    notes, total = await note_service.search(
        db_session, test_user.id, view='active',
    )

    assert total == 1
    assert notes[0].title == 'Active Note'


async def test__search_notes__view_archived_returns_only_archived(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that view='archived' returns only archived (not deleted) notes."""
    n1 = Note(user_id=test_user.id, title='Active Note')
    n2 = Note(user_id=test_user.id, title='Archived Note')
    n3 = Note(user_id=test_user.id, title='Deleted Note')
    db_session.add_all([n1, n2, n3])
    await db_session.flush()

    await note_service.archive(db_session, test_user.id, n2.id)
    await note_service.delete(db_session, test_user.id, n3.id)
    await db_session.flush()

    notes, total = await note_service.search(
        db_session, test_user.id, view='archived',
    )

    assert total == 1
    assert notes[0].title == 'Archived Note'


async def test__search_notes__view_deleted_returns_all_deleted(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that view='deleted' returns all deleted notes including deleted+archived."""
    n1 = Note(user_id=test_user.id, title='Active Note')
    n2 = Note(user_id=test_user.id, title='Deleted Note')
    n3 = Note(user_id=test_user.id, title='Deleted and Archived Note')
    db_session.add_all([n1, n2, n3])
    await db_session.flush()

    await note_service.delete(db_session, test_user.id, n2.id)
    await note_service.archive(db_session, test_user.id, n3.id)
    await note_service.delete(db_session, test_user.id, n3.id)
    await db_session.flush()

    notes, total = await note_service.search(
        db_session, test_user.id, view='deleted',
    )

    assert total == 2
    titles = {n.title for n in notes}
    assert 'Deleted Note' in titles
    assert 'Deleted and Archived Note' in titles


async def test__search_notes__view_with_query_filter(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that search query works with view filtering."""
    n1 = Note(
        user_id=test_user.id, title='Python Guide',
    )
    n2 = Note(
        user_id=test_user.id, title='Python Tutorial',
    )
    db_session.add_all([n1, n2])
    await db_session.flush()

    await note_service.archive(db_session, test_user.id, n2.id)
    await db_session.flush()

    # Search for "Python" in archived view
    notes, total = await note_service.search(
        db_session, test_user.id, query='Python', view='archived',
    )

    assert total == 1
    assert notes[0].title == 'Python Tutorial'


# =============================================================================
# Restore Tests
# =============================================================================


async def test__restore_note__clears_deleted_at(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that restore clears deleted_at timestamp."""
    note_id = test_note.id

    await note_service.delete(db_session, test_user.id, note_id)
    await db_session.flush()

    restored = await note_service.restore(db_session, test_user.id, note_id)

    assert restored is not None
    assert restored.deleted_at is None


async def test__restore_note__clears_both_timestamps(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that restoring deleted+archived note clears BOTH timestamps."""
    note_id = test_note.id

    await note_service.archive(db_session, test_user.id, note_id)
    await note_service.delete(db_session, test_user.id, note_id)
    await db_session.flush()

    restored = await note_service.restore(db_session, test_user.id, note_id)

    assert restored is not None
    assert restored.deleted_at is None
    assert restored.archived_at is None


async def test__restore_note__appears_in_active_list(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that restored note appears in active list."""
    note_id = test_note.id

    await note_service.delete(db_session, test_user.id, note_id)
    await db_session.flush()

    await note_service.restore(db_session, test_user.id, note_id)
    await db_session.flush()

    notes, total = await note_service.search(
        db_session, test_user.id, view='active',
    )

    assert total == 1
    assert notes[0].id == note_id


async def test__restore_note__returns_none_for_nonexistent(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that restore returns None for non-existent note."""
    result = await note_service.restore(db_session, test_user.id, 99999)
    assert result is None


async def test__restore_note__raises_error_if_not_deleted(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that restoring a non-deleted note raises InvalidStateError."""
    with pytest.raises(InvalidStateError) as exc_info:
        await note_service.restore(db_session, test_user.id, test_note.id)

    assert "not deleted" in str(exc_info.value)


# =============================================================================
# Archive Tests
# =============================================================================


async def test__archive_note__sets_archived_at(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that archive sets archived_at timestamp."""
    note_id = test_note.id

    archived = await note_service.archive(db_session, test_user.id, note_id)

    assert archived is not None
    assert archived.archived_at is not None


async def test__archive_note__is_idempotent(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that archiving an already-archived note is idempotent."""
    note_id = test_note.id

    await note_service.archive(db_session, test_user.id, note_id)
    await db_session.flush()

    # Archive again - should succeed
    archived = await note_service.archive(db_session, test_user.id, note_id)

    assert archived is not None
    assert archived.archived_at is not None


async def test__archive_note__hides_from_active_list(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that archived note is hidden from active list."""
    note_id = test_note.id

    await note_service.archive(db_session, test_user.id, note_id)
    await db_session.flush()

    notes, total = await note_service.search(
        db_session, test_user.id, view='active',
    )

    assert total == 0


async def test__archive_note__returns_none_for_nonexistent(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that archive returns None for non-existent note."""
    result = await note_service.archive(db_session, test_user.id, 99999)
    assert result is None


# =============================================================================
# Unarchive Tests
# =============================================================================


async def test__unarchive_note__clears_archived_at(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that unarchive clears archived_at timestamp."""
    note_id = test_note.id

    await note_service.archive(db_session, test_user.id, note_id)
    await db_session.flush()

    unarchived = await note_service.unarchive(db_session, test_user.id, note_id)

    assert unarchived is not None
    assert unarchived.archived_at is None


async def test__unarchive_note__appears_in_active_list(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that unarchived note appears in active list."""
    note_id = test_note.id

    await note_service.archive(db_session, test_user.id, note_id)
    await db_session.flush()

    await note_service.unarchive(db_session, test_user.id, note_id)
    await db_session.flush()

    notes, total = await note_service.search(
        db_session, test_user.id, view='active',
    )

    assert total == 1
    assert notes[0].id == note_id


async def test__unarchive_note__returns_none_for_nonexistent(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that unarchive returns None for non-existent note."""
    result = await note_service.unarchive(db_session, test_user.id, 99999)
    assert result is None


async def test__unarchive_note__raises_error_for_non_archived(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that unarchiving a non-archived note raises InvalidStateError."""
    with pytest.raises(InvalidStateError) as exc_info:
        await note_service.unarchive(db_session, test_user.id, test_note.id)

    assert "not archived" in str(exc_info.value)


# =============================================================================
# get_note Include Flags Tests
# =============================================================================


async def test__get_note__excludes_archived_by_default(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that get_note excludes archived notes by default."""
    note_id = test_note.id

    await note_service.archive(db_session, test_user.id, note_id)
    await db_session.flush()

    result = await note_service.get(db_session, test_user.id, note_id)
    assert result is None


async def test__get_note__includes_archived_when_requested(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that get_note includes archived when include_archived=True."""
    note_id = test_note.id

    await note_service.archive(db_session, test_user.id, note_id)
    await db_session.flush()

    result = await note_service.get(
        db_session, test_user.id, note_id, include_archived=True,
    )
    assert result is not None
    assert result.archived_at is not None


# =============================================================================
# Track Usage Tests
# =============================================================================


async def test__track_note_usage__updates_last_used_at(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that track_note_usage updates the last_used_at timestamp."""
    import asyncio

    original_last_used = test_note.last_used_at

    # Small delay to ensure different timestamp
    await asyncio.sleep(0.01)

    result = await note_service.track_usage(db_session, test_user.id, test_note.id)
    await db_session.flush()
    await db_session.refresh(test_note)

    assert result is True
    assert test_note.last_used_at > original_last_used


async def test__track_note_usage__returns_false_for_nonexistent(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that track_note_usage returns False for non-existent note."""
    result = await note_service.track_usage(db_session, test_user.id, 99999)
    assert result is False


async def test__track_note_usage__works_on_archived_note(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that track_note_usage works on archived notes."""
    import asyncio

    await note_service.archive(db_session, test_user.id, test_note.id)
    await db_session.flush()

    original_last_used = test_note.last_used_at

    # Small delay to ensure different timestamp
    await asyncio.sleep(0.01)

    result = await note_service.track_usage(db_session, test_user.id, test_note.id)
    await db_session.flush()
    await db_session.refresh(test_note)

    assert result is True
    assert test_note.last_used_at > original_last_used


async def test__track_note_usage__works_on_deleted_note(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that track_note_usage works on soft-deleted notes."""
    import asyncio

    await note_service.delete(db_session, test_user.id, test_note.id)
    await db_session.flush()

    original_last_used = test_note.last_used_at

    # Small delay to ensure different timestamp
    await asyncio.sleep(0.01)

    result = await note_service.track_usage(db_session, test_user.id, test_note.id)
    await db_session.flush()
    await db_session.refresh(test_note)

    assert result is True
    assert test_note.last_used_at > original_last_used


async def test__track_note_usage__does_not_update_updated_at(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that track_note_usage does NOT update updated_at."""
    import asyncio

    original_updated_at = test_note.updated_at

    # Small delay to ensure different timestamp if it were to change
    await asyncio.sleep(0.01)

    result = await note_service.track_usage(db_session, test_user.id, test_note.id)
    await db_session.flush()
    await db_session.refresh(test_note)

    assert result is True
    # updated_at should remain unchanged
    assert test_note.updated_at == original_updated_at


# =============================================================================
# Create Note Tests
# =============================================================================


async def test__create_note__creates_note_with_all_fields(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that create_note creates a note with all provided fields."""
    data = NoteCreate(
        title='My Test Note',
        description='A test description',
        content='# Test\n\nContent here.',
        tags=['test', 'python'],
    )
    note = await note_service.create(db_session, test_user.id, data)

    assert note.title == 'My Test Note'
    assert note.description == 'A test description'
    assert note.content == '# Test\n\nContent here.'
    assert len(note.tag_objects) == 2
    tag_names = [t.name for t in note.tag_objects]
    assert 'test' in tag_names
    assert 'python' in tag_names


async def test__create_note__last_used_at_equals_created_at(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that new notes have last_used_at exactly equal to created_at."""
    data = NoteCreate(title='New Note')
    note = await note_service.create(db_session, test_user.id, data)

    assert note.last_used_at == note.created_at


async def test__create_note__version_starts_at_one(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that new notes have version=1."""
    data = NoteCreate(title='New Note')
    note = await note_service.create(db_session, test_user.id, data)

    assert note.version == 1


# =============================================================================
# Sort Tests
# =============================================================================


async def test__search_notes__sort_by_last_used_at_desc(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test sorting by last_used_at descending (most recently used first)."""
    import asyncio

    # Create notes
    data1 = NoteCreate(title='First Note')
    n1 = await note_service.create(db_session, test_user.id, data1)
    await db_session.flush()

    await asyncio.sleep(0.01)  # Small delay to ensure different timestamps

    data2 = NoteCreate(title='Second Note')
    n2 = await note_service.create(db_session, test_user.id, data2)
    await db_session.flush()

    await asyncio.sleep(0.01)  # Small delay before tracking usage

    # Track usage on first note (makes it most recently used)
    await note_service.track_usage(db_session, test_user.id, n1.id)
    await db_session.flush()

    notes, total = await note_service.search(
        db_session, test_user.id, sort_by='last_used_at', sort_order='desc',
    )

    assert total == 2
    assert notes[0].id == n1.id  # Most recently used
    assert notes[1].id == n2.id


async def test__search_notes__sort_by_last_used_at_asc(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test sorting by last_used_at ascending (least recently used first)."""
    import asyncio

    # Create notes
    data1 = NoteCreate(title='First Note')
    n1 = await note_service.create(db_session, test_user.id, data1)
    await db_session.flush()

    await asyncio.sleep(0.01)

    data2 = NoteCreate(title='Second Note')
    n2 = await note_service.create(db_session, test_user.id, data2)
    await db_session.flush()

    await asyncio.sleep(0.01)  # Small delay before tracking usage

    # Track usage on first note
    await note_service.track_usage(db_session, test_user.id, n1.id)
    await db_session.flush()

    notes, total = await note_service.search(
        db_session, test_user.id, sort_by='last_used_at', sort_order='asc',
    )

    assert total == 2
    assert notes[0].id == n2.id  # Least recently used
    assert notes[1].id == n1.id


async def test__search_notes__sort_by_updated_at_desc(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test sorting by updated_at descending (most recently modified first)."""
    import asyncio

    # Create notes
    data1 = NoteCreate(title='First Note')
    n1 = await note_service.create(db_session, test_user.id, data1)
    await db_session.flush()

    await asyncio.sleep(0.01)

    data2 = NoteCreate(title='Second Note')
    n2 = await note_service.create(db_session, test_user.id, data2)
    await db_session.flush()

    await asyncio.sleep(0.01)  # Small delay before updating

    # Update first note via service (makes it most recently modified)
    await note_service.update(
        db_session, test_user.id, n1.id, NoteUpdate(title='Updated Title'),
    )
    await db_session.flush()

    notes, total = await note_service.search(
        db_session, test_user.id, sort_by='updated_at', sort_order='desc',
    )

    assert total == 2
    assert notes[0].id == n1.id  # Most recently modified
    assert notes[1].id == n2.id


async def test__search_notes__sort_by_title_asc(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test sorting by title ascending (alphabetical)."""
    n1 = Note(user_id=test_user.id, title='Zebra Note')
    n2 = Note(user_id=test_user.id, title='Apple Note')
    n3 = Note(user_id=test_user.id, title='Mango Note')
    db_session.add_all([n1, n2, n3])
    await db_session.flush()

    notes, total = await note_service.search(
        db_session, test_user.id, sort_by='title', sort_order='asc',
    )

    assert total == 3
    assert notes[0].title == 'Apple Note'
    assert notes[1].title == 'Mango Note'
    assert notes[2].title == 'Zebra Note'


# =============================================================================
# Filter Expression Tests (for ContentList filtering)
# =============================================================================


async def test__search_notes__filter_expression_single_group_and(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test filter expression with single group (AND logic)."""
    # Create notes with different tag combinations
    data1 = NoteCreate(
        title='Work Priority Note',
        tags=['work', 'priority'],
    )
    n1 = await note_service.create(db_session, test_user.id, data1)

    data2 = NoteCreate(
        title='Work Only Note',
        tags=['work'],
    )
    await note_service.create(db_session, test_user.id, data2)

    data3 = NoteCreate(
        title='Priority Only Note',
        tags=['priority'],
    )
    await note_service.create(db_session, test_user.id, data3)

    await db_session.flush()

    # Filter: must have BOTH work AND priority
    filter_expression = {
        'groups': [{'tags': ['work', 'priority'], 'operator': 'AND'}],
        'group_operator': 'OR',
    }

    notes, total = await note_service.search(
        db_session, test_user.id, filter_expression=filter_expression,
    )

    assert total == 1
    assert notes[0].id == n1.id


async def test__search_notes__filter_expression_multiple_groups_or(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test filter expression with multiple groups (OR logic between groups)."""
    # Create notes
    data1 = NoteCreate(
        title='Work Priority Note',
        tags=['work', 'priority'],
    )
    n1 = await note_service.create(db_session, test_user.id, data1)

    data2 = NoteCreate(
        title='Urgent Note',
        tags=['urgent'],
    )
    n2 = await note_service.create(db_session, test_user.id, data2)

    data3 = NoteCreate(
        title='Personal Note',
        tags=['personal'],
    )
    await note_service.create(db_session, test_user.id, data3)

    await db_session.flush()

    # Filter: (work AND priority) OR (urgent)
    filter_expression = {
        'groups': [
            {'tags': ['work', 'priority'], 'operator': 'AND'},
            {'tags': ['urgent'], 'operator': 'AND'},
        ],
        'group_operator': 'OR',
    }

    notes, total = await note_service.search(
        db_session, test_user.id, filter_expression=filter_expression,
    )

    assert total == 2
    ids = [n.id for n in notes]
    assert n1.id in ids
    assert n2.id in ids


async def test__search_notes__filter_expression_with_text_search(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test filter expression combined with text search."""
    data1 = NoteCreate(
        title='Python Guide',
        tags=['work', 'coding'],
    )
    n1 = await note_service.create(db_session, test_user.id, data1)

    data2 = NoteCreate(
        title='JavaScript Guide',
        tags=['work', 'coding'],
    )
    await note_service.create(db_session, test_user.id, data2)

    await db_session.flush()

    # Filter by tags AND text search
    filter_expression = {
        'groups': [{'tags': ['work', 'coding'], 'operator': 'AND'}],
        'group_operator': 'OR',
    }

    notes, total = await note_service.search(
        db_session, test_user.id, query='python', filter_expression=filter_expression,
    )

    assert total == 1
    assert notes[0].id == n1.id


# =============================================================================
# Update Note Tests
# =============================================================================


async def test__update_note__updates_title(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that update_note updates the title."""
    note_id = test_note.id

    updated = await note_service.update(
        db_session, test_user.id, note_id, NoteUpdate(title='New Title'),
    )

    assert updated is not None
    assert updated.title == 'New Title'


async def test__update_note__updates_description(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that update_note updates the description."""
    note_id = test_note.id

    updated = await note_service.update(
        db_session, test_user.id, note_id,
        NoteUpdate(description='New description'),
    )

    assert updated is not None
    assert updated.description == 'New description'


async def test__update_note__updates_content(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that update_note updates the content field."""
    note_id = test_note.id

    updated = await note_service.update(
        db_session, test_user.id, note_id,
        NoteUpdate(content='# New Content\n\nUpdated markdown.'),
    )

    assert updated is not None
    assert updated.content == '# New Content\n\nUpdated markdown.'


async def test__update_note__partial_update_preserves_other_fields(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that partial update only changes specified fields."""
    note_id = test_note.id
    original_title = test_note.title
    original_content = test_note.content

    updated = await note_service.update(
        db_session, test_user.id, note_id,
        NoteUpdate(description='Only description changed'),
    )

    assert updated is not None
    assert updated.description == 'Only description changed'
    assert updated.title == original_title
    assert updated.content == original_content


async def test__update_note__updates_tags(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that update_note updates tags."""
    data = NoteCreate(
        title='Tag Update Test',
        tags=['original-tag'],
    )
    note = await note_service.create(db_session, test_user.id, data)
    await db_session.flush()

    updated = await note_service.update(
        db_session, test_user.id, note.id,
        NoteUpdate(tags=['new-tag-1', 'new-tag-2']),
    )

    assert updated is not None
    tag_names = [t.name for t in updated.tag_objects]
    assert 'new-tag-1' in tag_names
    assert 'new-tag-2' in tag_names
    assert 'original-tag' not in tag_names


async def test__update_note__returns_none_for_nonexistent(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that update_note returns None for non-existent note."""
    result = await note_service.update(
        db_session, test_user.id, 99999,
        NoteUpdate(title='Will not work'),
    )
    assert result is None


async def test__update_note__updates_updated_at(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that update_note updates the updated_at timestamp."""
    import asyncio

    note_id = test_note.id
    original_updated_at = test_note.updated_at

    await asyncio.sleep(0.01)

    await note_service.update(
        db_session, test_user.id, note_id,
        NoteUpdate(title='Updated Title'),
    )
    await db_session.flush()
    await db_session.refresh(test_note)

    assert test_note.updated_at > original_updated_at


async def test__update_note__does_not_update_last_used_at(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that update_note does NOT update last_used_at."""
    import asyncio

    note_id = test_note.id
    original_last_used_at = test_note.last_used_at

    await asyncio.sleep(0.01)

    await note_service.update(
        db_session, test_user.id, note_id,
        NoteUpdate(title='Updated Title'),
    )
    await db_session.flush()
    await db_session.refresh(test_note)

    assert test_note.last_used_at == original_last_used_at


async def test__update_note__wrong_user_returns_none(
    db_session: AsyncSession,
    test_note: Note,
) -> None:
    """Test that update_note returns None for wrong user."""
    # Create another user
    other_user = User(auth0_id='other-user-notes-456', email='other-notes@example.com')
    db_session.add(other_user)
    await db_session.flush()

    # Try to update test_user's note as other_user
    result = await note_service.update(
        db_session, other_user.id, test_note.id,
        NoteUpdate(title='Hacked Title'),
    )

    assert result is None

    # Verify original note unchanged
    await db_session.refresh(test_note)
    assert test_note.title == 'Example Note'


async def test__update_note__can_update_archived_note(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """
    Test that update_note can update an already-archived note.

    This is important because the UI shows an edit button in the archived view,
    so users expect to be able to edit archived note metadata.
    """
    # Archive the note
    await note_service.archive(db_session, test_user.id, test_note.id)
    await db_session.flush()
    await db_session.refresh(test_note)

    # Verify it's archived
    assert test_note.is_archived is True

    # Try to update the archived note's title
    updated = await note_service.update(
        db_session, test_user.id, test_note.id,
        NoteUpdate(title='Updated Archived Title'),
    )

    # Should succeed - archived notes should be editable
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


# =============================================================================
# build_note_filter_from_expression Tests
# =============================================================================


def test__build_note_filter_from_expression__empty_groups_returns_empty() -> None:
    """Test that empty groups returns empty filter list."""
    filter_expression = {'groups': [], 'group_operator': 'OR'}
    result = build_tag_filter_from_expression(
        filter_expression=filter_expression,
        user_id=1,
        junction_table=note_tags,
        entity_id_column=Note.id,
    )
    assert result == []


def test__build_note_filter_from_expression__missing_groups_returns_empty() -> None:
    """Test that missing groups key returns empty filter list."""
    filter_expression = {'group_operator': 'OR'}
    result = build_tag_filter_from_expression(
        filter_expression=filter_expression,
        user_id=1,
        junction_table=note_tags,
        entity_id_column=Note.id,
    )
    assert result == []


def test__build_note_filter_from_expression__single_group_single_tag() -> None:
    """Test filter with single group containing single tag."""
    filter_expression = {
        'groups': [{'tags': ['python'], 'operator': 'AND'}],
        'group_operator': 'OR',
    }
    result = build_tag_filter_from_expression(
        filter_expression=filter_expression,
        user_id=1,
        junction_table=note_tags,
        entity_id_column=Note.id,
    )
    assert len(result) == 1
    # Result should be an EXISTS clause (can't easily inspect, but should be truthy)
    assert result[0] is not None


def test__build_note_filter_from_expression__single_group_multiple_tags() -> None:
    """Test filter with single group containing multiple tags (AND)."""
    filter_expression = {
        'groups': [{'tags': ['python', 'web'], 'operator': 'AND'}],
        'group_operator': 'OR',
    }
    result = build_tag_filter_from_expression(
        filter_expression=filter_expression,
        user_id=1,
        junction_table=note_tags,
        entity_id_column=Note.id,
    )
    assert len(result) == 1
    # Result should be an AND clause combining EXISTS for each tag
    assert result[0] is not None


def test__build_note_filter_from_expression__multiple_groups() -> None:
    """Test filter with multiple groups (OR between groups)."""
    filter_expression = {
        'groups': [
            {'tags': ['python'], 'operator': 'AND'},
            {'tags': ['javascript'], 'operator': 'AND'},
        ],
        'group_operator': 'OR',
    }
    result = build_tag_filter_from_expression(
        filter_expression=filter_expression,
        user_id=1,
        junction_table=note_tags,
        entity_id_column=Note.id,
    )
    assert len(result) == 1
    # Result should be an OR clause combining the two groups
    assert result[0] is not None


def test__build_note_filter_from_expression__group_with_empty_tags_skipped() -> None:
    """Test that groups with empty tags are skipped."""
    filter_expression = {
        'groups': [
            {'tags': [], 'operator': 'AND'},
            {'tags': ['python'], 'operator': 'AND'},
        ],
        'group_operator': 'OR',
    }
    result = build_tag_filter_from_expression(
        filter_expression=filter_expression,
        user_id=1,
        junction_table=note_tags,
        entity_id_column=Note.id,
    )
    # Should only have one condition (from the python tag group)
    assert len(result) == 1


def test__build_note_filter_from_expression__all_groups_empty_returns_empty() -> None:
    """Test that if all groups have empty tags, empty list is returned."""
    filter_expression = {
        'groups': [
            {'tags': [], 'operator': 'AND'},
            {'tags': [], 'operator': 'AND'},
        ],
        'group_operator': 'OR',
    }
    result = build_tag_filter_from_expression(
        filter_expression=filter_expression,
        user_id=1,
        junction_table=note_tags,
        entity_id_column=Note.id,
    )
    assert result == []


# =============================================================================
# is_archived Hybrid Property Tests
# =============================================================================


async def test__is_archived__returns_false_when_archived_at_is_none(
    db_session: AsyncSession,  # noqa: ARG001
    test_user: User,  # noqa: ARG001
    test_note: Note,
) -> None:
    """Test that is_archived returns False when archived_at is None."""
    assert test_note.archived_at is None
    assert test_note.is_archived is False


async def test__is_archived__returns_true_when_archived_at_is_past(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that is_archived returns True when archived_at is in the past."""
    await note_service.archive(db_session, test_user.id, test_note.id)
    await db_session.flush()
    await db_session.refresh(test_note)

    assert test_note.archived_at is not None
    assert test_note.is_archived is True


async def test__is_archived__returns_false_when_archived_at_is_future(
    db_session: AsyncSession,
    test_user: User,  # noqa: ARG001
    test_note: Note,
) -> None:
    """Test that is_archived returns False when archived_at is in the future (scheduled)."""
    from datetime import datetime, timedelta

    # Set archived_at to 1 day in the future
    future_time = datetime.now(UTC) + timedelta(days=1)
    test_note.archived_at = future_time
    await db_session.flush()
    await db_session.refresh(test_note)

    assert test_note.archived_at is not None
    assert test_note.is_archived is False


async def test__is_archived__sql_expression_filters_past_archived(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that is_archived SQL expression correctly filters archived notes."""
    from sqlalchemy import select

    # Create notes: active, archived (past), scheduled (future)
    active = Note(user_id=test_user.id, title='Active Note')
    past_archived = Note(user_id=test_user.id, title='Past Archived Note')
    future_scheduled = Note(user_id=test_user.id, title='Future Scheduled Note')

    db_session.add_all([active, past_archived, future_scheduled])
    await db_session.flush()

    # Archive one note (sets to now/past)
    await note_service.archive(db_session, test_user.id, past_archived.id)
    await db_session.flush()

    # Set future archive date on another
    from datetime import datetime, timedelta

    future_time = datetime.now(UTC) + timedelta(days=7)
    future_scheduled.archived_at = future_time
    await db_session.flush()

    # Query for archived notes using the hybrid property
    result = await db_session.execute(
        select(Note).where(
            Note.user_id == test_user.id,
            Note.is_archived,
        ),
    )
    archived_notes = list(result.scalars().all())

    # Only past_archived should be returned
    assert len(archived_notes) == 1
    assert archived_notes[0].title == 'Past Archived Note'


# =============================================================================
# Auto-Archive (Future-Dated archived_at) Tests
# =============================================================================


async def test__search_notes__future_scheduled_appears_in_active_view(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that notes with future archived_at appear in active view."""
    from datetime import datetime, timedelta

    # Create a note with future archived_at
    note = Note(user_id=test_user.id, title='Future Scheduled Note')
    note.archived_at = datetime.now(UTC) + timedelta(days=7)
    db_session.add(note)
    await db_session.flush()

    # Search active view
    notes, total = await note_service.search(db_session, test_user.id, view='active')

    assert total == 1
    assert notes[0].title == 'Future Scheduled Note'


async def test__search_notes__future_scheduled_not_in_archived_view(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that notes with future archived_at do NOT appear in archived view."""
    from datetime import datetime, timedelta

    # Create a note with future archived_at
    note = Note(user_id=test_user.id, title='Future Scheduled Note')
    note.archived_at = datetime.now(UTC) + timedelta(days=7)
    db_session.add(note)
    await db_session.flush()

    # Search archived view
    notes, total = await note_service.search(db_session, test_user.id, view='archived')

    assert total == 0
    assert notes == []


async def test__archive_note__overrides_future_scheduled_date(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that archive_note on future-scheduled note sets to now."""
    from datetime import datetime, timedelta

    # Create a note with future archived_at
    note = Note(user_id=test_user.id, title='Future Scheduled Note')
    future_date = datetime.now(UTC) + timedelta(days=7)
    note.archived_at = future_date
    db_session.add(note)
    await db_session.flush()

    # Archive it (should set to now, overriding the future date)
    archived = await note_service.archive(db_session, test_user.id, note.id)
    await db_session.flush()
    await db_session.refresh(archived)

    # Should now be archived (is_archived == True)
    assert archived.is_archived is True
    # archived_at should be different from the future date
    assert archived.archived_at < future_date


async def test__unarchive_note__fails_on_future_scheduled(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that unarchive_note fails on future-scheduled note."""
    from datetime import datetime, timedelta

    # Create a note with future archived_at
    note = Note(user_id=test_user.id, title='Future Scheduled Note')
    note.archived_at = datetime.now(UTC) + timedelta(days=7)
    db_session.add(note)
    await db_session.flush()

    # Try to unarchive - should raise InvalidStateError because it's not archived yet
    with pytest.raises(InvalidStateError) as exc_info:
        await note_service.unarchive(db_session, test_user.id, note.id)

    assert "not archived" in str(exc_info.value)


async def test__create_note__with_archived_at_future_date(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that create_note accepts archived_at for scheduling."""
    from datetime import datetime, timedelta

    future_date = datetime.now(UTC) + timedelta(days=7)
    data = NoteCreate(
        title='Scheduled Note',
        archived_at=future_date,
    )
    note = await note_service.create(db_session, test_user.id, data)

    assert note.archived_at is not None
    assert note.is_archived is False  # Not yet archived
    # Should appear in active view
    notes, total = await note_service.search(db_session, test_user.id, view='active')
    assert total == 1


async def test__create_note__with_archived_at_past_date(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that create_note with past archived_at creates immediately archived note."""
    from datetime import datetime, timedelta

    past_date = datetime.now(UTC) - timedelta(hours=1)
    data = NoteCreate(
        title='Immediately Archived Note',
        archived_at=past_date,
    )
    note = await note_service.create(db_session, test_user.id, data)

    assert note.archived_at is not None
    assert note.is_archived is True  # Already archived
    # Should appear in archived view
    notes, total = await note_service.search(db_session, test_user.id, view='archived')
    assert total == 1


async def test__update_note__can_set_archived_at(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that update_note can set archived_at for scheduling."""
    from datetime import datetime, timedelta

    future_date = datetime.now(UTC) + timedelta(days=7)
    updated = await note_service.update(
        db_session, test_user.id, test_note.id,
        NoteUpdate(archived_at=future_date),
    )

    assert updated is not None
    assert updated.archived_at is not None
    assert updated.is_archived is False  # Not yet archived


async def test__update_note__can_clear_archived_at(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that update_note can clear archived_at to cancel schedule."""
    from datetime import datetime, timedelta

    # Create a note with future archived_at
    future_date = datetime.now(UTC) + timedelta(days=7)
    data = NoteCreate(
        title='Scheduled Then Cleared Note',
        archived_at=future_date,
    )
    note = await note_service.create(db_session, test_user.id, data)
    await db_session.flush()

    # Clear the scheduled date
    updated = await note_service.update(
        db_session, test_user.id, note.id,
        NoteUpdate(archived_at=None),
    )

    assert updated is not None
    assert updated.archived_at is None
    assert updated.is_archived is False


# =============================================================================
# Text Search Tests
# =============================================================================


async def test__search_notes__text_search_in_title(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that text search finds matches in title."""
    n1 = Note(user_id=test_user.id, title='Python Programming Guide')
    n2 = Note(user_id=test_user.id, title='JavaScript Tutorial')
    db_session.add_all([n1, n2])
    await db_session.flush()

    notes, total = await note_service.search(db_session, test_user.id, query='python')

    assert total == 1
    assert notes[0].title == 'Python Programming Guide'


async def test__search_notes__text_search_in_description(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that text search finds matches in description."""
    n1 = Note(user_id=test_user.id, title='Note 1', description='Learn Python basics')
    n2 = Note(user_id=test_user.id, title='Note 2', description='JavaScript advanced')
    db_session.add_all([n1, n2])
    await db_session.flush()

    notes, total = await note_service.search(db_session, test_user.id, query='python')

    assert total == 1
    assert notes[0].title == 'Note 1'


async def test__search_notes__text_search_in_content(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that text search finds matches in content."""
    n1 = Note(
        user_id=test_user.id,
        title='Note 1',
        content='# Python\n\nThis is about Python programming.',
    )
    n2 = Note(
        user_id=test_user.id,
        title='Note 2',
        content='# JavaScript\n\nThis is about JavaScript.',
    )
    db_session.add_all([n1, n2])
    await db_session.flush()

    notes, total = await note_service.search(db_session, test_user.id, query='python')

    assert total == 1
    assert notes[0].title == 'Note 1'


async def test__search_notes__text_search_case_insensitive(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that text search is case insensitive."""
    n1 = Note(user_id=test_user.id, title='PYTHON Programming Guide')
    db_session.add(n1)
    await db_session.flush()

    notes, total = await note_service.search(db_session, test_user.id, query='python')

    assert total == 1
    assert notes[0].title == 'PYTHON Programming Guide'


# =============================================================================
# Tag Filtering Tests
# =============================================================================


async def test__search_notes__tag_filter_all_mode(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test tag filtering with tag_match='all' (must have ALL tags)."""
    data1 = NoteCreate(title='Both Tags', tags=['python', 'web'])
    n1 = await note_service.create(db_session, test_user.id, data1)

    data2 = NoteCreate(title='Python Only', tags=['python'])
    await note_service.create(db_session, test_user.id, data2)

    data3 = NoteCreate(title='Web Only', tags=['web'])
    await note_service.create(db_session, test_user.id, data3)

    await db_session.flush()

    notes, total = await note_service.search(
        db_session, test_user.id, tags=['python', 'web'], tag_match='all',
    )

    assert total == 1
    assert notes[0].id == n1.id


async def test__search_notes__tag_filter_any_mode(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test tag filtering with tag_match='any' (must have ANY tag)."""
    data1 = NoteCreate(title='Python Note', tags=['python'])
    n1 = await note_service.create(db_session, test_user.id, data1)

    data2 = NoteCreate(title='Web Note', tags=['web'])
    n2 = await note_service.create(db_session, test_user.id, data2)

    data3 = NoteCreate(title='Java Note', tags=['java'])
    await note_service.create(db_session, test_user.id, data3)

    await db_session.flush()

    notes, total = await note_service.search(
        db_session, test_user.id, tags=['python', 'web'], tag_match='any',
    )

    assert total == 2
    ids = [n.id for n in notes]
    assert n1.id in ids
    assert n2.id in ids


# =============================================================================
# Pagination Tests
# =============================================================================


async def test__search_notes__pagination_offset_and_limit(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test pagination with offset and limit."""
    # Create 5 notes
    for i in range(5):
        note = Note(user_id=test_user.id, title=f'Note {i}')
        db_session.add(note)
    await db_session.flush()

    # Get first page (2 items)
    notes, total = await note_service.search(
        db_session, test_user.id, offset=0, limit=2,
    )

    assert total == 5
    assert len(notes) == 2

    # Get second page
    notes, total = await note_service.search(
        db_session, test_user.id, offset=2, limit=2,
    )

    assert total == 5
    assert len(notes) == 2


async def test__search_notes__returns_total_before_pagination(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that total count is before pagination is applied."""
    # Create 10 notes
    for i in range(10):
        note = Note(user_id=test_user.id, title=f'Note {i}')
        db_session.add(note)
    await db_session.flush()

    # Get only 3 items
    notes, total = await note_service.search(
        db_session, test_user.id, offset=0, limit=3,
    )

    # Total should be 10, not 3
    assert total == 10
    assert len(notes) == 3


# =============================================================================
# User Isolation Tests
# =============================================================================


async def test__search_notes__excludes_other_users_notes(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that search only returns the current user's notes."""
    # Create another user
    other_user = User(auth0_id='other-user-isolation', email='other-isolation@example.com')
    db_session.add(other_user)
    await db_session.flush()

    # Create notes for both users
    note1 = Note(user_id=test_user.id, title='My Note')
    note2 = Note(user_id=other_user.id, title='Other User Note')
    db_session.add_all([note1, note2])
    await db_session.flush()

    # Search should only return test_user's note
    notes, total = await note_service.search(db_session, test_user.id)

    assert total == 1
    assert notes[0].title == 'My Note'


async def test__get_note__returns_none_for_other_users_note(
    db_session: AsyncSession,
) -> None:
    """Test that get_note returns None when trying to access another user's note."""
    # Create two users
    user1 = User(auth0_id='user1-isolation', email='user1-isolation@example.com')
    user2 = User(auth0_id='user2-isolation', email='user2-isolation@example.com')
    db_session.add_all([user1, user2])
    await db_session.flush()

    # Create note for user1
    note = Note(user_id=user1.id, title='User 1 Note')
    db_session.add(note)
    await db_session.flush()

    # Try to get user1's note as user2
    result = await note_service.get(db_session, user2.id, note.id)

    assert result is None
