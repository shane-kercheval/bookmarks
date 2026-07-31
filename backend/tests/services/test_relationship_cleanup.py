"""Tests for relationship cleanup on permanent delete via BaseEntityService."""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.tier_limits import Tier, get_tier_limits
from models.bookmark import Bookmark
from models.content_relationship import ContentRelationship
from models.note import Note
from models.prompt import Prompt
from models.user import User
from schemas.bookmark import BookmarkCreate
from schemas.note import NoteCreate
from schemas.prompt import PromptCreate
from services.bookmark_service import BookmarkService
from services.note_service import NoteService
from services.prompt_service import PromptService
from services.relationship_service import (
    create_relationship,
    get_relationships_for_content,
)

bookmark_service = BookmarkService()
note_service = NoteService()
prompt_service = PromptService()
DEFAULT_LIMITS = get_tier_limits(Tier.DEV)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(external_auth_id='test-user-rel-cleanup', email='rel-cleanup@test.com', tier=Tier.FREE.value)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def bookmark_a(db_session: AsyncSession, test_user: User) -> Bookmark:
    data = BookmarkCreate(url='https://a.com/', title='Bookmark A')
    return await bookmark_service.create(db_session, test_user.id, data, DEFAULT_LIMITS)


@pytest.fixture
async def bookmark_b(db_session: AsyncSession, test_user: User) -> Bookmark:
    data = BookmarkCreate(url='https://b.com/', title='Bookmark B')
    return await bookmark_service.create(db_session, test_user.id, data, DEFAULT_LIMITS)


@pytest.fixture
async def note_a(db_session: AsyncSession, test_user: User) -> Note:
    data = NoteCreate(title='Note A', content='Content A')
    return await note_service.create(db_session, test_user.id, data, DEFAULT_LIMITS)


@pytest.fixture
async def note_b(db_session: AsyncSession, test_user: User) -> Note:
    data = NoteCreate(title='Note B', content='Content B')
    return await note_service.create(db_session, test_user.id, data, DEFAULT_LIMITS)


@pytest.fixture
async def prompt_a(db_session: AsyncSession, test_user: User) -> Prompt:
    data = PromptCreate(name='prompt-a', title='Prompt A', content='Hello')
    return await prompt_service.create(db_session, test_user.id, data, DEFAULT_LIMITS)


@pytest.fixture
async def prompt_b(db_session: AsyncSession, test_user: User) -> Prompt:
    data = PromptCreate(name='prompt-b', title='Prompt B', content='World')
    return await prompt_service.create(db_session, test_user.id, data, DEFAULT_LIMITS)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _count_relationships(db: AsyncSession, user_id: object) -> int:
    """Count all relationships for a user."""
    result = await db.execute(
        select(ContentRelationship).where(ContentRelationship.user_id == user_id),
    )
    return len(result.scalars().all())


# ---------------------------------------------------------------------------
# Permanent delete removes relationships
# ---------------------------------------------------------------------------


