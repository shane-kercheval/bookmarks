"""Tests for the ContentRelationship model constraints."""
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.bookmark import Bookmark
from models.content_relationship import ContentRelationship
from models.note import Note
from models.user import User
from core.tier_limits import Tier


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(external_auth_id='test-user-relationship', email='rel@test.com', tier=Tier.FREE.value)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_bookmark(db_session: AsyncSession, test_user: User) -> Bookmark:
    """Create a test bookmark."""
    bookmark = Bookmark(user_id=test_user.id, url='https://example.com/', title='Example')
    db_session.add(bookmark)
    await db_session.flush()
    await db_session.refresh(bookmark)
    return bookmark


@pytest.fixture
async def test_note(db_session: AsyncSession, test_user: User) -> Note:
    """Create a test note."""
    note = Note(user_id=test_user.id, title='Test Note')
    db_session.add(note)
    await db_session.flush()
    await db_session.refresh(note)
    return note


class TestContentRelationshipModel:
    """Tests for ContentRelationship model creation and constraints."""

    async def test__create__basic_relationship(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_bookmark: Bookmark,
        test_note: Note,
    ) -> None:
        """ContentRelationship can be created between a bookmark and a note."""
        rel = ContentRelationship(
            user_id=test_user.id,
            source_type='bookmark',
            source_id=test_bookmark.id,
            target_type='note',
            target_id=test_note.id,
            relationship_type='related',
            description='Background reading',
        )
        db_session.add(rel)
        await db_session.flush()
        await db_session.refresh(rel)

        assert rel.id is not None
        assert rel.user_id == test_user.id
        assert rel.source_type == 'bookmark'
        assert rel.source_id == test_bookmark.id
        assert rel.target_type == 'note'
        assert rel.target_id == test_note.id
        assert rel.relationship_type == 'related'
        assert rel.description == 'Background reading'
        assert rel.created_at is not None
        assert rel.updated_at is not None

    async def test__create__without_description(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_bookmark: Bookmark,
        test_note: Note,
    ) -> None:
        """ContentRelationship can be created without a description."""
        rel = ContentRelationship(
            user_id=test_user.id,
            source_type='bookmark',
            source_id=test_bookmark.id,
            target_type='note',
            target_id=test_note.id,
            relationship_type='related',
        )
        db_session.add(rel)
        await db_session.flush()
        await db_session.refresh(rel)

        assert rel.description is None

    async def test__constraint__self_reference_rejected(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_bookmark: Bookmark,
    ) -> None:
        """Self-reference is rejected by check constraint."""
        rel = ContentRelationship(
            user_id=test_user.id,
            source_type='bookmark',
            source_id=test_bookmark.id,
            target_type='bookmark',
            target_id=test_bookmark.id,
            relationship_type='related',
        )
        db_session.add(rel)
        with pytest.raises(IntegrityError, match='ck_no_self_reference'):
            await db_session.flush()

    async def test__constraint__invalid_source_type_rejected(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Invalid source_type is rejected by check constraint."""
        rel = ContentRelationship(
            user_id=test_user.id,
            source_type='invalid',
            source_id=uuid4(),
            target_type='note',
            target_id=uuid4(),
            relationship_type='related',
        )
        db_session.add(rel)
        with pytest.raises(IntegrityError, match='ck_source_type'):
            await db_session.flush()

    async def test__constraint__invalid_target_type_rejected(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Invalid target_type is rejected by check constraint."""
        rel = ContentRelationship(
            user_id=test_user.id,
            source_type='bookmark',
            source_id=uuid4(),
            target_type='invalid',
            target_id=uuid4(),
            relationship_type='related',
        )
        db_session.add(rel)
        with pytest.raises(IntegrityError, match='ck_target_type'):
            await db_session.flush()

    async def test__constraint__invalid_relationship_type_rejected(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Invalid relationship_type is rejected by check constraint."""
        rel = ContentRelationship(
            user_id=test_user.id,
            source_type='bookmark',
            source_id=uuid4(),
            target_type='note',
            target_id=uuid4(),
            relationship_type='invalid',
        )
        db_session.add(rel)
        with pytest.raises(IntegrityError, match='ck_relationship_type'):
            await db_session.flush()

    async def test__constraint__duplicate_rejected(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_bookmark: Bookmark,
        test_note: Note,
    ) -> None:
        """Duplicate relationship is rejected by unique constraint."""
        rel1 = ContentRelationship(
            user_id=test_user.id,
            source_type='bookmark',
            source_id=test_bookmark.id,
            target_type='note',
            target_id=test_note.id,
            relationship_type='related',
        )
        db_session.add(rel1)
        await db_session.flush()

        rel2 = ContentRelationship(
            user_id=test_user.id,
            source_type='bookmark',
            source_id=test_bookmark.id,
            target_type='note',
            target_id=test_note.id,
            relationship_type='related',
        )
        db_session.add(rel2)
        with pytest.raises(IntegrityError, match='uq_content_relationship'):
            await db_session.flush()

    async def test__constraint__same_type_different_ids_allowed(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Two different bookmarks can be related."""
        bm1 = Bookmark(user_id=test_user.id, url='https://a.com/', title='A')
        bm2 = Bookmark(user_id=test_user.id, url='https://b.com/', title='B')
        db_session.add_all([bm1, bm2])
        await db_session.flush()

        rel = ContentRelationship(
            user_id=test_user.id,
            source_type='bookmark',
            source_id=bm1.id,
            target_type='bookmark',
            target_id=bm2.id,
            relationship_type='related',
        )
        db_session.add(rel)
        await db_session.flush()
        await db_session.refresh(rel)

        assert rel.id is not None

    async def test__constraint__user_cascade_delete(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Relationships are deleted when user is deleted (FK CASCADE)."""
        user = User(external_auth_id='test-cascade-user', email='cascade@test.com', tier=Tier.FREE.value)
        db_session.add(user)
        await db_session.flush()

        rel = ContentRelationship(
            user_id=user.id,
            source_type='bookmark',
            source_id=uuid4(),
            target_type='note',
            target_id=uuid4(),
            relationship_type='related',
        )
        db_session.add(rel)
        await db_session.flush()

        rel_id = rel.id
        await db_session.delete(user)
        await db_session.flush()

        # Expire cached objects so the next get hits the DB
        db_session.expire_all()
        result = await db_session.get(ContentRelationship, rel_id)
        assert result is None

    async def test__constraint__cross_user_isolation(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Two different users can create identical relationships (user_id in unique constraint)."""
        user2 = User(external_auth_id='test-user-relationship-2', email='rel2@test.com', tier=Tier.FREE.value)
        db_session.add(user2)
        await db_session.flush()

        source_id = uuid4()
        target_id = uuid4()

        rel1 = ContentRelationship(
            user_id=test_user.id,
            source_type='bookmark',
            source_id=source_id,
            target_type='note',
            target_id=target_id,
            relationship_type='related',
        )
        rel2 = ContentRelationship(
            user_id=user2.id,
            source_type='bookmark',
            source_id=source_id,
            target_type='note',
            target_id=target_id,
            relationship_type='related',
        )
        db_session.add_all([rel1, rel2])
        await db_session.flush()

        await db_session.refresh(rel1)
        await db_session.refresh(rel2)
        assert rel1.id != rel2.id
        assert rel1.user_id == test_user.id
        assert rel2.user_id == user2.id
