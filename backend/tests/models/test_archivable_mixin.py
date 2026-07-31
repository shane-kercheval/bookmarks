"""
Tests for ArchivableMixin functionality.

Tests the shared soft-delete and archive behavior across all archivable entities.
Uses Prompt as the test model since it's the simplest archivable entity.
"""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.bookmark import Bookmark
from models.note import Note
from models.prompt import Prompt
from models.user import User
from core.tier_limits import Tier


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(external_auth_id="test-user-mixin-123", email="mixin@example.com", tier=Tier.FREE.value)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


# =============================================================================
# is_archived Hybrid Property Tests (Python-side)
# =============================================================================


async def test__archivable_mixin__is_archived_false_when_none(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that is_archived returns False when archived_at is None."""
    prompt = Prompt(user_id=test_user.id, name="test-prompt")
    db_session.add(prompt)
    await db_session.flush()

    assert prompt.archived_at is None
    assert prompt.is_archived is False


async def test__archivable_mixin__is_archived_true_when_past(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that is_archived returns True when archived_at is in the past."""
    prompt = Prompt(user_id=test_user.id, name="test-prompt")
    prompt.archived_at = datetime.now(UTC) - timedelta(hours=1)
    db_session.add(prompt)
    await db_session.flush()

    assert prompt.is_archived is True


async def test__archivable_mixin__is_archived_false_when_future(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that is_archived returns False when archived_at is in the future."""
    prompt = Prompt(user_id=test_user.id, name="test-prompt")
    prompt.archived_at = datetime.now(UTC) + timedelta(days=1)
    db_session.add(prompt)
    await db_session.flush()

    assert prompt.is_archived is False


async def test__archivable_mixin__is_archived_handles_naive_datetime(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that is_archived handles naive datetimes by assuming UTC."""
    prompt = Prompt(user_id=test_user.id, name="test-prompt")
    # Use naive datetime (no timezone info) in the past
    prompt.archived_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
    db_session.add(prompt)
    await db_session.flush()

    # Should still work - naive datetime assumed to be UTC
    assert prompt.is_archived is True


# =============================================================================
# is_archived SQL Expression Tests
# =============================================================================


async def test__archivable_mixin__sql_expression_filters_archived(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that is_archived SQL expression correctly filters in queries."""
    # Create prompts: active, archived (past), scheduled (future)
    active = Prompt(user_id=test_user.id, name="active-prompt")
    archived = Prompt(user_id=test_user.id, name="archived-prompt")
    archived.archived_at = datetime.now(UTC) - timedelta(hours=1)
    scheduled = Prompt(user_id=test_user.id, name="scheduled-prompt")
    scheduled.archived_at = datetime.now(UTC) + timedelta(days=7)

    db_session.add_all([active, archived, scheduled])
    await db_session.flush()

    # Query for archived prompts using the hybrid expression
    result = await db_session.execute(
        select(Prompt).where(
            Prompt.user_id == test_user.id,
            Prompt.is_archived,
        ),
    )
    archived_prompts = list(result.scalars().all())

    # Only the past-archived prompt should be returned
    assert len(archived_prompts) == 1
    assert archived_prompts[0].name == "archived-prompt"


async def test__archivable_mixin__sql_expression_filters_not_archived(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that NOT is_archived SQL expression correctly filters non-archived."""
    # Create prompts: active, archived (past), scheduled (future)
    active = Prompt(user_id=test_user.id, name="active-prompt")
    archived = Prompt(user_id=test_user.id, name="archived-prompt")
    archived.archived_at = datetime.now(UTC) - timedelta(hours=1)
    scheduled = Prompt(user_id=test_user.id, name="scheduled-prompt")
    scheduled.archived_at = datetime.now(UTC) + timedelta(days=7)

    db_session.add_all([active, archived, scheduled])
    await db_session.flush()

    # Query for NOT archived prompts
    result = await db_session.execute(
        select(Prompt).where(
            Prompt.user_id == test_user.id,
            ~Prompt.is_archived,
        ),
    )
    not_archived = list(result.scalars().all())

    # Active and scheduled should be returned (not the past-archived one)
    assert len(not_archived) == 2
    names = {p.name for p in not_archived}
    assert names == {"active-prompt", "scheduled-prompt"}


# =============================================================================
# deleted_at Soft Delete Tests
# =============================================================================


async def test__archivable_mixin__deleted_at_defaults_to_none(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that deleted_at defaults to None."""
    prompt = Prompt(user_id=test_user.id, name="test-prompt")
    db_session.add(prompt)
    await db_session.flush()

    assert prompt.deleted_at is None


async def test__archivable_mixin__deleted_at_can_be_set(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that deleted_at can be set for soft delete."""
    prompt = Prompt(user_id=test_user.id, name="test-prompt")
    prompt.deleted_at = datetime.now(UTC)
    db_session.add(prompt)
    await db_session.flush()

    assert prompt.deleted_at is not None


# =============================================================================
# Cross-Model Consistency Tests
# =============================================================================


async def test__archivable_mixin__works_consistently_across_models(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that ArchivableMixin behavior is consistent across Bookmark, Note, Prompt."""
    past_time = datetime.now(UTC) - timedelta(hours=1)
    future_time = datetime.now(UTC) + timedelta(days=1)

    # Create one of each model type with past archived_at
    bookmark = Bookmark(
        user_id=test_user.id,
        url="https://example.com",
        archived_at=past_time,
    )
    note = Note(
        user_id=test_user.id,
        title="Test Note",
        archived_at=past_time,
    )
    prompt = Prompt(
        user_id=test_user.id,
        name="test-prompt",
        archived_at=past_time,
    )

    db_session.add_all([bookmark, note, prompt])
    await db_session.flush()

    # All should be archived
    assert bookmark.is_archived is True
    assert note.is_archived is True
    assert prompt.is_archived is True

    # Change to future - none should be archived
    bookmark.archived_at = future_time
    note.archived_at = future_time
    prompt.archived_at = future_time
    await db_session.flush()

    assert bookmark.is_archived is False
    assert note.is_archived is False
    assert prompt.is_archived is False

    # Set to None - none should be archived
    bookmark.archived_at = None
    note.archived_at = None
    prompt.archived_at = None
    await db_session.flush()

    assert bookmark.is_archived is False
    assert note.is_archived is False
    assert prompt.is_archived is False
