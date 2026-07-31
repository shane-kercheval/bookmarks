"""Tests for the HistoryService."""
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from diff_match_patch import diff_match_patch
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.request_context import AuthType, RequestContext
from core.tier_limits import TierLimits
from models.content_history import ActionType, ContentHistory, EntityType
from models.note import Note
from models.user import User
from services.history_service import (
    PRUNE_CHECK_INTERVAL,
    SNAPSHOT_INTERVAL,
    history_service,
)


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user for history service tests."""
    user = User(
        external_auth_id="test-auth0-id-history-service",
        email="historyservice@test.com",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def request_context() -> RequestContext:
    """Create a test request context."""
    return RequestContext(
        source="web",
        auth_type=AuthType.SESSION,
        token_prefix=None,
    )


@pytest.fixture
def pat_context() -> RequestContext:
    """Create a test request context with PAT auth."""
    return RequestContext(
        source="mcp-content",
        auth_type=AuthType.PAT,
        token_prefix="bm_test1234567",
    )


@pytest.fixture
async def test_note(db_session: AsyncSession, test_user: User) -> Note:
    """Create a test note for history tests."""
    note = Note(
        user_id=test_user.id,
        title="Test Note",
        content="Initial content",
    )
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)
    return note


class TestHistoryServiceRecordAction:
    """Tests for HistoryService.record_action()."""

    async def test__record_action__create_stores_snapshot(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """CREATE action stores content as snapshot with no diff."""
        entity_id = uuid4()
        content = "Hello World"
        metadata = {"title": "Test", "tags": []}

        history = await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content=content,
            previous_content=None,
            metadata=metadata,
            context=request_context,
        )

        assert history.version == 1
        assert history.content_snapshot == content
        assert history.content_diff is None
        assert history.action == ActionType.CREATE.value

    async def test__record_action__update_stores_diff(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """UPDATE action stores diff when content changes."""
        entity_id = uuid4()
        metadata = {"title": "Test", "tags": []}

        # Create v1
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content="Hello",
            previous_content=None,
            metadata=metadata,
            context=request_context,
        )

        # Update v2
        history = await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.UPDATE,
            current_content="Hello World",
            previous_content="Hello",
            metadata=metadata,
            context=request_context,
        )

        assert history.version == 2
        assert history.content_snapshot is None
        assert history.content_diff is not None
        assert history.action == ActionType.UPDATE.value

    async def test__record_action__metadata_only_change(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """Metadata-only change (content unchanged) stores METADATA type."""
        entity_id = uuid4()
        content = "Hello World"

        # Create v1
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content=content,
            previous_content=None,
            metadata={"title": "Test", "tags": []},
            context=request_context,
        )

        # Update v2 with same content but different metadata
        history = await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.UPDATE,
            current_content=content,
            previous_content=content,  # Same as current
            metadata={"title": "Updated Title", "tags": ["new-tag"]},
            context=request_context,
        )

        assert history.version == 2
        assert history.content_snapshot is None
        assert history.content_diff is None
        assert history.metadata_snapshot == {"title": "Updated Title", "tags": ["new-tag"]}

    async def test__record_action__delete_stores_audit_record(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """DELETE action stores AUDIT record with NULL version and no content."""
        entity_id = uuid4()
        content = "Hello World"
        metadata = {"title": "Test"}

        # Create v1
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content=content,
            previous_content=None,
            metadata={"title": "Test", "tags": []},
            context=request_context,
        )

        # Delete (audit event, no version)
        history = await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.DELETE,
            current_content=content,
            previous_content=content,
            metadata=metadata,
            context=request_context,
        )

        assert history.version is None
        assert history.content_snapshot is None
        assert history.content_diff is None
        assert history.action == ActionType.DELETE.value
        assert history.metadata_snapshot == metadata

    async def test__record_action__periodic_snapshot_stores_both(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """Periodic snapshot (every 10th version) stores both snapshot and diff."""
        entity_id = uuid4()
        metadata = {"title": "Test", "tags": []}

        # Create versions 1-9
        previous = None
        for i in range(1, SNAPSHOT_INTERVAL):
            content = f"Content v{i}"
            await history_service.record_action(
                db=db_session,
                user_id=test_user.id,
                entity_type=EntityType.NOTE,
                entity_id=entity_id,
                action=ActionType.CREATE if i == 1 else ActionType.UPDATE,
                current_content=content,
                previous_content=previous,
                metadata=metadata,
                context=request_context,
            )
            previous = content

        # Create version 10 (periodic snapshot)
        content_v10 = "Content v10"
        history = await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.UPDATE,
            current_content=content_v10,
            previous_content=previous,
            metadata=metadata,
            context=request_context,
        )

        assert history.version == SNAPSHOT_INTERVAL
        assert history.content_snapshot == content_v10  # Full content
        assert history.content_diff is not None  # Also has diff for chain traversal

    async def test__record_action__metadata_only_at_snapshot_interval(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """Metadata-only change at modulo-10 version stores content_snapshot for bounded reconstruction."""
        entity_id = uuid4()
        content = "Stable content"

        # Create versions 1-9
        previous = None
        for i in range(1, SNAPSHOT_INTERVAL):
            c = f"Content v{i}" if i < SNAPSHOT_INTERVAL - 1 else content
            await history_service.record_action(
                db=db_session,
                user_id=test_user.id,
                entity_type=EntityType.NOTE,
                entity_id=entity_id,
                action=ActionType.CREATE if i == 1 else ActionType.UPDATE,
                current_content=c,
                previous_content=previous,
                metadata={"title": "Test", "tags": []},
                context=request_context,
            )
            previous = c

        # Create version 10 as metadata-only (same content, different title)
        history = await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.UPDATE,
            current_content=content,
            previous_content=content,  # Same content — metadata-only
            metadata={"title": "Updated Title", "tags": []},
            context=request_context,
        )

        assert history.version == SNAPSHOT_INTERVAL
        assert history.content_snapshot == content  # Snapshot for bounded reconstruction
        assert history.content_diff is None  # No content change

    async def test__record_action__stores_request_context(
        self,
        db_session: AsyncSession,
        test_user: User,
        pat_context: RequestContext,
    ) -> None:
        """History records store source, auth_type, and token_prefix from context."""
        entity_id = uuid4()

        history = await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.BOOKMARK,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content="http://example.com",
            previous_content=None,
            metadata={"title": "Test", "url": "http://example.com"},
            context=pat_context,
        )

        assert history.source == "mcp-content"
        assert history.auth_type == AuthType.PAT.value
        assert history.token_prefix == "bm_test1234567"

    async def test__record_action__archive_stores_audit_record(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """ARCHIVE action stores AUDIT record with NULL version."""
        entity_id = uuid4()
        content = "Content"
        metadata = {"title": "Test"}

        # Create v1
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content=content,
            previous_content=None,
            metadata={"title": "Test"},
            context=request_context,
        )

        # Archive (audit event, no version)
        history = await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.ARCHIVE,
            current_content=content,
            previous_content=content,
            metadata=metadata,
            context=request_context,
        )

        assert history.version is None
        assert history.action == ActionType.ARCHIVE.value
        assert history.content_snapshot is None
        assert history.content_diff is None
        assert history.metadata_snapshot == metadata


class TestHistoryServiceDiffComputation:
    """Tests for diff computation and application."""

    async def test__diff__simple_text_change_produces_valid_diff(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """Simple text change produces a valid diff that can be applied."""
        entity_id = uuid4()
        metadata = {"title": "Test"}
        original = "Hello"
        modified = "Hello World"

        # Create v1
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content=original,
            previous_content=None,
            metadata=metadata,
            context=request_context,
        )

        # Update v2
        history = await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.UPDATE,
            current_content=modified,
            previous_content=original,
            metadata=metadata,
            context=request_context,
        )

        # Apply the reverse diff manually to verify correctness
        # The diff transforms current → previous (reverse direction)
        dmp = history_service.dmp
        patches = dmp.patch_fromText(history.content_diff)
        result, _ = dmp.patch_apply(patches, modified)
        assert result == original

    async def test__diff__large_content_changes_work(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """Large content changes are handled correctly."""
        entity_id = uuid4()
        metadata = {"title": "Test"}
        original = "A" * 10000
        modified = "B" * 10000

        # Create v1
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content=original,
            previous_content=None,
            metadata=metadata,
            context=request_context,
        )

        # Update v2
        history = await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.UPDATE,
            current_content=modified,
            previous_content=original,
            metadata=metadata,
            context=request_context,
        )

        assert history.content_diff is not None

        # Verify reverse diff works
        dmp = history_service.dmp
        patches = dmp.patch_fromText(history.content_diff)
        result, _ = dmp.patch_apply(patches, modified)
        assert result == original

    async def test__diff__empty_content_handled_correctly(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """Empty content is handled correctly."""
        entity_id = uuid4()
        metadata = {"title": "Test"}

        # Create v1 with empty content
        history = await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content="",
            previous_content=None,
            metadata=metadata,
            context=request_context,
        )

        assert history.content_snapshot == ""
        assert history.content_diff is None

    async def test__diff__null_to_value_creates_diff_not_snapshot(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """Update from None content to value creates DIFF, not SNAPSHOT."""
        entity_id = uuid4()
        metadata = {"title": "Test"}

        # Create v1 with None content (like an empty note)
        v1 = await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content=None,
            previous_content=None,
            metadata=metadata,
            context=request_context,
        )

        assert v1.version == 1
        assert v1.content_snapshot is None  # No content stored
        assert v1.content_diff is None

        # Update v2: None -> "1" (this was incorrectly creating SNAPSHOT before fix)
        v2 = await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.UPDATE,
            current_content="1",
            previous_content=None,  # Previous content was None
            metadata=metadata,
            context=request_context,
        )

        # Should be DIFF, not SNAPSHOT
        assert v2.version == 2
        assert v2.content_snapshot is None  # Not a snapshot
        assert v2.content_diff is not None  # Has the reverse diff

        # Verify the diff is valid: applying it to "1" should give ""
        dmp = diff_match_patch()
        patches = dmp.patch_fromText(v2.content_diff)
        result, _ = dmp.patch_apply(patches, "1")
        assert result == ""  # Reverse diff from "1" to None/""

    async def test__diff__unicode_content_handled_correctly(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """Unicode and emoji content is handled correctly."""
        entity_id = uuid4()
        metadata = {"title": "Test"}
        original = "Hello 世界 🌍"
        modified = "Hello 世界 🌍 Updated 更新"

        # Create v1
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content=original,
            previous_content=None,
            metadata=metadata,
            context=request_context,
        )

        # Update v2
        history = await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.UPDATE,
            current_content=modified,
            previous_content=original,
            metadata=metadata,
            context=request_context,
        )

        # Verify reverse diff works with unicode
        dmp = history_service.dmp
        patches = dmp.patch_fromText(history.content_diff)
        result, _ = dmp.patch_apply(patches, modified)
        assert result == original


class TestHistoryServiceReconstruction:
    """Tests for content reconstruction at specific versions."""

    async def test__reconstruct__latest_version_returns_directly(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_note: Note,
        request_context: RequestContext,
    ) -> None:
        """Reconstructing latest version returns content directly (no diff application)."""
        # Create history for the note
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=test_note.id,
            action=ActionType.CREATE,
            current_content=test_note.content,
            previous_content=None,
            metadata={"title": test_note.title},
            context=request_context,
        )

        result = await history_service.reconstruct_content_at_version(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=test_note.id,
            target_version=1,
        )

        assert result.found is True
        assert result.content == test_note.content
        assert result.warnings is None

    async def test__reconstruct__non_existent_version_returns_not_found(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_note: Note,
        request_context: RequestContext,
    ) -> None:
        """Reconstructing non-existent version returns found=False."""
        # Create history for the note
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=test_note.id,
            action=ActionType.CREATE,
            current_content=test_note.content,
            previous_content=None,
            metadata={"title": test_note.title},
            context=request_context,
        )

        result = await history_service.reconstruct_content_at_version(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=test_note.id,
            target_version=999,
        )

        assert result.found is False
        assert result.content is None

    async def test__reconstruct__invalid_version_returns_not_found(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_note: Note,
        request_context: RequestContext,
    ) -> None:
        """Reconstructing version 0 or negative returns found=False."""
        # Create history for the note
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=test_note.id,
            action=ActionType.CREATE,
            current_content=test_note.content,
            previous_content=None,
            metadata={"title": test_note.title},
            context=request_context,
        )

        result = await history_service.reconstruct_content_at_version(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=test_note.id,
            target_version=0,
        )

        assert result.found is False

    async def test__reconstruct__hard_deleted_entity_returns_not_found(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Reconstructing content for hard-deleted entity returns found=False."""
        entity_id = uuid4()  # Non-existent entity

        result = await history_service.reconstruct_content_at_version(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            target_version=1,
        )

        assert result.found is False
        assert result.content is None

    async def test__reconstruct__applies_reverse_diffs_correctly(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_note: Note,
        request_context: RequestContext,
    ) -> None:
        """Reconstruction applies reverse diffs to get earlier versions."""
        metadata = {"title": test_note.title}

        # Create v1
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=test_note.id,
            action=ActionType.CREATE,
            current_content="Content v1",
            previous_content=None,
            metadata=metadata,
            context=request_context,
        )

        # Create v2, v3, v4, v5
        previous = "Content v1"
        for i in range(2, 6):
            current = f"Content v{i}"
            await history_service.record_action(
                db=db_session,
                user_id=test_user.id,
                entity_type=EntityType.NOTE,
                entity_id=test_note.id,
                action=ActionType.UPDATE,
                current_content=current,
                previous_content=previous,
                metadata=metadata,
                context=request_context,
            )
            previous = current

        # Update entity content to match v5
        test_note.content = "Content v5"
        await db_session.flush()

        # Reconstruct v1
        result = await history_service.reconstruct_content_at_version(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=test_note.id,
            target_version=1,
        )

        assert result.found is True
        assert result.content == "Content v1"

        # Reconstruct v3
        result = await history_service.reconstruct_content_at_version(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=test_note.id,
            target_version=3,
        )

        assert result.found is True
        assert result.content == "Content v3"

    async def test__reconstruct__through_metadata_snapshot(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """Reconstruction uses content_snapshot from a metadata-only record at modulo-10 as anchor."""
        entity_id = uuid4()
        metadata = {"title": "Test", "tags": []}

        # Create v1 with content
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content="Content v1",
            previous_content=None,
            metadata=metadata,
            context=request_context,
        )

        # Create v2-9 with content changes
        previous = "Content v1"
        for i in range(2, SNAPSHOT_INTERVAL):
            c = f"Content v{i}"
            await history_service.record_action(
                db=db_session,
                user_id=test_user.id,
                entity_type=EntityType.NOTE,
                entity_id=entity_id,
                action=ActionType.UPDATE,
                current_content=c,
                previous_content=previous,
                metadata=metadata,
                context=request_context,
            )
            previous = c

        # v10: metadata-only change (content stays same as v9)
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.UPDATE,
            current_content=previous,
            previous_content=previous,  # Same content
            metadata={"title": "New Title", "tags": []},
            context=request_context,
        )

        # v11: content change
        new_content = "Content v11"
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.UPDATE,
            current_content=new_content,
            previous_content=previous,
            metadata={"title": "New Title", "tags": []},
            context=request_context,
        )

        # Create a note entity to serve as anchor
        note = Note(user_id=test_user.id, title="Test", content=new_content)
        note.id = entity_id
        db_session.add(note)
        await db_session.flush()

        # Reconstruct v9 — should use the metadata-only v10 snapshot as anchor
        result = await history_service.reconstruct_content_at_version(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            target_version=9,
        )

        assert result.found is True
        assert result.content == f"Content v{SNAPSHOT_INTERVAL - 1}"


