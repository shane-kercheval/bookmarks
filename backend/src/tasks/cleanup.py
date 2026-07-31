"""
Scheduled cleanup task.

This module provides time-based cleanup of history records and soft-deleted
entities. Designed to run as a cron job (e.g., daily at 3 AM).

Usage:
    python -m tasks.cleanup

The task:
1. Permanently deletes soft-deleted entities older than 30 days (with their history)
2. Deletes history records older than each tier's retention_days
3. Cleans up orphaned history (entities that no longer exist)
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from core.tier_limits import TIER_LIMITS, Tier
from models.bookmark import Bookmark
from models.content_history import ContentHistory, EntityType
from models.deleted_identity import DeletedIdentity
from models.note import Note
from models.prompt import Prompt
from models.user import User
from services.history_service import history_service

logger = logging.getLogger(__name__)

# Last-updated marker for the cleanup task. Logged on each scheduled run so
# the deployed code revision is visible in Railway logs without needing to
# inspect the image SHA. **Update this to the current UTC timestamp whenever
# cleanup logic changes** (format: YYYY-MM-DDTHH:MMZ). Minute precision
# distinguishes multiple same-day pushes; a stale deploy is then immediately
# obvious in the logs.
CLEANUP_TASK_VERSION = "2026-07-31T18:30Z"

# Default expiry for soft-deleted items (days in trash before permanent deletion)
SOFT_DELETE_EXPIRY_DAYS = 30

# Retention for deleted-identity tombstones (see models/deleted_identity.py).
# Safe only post-M6b: with the Auth0 auth path gone, a tombstone's job ends
# when the deleted account's last Clerk token expires (~1 day); 30 days is a
# comfortable multiple. Do NOT shorten below the longest possible token
# lifetime — a swept tombstone reopens the JIT-resurrection hole for any
# still-valid token.
DELETED_IDENTITY_RETENTION_DAYS = 30


@dataclass
class CleanupStats:
    """Statistics from a cleanup run."""

    soft_deleted_expired: int = 0
    expired_deleted: int = 0
    orphaned_deleted: int = 0
    tombstones_deleted: int = 0

    # Detailed breakdowns for verification
    soft_deleted_by_type: dict[str, int] = field(default_factory=dict)
    expired_by_tier: dict[str, int] = field(default_factory=dict)
    orphaned_by_entity_type: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, int]:
        """Convert to simple dict for logging/return."""
        return {
            "soft_deleted_expired": self.soft_deleted_expired,
            "expired_deleted": self.expired_deleted,
            "orphaned_deleted": self.orphaned_deleted,
            "tombstones_deleted": self.tombstones_deleted,
        }


async def cleanup_soft_deleted_items(
    db: AsyncSession,
    now: datetime | None = None,
    expiry_days: int = SOFT_DELETE_EXPIRY_DAYS,
) -> CleanupStats:
    """
    Permanently delete soft-deleted items older than expiry_days.

    This supports GDPR "right to erasure" - items in trash are eventually
    permanently removed. History is cascade-deleted at application level
    before the entity is deleted.

    Args:
        db: Database session.
        now: Current time for cutoff calculation. Defaults to datetime.now(UTC).
        expiry_days: Days after soft-delete before permanent deletion.

    Returns:
        CleanupStats with soft_deleted_by_type breakdown.
    """
    if now is None:
        now = datetime.now(UTC)

    stats = CleanupStats()
    cutoff = now - timedelta(days=expiry_days)

    # Map entity types to their models
    entity_models: list[tuple[type, str, str]] = [
        (Bookmark, "bookmark", "bookmarks"),
        (Note, "note", "notes"),
        (Prompt, "prompt", "prompts"),
    ]

    for model, entity_type, type_key in entity_models:
        # Find expired soft-deleted items
        stmt = select(model).where(
            model.deleted_at.is_not(None),
            model.deleted_at < cutoff,
        )
        result = await db.execute(stmt)
        items = result.scalars().all()

        for item in items:
            # Delete history first (application-level cascade)
            await history_service.delete_entity_history(
                db, item.user_id, entity_type, item.id,
            )
            await db.delete(item)

        deleted_count = len(items)
        if deleted_count > 0:
            stats.soft_deleted_by_type[type_key] = deleted_count
            stats.soft_deleted_expired += deleted_count
            logger.info(
                "Permanently deleted %d expired %s (soft-deleted > %d days)",
                deleted_count,
                type_key,
                expiry_days,
            )

    await db.commit()
    return stats


async def cleanup_expired_history(
    db: AsyncSession,
    now: datetime | None = None,
) -> CleanupStats:
    """
    Delete history records older than retention period, batched by tier,
    except the most recent versioned record per entity.

    For each tier:
    1. Calculate the cutoff date based on tier's history_retention_days
    2. Delete all aged history records for users in that tier EXCEPT the
       single most recent versioned record per (user_id, entity_type, entity_id)

    Preserving the latest versioned record per entity guarantees diff and
    restore remain functional after long idle periods. Audit records
    (DELETE/UNDELETE/ARCHIVE/UNARCHIVE — NULL version) carry no diff/restore
    value and remain fully subject to time-based pruning.

    This is more efficient than per-user deletion as it executes one DELETE
    per tier rather than one per user.

    Args:
        db: Database session.
        now: Current time for cutoff calculation. Defaults to datetime.now(UTC).
             Inject a specific time for testing boundary conditions.

    Returns:
        CleanupStats with expired_by_tier breakdown.
    """
    if now is None:
        now = datetime.now(UTC)

    stats = CleanupStats()

    # Batch by tier: single DELETE per tier (more efficient than per-user)
    for tier, limits in TIER_LIMITS.items():
        cutoff = now - timedelta(days=limits.history_retention_days)

        # Delete aged history for users in this tier, preserving the single
        # latest versioned row per entity. Use coalesce to handle NULL tier
        # values (default to FREE).
        #
        # A row is deletable when aged AND either:
        #   - it's an audit row (version IS NULL), OR
        #   - a higher-versioned row exists for the same entity.
        #
        # IMPORTANT — foot-gun warning: do NOT narrow the `newer` self-alias
        # by `newer.created_at < cutoff` or similar. The comparison must span
        # ALL versioned rows for the entity (aged or fresh). Narrowing to
        # aged-only would preserve a stale aged anchor even when a fresh
        # higher-versioned row already exists, reintroducing the original bug
        # in a different shape.
        newer = aliased(ContentHistory)
        delete_stmt = delete(ContentHistory).where(
            ContentHistory.user_id.in_(
                select(User.id).where(
                    func.coalesce(User.tier, Tier.FREE.value) == tier.value,
                ),
            ),
            ContentHistory.created_at < cutoff,
            or_(
                ContentHistory.version.is_(None),
                select(1).where(
                    newer.user_id == ContentHistory.user_id,
                    newer.entity_type == ContentHistory.entity_type,
                    newer.entity_id == ContentHistory.entity_id,
                    newer.version.is_not(None),
                    newer.version > ContentHistory.version,
                ).exists(),
            ),
        )

        result = await db.execute(delete_stmt)
        deleted = result.rowcount

        if deleted > 0:
            stats.expired_by_tier[tier.value] = deleted
            stats.expired_deleted += deleted
            logger.info(
                "Cleaned %d expired history records for tier=%s (cutoff=%s)",
                deleted,
                tier.value,
                cutoff.isoformat(),
            )

    await db.commit()
    return stats


async def cleanup_orphaned_history(db: AsyncSession) -> CleanupStats:
    """
    Delete history records for entities that no longer exist.

    This handles edge cases where:
    - Entity was permanently deleted but history records remain
    - Entity-history relationship becomes inconsistent

    With entity-anchored reconstruction, orphaned history is useless.

    Note: Soft-deleted entities (deleted_at IS NOT NULL) are NOT considered
    orphaned - their history should be preserved until permanent deletion.

    Returns:
        CleanupStats with orphan breakdown by entity type.
    """
    stats = CleanupStats()

    # Map entity types to their models
    entity_models = {
        EntityType.BOOKMARK.value: Bookmark,
        EntityType.NOTE.value: Note,
        EntityType.PROMPT.value: Prompt,
    }

    for entity_type, model in entity_models.items():
        # Find history records where entity doesn't exist at all
        # (not even soft-deleted). Using NOT EXISTS subquery for efficiency.
        entity_exists_subquery = (
            select(model.id).where(model.id == ContentHistory.entity_id).exists()
        )

        delete_stmt = delete(ContentHistory).where(
            ContentHistory.entity_type == entity_type,
            ~entity_exists_subquery,
        )

        result = await db.execute(delete_stmt)
        deleted = result.rowcount

        if deleted > 0:
            stats.orphaned_by_entity_type[entity_type] = deleted
            stats.orphaned_deleted += deleted
            logger.info(
                "Cleaned %d orphaned history records for entity_type=%s",
                deleted,
                entity_type,
            )

    await db.commit()

    return stats


async def cleanup_expired_tombstones(
    db: AsyncSession,
    now: datetime | None = None,
    retention_days: int = DELETED_IDENTITY_RETENTION_DAYS,
) -> CleanupStats:
    """
    Delete deleted-identity tombstones older than the retention period.

    A tombstone only needs to outlive the deleted account's last still-valid
    token (see DELETED_IDENTITY_RETENTION_DAYS); after that it is inert PII
    (provider user IDs) with no remaining guard value.

    Args:
        db: Database session.
        now: Current time for cutoff calculation. Defaults to datetime.now(UTC).
        retention_days: Days a tombstone is retained after creation.

    Returns:
        CleanupStats with tombstones_deleted set.
    """
    if now is None:
        now = datetime.now(UTC)

    stats = CleanupStats()
    cutoff = now - timedelta(days=retention_days)

    result = await db.execute(
        delete(DeletedIdentity).where(DeletedIdentity.created_at < cutoff),
    )
    stats.tombstones_deleted = result.rowcount

    if stats.tombstones_deleted > 0:
        logger.info(
            "Cleaned %d deleted-identity tombstones (older than %d days)",
            stats.tombstones_deleted,
            retention_days,
        )

    await db.commit()
    return stats


async def run_cleanup(
    db: AsyncSession | None = None,
    now: datetime | None = None,
) -> CleanupStats:
    """
    Run all cleanup tasks.

    Order matters:
    1. Soft-delete expiry first (permanently deletes entities + their history)
    2. Expired history cleanup (deletes old history based on tier limits)
    3. Orphan cleanup (catches any edge cases)
    4. Deleted-identity tombstone expiry (independent of the others)

    Args:
        db: Database session. If None, creates one from async_session_factory.
        now: Current time for cutoff calculation. Defaults to datetime.now(UTC).

    Returns:
        Combined CleanupStats from all cleanup operations.
    """
    logger.info("Starting cleanup task (version=%s)", CLEANUP_TASK_VERSION)

    async def _run(session: AsyncSession) -> CleanupStats:
        # 1. Permanently delete soft-deleted items older than 30 days
        soft_delete_stats = await cleanup_soft_deleted_items(session, now=now)

        # 2. Time-based history cleanup
        expired_stats = await cleanup_expired_history(session, now=now)

        # 3. Orphan cleanup (defense-in-depth)
        orphan_stats = await cleanup_orphaned_history(session)

        # 4. Deleted-identity tombstone expiry
        tombstone_stats = await cleanup_expired_tombstones(session, now=now)

        # Combine stats
        return CleanupStats(
            soft_deleted_expired=soft_delete_stats.soft_deleted_expired,
            expired_deleted=expired_stats.expired_deleted,
            orphaned_deleted=orphan_stats.orphaned_deleted,
            tombstones_deleted=tombstone_stats.tombstones_deleted,
            soft_deleted_by_type=soft_delete_stats.soft_deleted_by_type,
            expired_by_tier=expired_stats.expired_by_tier,
            orphaned_by_entity_type=orphan_stats.orphaned_by_entity_type,
        )

    if db is not None:
        stats = await _run(db)
    else:
        # Deferred: db.session triggers get_settings() at import time, which
        # breaks test collection (Settings validation runs before fixtures).
        from db.session import async_session_factory  # noqa: PLC0415

        async with async_session_factory() as session:
            stats = await _run(session)

    logger.info("Cleanup complete: %s", stats.to_dict())
    return stats


def main() -> None:
    """Entry point for running cleanup as a script."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(run_cleanup())


if __name__ == "__main__":
    main()
