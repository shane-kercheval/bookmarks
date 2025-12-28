"""Service layer for bookmark CRUD operations."""
import logging

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, selectinload

from models.bookmark import Bookmark
from models.tag import bookmark_tags
from schemas.bookmark import BookmarkCreate, BookmarkUpdate
from services.base_entity_service import BaseEntityService
from services.exceptions import InvalidStateError
from services.tag_service import get_or_create_tags, update_bookmark_tags

logger = logging.getLogger(__name__)


class DuplicateUrlError(Exception):
    """Raised when a bookmark with the same URL already exists for the user."""

    def __init__(self, url: str) -> None:
        self.url = url
        super().__init__(f"A bookmark with URL '{url}' already exists")


class ArchivedUrlExistsError(Exception):
    """Raised when trying to create a bookmark but URL exists as archived."""

    def __init__(self, url: str, existing_bookmark_id: int) -> None:
        self.url = url
        self.existing_bookmark_id = existing_bookmark_id
        super().__init__(f"A bookmark with URL '{url}' exists in archive")


class BookmarkService(BaseEntityService[Bookmark]):
    """
    Bookmark service with full CRUD operations.

    Extends BaseEntityService with bookmark-specific:
    - Text search fields (includes url, summary)
    - Sort columns (title falls back to url)
    - URL uniqueness checks in create/update/restore
    """

    model = Bookmark
    junction_table = bookmark_tags
    entity_name = "Bookmark"

    def _build_text_search_filter(self, pattern: str) -> list:
        """Build text search filter for bookmark fields."""
        return [
            or_(
                Bookmark.title.ilike(pattern),
                Bookmark.description.ilike(pattern),
                Bookmark.url.ilike(pattern),
                Bookmark.summary.ilike(pattern),
                Bookmark.content.ilike(pattern),
            ),
        ]

    def _get_sort_columns(self) -> dict[str, InstrumentedAttribute]:
        """Get sort columns with title falling back to URL."""
        return {
            "created_at": Bookmark.created_at,
            "updated_at": Bookmark.updated_at,
            "last_used_at": Bookmark.last_used_at,
            "title": func.coalesce(Bookmark.title, Bookmark.url),
            "archived_at": Bookmark.archived_at,
            "deleted_at": Bookmark.deleted_at,
        }

    async def _check_url_exists(
        self,
        db: AsyncSession,
        user_id: int,
        url: str,
    ) -> Bookmark | None:
        """Check if a URL exists for this user (excluding soft-deleted)."""
        result = await db.execute(
            select(Bookmark).where(
                Bookmark.user_id == user_id,
                Bookmark.url == url,
                Bookmark.deleted_at.is_(None),
            ),
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        db: AsyncSession,
        user_id: int,
        data: BookmarkCreate,
    ) -> Bookmark:
        """
        Create a new bookmark for a user.

        Args:
            db: Database session.
            user_id: User ID to create the bookmark for.
            data: Bookmark creation data.

        Returns:
            The created bookmark.

        Raises:
            DuplicateUrlError: If URL exists as an active bookmark.
            ArchivedUrlExistsError: If URL exists as an archived bookmark.
        """
        url_str = str(data.url)

        # Check if URL already exists for this user (non-deleted)
        existing = await self._check_url_exists(db, user_id, url_str)
        if existing:
            if existing.is_archived:
                raise ArchivedUrlExistsError(url_str, existing.id)
            raise DuplicateUrlError(url_str)

        # Get or create tags
        tag_objects = await get_or_create_tags(db, user_id, data.tags)
        bookmark = Bookmark(
            user_id=user_id,
            url=url_str,
            title=data.title,
            description=data.description,
            content=data.content,
            archived_at=data.archived_at,
        )
        bookmark.tag_objects = tag_objects
        db.add(bookmark)
        try:
            await db.flush()
        except IntegrityError as e:
            await db.rollback()
            if "uq_bookmark_user_url_active" in str(e):
                raise DuplicateUrlError(url_str) from e
            raise
        await db.refresh(bookmark)
        await db.refresh(bookmark, attribute_names=["tag_objects"])
        # Set last_used_at to match created_at for "never clicked" detection
        bookmark.last_used_at = bookmark.created_at
        await db.flush()
        return bookmark

    async def update(
        self,
        db: AsyncSession,
        user_id: int,
        bookmark_id: int,
        data: BookmarkUpdate,
    ) -> Bookmark | None:
        """
        Update a bookmark.

        Args:
            db: Database session.
            user_id: User ID to scope the bookmark.
            bookmark_id: ID of the bookmark to update.
            data: Update data.

        Returns:
            The updated bookmark, or None if not found.

        Raises:
            DuplicateUrlError: If the new URL already exists.
        """
        bookmark = await self.get(db, user_id, bookmark_id, include_archived=True)
        if bookmark is None:
            return None

        update_data = data.model_dump(exclude_unset=True)

        # Convert HttpUrl to string if URL is being updated
        if "url" in update_data and update_data["url"] is not None:
            update_data["url"] = str(update_data["url"])

        # Handle tag updates separately
        new_tags = update_data.pop("tags", None)

        for field, value in update_data.items():
            setattr(bookmark, field, value)

        if new_tags is not None:
            await update_bookmark_tags(db, bookmark, new_tags)

        bookmark.updated_at = func.clock_timestamp()

        try:
            await db.flush()
        except IntegrityError as e:
            await db.rollback()
            if "uq_bookmark_user_url_active" in str(e):
                raise DuplicateUrlError(str(update_data.get("url", ""))) from e
            raise
        await self._refresh_with_tags(db, bookmark)
        return bookmark

    async def restore(
        self,
        db: AsyncSession,
        user_id: int,
        entity_id: int,
    ) -> Bookmark | None:
        """
        Restore a soft-deleted bookmark.

        Overrides base to add URL uniqueness check.

        Args:
            db: Database session.
            user_id: User ID to scope the bookmark.
            entity_id: ID of the bookmark to restore.

        Returns:
            The restored bookmark, or None if not found.

        Raises:
            InvalidStateError: If the bookmark is not deleted.
            DuplicateUrlError: If an active bookmark with the same URL exists.
        """
        # Find the bookmark (must be deleted)
        result = await db.execute(
            select(Bookmark)
            .options(selectinload(Bookmark.tag_objects))
            .where(
                Bookmark.id == entity_id,
                Bookmark.user_id == user_id,
                Bookmark.deleted_at.is_not(None),
            ),
        )
        bookmark = result.scalar_one_or_none()

        if bookmark is None:
            non_deleted = await self.get(db, user_id, entity_id, include_archived=True)
            if non_deleted is not None:
                raise InvalidStateError("Bookmark is not deleted")
            return None

        # Check URL uniqueness before restore
        existing = await self._check_url_exists(db, user_id, bookmark.url)
        if existing and existing.id != entity_id:
            raise DuplicateUrlError(bookmark.url)

        bookmark.deleted_at = None
        bookmark.archived_at = None
        await db.flush()
        await self._refresh_with_tags(db, bookmark)
        return bookmark

