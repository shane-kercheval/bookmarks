"""Service layer for bookmark CRUD operations."""
import logging
from typing import Literal

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.bookmark import Bookmark
from models.tag import Tag, bookmark_tags
from schemas.bookmark import BookmarkCreate, BookmarkUpdate, validate_and_normalize_tags
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


class InvalidStateError(Exception):
    """Raised when an operation is invalid for the bookmark's current state."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


def escape_ilike(value: str) -> str:
    r"""
    Escape special ILIKE characters for safe use in LIKE/ILIKE patterns.

    PostgreSQL LIKE/ILIKE treats these characters specially:
    - % matches any sequence of characters
    - _ matches any single character
    - \\ is the escape character

    This function escapes them so they match literally.
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def build_filter_from_expression(filter_expression: dict, user_id: int) -> list:
    """
    Build SQLAlchemy filter clauses from a filter expression.

    Converts:
        {"groups": [{"tags": ["a", "b"]}, {"tags": ["c"]}], "group_operator": "OR"}
    To:
        EXISTS subqueries checking tag relationships via junction table.

    Each group uses AND internally (bookmark must have ALL tags in the group).
    Groups are combined with OR.

    Args:
        filter_expression: Dict with "groups" list and "group_operator".
        user_id: User ID to scope tags.

    Returns:
        List of SQLAlchemy filter clauses to apply.
    """
    groups = filter_expression.get("groups", [])
    if not groups:
        return []

    # Build OR conditions for each group
    group_conditions = []
    for group in groups:
        tags = group.get("tags", [])
        if tags:
            # Build AND conditions for all tags in the group
            tag_conditions = []
            for tag_name in tags:
                # EXISTS subquery: check bookmark has this tag via junction table
                subq = (
                    select(bookmark_tags.c.bookmark_id)
                    .join(Tag, bookmark_tags.c.tag_id == Tag.id)
                    .where(
                        bookmark_tags.c.bookmark_id == Bookmark.id,
                        Tag.name == tag_name,
                        Tag.user_id == user_id,
                    )
                )
                tag_conditions.append(exists(subq))

            if len(tag_conditions) == 1:
                group_conditions.append(tag_conditions[0])
            else:
                group_conditions.append(and_(*tag_conditions))

    if not group_conditions:
        return []

    # Combine groups with OR
    if len(group_conditions) == 1:
        return [group_conditions[0]]
    return [or_(*group_conditions)]


async def _check_url_exists(
    db: AsyncSession,
    user_id: int,
    url: str,
) -> Bookmark | None:
    """
    Check if a URL exists for this user (excluding soft-deleted bookmarks).

    Returns the existing bookmark if found, None otherwise.
    """
    result = await db.execute(
        select(Bookmark).where(
            Bookmark.user_id == user_id,
            Bookmark.url == url,
            Bookmark.deleted_at.is_(None),  # Only non-deleted
        ),
    )
    return result.scalar_one_or_none()


async def create_bookmark(
    db: AsyncSession,
    user_id: int,
    data: BookmarkCreate,
) -> Bookmark:
    """
    Create a new bookmark for a user.

    Saves exactly what is provided - no automatic URL scraping. Callers who want
    metadata preview should use the /fetch-metadata endpoint first.

    Args:
        db: Database session.
        user_id: User ID to create the bookmark for.
        data: Bookmark creation data.

    Returns:
        The created bookmark.

    Raises:
        DuplicateUrlError: If URL exists as an active bookmark.
        ArchivedUrlExistsError: If URL exists as an archived bookmark.

    Note:
        Does not commit. Caller (session generator) handles commit at request end.
    """
    url_str = str(data.url)

    # Check if URL already exists for this user (non-deleted)
    existing = await _check_url_exists(db, user_id, url_str)
    if existing:
        if existing.archived_at is not None:
            # URL exists as archived - offer to restore
            raise ArchivedUrlExistsError(url_str, existing.id)
        # URL exists as active
        raise DuplicateUrlError(url_str)

    # Get or create tags (via junction table)
    tag_objects = await get_or_create_tags(db, user_id, data.tags)
    bookmark = Bookmark(
        user_id=user_id,
        url=url_str,
        title=data.title,
        description=data.description,
        content=data.content,
    )
    bookmark.tag_objects = tag_objects
    db.add(bookmark)
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        # Fallback for race condition: partial unique index constraint
        if "uq_bookmark_user_url_active" in str(e):
            raise DuplicateUrlError(url_str) from e
        raise
    await db.refresh(bookmark)
    # Ensure tag_objects is loaded for the response
    await db.refresh(bookmark, attribute_names=["tag_objects"])
    # Set last_used_at to exactly match created_at for "never clicked" detection
    bookmark.last_used_at = bookmark.created_at
    await db.flush()
    await db.refresh(bookmark)
    await db.refresh(bookmark, attribute_names=["tag_objects"])
    return bookmark


