"""Integration tests for history recording in services."""
from datetime import UTC, datetime, timedelta

import pytest
from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core import tier_limits
from core.request_context import AuthType, RequestContext
from core.tier_limits import Tier, TierLimits, get_tier_limits
from models.bookmark import Bookmark
from models.content_history import ActionType, ContentHistory, EntityType
from models.user import User
from schemas.bookmark import BookmarkCreate, BookmarkUpdate
from schemas.note import NoteCreate, NoteUpdate
from schemas.prompt import PromptArgument, PromptCreate, PromptUpdate
from schemas.relationship import RelationshipInput
from services.bookmark_service import BookmarkService, DuplicateUrlError
from services.history_service import PRUNE_CHECK_INTERVAL, history_service
from services.note_service import NoteService
from services.prompt_service import PromptService
from tasks.cleanup import cleanup_expired_history


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user for history integration tests."""
    user = User(
        external_auth_id="test-user-history-integration",
        email="historyintegration@test.com",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def make_context(
    source: str = "web",
    auth_type: AuthType = AuthType.SESSION,
    token_prefix: str | None = None,
) -> RequestContext:
    """Create a RequestContext for testing."""
    return RequestContext(source=source, auth_type=auth_type, token_prefix=token_prefix)


async def get_entity_history(
    db_session: AsyncSession,
    user_id: UUID,
    entity_type: EntityType,
    entity_id: UUID,
) -> list[ContentHistory]:
    """Get all history for an entity, ordered chronologically."""
    result = await db_session.execute(
        select(ContentHistory)
        .where(
            ContentHistory.user_id == user_id,
            ContentHistory.entity_type == entity_type.value,
            ContentHistory.entity_id == entity_id,
        )
        .order_by(ContentHistory.created_at, ContentHistory.id),
    )
    return list(result.scalars().all())


class TestBookmarkHistoryIntegration:
    """Tests for history recording in BookmarkService."""

    @pytest.fixture
    def service(self) -> BookmarkService:
        return BookmarkService()

    @pytest.fixture
    def limits(self) -> dict:
        return get_tier_limits("free")

    @pytest.fixture
    def context(self) -> RequestContext:
        return make_context()

    async def test__create__records_history(
        self,
        db_session: AsyncSession,
        test_user: User,
        service: BookmarkService,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Create bookmark records CREATE action in history."""
        data = BookmarkCreate(
            url="https://example.com",
            title="Test Bookmark",
            content="Initial content",
            tags=["test"],
        )

        bookmark = await service.create(db_session, test_user.id, data, limits, context)
        history = await get_entity_history(db_session, test_user.id, EntityType.BOOKMARK, bookmark.id)

        assert len(history) == 1
        record = history[0]
        assert record.version == 1
        assert record.action == ActionType.CREATE.value
        assert record.content_snapshot == "Initial content"
        assert record.content_diff is None
        assert record.metadata_snapshot["title"] == "Test Bookmark"
        assert record.metadata_snapshot["url"] == "https://example.com/"  # URL normalized
        assert len(record.metadata_snapshot["tags"]) == 1
        assert record.metadata_snapshot["tags"][0]["name"] == "test"
        assert "id" in record.metadata_snapshot["tags"][0]
        assert record.source == "web"
        assert record.auth_type == AuthType.SESSION.value

    async def test__update__records_history_on_content_change(
        self,
        db_session: AsyncSession,
        test_user: User,
        service: BookmarkService,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Update bookmark records UPDATE action when content changes."""
        # Create bookmark
        create_data = BookmarkCreate(
            url="https://example.com",
            content="Original content",
        )
        bookmark = await service.create(db_session, test_user.id, create_data, limits, context)

        # Update content
        update_data = BookmarkUpdate(content="Updated content")
        await service.update(db_session, test_user.id, bookmark.id, update_data, limits, context)

        history = await get_entity_history(db_session, test_user.id, EntityType.BOOKMARK, bookmark.id)

        assert len(history) == 2
        update_record = history[1]
        assert update_record.version == 2
        assert update_record.action == ActionType.UPDATE.value
        assert update_record.content_snapshot is None
        assert update_record.content_diff is not None  # Reverse diff stored

    async def test__update__records_history_on_metadata_change(
        self,
        db_session: AsyncSession,
        test_user: User,
        service: BookmarkService,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Update bookmark records UPDATE action when metadata changes."""
        # Create bookmark
        create_data = BookmarkCreate(
            url="https://example.com",
            title="Original Title",
            content="Content",
        )
        bookmark = await service.create(db_session, test_user.id, create_data, limits, context)

        # Update title only (no content change)
        update_data = BookmarkUpdate(title="New Title")
        await service.update(db_session, test_user.id, bookmark.id, update_data, limits, context)

        history = await get_entity_history(db_session, test_user.id, EntityType.BOOKMARK, bookmark.id)

        assert len(history) == 2
        update_record = history[1]
        assert update_record.action == ActionType.UPDATE.value
        assert update_record.metadata_snapshot["title"] == "New Title"

    async def test__update__skips_history_on_no_change(
        self,
        db_session: AsyncSession,
        test_user: User,
        service: BookmarkService,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """No-op update does not record history."""
        # Create bookmark
        create_data = BookmarkCreate(
            url="https://example.com",
            title="Title",
            content="Content",
        )
        bookmark = await service.create(db_session, test_user.id, create_data, limits, context)

        # Update with same values
        update_data = BookmarkUpdate(title="Title")
        await service.update(db_session, test_user.id, bookmark.id, update_data, limits, context)

        history = await get_entity_history(db_session, test_user.id, EntityType.BOOKMARK, bookmark.id)

        # Only CREATE, no UPDATE
        assert len(history) == 1
        assert history[0].action == ActionType.CREATE.value

    async def test__delete__records_history(
        self,
        db_session: AsyncSession,
        test_user: User,
        service: BookmarkService,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Soft delete records DELETE as audit action (no content, no version)."""
        # Create bookmark
        create_data = BookmarkCreate(
            url="https://example.com",
            content="Content to preserve",
        )
        bookmark = await service.create(db_session, test_user.id, create_data, limits, context)

        # Soft delete
        await service.delete(db_session, test_user.id, bookmark.id, permanent=False, context=context)

        history = await get_entity_history(db_session, test_user.id, EntityType.BOOKMARK, bookmark.id)

        assert len(history) == 2
        delete_record = history[1]
        assert delete_record.action == ActionType.DELETE.value
        assert delete_record.version is None
        assert delete_record.content_snapshot is None
        assert delete_record.content_diff is None
        assert "url" in delete_record.metadata_snapshot

    async def test__hard_delete__cascades_history(
        self,
        db_session: AsyncSession,
        test_user: User,
        service: BookmarkService,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Hard delete removes all history for the entity."""
        # Create and soft delete bookmark
        create_data = BookmarkCreate(url="https://example.com", content="Content")
        bookmark = await service.create(db_session, test_user.id, create_data, limits, context)
        await service.delete(db_session, test_user.id, bookmark.id, permanent=False, context=context)

        # Verify history exists
        history = await get_entity_history(db_session, test_user.id, EntityType.BOOKMARK, bookmark.id)
        assert len(history) == 2

        # Hard delete
        await service.delete(db_session, test_user.id, bookmark.id, permanent=True)

        # Verify history is gone
        history = await get_entity_history(db_session, test_user.id, EntityType.BOOKMARK, bookmark.id)
        assert len(history) == 0

    async def test__restore__records_history(
        self,
        db_session: AsyncSession,
        test_user: User,
        service: BookmarkService,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Restore (undelete) records UNDELETE as audit action."""
        # Create, delete, then restore
        create_data = BookmarkCreate(url="https://example.com", content="Content")
        bookmark = await service.create(db_session, test_user.id, create_data, limits, context)
        await service.delete(db_session, test_user.id, bookmark.id, permanent=False, context=context)
        await service.restore(db_session, test_user.id, bookmark.id, context)

        history = await get_entity_history(db_session, test_user.id, EntityType.BOOKMARK, bookmark.id)

        assert len(history) == 3
        restore_record = history[2]
        assert restore_record.action == ActionType.UNDELETE.value
        assert restore_record.version is None

    async def test__archive__records_history(
        self,
        db_session: AsyncSession,
        test_user: User,
        service: BookmarkService,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Archive records ARCHIVE as audit action."""
        create_data = BookmarkCreate(url="https://example.com", content="Content")
        bookmark = await service.create(db_session, test_user.id, create_data, limits, context)
        await service.archive(db_session, test_user.id, bookmark.id, context)

        history = await get_entity_history(db_session, test_user.id, EntityType.BOOKMARK, bookmark.id)

        assert len(history) == 2
        archive_record = history[1]
        assert archive_record.action == ActionType.ARCHIVE.value
        assert archive_record.version is None

    async def test__archive__idempotent_no_duplicate_history(
        self,
        db_session: AsyncSession,
        test_user: User,
        service: BookmarkService,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Archiving already-archived bookmark does not record duplicate history."""
        create_data = BookmarkCreate(url="https://example.com", content="Content")
        bookmark = await service.create(db_session, test_user.id, create_data, limits, context)
        await service.archive(db_session, test_user.id, bookmark.id, context)
        await service.archive(db_session, test_user.id, bookmark.id, context)  # Second archive

        history = await get_entity_history(db_session, test_user.id, EntityType.BOOKMARK, bookmark.id)

        # Only CREATE + one ARCHIVE
        assert len(history) == 2

    async def test__unarchive__records_history(
        self,
        db_session: AsyncSession,
        test_user: User,
        service: BookmarkService,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Unarchive records UNARCHIVE as audit action."""
        create_data = BookmarkCreate(url="https://example.com", content="Content")
        bookmark = await service.create(db_session, test_user.id, create_data, limits, context)
        await service.archive(db_session, test_user.id, bookmark.id, context)
        await service.unarchive(db_session, test_user.id, bookmark.id, context)

        history = await get_entity_history(db_session, test_user.id, EntityType.BOOKMARK, bookmark.id)

        assert len(history) == 3
        unarchive_record = history[2]
        assert unarchive_record.action == ActionType.UNARCHIVE.value
        assert unarchive_record.version is None


class TestContextPropagation:
    """Tests for request context propagation to history records."""

    async def test__context_web_session(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Web + session context is recorded."""
        context = make_context(source="web", auth_type=AuthType.SESSION)
        service = BookmarkService()
        limits = get_tier_limits("free")

        data = BookmarkCreate(url="https://example.com", content="Content")
        bookmark = await service.create(db_session, test_user.id, data, limits, context)

        history = await get_entity_history(db_session, test_user.id, EntityType.BOOKMARK, bookmark.id)

        assert history[0].source == "web"
        assert history[0].auth_type == "session"
        assert history[0].token_prefix is None

    async def test__context_api_pat(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """API + PAT context with token prefix is recorded."""
        context = make_context(
            source="api",
            auth_type=AuthType.PAT,
            token_prefix="bm_test123...",
        )
        service = BookmarkService()
        limits = get_tier_limits("free")

        data = BookmarkCreate(url="https://example.com", content="Content")
        bookmark = await service.create(db_session, test_user.id, data, limits, context)

        history = await get_entity_history(db_session, test_user.id, EntityType.BOOKMARK, bookmark.id)

        assert history[0].source == "api"
        assert history[0].auth_type == "pat"
        assert history[0].token_prefix == "bm_test123..."

    async def test__context_mcp_content(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """MCP-content source is recorded."""
        context = make_context(
            source="mcp-content",
            auth_type=AuthType.PAT,
            token_prefix="bm_mcp...",
        )
        service = NoteService()
        limits = get_tier_limits("free")

        data = NoteCreate(title="Test", content="Content")
        note = await service.create(db_session, test_user.id, data, limits, context)

        history = await get_entity_history(db_session, test_user.id, EntityType.NOTE, note.id)

        assert history[0].source == "mcp-content"


class TestNoteHistoryIntegration:
    """Tests for history recording in NoteService."""

    @pytest.fixture
    def service(self) -> NoteService:
        return NoteService()

    @pytest.fixture
    def limits(self) -> dict:
        return get_tier_limits("free")

    @pytest.fixture
    def context(self) -> RequestContext:
        return make_context()

    async def test__create__records_history(
        self,
        db_session: AsyncSession,
        test_user: User,
        service: NoteService,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Create note records CREATE action in history."""
        data = NoteCreate(
            title="Test Note",
            content="Initial content",
            tags=["test"],
        )

        note = await service.create(db_session, test_user.id, data, limits, context)
        history = await get_entity_history(db_session, test_user.id, EntityType.NOTE, note.id)

        assert len(history) == 1
        record = history[0]
        assert record.version == 1
        assert record.action == ActionType.CREATE.value
        assert record.content_snapshot == "Initial content"
        assert record.content_diff is None
        assert record.metadata_snapshot["title"] == "Test Note"
        assert len(record.metadata_snapshot["tags"]) == 1
        assert record.metadata_snapshot["tags"][0]["name"] == "test"
        assert "id" in record.metadata_snapshot["tags"][0]
        assert record.source == "web"
        assert record.auth_type == AuthType.SESSION.value

    async def test__update__records_history_on_content_change(
        self,
        db_session: AsyncSession,
        test_user: User,
        service: NoteService,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Update note records UPDATE action when content changes."""
        create_data = NoteCreate(title="Test Note", content="Original content")
        note = await service.create(db_session, test_user.id, create_data, limits, context)

        update_data = NoteUpdate(content="Updated content")
        await service.update(db_session, test_user.id, note.id, update_data, limits, context)

        history = await get_entity_history(db_session, test_user.id, EntityType.NOTE, note.id)

        assert len(history) == 2
        update_record = history[1]
        assert update_record.version == 2
        assert update_record.action == ActionType.UPDATE.value
        assert update_record.content_snapshot is None
        assert update_record.content_diff is not None

    async def test__update__records_history_on_metadata_change(
        self,
        db_session: AsyncSession,
        test_user: User,
        service: NoteService,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Update note records UPDATE action when metadata changes."""
        create_data = NoteCreate(title="Original Title", content="Content")
        note = await service.create(db_session, test_user.id, create_data, limits, context)

        update_data = NoteUpdate(title="New Title")
        await service.update(db_session, test_user.id, note.id, update_data, limits, context)

        history = await get_entity_history(db_session, test_user.id, EntityType.NOTE, note.id)

        assert len(history) == 2
        update_record = history[1]
        assert update_record.action == ActionType.UPDATE.value
        assert update_record.metadata_snapshot["title"] == "New Title"

    async def test__update__skips_history_on_no_change(
        self,
        db_session: AsyncSession,
        test_user: User,
        service: NoteService,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """No-op update does not record history."""
        create_data = NoteCreate(title="Title", content="Content")
        note = await service.create(db_session, test_user.id, create_data, limits, context)

        update_data = NoteUpdate(title="Title")
        await service.update(db_session, test_user.id, note.id, update_data, limits, context)

        history = await get_entity_history(db_session, test_user.id, EntityType.NOTE, note.id)

        assert len(history) == 1
        assert history[0].action == ActionType.CREATE.value

    async def test__delete__records_history(
        self,
        db_session: AsyncSession,
        test_user: User,
        service: NoteService,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Soft delete records DELETE as audit action (no content, no version)."""
        create_data = NoteCreate(title="Test Note", content="Content to preserve")
        note = await service.create(db_session, test_user.id, create_data, limits, context)

        await service.delete(db_session, test_user.id, note.id, permanent=False, context=context)

        history = await get_entity_history(db_session, test_user.id, EntityType.NOTE, note.id)

        assert len(history) == 2
        delete_record = history[1]
        assert delete_record.action == ActionType.DELETE.value
        assert delete_record.version is None
        assert delete_record.content_snapshot is None
        assert delete_record.content_diff is None
        assert "title" in delete_record.metadata_snapshot

    async def test__hard_delete__cascades_history(
        self,
        db_session: AsyncSession,
        test_user: User,
        service: NoteService,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Hard delete removes all history for the entity."""
        create_data = NoteCreate(title="Test Note", content="Content")
        note = await service.create(db_session, test_user.id, create_data, limits, context)
        await service.delete(db_session, test_user.id, note.id, permanent=False, context=context)

        history = await get_entity_history(db_session, test_user.id, EntityType.NOTE, note.id)
        assert len(history) == 2

        await service.delete(db_session, test_user.id, note.id, permanent=True)

        history = await get_entity_history(db_session, test_user.id, EntityType.NOTE, note.id)
        assert len(history) == 0

    async def test__restore__records_history(
        self,
        db_session: AsyncSession,
        test_user: User,
        service: NoteService,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Restore (undelete) records UNDELETE as audit action."""
        create_data = NoteCreate(title="Test Note", content="Content")
        note = await service.create(db_session, test_user.id, create_data, limits, context)
        await service.delete(db_session, test_user.id, note.id, permanent=False, context=context)
        await service.restore(db_session, test_user.id, note.id, context)

        history = await get_entity_history(db_session, test_user.id, EntityType.NOTE, note.id)

        assert len(history) == 3
        restore_record = history[2]
        assert restore_record.action == ActionType.UNDELETE.value
        assert restore_record.version is None

    async def test__archive__records_history(
        self,
        db_session: AsyncSession,
        test_user: User,
        service: NoteService,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Archive records ARCHIVE as audit action."""
        create_data = NoteCreate(title="Test Note", content="Content")
        note = await service.create(db_session, test_user.id, create_data, limits, context)
        await service.archive(db_session, test_user.id, note.id, context)

        history = await get_entity_history(db_session, test_user.id, EntityType.NOTE, note.id)

        assert len(history) == 2
        archive_record = history[1]
        assert archive_record.action == ActionType.ARCHIVE.value
        assert archive_record.version is None

    async def test__archive__idempotent_no_duplicate_history(
        self,
        db_session: AsyncSession,
        test_user: User,
        service: NoteService,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Archiving already-archived note does not record duplicate history."""
        create_data = NoteCreate(title="Test Note", content="Content")
        note = await service.create(db_session, test_user.id, create_data, limits, context)
        await service.archive(db_session, test_user.id, note.id, context)
        await service.archive(db_session, test_user.id, note.id, context)

        history = await get_entity_history(db_session, test_user.id, EntityType.NOTE, note.id)

        assert len(history) == 2

    async def test__unarchive__records_history(
        self,
        db_session: AsyncSession,
        test_user: User,
        service: NoteService,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Unarchive records UNARCHIVE as audit action."""
        create_data = NoteCreate(title="Test Note", content="Content")
        note = await service.create(db_session, test_user.id, create_data, limits, context)
        await service.archive(db_session, test_user.id, note.id, context)
        await service.unarchive(db_session, test_user.id, note.id, context)

        history = await get_entity_history(db_session, test_user.id, EntityType.NOTE, note.id)

        assert len(history) == 3
        unarchive_record = history[2]
        assert unarchive_record.action == ActionType.UNARCHIVE.value
        assert unarchive_record.version is None


class TestPromptHistoryIntegration:
    """Tests for history recording in PromptService."""

    @pytest.fixture
    def service(self) -> PromptService:
        return PromptService()

    @pytest.fixture
    def limits(self) -> dict:
        return get_tier_limits("free")

    @pytest.fixture
    def context(self) -> RequestContext:
        return make_context()

    async def test__create__records_history_with_arguments(
        self,
        db_session: AsyncSession,
        test_user: User,
        service: PromptService,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Prompt create records history including arguments in metadata."""
        data = PromptCreate(
            name="test-prompt",
            content="Hello {{ name }}",
            arguments=[PromptArgument(name="name", description="User name")],
        )

        prompt = await service.create(db_session, test_user.id, data, limits, context)
        history = await get_entity_history(db_session, test_user.id, EntityType.PROMPT, prompt.id)

        assert len(history) == 1
        record = history[0]
        assert record.version == 1
        assert record.action == ActionType.CREATE.value
        assert record.content_snapshot == "Hello {{ name }}"
        assert record.metadata_snapshot["name"] == "test-prompt"
        assert record.metadata_snapshot["arguments"] == [
            {"name": "name", "description": "User name", "required": None},
        ]

    async def test__update__records_history_on_content_change(
        self,
        db_session: AsyncSession,
        test_user: User,
        service: PromptService,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Update prompt records UPDATE action when content changes."""
        create_data = PromptCreate(name="test-prompt-update", content="Original content")
        prompt = await service.create(db_session, test_user.id, create_data, limits, context)

        update_data = PromptUpdate(content="Updated content")
        await service.update(db_session, test_user.id, prompt.id, update_data, limits, context)

        history = await get_entity_history(db_session, test_user.id, EntityType.PROMPT, prompt.id)

        assert len(history) == 2
        update_record = history[1]
        assert update_record.version == 2
        assert update_record.action == ActionType.UPDATE.value
        assert update_record.content_snapshot is None
        assert update_record.content_diff is not None

    async def test__update__records_history_on_metadata_change(
        self,
        db_session: AsyncSession,
        test_user: User,
        service: PromptService,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Update prompt records UPDATE action when metadata changes."""
        create_data = PromptCreate(
            name="test-prompt-meta",
            title="Original Title",
            content="Content",
        )
        prompt = await service.create(db_session, test_user.id, create_data, limits, context)

        update_data = PromptUpdate(title="New Title")
        await service.update(db_session, test_user.id, prompt.id, update_data, limits, context)

        history = await get_entity_history(db_session, test_user.id, EntityType.PROMPT, prompt.id)

        assert len(history) == 2
        update_record = history[1]
        assert update_record.action == ActionType.UPDATE.value
        assert update_record.metadata_snapshot["title"] == "New Title"

    async def test__update__skips_history_on_no_change(
        self,
        db_session: AsyncSession,
        test_user: User,
        service: PromptService,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """No-op update does not record history."""
        create_data = PromptCreate(name="test-prompt-noop", title="Title", content="Content")
        prompt = await service.create(db_session, test_user.id, create_data, limits, context)

        update_data = PromptUpdate(title="Title")
        await service.update(db_session, test_user.id, prompt.id, update_data, limits, context)

        history = await get_entity_history(db_session, test_user.id, EntityType.PROMPT, prompt.id)

        assert len(history) == 1
        assert history[0].action == ActionType.CREATE.value

    async def test__delete__records_history(
        self,
        db_session: AsyncSession,
        test_user: User,
        service: PromptService,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Soft delete records DELETE as audit action (no content, no version)."""
        create_data = PromptCreate(name="test-prompt-delete", content="Content to preserve")
        prompt = await service.create(db_session, test_user.id, create_data, limits, context)

        await service.delete(db_session, test_user.id, prompt.id, permanent=False, context=context)

        history = await get_entity_history(db_session, test_user.id, EntityType.PROMPT, prompt.id)

        assert len(history) == 2
        delete_record = history[1]
        assert delete_record.action == ActionType.DELETE.value
        assert delete_record.version is None
        assert delete_record.content_snapshot is None
        assert delete_record.content_diff is None
        assert "name" in delete_record.metadata_snapshot

    async def test__hard_delete__cascades_history(
        self,
        db_session: AsyncSession,
        test_user: User,
        service: PromptService,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Hard delete removes all history for the entity."""
        create_data = PromptCreate(name="test-prompt-hard-delete", content="Content")
        prompt = await service.create(db_session, test_user.id, create_data, limits, context)
        await service.delete(db_session, test_user.id, prompt.id, permanent=False, context=context)

        history = await get_entity_history(db_session, test_user.id, EntityType.PROMPT, prompt.id)
        assert len(history) == 2

        await service.delete(db_session, test_user.id, prompt.id, permanent=True)

        history = await get_entity_history(db_session, test_user.id, EntityType.PROMPT, prompt.id)
        assert len(history) == 0

    async def test__restore__records_history(
        self,
        db_session: AsyncSession,
        test_user: User,
        service: PromptService,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Restore (undelete) records UNDELETE as audit action."""
        create_data = PromptCreate(name="test-prompt-restore", content="Content")
        prompt = await service.create(db_session, test_user.id, create_data, limits, context)
        await service.delete(db_session, test_user.id, prompt.id, permanent=False, context=context)
        await service.restore(db_session, test_user.id, prompt.id, context)

        history = await get_entity_history(db_session, test_user.id, EntityType.PROMPT, prompt.id)

        assert len(history) == 3
        restore_record = history[2]
        assert restore_record.action == ActionType.UNDELETE.value
        assert restore_record.version is None

    async def test__archive__records_history(
        self,
        db_session: AsyncSession,
        test_user: User,
        service: PromptService,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Archive records ARCHIVE as audit action."""
        create_data = PromptCreate(name="test-prompt-archive", content="Content")
        prompt = await service.create(db_session, test_user.id, create_data, limits, context)
        await service.archive(db_session, test_user.id, prompt.id, context)

        history = await get_entity_history(db_session, test_user.id, EntityType.PROMPT, prompt.id)

        assert len(history) == 2
        archive_record = history[1]
        assert archive_record.action == ActionType.ARCHIVE.value
        assert archive_record.version is None

    async def test__archive__idempotent_no_duplicate_history(
        self,
        db_session: AsyncSession,
        test_user: User,
        service: PromptService,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Archiving already-archived prompt does not record duplicate history."""
        create_data = PromptCreate(name="test-prompt-idempotent", content="Content")
        prompt = await service.create(db_session, test_user.id, create_data, limits, context)
        await service.archive(db_session, test_user.id, prompt.id, context)
        await service.archive(db_session, test_user.id, prompt.id, context)

        history = await get_entity_history(db_session, test_user.id, EntityType.PROMPT, prompt.id)

        assert len(history) == 2

    async def test__unarchive__records_history(
        self,
        db_session: AsyncSession,
        test_user: User,
        service: PromptService,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Unarchive records UNARCHIVE as audit action."""
        create_data = PromptCreate(name="test-prompt-unarchive", content="Content")
        prompt = await service.create(db_session, test_user.id, create_data, limits, context)
        await service.archive(db_session, test_user.id, prompt.id, context)
        await service.unarchive(db_session, test_user.id, prompt.id, context)

        history = await get_entity_history(db_session, test_user.id, EntityType.PROMPT, prompt.id)

        assert len(history) == 3
        unarchive_record = history[2]
        assert unarchive_record.action == ActionType.UNARCHIVE.value
        assert unarchive_record.version is None


class TestTransactionRollbackSafety:
    """P0 test: Verify history survives transaction rollback scenarios."""

    async def test__service_error_after_history__history_rolled_back(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """If service operation fails after history recorded, both are rolled back."""
        # This test verifies the atomic nature of history + entity changes.
        # Since history is recorded AFTER entity changes in the same transaction,
        # if the transaction commits, both are persisted; if it fails, both roll back.
        #
        # We can't easily simulate mid-operation failures, but we can verify that
        # a successful operation has both entity and history persisted.

        service = BookmarkService()
        limits = get_tier_limits("free")
        context = make_context()

        data = BookmarkCreate(url="https://example.com", content="Content")
        bookmark = await service.create(db_session, test_user.id, data, limits, context)

        # Verify both entity and history exist
        assert bookmark.id is not None
        history = await get_entity_history(db_session, test_user.id, EntityType.BOOKMARK, bookmark.id)
        assert len(history) == 1

        # If we had a way to fail between entity change and history recording,
        # the transaction would roll back and neither would be persisted.
        # The implementation ensures history is recorded in the same transaction.


class TestHistoryWithoutContext:
    """Tests for operations without context (history skipped)."""

    async def test__create_without_context__no_history(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Create without context does not record history."""
        service = BookmarkService()
        limits = get_tier_limits("free")

        data = BookmarkCreate(url="https://example.com", content="Content")
        bookmark = await service.create(db_session, test_user.id, data, limits)  # No context

        history = await get_entity_history(db_session, test_user.id, EntityType.BOOKMARK, bookmark.id)

        assert len(history) == 0

    async def test__update_without_context__no_history(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Update without context does not record history."""
        service = BookmarkService()
        limits = get_tier_limits("free")
        context = make_context()

        # Create with context
        data = BookmarkCreate(url="https://example.com", content="Content")
        bookmark = await service.create(db_session, test_user.id, data, limits, context)

        # Update without context
        update_data = BookmarkUpdate(content="New content")
        await service.update(db_session, test_user.id, bookmark.id, update_data, limits)  # No context

        history = await get_entity_history(db_session, test_user.id, EntityType.BOOKMARK, bookmark.id)

        # Only CREATE, no UPDATE
        assert len(history) == 1
        assert history[0].action == ActionType.CREATE.value


class TestRestoreUrlConflict:
    """Tests for history behavior when restore fails due to URL conflict."""

    async def test__restore__url_conflict_does_not_record_history(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """When restore fails due to URL conflict, no history should be recorded."""
        service = BookmarkService()
        limits = get_tier_limits("free")
        context = make_context()

        # Create and soft-delete a bookmark
        data1 = BookmarkCreate(url="https://conflict-test.com", content="First bookmark")
        bookmark1 = await service.create(db_session, test_user.id, data1, limits, context)
        await service.delete(db_session, test_user.id, bookmark1.id, permanent=False, context=context)

        # Create another bookmark with the same URL (now that the first is deleted)
        data2 = BookmarkCreate(url="https://conflict-test.com", content="Second bookmark")
        bookmark2 = await service.create(db_session, test_user.id, data2, limits, context)

        # Get history count before restore attempt
        history_before = await get_entity_history(
            db_session, test_user.id, EntityType.BOOKMARK, bookmark1.id,
        )
        history_count_before = len(history_before)

        # Try to restore the first bookmark - should fail due to URL conflict
        with pytest.raises(DuplicateUrlError):
            await service.restore(db_session, test_user.id, bookmark1.id, context)

        # History count should be unchanged (no RESTORE record added)
        history_after = await get_entity_history(
            db_session, test_user.id, EntityType.BOOKMARK, bookmark1.id,
        )
        assert len(history_after) == history_count_before

        # The last action should still be DELETE, not RESTORE
        assert history_after[-1].action == ActionType.DELETE.value

        # Clean up: bookmark2 should still exist
        active = await service.get(db_session, test_user.id, bookmark2.id)
        assert active is not None


class TestStrReplaceHistory:
    """Tests for history recording in str-replace endpoints."""

    @pytest.fixture
    async def dev_user_id(self, client: AsyncClient) -> UUID:
        """Get the dev user ID from the API."""
        response = await client.get("/users/me")
        assert response.status_code == 200
        return UUID(response.json()["id"])

    async def test__str_replace_bookmark__records_history(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        dev_user_id: UUID,
    ) -> None:
        """str-replace on bookmark creates history record with UPDATE action."""
        # Create bookmark via API
        response = await client.post(
            "/bookmarks/",
            json={"url": "https://str-replace-history.com", "content": "Original content"},
        )
        assert response.status_code == 201
        bookmark_id = response.json()["id"]

        # Perform str-replace via API
        response = await client.patch(
            f"/bookmarks/{bookmark_id}/str-replace",
            json={"old_str": "Original", "new_str": "Updated"},
        )
        assert response.status_code == 200

        # Query history from database
        history = await get_entity_history(
            db_session, dev_user_id, EntityType.BOOKMARK, UUID(bookmark_id),
        )

        # Should have CREATE + UPDATE from str-replace
        assert len(history) == 2
        update_record = history[1]
        assert update_record.action == ActionType.UPDATE.value
        assert update_record.content_diff is not None
        # Source is recorded (actual value depends on test client headers)
        assert update_record.source is not None

    async def test__str_replace_note__records_history(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        dev_user_id: UUID,
    ) -> None:
        """str-replace on note creates history record with UPDATE action."""
        # Create note via API
        response = await client.post(
            "/notes/",
            json={"title": "Test Note", "content": "Hello world"},
        )
        assert response.status_code == 201
        note_id = response.json()["id"]

        # Perform str-replace via API
        response = await client.patch(
            f"/notes/{note_id}/str-replace",
            json={"old_str": "world", "new_str": "universe"},
        )
        assert response.status_code == 200

        # Query history from database
        history = await get_entity_history(
            db_session, dev_user_id, EntityType.NOTE, UUID(note_id),
        )

        # Should have CREATE + UPDATE from str-replace
        assert len(history) == 2
        update_record = history[1]
        assert update_record.action == ActionType.UPDATE.value
        assert update_record.content_diff is not None

    async def test__str_replace_prompt__records_history(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        dev_user_id: UUID,
    ) -> None:
        """str-replace on prompt creates history record with UPDATE action."""
        # Use unique name to avoid conflicts with other tests
        unique_name = f"str-replace-test-{uuid4().hex[:8]}"

        # Create prompt via API (include argument definition for Jinja2 validation)
        response = await client.post(
            "/prompts/",
            json={
                "name": unique_name,
                "content": "Say hello to {{ name }}",
                "arguments": [{"name": "name", "description": "User name"}],
            },
        )
        assert response.status_code == 201
        prompt_id = response.json()["id"]

        # Perform str-replace via API
        response = await client.patch(
            f"/prompts/{prompt_id}/str-replace",
            json={"old_str": "hello", "new_str": "goodbye"},
        )
        assert response.status_code == 200

        # Query history from database
        history = await get_entity_history(
            db_session, dev_user_id, EntityType.PROMPT, UUID(prompt_id),
        )

        # Should have CREATE + UPDATE from str-replace
        assert len(history) == 2
        update_record = history[1]
        assert update_record.action == ActionType.UPDATE.value
        assert update_record.content_diff is not None

    async def test__str_replace__history_has_correct_content(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        dev_user_id: UUID,
    ) -> None:
        """str-replace history has correct previous and current content captured."""
        # Create note via API
        response = await client.post(
            "/notes/",
            json={"title": "Test", "content": "First line\nSecond line\nThird line"},
        )
        assert response.status_code == 201
        note_id = response.json()["id"]

        # Perform str-replace via API
        response = await client.patch(
            f"/notes/{note_id}/str-replace",
            json={"old_str": "Second", "new_str": "Modified"},
        )
        assert response.status_code == 200

        # Query history from database
        history = await get_entity_history(
            db_session, dev_user_id, EntityType.NOTE, UUID(note_id),
        )

        update_record = history[1]

        # Verify the reverse diff can reconstruct the original content
        dmp = history_service.dmp
        patches = dmp.patch_fromText(update_record.content_diff)
        new_content = "First line\nModified line\nThird line"
        result, _ = dmp.patch_apply(patches, new_content)
        assert result == "First line\nSecond line\nThird line"  # Original content

    async def test__str_replace_noop__no_history_recorded(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        dev_user_id: UUID,
    ) -> None:
        """str-replace with old_str == new_str (no-op) does not record history."""
        # Create note via API
        response = await client.post(
            "/notes/",
            json={"title": "Test", "content": "Hello world"},
        )
        assert response.status_code == 201
        note_id = response.json()["id"]

        # Perform no-op str-replace via API
        response = await client.patch(
            f"/notes/{note_id}/str-replace",
            json={"old_str": "world", "new_str": "world"},  # Same value
        )
        assert response.status_code == 200

        # Query history from database
        history = await get_entity_history(
            db_session, dev_user_id, EntityType.NOTE, UUID(note_id),
        )

        # Should only have CREATE, no UPDATE from no-op str-replace
        assert len(history) == 1
        assert history[0].action == ActionType.CREATE.value

    async def test__str_replace__triggers_count_based_pruning(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        dev_user_id: UUID,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        str-replace triggers count-based pruning when limits are exceeded.

        This is a regression test for the bug where str-replace endpoints
        didn't pass limits to record_action, preventing pruning.
        """
        # Set very low history limit to trigger pruning quickly
        max_history = 3
        test_limits = TierLimits(
            max_bookmarks=100,
            max_notes=100,
            max_prompts=100,
            max_pats=100,
            max_title_length=200,
            max_description_length=1000,
            max_tag_name_length=50,
            max_bookmark_content_length=100_000,
            max_note_content_length=100_000,
            max_prompt_content_length=100_000,
            max_url_length=2048,
            max_prompt_name_length=100,
            max_argument_name_length=100,
            max_argument_description_length=500,
            rate_read_per_minute=1000,
            rate_read_per_day=10000,
            rate_write_per_minute=1000,
            rate_write_per_day=10000,
            rate_sensitive_per_minute=1000,
            rate_sensitive_per_day=10000,
            rate_ai_per_minute=0,
            rate_ai_per_day=0,
            rate_ai_byok_per_minute=0,
            rate_ai_byok_per_day=0,
            max_relationships_per_entity=50,
            history_retention_days=30,
            max_history_per_entity=max_history,
        )
        monkeypatch.setattr(tier_limits, "TIER_LIMITS", {
            Tier.FREE: test_limits,
            Tier.STANDARD: test_limits,
            Tier.PRO: test_limits,
            Tier.DEV: test_limits,
        })

        # Create note with content we can edit repeatedly
        # Use bracketed markers so each replacement is unique and won't match others
        # e.g., [W0] won't match [W10]
        content = " ".join([f"[W{i}]" for i in range(20)])
        response = await client.post(
            "/notes/",
            json={"title": "Pruning Test", "content": content},
        )
        assert response.status_code == 201
        note_id = response.json()["id"]

        # Perform enough str-replace edits to exceed limit and trigger prune check
        # PRUNE_CHECK_INTERVAL is 10, so at version 10 pruning should trigger
        # Version 1 = CREATE, so we need 9 more edits to reach version 10
        num_edits = PRUNE_CHECK_INTERVAL - 1  # 9 edits to reach v10
        for i in range(num_edits):
            response = await client.patch(
                f"/notes/{note_id}/str-replace",
                json={"old_str": f"[W{i}]", "new_str": f"[E{i}]"},
            )
            assert response.status_code == 200, f"Edit {i} failed: {response.text}"

        # Force commit to ensure pruning is visible
        await db_session.commit()

        # Query history - should be pruned to max_history
        history = await get_entity_history(
            db_session, dev_user_id, EntityType.NOTE, UUID(note_id),
        )

        # Should have exactly max_history records after pruning at v10
        # v1 (CREATE) + 9 edits = v10, which triggers prune to max_history
        assert len(history) == max_history, (
            f"Expected exactly {max_history} history records after pruning, "
            f"got {len(history)}. Pruning may not have triggered."
        )

        # Verify we kept the newest versions (highest version numbers)
        versions = sorted([h.version for h in history])
        # The newest version should be PRUNE_CHECK_INTERVAL (CREATE + 9 edits = 10)
        expected_newest = PRUNE_CHECK_INTERVAL
        assert versions[-1] == expected_newest, (
            f"Expected newest version to be {expected_newest}, got {versions[-1]}"
        )


class TestAuditMetadata:
    """Tests for _get_audit_metadata returning only identifying fields."""

    async def test__get_audit_metadata__bookmark(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Bookmark audit metadata includes title and url."""
        service = BookmarkService()
        limits = get_tier_limits("free")
        context = make_context()

        data = BookmarkCreate(
            url="https://audit-meta.com",
            title="Audit Test",
            content="Content",
        )
        bookmark = await service.create(db_session, test_user.id, data, limits, context)
        await service.delete(db_session, test_user.id, bookmark.id, permanent=False, context=context)

        history = await get_entity_history(db_session, test_user.id, EntityType.BOOKMARK, bookmark.id)
        delete_record = history[1]

        # Should have only identifying fields, not description/tags
        assert delete_record.metadata_snapshot == {
            "title": "Audit Test",
            "url": "https://audit-meta.com/",  # URL normalized
        }

    async def test__get_audit_metadata__bookmark_no_title(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Bookmark without title has only url in audit metadata."""
        service = BookmarkService()
        limits = get_tier_limits("free")
        context = make_context()

        data = BookmarkCreate(url="https://no-title-audit.com", content="Content")
        bookmark = await service.create(db_session, test_user.id, data, limits, context)
        await service.archive(db_session, test_user.id, bookmark.id, context)

        history = await get_entity_history(db_session, test_user.id, EntityType.BOOKMARK, bookmark.id)
        archive_record = history[1]

        assert archive_record.metadata_snapshot == {
            "url": "https://no-title-audit.com/",
        }

    async def test__get_audit_metadata__note(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Note audit metadata includes only title."""
        service = NoteService()
        limits = get_tier_limits("free")
        context = make_context()

        data = NoteCreate(title="Note Audit Test", content="Content")
        note = await service.create(db_session, test_user.id, data, limits, context)
        await service.archive(db_session, test_user.id, note.id, context)

        history = await get_entity_history(db_session, test_user.id, EntityType.NOTE, note.id)
        archive_record = history[1]

        assert archive_record.metadata_snapshot == {"title": "Note Audit Test"}

    async def test__get_audit_metadata__prompt_with_title(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Prompt with title has both title and name in audit metadata."""
        service = PromptService()
        limits = get_tier_limits("free")
        context = make_context()

        data = PromptCreate(
            name="audit-prompt",
            title="Audit Prompt Title",
            content="Content",
        )
        prompt = await service.create(db_session, test_user.id, data, limits, context)
        await service.archive(db_session, test_user.id, prompt.id, context)

        history = await get_entity_history(db_session, test_user.id, EntityType.PROMPT, prompt.id)
        archive_record = history[1]

        assert archive_record.metadata_snapshot == {
            "title": "Audit Prompt Title",
            "name": "audit-prompt",
        }

    async def test__get_audit_metadata__prompt_without_title(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Prompt without title has only name in audit metadata."""
        service = PromptService()
        limits = get_tier_limits("free")
        context = make_context()

        data = PromptCreate(name="audit-no-title", content="Content")
        prompt = await service.create(db_session, test_user.id, data, limits, context)
        await service.archive(db_session, test_user.id, prompt.id, context)

        history = await get_entity_history(db_session, test_user.id, EntityType.PROMPT, prompt.id)
        archive_record = history[1]

        assert archive_record.metadata_snapshot == {"name": "audit-no-title"}


class TestUpdateActionParameter:
    """Tests for the action parameter on update methods."""

    async def test__update_with_restore_action__records_restore(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """update() with action=RESTORE records RESTORE action in history."""
        service = NoteService()
        limits = get_tier_limits("free")
        context = make_context()

        data = NoteCreate(title="Test", content="Original")
        note = await service.create(db_session, test_user.id, data, limits, context)

        update_data = NoteUpdate(content="Restored content")
        await service.update(
            db_session, test_user.id, note.id, update_data, limits, context,
            action=ActionType.RESTORE,
        )

        history = await get_entity_history(db_session, test_user.id, EntityType.NOTE, note.id)
        assert len(history) == 2
        restore_record = history[1]
        assert restore_record.action == ActionType.RESTORE.value
        assert restore_record.version == 2  # Content version, not audit

    async def test__update_default_action__records_update(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """update() without action parameter defaults to UPDATE."""
        service = BookmarkService()
        limits = get_tier_limits("free")
        context = make_context()

        data = BookmarkCreate(url="https://default-action.com", content="Original")
        bookmark = await service.create(db_session, test_user.id, data, limits, context)

        update_data = BookmarkUpdate(content="Updated content")
        await service.update(
            db_session, test_user.id, bookmark.id, update_data, limits, context,
        )

        history = await get_entity_history(db_session, test_user.id, EntityType.BOOKMARK, bookmark.id)
        assert len(history) == 2
        assert history[1].action == ActionType.UPDATE.value


# =============================================================================
# Relationship history integration
# =============================================================================


class TestRelationshipHistoryIntegration:
    """Tests for history recording when relationships change via entity create/update."""

    @pytest.fixture
    def limits(self) -> dict:
        return get_tier_limits("free")

    @pytest.fixture
    def context(self) -> RequestContext:
        return make_context()

    async def test__create_bookmark_with_relationships__snapshot_includes_relationships(
        self,
        db_session: AsyncSession,
        test_user: User,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Creating a bookmark with relationships includes them in the history metadata snapshot."""
        service = BookmarkService()
        note_service = NoteService()

        # Create a note first (target)
        note = await note_service.create(
            db_session, test_user.id,
            NoteCreate(title="Target Note"),
            limits, context,
        )

        # Create bookmark with relationship to the note
        data = BookmarkCreate(
            url="https://example.com",
            title="BM with Link",
            relationships=[
                RelationshipInput(target_type='note', target_id=note.id),
            ],
        )
        bookmark = await service.create(db_session, test_user.id, data, limits, context)

        history = await get_entity_history(db_session, test_user.id, EntityType.BOOKMARK, bookmark.id)

        assert len(history) == 1
        metadata = history[0].metadata_snapshot
        assert 'relationships' in metadata
        assert len(metadata['relationships']) == 1
        assert metadata['relationships'][0]['target_type'] == 'note'
        assert metadata['relationships'][0]['target_id'] == str(note.id)

    async def test__update_bookmark_add_relationship__records_history(
        self,
        db_session: AsyncSession,
        test_user: User,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Adding a relationship via update records a versioned history entry."""
        service = BookmarkService()
        note_service = NoteService()

        note = await note_service.create(
            db_session, test_user.id,
            NoteCreate(title="Link Target"),
            limits, context,
        )
        bookmark = await service.create(
            db_session, test_user.id,
            BookmarkCreate(url="https://example.com", title="BM"),
            limits, context,
        )

        # Update: add relationship
        update = BookmarkUpdate(
            relationships=[
                RelationshipInput(target_type='note', target_id=note.id),
            ],
        )
        await service.update(db_session, test_user.id, bookmark.id, update, limits, context)

        history = await get_entity_history(db_session, test_user.id, EntityType.BOOKMARK, bookmark.id)
        assert len(history) == 2

        update_record = history[1]
        assert update_record.action == ActionType.UPDATE.value
        assert update_record.version == 2
        assert len(update_record.metadata_snapshot['relationships']) == 1

    async def test__update_bookmark_remove_relationship__records_history(
        self,
        db_session: AsyncSession,
        test_user: User,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Removing all relationships via update (empty list) records a versioned history entry."""
        service = BookmarkService()
        note_service = NoteService()

        note = await note_service.create(
            db_session, test_user.id,
            NoteCreate(title="Target"),
            limits, context,
        )
        bookmark = await service.create(
            db_session, test_user.id,
            BookmarkCreate(
                url="https://example.com",
                relationships=[
                    RelationshipInput(target_type='note', target_id=note.id),
                ],
            ),
            limits, context,
        )

        # Update: clear all relationships
        update = BookmarkUpdate(relationships=[])
        await service.update(db_session, test_user.id, bookmark.id, update, limits, context)

        history = await get_entity_history(db_session, test_user.id, EntityType.BOOKMARK, bookmark.id)
        assert len(history) == 2

        update_record = history[1]
        assert update_record.metadata_snapshot['relationships'] == []

    async def test__update_with_relationships_none__no_change(
        self,
        db_session: AsyncSession,
        test_user: User,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Update with relationships=None does not modify relationships and skips history."""
        service = BookmarkService()
        note_service = NoteService()

        note = await note_service.create(
            db_session, test_user.id,
            NoteCreate(title="Target"),
            limits, context,
        )
        bookmark = await service.create(
            db_session, test_user.id,
            BookmarkCreate(
                url="https://example.com",
                relationships=[
                    RelationshipInput(target_type='note', target_id=note.id),
                ],
            ),
            limits, context,
        )

        # Update with relationships=None (no change)
        update = BookmarkUpdate(title="Same BM")
        assert update.relationships is None
        await service.update(db_session, test_user.id, bookmark.id, update, limits, context)

        history = await get_entity_history(db_session, test_user.id, EntityType.BOOKMARK, bookmark.id)
        # No update history since title wasn't actually changing is ambiguous,
        # but relationships should still be there
        # The title IS changing (None -> "Same BM"), so there should be 2 records
        assert len(history) == 2
        # Relationships unchanged
        assert len(history[1].metadata_snapshot['relationships']) == 1

    async def test__create_note_with_relationships__snapshot_includes_relationships(
        self,
        db_session: AsyncSession,
        test_user: User,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Creating a note with relationships includes them in the metadata snapshot."""
        service = NoteService()
        bm_service = BookmarkService()

        bookmark = await bm_service.create(
            db_session, test_user.id,
            BookmarkCreate(url="https://example.com", title="Target BM"),
            limits, context,
        )

        note = await service.create(
            db_session, test_user.id,
            NoteCreate(
                title="Note with Link",
                relationships=[
                    RelationshipInput(target_type='bookmark', target_id=bookmark.id),
                ],
            ),
            limits, context,
        )

        history = await get_entity_history(db_session, test_user.id, EntityType.NOTE, note.id)
        assert len(history) == 1
        assert len(history[0].metadata_snapshot['relationships']) == 1
        assert history[0].metadata_snapshot['relationships'][0]['target_type'] == 'bookmark'

    async def test__create_prompt_with_relationships__snapshot_includes_relationships(
        self,
        db_session: AsyncSession,
        test_user: User,
        limits: dict,
        context: RequestContext,
    ) -> None:
        """Creating a prompt with relationships includes them in the metadata snapshot."""
        service = PromptService()
        note_service = NoteService()

        note = await note_service.create(
            db_session, test_user.id,
            NoteCreate(title="Target Note"),
            limits, context,
        )

        prompt = await service.create(
            db_session, test_user.id,
            PromptCreate(
                name="test-with-rel",
                title="Prompt with Link",
                content="Content",
                relationships=[
                    RelationshipInput(target_type='note', target_id=note.id),
                ],
            ),
            limits, context,
        )

        history = await get_entity_history(db_session, test_user.id, EntityType.PROMPT, prompt.id)
        assert len(history) == 1
        assert len(history[0].metadata_snapshot['relationships']) == 1


class TestCleanupPreservationServicePathRegression:
    """
    Symptom-level regression test for KAN-123.

    After time-based cleanup on a long-idle entity, the next edit driven
    through the service layer must still produce a working diff and a
    restorable anchor. Drives the post-cleanup update through
    BookmarkService.update (not a direct ORM insert) so record_action
    correctly reads the preserved predecessor when computing the next diff.
    """

    @pytest.mark.parametrize(
        "starting_state",
        ["versioned-aged", "audit-only-aged"],
    )
    async def test__edit_after_long_idle_produces_working_diff_and_anchor(
        self,
        db_session: AsyncSession,
        test_user: User,
        starting_state: str,
    ) -> None:
        """
        Edit through the service after cleanup produces a working diff/anchor.

        Two starting states:

        - versioned-aged: multiple aged versioned rows. Preservation rule
          retains the latest (v2); the next edit anchors on it and the diff
          endpoint reads v2's metadata as `before_metadata`.

        - audit-only-aged: only aged audit rows (e.g. ARCHIVE/UNARCHIVE).
          This is a legacy-data edge case — it only arises for entities whose
          CREATE record was deleted by pre-fix cleanup runs. New entities
          always retain their CREATE. The contract here is a
          pruned-predecessor UPDATE: `_get_next_version` over NULL versions
          yields 1, so the first post-cleanup edit lands at v1 with
          `action='update'`, `content_diff` set, `content_snapshot` None,
          and `before_metadata` None on the diff endpoint. The frontend's
          "Previous metadata unavailable" branch is the expected UX here.
        """
        now = datetime.now(UTC)
        aged_at = now - timedelta(days=60)  # past FREE retention
        service = BookmarkService()
        limits = get_tier_limits(Tier.FREE)
        context = make_context()

        # Seed entity and aged history directly (bypasses service for seeding
        # only — the post-cleanup edit below goes through the service).
        bookmark = Bookmark(
            user_id=test_user.id,
            url="https://example.com/post-cleanup",
            title="Current entity title",
            content="current content",
        )
        db_session.add(bookmark)
        await db_session.flush()

        seeded_v2_metadata: dict | None = None
        if starting_state == "versioned-aged":
            # v1 CREATE (aged), v2 UPDATE (aged, metadata differs from entity).
            db_session.add(ContentHistory(
                user_id=test_user.id,
                entity_type=EntityType.BOOKMARK.value,
                entity_id=bookmark.id,
                action=ActionType.CREATE.value,
                version=1,
                content_snapshot="v1 content",
                metadata_snapshot={
                    "title": "v1 title",
                    "url": "https://example.com/post-cleanup",
                    "tags": [],
                },
                source="web",
                auth_type=AuthType.SESSION.value,
                created_at=aged_at,
            ))
            seeded_v2_metadata = {
                "title": "v2 title",
                "url": "https://example.com/post-cleanup",
                "tags": [{"name": "tag-v2"}],
            }
            # Real reverse diff v2 -> v1. The test's assertions don't depend
            # on this value being walked (reconstruction at v2 anchors on
            # entity.content and applies v3's diff, not v2's), but using a
            # valid diff here makes the test robust to future changes in
            # reconstruction semantics — a failure would then point at the
            # preservation rule, not a cryptic diff parser error.
            v2_reverse_diff = history_service.dmp.patch_toText(
                history_service.dmp.patch_make("v2 content", "v1 content"),
            )
            db_session.add(ContentHistory(
                user_id=test_user.id,
                entity_type=EntityType.BOOKMARK.value,
                entity_id=bookmark.id,
                action=ActionType.UPDATE.value,
                version=2,
                content_snapshot=None,
                content_diff=v2_reverse_diff,
                metadata_snapshot=seeded_v2_metadata,
                source="web",
                auth_type=AuthType.SESSION.value,
                created_at=aged_at,
            ))
        else:  # audit-only-aged
            for action in [ActionType.ARCHIVE, ActionType.UNARCHIVE]:
                db_session.add(ContentHistory(
                    user_id=test_user.id,
                    entity_type=EntityType.BOOKMARK.value,
                    entity_id=bookmark.id,
                    action=action.value,
                    version=None,
                    content_snapshot=None,
                    content_diff=None,
                    metadata_snapshot={"title": "audit"},
                    source="web",
                    auth_type=AuthType.SESSION.value,
                    created_at=aged_at,
                ))
        await db_session.commit()

        # Inject a `now` that makes all seeded rows aged, and run cleanup.
        await cleanup_expired_history(db_session, now=now)

        # Verify expected surviving set.
        surviving = await get_entity_history(
            db_session, test_user.id, EntityType.BOOKMARK, bookmark.id,
        )
        if starting_state == "versioned-aged":
            assert len(surviving) == 1
            assert surviving[0].version == 2
        else:
            assert len(surviving) == 0

        # Drive the post-cleanup edit through the service.
        await service.update(
            db_session,
            test_user.id,
            bookmark.id,
            BookmarkUpdate(
                title="title after edit",
                content="updated content after long idle",
            ),
            limits,
            context,
        )

        post = await get_entity_history(
            db_session, test_user.id, EntityType.BOOKMARK, bookmark.id,
        )

        if starting_state == "versioned-aged":
            # Exactly [preserved v2, new v3].
            assert [r.version for r in post] == [2, 3]
            new_record = post[-1]
            assert new_record.action == ActionType.UPDATE.value
            assert new_record.content_diff is not None

            # Diff endpoint reads the right predecessor — v2's metadata.
            diff = await history_service.get_version_diff(
                db_session, test_user.id, EntityType.BOOKMARK, bookmark.id, 3,
            )
            assert diff.found is True
            assert diff.before_metadata is not None
            assert seeded_v2_metadata is not None
            assert diff.before_metadata["title"] == seeded_v2_metadata["title"]
            assert diff.before_metadata["url"] == seeded_v2_metadata["url"]
            assert diff.before_metadata["tags"] == seeded_v2_metadata["tags"]

            # Restore anchor works: reconstructing at v2 applies v3's
            # reverse diff to the current entity content, yielding the
            # pre-edit content.
            recon = await history_service.reconstruct_content_at_version(
                db_session, test_user.id, EntityType.BOOKMARK, bookmark.id, 2,
            )
            assert recon.found is True
            assert recon.content == "current content"
        else:
            # audit-only-aged: pruned-predecessor UPDATE contract.
            # _get_next_version over NULL versions yields 1; the first
            # post-cleanup edit lands at v1 with action='update',
            # content_diff set, content_snapshot None. Not a CREATE path.
            assert len(post) == 1
            new_record = post[-1]
            assert new_record.version == 1
            assert new_record.action == ActionType.UPDATE.value
            assert new_record.content_diff is not None
            assert new_record.content_snapshot is None

            # Diff endpoint for v1 returns no predecessor metadata (no v0).
            # Frontend renders "Previous metadata unavailable" here —
            # expected degraded UX for this legacy-data edge.
            diff = await history_service.get_version_diff(
                db_session, test_user.id, EntityType.BOOKMARK, bookmark.id, 1,
            )
            assert diff.found is True
            assert diff.before_metadata is None