class TestPermanentDeleteCascade:
    """Tests that permanent delete removes all relationships involving the entity."""

    async def test__delete_bookmark_permanent__removes_as_source(
        self,
        db_session: AsyncSession,
        test_user: User,
        bookmark_a: Bookmark,
        note_a: Note,
    ) -> None:
        """Permanent delete of bookmark removes relationships where it is source."""
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id, 'related',
        )
        assert await _count_relationships(db_session, test_user.id) == 1

        # Soft delete first, then permanent
        await bookmark_service.delete(db_session, test_user.id, bookmark_a.id)
        await bookmark_service.delete(db_session, test_user.id, bookmark_a.id, permanent=True)

        assert await _count_relationships(db_session, test_user.id) == 0

    async def test__delete_bookmark_permanent__removes_as_target(
        self,
        db_session: AsyncSession,
        test_user: User,
        bookmark_a: Bookmark,
        note_a: Note,
    ) -> None:
        """Permanent delete of bookmark removes relationships where it is target."""
        # note < bookmark lexicographically, so note is stored as source
        await create_relationship(
            db_session, test_user.id,
            'note', note_a.id, 'bookmark', bookmark_a.id, 'related',
        )
        assert await _count_relationships(db_session, test_user.id) == 1

        await bookmark_service.delete(db_session, test_user.id, bookmark_a.id)
        await bookmark_service.delete(db_session, test_user.id, bookmark_a.id, permanent=True)

        assert await _count_relationships(db_session, test_user.id) == 0

    async def test__delete_note_permanent__removes_as_source(
        self,
        db_session: AsyncSession,
        test_user: User,
        note_a: Note,
        bookmark_a: Bookmark,
    ) -> None:
        """Permanent delete of note removes relationships where it is source."""
        await create_relationship(
            db_session, test_user.id,
            'note', note_a.id, 'bookmark', bookmark_a.id, 'related',
        )
        assert await _count_relationships(db_session, test_user.id) == 1

        await note_service.delete(db_session, test_user.id, note_a.id)
        await note_service.delete(db_session, test_user.id, note_a.id, permanent=True)

        assert await _count_relationships(db_session, test_user.id) == 0

    async def test__delete_note_permanent__removes_as_target(
        self,
        db_session: AsyncSession,
        test_user: User,
        note_a: Note,
        bookmark_a: Bookmark,
    ) -> None:
        """Permanent delete of note removes relationships where it is target."""
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id, 'related',
        )
        assert await _count_relationships(db_session, test_user.id) == 1

        await note_service.delete(db_session, test_user.id, note_a.id)
        await note_service.delete(db_session, test_user.id, note_a.id, permanent=True)

        assert await _count_relationships(db_session, test_user.id) == 0

    async def test__delete_prompt_permanent__removes_relationships(
        self,
        db_session: AsyncSession,
        test_user: User,
        prompt_a: Prompt,
        note_a: Note,
    ) -> None:
        """Permanent delete of prompt removes all its relationships."""
        await create_relationship(
            db_session, test_user.id,
            'note', note_a.id, 'prompt', prompt_a.id, 'related',
        )
        assert await _count_relationships(db_session, test_user.id) == 1

        await prompt_service.delete(db_session, test_user.id, prompt_a.id)
        await prompt_service.delete(db_session, test_user.id, prompt_a.id, permanent=True)

        assert await _count_relationships(db_session, test_user.id) == 0

    async def test__delete_permanent__mixed_relationships(
        self,
        db_session: AsyncSession,
        test_user: User,
        bookmark_a: Bookmark,
        bookmark_b: Bookmark,
        note_a: Note,
        prompt_a: Prompt,
    ) -> None:
        """Permanent delete removes all relationships where entity is source or target."""
        # bookmark_a linked to note, prompt, and another bookmark
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id, 'related',
        )
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'prompt', prompt_a.id, 'related',
        )
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'bookmark', bookmark_b.id, 'related',
        )
        # Unrelated relationship that should survive
        await create_relationship(
            db_session, test_user.id,
            'note', note_a.id, 'prompt', prompt_a.id, 'related',
        )
        assert await _count_relationships(db_session, test_user.id) == 4

        await bookmark_service.delete(db_session, test_user.id, bookmark_a.id)
        await bookmark_service.delete(db_session, test_user.id, bookmark_a.id, permanent=True)

        # Only the note↔prompt relationship should remain
        assert await _count_relationships(db_session, test_user.id) == 1
        remaining, _ = await get_relationships_for_content(
            db_session, test_user.id, 'note', note_a.id,
        )
        assert len(remaining) == 1
        # The remaining one links note_a and prompt_a
        rel = remaining[0]
        assert {rel.source_id, rel.target_id} == {note_a.id, prompt_a.id}

    async def test__delete_bookmark_permanent__direct_without_soft_delete(
        self,
        db_session: AsyncSession,
        test_user: User,
        bookmark_a: Bookmark,
        note_a: Note,
    ) -> None:
        """Direct permanent delete (no prior soft delete) still removes relationships."""
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id, 'related',
        )
        assert await _count_relationships(db_session, test_user.id) == 1

        # Permanent delete without soft-deleting first
        result = await bookmark_service.delete(
            db_session, test_user.id, bookmark_a.id, permanent=True,
        )
        assert result is True
        await db_session.flush()

        # Entity gone
        query = select(Bookmark).where(Bookmark.id == bookmark_a.id)
        db_result = await db_session.execute(query)
        assert db_result.scalar_one_or_none() is None

        # Relationships gone
        assert await _count_relationships(db_session, test_user.id) == 0


# ---------------------------------------------------------------------------
# Soft delete preserves relationships
# ---------------------------------------------------------------------------


class TestSoftDeletePreservesRelationships:
    """Tests that soft delete and restore preserve relationships."""

    async def test__delete_bookmark_soft__preserves_relationships(
        self,
        db_session: AsyncSession,
        test_user: User,
        bookmark_a: Bookmark,
        note_a: Note,
    ) -> None:
        """Soft delete of bookmark preserves its relationships."""
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id, 'related',
        )

        await bookmark_service.delete(db_session, test_user.id, bookmark_a.id)

        assert await _count_relationships(db_session, test_user.id) == 1

    async def test__delete_note_soft__preserves_relationships(
        self,
        db_session: AsyncSession,
        test_user: User,
        note_a: Note,
        bookmark_a: Bookmark,
    ) -> None:
        """Soft delete of note preserves its relationships."""
        await create_relationship(
            db_session, test_user.id,
            'note', note_a.id, 'bookmark', bookmark_a.id, 'related',
        )

        await note_service.delete(db_session, test_user.id, note_a.id)

        assert await _count_relationships(db_session, test_user.id) == 1

    async def test__delete_prompt_soft__preserves_relationships(
        self,
        db_session: AsyncSession,
        test_user: User,
        prompt_a: Prompt,
        note_a: Note,
    ) -> None:
        """Soft delete of prompt preserves its relationships."""
        await create_relationship(
            db_session, test_user.id,
            'note', note_a.id, 'prompt', prompt_a.id, 'related',
        )

        await prompt_service.delete(db_session, test_user.id, prompt_a.id)

        assert await _count_relationships(db_session, test_user.id) == 1

    async def test__restore_bookmark__relationships_intact(
        self,
        db_session: AsyncSession,
        test_user: User,
        bookmark_a: Bookmark,
        note_a: Note,
    ) -> None:
        """Restoring a soft-deleted bookmark still has its relationships."""
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id, 'related',
        )

        # Soft delete then restore
        await bookmark_service.delete(db_session, test_user.id, bookmark_a.id)
        await bookmark_service.restore(db_session, test_user.id, bookmark_a.id)

        rels, _ = await get_relationships_for_content(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        assert len(rels) == 1

    async def test__restore_note__relationships_intact(
        self,
        db_session: AsyncSession,
        test_user: User,
        note_a: Note,
        prompt_a: Prompt,
    ) -> None:
        """Restoring a soft-deleted note still has its relationships."""
        await create_relationship(
            db_session, test_user.id,
            'note', note_a.id, 'prompt', prompt_a.id, 'related',
        )

        await note_service.delete(db_session, test_user.id, note_a.id)
        await note_service.restore(db_session, test_user.id, note_a.id)

        rels, _ = await get_relationships_for_content(
            db_session, test_user.id, 'note', note_a.id,
        )
        assert len(rels) == 1