async def get_bookmark(
    db: AsyncSession,
    user_id: int,
    bookmark_id: int,
    include_deleted: bool = False,
    include_archived: bool = False,
) -> Bookmark | None:
    """
    Get a bookmark by ID, scoped to user.

    Args:
        db: Database session.
        user_id: User ID to scope the bookmark.
        bookmark_id: ID of the bookmark to retrieve.
        include_deleted: If True, include soft-deleted bookmarks. Default False.
        include_archived: If True, include archived bookmarks. Default False.

    Returns:
        The bookmark if found and matches filters, None otherwise.
    """
    query = (
        select(Bookmark)
        .options(selectinload(Bookmark.tag_objects))
        .where(
            Bookmark.id == bookmark_id,
            Bookmark.user_id == user_id,
        )
    )

    if not include_deleted:
        query = query.where(Bookmark.deleted_at.is_(None))
    if not include_archived:
        query = query.where(Bookmark.archived_at.is_(None))

    result = await db.execute(query)
    return result.scalar_one_or_none()


async def search_bookmarks(  # noqa: PLR0912
    db: AsyncSession,
    user_id: int,
    query: str | None = None,
    tags: list[str] | None = None,
    tag_match: Literal["all", "any"] = "all",
    sort_by: Literal["created_at", "updated_at", "last_used_at", "title"] = "created_at",
    sort_order: Literal["asc", "desc"] = "desc",
    offset: int = 0,
    limit: int = 50,
    view: Literal["active", "archived", "deleted"] = "active",
    filter_expression: dict | None = None,
) -> tuple[list[Bookmark], int]:
    """
    Search and filter bookmarks for a user with pagination.

    Args:
        db: Database session.
        user_id: User ID to scope bookmarks.
        query: Text search across title, description, url, summary, content (ILIKE).
        tags: Filter by tags (normalized to lowercase).
        tag_match: "all" (AND - must have all tags) or "any" (OR - has any tag).
        sort_by: Field to sort by.
        sort_order: Sort direction.
        offset: Pagination offset.
        limit: Pagination limit.
        view:
            Which bookmarks to show:
            - "active": Not deleted and not archived (default).
            - "archived": Archived but not deleted.
            - "deleted": Soft-deleted (includes deleted+archived).
        filter_expression:
            Optional filter expression from a BookmarkList.
            Format: {"groups": [{"tags": ["a", "b"]}, {"tags": ["c"]}], "group_operator": "OR"}
            Can be combined with `tags` parameter for additional filtering.

    Returns:
        Tuple of (list of bookmarks, total count).
    """
    # Base query scoped to user with eager loading of tags
    base_query = (
        select(Bookmark)
        .options(selectinload(Bookmark.tag_objects))
        .where(Bookmark.user_id == user_id)
    )

    # Apply view filter
    if view == "active":
        # Active = not deleted AND not archived
        base_query = base_query.where(
            Bookmark.deleted_at.is_(None),
            Bookmark.archived_at.is_(None),
        )
    elif view == "archived":
        # Archived = not deleted AND is archived
        base_query = base_query.where(
            Bookmark.deleted_at.is_(None),
            Bookmark.archived_at.is_not(None),
        )
    elif view == "deleted":
        # Deleted = has deleted_at (regardless of archived_at)
        base_query = base_query.where(Bookmark.deleted_at.is_not(None))

    # Apply text search filter
    if query:
        escaped_query = escape_ilike(query)
        search_pattern = f"%{escaped_query}%"
        base_query = base_query.where(
            or_(
                Bookmark.title.ilike(search_pattern),
                Bookmark.description.ilike(search_pattern),
                Bookmark.url.ilike(search_pattern),
                Bookmark.summary.ilike(search_pattern),
                Bookmark.content.ilike(search_pattern),
            ),
        )

    # Apply filter expression (from BookmarkList)
    if filter_expression is not None:
        filter_clauses = build_filter_from_expression(filter_expression, user_id)
        for clause in filter_clauses:
            base_query = base_query.where(clause)

    # Apply tag filter (can be combined with filter_expression for additional filtering)
    if tags:
        # Normalize tags to lowercase for consistent matching
        normalized_tags = validate_and_normalize_tags(tags)
        if normalized_tags:
            if tag_match == "all":
                # Must have ALL specified tags (via junction table)
                for tag_name in normalized_tags:
                    subq = (
                        select(bookmark_tags.c.bookmark_id)
                        .join(Tag, bookmark_tags.c.tag_id == Tag.id)
                        .where(
                            bookmark_tags.c.bookmark_id == Bookmark.id,
                            Tag.name == tag_name,
                            Tag.user_id == user_id,
                        )
                    )
                    base_query = base_query.where(exists(subq))
            else:
                # Must have ANY of the specified tags (via junction table)
                subq = (
                    select(bookmark_tags.c.bookmark_id)
                    .join(Tag, bookmark_tags.c.tag_id == Tag.id)
                    .where(
                        bookmark_tags.c.bookmark_id == Bookmark.id,
                        Tag.name.in_(normalized_tags),
                        Tag.user_id == user_id,
                    )
                )
                base_query = base_query.where(exists(subq))

    # Get total count before pagination
    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply sorting with tiebreakers (created_at, then id for deterministic ordering)
    # For title sorting, fall back to URL when title is NULL
    sort_columns = {
        "created_at": Bookmark.created_at,
        "updated_at": Bookmark.updated_at,
        "last_used_at": Bookmark.last_used_at,
        "title": func.coalesce(Bookmark.title, Bookmark.url),
    }
    sort_column = sort_columns[sort_by]

    if sort_order == "desc":
        base_query = base_query.order_by(
            sort_column.desc(),
            Bookmark.created_at.desc(),
            Bookmark.id.desc(),
        )
    else:
        base_query = base_query.order_by(
            sort_column.asc(),
            Bookmark.created_at.asc(),
            Bookmark.id.asc(),
        )

    # Apply pagination
    base_query = base_query.offset(offset).limit(limit)

    # Execute query
    result = await db.execute(base_query)
    bookmarks = list(result.scalars().all())

    return bookmarks, total