class TestReconstructionChainIntegrity:
    """[P0] End-to-end reconstruction chain integrity tests."""

    async def test__reconstruction_chain__all_versions_reconstruct_correctly(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_note: Note,
        request_context: RequestContext,
    ) -> None:
        """
        Create a realistic chain with audit events and verify reconstruction.

        Post-refactor chain (audit events have NULL version):
        v1:  CREATE (SNAPSHOT)          content = "A"
        v2:  UPDATE (DIFF)              content = "AB"
        ...
        v10: UPDATE (SNAPSHOT + DIFF)   content = "ABCDEFGHIJ"
        ...
        v14: UPDATE (DIFF)              content = "ABCDEFGHIJKLMN"
             ARCHIVE (AUDIT, v=NULL)    content unchanged
             UNARCHIVE (AUDIT, v=NULL)  content unchanged
        v15: UPDATE (DIFF)              content = "ABCDEFGHIJKLMNO"
        ...
        v18: UPDATE (DIFF)              content = "ABCDEFGHIJKLMNOPQR"

        Key: audit events don't consume version numbers, so
        what was v17-v20 pre-refactor is now v15-v18.
        """
        metadata = {"title": test_note.title}
        # Map version -> expected content for versioned records
        expected_content: dict[int, str] = {}

        previous = None
        content_version = 0  # track content version separately
        for i in range(1, 21):
            if i == 15:
                # ARCHIVE - audit event, no version
                action = ActionType.ARCHIVE
                current = previous  # content unchanged
            elif i == 16:
                # UNARCHIVE - audit event, no version
                action = ActionType.UNARCHIVE
                current = previous  # content unchanged
            elif i == 1:
                action = ActionType.CREATE
                content_version += 1
                current = "A"
                expected_content[content_version] = current
            else:
                action = ActionType.UPDATE
                content_version += 1
                current = "".join(chr(ord("A") + j) for j in range(content_version))
                expected_content[content_version] = current

            await history_service.record_action(
                db=db_session,
                user_id=test_user.id,
                entity_type=EntityType.NOTE,
                entity_id=test_note.id,
                action=action,
                current_content=current,
                previous_content=previous,
                metadata=metadata,
                context=request_context,
            )
            previous = current

        # content_version should be 18 (20 iterations - 2 audit events)
        assert content_version == 18

        # Update entity content to match latest version
        test_note.content = expected_content[18]
        await db_session.flush()

        # Verify key versions reconstruct correctly
        # v10 is periodic snapshot, v14 is just before audit gap, v15 is just after
        test_versions = [1, 5, 10, 14, 15, 18]
        for version in test_versions:
            result = await history_service.reconstruct_content_at_version(
                db=db_session,
                user_id=test_user.id,
                entity_type=EntityType.NOTE,
                entity_id=test_note.id,
                target_version=version,
            )
            assert result.found is True, f"Version {version} should be found"
            assert result.content == expected_content[version], (
                f"Version {version} content mismatch: "
                f"expected '{expected_content[version]}', got '{result.content}'"
            )


