"""
Tests for note service layer functionality.

Tests the soft delete, archive, restore, and view filtering functionality
that was added to support the trash/archive features.
"""
import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4
import re

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import defer, selectinload

from core.tier_limits import Tier, TierLimits, get_tier_limits
from models.note import Note
from models.tag import note_tags
from models.user import User
from schemas.note import NoteCreate, NoteUpdate
from services.exceptions import FieldLimitExceededError, InvalidStateError, QuotaExceededError
from services.note_service import NoteService
from services.utils import build_tag_filter_from_expression, escape_ilike
from services.base_entity_service import CONTENT_PREVIEW_LENGTH


note_service = NoteService()
DEFAULT_LIMITS = get_tier_limits(Tier.DEV)


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(external_auth_id='test-user-notes-123', email='test-notes@example.com', tier=Tier.FREE.value)
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
async def test__restore_note__returns_none_for_nonexistent(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that restore returns None for non-existent note."""
    result = await note_service.restore(db_session, test_user.id, uuid4())
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
async def test__archive_note__returns_none_for_nonexistent(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that archive returns None for non-existent note."""
    result = await note_service.archive(db_session, test_user.id, uuid4())
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
async def test__unarchive_note__returns_none_for_nonexistent(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that unarchive returns None for non-existent note."""
    result = await note_service.unarchive(db_session, test_user.id, uuid4())
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
    result = await note_service.track_usage(db_session, test_user.id, uuid4())
    assert result is False


async def test__track_note_usage__works_on_archived_note(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that track_note_usage works on archived notes."""
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
    note = await note_service.create(db_session, test_user.id, data, DEFAULT_LIMITS)

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
    note = await note_service.create(db_session, test_user.id, data, DEFAULT_LIMITS)

    assert note.last_used_at == note.created_at


# =============================================================================
# Sort Tests
# =============================================================================


async def test__update_note__updates_description(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that update_note updates the description."""
    note_id = test_note.id

    updated = await note_service.update(
        db_session, test_user.id, note_id,
        NoteUpdate(description='New description'), DEFAULT_LIMITS,
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
        NoteUpdate(content='# New Content\n\nUpdated markdown.'), DEFAULT_LIMITS,
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
        NoteUpdate(description='Only description changed'), DEFAULT_LIMITS,
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
    note = await note_service.create(db_session, test_user.id, data, DEFAULT_LIMITS)
    await db_session.flush()

    updated = await note_service.update(
        db_session, test_user.id, note.id,
        NoteUpdate(tags=['new-tag-1', 'new-tag-2']), DEFAULT_LIMITS,
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
        db_session, test_user.id, uuid4(),
        NoteUpdate(title='Will not work'), DEFAULT_LIMITS,
    )
    assert result is None


async def test__update_note__updates_updated_at(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that update_note updates the updated_at timestamp."""
    note_id = test_note.id
    original_updated_at = test_note.updated_at

    await asyncio.sleep(0.01)

    await note_service.update(
        db_session, test_user.id, note_id,
        NoteUpdate(title='Updated Title'), DEFAULT_LIMITS,
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
    note_id = test_note.id
    original_last_used_at = test_note.last_used_at

    await asyncio.sleep(0.01)

    await note_service.update(
        db_session, test_user.id, note_id,
        NoteUpdate(title='Updated Title'), DEFAULT_LIMITS,
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
    other_user = User(external_auth_id='other-user-notes-456', email='other-notes@example.com', tier=Tier.FREE.value)
    db_session.add(other_user)
    await db_session.flush()

    # Try to update test_user's note as other_user
    result = await note_service.update(
        db_session, other_user.id, test_note.id,
        NoteUpdate(title='Hacked Title'), DEFAULT_LIMITS,
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
        NoteUpdate(title='Updated Archived Title'), DEFAULT_LIMITS,
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
        user_id=uuid4(),
        junction_table=note_tags,
        entity_id_column=Note.id,
    )
    assert result == []


def test__build_note_filter_from_expression__missing_groups_returns_empty() -> None:
    """Test that missing groups key returns empty filter list."""
    filter_expression = {'group_operator': 'OR'}
    result = build_tag_filter_from_expression(
        filter_expression=filter_expression,
        user_id=uuid4(),
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
        user_id=uuid4(),
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
        user_id=uuid4(),
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
        user_id=uuid4(),
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
        user_id=uuid4(),
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
        user_id=uuid4(),
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


async def test__archive_note__overrides_future_scheduled(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that archive_note on future-scheduled note sets to now."""
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
    # Create a note with future archived_at
    note = Note(user_id=test_user.id, title='Future Scheduled Note')
    note.archived_at = datetime.now(UTC) + timedelta(days=7)
    db_session.add(note)
    await db_session.flush()

    # Try to unarchive - should raise InvalidStateError because it's not archived yet
    with pytest.raises(InvalidStateError) as exc_info:
        await note_service.unarchive(db_session, test_user.id, note.id)

    assert "not archived" in str(exc_info.value)


async def test__update_note__can_set_archived_at(
    db_session: AsyncSession,
    test_user: User,
    test_note: Note,
) -> None:
    """Test that update_note can set archived_at for scheduling."""
    future_date = datetime.now(UTC) + timedelta(days=7)
    updated = await note_service.update(
        db_session, test_user.id, test_note.id,
        NoteUpdate(archived_at=future_date), DEFAULT_LIMITS,
    )

    assert updated is not None
    assert updated.archived_at is not None
    assert updated.is_archived is False  # Not yet archived


async def test__update_note__can_clear_archived_at(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that update_note can clear archived_at to cancel schedule."""
    # Create a note with future archived_at
    future_date = datetime.now(UTC) + timedelta(days=7)
    data = NoteCreate(
        title='Scheduled Then Cleared Note',
        archived_at=future_date,
    )
    note = await note_service.create(db_session, test_user.id, data, DEFAULT_LIMITS)
    await db_session.flush()

    # Clear the scheduled date
    updated = await note_service.update(
        db_session, test_user.id, note.id,
        NoteUpdate(archived_at=None), DEFAULT_LIMITS,
    )

    assert updated is not None
    assert updated.archived_at is None
    assert updated.is_archived is False


# =============================================================================
# Cascade Delete Tests
# =============================================================================


async def test__cascade_delete__user_deletion_removes_notes(
    db_session: AsyncSession,
) -> None:
    """Test that deleting a user removes all their notes."""
    # Create a user with notes
    user = User(external_auth_id="cascade-test-user-notes", email="cascade-notes@example.com", tier=Tier.FREE.value)
    db_session.add(user)
    await db_session.flush()

    await note_service.create(
        db_session, user.id, NoteCreate(title="Note 1", content="Test content"), DEFAULT_LIMITS,
    )
    await note_service.create(
        db_session, user.id, NoteCreate(title="Note 2", content="Test content"), DEFAULT_LIMITS,
    )
    await db_session.flush()

    # Delete the user
    await db_session.delete(user)
    await db_session.flush()

    # Verify notes are gone
    result = await db_session.execute(
        select(Note).where(Note.user_id == user.id),
    )
    assert result.scalars().all() == []


def test__search_query__defer_excludes_content_from_select() -> None:
    """
    Verify that defer() excludes content column from SELECT while computed columns work.

    This test ensures the SQL optimization in BaseEntityService.search() is working:
    - The full content column should NOT be in the SELECT list
    - content_length and content_preview should be computed via length() and left()

    If this test fails, it means content is being transferred from the database,
    defeating the performance optimization.
    """
    # Build the same query pattern used in BaseEntityService.search()
    query = (
        select(
            Note,
            func.length(Note.content).label("content_length"),
            func.left(Note.content, CONTENT_PREVIEW_LENGTH).label("content_preview"),
        )
        .options(
            defer(Note.content),
            selectinload(Note.tag_objects),
        )
        .where(Note.user_id == "some-uuid")
    )

    # Compile to PostgreSQL SQL
    compiled = query.compile(dialect=postgresql.dialect())
    sql = str(compiled)

    # The SQL should look like:
    # SELECT notes.user_id, notes.title, notes.description, ...,
    #        length(notes.content) AS content_length,
    #        left(notes.content, 500) AS content_preview
    # FROM notes WHERE ...
    #
    # Note: notes.content should NOT appear as a direct column selection

    # Split into SELECT clause and rest
    select_clause = sql.split(" FROM ", maxsplit=1)[0].upper()

    # content should appear in function calls (LENGTH, LEFT) but not as a standalone column
    # A standalone column would look like: "NOTES.CONTENT," or "NOTES.CONTENT AS"
    # We check that NOTES.CONTENT only appears within function parentheses

    # Count occurrences of NOTES.CONTENT
    content_occurrences = select_clause.count("NOTES.CONTENT")

    # It should appear exactly twice: once in LENGTH(), once in LEFT()
    assert content_occurrences == 2, (
        f"Expected notes.content to appear exactly 2 times (in LENGTH and LEFT), "
        f"but found {content_occurrences} occurrences. SQL: {sql}"
    )

    # Verify it appears within the function calls
    assert "LENGTH(NOTES.CONTENT)" in select_clause, (
        f"Expected LENGTH(notes.content) in SELECT clause. SQL: {sql}"
    )
    assert "LEFT(NOTES.CONTENT" in select_clause, (
        f"Expected LEFT(notes.content, ...) in SELECT clause. SQL: {sql}"
    )

    # Verify content is NOT a standalone selected column
    # A standalone column would have a comma before/after or be at the start
    # We check that "NOTES.CONTENT," doesn't appear outside of function calls
    # Match notes.content that is NOT preceded by ( (which would indicate a function call)
    standalone_content = re.search(r'(?<!\()NOTES\.CONTENT\s*,', select_clause)
    assert standalone_content is None, (
        f"Found standalone notes.content column in SELECT (defer not working). SQL: {sql}"
    )


# =============================================================================
# Tier Limits Enforcement Tests
# =============================================================================


async def test__create__quota_exceeded__raises(
    db_session: AsyncSession, test_user: User, low_limits: TierLimits,
) -> None:
    """Test that creating beyond max_notes raises QuotaExceededError."""
    for i in range(low_limits.max_notes):
        data = NoteCreate(title=f"Note {i}", content="content")
        await note_service.create(db_session, test_user.id, data, low_limits)
    data = NoteCreate(title="Over", content="content")
    with pytest.raises(QuotaExceededError, match=r"(?i)note"):
        await note_service.create(db_session, test_user.id, data, low_limits)


async def test__create__quota_counts_archived_and_deleted(
    db_session: AsyncSession, test_user: User, low_limits: TierLimits,
) -> None:
    """Test that archived and soft-deleted notes count toward quota."""
    n1 = await note_service.create(
        db_session, test_user.id, NoteCreate(title="Archived", content="c"), low_limits,
    )
    await note_service.archive(db_session, test_user.id, n1.id)

    n2 = await note_service.create(
        db_session, test_user.id, NoteCreate(title="Deleted", content="c"), low_limits,
    )
    await note_service.delete(db_session, test_user.id, n2.id)

    with pytest.raises(QuotaExceededError, match=r"(?i)note"):
        await note_service.create(
            db_session, test_user.id, NoteCreate(title="Over", content="c"), low_limits,
        )


async def test__create__title_exceeds_max_length__raises(
    db_session: AsyncSession, test_user: User, low_limits: TierLimits,
) -> None:
    """Test that title exceeding max_title_length raises FieldLimitExceededError."""
    data = NoteCreate(title="a" * (low_limits.max_title_length + 1), content="ok")
    with pytest.raises(FieldLimitExceededError, match=r"(?i)title"):
        await note_service.create(db_session, test_user.id, data, low_limits)


async def test__create__description_exceeds_max_length__raises(
    db_session: AsyncSession, test_user: User, low_limits: TierLimits,
) -> None:
    """Test that description exceeding max_description_length raises FieldLimitExceededError."""
    data = NoteCreate(
        title="ok", description="a" * (low_limits.max_description_length + 1), content="ok",
    )
    with pytest.raises(FieldLimitExceededError, match=r"(?i)description"):
        await note_service.create(db_session, test_user.id, data, low_limits)


async def test__create__content_exceeds_max_length__raises(
    db_session: AsyncSession, test_user: User, low_limits: TierLimits,
) -> None:
    """Test that content exceeding max_note_content_length raises FieldLimitExceededError."""
    data = NoteCreate(title="ok", content="a" * (low_limits.max_note_content_length + 1))
    with pytest.raises(FieldLimitExceededError, match=r"(?i)content"):
        await note_service.create(db_session, test_user.id, data, low_limits)


async def test__create__tag_name_exceeds_max_length__raises(
    db_session: AsyncSession, test_user: User, low_limits: TierLimits,
) -> None:
    """Test that tag name exceeding max_tag_name_length raises FieldLimitExceededError."""
    long_tag = "a" * (low_limits.max_tag_name_length + 1)
    data = NoteCreate(title="ok", content="ok", tags=[long_tag])
    with pytest.raises(FieldLimitExceededError, match=r"(?i)tag"):
        await note_service.create(db_session, test_user.id, data, low_limits)


async def test__update__title_exceeds_max_length__raises(
    db_session: AsyncSession, test_user: User, low_limits: TierLimits,
) -> None:
    """Test that updating title beyond max_title_length raises FieldLimitExceededError."""
    note = await note_service.create(
        db_session, test_user.id, NoteCreate(title="ok", content="c"), low_limits,
    )
    with pytest.raises(FieldLimitExceededError, match=r"(?i)title"):
        await note_service.update(
            db_session, test_user.id, note.id,
            NoteUpdate(title="a" * (low_limits.max_title_length + 1)), low_limits,
        )


async def test__update__description_exceeds_max_length__raises(
    db_session: AsyncSession, test_user: User, low_limits: TierLimits,
) -> None:
    """Test that updating description beyond limit raises FieldLimitExceededError."""
    note = await note_service.create(
        db_session, test_user.id, NoteCreate(title="ok", content="c"), low_limits,
    )
    with pytest.raises(FieldLimitExceededError, match=r"(?i)description"):
        await note_service.update(
            db_session, test_user.id, note.id,
            NoteUpdate(description="a" * (low_limits.max_description_length + 1)), low_limits,
        )


async def test__update__content_exceeds_max_length__raises(
    db_session: AsyncSession, test_user: User, low_limits: TierLimits,
) -> None:
    """Test that updating content beyond limit raises FieldLimitExceededError."""
    note = await note_service.create(
        db_session, test_user.id, NoteCreate(title="ok", content="c"), low_limits,
    )
    with pytest.raises(FieldLimitExceededError, match=r"(?i)content"):
        await note_service.update(
            db_session, test_user.id, note.id,
            NoteUpdate(content="a" * (low_limits.max_note_content_length + 1)), low_limits,
        )


async def test__update__tag_name_exceeds_max_length__raises(
    db_session: AsyncSession, test_user: User, low_limits: TierLimits,
) -> None:
    """Test that updating with oversized tag raises FieldLimitExceededError."""
    note = await note_service.create(
        db_session, test_user.id, NoteCreate(title="ok", content="c"), low_limits,
    )
    long_tag = "a" * (low_limits.max_tag_name_length + 1)
    with pytest.raises(FieldLimitExceededError, match=r"(?i)tag"):
        await note_service.update(
            db_session, test_user.id, note.id,
            NoteUpdate(tags=[long_tag]), low_limits,
        )
