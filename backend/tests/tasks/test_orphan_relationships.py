"""Tests for orphan relationship detection and cleanup."""
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.bookmark import Bookmark
from models.content_relationship import ContentRelationship
from models.note import Note
from models.prompt import Prompt
from models.user import User
from tasks.orphan_relationships import (
    OrphanStats,
    cleanup_orphaned_relationships,
    find_orphaned_relationships,
    run_orphan_cleanup,
)


def create_relationship(
    user_id: UUID,
    source_type: str,
    source_id: UUID,
    target_type: str,
    target_id: UUID,
    relationship_type: str = "related",
) -> ContentRelationship:
    """Helper to create a ContentRelationship directly via ORM."""
    return ContentRelationship(
        user_id=user_id,
        source_type=source_type,
        source_id=source_id,
        target_type=target_type,
        target_id=target_id,
        relationship_type=relationship_type,
    )


async def count_relationships(db: AsyncSession, user_id: UUID | None = None) -> int:
    """Count relationships, optionally filtered by user."""
    stmt = select(func.count()).select_from(ContentRelationship)
    if user_id:
        stmt = stmt.where(ContentRelationship.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one()


class TestFindOrphanedRelationships:
    """Tests for find_orphaned_relationships."""

    @pytest.fixture
    async def user(self, db_session: AsyncSession) -> User:
        """Create a test user."""
        user = User(
            external_auth_id=f"test-find-orphan-{uuid4()}",
            email=f"find-orphan-{uuid4()}@test.com",
            tier="free",
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    async def test__no_orphans__returns_empty(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """All relationships have valid endpoints -> empty list."""
        note = Note(user_id=user.id, title="Note", content="Content")
        bookmark = Bookmark(user_id=user.id, url="https://example.com")
        db_session.add_all([note, bookmark])
        await db_session.flush()

        db_session.add(create_relationship(
            user_id=user.id,
            source_type="note",
            source_id=note.id,
            target_type="bookmark",
            target_id=bookmark.id,
        ))
        await db_session.commit()

        orphans = await find_orphaned_relationships(db_session)

        assert len(orphans) == 0

    async def test__source_entity_missing__detected(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """Source entity permanently deleted -> detected."""
        bookmark = Bookmark(user_id=user.id, url="https://example.com")
        db_session.add(bookmark)
        await db_session.flush()

        rel = create_relationship(
            user_id=user.id,
            source_type="note",
            source_id=uuid4(),
            target_type="bookmark",
            target_id=bookmark.id,
        )
        db_session.add(rel)
        await db_session.commit()

        orphans = await find_orphaned_relationships(db_session)

        assert len(orphans) == 1
        assert orphans[0].id == rel.id

    async def test__target_entity_missing__detected(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """Target entity permanently deleted -> detected."""
        note = Note(user_id=user.id, title="Note", content="Content")
        db_session.add(note)
        await db_session.flush()

        rel = create_relationship(
            user_id=user.id,
            source_type="note",
            source_id=note.id,
            target_type="prompt",
            target_id=uuid4(),
        )
        db_session.add(rel)
        await db_session.commit()

        orphans = await find_orphaned_relationships(db_session)

        assert len(orphans) == 1
        assert orphans[0].id == rel.id

    async def test__both_endpoints_missing__detected_once(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """Both source and target gone -> detected exactly once (deduplicated)."""
        rel = create_relationship(
            user_id=user.id,
            source_type="bookmark",
            source_id=uuid4(),
            target_type="note",
            target_id=uuid4(),
        )
        db_session.add(rel)
        await db_session.commit()

        orphans = await find_orphaned_relationships(db_session)

        assert len(orphans) == 1
        assert orphans[0].id == rel.id

    async def test__soft_deleted_entity__not_orphaned(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """Soft-deleted entity still exists in DB -> NOT detected as orphan."""
        note = Note(user_id=user.id, title="Soft Deleted", content="Content")
        bookmark = Bookmark(user_id=user.id, url="https://example.com")
        db_session.add_all([note, bookmark])
        await db_session.flush()

        note.deleted_at = datetime.now(UTC)

        db_session.add(create_relationship(
            user_id=user.id,
            source_type="note",
            source_id=note.id,
            target_type="bookmark",
            target_id=bookmark.id,
        ))
        await db_session.commit()

        orphans = await find_orphaned_relationships(db_session)

        assert len(orphans) == 0


class TestCleanupOrphanedRelationships:
    """Tests for cleanup_orphaned_relationships."""

    @pytest.fixture
    async def user(self, db_session: AsyncSession) -> User:
        """Create a test user."""
        user = User(
            external_auth_id=f"test-cleanup-rel-{uuid4()}",
            email=f"cleanup-rel-{uuid4()}@test.com",
            tier="free",
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    async def test__report_mode__does_not_delete(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """Default mode reports orphans but doesn't delete them."""
        db_session.add(create_relationship(
            user_id=user.id,
            source_type="note",
            source_id=uuid4(),
            target_type="bookmark",
            target_id=uuid4(),
        ))
        await db_session.commit()

        stats = await cleanup_orphaned_relationships(db_session, delete=False)

        assert stats.orphaned_source > 0 or stats.orphaned_target > 0
        assert stats.total_deleted == 0
        assert await count_relationships(db_session, user.id) == 1

    async def test__delete_mode__source_orphan__removed(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """Delete mode removes relationships where only source is missing."""
        bookmark = Bookmark(user_id=user.id, url="https://example.com")
        db_session.add(bookmark)
        await db_session.flush()

        db_session.add(create_relationship(
            user_id=user.id,
            source_type="note",
            source_id=uuid4(),
            target_type="bookmark",
            target_id=bookmark.id,
        ))
        await db_session.commit()

        stats = await cleanup_orphaned_relationships(db_session, delete=True)

        assert stats.orphaned_source == 1
        assert stats.orphaned_target == 0
        assert stats.total_deleted == 1
        assert await count_relationships(db_session, user.id) == 0

    async def test__delete_mode__target_orphan__removed(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """Delete mode removes relationships where only target is missing."""
        note = Note(user_id=user.id, title="Note", content="Content")
        db_session.add(note)
        await db_session.flush()

        db_session.add(create_relationship(
            user_id=user.id,
            source_type="note",
            source_id=note.id,
            target_type="prompt",
            target_id=uuid4(),
        ))
        await db_session.commit()

        stats = await cleanup_orphaned_relationships(db_session, delete=True)

        assert stats.orphaned_source == 0
        assert stats.orphaned_target == 1
        assert stats.total_deleted == 1
        assert await count_relationships(db_session, user.id) == 0

    async def test__delete_mode__both_sides_missing__deleted_once(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """
        Relationship with both sides missing is deleted exactly once.

        The source pass deletes it; the target pass finds nothing (already gone).
        total_deleted accurately reflects 1 row removed, not 2.
        """
        db_session.add(create_relationship(
            user_id=user.id,
            source_type="bookmark",
            source_id=uuid4(),
            target_type="note",
            target_id=uuid4(),
        ))
        await db_session.commit()

        stats = await cleanup_orphaned_relationships(db_session, delete=True)

        # Source pass deletes it; target pass finds 0 (already deleted)
        assert stats.total_deleted == 1
        assert stats.orphaned_source == 1
        assert stats.orphaned_target == 0
        assert await count_relationships(db_session, user.id) == 0

    async def test__mixed_valid_and_orphaned__only_orphans_deleted(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """Valid relationships are preserved; only orphans are removed."""
        note = Note(user_id=user.id, title="Note", content="Content")
        bookmark = Bookmark(user_id=user.id, url="https://example.com")
        db_session.add_all([note, bookmark])
        await db_session.flush()

        valid_rel = create_relationship(
            user_id=user.id,
            source_type="bookmark",
            source_id=bookmark.id,
            target_type="note",
            target_id=note.id,
        )
        db_session.add(valid_rel)

        db_session.add(create_relationship(
            user_id=user.id,
            source_type="prompt",
            source_id=uuid4(),
            target_type="note",
            target_id=note.id,
        ))
        await db_session.commit()

        stats = await cleanup_orphaned_relationships(db_session, delete=True)

        assert stats.total_deleted == 1
        assert await count_relationships(db_session, user.id) == 1

        # Verify the valid relationship is the one that survived
        stmt = select(ContentRelationship).where(
            ContentRelationship.user_id == user.id,
        )
        result = await db_session.execute(stmt)
        remaining = result.scalar_one()
        assert remaining.id == valid_rel.id

    async def test__idempotent__second_run_finds_nothing(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """Running delete twice -> second run finds and deletes nothing."""
        db_session.add(create_relationship(
            user_id=user.id,
            source_type="bookmark",
            source_id=uuid4(),
            target_type="note",
            target_id=uuid4(),
        ))
        await db_session.commit()

        first = await cleanup_orphaned_relationships(db_session, delete=True)
        assert first.total_deleted == 1

        second = await cleanup_orphaned_relationships(db_session, delete=True)
        assert second.total_deleted == 0
        assert second.orphaned_source == 0
        assert second.orphaned_target == 0
        assert second.by_content_type == {}

    async def test__stats_breakdown_by_content_type(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """Verify by_content_type tracks the type of the missing entity."""
        note = Note(user_id=user.id, title="Note", content="Content")
        db_session.add(note)
        await db_session.flush()

        # Missing bookmark source -> counted under "bookmark"
        db_session.add(create_relationship(
            user_id=user.id,
            source_type="bookmark",
            source_id=uuid4(),
            target_type="note",
            target_id=note.id,
        ))
        # Missing prompt source -> counted under "prompt"
        db_session.add(create_relationship(
            user_id=user.id,
            source_type="prompt",
            source_id=uuid4(),
            target_type="note",
            target_id=note.id,
        ))
        # Missing prompt target -> also counted under "prompt"
        db_session.add(create_relationship(
            user_id=user.id,
            source_type="note",
            source_id=note.id,
            target_type="prompt",
            target_id=uuid4(),
        ))
        await db_session.commit()

        stats = await cleanup_orphaned_relationships(db_session, delete=False)

        assert stats.by_content_type["bookmark"] == 1
        assert stats.by_content_type["prompt"] == 2  # 1 source + 1 target
        assert "note" not in stats.by_content_type  # note entity exists
        assert stats.orphaned_source == 2  # bookmark + prompt sources
        assert stats.orphaned_target == 1  # prompt target

    async def test__all_three_entity_types__delete_mode(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """Orphans involving all three entity types are detected and deleted."""
        note = Note(user_id=user.id, title="Note", content="Content")
        bookmark = Bookmark(user_id=user.id, url="https://example.com")
        prompt = Prompt(
            user_id=user.id,
            name=f"test-prompt-{uuid4().hex[:8]}",
            content="Content",
        )
        db_session.add_all([note, bookmark, prompt])
        await db_session.flush()

        # Missing bookmark target
        db_session.add(create_relationship(
            user_id=user.id,
            source_type="note",
            source_id=note.id,
            target_type="bookmark",
            target_id=uuid4(),
        ))
        # Missing note source
        db_session.add(create_relationship(
            user_id=user.id,
            source_type="note",
            source_id=uuid4(),
            target_type="prompt",
            target_id=prompt.id,
        ))
        # Missing prompt target
        db_session.add(create_relationship(
            user_id=user.id,
            source_type="bookmark",
            source_id=bookmark.id,
            target_type="prompt",
            target_id=uuid4(),
        ))
        await db_session.commit()

        stats = await cleanup_orphaned_relationships(db_session, delete=True)

        assert stats.total_deleted == 3
        assert await count_relationships(db_session, user.id) == 0
        assert "bookmark" in stats.by_content_type
        assert "note" in stats.by_content_type
        assert "prompt" in stats.by_content_type

    async def test__empty_database__completes_without_error(
        self,
        db_session: AsyncSession,
    ) -> None:
        """No relationships in database -> no error, zero stats."""
        stats = await cleanup_orphaned_relationships(db_session, delete=True)

        assert stats.orphaned_source == 0
        assert stats.orphaned_target == 0
        assert stats.total_deleted == 0
        assert stats.by_content_type == {}

    async def test__report_then_delete__counts_consistent(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """
        Report mode counts match what delete mode actually removes.

        Uses single-side orphans to avoid the expected divergence that
        occurs with both-sides-missing relationships (where report mode
        counts per-side but delete mode removes the row on first pass).
        """
        note = Note(user_id=user.id, title="Note", content="Content")
        db_session.add(note)
        await db_session.flush()

        # 2 source orphans, 1 target orphan (all single-side)
        db_session.add(create_relationship(
            user_id=user.id,
            source_type="bookmark",
            source_id=uuid4(),
            target_type="note",
            target_id=note.id,
        ))
        db_session.add(create_relationship(
            user_id=user.id,
            source_type="prompt",
            source_id=uuid4(),
            target_type="note",
            target_id=note.id,
        ))
        db_session.add(create_relationship(
            user_id=user.id,
            source_type="note",
            source_id=note.id,
            target_type="bookmark",
            target_id=uuid4(),
        ))
        await db_session.commit()

        # Report first
        report = await cleanup_orphaned_relationships(db_session, delete=False)
        assert report.orphaned_source == 2
        assert report.orphaned_target == 1
        assert report.total_deleted == 0

        # Then delete — counts should match report
        result = await cleanup_orphaned_relationships(db_session, delete=True)
        assert result.orphaned_source == report.orphaned_source
        assert result.orphaned_target == report.orphaned_target
        assert result.total_deleted == 3
        assert await count_relationships(db_session, user.id) == 0

    async def test__cross_user__entity_exists_for_other_user__is_orphaned(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """
        Entity belonging to another user exists in DB but not for the
        relationship's user.

        The NOT EXISTS query checks entity existence scoped to user_id,
        so a relationship pointing to another user's entity IS considered
        orphaned — the entity doesn't belong to the relationship's user.
        """
        other_user = User(
            external_auth_id=f"test-other-{uuid4()}",
            email=f"other-{uuid4()}@test.com",
            tier="free",
        )
        db_session.add(other_user)
        await db_session.flush()

        other_bookmark = Bookmark(
            user_id=other_user.id,
            url="https://other-user.com",
        )
        note = Note(user_id=user.id, title="Note", content="Content")
        db_session.add_all([other_bookmark, note])
        await db_session.flush()

        # Relationship from user points to other_user's bookmark
        db_session.add(create_relationship(
            user_id=user.id,
            source_type="note",
            source_id=note.id,
            target_type="bookmark",
            target_id=other_bookmark.id,
        ))
        await db_session.commit()

        stats = await cleanup_orphaned_relationships(db_session, delete=True)

        # Orphaned — the bookmark belongs to another user
        assert stats.total_deleted == 1
        assert stats.orphaned_target == 1
        assert await count_relationships(db_session, user.id) == 0

    async def test__soft_deleted_entity__not_treated_as_orphan(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """
        Soft-deleted entities still exist in DB, so relationships
        pointing to them are NOT orphaned. Critical safety test —
        verifies delete mode does NOT remove these relationships.
        """
        note = Note(user_id=user.id, title="Soft Deleted", content="Content")
        bookmark = Bookmark(user_id=user.id, url="https://example.com")
        db_session.add_all([note, bookmark])
        await db_session.flush()

        note.deleted_at = datetime.now(UTC)

        db_session.add(create_relationship(
            user_id=user.id,
            source_type="note",
            source_id=note.id,
            target_type="bookmark",
            target_id=bookmark.id,
        ))
        await db_session.commit()

        # Must NOT delete this relationship
        stats = await cleanup_orphaned_relationships(db_session, delete=True)

        assert stats.total_deleted == 0
        assert await count_relationships(db_session, user.id) == 1


class TestRunOrphanCleanup:
    """Tests for the run_orphan_cleanup entry point."""

    @pytest.fixture
    async def user(self, db_session: AsyncSession) -> User:
        """Create a test user."""
        user = User(
            external_auth_id=f"test-run-orphan-{uuid4()}",
            email=f"run-orphan-{uuid4()}@test.com",
            tier="free",
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    async def test__with_db__delegates_to_cleanup(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """run_orphan_cleanup with db session finds and reports orphans."""
        db_session.add(create_relationship(
            user_id=user.id,
            source_type="note",
            source_id=uuid4(),
            target_type="bookmark",
            target_id=uuid4(),
        ))
        await db_session.commit()

        stats = await run_orphan_cleanup(db=db_session, delete=False)

        assert stats.orphaned_source > 0 or stats.orphaned_target > 0
        assert stats.total_deleted == 0
        assert await count_relationships(db_session, user.id) == 1

    async def test__delete_flag__passed_through(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """run_orphan_cleanup passes delete flag to cleanup function."""
        db_session.add(create_relationship(
            user_id=user.id,
            source_type="bookmark",
            source_id=uuid4(),
            target_type="note",
            target_id=uuid4(),
        ))
        await db_session.commit()

        stats = await run_orphan_cleanup(db=db_session, delete=True)

        assert stats.total_deleted > 0
        assert await count_relationships(db_session, user.id) == 0


class TestOrphanStatsDataclass:
    """Tests for the OrphanStats dataclass."""

    def test__to_dict__returns_summary(self) -> None:
        """to_dict returns a simple summary dict without by_content_type."""
        stats = OrphanStats(
            orphaned_source=3,
            orphaned_target=2,
            total_deleted=5,
            by_content_type={"bookmark": 2, "note": 3},
        )

        result = stats.to_dict()

        assert result == {
            "orphaned_source": 3,
            "orphaned_target": 2,
            "total_deleted": 5,
        }
        assert "by_content_type" not in result

    def test__default_values__are_empty(self) -> None:
        """Default OrphanStats has zero counts and empty dict."""
        stats = OrphanStats()

        assert stats.orphaned_source == 0
        assert stats.orphaned_target == 0
        assert stats.total_deleted == 0
        assert stats.by_content_type == {}