class TestPeriodicSnapshotDualStorage:
    """[P0] Tests for periodic snapshot dual-storage traversal."""

    async def test__periodic_snapshot__stores_both_snapshot_and_diff(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_note: Note,
        request_context: RequestContext,
    ) -> None:
        """Periodic snapshots (v10, v20, etc.) store BOTH content_snapshot AND content_diff."""
        metadata = {"title": test_note.title}

        # Create versions 1-10
        previous = None
        for i in range(1, 11):
            current = f"Content {i}"
            await history_service.record_action(
                db=db_session,
                user_id=test_user.id,
                entity_type=EntityType.NOTE,
                entity_id=test_note.id,
                action=ActionType.CREATE if i == 1 else ActionType.UPDATE,
                current_content=current,
                previous_content=previous,
                metadata=metadata,
                context=request_context,
            )
            previous = current

        # Get v10 record
        v10 = await history_service.get_history_at_version(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=test_note.id,
            version=10,
        )

        assert v10 is not None
        assert v10.content_snapshot == "Content 10"  # Full content for optimization
        assert v10.content_diff is not None  # Diff for chain traversal


class TestDeleteVersionReconstruction:
    """[P0] DELETE produces audit record; surrounding versions still work."""

    async def test__reconstruct__version_before_delete_still_works(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_note: Note,
        request_context: RequestContext,
    ) -> None:
        """
        DELETE creates an audit record (NULL version, no content).
        The content version before DELETE must still reconstruct correctly.
        """
        original_content = "Hello World"
        metadata = {"title": test_note.title}

        # Create v1
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=test_note.id,
            action=ActionType.CREATE,
            current_content=original_content,
            previous_content=None,
            metadata=metadata,
            context=request_context,
        )

        # DELETE (audit event, NULL version)
        delete_record = await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=test_note.id,
            action=ActionType.DELETE,
            current_content=original_content,
            previous_content=original_content,
            metadata=metadata,
            context=request_context,
        )

        assert delete_record.version is None
        assert delete_record.content_snapshot is None

        # v1 (the content version before DELETE) still reconstructs
        result = await history_service.reconstruct_content_at_version(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=test_note.id,
            target_version=1,
        )

        assert result.found is True
        assert result.content == original_content


class TestNearestSnapshotSelection:
    """[P1] Tests for nearest snapshot selection optimization."""

    async def test__reconstruct__uses_nearest_snapshot(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_note: Note,
        request_context: RequestContext,
    ) -> None:
        """
        Verify reconstruction picks the closest snapshot to target.

        v1-v50 exist, with SNAPSHOTs at v10, v20, v30, v40
        Target: v25

        Should start from v30's content_snapshot (nearest to v25)
        NOT v40's content_snapshot (first encountered in DESC order)
        """
        metadata = {"title": test_note.title}

        # Create versions 1-50
        previous = None
        expected_content: dict[int, str] = {}
        for i in range(1, 51):
            current = f"Content version {i}"
            expected_content[i] = current
            await history_service.record_action(
                db=db_session,
                user_id=test_user.id,
                entity_type=EntityType.NOTE,
                entity_id=test_note.id,
                action=ActionType.CREATE if i == 1 else ActionType.UPDATE,
                current_content=current,
                previous_content=previous,
                metadata=metadata,
                context=request_context,
            )
            previous = current

        # Update entity content to match v50
        test_note.content = expected_content[50]
        await db_session.flush()

        # Reconstruct v25
        result = await history_service.reconstruct_content_at_version(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=test_note.id,
            target_version=25,
        )

        assert result.found is True
        assert result.content == expected_content[25]


class TestAuditRecordTraversal:
    """[P1] Tests for audit record behavior in reconstruction."""

    async def test__reconstruct__audit_records_dont_affect_version_chain(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_note: Note,
        request_context: RequestContext,
    ) -> None:
        """
        Audit records (NULL version) are excluded from reconstruction.

        v5: UPDATE content = "Hello"
             ARCHIVE (AUDIT, v=NULL)
        v6: UPDATE (DIFF) content = "Hello World"

        Reconstruct v5: traverses v6 diff, audit record is invisible.
        Result: "Hello"
        """
        metadata = {"title": test_note.title}

        # Create v1-v5 with actual content
        previous = None
        for i in range(1, 6):
            current = f"Content v{i}" if i < 5 else "Hello"
            await history_service.record_action(
                db=db_session,
                user_id=test_user.id,
                entity_type=EntityType.NOTE,
                entity_id=test_note.id,
                action=ActionType.CREATE if i == 1 else ActionType.UPDATE,
                current_content=current,
                previous_content=previous,
                metadata=metadata,
                context=request_context,
            )
            previous = current

        # ARCHIVE (audit event, NULL version - doesn't consume v6)
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=test_note.id,
            action=ActionType.ARCHIVE,
            current_content="Hello",
            previous_content="Hello",
            metadata=metadata,
            context=request_context,
        )

        # v6: UPDATE with content change (not v7 - ARCHIVE didn't consume a version)
        history = await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=test_note.id,
            action=ActionType.UPDATE,
            current_content="Hello World",
            previous_content="Hello",
            metadata=metadata,
            context=request_context,
        )
        assert history.version == 6  # Confirms audit didn't consume v6

        # Update entity content to match v6
        test_note.content = "Hello World"
        await db_session.flush()

        # Reconstruct v5
        result = await history_service.reconstruct_content_at_version(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=test_note.id,
            target_version=5,
        )

        assert result.found is True
        assert result.content == "Hello"


class TestReconstructionAtSnapshot:
    """[P1] Tests for reconstruction starting AT a snapshot."""

    async def test__reconstruct__at_periodic_snapshot_returns_directly(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_note: Note,
        request_context: RequestContext,
    ) -> None:
        """When target version IS a periodic snapshot, return content_snapshot directly."""
        metadata = {"title": test_note.title}

        # Create versions 1-15
        previous = None
        for i in range(1, 16):
            current = f"Content {i}"
            await history_service.record_action(
                db=db_session,
                user_id=test_user.id,
                entity_type=EntityType.NOTE,
                entity_id=test_note.id,
                action=ActionType.CREATE if i == 1 else ActionType.UPDATE,
                current_content=current,
                previous_content=previous,
                metadata=metadata,
                context=request_context,
            )
            previous = current

        # Update entity content to match v15
        test_note.content = "Content 15"
        await db_session.flush()

        # Reconstruct v10 (periodic snapshot)
        result = await history_service.reconstruct_content_at_version(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=test_note.id,
            target_version=10,
        )

        assert result.found is True
        assert result.content == "Content 10"


class TestEmptyDiffHandling:
    """[P2] Tests for empty diff vs None diff handling."""

    async def test__reconstruct__empty_string_diff_behaves_like_none(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_note: Note,
        request_context: RequestContext,
    ) -> None:
        """Empty string content_diff should behave same as None (no transformation)."""
        metadata = {"title": test_note.title}

        # Create v1
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=test_note.id,
            action=ActionType.CREATE,
            current_content="Hello",
            previous_content=None,
            metadata=metadata,
            context=request_context,
        )

        # Manually insert a history record with empty string diff to test edge case
        # (This shouldn't happen in practice, but tests defensive handling)
        history = ContentHistory(
            user_id=test_user.id,
            entity_type=EntityType.NOTE.value,
            entity_id=test_note.id,
            action=ActionType.UPDATE.value,
            version=2,
            content_snapshot=None,
            content_diff="",  # Empty string
            metadata_snapshot=metadata,
            source="web",
            auth_type=AuthType.SESSION.value,
        )
        db_session.add(history)
        await db_session.flush()

        # Update entity content
        test_note.content = "Hello"
        await db_session.flush()

        # Reconstruct v1 - should still work (empty diff = no transformation)
        result = await history_service.reconstruct_content_at_version(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=test_note.id,
            target_version=1,
        )

        assert result.found is True
        assert result.content == "Hello"


