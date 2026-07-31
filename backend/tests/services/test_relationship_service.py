"""Tests for the relationship service layer."""
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from core.tier_limits import Tier
from models.bookmark import Bookmark
from models.note import Note
from models.prompt import Prompt
from models.user import User
from schemas.relationship import RelationshipInput
from services.exceptions import (
    ContentNotFoundError,
    DuplicateRelationshipError,
    InvalidRelationshipError,
    QuotaExceededError,
)
from services.relationship_service import (
    canonical_pair,
    create_relationship,
    delete_relationship,
    delete_relationships_for_content,
    enrich_with_content_info,
    get_relationship,
    get_relationships_for_content,
    get_relationships_snapshot,
    sync_relationships_for_entity,
    update_relationship,
    validate_content_exists,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(external_auth_id='test-user-rel-svc', email='relsvc@test.com', tier=Tier.FREE.value)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def other_user(db_session: AsyncSession) -> User:
    """Create a second user for cross-user isolation tests."""
    user = User(external_auth_id='test-user-rel-svc-other', email='relsvc-other@test.com', tier=Tier.FREE.value)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def bookmark_a(db_session: AsyncSession, test_user: User) -> Bookmark:
    """Create test bookmark A."""
    bm = Bookmark(user_id=test_user.id, url='https://a.com/', title='Bookmark A')
    db_session.add(bm)
    await db_session.flush()
    await db_session.refresh(bm)
    return bm


@pytest.fixture
async def bookmark_b(db_session: AsyncSession, test_user: User) -> Bookmark:
    """Create test bookmark B."""
    bm = Bookmark(user_id=test_user.id, url='https://b.com/', title='Bookmark B')
    db_session.add(bm)
    await db_session.flush()
    await db_session.refresh(bm)
    return bm


@pytest.fixture
async def note_a(db_session: AsyncSession, test_user: User) -> Note:
    """Create test note A."""
    note = Note(user_id=test_user.id, title='Note A')
    db_session.add(note)
    await db_session.flush()
    await db_session.refresh(note)
    return note


@pytest.fixture
async def note_b(db_session: AsyncSession, test_user: User) -> Note:
    """Create test note B."""
    note = Note(user_id=test_user.id, title='Note B')
    db_session.add(note)
    await db_session.flush()
    await db_session.refresh(note)
    return note


@pytest.fixture
async def prompt_a(db_session: AsyncSession, test_user: User) -> Prompt:
    """Create test prompt A."""
    prompt = Prompt(user_id=test_user.id, name='prompt-a', title='Prompt A')
    db_session.add(prompt)
    await db_session.flush()
    await db_session.refresh(prompt)
    return prompt


@pytest.fixture
async def prompt_b(db_session: AsyncSession, test_user: User) -> Prompt:
    """Create test prompt B."""
    prompt = Prompt(user_id=test_user.id, name='prompt-b', title='Prompt B')
    db_session.add(prompt)
    await db_session.flush()
    await db_session.refresh(prompt)
    return prompt


# ---------------------------------------------------------------------------
# canonical_pair tests
# ---------------------------------------------------------------------------


class TestCanonicalPair:
    """Tests for the canonical_pair normalization function."""

    def test__canonical_pair__already_canonical_unchanged(self) -> None:
        """Pair already in canonical order is returned unchanged."""
        id_a, id_b = uuid4(), uuid4()
        # Force a < b by using known types
        result = canonical_pair('bookmark', id_a, 'note', id_b)
        assert result == ('bookmark', id_a, 'note', id_b)

    def test__canonical_pair__different_type_orders_by_type(self) -> None:
        """Different types are ordered lexicographically by type string."""
        id_a, id_b = uuid4(), uuid4()
        # 'note' > 'bookmark' lexicographically, so should swap
        result = canonical_pair('note', id_a, 'bookmark', id_b)
        assert result == ('bookmark', id_b, 'note', id_a)

    def test__canonical_pair__same_type_orders_by_id(self) -> None:
        """Same type falls back to str(id) comparison."""
        # Create UUIDs where we know the ordering
        id_small = UUID('00000000-0000-0000-0000-000000000001')
        id_large = UUID('ffffffff-ffff-ffff-ffff-ffffffffffff')
        # Pass large first — should swap to put small first
        result = canonical_pair('note', id_large, 'note', id_small)
        assert result == ('note', id_small, 'note', id_large)

    def test__canonical_pair__same_type_already_ordered(self) -> None:
        """Same type, already in order by ID."""
        id_small = UUID('00000000-0000-0000-0000-000000000001')
        id_large = UUID('ffffffff-ffff-ffff-ffff-ffffffffffff')
        result = canonical_pair('bookmark', id_small, 'bookmark', id_large)
        assert result == ('bookmark', id_small, 'bookmark', id_large)

    def test__canonical_pair__deterministic_uuid_format(self) -> None:
        """Canonical ordering is deterministic regardless of UUID generation."""
        id_a, id_b = uuid4(), uuid4()
        result1 = canonical_pair('note', id_a, 'bookmark', id_b)
        result2 = canonical_pair('bookmark', id_b, 'note', id_a)
        assert result1 == result2


# ---------------------------------------------------------------------------
# validate_content_exists tests
# ---------------------------------------------------------------------------


class TestValidateContentExists:
    """Tests for content existence validation."""

    async def test__validate_content_exists__bookmark_found(
        self, db_session: AsyncSession, test_user: User, bookmark_a: Bookmark,
    ) -> None:
        """Returns True for existing bookmark."""
        result = await validate_content_exists(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        assert result is True

    async def test__validate_content_exists__note_found(
        self, db_session: AsyncSession, test_user: User, note_a: Note,
    ) -> None:
        """Returns True for existing note."""
        result = await validate_content_exists(
            db_session, test_user.id, 'note', note_a.id,
        )
        assert result is True

    async def test__validate_content_exists__prompt_found(
        self, db_session: AsyncSession, test_user: User, prompt_a: Prompt,
    ) -> None:
        """Returns True for existing prompt."""
        result = await validate_content_exists(
            db_session, test_user.id, 'prompt', prompt_a.id,
        )
        assert result is True

    async def test__validate_content_exists__nonexistent_returns_false(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        """Returns False for non-existent content ID."""
        result = await validate_content_exists(
            db_session, test_user.id, 'bookmark', uuid4(),
        )
        assert result is False

    async def test__validate_content_exists__invalid_type_returns_false(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        """Returns False for invalid content type."""
        result = await validate_content_exists(
            db_session, test_user.id, 'invalid', uuid4(),
        )
        assert result is False

    async def test__validate_content_exists__soft_deleted_returns_false(
        self, db_session: AsyncSession, test_user: User, bookmark_a: Bookmark,
    ) -> None:
        """Returns False for soft-deleted content."""
        bookmark_a.deleted_at = func.now()
        await db_session.flush()

        result = await validate_content_exists(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        assert result is False

    async def test__validate_content_exists__archived_returns_true(
        self, db_session: AsyncSession, test_user: User, bookmark_a: Bookmark,
    ) -> None:
        """Returns True for archived content (archived is valid)."""
        bookmark_a.archived_at = func.now()
        await db_session.flush()

        result = await validate_content_exists(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        assert result is True

    async def test__validate_content_exists__other_user_returns_false(
        self, db_session: AsyncSession, other_user: User, bookmark_a: Bookmark,
    ) -> None:
        """Returns False when content belongs to a different user."""
        result = await validate_content_exists(
            db_session, other_user.id, 'bookmark', bookmark_a.id,
        )
        assert result is False


# ---------------------------------------------------------------------------
# create_relationship tests
# ---------------------------------------------------------------------------


class TestCreateRelationship:
    """Tests for relationship creation."""

    async def test__create_relationship__bookmark_to_bookmark(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, bookmark_b: Bookmark,
    ) -> None:
        """Can create relationship between two bookmarks."""
        rel = await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'bookmark', bookmark_b.id,
            'related',
        )
        assert rel.id is not None
        assert rel.user_id == test_user.id
        assert rel.relationship_type == 'related'

    async def test__create_relationship__bookmark_to_note(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Can create relationship between bookmark and note."""
        rel = await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id,
            'related',
        )
        assert rel.id is not None

    async def test__create_relationship__bookmark_to_prompt(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, prompt_a: Prompt,
    ) -> None:
        """Can create relationship between bookmark and prompt."""
        rel = await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'prompt', prompt_a.id,
            'related',
        )
        assert rel.id is not None

    async def test__create_relationship__note_to_bookmark(
        self, db_session: AsyncSession, test_user: User,
        note_a: Note, bookmark_a: Bookmark,
    ) -> None:
        """Can create relationship from note to bookmark."""
        rel = await create_relationship(
            db_session, test_user.id,
            'note', note_a.id, 'bookmark', bookmark_a.id,
            'related',
        )
        assert rel.id is not None

    async def test__create_relationship__note_to_note(
        self, db_session: AsyncSession, test_user: User,
        note_a: Note, note_b: Note,
    ) -> None:
        """Can create relationship between two notes."""
        rel = await create_relationship(
            db_session, test_user.id,
            'note', note_a.id, 'note', note_b.id,
            'related',
        )
        assert rel.id is not None

    async def test__create_relationship__note_to_prompt(
        self, db_session: AsyncSession, test_user: User,
        note_a: Note, prompt_a: Prompt,
    ) -> None:
        """Can create relationship between note and prompt."""
        rel = await create_relationship(
            db_session, test_user.id,
            'note', note_a.id, 'prompt', prompt_a.id,
            'related',
        )
        assert rel.id is not None

    async def test__create_relationship__prompt_to_bookmark(
        self, db_session: AsyncSession, test_user: User,
        prompt_a: Prompt, bookmark_a: Bookmark,
    ) -> None:
        """Can create relationship from prompt to bookmark."""
        rel = await create_relationship(
            db_session, test_user.id,
            'prompt', prompt_a.id, 'bookmark', bookmark_a.id,
            'related',
        )
        assert rel.id is not None

    async def test__create_relationship__prompt_to_note(
        self, db_session: AsyncSession, test_user: User,
        prompt_a: Prompt, note_a: Note,
    ) -> None:
        """Can create relationship from prompt to note."""
        rel = await create_relationship(
            db_session, test_user.id,
            'prompt', prompt_a.id, 'note', note_a.id,
            'related',
        )
        assert rel.id is not None

    async def test__create_relationship__prompt_to_prompt(
        self, db_session: AsyncSession, test_user: User,
        prompt_a: Prompt, prompt_b: Prompt,
    ) -> None:
        """Can create relationship between two prompts."""
        rel = await create_relationship(
            db_session, test_user.id,
            'prompt', prompt_a.id, 'prompt', prompt_b.id,
            'related',
        )
        assert rel.id is not None

    async def test__create_relationship__with_description(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Relationship can include a description."""
        rel = await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id,
            'related', description='Background reading',
        )
        assert rel.description == 'Background reading'

    async def test__create_relationship__description_optional(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Relationship description defaults to None."""
        rel = await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id,
            'related',
        )
        assert rel.description is None

    async def test__create_relationship__canonical_ordering(
        self, db_session: AsyncSession, test_user: User,
        note_a: Note, bookmark_a: Bookmark,
    ) -> None:
        """Bidirectional type normalizes source/target to canonical order."""
        # Pass note (n > b lexicographically) as source — should be swapped
        rel = await create_relationship(
            db_session, test_user.id,
            'note', note_a.id, 'bookmark', bookmark_a.id,
            'related',
        )
        # After canonical ordering: bookmark should be source, note should be target
        assert rel.source_type == 'bookmark'
        assert rel.source_id == bookmark_a.id
        assert rel.target_type == 'note'
        assert rel.target_id == note_a.id

    async def test__create_relationship__reverse_direction_deduplicates(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Creating B→A when A→B exists raises DuplicateRelationshipError."""
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id,
            'related',
        )
        with pytest.raises(DuplicateRelationshipError):
            await create_relationship(
                db_session, test_user.id,
                'note', note_a.id, 'bookmark', bookmark_a.id,
                'related',
            )

    async def test__create_relationship__duplicate_rejected(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Exact same relationship cannot be created twice."""
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id,
            'related',
        )
        with pytest.raises(DuplicateRelationshipError):
            await create_relationship(
                db_session, test_user.id,
                'bookmark', bookmark_a.id, 'note', note_a.id,
                'related',
            )

    async def test__create_relationship__self_reference_rejected_bookmark(
        self, db_session: AsyncSession, test_user: User, bookmark_a: Bookmark,
    ) -> None:
        """Self-reference for bookmark is rejected."""
        with pytest.raises(InvalidRelationshipError, match="same content"):
            await create_relationship(
                db_session, test_user.id,
                'bookmark', bookmark_a.id, 'bookmark', bookmark_a.id,
                'related',
            )

    async def test__create_relationship__self_reference_rejected_note(
        self, db_session: AsyncSession, test_user: User, note_a: Note,
    ) -> None:
        """Self-reference for note is rejected."""
        with pytest.raises(InvalidRelationshipError, match="same content"):
            await create_relationship(
                db_session, test_user.id,
                'note', note_a.id, 'note', note_a.id,
                'related',
            )

    async def test__create_relationship__self_reference_rejected_prompt(
        self, db_session: AsyncSession, test_user: User, prompt_a: Prompt,
    ) -> None:
        """Self-reference for prompt is rejected."""
        with pytest.raises(InvalidRelationshipError, match="same content"):
            await create_relationship(
                db_session, test_user.id,
                'prompt', prompt_a.id, 'prompt', prompt_a.id,
                'related',
            )

    async def test__create_relationship__source_not_found(
        self, db_session: AsyncSession, test_user: User, note_a: Note,
    ) -> None:
        """Non-existent source content raises ContentNotFoundError."""
        with pytest.raises(ContentNotFoundError) as exc_info:
            await create_relationship(
                db_session, test_user.id,
                'bookmark', uuid4(), 'note', note_a.id,
                'related',
            )
        assert exc_info.value.content_type == 'bookmark'

    async def test__create_relationship__target_not_found(
        self, db_session: AsyncSession, test_user: User, bookmark_a: Bookmark,
    ) -> None:
        """Non-existent target content raises ContentNotFoundError."""
        with pytest.raises(ContentNotFoundError) as exc_info:
            await create_relationship(
                db_session, test_user.id,
                'bookmark', bookmark_a.id, 'note', uuid4(),
                'related',
            )
        assert exc_info.value.content_type == 'note'

    async def test__create_relationship__soft_deleted_source_rejected(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Soft-deleted source content raises ContentNotFoundError."""
        bookmark_a.deleted_at = func.now()
        await db_session.flush()

        with pytest.raises(ContentNotFoundError):
            await create_relationship(
                db_session, test_user.id,
                'bookmark', bookmark_a.id, 'note', note_a.id,
                'related',
            )

    async def test__create_relationship__soft_deleted_target_rejected(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Soft-deleted target content raises ContentNotFoundError."""
        note_a.deleted_at = func.now()
        await db_session.flush()

        with pytest.raises(ContentNotFoundError):
            await create_relationship(
                db_session, test_user.id,
                'bookmark', bookmark_a.id, 'note', note_a.id,
                'related',
            )

    async def test__create_relationship__archived_source_allowed(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Archived source content is allowed."""
        bookmark_a.archived_at = func.now()
        await db_session.flush()

        rel = await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id,
            'related',
        )
        assert rel.id is not None

    async def test__create_relationship__archived_target_allowed(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Archived target content is allowed."""
        note_a.archived_at = func.now()
        await db_session.flush()

        rel = await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id,
            'related',
        )
        assert rel.id is not None

    async def test__create_relationship__different_user_content_rejected(
        self, db_session: AsyncSession,
        other_user: User, bookmark_a: Bookmark,
    ) -> None:
        """Content belonging to another user raises ContentNotFoundError."""
        # bookmark_a belongs to test_user; try to link from other_user's perspective
        note = Note(user_id=other_user.id, title='Other Note')
        db_session.add(note)
        await db_session.flush()
        await db_session.refresh(note)

        with pytest.raises(ContentNotFoundError):
            await create_relationship(
                db_session, other_user.id,
                'bookmark', bookmark_a.id, 'note', note.id,
                'related',
            )

    async def test__create_relationship__invalid_source_type_rejected(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        """Invalid source_type raises InvalidRelationshipError."""
        with pytest.raises(InvalidRelationshipError, match="Invalid source type"):
            await create_relationship(
                db_session, test_user.id,
                'invalid', uuid4(), 'note', uuid4(),
                'related',
            )

    async def test__create_relationship__invalid_target_type_rejected(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        """Invalid target_type raises InvalidRelationshipError."""
        with pytest.raises(InvalidRelationshipError, match="Invalid target type"):
            await create_relationship(
                db_session, test_user.id,
                'bookmark', uuid4(), 'invalid', uuid4(),
                'related',
            )

    async def test__create_relationship__invalid_relationship_type_rejected(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Invalid relationship_type raises InvalidRelationshipError."""
        with pytest.raises(InvalidRelationshipError, match="Invalid relationship type"):
            await create_relationship(
                db_session, test_user.id,
                'bookmark', bookmark_a.id, 'note', note_a.id,
                'invalid',
            )

    async def test__create__enforces_max_per_entity(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note, note_b: Note,
    ) -> None:
        """Exceeding max_per_entity raises QuotaExceededError."""
        # Create one relationship to reach the limit of 1
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id, 'related',
            max_per_entity=1,
        )
        # Second should fail
        with pytest.raises(QuotaExceededError, match="Relationship"):
            await create_relationship(
                db_session, test_user.id,
                'bookmark', bookmark_a.id, 'note', note_b.id, 'related',
                max_per_entity=1,
            )

    async def test__create__duplicate_at_limit_raises_duplicate_not_quota(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Retrying an existing relationship at the limit returns duplicate, not quota."""
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id, 'related',
            max_per_entity=1,
        )
        # At limit (1/1), retrying the same relationship should raise Duplicate, not Quota
        with pytest.raises(DuplicateRelationshipError):
            await create_relationship(
                db_session, test_user.id,
                'bookmark', bookmark_a.id, 'note', note_a.id, 'related',
                max_per_entity=1,
            )

    async def test__create__no_limit_when_max_per_entity_is_none(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note, note_b: Note,
    ) -> None:
        """No limit enforced when max_per_entity is None (default)."""
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id, 'related',
        )
        # Should succeed without limit
        rel = await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_b.id, 'related',
        )
        assert rel is not None


# ---------------------------------------------------------------------------
# get_relationship tests
# ---------------------------------------------------------------------------


class TestGetRelationship:
    """Tests for fetching a single relationship."""

    async def test__get_relationship__found(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Returns relationship when found."""
        created = await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id,
            'related',
        )
        fetched = await get_relationship(db_session, test_user.id, created.id)
        assert fetched is not None
        assert fetched.id == created.id

    async def test__get_relationship__not_found(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        """Returns None for non-existent ID."""
        result = await get_relationship(db_session, test_user.id, uuid4())
        assert result is None

    async def test__get_relationship__wrong_user(
        self, db_session: AsyncSession, test_user: User,
        other_user: User, bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Returns None when relationship belongs to another user."""
        created = await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id,
            'related',
        )
        result = await get_relationship(db_session, other_user.id, created.id)
        assert result is None


# ---------------------------------------------------------------------------
# update_relationship tests
# ---------------------------------------------------------------------------


class TestUpdateRelationship:
    """Tests for updating relationship metadata."""

    async def test__update_relationship__description(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Can update description."""
        rel = await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id,
            'related',
        )
        updated, changed = await update_relationship(
            db_session, test_user.id, rel.id,
            description='Updated description',
        )
        assert updated is not None
        assert updated.description == 'Updated description'
        assert changed is True

    async def test__update_relationship__clear_description(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Can set description to None."""
        rel = await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id,
            'related', description='Original',
        )
        updated, changed = await update_relationship(
            db_session, test_user.id, rel.id,
            description=None,
        )
        assert updated is not None
        assert updated.description is None
        assert changed is True

    async def test__update_relationship__no_change_when_not_provided(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Description unchanged when not provided (sentinel default)."""
        rel = await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id,
            'related', description='Keep this',
        )
        # Call without description keyword — uses sentinel default
        updated, changed = await update_relationship(db_session, test_user.id, rel.id)
        assert updated is not None
        assert updated.description == 'Keep this'
        assert changed is False

    async def test__update_relationship__bumps_updated_at(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Updating description bumps updated_at."""
        rel = await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id,
            'related',
        )
        original_updated_at = rel.updated_at

        updated, changed = await update_relationship(
            db_session, test_user.id, rel.id,
            description='New description',
        )
        assert updated is not None
        assert updated.updated_at > original_updated_at
        assert changed is True

    async def test__update_relationship__no_change_does_not_bump_updated_at(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Not providing description does not bump updated_at."""
        rel = await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id,
            'related',
        )
        original_updated_at = rel.updated_at

        updated, changed = await update_relationship(db_session, test_user.id, rel.id)
        assert updated is not None
        assert updated.updated_at == original_updated_at
        assert changed is False

    async def test__update_relationship__not_found(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        """Returns None for non-existent relationship."""
        result, changed = await update_relationship(
            db_session, test_user.id, uuid4(),
            description='Does not matter',
        )
        assert result is None
        assert changed is False


# ---------------------------------------------------------------------------
# delete_relationship tests
# ---------------------------------------------------------------------------


class TestDeleteRelationship:
    """Tests for deleting a single relationship."""

    async def test__delete_relationship__success(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Returns True and deletes the relationship."""
        rel = await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id,
            'related',
        )
        result = await delete_relationship(db_session, test_user.id, rel.id)
        assert result is True

        # Verify it's gone
        fetched = await get_relationship(db_session, test_user.id, rel.id)
        assert fetched is None

    async def test__delete_relationship__not_found(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        """Returns False for non-existent relationship."""
        result = await delete_relationship(db_session, test_user.id, uuid4())
        assert result is False

    async def test__delete_relationship__wrong_user(
        self, db_session: AsyncSession, test_user: User,
        other_user: User, bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Returns False when relationship belongs to another user."""
        rel = await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id,
            'related',
        )
        result = await delete_relationship(db_session, other_user.id, rel.id)
        assert result is False

        # Verify it still exists for the correct user
        fetched = await get_relationship(db_session, test_user.id, rel.id)
        assert fetched is not None


# ---------------------------------------------------------------------------
# get_relationships_for_content tests
# ---------------------------------------------------------------------------


class TestGetRelationshipsForContent:
    """Tests for querying relationships by content item."""

    async def test__get_relationships__related_from_source(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Querying from the stored source returns the relationship."""
        rel = await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id,
            'related',
        )
        results, total = await get_relationships_for_content(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        assert len(results) == 1
        assert total == 1
        assert results[0].id == rel.id

    async def test__get_relationships__related_from_target(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Querying from the stored target returns the relationship."""
        rel = await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id,
            'related',
        )
        results, _ = await get_relationships_for_content(
            db_session, test_user.id, 'note', note_a.id,
        )
        assert len(results) == 1
        assert results[0].id == rel.id

    async def test__get_relationships__related_bidirectional(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Same relationship returned when querying from either side."""
        rel = await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id,
            'related',
        )
        from_source, _ = await get_relationships_for_content(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        from_target, _ = await get_relationships_for_content(
            db_session, test_user.id, 'note', note_a.id,
        )
        assert len(from_source) == 1
        assert len(from_target) == 1
        assert from_source[0].id == from_target[0].id == rel.id

    async def test__get_relationships__empty_result(
        self, db_session: AsyncSession, test_user: User, bookmark_a: Bookmark,
    ) -> None:
        """Returns empty list when no relationships exist."""
        results, total = await get_relationships_for_content(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        assert results == []
        assert total == 0

    async def test__get_relationships__nonexistent_content_returns_empty(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        """Returns empty list for non-existent content ID (not 404)."""
        results, _ = await get_relationships_for_content(
            db_session, test_user.id, 'bookmark', uuid4(),
        )
        assert results == []

    async def test__get_relationships__filter_by_type(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Can filter by relationship_type."""
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id,
            'related',
        )
        # Filter for 'related' should return it
        results, _ = await get_relationships_for_content(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
            relationship_type='related',
        )
        assert len(results) == 1

        # Filter for non-existent type should return nothing
        results, _ = await get_relationships_for_content(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
            relationship_type='references',
        )
        assert len(results) == 0

    async def test__get_relationships__multiple_relationships(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note, note_b: Note, prompt_a: Prompt,
    ) -> None:
        """Returns all relationships for an item across types."""
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id,
            'related',
        )
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_b.id,
            'related',
        )
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'prompt', prompt_a.id,
            'related',
        )
        results, total = await get_relationships_for_content(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        assert len(results) == 3
        assert total == 3

    async def test__get_relationships__ordered_by_created_at_desc(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note, note_b: Note,
    ) -> None:
        """Results are ordered by created_at DESC."""
        rel1 = await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id,
            'related',
        )
        rel2 = await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_b.id,
            'related',
        )
        results, _ = await get_relationships_for_content(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        # Most recently created first
        assert results[0].id == rel2.id
        assert results[1].id == rel1.id

    async def test__get_relationships__cross_user_isolation(
        self, db_session: AsyncSession, test_user: User,
        other_user: User, bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Relationships are isolated by user — other user sees nothing."""
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id,
            'related',
        )
        results, _ = await get_relationships_for_content(
            db_session, other_user.id, 'bookmark', bookmark_a.id,
        )
        assert results == []


# ---------------------------------------------------------------------------
# delete_relationships_for_content tests
# ---------------------------------------------------------------------------


class TestDeleteRelationshipsForContent:
    """Tests for bulk cleanup when content is permanently deleted."""

    async def test__delete_relationships_for_content__as_source(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note, note_b: Note,
    ) -> None:
        """Deletes all relationships where content is source."""
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id,
            'related',
        )
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_b.id,
            'related',
        )
        count = await delete_relationships_for_content(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        assert count == 2

        # Verify they're gone
        results, _ = await get_relationships_for_content(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        assert results == []

    async def test__delete_relationships_for_content__as_target(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, bookmark_b: Bookmark, note_a: Note,
    ) -> None:
        """Deletes all relationships where content is target."""
        # note_a is target in canonical order (bookmark < note)
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id,
            'related',
        )
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_b.id, 'note', note_a.id,
            'related',
        )
        count = await delete_relationships_for_content(
            db_session, test_user.id, 'note', note_a.id,
        )
        assert count == 2

    async def test__delete_relationships_for_content__mixed_source_and_target(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note, prompt_a: Prompt,
    ) -> None:
        """Deletes relationships where content is either source or target."""
        # note_a as target (bookmark < note canonical)
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id,
            'related',
        )
        # note_a as source (note < prompt canonical)
        await create_relationship(
            db_session, test_user.id,
            'note', note_a.id, 'prompt', prompt_a.id,
            'related',
        )
        count = await delete_relationships_for_content(
            db_session, test_user.id, 'note', note_a.id,
        )
        assert count == 2

    async def test__delete_relationships_for_content__no_relationships(
        self, db_session: AsyncSession, test_user: User, bookmark_a: Bookmark,
    ) -> None:
        """Returns 0 when content has no relationships."""
        count = await delete_relationships_for_content(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        assert count == 0

    async def test__delete_relationships_for_content__user_scoped(
        self, db_session: AsyncSession, test_user: User,
        other_user: User, bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Only deletes relationships for the specified user."""
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id,
            'related',
        )
        # Other user's cleanup should not affect test_user's relationships
        count = await delete_relationships_for_content(
            db_session, other_user.id, 'bookmark', bookmark_a.id,
        )
        assert count == 0

        # Original relationship still exists
        results, _ = await get_relationships_for_content(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        assert len(results) == 1


class TestEnrichWithContentInfo:
    """Tests for enrich_with_content_info batch resolution."""

    async def test__enrich__future_archived_at_not_flagged_as_archived(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """A note with archived_at in the future should return archived=False."""
        # Set archived_at to 7 days in the future (scheduled, not yet archived)
        note_a.archived_at = datetime.now(UTC) + timedelta(days=7)
        await db_session.flush()

        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id,
            'related',
        )

        rels, _ = await get_relationships_for_content(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        enriched = await enrich_with_content_info(db_session, test_user.id, rels)

        assert len(enriched) == 1
        item = enriched[0]
        # Find the note side — should NOT be archived
        if item.source_type == 'note':
            assert item.source_archived is False
        else:
            assert item.target_archived is False

    async def test__enrich__past_archived_at_flagged_as_archived(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """A note with archived_at in the past should return archived=True."""
        note_a.archived_at = datetime.now(UTC) - timedelta(days=1)
        await db_session.flush()

        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id,
            'related',
        )

        rels, _ = await get_relationships_for_content(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        enriched = await enrich_with_content_info(db_session, test_user.id, rels)

        assert len(enriched) == 1
        item = enriched[0]
        if item.source_type == 'note':
            assert item.source_archived is True
        else:
            assert item.target_archived is True

    async def test__enrich__empty_list_returns_empty(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        """Enriching an empty list returns an empty list without DB queries."""
        result = await enrich_with_content_info(db_session, test_user.id, [])
        assert result == []

    async def test__enrich__prompt_name_populated_for_prompts(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, prompt_a: Prompt,
    ) -> None:
        """Prompt side has prompt_name set; bookmark side has prompt_name=None."""
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'prompt', prompt_a.id, 'related',
        )
        rels, _ = await get_relationships_for_content(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        enriched = await enrich_with_content_info(db_session, test_user.id, rels)

        assert len(enriched) == 1
        item = enriched[0]
        # Canonical order: bookmark < prompt, so bookmark=source, prompt=target
        assert item.source_prompt_name is None
        assert item.target_prompt_name == 'prompt-a'

    async def test__enrich__prompt_name_null_for_non_prompts(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Bookmark↔note relationship has prompt_name=None on both sides."""
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id, 'related',
        )
        rels, _ = await get_relationships_for_content(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        enriched = await enrich_with_content_info(db_session, test_user.id, rels)

        assert len(enriched) == 1
        item = enriched[0]
        assert item.source_prompt_name is None
        assert item.target_prompt_name is None

    async def test__enrich__prompt_title_and_name_both_populated(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, prompt_a: Prompt,
    ) -> None:
        """Prompt with both title and name returns both fields independently."""
        # prompt_a has title='Prompt A' and name='prompt-a'
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'prompt', prompt_a.id, 'related',
        )
        rels, _ = await get_relationships_for_content(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        enriched = await enrich_with_content_info(db_session, test_user.id, rels)

        assert len(enriched) == 1
        item = enriched[0]
        # Canonical: bookmark=source, prompt=target
        assert item.target_title == 'Prompt A'
        assert item.target_prompt_name == 'prompt-a'


# ---------------------------------------------------------------------------
# get_relationships_snapshot
# ---------------------------------------------------------------------------


class TestGetRelationshipsSnapshot:
    """Tests for get_relationships_snapshot()."""

    async def test__snapshot__empty_when_no_relationships(
        self, db_session: AsyncSession, test_user: User, bookmark_a: Bookmark,
    ) -> None:
        """Snapshot of entity with no relationships returns empty list."""
        result = await get_relationships_snapshot(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        assert result == []

    async def test__snapshot__returns_target_perspective(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Snapshot from bookmark's perspective shows note as target."""
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id, 'related',
        )
        result = await get_relationships_snapshot(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        assert len(result) == 1
        assert result[0]['target_type'] == 'note'
        assert result[0]['target_id'] == str(note_a.id)
        assert result[0]['relationship_type'] == 'related'
        assert result[0]['description'] is None

    async def test__snapshot__perspective_when_entity_is_on_target_side(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """When entity is stored as target (due to canonical ordering), snapshot still resolves correctly."""
        # note > bookmark lexicographically, so canonical stores bookmark as source
        # Querying from note's perspective should still show bookmark as "target"
        await create_relationship(
            db_session, test_user.id,
            'note', note_a.id, 'bookmark', bookmark_a.id, 'related',
        )
        result = await get_relationships_snapshot(
            db_session, test_user.id, 'note', note_a.id,
        )
        assert len(result) == 1
        assert result[0]['target_type'] == 'bookmark'
        assert result[0]['target_id'] == str(bookmark_a.id)

    async def test__snapshot__sorted_deterministically(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note, note_b: Note, prompt_a: Prompt,
    ) -> None:
        """Multiple relationships are sorted by (target_type, target_id, relationship_type)."""
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'prompt', prompt_a.id, 'related',
        )
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id, 'related',
        )
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_b.id, 'related',
        )

        result = await get_relationships_snapshot(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )

        assert len(result) == 3
        # note < prompt lexicographically, then sorted by target_id within type
        types = [r['target_type'] for r in result]
        assert types[0] == 'note'
        assert types[1] == 'note'
        assert types[2] == 'prompt'

    async def test__snapshot__includes_description(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Snapshot includes description field."""
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id, 'related',
            description='See also',
        )
        result = await get_relationships_snapshot(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        assert result[0]['description'] == 'See also'

    async def test__snapshot__stable_across_calls(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note, note_b: Note,
    ) -> None:
        """Calling snapshot twice returns identical results (stable sorting)."""
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_b.id, 'related',
        )
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id, 'related',
        )

        snap1 = await get_relationships_snapshot(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        snap2 = await get_relationships_snapshot(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        assert snap1 == snap2


# ---------------------------------------------------------------------------
# sync_relationships_for_entity
# ---------------------------------------------------------------------------


class TestSyncRelationshipsForEntity:
    """Tests for sync_relationships_for_entity()."""

    async def test__sync__adds_new_relationships(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Syncing with a desired set creates new relationships."""
        desired = [
            RelationshipInput(target_type='note', target_id=note_a.id, relationship_type='related'),
        ]
        await sync_relationships_for_entity(
            db_session, test_user.id, 'bookmark', bookmark_a.id, desired,
        )

        _rels, count = await get_relationships_for_content(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        assert count == 1

    async def test__sync__removes_extra_relationships(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note, note_b: Note,
    ) -> None:
        """Syncing with a smaller set removes extra relationships."""
        # Create two relationships
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id, 'related',
        )
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_b.id, 'related',
        )

        # Sync to keep only note_a
        desired = [
            RelationshipInput(target_type='note', target_id=note_a.id, relationship_type='related'),
        ]
        await sync_relationships_for_entity(
            db_session, test_user.id, 'bookmark', bookmark_a.id, desired,
        )

        snapshot = await get_relationships_snapshot(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        assert len(snapshot) == 1
        assert snapshot[0]['target_id'] == str(note_a.id)

    async def test__sync__empty_list_clears_all(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Syncing with empty list removes all relationships."""
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id, 'related',
        )
        await sync_relationships_for_entity(
            db_session, test_user.id, 'bookmark', bookmark_a.id, [],
        )

        snapshot = await get_relationships_snapshot(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        assert snapshot == []

    async def test__sync__noop_when_already_matching(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Syncing with the same set produces no changes."""
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id, 'related',
        )

        desired = [
            RelationshipInput(target_type='note', target_id=note_a.id, relationship_type='related'),
        ]
        await sync_relationships_for_entity(
            db_session, test_user.id, 'bookmark', bookmark_a.id, desired,
        )

        snapshot = await get_relationships_snapshot(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        assert len(snapshot) == 1

    async def test__sync__mixed_adds_and_removes(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note, note_b: Note, prompt_a: Prompt,
    ) -> None:
        """Syncing can add and remove in one operation."""
        # Start with note_a
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id, 'related',
        )

        # Sync to note_b + prompt_a (remove note_a, add note_b + prompt_a)
        desired = [
            RelationshipInput(target_type='note', target_id=note_b.id, relationship_type='related'),
            RelationshipInput(target_type='prompt', target_id=prompt_a.id, relationship_type='related'),
        ]
        await sync_relationships_for_entity(
            db_session, test_user.id, 'bookmark', bookmark_a.id, desired,
        )

        snapshot = await get_relationships_snapshot(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        assert len(snapshot) == 2
        target_ids = {s['target_id'] for s in snapshot}
        assert str(note_b.id) in target_ids
        assert str(prompt_a.id) in target_ids

    async def test__sync__updates_description_for_existing(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Syncing updates description when relationship already exists but description changed."""
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id, 'related',
            description='Old desc',
        )

        desired = [
            RelationshipInput(
                target_type='note',
                target_id=note_a.id,
                relationship_type='related',
                description='New desc',
            ),
        ]
        await sync_relationships_for_entity(
            db_session, test_user.id, 'bookmark', bookmark_a.id, desired,
        )

        snapshot = await get_relationships_snapshot(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        assert snapshot[0]['description'] == 'New desc'

    async def test__sync__skips_nonexistent_targets(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """Syncing gracefully skips targets that don't exist (ContentNotFoundError caught per-item)."""
        fake_id = uuid4()
        desired = [
            RelationshipInput(target_type='note', target_id=note_a.id, relationship_type='related'),
            RelationshipInput(target_type='note', target_id=fake_id, relationship_type='related'),
        ]
        await sync_relationships_for_entity(
            db_session, test_user.id, 'bookmark', bookmark_a.id, desired,
            skip_missing_targets=True,
        )

        # Only the valid one should be created
        snapshot = await get_relationships_snapshot(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        assert len(snapshot) == 1
        assert snapshot[0]['target_id'] == str(note_a.id)

    async def test__sync__raises_on_nonexistent_target_by_default(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark,
    ) -> None:
        """Syncing with default skip_missing_targets=False raises ContentNotFoundError."""
        fake_id = uuid4()
        desired = [
            RelationshipInput(target_type='note', target_id=fake_id, relationship_type='related'),
        ]
        with pytest.raises(ContentNotFoundError):
            await sync_relationships_for_entity(
                db_session, test_user.id, 'bookmark', bookmark_a.id, desired,
            )

    async def test__sync__handles_duplicate_gracefully(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note,
    ) -> None:
        """If a relationship already exists (race condition), sync catches DuplicateRelationshipError."""
        # Pre-create the relationship
        await create_relationship(
            db_session, test_user.id,
            'bookmark', bookmark_a.id, 'note', note_a.id, 'related',
        )

        # Sync from note_a's perspective (will try to create the same link in reverse,
        # which canonical ordering makes duplicate)
        desired = [
            RelationshipInput(target_type='bookmark', target_id=bookmark_a.id, relationship_type='related'),
        ]
        # Should not raise
        await sync_relationships_for_entity(
            db_session, test_user.id, 'note', note_a.id, desired,
        )

        # Relationship still exists
        snapshot = await get_relationships_snapshot(
            db_session, test_user.id, 'note', note_a.id,
        )
        assert len(snapshot) == 1

    async def test__sync__enforces_max_per_entity(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note, note_b: Note,
    ) -> None:
        """Sync rejects desired set that exceeds max_per_entity."""
        desired = [
            RelationshipInput(target_type='note', target_id=note_a.id, relationship_type='related'),
            RelationshipInput(target_type='note', target_id=note_b.id, relationship_type='related'),
        ]
        with pytest.raises(QuotaExceededError, match="Relationship"):
            await sync_relationships_for_entity(
                db_session, test_user.id, 'bookmark', bookmark_a.id, desired,
                max_per_entity=1,
            )

    async def test__sync__no_limit_when_max_per_entity_is_none(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note, note_b: Note,
    ) -> None:
        """No limit enforced when max_per_entity is None (default)."""
        desired = [
            RelationshipInput(target_type='note', target_id=note_a.id, relationship_type='related'),
            RelationshipInput(target_type='note', target_id=note_b.id, relationship_type='related'),
        ]
        await sync_relationships_for_entity(
            db_session, test_user.id, 'bookmark', bookmark_a.id, desired,
        )
        snapshot = await get_relationships_snapshot(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        assert len(snapshot) == 2

    async def test__sync__skips_limit_during_restore(
        self, db_session: AsyncSession, test_user: User,
        bookmark_a: Bookmark, note_a: Note, note_b: Note,
    ) -> None:
        """Restore (skip_missing_targets=True) bypasses the per-entity limit."""
        desired = [
            RelationshipInput(target_type='note', target_id=note_a.id, relationship_type='related'),
            RelationshipInput(target_type='note', target_id=note_b.id, relationship_type='related'),
        ]
        # Would fail with max_per_entity=1 normally, but restore skips the check
        await sync_relationships_for_entity(
            db_session, test_user.id, 'bookmark', bookmark_a.id, desired,
            skip_missing_targets=True,
            max_per_entity=1,
        )
        snapshot = await get_relationships_snapshot(
            db_session, test_user.id, 'bookmark', bookmark_a.id,
        )
        assert len(snapshot) == 2