async def update_bookmark(
    db: AsyncSession,
    user_id: int,
    bookmark_id: int,
    data: BookmarkUpdate,
) -> Bookmark | None:
    """
    Update a bookmark. Returns None if not found or wrong user.

    Note: Does not commit. Caller (session generator) handles commit at request end.

    Raises:
        DuplicateUrlError: If the new URL already exists for this user.
    """
    bookmark = await get_bookmark(db, user_id, bookmark_id)
    if bookmark is None:
        return None

    update_data = data.model_dump(exclude_unset=True)

    # Convert HttpUrl to string if URL is being updated
    if "url" in update_data and update_data["url"] is not None:
        update_data["url"] = str(update_data["url"])

    # Handle tag updates separately via junction table
    new_tags = update_data.pop("tags", None)

    for field, value in update_data.items():
        setattr(bookmark, field, value)

    # Update tags via junction table if provided
    if new_tags is not None:
        await update_bookmark_tags(db, bookmark, new_tags)

    # Explicitly set updated_at since we removed onupdate from TimestampMixin
    # (onupdate was removed to prevent non-content changes like track_bookmark_usage
    # from updating updated_at)
    bookmark.updated_at = func.clock_timestamp()

    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        if "uq_bookmark_user_url_active" in str(e):
            raise DuplicateUrlError(str(update_data.get("url", ""))) from e
        raise
    await db.refresh(bookmark)
    # Ensure tag_objects is loaded for the response
    await db.refresh(bookmark, attribute_names=["tag_objects"])
    return bookmark


async def delete_bookmark(
    db: AsyncSession,
    user_id: int,
    bookmark_id: int,
    permanent: bool = False,
) -> bool:
    """
    Delete a bookmark (soft or permanent).

    Args:
        db: Database session.
        user_id: User ID to scope the bookmark.
        bookmark_id: ID of the bookmark to delete.
        permanent:
            If False (default), soft delete by setting deleted_at timestamp.
            If True, permanently remove from database (for trash view).

    Returns:
        True if deleted/soft-deleted, False if not found.

    Note:
        Does not commit. Caller (session generator) handles commit at request end.
    """
    # For soft delete, we need to find the bookmark even if it's archived
    # For permanent delete (from trash), we need to find deleted bookmarks
    bookmark = await get_bookmark(
        db, user_id, bookmark_id, include_deleted=permanent, include_archived=True,
    )
    if bookmark is None:
        return False

    if permanent:
        await db.delete(bookmark)
    else:
        bookmark.deleted_at = func.now()
        await db.flush()

    return True


