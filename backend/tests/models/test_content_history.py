"""Tests for the ContentHistory model."""
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.content_history import ActionType, ContentHistory, EntityType
from models.user import User
from core.tier_limits import Tier


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user for content history tests."""
    user = User(
        external_auth_id="test-user-content-history",
        email="contenthistory@test.com",
        tier=Tier.FREE.value,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


class TestContentHistoryModel:
    """Tests for ContentHistory model creation and fields."""

    async def test__create__with_all_fields(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """ContentHistory can be created with all fields."""
        entity_id = uuid4()
        history = ContentHistory(
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            version=1,
            content_snapshot="Initial content",
            content_diff=None,
            metadata_snapshot={"title": "Test Note", "tags": ["test"]},
            source="web",
            auth_type="session",
            token_prefix=None,
        )
        db_session.add(history)
        await db_session.commit()
        await db_session.refresh(history)

        assert history.id is not None
        assert history.user_id == test_user.id
        assert history.entity_type == EntityType.NOTE
        assert history.entity_id == entity_id
        assert history.action == ActionType.CREATE
        assert history.version == 1
        assert history.content_snapshot == "Initial content"
        assert history.content_diff is None
        assert history.metadata_snapshot == {"title": "Test Note", "tags": ["test"]}
        assert history.source == "web"
        assert history.auth_type == "session"
        assert history.token_prefix is None
        assert history.created_at is not None

    async def test__create__with_pat_auth(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """ContentHistory can be created with PAT auth and token prefix."""
        entity_id = uuid4()
        history = ContentHistory(
            user_id=test_user.id,
            entity_type=EntityType.BOOKMARK,
            entity_id=entity_id,
            action=ActionType.UPDATE,
            version=2,
            content_snapshot=None,
            content_diff="@@ -1,5 +1,6 @@\n Test\n",
            metadata_snapshot={"title": "Test Bookmark"},
            source="mcp-content",
            auth_type="pat",
            token_prefix="bm_a3f8xyz1234",
        )
        db_session.add(history)
        await db_session.commit()
        await db_session.refresh(history)

        assert history.auth_type == "pat"
        assert history.token_prefix == "bm_a3f8xyz1234"
        assert history.source == "mcp-content"

    async def test__create__metadata_only_action(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """ContentHistory can be created for metadata-only actions like ARCHIVE."""
        entity_id = uuid4()
        history = ContentHistory(
            user_id=test_user.id,
            entity_type=EntityType.PROMPT,
            entity_id=entity_id,
            action=ActionType.ARCHIVE,
            version=3,
            content_snapshot=None,
            content_diff=None,
            metadata_snapshot={"title": "Archived Prompt", "archived_at": "2024-01-01T00:00:00Z"},
            source="web",
            auth_type="session",
        )
        db_session.add(history)
        await db_session.commit()
        await db_session.refresh(history)

        assert history.action == ActionType.ARCHIVE
        assert history.content_snapshot is None
        assert history.content_diff is None


class TestContentHistoryEnums:
    """Tests for ContentHistory enum values."""

    def test__action_type__all_values(self) -> None:
        """ActionType has all expected values."""
        assert ActionType.CREATE == "create"
        assert ActionType.UPDATE == "update"
        assert ActionType.DELETE == "delete"
        assert ActionType.RESTORE == "restore"
        assert ActionType.UNDELETE == "undelete"
        assert ActionType.ARCHIVE == "archive"
        assert ActionType.UNARCHIVE == "unarchive"

    def test__entity_type__all_values(self) -> None:
        """EntityType has all expected values."""
        assert EntityType.BOOKMARK == "bookmark"
        assert EntityType.NOTE == "note"
        assert EntityType.PROMPT == "prompt"



class TestContentHistoryJsonb:
    """Tests for JSONB metadata_snapshot field."""

    async def test__metadata_snapshot__stores_complex_json(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """metadata_snapshot can store complex nested JSON."""
        entity_id = uuid4()
        complex_metadata = {
            "title": "Complex Note",
            "description": "A note with complex metadata",
            "tags": ["python", "web-dev", "testing"],
            "nested": {
                "level1": {
                    "level2": ["a", "b", "c"],
                },
            },
            "numbers": [1, 2, 3.14],
            "boolean": True,
            "null_value": None,
        }
        history = ContentHistory(
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            version=1,
            content_snapshot="Content",
            metadata_snapshot=complex_metadata,
            source="web",
            auth_type="session",
        )
        db_session.add(history)
        await db_session.commit()
        await db_session.refresh(history)

        # Verify the metadata was stored and retrieved correctly
        assert history.metadata_snapshot == complex_metadata
        assert history.metadata_snapshot["tags"] == ["python", "web-dev", "testing"]
        assert history.metadata_snapshot["nested"]["level1"]["level2"] == ["a", "b", "c"]


class TestContentHistoryRelationships:
    """Tests for ContentHistory relationships."""

    async def test__user_relationship__works(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """ContentHistory.user relationship returns the correct user."""
        entity_id = uuid4()
        history = ContentHistory(
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            version=1,
            content_snapshot="Content",
            metadata_snapshot={"title": "Test"},
            source="web",
            auth_type="session",
        )
        db_session.add(history)
        await db_session.commit()

        # Query the history and access the user relationship
        result = await db_session.execute(
            select(ContentHistory).where(ContentHistory.id == history.id),
        )
        loaded_history = result.scalar_one()
        await db_session.refresh(loaded_history, ["user"])

        assert loaded_history.user.id == test_user.id
        assert loaded_history.user.email == "contenthistory@test.com"

    async def test__user_content_history__relationship(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """User.content_history relationship returns all history records."""
        entity_id = uuid4()

        # Create multiple history records
        for version in range(1, 4):
            history = ContentHistory(
                user_id=test_user.id,
                entity_type=EntityType.NOTE,
                entity_id=entity_id,
                action=ActionType.UPDATE if version > 1 else ActionType.CREATE,
                version=version,
                content_snapshot="Content" if version == 1 else None,
                content_diff="diff" if version > 1 else None,
                metadata_snapshot={"title": f"Version {version}"},
                source="web",
                auth_type="session",
            )
            db_session.add(history)

        await db_session.commit()
        await db_session.refresh(test_user, ["content_history"])

        assert len(test_user.content_history) == 3


class TestContentHistoryUniqueConstraint:
    """Tests for unique constraint on (user_id, entity_type, entity_id, version)."""

    async def test__duplicate_version__raises_integrity_error(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Creating duplicate (user_id, entity_type, entity_id, version) raises IntegrityError."""
        entity_id = uuid4()

        # Create first history record
        history1 = ContentHistory(
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            version=1,
            content_snapshot="Content",
            metadata_snapshot={"title": "Test"},
            source="web",
            auth_type="session",
        )
        db_session.add(history1)
        await db_session.commit()

        # Try to create a duplicate version
        history2 = ContentHistory(
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.UPDATE,
            version=1,  # Same version - should fail
            content_snapshot=None,
            content_diff="diff",
            metadata_snapshot={"title": "Duplicate"},
            source="web",
            auth_type="session",
        )
        db_session.add(history2)

        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test__same_version_different_entity__succeeds(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Same version for different entities is allowed."""
        entity_id_1 = uuid4()
        entity_id_2 = uuid4()

        # Create history for first entity
        history1 = ContentHistory(
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id_1,
            action=ActionType.CREATE,
            version=1,
            content_snapshot="Content 1",
            metadata_snapshot={"title": "Note 1"},
            source="web",
            auth_type="session",
        )
        db_session.add(history1)

        # Create history for second entity with same version
        history2 = ContentHistory(
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id_2,
            action=ActionType.CREATE,
            version=1,  # Same version, different entity - should succeed
            content_snapshot="Content 2",
            metadata_snapshot={"title": "Note 2"},
            source="web",
            auth_type="session",
        )
        db_session.add(history2)

        await db_session.commit()

        # Both should exist
        result = await db_session.execute(
            select(ContentHistory).where(ContentHistory.user_id == test_user.id),
        )
        histories = result.scalars().all()
        assert len(histories) == 2

    async def test__same_version_different_entity_type__succeeds(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Same version for different entity types is allowed."""
        entity_id = uuid4()

        # Create history for note
        history1 = ContentHistory(
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            version=1,
            content_snapshot="Note content",
            metadata_snapshot={"title": "Note"},
            source="web",
            auth_type="session",
        )
        db_session.add(history1)

        # Create history for bookmark with same entity_id and version
        history2 = ContentHistory(
            user_id=test_user.id,
            entity_type=EntityType.BOOKMARK,  # Different entity type
            entity_id=entity_id,
            action=ActionType.CREATE,
            version=1,
            content_snapshot="Bookmark content",
            metadata_snapshot={"title": "Bookmark"},
            source="web",
            auth_type="session",
        )
        db_session.add(history2)

        await db_session.commit()

        # Both should exist
        result = await db_session.execute(
            select(ContentHistory).where(ContentHistory.user_id == test_user.id),
        )
        histories = result.scalars().all()
        assert len(histories) == 2