class TestCorruptedDiffHandling:
    """Tests for corrupted diff handling (graceful degradation)."""

    async def test__reconstruct__corrupted_diff_returns_warning_not_exception(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_note: Note,
        request_context: RequestContext,
    ) -> None:
        """
        Corrupted diff text should return warning, not raise exception.

        Per spec: "Partial failures are logged but don't fail the request."
        This ensures reconstruction continues even with corrupted data.

        Setup:
        - v1: SNAPSHOT content="A"
        - v2: DIFF content="AB" (valid)
        - v3: DIFF (corrupted)
        - entity.content = "ABC"
        - Target: v2 (requires traversing v3's corrupted diff)
        """
        metadata = {"title": test_note.title}

        # Create v1 (snapshot) content="A"
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=test_note.id,
            action=ActionType.CREATE,
            current_content="A",
            previous_content=None,
            metadata=metadata,
            context=request_context,
        )

        # Create v2 (diff) content="AB"
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=test_note.id,
            action=ActionType.UPDATE,
            current_content="AB",
            previous_content="A",
            metadata=metadata,
            context=request_context,
        )

        # Manually insert v3 with corrupted diff text
        history = ContentHistory(
            user_id=test_user.id,
            entity_type=EntityType.NOTE.value,
            entity_id=test_note.id,
            action=ActionType.UPDATE.value,
            version=3,
            content_snapshot=None,
            content_diff="this_is_not_valid_patch_text!!!",  # Corrupted
            metadata_snapshot=metadata,
            source="web",
            auth_type=AuthType.SESSION.value,
        )
        db_session.add(history)
        await db_session.flush()

        # Update entity content to simulate current state
        test_note.content = "ABC"
        await db_session.flush()

        # Reconstruct v2 - must traverse v3's corrupted diff
        # Should NOT raise, should return with warning
        result = await history_service.reconstruct_content_at_version(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=test_note.id,
            target_version=2,
        )

        assert result.found is True
        # Content will be entity.content since corrupted diff couldn't transform it
        assert result.content is not None
        # Should have a warning about the corrupted diff
        assert result.warnings is not None
        assert len(result.warnings) == 1
        assert "Corrupted diff at v3" in result.warnings[0]

    async def test__reconstruct__continues_after_corrupted_diff(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_note: Note,
        request_context: RequestContext,
    ) -> None:
        """
        Reconstruction continues processing after encountering corrupted diff.

        Setup:
        - v1: SNAPSHOT content="A"
        - v2: DIFF content="AB" (valid)
        - v3: DIFF (corrupted)
        - v4: DIFF content="ABCD" (valid)
        - entity.content = "ABCD"
        - Target: v2 (requires traversing v4, v3)

        v4's valid diff is applied, v3's corrupted diff is skipped with warning,
        then we reach target v2.
        """
        metadata = {"title": test_note.title}

        # Create v1 (snapshot) content="A"
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=test_note.id,
            action=ActionType.CREATE,
            current_content="A",
            previous_content=None,
            metadata=metadata,
            context=request_context,
        )

        # Create v2 (diff) content="AB"
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=test_note.id,
            action=ActionType.UPDATE,
            current_content="AB",
            previous_content="A",
            metadata=metadata,
            context=request_context,
        )

        # Manually insert v3 with corrupted diff
        history_v3 = ContentHistory(
            user_id=test_user.id,
            entity_type=EntityType.NOTE.value,
            entity_id=test_note.id,
            action=ActionType.UPDATE.value,
            version=3,
            content_snapshot=None,
            content_diff="CORRUPTED_GARBAGE_DATA",
            metadata_snapshot=metadata,
            source="web",
            auth_type=AuthType.SESSION.value,
        )
        db_session.add(history_v3)
        await db_session.flush()

        # Create v4 (diff) content="ABCD" - using the history service
        # We need to compute the diff from "ABC" (what v3 would have been) to "AB"
        # But since v3 is corrupted, let's manually create v4 with a valid diff
        dmp = history_service.dmp
        # Reverse diff: ABCD -> ABC (but we don't know what ABC was due to corruption)
        # Let's just create a valid diff that would work
        patches = dmp.patch_make("ABCD", "ABC")
        valid_diff = dmp.patch_toText(patches)

        history_v4 = ContentHistory(
            user_id=test_user.id,
            entity_type=EntityType.NOTE.value,
            entity_id=test_note.id,
            action=ActionType.UPDATE.value,
            version=4,
            content_snapshot=None,
            content_diff=valid_diff,
            metadata_snapshot=metadata,
            source="web",
            auth_type=AuthType.SESSION.value,
        )
        db_session.add(history_v4)
        await db_session.flush()

        # Update entity content to v4's content
        test_note.content = "ABCD"
        await db_session.flush()

        # Reconstruct v2 - should process v4 (valid), v3 (corrupted, skipped)
        result = await history_service.reconstruct_content_at_version(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=test_note.id,
            target_version=2,
        )

        assert result.found is True
        # Should have warning about v3
        assert result.warnings is not None
        assert any("v3" in w for w in result.warnings)
        # v4's diff was applied (ABCD -> ABC), but v3's was skipped
        # So content should be "ABC" (not "AB" as it would be without corruption)
        # v2's diff was still applied