async def restore_bookmark(
    db: AsyncSession,
    user_id: int,
    bookmark_id: int,
) -> Bookmark | None:
    """
    Restore a soft-deleted bookmark to active state.

    Clears both deleted_at AND archived_at timestamps, returning the bookmark
    to active state (not archived).

    Args:
        db: Database session.
        user_id: User ID to scope the bookmark.
        bookmark_id: ID of the bookmark to restore.

    Returns:
        The restored bookmark, or None if not found.

    Raises:
        InvalidStateError: If the bookmark is not deleted.
        DuplicateUrlError: If an active bookmark with the same URL already exists.

    Note:
        Does not commit. Caller (session generator) handles commit at request end.
    """
    # Find the bookmark (must be deleted)
    result = await db.execute(
        select(Bookmark).where(
            Bookmark.id == bookmark_id,
            Bookmark.user_id == user_id,
            Bookmark.deleted_at.is_not(None),  # Must be deleted
        ),
    )
    bookmark = result.scalar_one_or_none()

    if bookmark is None:
        # Check if bookmark exists but is not deleted
        non_deleted = await get_bookmark(
            db, user_id, bookmark_id, include_archived=True,
        )
        if non_deleted is not None:
            raise InvalidStateError("Bookmark is not deleted")
        return None

    # Check if URL already exists as active or archived bookmark
    existing = await _check_url_exists(db, user_id, bookmark.url)
    if existing and existing.id != bookmark_id:
        raise DuplicateUrlError(bookmark.url)

    # Restore: clear both deleted_at and archived_at
    bookmark.deleted_at = None
    bookmark.archived_at = None
    await db.flush()
    await db.refresh(bookmark)
    return bookmark


async def archive_bookmark(
    db: AsyncSession,
    user_id: int,
    bookmark_id: int,
) -> Bookmark | None:
    """
    Archive a bookmark by setting archived_at timestamp.

    This operation is idempotent - archiving an already-archived bookmark
    returns success with the current state.

    Args:
        db: Database session.
        user_id: User ID to scope the bookmark.
        bookmark_id: ID of the bookmark to archive.

    Returns:
        The archived bookmark, or None if not found.

    Note:
        Does not commit. Caller (session generator) handles commit at request end.
    """
    # Find active bookmark (not deleted, not archived) OR already archived
    bookmark = await get_bookmark(
        db, user_id, bookmark_id, include_archived=True,
    )
    if bookmark is None:
        return None

    # Idempotent: if already archived, just return it
    if bookmark.archived_at is None:
        bookmark.archived_at = func.now()
        await db.flush()
        await db.refresh(bookmark)

    return bookmark


async def unarchive_bookmark(
    db: AsyncSession,
    user_id: int,
    bookmark_id: int,
) -> Bookmark | None:
    """
    Unarchive a bookmark by clearing archived_at timestamp.

    Args:
        db: Database session.
        user_id: User ID to scope the bookmark.
        bookmark_id: ID of the bookmark to unarchive.

    Returns:
        The unarchived bookmark, or None if not found.

    Raises:
        InvalidStateError: If the bookmark exists but is not archived.

    Note:
        Does not commit. Caller (session generator) handles commit at request end.
    """
    # Find archived bookmark (must be archived, not deleted)
    result = await db.execute(
        select(Bookmark).where(
            Bookmark.id == bookmark_id,
            Bookmark.user_id == user_id,
            Bookmark.deleted_at.is_(None),
            Bookmark.archived_at.is_not(None),
        ),
    )
    bookmark = result.scalar_one_or_none()

    if bookmark is None:
        # Check if bookmark exists but is not archived
        non_archived = await get_bookmark(db, user_id, bookmark_id)
        if non_archived is not None:
            raise InvalidStateError("Bookmark is not archived")
        return None

    bookmark.archived_at = None
    await db.flush()
    await db.refresh(bookmark)
    return bookmark


async def track_bookmark_usage(
    db: AsyncSession,
    user_id: int,
    bookmark_id: int,
) -> bool:
    """
    Update last_used_at timestamp for a bookmark.

    This operation works on active, archived, and deleted bookmarks,
    as users can click links from any view.

    Args:
        db: Database session.
        user_id: User ID to scope the bookmark.
        bookmark_id: ID of the bookmark to track usage for.

    Returns:
        True if updated, False if bookmark not found.

    Note:
        Does not commit. Caller (session generator) handles commit at request end.
    """
    # Get bookmark regardless of state (include archived and deleted)
    bookmark = await get_bookmark(
        db, user_id, bookmark_id, include_archived=True, include_deleted=True,
    )
    if bookmark is None:
        return False

    # Use clock_timestamp() to get actual wall-clock time, not transaction start time.
    # This ensures different timestamps for multiple updates within the same transaction.
    bookmark.last_used_at = func.clock_timestamp()
    await db.flush()
    return True
