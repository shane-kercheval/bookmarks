"""
Comprehensive tests for the cleanup task.

These tests verify the cleanup logic handles all edge cases correctly
since this is critical code that deletes production user data.
"""
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.request_context import AuthType
from core.tier_limits import TIER_LIMITS, Tier
from models.bookmark import Bookmark
from models.content_history import ActionType, ContentHistory, EntityType
from models.note import Note
from models.prompt import Prompt
from models.user import User
from services.history_service import history_service
from models.deleted_identity import DeletedIdentity
from tasks.cleanup import (
    DELETED_IDENTITY_RETENTION_DAYS,
    SOFT_DELETE_EXPIRY_DAYS,
    CleanupStats,
    cleanup_expired_history,
    cleanup_expired_tombstones,
    cleanup_orphaned_history,
    cleanup_soft_deleted_items,
    run_cleanup,
)


# Get retention days from actual config for accurate boundary testing
FREE_RETENTION_DAYS = TIER_LIMITS[Tier.FREE].history_retention_days


def create_history_record(
    user_id,
    entity_type: EntityType,
    entity_id,
    version: int = 1,
    created_at: datetime | None = None,
) -> ContentHistory:
    """Helper to create a ContentHistory record with minimal required fields."""
    return ContentHistory(
        user_id=user_id,
        entity_type=entity_type.value,
        entity_id=entity_id,
        action=ActionType.CREATE.value,
        version=version,
        content_snapshot=f"Content v{version}",
        metadata_snapshot={"title": f"Test v{version}"},
        source="web",
        auth_type=AuthType.SESSION.value,
        created_at=created_at,
    )


def create_versioned_history_record(
    user_id: UUID,
    entity_type: EntityType,
    entity_id: UUID,
    version: int,
    action: ActionType = ActionType.CREATE,
    content_snapshot: str | None = None,
    content_diff: str | None = None,
    metadata: dict | None = None,
    created_at: datetime | None = None,
) -> ContentHistory:
    """
    Create a versioned ContentHistory record with explicit action/content shape.

    Prefer over `create_history_record` when you need to control
    content_snapshot/content_diff explicitly (e.g. UPDATE with diff only,
    modulo-10 snapshot, CREATE with snapshot only).
    """
    return ContentHistory(
        user_id=user_id,
        entity_type=entity_type.value,
        entity_id=entity_id,
        action=action.value,
        version=version,
        content_snapshot=content_snapshot,
        content_diff=content_diff,
        metadata_snapshot=metadata or {"title": f"Test v{version}"},
        source="web",
        auth_type=AuthType.SESSION.value,
        created_at=created_at,
    )


def create_audit_history_record(
    user_id: UUID,
    entity_type: EntityType,
    entity_id: UUID,
    action: ActionType,
    created_at: datetime | None = None,
) -> ContentHistory:
    """Create an audit (NULL version) ContentHistory record."""
    return ContentHistory(
        user_id=user_id,
        entity_type=entity_type.value,
        entity_id=entity_id,
        action=action.value,
        version=None,
        content_snapshot=None,
        content_diff=None,
        metadata_snapshot={"title": "Audit marker"},
        source="web",
        auth_type=AuthType.SESSION.value,
        created_at=created_at,
    )