class TestHistoryRetrieval:
    """Tests for history retrieval methods."""

    async def test__get_entity_history__returns_records_and_count(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """get_entity_history returns correct records and total count."""
        entity_id = uuid4()
        metadata = {"title": "Test"}

        # Create 5 history records
        previous = None
        for i in range(1, 6):
            current = f"Content {i}"
            await history_service.record_action(
                db=db_session,
                user_id=test_user.id,
                entity_type=EntityType.NOTE,
                entity_id=entity_id,
                action=ActionType.CREATE if i == 1 else ActionType.UPDATE,
                current_content=current,
                previous_content=previous,
                metadata=metadata,
                context=request_context,
            )
            previous = current

        items, total = await history_service.get_entity_history(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
        )

        assert total == 5
        assert len(items) == 5
        # Should be ordered by created_at DESC (newest first)
        versions = [item.version for item in items]
        assert versions == [5, 4, 3, 2, 1]

    async def test__get_entity_history__pagination_works(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """get_entity_history pagination works correctly."""
        entity_id = uuid4()
        metadata = {"title": "Test"}

        # Create 10 history records
        previous = None
        for i in range(1, 11):
            current = f"Content {i}"
            await history_service.record_action(
                db=db_session,
                user_id=test_user.id,
                entity_type=EntityType.NOTE,
                entity_id=entity_id,
                action=ActionType.CREATE if i == 1 else ActionType.UPDATE,
                current_content=current,
                previous_content=previous,
                metadata=metadata,
                context=request_context,
            )
            previous = current

        # Get first page
        items, total = await history_service.get_entity_history(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            limit=3,
            offset=0,
        )

        assert total == 10
        assert len(items) == 3
        # Ordered by created_at DESC (newest first)
        versions = [item.version for item in items]
        assert versions == [10, 9, 8]

        # Get second page
        items, total = await history_service.get_entity_history(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            limit=3,
            offset=3,
        )

        assert total == 10
        assert len(items) == 3
        assert items[0].version == 7

    async def test__get_user_history__returns_all_entity_types(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """get_user_history returns history across all entity types."""
        metadata = {"title": "Test"}

        # Create history for different entity types
        for entity_type in [EntityType.NOTE, EntityType.BOOKMARK, EntityType.PROMPT]:
            await history_service.record_action(
                db=db_session,
                user_id=test_user.id,
                entity_type=entity_type,
                entity_id=uuid4(),
                action=ActionType.CREATE,
                current_content="Content",
                previous_content=None,
                metadata=metadata,
                context=request_context,
            )

        items, total = await history_service.get_user_history(
            db=db_session,
            user_id=test_user.id,
        )

        assert total == 3
        assert len(items) == 3
        entity_types = {item.entity_type for item in items}
        assert entity_types == {"note", "bookmark", "prompt"}

    async def test__get_user_history__filters_by_entity_type(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """get_user_history filters by entity_type when provided."""
        metadata = {"title": "Test"}

        # Create history for different entity types
        for entity_type in [EntityType.NOTE, EntityType.NOTE, EntityType.BOOKMARK]:
            await history_service.record_action(
                db=db_session,
                user_id=test_user.id,
                entity_type=entity_type,
                entity_id=uuid4(),
                action=ActionType.CREATE,
                current_content="Content",
                previous_content=None,
                metadata=metadata,
                context=request_context,
            )

        items, total = await history_service.get_user_history(
            db=db_session,
            user_id=test_user.id,
            entity_types=[EntityType.NOTE],
        )

        assert total == 2
        assert len(items) == 2
        assert all(item.entity_type == "note" for item in items)

    async def test__get_history_at_version__returns_correct_record(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """get_history_at_version returns the correct record."""
        entity_id = uuid4()
        metadata = {"title": "Test"}

        # Create multiple versions
        previous = None
        for i in range(1, 4):
            current = f"Content v{i}"
            await history_service.record_action(
                db=db_session,
                user_id=test_user.id,
                entity_type=EntityType.NOTE,
                entity_id=entity_id,
                action=ActionType.CREATE if i == 1 else ActionType.UPDATE,
                current_content=current,
                previous_content=previous,
                metadata=metadata,
                context=request_context,
            )
            previous = current

        # Get v2
        record = await history_service.get_history_at_version(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            version=2,
        )

        assert record is not None
        assert record.version == 2
        assert record.action == ActionType.UPDATE.value


class TestDeleteEntityHistory:
    """Tests for delete_entity_history method."""

    async def test__delete_entity_history__removes_all_records(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """delete_entity_history removes all history for an entity."""
        entity_id = uuid4()
        metadata = {"title": "Test"}

        # Create history
        previous = None
        for i in range(1, 4):
            current = f"Content v{i}"
            await history_service.record_action(
                db=db_session,
                user_id=test_user.id,
                entity_type=EntityType.NOTE,
                entity_id=entity_id,
                action=ActionType.CREATE if i == 1 else ActionType.UPDATE,
                current_content=current,
                previous_content=previous,
                metadata=metadata,
                context=request_context,
            )
            previous = current

        # Verify history exists
        _items, total = await history_service.get_entity_history(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
        )
        assert total == 3

        # Delete history
        deleted_count = await history_service.delete_entity_history(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
        )

        assert deleted_count == 3

        # Verify history is gone
        _items, total = await history_service.get_entity_history(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
        )
        assert total == 0


class TestVersionNumbering:
    """Tests for version number allocation."""

    async def test__version_numbers__increment_correctly(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """Version numbers increment sequentially."""
        entity_id = uuid4()
        metadata = {"title": "Test"}

        versions = []
        previous = None
        for i in range(1, 6):
            current = f"Content v{i}"
            history = await history_service.record_action(
                db=db_session,
                user_id=test_user.id,
                entity_type=EntityType.NOTE,
                entity_id=entity_id,
                action=ActionType.CREATE if i == 1 else ActionType.UPDATE,
                current_content=current,
                previous_content=previous,
                metadata=metadata,
                context=request_context,
            )
            versions.append(history.version)
            previous = current

        assert versions == [1, 2, 3, 4, 5]

    async def test__version_numbers__independent_per_entity(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """Version numbers are independent per entity."""
        entity_id_1 = uuid4()
        entity_id_2 = uuid4()
        metadata = {"title": "Test"}

        # Create v1-v3 for entity 1
        previous = None
        for i in range(1, 4):
            current = f"Content v{i}"
            await history_service.record_action(
                db=db_session,
                user_id=test_user.id,
                entity_type=EntityType.NOTE,
                entity_id=entity_id_1,
                action=ActionType.CREATE if i == 1 else ActionType.UPDATE,
                current_content=current,
                previous_content=previous,
                metadata=metadata,
                context=request_context,
            )
            previous = current

        # Create v1 for entity 2 - should start at 1, not 4
        history = await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id_2,
            action=ActionType.CREATE,
            current_content="Content",
            previous_content=None,
            metadata=metadata,
            context=request_context,
        )

        assert history.version == 1


class TestRaceConditionHandling:
    """Tests for race condition handling in version allocation."""

    async def test__record_action__retries_on_version_uniqueness_violation(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """Version uniqueness violation triggers retry with savepoint."""
        entity_id = uuid4()
        metadata = {"title": "Test"}

        # Mock _record_action_impl to fail on first call, succeed on second
        original_impl = history_service._record_action_impl
        call_count = 0

        async def mock_impl(*args, **kwargs):  # noqa
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Simulate version conflict on first attempt
                raise IntegrityError(
                    "duplicate key",
                    params={},
                    orig=Exception("uq_content_history_version"),
                )
            return await original_impl(*args, **kwargs)

        with patch.object(history_service, "_record_action_impl", side_effect=mock_impl):
            history = await history_service.record_action(
                db=db_session,
                user_id=test_user.id,
                entity_type=EntityType.NOTE,
                entity_id=entity_id,
                action=ActionType.CREATE,
                current_content="Content",
                previous_content=None,
                metadata=metadata,
                context=request_context,
            )

        # Should succeed on retry
        assert history.version == 1
        assert call_count == 2  # First failed, second succeeded

    async def test__record_action__raises_other_integrity_errors_immediately(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """Non-version IntegrityErrors are raised immediately without retry."""
        entity_id = uuid4()
        metadata = {"title": "Test"}
        call_count = 0

        async def mock_impl(*args, **kwargs):  # noqa
            nonlocal call_count
            call_count += 1
            # Simulate a different integrity error (not version-related)
            raise IntegrityError(
                "foreign key violation",
                params={},
                orig=Exception("fk_user_id"),
            )

        with patch.object(history_service, "_record_action_impl", side_effect=mock_impl):
            with pytest.raises(IntegrityError) as exc_info:
                await history_service.record_action(
                    db=db_session,
                    user_id=test_user.id,
                    entity_type=EntityType.NOTE,
                    entity_id=entity_id,
                    action=ActionType.CREATE,
                    current_content="Content",
                    previous_content=None,
                    metadata=metadata,
                    context=request_context,
                )

        # Should raise immediately without retry
        assert call_count == 1
        assert "fk_user_id" in str(exc_info.value)

    async def test__record_action__raises_after_max_retries_exceeded(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """Max retries exceeded raises the IntegrityError."""
        entity_id = uuid4()
        metadata = {"title": "Test"}
        call_count = 0

        async def mock_impl(*args, **kwargs):  # noqa
            nonlocal call_count
            call_count += 1
            # Always fail with version conflict
            raise IntegrityError(
                "duplicate key",
                params={},
                orig=Exception("uq_content_history_version"),
            )

        with patch.object(history_service, "_record_action_impl", side_effect=mock_impl):
            with pytest.raises(IntegrityError) as exc_info:
                await history_service.record_action(
                    db=db_session,
                    user_id=test_user.id,
                    entity_type=EntityType.NOTE,
                    entity_id=entity_id,
                    action=ActionType.CREATE,
                    current_content="Content",
                    previous_content=None,
                    metadata=metadata,
                    context=request_context,
                )

        # Should try 3 times then raise
        assert call_count == 3
        assert "uq_content_history_version" in str(exc_info.value)


class TestBoundaryConditions:
    """Tests for boundary conditions in content and metadata."""

    async def test__diff__100kb_content_handled_correctly(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """Content at exactly 100KB limit is handled correctly."""
        entity_id = uuid4()
        metadata = {"title": "Large Content Test"}

        # Create 100KB of content (100 * 1024 = 102400 bytes)
        original_100kb = "A" * 102400
        modified_100kb = original_100kb[:50000] + "B" * 2400 + original_100kb[52400:]

        # Create v1 with 100KB content
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content=original_100kb,
            previous_content=None,
            metadata=metadata,
            context=request_context,
        )

        # Update v2 with modified 100KB content
        history = await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.UPDATE,
            current_content=modified_100kb,
            previous_content=original_100kb,
            metadata=metadata,
            context=request_context,
        )

        assert history.version == 2
        assert history.content_diff is not None

        # Verify reverse diff works correctly
        dmp = history_service.dmp
        patches = dmp.patch_fromText(history.content_diff)
        result, success = dmp.patch_apply(patches, modified_100kb)
        assert all(success)
        assert result == original_100kb

    async def test__metadata__long_tag_list_handled_correctly(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """Very long tag lists in metadata are stored and retrieved correctly."""
        entity_id = uuid4()

        # Create metadata with many tags (50 tags with varying lengths)
        tags = [f"tag-{i}-{'x' * (i % 20)}" for i in range(50)]
        metadata = {
            "title": "Many Tags Test",
            "description": "Testing long tag lists",
            "tags": tags,
        }

        history = await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.BOOKMARK,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content="http://example.com",
            previous_content=None,
            metadata=metadata,
            context=request_context,
        )

        # Verify metadata was stored correctly
        assert history.metadata_snapshot is not None
        assert history.metadata_snapshot["tags"] == tags
        assert len(history.metadata_snapshot["tags"]) == 50

        # Retrieve and verify
        retrieved = await history_service.get_history_at_version(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.BOOKMARK,
            entity_id=entity_id,
            version=1,
        )
        assert retrieved is not None
        assert retrieved.metadata_snapshot["tags"] == tags

    async def test__metadata__deeply_nested_structure_handled_correctly(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """Complex nested metadata structures are stored and retrieved correctly."""
        entity_id = uuid4()

        # Create metadata with nested structure (simulating prompt arguments)
        metadata = {
            "name": "complex-prompt",
            "title": "Complex Prompt",
            "arguments": [
                {
                    "name": "code_to_review",
                    "description": "The code to review",
                    "required": True,
                },
                {
                    "name": "language",
                    "description": "Programming language",
                    "required": False,
                },
                {
                    "name": "options",
                    "description": "Review options",
                    "required": False,
                },
            ],
            "tags": ["code", "review", "development"],
        }

        history = await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.PROMPT,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content="Review this {{ code_to_review }}",
            previous_content=None,
            metadata=metadata,
            context=request_context,
        )

        assert history.metadata_snapshot == metadata
        assert len(history.metadata_snapshot["arguments"]) == 3
        assert history.metadata_snapshot["arguments"][0]["name"] == "code_to_review"


class TestCountBasedPruning:
    """Tests for count-based history pruning."""

    async def test__prune_to_limit__deletes_oldest_records(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """_prune_to_limit deletes oldest records while keeping target count."""
        entity_id = uuid4()
        metadata = {"title": "Test"}

        # Create 20 history records
        previous = None
        for i in range(1, 21):
            current = f"Content v{i}"
            await history_service.record_action(
                db=db_session,
                user_id=test_user.id,
                entity_type=EntityType.NOTE,
                entity_id=entity_id,
                action=ActionType.CREATE if i == 1 else ActionType.UPDATE,
                current_content=current,
                previous_content=previous,
                metadata=metadata,
                context=request_context,
            )
            previous = current

        # Verify we have 20 records
        items, total = await history_service.get_entity_history(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
        )
        assert total == 20

        # Prune to keep only 10 records
        deleted = await history_service._prune_to_limit(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE.value,
            entity_id=entity_id,
            target=10,
        )
        await db_session.commit()

        # Should have deleted 10 oldest records
        assert deleted == 10

        # Verify remaining records
        items, total = await history_service.get_entity_history(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
        )
        assert total == 10

        # Remaining should be versions 11-20 (newest)
        versions = sorted([item.version for item in items])
        assert versions == list(range(11, 21))

    async def test__prune_to_limit__no_op_when_under_limit(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """_prune_to_limit does nothing when count is below target."""
        entity_id = uuid4()
        metadata = {"title": "Test"}

        # Create 5 history records
        previous = None
        for i in range(1, 6):
            current = f"Content v{i}"
            await history_service.record_action(
                db=db_session,
                user_id=test_user.id,
                entity_type=EntityType.NOTE,
                entity_id=entity_id,
                action=ActionType.CREATE if i == 1 else ActionType.UPDATE,
                current_content=current,
                previous_content=previous,
                metadata=metadata,
                context=request_context,
            )
            previous = current

        # Try to prune to 10 (more than we have)
        deleted = await history_service._prune_to_limit(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE.value,
            entity_id=entity_id,
            target=10,
        )

        # Should not delete anything
        assert deleted == 0

        # Verify all records still exist
        _items, total = await history_service.get_entity_history(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
        )
        assert total == 5

    async def test__record_action__triggers_pruning_at_interval(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """
        record_action triggers pruning check every PRUNE_CHECK_INTERVAL writes.

        When limits.max_history_per_entity is exceeded and version is divisible
        by PRUNE_CHECK_INTERVAL, pruning occurs.
        """
        entity_id = uuid4()
        metadata = {"title": "Test"}

        # Create limits with small max to trigger pruning
        limits = TierLimits(
            max_bookmarks=100,
            max_notes=100,
            max_prompts=100,
            max_pats=100,
            max_url_length=2000,
            max_title_length=200,
            max_description_length=5000,
            max_bookmark_content_length=100000,
            max_note_content_length=100000,
            max_prompt_content_length=100000,
            max_tag_name_length=50,
            max_prompt_name_length=100,
            max_argument_name_length=50,
            max_argument_description_length=500,
            rate_read_per_minute=100,
            rate_read_per_day=1000,
            rate_write_per_minute=50,
            rate_write_per_day=500,
            rate_sensitive_per_minute=10,
            rate_sensitive_per_day=100,
            rate_ai_per_minute=0,
            rate_ai_per_day=0,
            rate_ai_byok_per_minute=0,
            rate_ai_byok_per_day=0,
            max_relationships_per_entity=50,
            history_retention_days=30,
            max_history_per_entity=5,  # Low limit for testing
        )

        # Create more records than the limit
        previous = None
        for i in range(1, PRUNE_CHECK_INTERVAL + 1):
            current = f"Content v{i}"
            await history_service.record_action(
                db=db_session,
                user_id=test_user.id,
                entity_type=EntityType.NOTE,
                entity_id=entity_id,
                action=ActionType.CREATE if i == 1 else ActionType.UPDATE,
                current_content=current,
                previous_content=previous,
                metadata=metadata,
                context=request_context,
                limits=limits,
            )
            previous = current

        await db_session.commit()

        # After PRUNE_CHECK_INTERVAL writes with limit=5, should have pruned
        _items, total = await history_service.get_entity_history(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
        )

        # Should have at most max_history_per_entity records
        assert total <= limits.max_history_per_entity

    async def test__record_action__no_pruning_without_limits(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """record_action does not prune when limits is None."""
        entity_id = uuid4()
        metadata = {"title": "Test"}

        # Create PRUNE_CHECK_INTERVAL records without limits
        previous = None
        for i in range(1, PRUNE_CHECK_INTERVAL + 1):
            current = f"Content v{i}"
            await history_service.record_action(
                db=db_session,
                user_id=test_user.id,
                entity_type=EntityType.NOTE,
                entity_id=entity_id,
                action=ActionType.CREATE if i == 1 else ActionType.UPDATE,
                current_content=current,
                previous_content=previous,
                metadata=metadata,
                context=request_context,
                limits=None,  # No limits
            )
            previous = current

        # All records should still exist (no pruning)
        _items, total = await history_service.get_entity_history(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
        )
        assert total == PRUNE_CHECK_INTERVAL


class TestGetUserHistoryFilters:
    """Tests for get_user_history filter functionality."""

    async def test__get_user_history__filter_by_single_entity_type(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """Filter by single entity type returns only matching records."""
        note_id = uuid4()
        bookmark_id = uuid4()

        # Create a note
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=note_id,
            action=ActionType.CREATE,
            current_content="Note content",
            previous_content=None,
            metadata={"title": "Test Note"},
            context=request_context,
        )

        # Create a bookmark
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.BOOKMARK,
            entity_id=bookmark_id,
            action=ActionType.CREATE,
            current_content="Bookmark content",
            previous_content=None,
            metadata={"url": "https://test.com"},
            context=request_context,
        )

        # Filter by note entity type
        items, total = await history_service.get_user_history(
            db=db_session,
            user_id=test_user.id,
            entity_types=[EntityType.NOTE],
        )

        assert total == 1
        assert items[0].entity_type == EntityType.NOTE.value

    async def test__get_user_history__filter_by_multiple_entity_types(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """Filter by multiple entity types returns union (OR logic)."""
        note_id = uuid4()
        bookmark_id = uuid4()
        prompt_id = uuid4()

        # Create one of each
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=note_id,
            action=ActionType.CREATE,
            current_content="Note",
            previous_content=None,
            metadata={"title": "Test"},
            context=request_context,
        )
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.BOOKMARK,
            entity_id=bookmark_id,
            action=ActionType.CREATE,
            current_content="Bookmark",
            previous_content=None,
            metadata={"url": "https://test.com"},
            context=request_context,
        )
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.PROMPT,
            entity_id=prompt_id,
            action=ActionType.CREATE,
            current_content="Prompt",
            previous_content=None,
            metadata={"name": "test-prompt"},
            context=request_context,
        )

        # Filter by note and bookmark (should return 2)
        items, total = await history_service.get_user_history(
            db=db_session,
            user_id=test_user.id,
            entity_types=[EntityType.NOTE, EntityType.BOOKMARK],
        )

        assert total == 2
        entity_types = {item.entity_type for item in items}
        assert entity_types == {"note", "bookmark"}

    async def test__get_user_history__filter_by_actions(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """Filter by action types returns only matching records."""
        entity_id = uuid4()

        # Create and update
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content="Initial",
            previous_content=None,
            metadata={"title": "Test"},
            context=request_context,
        )
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.UPDATE,
            current_content="Updated",
            previous_content="Initial",
            metadata={"title": "Test"},
            context=request_context,
        )

        # Filter by create only
        items, total = await history_service.get_user_history(
            db=db_session,
            user_id=test_user.id,
            actions=[ActionType.CREATE],
        )
        assert total == 1
        assert items[0].action == ActionType.CREATE.value

        # Filter by both
        items, total = await history_service.get_user_history(
            db=db_session,
            user_id=test_user.id,
            actions=[ActionType.CREATE, ActionType.UPDATE],
        )
        assert total == 2

    async def test__get_user_history__filter_by_sources(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
        pat_context: RequestContext,
    ) -> None:
        """Filter by source returns only matching records."""
        entity_id_1 = uuid4()
        entity_id_2 = uuid4()

        # Create with web source (via request_context)
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id_1,
            action=ActionType.CREATE,
            current_content="Web content",
            previous_content=None,
            metadata={"title": "Web"},
            context=request_context,  # source=web
        )

        # Create with MCP source (via pat_context)
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id_2,
            action=ActionType.CREATE,
            current_content="MCP content",
            previous_content=None,
            metadata={"title": "MCP"},
            context=pat_context,  # source=mcp-content
        )

        # Filter by web source
        items, total = await history_service.get_user_history(
            db=db_session,
            user_id=test_user.id,
            sources=["web"],
        )
        assert total == 1
        assert items[0].source == "web"

        # Filter by mcp-content source
        items, total = await history_service.get_user_history(
            db=db_session,
            user_id=test_user.id,
            sources=["mcp-content"],
        )
        assert total == 1
        assert items[0].source == "mcp-content"

    async def test__get_user_history__filter_by_date_range(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """Filter by date range returns only records in range."""
        entity_id = uuid4()

        # Create a record
        history = await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content="Content",
            previous_content=None,
            metadata={"title": "Test"},
            context=request_context,
        )
        await db_session.flush()

        created_at = history.created_at

        # Filter with start_date before creation
        _items, total = await history_service.get_user_history(
            db=db_session,
            user_id=test_user.id,
            start_date=created_at - timedelta(hours=1),
        )
        assert total == 1

        # Filter with start_date after creation
        _items, total = await history_service.get_user_history(
            db=db_session,
            user_id=test_user.id,
            start_date=created_at + timedelta(hours=1),
        )
        assert total == 0

        # Filter with end_date after creation
        _items, total = await history_service.get_user_history(
            db=db_session,
            user_id=test_user.id,
            end_date=created_at + timedelta(hours=1),
        )
        assert total == 1

        # Filter with end_date before creation
        _items, total = await history_service.get_user_history(
            db=db_session,
            user_id=test_user.id,
            end_date=created_at - timedelta(hours=1),
        )
        assert total == 0

    async def test__get_user_history__combined_filters(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """Combined filters use AND logic between categories."""
        note_id = uuid4()
        bookmark_id = uuid4()

        # Create note
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=note_id,
            action=ActionType.CREATE,
            current_content="Note",
            previous_content=None,
            metadata={"title": "Note"},
            context=request_context,
        )

        # Update note
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=note_id,
            action=ActionType.UPDATE,
            current_content="Updated Note",
            previous_content="Note",
            metadata={"title": "Note"},
            context=request_context,
        )

        # Create bookmark
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.BOOKMARK,
            entity_id=bookmark_id,
            action=ActionType.CREATE,
            current_content="Bookmark",
            previous_content=None,
            metadata={"url": "https://test.com"},
            context=request_context,
        )

        # Filter by note AND update (should return 1)
        items, total = await history_service.get_user_history(
            db=db_session,
            user_id=test_user.id,
            entity_types=[EntityType.NOTE],
            actions=[ActionType.UPDATE],
        )
        assert total == 1
        assert items[0].entity_type == "note"
        assert items[0].action == "update"

    async def test__get_user_history__empty_filters_return_all(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """Empty filter lists return all records (same as None)."""
        entity_id = uuid4()

        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content="Content",
            previous_content=None,
            metadata={"title": "Test"},
            context=request_context,
        )

        # Empty lists are falsy in Python, so they skip the filter (show all)
        _items, total = await history_service.get_user_history(
            db=db_session,
            user_id=test_user.id,
            entity_types=[],
            actions=[],
            sources=[],
        )
        assert total == 1


class TestAuditActions:
    """Tests for audit action behavior (DELETE/UNDELETE/ARCHIVE/UNARCHIVE)."""

    async def test__record_action__all_audit_actions_have_null_version(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """All audit actions (DELETE/UNDELETE/ARCHIVE/UNARCHIVE) create NULL version records."""
        entity_id = uuid4()
        content = "Content"
        metadata = {"title": "Test"}

        # Create v1 first
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content=content,
            previous_content=None,
            metadata=metadata,
            context=request_context,
        )

        audit_actions = [
            ActionType.DELETE,
            ActionType.UNDELETE,
            ActionType.ARCHIVE,
            ActionType.UNARCHIVE,
        ]

        for action in audit_actions:
            history = await history_service.record_action(
                db=db_session,
                user_id=test_user.id,
                entity_type=EntityType.NOTE,
                entity_id=entity_id,
                action=action,
                current_content=content,
                previous_content=content,
                metadata=metadata,
                context=request_context,
            )
            assert history.version is None, f"{action} should have NULL version"
            assert history.content_snapshot is None, f"{action} should have no content"
            assert history.content_diff is None, f"{action} should have no diff"

    async def test__record_action__audit_doesnt_affect_version_sequence(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """Audit events don't consume version numbers."""
        entity_id = uuid4()
        metadata = {"title": "Test"}

        # v1: CREATE
        v1 = await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content="Content v1",
            previous_content=None,
            metadata=metadata,
            context=request_context,
        )
        assert v1.version == 1

        # DELETE (audit, NULL version)
        delete = await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.DELETE,
            current_content="Content v1",
            previous_content="Content v1",
            metadata=metadata,
            context=request_context,
        )
        assert delete.version is None

        # v2: UPDATE (should be v2, not v3)
        v2 = await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.UPDATE,
            current_content="Content v2",
            previous_content="Content v1",
            metadata=metadata,
            context=request_context,
        )
        assert v2.version == 2

    async def test__record_action__audit_skips_prune_check(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """Audit actions don't trigger modulo-based pruning (no crash on NULL % 10)."""
        entity_id = uuid4()
        metadata = {"title": "Test"}

        limits = TierLimits(
            max_bookmarks=100,
            max_notes=100,
            max_prompts=100,
            max_pats=100,
            max_url_length=2000,
            max_title_length=200,
            max_description_length=5000,
            max_bookmark_content_length=100000,
            max_note_content_length=100000,
            max_prompt_content_length=100000,
            max_tag_name_length=50,
            max_prompt_name_length=100,
            max_argument_name_length=50,
            max_argument_description_length=500,
            rate_read_per_minute=100,
            rate_read_per_day=1000,
            rate_write_per_minute=50,
            rate_write_per_day=500,
            rate_sensitive_per_minute=10,
            rate_sensitive_per_day=100,
            rate_ai_per_minute=0,
            rate_ai_per_day=0,
            rate_ai_byok_per_minute=0,
            rate_ai_byok_per_day=0,
            max_relationships_per_entity=50,
            history_retention_days=30,
            max_history_per_entity=5,
        )

        # Create v1
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content="Content",
            previous_content=None,
            metadata=metadata,
            context=request_context,
            limits=limits,
        )

        # DELETE with limits - should not crash on NULL % PRUNE_CHECK_INTERVAL
        history = await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.DELETE,
            current_content="Content",
            previous_content="Content",
            metadata=metadata,
            context=request_context,
            limits=limits,
        )
        assert history.version is None

    async def test__record_action__audit_stores_identifying_metadata(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """Audit records store the metadata dict passed to them."""
        entity_id = uuid4()

        # Create v1
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.BOOKMARK,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content="content",
            previous_content=None,
            metadata={"title": "My Bookmark", "url": "https://example.com"},
            context=request_context,
        )

        # DELETE with identifying metadata only
        audit_metadata = {"title": "My Bookmark", "url": "https://example.com"}
        history = await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.BOOKMARK,
            entity_id=entity_id,
            action=ActionType.DELETE,
            current_content="content",
            previous_content="content",
            metadata=audit_metadata,
            context=request_context,
        )

        assert history.metadata_snapshot == audit_metadata

    async def test__record_action__restore_stores_diff_and_increments_version(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """RESTORE action (version restoration) stores diff like UPDATE."""
        entity_id = uuid4()
        metadata = {"title": "Test"}

        # Create v1
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content="Original",
            previous_content=None,
            metadata=metadata,
            context=request_context,
        )

        # v2: UPDATE
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.UPDATE,
            current_content="Modified",
            previous_content="Original",
            metadata=metadata,
            context=request_context,
        )

        # v3: RESTORE (back to "Original")
        history = await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.RESTORE,
            current_content="Original",
            previous_content="Modified",
            metadata=metadata,
            context=request_context,
        )

        assert history.version == 3
        assert history.action == ActionType.RESTORE.value
        assert history.content_diff is not None

    async def test__get_latest_version__ignores_audit_events(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """get_latest_version returns latest versioned record, ignoring audit events."""
        entity_id = uuid4()
        metadata = {"title": "Test"}

        # v1: CREATE
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content="Content",
            previous_content=None,
            metadata=metadata,
            context=request_context,
        )

        # DELETE (audit, NULL version)
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.DELETE,
            current_content="Content",
            previous_content="Content",
            metadata=metadata,
            context=request_context,
        )

        latest = await history_service.get_latest_version(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
        )
        assert latest == 1  # Not None or affected by DELETE audit

    async def test__get_entity_history__orders_by_created_at(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """Entity history is ordered by created_at DESC, mixing versioned and audit records."""
        entity_id = uuid4()
        metadata = {"title": "Test"}

        # v1: CREATE
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content="Content v1",
            previous_content=None,
            metadata=metadata,
            context=request_context,
        )

        # DELETE (audit)
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.DELETE,
            current_content="Content v1",
            previous_content="Content v1",
            metadata=metadata,
            context=request_context,
        )

        # v2: UPDATE
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.UPDATE,
            current_content="Content v2",
            previous_content="Content v1",
            metadata=metadata,
            context=request_context,
        )

        items, total = await history_service.get_entity_history(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
        )

        assert total == 3
        # Chronological DESC: v2, DELETE (null), v1
        assert items[0].version == 2
        assert items[1].version is None
        assert items[1].action == ActionType.DELETE.value
        assert items[2].version == 1

    async def test__get_entity_history_count__excludes_audit(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """_get_entity_history_count only counts versioned records."""
        entity_id = uuid4()
        metadata = {"title": "Test"}

        # v1: CREATE
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content="Content",
            previous_content=None,
            metadata=metadata,
            context=request_context,
        )

        # 3 audit events
        for action in [ActionType.DELETE, ActionType.UNDELETE, ActionType.ARCHIVE]:
            await history_service.record_action(
                db=db_session,
                user_id=test_user.id,
                entity_type=EntityType.NOTE,
                entity_id=entity_id,
                action=action,
                current_content="Content",
                previous_content="Content",
                metadata=metadata,
                context=request_context,
            )

        count = await history_service._get_entity_history_count(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE.value,
            entity_id=entity_id,
        )
        assert count == 1  # Only v1, not the 3 audit events

    async def test__prune_to_limit__excludes_audit_records(
        self,
        db_session: AsyncSession,
        test_user: User,
        request_context: RequestContext,
    ) -> None:
        """Pruning only deletes versioned records; audit records are retained."""
        entity_id = uuid4()
        metadata = {"title": "Test"}

        # Create v1-v5
        previous = None
        for i in range(1, 6):
            current = f"Content v{i}"
            await history_service.record_action(
                db=db_session,
                user_id=test_user.id,
                entity_type=EntityType.NOTE,
                entity_id=entity_id,
                action=ActionType.CREATE if i == 1 else ActionType.UPDATE,
                current_content=current,
                previous_content=previous,
                metadata=metadata,
                context=request_context,
            )
            previous = current

        # 3 audit events
        for action in [ActionType.DELETE, ActionType.UNDELETE, ActionType.ARCHIVE]:
            await history_service.record_action(
                db=db_session,
                user_id=test_user.id,
                entity_type=EntityType.NOTE,
                entity_id=entity_id,
                action=action,
                current_content=previous,
                previous_content=previous,
                metadata=metadata,
                context=request_context,
            )

        # Prune to keep 3 versioned records
        deleted = await history_service._prune_to_limit(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE.value,
            entity_id=entity_id,
            target=3,
        )
        await db_session.commit()

        # Should delete v1, v2 (2 oldest versioned records)
        assert deleted == 2

        items, total = await history_service.get_entity_history(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
        )

        # 3 versioned (v3, v4, v5) + 3 audit = 6 total
        assert total == 6
        versioned = [i for i in items if i.version is not None]
        audit = [i for i in items if i.version is None]
        assert len(versioned) == 3
        assert sorted([v.version for v in versioned]) == [3, 4, 5]
        assert len(audit) == 3