async def count_history_records(db: AsyncSession, user_id=None) -> int:
    """Count history records, optionally filtered by user."""
    stmt = select(func.count()).select_from(ContentHistory)
    if user_id:
        stmt = stmt.where(ContentHistory.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one()


async def count_entities(db: AsyncSession, model: type, user_id=None) -> int:
    """Count entities of a given type, optionally filtered by user."""
    stmt = select(func.count()).select_from(model)
    if user_id:
        stmt = stmt.where(model.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one()


class TestCleanupSoftDeletedItems:
    """Tests for permanent deletion of expired soft-deleted items."""

    @pytest.fixture
    async def user(self, db_session: AsyncSession) -> User:
        """Create a test user."""
        user = User(
            external_auth_id=f"test-softdel-{uuid4()}",
            email=f"softdel-{uuid4()}@test.com",
            tier=Tier.FREE.value,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    async def test__day_29__soft_deleted_item_kept(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """Soft-deleted item 29 days ago should be kept."""
        now = datetime.now(UTC)

        # Create note soft-deleted 29 days ago
        note = Note(
            user_id=user.id,
            title="Recently Deleted",
            content="Content",
            deleted_at=now - timedelta(days=29),
        )
        db_session.add(note)
        await db_session.commit()

        # Run cleanup
        stats = await cleanup_soft_deleted_items(db_session, now=now)

        # Note should still exist
        assert stats.soft_deleted_expired == 0
        assert await count_entities(db_session, Note, user.id) == 1

    async def test__day_30_exactly__soft_deleted_item_kept(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """Soft-deleted item exactly 30 days ago should be kept (boundary)."""
        now = datetime.now(UTC)

        note = Note(
            user_id=user.id,
            title="Exactly 30 Days",
            content="Content",
            deleted_at=now - timedelta(days=SOFT_DELETE_EXPIRY_DAYS),
        )
        db_session.add(note)
        await db_session.commit()

        stats = await cleanup_soft_deleted_items(db_session, now=now)

        assert stats.soft_deleted_expired == 0
        assert await count_entities(db_session, Note, user.id) == 1

    async def test__day_30_plus_1_second__soft_deleted_item_deleted(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """Soft-deleted item 30 days + 1 second ago should be permanently deleted."""
        now = datetime.now(UTC)

        note = Note(
            user_id=user.id,
            title="Just Past Expiry",
            content="Content",
            deleted_at=now - timedelta(days=SOFT_DELETE_EXPIRY_DAYS, seconds=1),
        )
        db_session.add(note)
        await db_session.flush()

        # Add history for the note
        db_session.add(create_history_record(
            user_id=user.id,
            entity_type=EntityType.NOTE,
            entity_id=note.id,
        ))
        await db_session.commit()

        stats = await cleanup_soft_deleted_items(db_session, now=now)

        # Note and history should be deleted
        assert stats.soft_deleted_expired == 1
        assert stats.soft_deleted_by_type["notes"] == 1
        assert await count_entities(db_session, Note, user.id) == 0
        assert await count_history_records(db_session, user.id) == 0

    async def test__day_31__soft_deleted_item_deleted(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """Soft-deleted item 31 days ago should be permanently deleted."""
        now = datetime.now(UTC)

        note = Note(
            user_id=user.id,
            title="Expired",
            content="Content",
            deleted_at=now - timedelta(days=31),
        )
        db_session.add(note)
        await db_session.commit()

        stats = await cleanup_soft_deleted_items(db_session, now=now)

        assert stats.soft_deleted_expired == 1
        assert await count_entities(db_session, Note, user.id) == 0

    async def test__all_entity_types__cleaned_correctly(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """Expired soft-deleted bookmarks, notes, and prompts are all cleaned."""
        now = datetime.now(UTC)
        expired_time = now - timedelta(days=60)

        # Create expired soft-deleted entities of each type
        note = Note(
            user_id=user.id,
            title="Deleted Note",
            content="Content",
            deleted_at=expired_time,
        )
        bookmark = Bookmark(
            user_id=user.id,
            url="https://example.com",
            deleted_at=expired_time,
        )
        prompt = Prompt(
            user_id=user.id,
            name=f"deleted-prompt-{uuid4().hex[:8]}",
            content="Content",
            deleted_at=expired_time,
        )
        db_session.add_all([note, bookmark, prompt])
        await db_session.commit()

        stats = await cleanup_soft_deleted_items(db_session, now=now)

        assert stats.soft_deleted_expired == 3
        assert stats.soft_deleted_by_type["notes"] == 1
        assert stats.soft_deleted_by_type["bookmarks"] == 1
        assert stats.soft_deleted_by_type["prompts"] == 1

    async def test__history_cascade_deleted_before_entity(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """History is deleted before the entity (application-level cascade)."""
        now = datetime.now(UTC)

        # Create expired soft-deleted note with history
        note = Note(
            user_id=user.id,
            title="Expired With History",
            content="Content",
            deleted_at=now - timedelta(days=60),
        )
        db_session.add(note)
        await db_session.flush()

        # Add multiple history records
        for v in range(1, 4):
            db_session.add(create_history_record(
                user_id=user.id,
                entity_type=EntityType.NOTE,
                entity_id=note.id,
                version=v,
            ))
        await db_session.commit()

        # Verify setup
        assert await count_history_records(db_session, user.id) == 3

        stats = await cleanup_soft_deleted_items(db_session, now=now)

        # Both entity and all history deleted
        assert stats.soft_deleted_expired == 1
        assert await count_entities(db_session, Note, user.id) == 0
        assert await count_history_records(db_session, user.id) == 0

    async def test__active_entities_not_affected(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """Active (non-deleted) entities are not affected by cleanup."""
        now = datetime.now(UTC)

        # Create active note and expired soft-deleted note
        active_note = Note(
            user_id=user.id,
            title="Active Note",
            content="Active content",
        )
        deleted_note = Note(
            user_id=user.id,
            title="Deleted Note",
            content="Deleted content",
            deleted_at=now - timedelta(days=60),
        )
        db_session.add_all([active_note, deleted_note])
        await db_session.commit()

        stats = await cleanup_soft_deleted_items(db_session, now=now)

        # Only deleted note removed
        assert stats.soft_deleted_expired == 1
        assert await count_entities(db_session, Note, user.id) == 1


class TestCleanupExpiredHistoryBoundaryConditions:
    """
    Test precise boundary conditions for time-based cleanup.

    Uses FREE tier retention days from config. Tests:
    - Before retention window: KEEP
    - Exactly at boundary: KEEP (created_at < cutoff means strictly less than)
    - Just past boundary: DELETE
    - Well past boundary: DELETE
    """

    @pytest.fixture
    async def user(self, db_session: AsyncSession) -> User:
        """Create a test user on FREE tier."""
        user = User(
            external_auth_id=f"test-boundary-{uuid4()}",
            email=f"boundary-{uuid4()}@test.com",
            tier=Tier.FREE.value,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    async def test__within_retention__record_is_kept(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """Record created within retention window should be kept."""
        now = datetime.now(UTC)
        entity_id = uuid4()

        # Create record half a retention period ago (safely within window)
        hours_within = max(1, (FREE_RETENTION_DAYS * 24) // 2)
        record = create_history_record(
            user_id=user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            created_at=now - timedelta(hours=hours_within),
        )
        db_session.add(record)
        await db_session.commit()

        stats = await cleanup_expired_history(db_session, now=now)

        assert stats.expired_deleted == 0
        assert await count_history_records(db_session, user.id) == 1

    async def test__exactly_at_boundary__record_is_kept(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """
        Record created exactly at the retention boundary should be kept.

        The cutoff is `now - retention_days`, and we delete where `created_at < cutoff`.
        A record created exactly at cutoff (created_at == cutoff) is NOT deleted.
        """
        now = datetime.now(UTC)
        entity_id = uuid4()

        exactly_at_boundary = now - timedelta(days=FREE_RETENTION_DAYS)
        record = create_history_record(
            user_id=user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            created_at=exactly_at_boundary,
        )
        db_session.add(record)
        await db_session.commit()

        stats = await cleanup_expired_history(db_session, now=now)

        assert stats.expired_deleted == 0
        assert await count_history_records(db_session, user.id) == 1

    async def test__just_past_boundary__record_is_deleted(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """
        Record created just past the retention boundary should be deleted.

        The preservation rule protects the *latest* versioned row per entity,
        so this test seeds a fresh higher-versioned anchor (v2) to ensure
        v1 is not the latest and thus remains deletable.
        """
        now = datetime.now(UTC)
        entity_id = uuid4()

        # Fresh anchor (v2) so v1 is not the latest versioned row.
        db_session.add(create_history_record(
            user_id=user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            version=2,
            created_at=now - timedelta(hours=1),
        ))
        just_past_cutoff = now - timedelta(days=FREE_RETENTION_DAYS, seconds=1)
        db_session.add(create_history_record(
            user_id=user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            version=1,
            created_at=just_past_cutoff,
        ))
        await db_session.commit()

        stats = await cleanup_expired_history(db_session, now=now)

        assert stats.expired_deleted == 1
        assert stats.expired_by_tier[Tier.FREE.value] == 1
        # v2 anchor remains; v1 deleted.
        assert await count_history_records(db_session, user.id) == 1

    async def test__well_past_boundary__record_is_deleted(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """
        Record created well past the retention boundary should be deleted.

        Seeds a fresh higher-versioned anchor (v2) so the aged v1 is not the
        latest versioned row and thus remains deletable under the preservation
        rule.
        """
        now = datetime.now(UTC)
        entity_id = uuid4()

        # Fresh anchor (v2) so v1 is not the latest versioned row.
        db_session.add(create_history_record(
            user_id=user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            version=2,
            created_at=now - timedelta(hours=1),
        ))
        db_session.add(create_history_record(
            user_id=user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            version=1,
            created_at=now - timedelta(days=FREE_RETENTION_DAYS + 5),
        ))
        await db_session.commit()

        stats = await cleanup_expired_history(db_session, now=now)

        # v1 deleted; v2 anchor remains.
        assert stats.expired_deleted == 1
        assert await count_history_records(db_session, user.id) == 1

    async def test__mixed_ages__only_old_deleted(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """
        With mixed record ages, only records past retention are deleted.

        Versions are seeded so higher version = newer (realistic entity
        evolution). v5 is fresh and serves as the latest-versioned anchor,
        so all aged rows (v1, v2, v3) are deletable under the preservation
        rule. v4 is exactly at the cutoff and preserved by strict `<`.
        """
        now = datetime.now(UTC)
        entity_id = uuid4()

        # Higher version = newer (chronological with entity evolution).
        r = FREE_RETENTION_DAYS
        ages_and_expected = [
            (timedelta(days=r * 10), False),           # v1 far past - delete
            (timedelta(days=r + 5), False),            # v2 well past - delete
            (timedelta(days=r, seconds=1), False),     # v3 just past - delete
            (timedelta(days=r), True),                 # v4 exactly at boundary - keep
            (timedelta(hours=1), True),                # v5 fresh / latest - keep
        ]

        for version, (age, _) in enumerate(ages_and_expected, 1):
            db_session.add(create_history_record(
                user_id=user.id,
                entity_type=EntityType.NOTE,
                entity_id=entity_id,
                version=version,
                created_at=now - age,
            ))
        await db_session.commit()

        stats = await cleanup_expired_history(db_session, now=now)

        expected_deleted = sum(1 for _, keep in ages_and_expected if not keep)
        expected_kept = sum(1 for _, keep in ages_and_expected if keep)
        assert stats.expired_deleted == expected_deleted
        assert await count_history_records(db_session, user.id) == expected_kept


class TestCleanupExpiredHistoryBatchByTier:
    """Test batch-by-tier cleanup behavior."""

    async def test__multiple_users_same_tier__single_delete(
        self,
        db_session: AsyncSession,
    ) -> None:
        """
        Multiple users in the same tier are cleaned with a single DELETE per tier.

        Each user's entity gets a fresh v2 anchor so the aged v1 remains
        deletable under the preservation rule. Verifies the tier-batched
        DELETE applies to aged rows across all users in one statement.
        """
        now = datetime.now(UTC)

        # Create 3 users all in FREE tier
        users = []
        for _ in range(3):
            user = User(
                external_auth_id=f"test-tier-{uuid4()}",
                email=f"tier-{uuid4()}@test.com",
                tier=Tier.FREE.value,
            )
            db_session.add(user)
            users.append(user)
        await db_session.flush()

        # Each user: aged v1 + fresh v2 anchor (so v1 is deletable).
        entity_ids = {user.id: uuid4() for user in users}
        for user in users:
            db_session.add(create_history_record(
                user_id=user.id,
                entity_type=EntityType.NOTE,
                entity_id=entity_ids[user.id],
                version=1,
                created_at=now - timedelta(days=60),
            ))
            db_session.add(create_history_record(
                user_id=user.id,
                entity_type=EntityType.NOTE,
                entity_id=entity_ids[user.id],
                version=2,
                created_at=now - timedelta(hours=1),
            ))
        await db_session.commit()

        stats = await cleanup_expired_history(db_session, now=now)

        # 3 aged v1 rows deleted in one tier DELETE; 3 fresh v2 anchors remain.
        assert stats.expired_deleted == 3
        assert stats.expired_by_tier[Tier.FREE.value] == 3
        for user in users:
            assert await count_history_records(db_session, user.id) == 1

    async def test__unknown_tier__not_cleaned_by_any_tier(
        self,
        db_session: AsyncSession,
    ) -> None:
        """
        Users with unrecognized tier values are not matched by any tier's cleanup.

        The cleanup iterates known tiers and matches users via
        `COALESCE(tier, 'free') == tier_value`. A non-NULL unknown value like
        'bogus' won't match any known tier, so records are left untouched.
        The database enforces NOT NULL on tier, so NULL is impossible.
        """
        now = datetime.now(UTC)

        # Create user then set tier to an unrecognized value via raw SQL
        user = User(
            external_auth_id=f"test-bogus-tier-{uuid4()}",
            email=f"bogustier-{uuid4()}@test.com",
            tier=Tier.FREE.value,
        )
        db_session.add(user)
        await db_session.flush()
        await db_session.execute(
            text("UPDATE users SET tier = :tier WHERE id = :uid"),
            {"tier": "bogus", "uid": str(user.id)},
        )

        # Add old record (well past any tier's retention)
        db_session.add(create_history_record(
            user_id=user.id,
            entity_type=EntityType.NOTE,
            entity_id=uuid4(),
            created_at=now - timedelta(days=60),
        ))
        await db_session.commit()

        stats = await cleanup_expired_history(db_session, now=now)

        # Unknown tier doesn't match any known tier, so nothing is deleted
        assert stats.expired_deleted == 0


class TestCleanupExpiredHistoryEntityTypes:
    """Test cleanup handles all entity types correctly."""

    @pytest.fixture
    async def user(self, db_session: AsyncSession) -> User:
        """Create a test user."""
        user = User(
            external_auth_id=f"test-entity-{uuid4()}",
            email=f"entity-{uuid4()}@test.com",
            tier=Tier.FREE.value,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    async def test__all_entity_types__cleaned_correctly(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """
        Cleanup applies to bookmark, note, and prompt history equally.

        Each entity gets an aged v1 + fresh v2 anchor so the aged rows
        remain deletable under the preservation rule.
        """
        now = datetime.now(UTC)

        for entity_type in [EntityType.BOOKMARK, EntityType.NOTE, EntityType.PROMPT]:
            entity_id = uuid4()
            db_session.add(create_history_record(
                user_id=user.id,
                entity_type=entity_type,
                entity_id=entity_id,
                version=1,
                created_at=now - timedelta(days=60),
            ))
            db_session.add(create_history_record(
                user_id=user.id,
                entity_type=entity_type,
                entity_id=entity_id,
                version=2,
                created_at=now - timedelta(hours=1),
            ))
        await db_session.commit()

        stats = await cleanup_expired_history(db_session, now=now)

        # 3 aged v1 rows deleted across entity types; 3 fresh v2 anchors remain.
        assert stats.expired_deleted == 3
        assert await count_history_records(db_session, user.id) == 3


class TestCleanupExpiredHistoryPreservesLatestVersioned:
    """
    Tests for the preservation rule in cleanup_expired_history.

    Rule: always preserve the single most recent versioned ContentHistory row
    per (user_id, entity_type, entity_id), regardless of age. Audit rows
    (NULL version) are never "latest" for this rule — they remain fully
    subject to time-based pruning.
    """

    @pytest.fixture
    async def user(self, db_session: AsyncSession) -> User:
        """Create a test user on FREE tier."""
        user = User(
            external_auth_id=f"test-preserve-{uuid4()}",
            email=f"preserve-{uuid4()}@test.com",
            tier=Tier.FREE.value,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    async def test_preserves_only_versioned_record_when_aged(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """A single aged versioned row is preserved (not deleted)."""
        now = datetime.now(UTC)
        entity_id = uuid4()
        db_session.add(create_history_record(
            user_id=user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            version=1,
            created_at=now - timedelta(days=FREE_RETENTION_DAYS + 10),
        ))
        await db_session.commit()

        stats = await cleanup_expired_history(db_session, now=now)

        assert stats.expired_deleted == 0
        assert await count_history_records(db_session, user.id) == 1

    async def test_preserves_latest_and_deletes_older_aged_records(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """Multiple aged versioned rows: only the highest-version row survives."""
        now = datetime.now(UTC)
        entity_id = uuid4()
        aged_at = now - timedelta(days=FREE_RETENTION_DAYS + 10)
        for version in [1, 2, 3]:
            db_session.add(create_history_record(
                user_id=user.id,
                entity_type=EntityType.NOTE,
                entity_id=entity_id,
                version=version,
                created_at=aged_at,
            ))
        await db_session.commit()

        stats = await cleanup_expired_history(db_session, now=now)

        assert stats.expired_deleted == 2
        rows = (await db_session.execute(
            select(ContentHistory).where(ContentHistory.user_id == user.id),
        )).scalars().all()
        assert len(rows) == 1
        assert rows[0].version == 3

    async def test_mixed_aged_and_fresh_records(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """
        Mixed aged and fresh versioned rows for one entity: fresh rows always
        preserved. Aged rows deleted when any higher versioned row exists.
        """
        now = datetime.now(UTC)
        entity_id = uuid4()
        aged_at = now - timedelta(days=FREE_RETENTION_DAYS + 10)
        fresh_at = now - timedelta(hours=1)

        # v1, v2 aged; v3 fresh (higher than both aged).
        db_session.add(create_history_record(
            user_id=user.id, entity_type=EntityType.NOTE, entity_id=entity_id,
            version=1, created_at=aged_at,
        ))
        db_session.add(create_history_record(
            user_id=user.id, entity_type=EntityType.NOTE, entity_id=entity_id,
            version=2, created_at=aged_at,
        ))
        db_session.add(create_history_record(
            user_id=user.id, entity_type=EntityType.NOTE, entity_id=entity_id,
            version=3, created_at=fresh_at,
        ))
        await db_session.commit()

        stats = await cleanup_expired_history(db_session, now=now)

        # v1, v2 deleted (v3 higher exists). v3 preserved (fresh and latest).
        assert stats.expired_deleted == 2
        rows = (await db_session.execute(
            select(ContentHistory).where(ContentHistory.user_id == user.id),
        )).scalars().all()
        assert [r.version for r in rows] == [3]

    async def test_audit_records_still_deleted_when_aged(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """Aged audit records (NULL version) are deleted; not exempted."""
        now = datetime.now(UTC)
        entity_id = uuid4()
        aged_at = now - timedelta(days=FREE_RETENTION_DAYS + 10)
        for action in [ActionType.ARCHIVE, ActionType.UNARCHIVE, ActionType.DELETE]:
            db_session.add(create_audit_history_record(
                user_id=user.id,
                entity_type=EntityType.NOTE,
                entity_id=entity_id,
                action=action,
                created_at=aged_at,
            ))
        await db_session.commit()

        stats = await cleanup_expired_history(db_session, now=now)

        assert stats.expired_deleted == 3
        assert await count_history_records(db_session, user.id) == 0

    async def test_audit_record_does_not_count_as_latest(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """
        The "latest" anchor is the latest *versioned* row, not the latest row.
        An aged audit row newer than all versioned rows is still deleted;
        the latest versioned row is preserved.
        """
        now = datetime.now(UTC)
        entity_id = uuid4()
        old_aged = now - timedelta(days=FREE_RETENTION_DAYS + 10)
        newer_aged = now - timedelta(days=FREE_RETENTION_DAYS + 2)

        db_session.add(create_history_record(
            user_id=user.id, entity_type=EntityType.NOTE, entity_id=entity_id,
            version=1, created_at=old_aged,
        ))
        db_session.add(create_history_record(
            user_id=user.id, entity_type=EntityType.NOTE, entity_id=entity_id,
            version=2, created_at=old_aged,
        ))
        db_session.add(create_audit_history_record(
            user_id=user.id, entity_type=EntityType.NOTE, entity_id=entity_id,
            action=ActionType.ARCHIVE, created_at=newer_aged,
        ))
        await db_session.commit()

        stats = await cleanup_expired_history(db_session, now=now)

        # v1 deleted (v2 higher). Audit deleted. v2 preserved (latest versioned).
        assert stats.expired_deleted == 2
        rows = (await db_session.execute(
            select(ContentHistory).where(ContentHistory.user_id == user.id),
        )).scalars().all()
        assert len(rows) == 1
        assert rows[0].version == 2

    async def test_preservation_is_per_entity_not_per_user(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """
        One user, two entities: each entity independently retains its own
        latest versioned row. Partition is per (user_id, entity_type, entity_id).
        """
        now = datetime.now(UTC)
        aged_at = now - timedelta(days=FREE_RETENTION_DAYS + 10)
        bookmark_id, note_id = uuid4(), uuid4()
        for entity_type, entity_id in [
            (EntityType.BOOKMARK, bookmark_id),
            (EntityType.NOTE, note_id),
        ]:
            for version in [1, 2]:
                db_session.add(create_history_record(
                    user_id=user.id, entity_type=entity_type,
                    entity_id=entity_id,
                    version=version, created_at=aged_at,
                ))
        await db_session.commit()

        stats = await cleanup_expired_history(db_session, now=now)

        # Each entity preserves its v2; each v1 deleted. 2 deleted, 2 preserved.
        assert stats.expired_deleted == 2
        rows = (await db_session.execute(
            select(ContentHistory).where(ContentHistory.user_id == user.id),
        )).scalars().all()
        assert len(rows) == 2
        assert {r.entity_id for r in rows} == {bookmark_id, note_id}
        assert all(r.version == 2 for r in rows)

    async def test_preservation_respects_tier_boundaries(
        self,
        db_session: AsyncSession,
    ) -> None:
        """
        Users in different tiers: each user's entity retains exactly its
        latest versioned row, even when all rows are aged past both tier
        cutoffs. Confirms the per-tier DELETE loop interacts correctly with
        the preservation rule.
        """
        now = datetime.now(UTC)
        # Aged well past PRO's 15-day retention (and FREE's 1-day).
        aged_at = now - timedelta(days=100)

        free_user = User(
            external_auth_id=f"free-{uuid4()}", email=f"free-{uuid4()}@test.com",
            tier=Tier.FREE.value,
        )
        pro_user = User(
            external_auth_id=f"pro-{uuid4()}", email=f"pro-{uuid4()}@test.com",
            tier=Tier.PRO.value,
        )
        db_session.add_all([free_user, pro_user])
        await db_session.flush()

        free_entity_id, pro_entity_id = uuid4(), uuid4()
        for u, entity_id in [(free_user, free_entity_id), (pro_user, pro_entity_id)]:
            for version in [1, 2]:
                db_session.add(create_history_record(
                    user_id=u.id, entity_type=EntityType.NOTE, entity_id=entity_id,
                    version=version, created_at=aged_at,
                ))
        await db_session.commit()

        await cleanup_expired_history(db_session, now=now)

        for u, entity_id in [(free_user, free_entity_id), (pro_user, pro_entity_id)]:
            rows = (await db_session.execute(
                select(ContentHistory).where(ContentHistory.user_id == u.id),
            )).scalars().all()
            assert len(rows) == 1
            assert rows[0].version == 2
            assert rows[0].entity_id == entity_id

    async def test_soft_deleted_entity_history_preserved_like_active(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """
        Soft-deleted (but not yet permanently deleted) entities: the latest
        versioned history row is still preserved by time-based cleanup.
        Permanent deletion via cleanup_soft_deleted_items cascades all
        history — covered by TestCleanupSoftDeletedItems.
        """
        now = datetime.now(UTC)
        note = Note(
            user_id=user.id,
            title="Soft deleted",
            content="Content",
            deleted_at=now - timedelta(days=5),  # inside 30-day cutoff
        )
        db_session.add(note)
        await db_session.flush()

        aged_at = now - timedelta(days=FREE_RETENTION_DAYS + 10)
        for version in [1, 2]:
            db_session.add(create_history_record(
                user_id=user.id, entity_type=EntityType.NOTE, entity_id=note.id,
                version=version, created_at=aged_at,
            ))
        await db_session.commit()

        stats = await cleanup_expired_history(db_session, now=now)

        # v1 deleted; v2 preserved (latest versioned).
        assert stats.expired_deleted == 1
        rows = (await db_session.execute(
            select(ContentHistory).where(ContentHistory.user_id == user.id),
        )).scalars().all()
        assert len(rows) == 1
        assert rows[0].version == 2

    async def test_boundary_exactly_at_cutoff_unchanged(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """
        Strict `<` comparison preserves rows exactly at the cutoff, and this
        interacts correctly with the preservation rule. A row at cutoff
        that would otherwise be a non-latest version (and thus deletable)
        is preserved because it is not aged by strict `<`.
        """
        now = datetime.now(UTC)
        entity_id = uuid4()
        at_cutoff = now - timedelta(days=FREE_RETENTION_DAYS)  # not aged (strict <)
        aged = now - timedelta(days=FREE_RETENTION_DAYS, seconds=1)

        db_session.add(create_history_record(
            user_id=user.id, entity_type=EntityType.NOTE, entity_id=entity_id,
            version=1, created_at=at_cutoff,
        ))
        db_session.add(create_history_record(
            user_id=user.id, entity_type=EntityType.NOTE, entity_id=entity_id,
            version=2, created_at=aged,
        ))
        db_session.add(create_history_record(
            user_id=user.id, entity_type=EntityType.NOTE, entity_id=entity_id,
            version=3, created_at=aged,
        ))
        await db_session.commit()

        stats = await cleanup_expired_history(db_session, now=now)

        # v1 at cutoff: not aged → preserved.
        # v2 aged; v3 higher exists → deleted.
        # v3 aged; no higher versioned row → preserved (latest).
        assert stats.expired_deleted == 1
        rows = (await db_session.execute(
            select(ContentHistory)
            .where(ContentHistory.user_id == user.id)
            .order_by(ContentHistory.version),
        )).scalars().all()
        assert [r.version for r in rows] == [1, 3]

    async def test_preservation_follows_latest_across_runs(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """
        Preservation re-evaluates "latest" on each run. After one cleanup
        preserves the current latest, inserting a higher-versioned aged row
        and re-running deletes the previously preserved row and preserves
        the new latest.
        """
        now = datetime.now(UTC)
        entity_id = uuid4()
        aged_at = now - timedelta(days=FREE_RETENTION_DAYS + 10)

        for version in [1, 2, 3]:
            db_session.add(create_history_record(
                user_id=user.id, entity_type=EntityType.NOTE, entity_id=entity_id,
                version=version, created_at=aged_at,
            ))
        await db_session.commit()

        await cleanup_expired_history(db_session, now=now)
        rows = (await db_session.execute(
            select(ContentHistory).where(ContentHistory.user_id == user.id),
        )).scalars().all()
        assert [r.version for r in rows] == [3]

        # Insert a higher-versioned aged row.
        db_session.add(create_history_record(
            user_id=user.id, entity_type=EntityType.NOTE, entity_id=entity_id,
            version=4, created_at=aged_at,
        ))
        await db_session.commit()

        await cleanup_expired_history(db_session, now=now)

        # v3 now deleted (v4 higher exists). v4 preserved.
        rows = (await db_session.execute(
            select(ContentHistory).where(ContentHistory.user_id == user.id),
        )).scalars().all()
        assert [r.version for r in rows] == [4]

    async def test_same_tier_users_isolated(
        self,
        db_session: AsyncSession,
    ) -> None:
        """
        Two users in the same tier: the tier-batched DELETE preserves each
        user's own latest versioned row. Partition is per
        (user_id, entity_type, entity_id); users don't bleed into each other.
        """
        now = datetime.now(UTC)
        aged_at = now - timedelta(days=FREE_RETENTION_DAYS + 10)
        user_a = User(
            external_auth_id=f"a-{uuid4()}", email=f"a-{uuid4()}@test.com",
            tier=Tier.FREE.value,
        )
        user_b = User(
            external_auth_id=f"b-{uuid4()}", email=f"b-{uuid4()}@test.com",
            tier=Tier.FREE.value,
        )
        db_session.add_all([user_a, user_b])
        await db_session.flush()

        entity_a, entity_b = uuid4(), uuid4()
        for u, entity_id in [(user_a, entity_a), (user_b, entity_b)]:
            for version in [1, 2]:
                db_session.add(create_history_record(
                    user_id=u.id, entity_type=EntityType.NOTE, entity_id=entity_id,
                    version=version, created_at=aged_at,
                ))
        await db_session.commit()

        await cleanup_expired_history(db_session, now=now)

        for u, entity_id in [(user_a, entity_a), (user_b, entity_b)]:
            rows = (await db_session.execute(
                select(ContentHistory).where(ContentHistory.user_id == u.id),
            )).scalars().all()
            assert len(rows) == 1
            assert rows[0].version == 2
            assert rows[0].entity_id == entity_id

    @pytest.mark.parametrize(
        ("preserved_version", "has_snapshot"),
        [
            (5, False),   # non-modulo-10: diff only, no snapshot
            (10, True),   # modulo-10: snapshot set
        ],
    )
    async def test_view_content_at_preserved_version(
        self,
        db_session: AsyncSession,
        user: User,
        preserved_version: int,
        has_snapshot: bool,
    ) -> None:
        """
        After cleanup leaves a single preserved row, reconstruction at that
        version returns correct content. Pins both shapes: modulo-10
        (snapshot present) and non-modulo (diff only, entity.content anchor).

        When target_version == latest_version (single-row post-cleanup),
        reconstruction short-circuits: returns content_snapshot if present,
        else entity.content. Both should equal the entity's current content.
        """
        now = datetime.now(UTC)
        entity_content = "current content"
        note = Note(user_id=user.id, title="Test", content=entity_content)
        db_session.add(note)
        await db_session.flush()

        aged_at = now - timedelta(days=FREE_RETENTION_DAYS + 10)
        # UPDATE row at `preserved_version` with a real reverse diff
        # (preserved_version -> preserved_version-1). content_snapshot is set
        # only for modulo-10 versions per real-system semantics. Generating
        # a valid diff here (instead of a placeholder) makes the test robust
        # if reconstruction ever changes to apply the target row's own diff —
        # a failure would then point at the preservation rule, not a cryptic
        # diff parser error.
        reverse_diff = history_service.dmp.patch_toText(
            history_service.dmp.patch_make(entity_content, "prior content"),
        )
        db_session.add(create_versioned_history_record(
            user_id=user.id,
            entity_type=EntityType.NOTE,
            entity_id=note.id,
            version=preserved_version,
            action=ActionType.UPDATE,
            content_snapshot=entity_content if has_snapshot else None,
            content_diff=reverse_diff,
            created_at=aged_at,
        ))
        await db_session.commit()

        await cleanup_expired_history(db_session, now=now)

        # Single row preserved.
        rows = (await db_session.execute(
            select(ContentHistory).where(ContentHistory.user_id == user.id),
        )).scalars().all()
        assert len(rows) == 1
        assert rows[0].version == preserved_version
        assert (rows[0].content_snapshot is not None) is has_snapshot

        # Reconstruction at the preserved version returns entity.content.
        result = await history_service.reconstruct_content_at_version(
            db_session, user.id, EntityType.NOTE, note.id, preserved_version,
        )
        assert result.found is True
        assert result.content == entity_content

    async def test_create_only_entity_preserved_when_aged(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """
        Entity with exactly one history record — a CREATE (action='create',
        version=1, content_snapshot set, content_diff None) — aged past
        cutoff is preserved. CREATE rows are first-class preservation-eligible
        rows; not excluded by any check that assumes content_diff is set.
        """
        now = datetime.now(UTC)
        entity_id = uuid4()
        db_session.add(create_versioned_history_record(
            user_id=user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            version=1,
            action=ActionType.CREATE,
            content_snapshot="Initial content",
            content_diff=None,
            created_at=now - timedelta(days=FREE_RETENTION_DAYS + 10),
        ))
        await db_session.commit()

        stats = await cleanup_expired_history(db_session, now=now)

        assert stats.expired_deleted == 0
        rows = (await db_session.execute(
            select(ContentHistory).where(ContentHistory.user_id == user.id),
        )).scalars().all()
        assert len(rows) == 1
        assert rows[0].action == ActionType.CREATE.value
        assert rows[0].version == 1
        assert rows[0].content_snapshot == "Initial content"
        assert rows[0].content_diff is None


class TestCleanupOrphanedHistory:
    """Test orphaned history cleanup."""

    @pytest.fixture
    async def user(self, db_session: AsyncSession) -> User:
        """Create a test user."""
        user = User(
            external_auth_id=f"test-orphan-{uuid4()}",
            email=f"orphan-{uuid4()}@test.com",
            tier=Tier.FREE.value,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    async def test__orphaned_bookmark_history__deleted(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """History for non-existent bookmark is deleted."""
        # Create orphaned history (no corresponding bookmark)
        orphan_id = uuid4()
        db_session.add(create_history_record(
            user_id=user.id,
            entity_type=EntityType.BOOKMARK,
            entity_id=orphan_id,
        ))
        await db_session.commit()

        # Run cleanup
        stats = await cleanup_orphaned_history(db_session)

        # Orphan deleted
        assert stats.orphaned_deleted == 1
        assert stats.orphaned_by_entity_type[EntityType.BOOKMARK.value] == 1
        assert await count_history_records(db_session, user.id) == 0

    async def test__orphaned_note_history__deleted(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """History for non-existent note is deleted."""
        orphan_id = uuid4()
        db_session.add(create_history_record(
            user_id=user.id,
            entity_type=EntityType.NOTE,
            entity_id=orphan_id,
        ))
        await db_session.commit()

        stats = await cleanup_orphaned_history(db_session)

        assert stats.orphaned_deleted == 1
        assert stats.orphaned_by_entity_type[EntityType.NOTE.value] == 1

    async def test__orphaned_prompt_history__deleted(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """History for non-existent prompt is deleted."""
        orphan_id = uuid4()
        db_session.add(create_history_record(
            user_id=user.id,
            entity_type=EntityType.PROMPT,
            entity_id=orphan_id,
        ))
        await db_session.commit()

        stats = await cleanup_orphaned_history(db_session)

        assert stats.orphaned_deleted == 1
        assert stats.orphaned_by_entity_type[EntityType.PROMPT.value] == 1

    async def test__existing_entity_history__not_deleted(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """History for existing entity is NOT deleted."""
        # Create a real note
        note = Note(
            user_id=user.id,
            title="Real Note",
            content="Real content",
        )
        db_session.add(note)
        await db_session.flush()

        # Create history for the real note
        db_session.add(create_history_record(
            user_id=user.id,
            entity_type=EntityType.NOTE,
            entity_id=note.id,
        ))
        await db_session.commit()

        # Run cleanup
        stats = await cleanup_orphaned_history(db_session)

        # Nothing deleted - entity exists
        assert stats.orphaned_deleted == 0
        assert await count_history_records(db_session, user.id) == 1

    async def test__soft_deleted_entity_history__not_deleted(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """
        History for soft-deleted entity is NOT deleted.

        Soft-deleted entities still exist in the database (deleted_at IS NOT NULL).
        Their history should be preserved until permanent deletion.
        """
        # Create a note and soft-delete it
        note = Note(
            user_id=user.id,
            title="Soft Deleted Note",
            content="Will be soft deleted",
        )
        db_session.add(note)
        await db_session.flush()

        # Create history for the note
        db_session.add(create_history_record(
            user_id=user.id,
            entity_type=EntityType.NOTE,
            entity_id=note.id,
        ))

        # Soft delete the note
        note.deleted_at = datetime.now(UTC)
        await db_session.commit()

        # Run cleanup
        stats = await cleanup_orphaned_history(db_session)

        # Nothing deleted - soft-deleted entity still exists in DB
        assert stats.orphaned_deleted == 0
        assert await count_history_records(db_session, user.id) == 1

    async def test__mixed_orphaned_and_valid__only_orphans_deleted(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """With mixed records, only orphaned history is deleted."""
        # Create real entities
        note = Note(user_id=user.id, title="Real", content="Content")
        bookmark = Bookmark(user_id=user.id, url="https://example.com")
        db_session.add(note)
        db_session.add(bookmark)
        await db_session.flush()

        # Create history for real entities
        db_session.add(create_history_record(
            user_id=user.id,
            entity_type=EntityType.NOTE,
            entity_id=note.id,
        ))
        db_session.add(create_history_record(
            user_id=user.id,
            entity_type=EntityType.BOOKMARK,
            entity_id=bookmark.id,
        ))

        # Create orphaned history
        db_session.add(create_history_record(
            user_id=user.id,
            entity_type=EntityType.NOTE,
            entity_id=uuid4(),  # Non-existent
        ))
        db_session.add(create_history_record(
            user_id=user.id,
            entity_type=EntityType.PROMPT,
            entity_id=uuid4(),  # Non-existent
        ))
        await db_session.commit()

        # Run cleanup
        stats = await cleanup_orphaned_history(db_session)

        # 2 orphans deleted, 2 valid kept
        assert stats.orphaned_deleted == 2
        assert await count_history_records(db_session, user.id) == 2

    async def test__no_orphans__nothing_deleted(
        self,
        db_session: AsyncSession,
        user: User,
    ) -> None:
        """When there are no orphans, nothing is deleted."""
        # Create real note with history
        note = Note(user_id=user.id, title="Real", content="Content")
        db_session.add(note)
        await db_session.flush()

        db_session.add(create_history_record(
            user_id=user.id,
            entity_type=EntityType.NOTE,
            entity_id=note.id,
        ))
        await db_session.commit()

        # Run cleanup
        stats = await cleanup_orphaned_history(db_session)

        assert stats.orphaned_deleted == 0
        assert len(stats.orphaned_by_entity_type) == 0


class TestCleanupEmptyScenarios:
    """Test cleanup handles empty scenarios correctly."""

    async def test__no_users__completes_without_error(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Cleanup completes successfully when there are no users."""
        # Run cleanup on empty-ish database
        stats = await cleanup_expired_history(db_session, now=datetime.now(UTC))

        # Should complete without error
        assert stats.expired_deleted == 0

    async def test__no_history_records__completes_without_error(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Cleanup completes successfully when there's no history."""
        # Create user but no history
        user = User(
            external_auth_id=f"test-nohistory-{uuid4()}",
            email=f"nohistory-{uuid4()}@test.com",
            tier=Tier.FREE.value,
        )
        db_session.add(user)
        await db_session.commit()

        # Run both cleanups
        expired_stats = await cleanup_expired_history(db_session, now=datetime.now(UTC))
        orphan_stats = await cleanup_orphaned_history(db_session)

        assert expired_stats.expired_deleted == 0
        assert orphan_stats.orphaned_deleted == 0

    async def test__no_soft_deleted_items__completes_without_error(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Soft-delete cleanup completes when there are no soft-deleted items."""
        # Create active note (not deleted)
        user = User(
            external_auth_id=f"test-active-{uuid4()}",
            email=f"active-{uuid4()}@test.com",
            tier=Tier.FREE.value,
        )
        db_session.add(user)
        await db_session.flush()

        note = Note(user_id=user.id, title="Active", content="Content")
        db_session.add(note)
        await db_session.commit()

        stats = await cleanup_soft_deleted_items(db_session, now=datetime.now(UTC))

        assert stats.soft_deleted_expired == 0


class TestRunCleanupIntegration:
    """Integration tests for the full cleanup flow."""

    async def test__run_cleanup__executes_all_cleanup_types(
        self,
        db_session: AsyncSession,
    ) -> None:
        """run_cleanup executes soft-delete, expired, and orphan cleanup."""
        now = datetime.now(UTC)

        # Create user
        user = User(
            external_auth_id=f"test-integration-{uuid4()}",
            email=f"integration-{uuid4()}@test.com",
            tier=Tier.FREE.value,
        )
        db_session.add(user)
        await db_session.flush()

        # Create real note
        note = Note(user_id=user.id, title="Real", content="Content")
        db_session.add(note)
        await db_session.flush()

        # Create expired soft-deleted note
        deleted_note = Note(
            user_id=user.id,
            title="Deleted",
            content="Content",
            deleted_at=now - timedelta(days=60),
        )
        db_session.add(deleted_note)
        await db_session.flush()

        # Create history: 1 old record (expired), 1 new record (keep), 1 orphan
        db_session.add(create_history_record(
            user_id=user.id,
            entity_type=EntityType.NOTE,
            entity_id=note.id,
            version=1,
            created_at=now - timedelta(days=60),  # Old - delete
        ))
        db_session.add(create_history_record(
            user_id=user.id,
            entity_type=EntityType.NOTE,
            entity_id=note.id,
            version=2,
            created_at=now - timedelta(hours=1),  # Recent - keep
        ))
        db_session.add(create_history_record(
            user_id=user.id,
            entity_type=EntityType.BOOKMARK,
            entity_id=uuid4(),  # Orphan - delete
        ))
        # History for the deleted note
        db_session.add(create_history_record(
            user_id=user.id,
            entity_type=EntityType.NOTE,
            entity_id=deleted_note.id,
        ))
        await db_session.commit()

        # Run full cleanup
        stats = await run_cleanup(db=db_session, now=now)

        # Verify combined results
        assert stats.soft_deleted_expired == 1  # The deleted note
        assert stats.expired_deleted == 1  # One old history record
        assert stats.orphaned_deleted == 1  # One orphan

        # Only the new, valid record remains
        assert await count_history_records(db_session, user.id) == 1
        # Only the active note remains
        assert await count_entities(db_session, Note, user.id) == 1

    async def test__run_cleanup__order_matters(
        self,
        db_session: AsyncSession,
    ) -> None:
        """
        Soft-delete cleanup runs first, so its history is deleted before
        expired history cleanup, preventing double-counting.
        """
        now = datetime.now(UTC)

        user = User(
            external_auth_id=f"test-order-{uuid4()}",
            email=f"order-{uuid4()}@test.com",
            tier=Tier.FREE.value,
        )
        db_session.add(user)
        await db_session.flush()

        # Create expired soft-deleted note with old history
        deleted_note = Note(
            user_id=user.id,
            title="Deleted",
            content="Content",
            deleted_at=now - timedelta(days=60),
        )
        db_session.add(deleted_note)
        await db_session.flush()

        # This history is old AND belongs to a soft-deleted entity
        db_session.add(create_history_record(
            user_id=user.id,
            entity_type=EntityType.NOTE,
            entity_id=deleted_note.id,
            created_at=now - timedelta(days=60),
        ))
        await db_session.commit()

        stats = await run_cleanup(db=db_session, now=now)

        # Soft-delete cleanup handles the entity and its history
        assert stats.soft_deleted_expired == 1
        # Expired cleanup doesn't double-count (history already deleted)
        assert stats.expired_deleted == 0

    async def test__run_cleanup__stats_breakdown_is_accurate(
        self,
        db_session: AsyncSession,
    ) -> None:
        """
        Verify detailed breakdown in stats matches actual deletions.

        Three aged v1 rows share one entity_id so they're non-latest relative
        to a fresh v4 anchor; this keeps them deletable under the preservation
        rule while still exercising the tier DELETE stats.
        """
        now = datetime.now(UTC)

        user = User(
            external_auth_id=f"test-breakdown-{uuid4()}",
            email=f"breakdown-{uuid4()}@test.com",
            tier=Tier.FREE.value,
        )
        db_session.add(user)
        await db_session.flush()

        # One real entity with 3 aged rows (v1, v2, v3) and a fresh v4 anchor.
        # The real Note prevents the preserved v4 anchor from being caught by
        # orphan cleanup later in run_cleanup.
        real_note = Note(user_id=user.id, title="Real", content="Content")
        db_session.add(real_note)
        await db_session.flush()
        for v in [1, 2, 3]:
            db_session.add(create_history_record(
                user_id=user.id,
                entity_type=EntityType.NOTE,
                entity_id=real_note.id,
                version=v,
                created_at=now - timedelta(days=60),
            ))
        db_session.add(create_history_record(
            user_id=user.id,
            entity_type=EntityType.NOTE,
            entity_id=real_note.id,
            version=4,
            created_at=now - timedelta(hours=1),
        ))

        # Add orphans of different types
        db_session.add(create_history_record(
            user_id=user.id,
            entity_type=EntityType.PROMPT,
            entity_id=uuid4(),
        ))
        db_session.add(create_history_record(
            user_id=user.id,
            entity_type=EntityType.PROMPT,
            entity_id=uuid4(),
        ))

        # Create expired soft-deleted items
        for _ in range(2):
            note = Note(
                user_id=user.id,
                title="Deleted",
                content="Content",
                deleted_at=now - timedelta(days=60),
            )
            db_session.add(note)
        await db_session.commit()

        # Run full cleanup
        stats = await run_cleanup(db=db_session, now=now)

        # Verify soft-delete breakdown
        assert stats.soft_deleted_expired == 2
        assert stats.soft_deleted_by_type["notes"] == 2

        # Verify expired breakdown: 3 aged rows deleted, v4 anchor preserved.
        assert stats.expired_by_tier[Tier.FREE.value] == 3
        assert stats.expired_deleted == 3

        # Verify orphan breakdown
        assert stats.orphaned_by_entity_type[EntityType.PROMPT.value] == 2
        assert stats.orphaned_deleted == 2

    async def test__run_cleanup_twice__second_run_deletes_nothing(
        self,
        db_session: AsyncSession,
    ) -> None:
        """
        Running cleanup twice is idempotent - second run deletes nothing.

        This is critical for cron jobs that might restart or run multiple times.
        """
        now = datetime.now(UTC)

        user = User(
            external_auth_id=f"test-idempotent-{uuid4()}",
            email=f"idempotent-{uuid4()}@test.com",
            tier=Tier.FREE.value,
        )
        db_session.add(user)
        await db_session.flush()

        # Create data that will be cleaned up
        # 1. Expired soft-deleted note
        deleted_note = Note(
            user_id=user.id,
            title="Deleted",
            content="Content",
            deleted_at=now - timedelta(days=60),
        )
        db_session.add(deleted_note)
        await db_session.flush()

        # 2. Old history record (v1 aged) + fresh v2 anchor so v1 is deletable
        #    under the preservation rule. Anchor to a real Note so the v2
        #    anchor isn't swept up as an orphan by step 3 of run_cleanup.
        real_note = Note(user_id=user.id, title="Real", content="Content")
        db_session.add(real_note)
        await db_session.flush()
        db_session.add(create_history_record(
            user_id=user.id,
            entity_type=EntityType.NOTE,
            entity_id=real_note.id,
            version=1,
            created_at=now - timedelta(days=60),
        ))
        db_session.add(create_history_record(
            user_id=user.id,
            entity_type=EntityType.NOTE,
            entity_id=real_note.id,
            version=2,
            created_at=now - timedelta(hours=1),
        ))

        # 3. Orphaned history
        db_session.add(create_history_record(
            user_id=user.id,
            entity_type=EntityType.BOOKMARK,
            entity_id=uuid4(),
        ))
        await db_session.commit()

        # First run - should delete everything
        first_stats = await run_cleanup(db=db_session, now=now)
        assert first_stats.soft_deleted_expired == 1
        assert first_stats.expired_deleted == 1
        assert first_stats.orphaned_deleted == 1

        # Second run - should delete nothing (idempotent)
        second_stats = await run_cleanup(db=db_session, now=now)
        assert second_stats.soft_deleted_expired == 0
        assert second_stats.expired_deleted == 0
        assert second_stats.orphaned_deleted == 0


class TestCleanupStatsDataclass:
    """Tests for the CleanupStats dataclass."""

    def test__to_dict__returns_summary(self) -> None:
        """to_dict returns a simple summary dict."""
        stats = CleanupStats(
            soft_deleted_expired=2,
            expired_deleted=5,
            orphaned_deleted=3,
            tombstones_deleted=1,
            soft_deleted_by_type={"notes": 1, "bookmarks": 1},
            expired_by_tier={"free": 5},
            orphaned_by_entity_type={"note": 2, "bookmark": 1},
        )

        result = stats.to_dict()

        assert result == {
            "soft_deleted_expired": 2,
            "expired_deleted": 5,
            "orphaned_deleted": 3,
            "tombstones_deleted": 1,
        }
        # Detailed breakdowns not in summary
        assert "soft_deleted_by_type" not in result
        assert "expired_by_tier" not in result
        assert "orphaned_by_entity_type" not in result

    def test__default_values__are_empty(self) -> None:
        """Default CleanupStats has zero counts and empty dicts."""
        stats = CleanupStats()

        assert stats.soft_deleted_expired == 0
        assert stats.expired_deleted == 0
        assert stats.orphaned_deleted == 0
        assert stats.soft_deleted_by_type == {}
        assert stats.expired_by_tier == {}
        assert stats.orphaned_by_entity_type == {}


class TestCleanupExpiredTombstones:
    """The M6b tombstone retention sweep (see models/deleted_identity.py)."""

    async def test__aged_tombstone_swept__recent_kept(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Only tombstones older than the retention period are deleted."""
        aged = DeletedIdentity(external_auth_id=f"user_aged_{uuid4()}")
        fresh = DeletedIdentity(external_auth_id=f"user_fresh_{uuid4()}")
        db_session.add_all([aged, fresh])
        await db_session.flush()
        # Backdate the aged tombstone past the retention window.
        aged.created_at = datetime.now(UTC) - timedelta(
            days=DELETED_IDENTITY_RETENTION_DAYS + 1,
        )
        await db_session.flush()

        stats = await cleanup_expired_tombstones(db_session)

        assert stats.tombstones_deleted == 1
        remaining = (await db_session.execute(select(DeletedIdentity.external_auth_id))).scalars().all()
        assert fresh.external_auth_id in remaining
        assert aged.external_auth_id not in remaining

    async def test__boundary__retention_old_not_swept_until_past_cutoff(
        self,
        db_session: AsyncSession,
    ) -> None:
        """A tombstone exactly at the retention boundary survives (strict <)."""
        now = datetime.now(UTC)
        boundary = DeletedIdentity(external_auth_id=f"user_boundary_{uuid4()}")
        db_session.add(boundary)
        await db_session.flush()
        boundary.created_at = now - timedelta(days=DELETED_IDENTITY_RETENTION_DAYS)
        await db_session.flush()

        stats = await cleanup_expired_tombstones(db_session, now=now)

        assert stats.tombstones_deleted == 0

    async def test__run_cleanup__includes_tombstone_sweep(
        self,
        db_session: AsyncSession,
    ) -> None:
        """run_cleanup reports swept tombstones in its combined stats."""
        aged = DeletedIdentity(external_auth_id=f"user_run_aged_{uuid4()}")
        db_session.add(aged)
        await db_session.flush()
        aged.created_at = datetime.now(UTC) - timedelta(
            days=DELETED_IDENTITY_RETENTION_DAYS + 1,
        )
        await db_session.flush()

        stats = await run_cleanup(db=db_session)

        assert stats.tombstones_deleted >= 1