class TestGetVersionDiff:
    """Tests for HistoryService.get_version_diff()."""

    async def test__get_version_diff__basic_content_change(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_note: Note,
        request_context: RequestContext,
    ) -> None:
        """Before content is derived correctly by applying version N's reverse diff."""
        entity_id = test_note.id
        metadata = {"title": "Test Note", "tags": []}

        # v1 CREATE
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content="Hello",
            previous_content=None,
            metadata=metadata,
            context=request_context,
        )

        # v2 UPDATE with content change
        test_note.content = "Hello World"
        await db_session.flush()

        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.UPDATE,
            current_content="Hello World",
            previous_content="Hello",
            metadata=metadata,
            context=request_context,
        )

        result = await history_service.get_version_diff(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            version=2,
        )

        assert result.found is True
        assert result.after_content == "Hello World"
        assert result.before_content == "Hello"
        assert result.after_metadata == metadata
        assert result.before_metadata == metadata
        assert result.warnings is None

    async def test__get_version_diff__version_1_no_predecessor(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_note: Note,
        request_context: RequestContext,
    ) -> None:
        """Version 1 (CREATE) has null before_content and before_metadata."""
        entity_id = test_note.id
        metadata = {"title": "Test Note", "tags": []}

        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content="Initial content",
            previous_content=None,
            metadata=metadata,
            context=request_context,
        )

        result = await history_service.get_version_diff(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            version=1,
        )

        assert result.found is True
        assert result.after_content == "Initial content"
        assert result.before_content is None
        assert result.after_metadata == metadata
        assert result.before_metadata is None
        assert result.warnings is None

    async def test__get_version_diff__metadata_only_change(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_note: Note,
        request_context: RequestContext,
    ) -> None:
        """Metadata-only change returns null content fields and both metadata snapshots."""
        entity_id = test_note.id
        content = "Stable content"
        test_note.content = content
        await db_session.flush()

        metadata_v1 = {"title": "Original", "tags": []}
        metadata_v2 = {"title": "Updated", "tags": ["new-tag"]}

        # v1 CREATE
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content=content,
            previous_content=None,
            metadata=metadata_v1,
            context=request_context,
        )

        # v2 metadata-only change
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.UPDATE,
            current_content=content,
            previous_content=content,
            metadata=metadata_v2,
            context=request_context,
        )

        result = await history_service.get_version_diff(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            version=2,
        )

        assert result.found is True
        assert result.after_content is None
        assert result.before_content is None
        assert result.after_metadata == metadata_v2
        assert result.before_metadata == metadata_v1

    async def test__get_version_diff__content_and_metadata_change(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_note: Note,
        request_context: RequestContext,
    ) -> None:
        """Both content and metadata differ between before/after."""
        entity_id = test_note.id
        metadata_v1 = {"title": "Original", "tags": []}
        metadata_v2 = {"title": "Updated", "tags": ["tag1"]}

        # v1 CREATE
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content="Old content",
            previous_content=None,
            metadata=metadata_v1,
            context=request_context,
        )

        # v2 UPDATE with content + metadata change
        test_note.content = "New content"
        await db_session.flush()

        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.UPDATE,
            current_content="New content",
            previous_content="Old content",
            metadata=metadata_v2,
            context=request_context,
        )

        result = await history_service.get_version_diff(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            version=2,
        )

        assert result.found is True
        assert result.after_content == "New content"
        assert result.before_content == "Old content"
        assert result.after_metadata == metadata_v2
        assert result.before_metadata == metadata_v1

    async def test__get_version_diff__pruned_predecessor(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_note: Note,
        request_context: RequestContext,
    ) -> None:
        """When predecessor record is pruned, before_content still works but before_metadata is None."""
        entity_id = test_note.id
        metadata = {"title": "Test", "tags": []}

        # v1 CREATE
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content="First",
            previous_content=None,
            metadata=metadata,
            context=request_context,
        )

        # v2 UPDATE
        test_note.content = "Second"
        await db_session.flush()

        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.UPDATE,
            current_content="Second",
            previous_content="First",
            metadata=metadata,
            context=request_context,
        )

        # v3 UPDATE
        test_note.content = "Third"
        await db_session.flush()

        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.UPDATE,
            current_content="Third",
            previous_content="Second",
            metadata=metadata,
            context=request_context,
        )

        # Delete v2's record to simulate pruning
        v2_record = await history_service.get_history_at_version(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            version=2,
        )
        assert v2_record is not None
        await db_session.delete(v2_record)
        await db_session.flush()

        # Get diff at v3 — v2's record is gone
        result = await history_service.get_version_diff(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            version=3,
        )

        assert result.found is True
        assert result.after_content == "Third"
        assert result.before_content == "Second"  # Derived from v3's diff, not v2's record
        assert result.before_metadata is None  # v2's record was pruned

    async def test__get_version_diff__multiple_versions_sequential(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_note: Note,
        request_context: RequestContext,
    ) -> None:
        """Chain consistency: each diff's before_content matches previous diff's after_content."""
        entity_id = test_note.id
        contents = ["v1 content", "v2 content", "v3 content", "v4 content"]
        metadata = {"title": "Test", "tags": []}

        # Build version chain
        previous = None
        for i, content in enumerate(contents):
            test_note.content = content
            await db_session.flush()

            await history_service.record_action(
                db=db_session,
                user_id=test_user.id,
                entity_type=EntityType.NOTE,
                entity_id=entity_id,
                action=ActionType.CREATE if i == 0 else ActionType.UPDATE,
                current_content=content,
                previous_content=previous,
                metadata=metadata,
                context=request_context,
            )
            previous = content

        # Check each diff
        prev_after: str | None = None
        for v in range(1, 5):
            result = await history_service.get_version_diff(
                db=db_session,
                user_id=test_user.id,
                entity_type=EntityType.NOTE,
                entity_id=entity_id,
                version=v,
            )
            assert result.found is True
            assert result.after_content == contents[v - 1]

            if v == 1:
                assert result.before_content is None
            else:
                assert result.before_content == contents[v - 2]
                # Chain consistency: before matches previous after
                assert result.before_content == prev_after

            prev_after = result.after_content

    async def test__get_version_diff__version_not_found(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Returns found=False for non-existent version."""
        result = await history_service.get_version_diff(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=uuid4(),
            version=99,
        )
        assert result.found is False

    async def test__get_version_diff__corrupted_diff_returns_warning_not_error(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_note: Note,
        request_context: RequestContext,
    ) -> None:
        """Corrupted (unparseable) diff text returns warning and None before_content, not an exception."""
        entity_id = test_note.id
        metadata = {"title": "Test", "tags": []}

        # v1 CREATE
        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.CREATE,
            current_content="Hello",
            previous_content=None,
            metadata=metadata,
            context=request_context,
        )

        # v2 UPDATE
        test_note.content = "World"
        await db_session.flush()

        await history_service.record_action(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            action=ActionType.UPDATE,
            current_content="World",
            previous_content="Hello",
            metadata=metadata,
            context=request_context,
        )

        # Corrupt v2's diff with garbage text
        v2_record = await history_service.get_history_at_version(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            version=2,
        )
        assert v2_record is not None
        v2_record.content_diff = "NOT_A_VALID_PATCH_FORMAT"
        await db_session.flush()

        result = await history_service.get_version_diff(
            db=db_session,
            user_id=test_user.id,
            entity_type=EntityType.NOTE,
            entity_id=entity_id,
            version=2,
        )

        assert result.found is True
        assert result.after_content is not None  # Reconstruction still works
        assert result.before_content is None  # Cannot derive — fallback to None
        assert result.warnings is not None
        assert any("corrupted" in w.lower() or "before-content" in w.lower() for w in result.warnings)
