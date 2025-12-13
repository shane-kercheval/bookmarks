"""Service layer for bookmark CRUD operations."""
import logging
from typing import Literal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.bookmark import Bookmark
from schemas.bookmark import BookmarkCreate, BookmarkUpdate, validate_and_normalize_tags
from services.url_scraper import extract_content, extract_metadata, fetch_url

logger = logging.getLogger(__name__)


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


async def create_bookmark(
    db: AsyncSession,
    user_id: int,
    data: BookmarkCreate,
) -> Bookmark:
    """
    Create a new bookmark for a user with automatic URL scraping.

    Flow:
    1. Fetch URL for metadata unless user provided both title AND description
    2. Extract title/description from HTML (user values take precedence)
    3. If user didn't provide content, extract it from HTML
    4. Store content only if store_content=True
    5. Return the created bookmark

    Scraping is best-effort - failures don't block bookmark creation.

    Note: Does not commit. Caller (session generator) handles commit at request end.
    """
    url_str = str(data.url)
    title = data.title
    description = data.description
    content = data.content

    # Determine if we need to fetch for metadata
    needs_metadata = title is None or description is None
    needs_content = content is None

    # Only fetch if we need metadata or content
    if needs_metadata or needs_content:
        fetch_result = await fetch_url(url_str)

        if fetch_result.html is not None:
            # Extract metadata if needed
            if needs_metadata:
                metadata = extract_metadata(fetch_result.html)
                if title is None:
                    title = metadata.title
                if description is None:
                    description = metadata.description

            # Extract content if user didn't provide it
            if needs_content:
                extracted_content = extract_content(fetch_result.html)
                if data.store_content:
                    content = extracted_content
        elif fetch_result.error:
            logger.warning(
                "Failed to fetch URL %s: %s",
                url_str,
                fetch_result.error,
            )

    bookmark = Bookmark(
        user_id=user_id,
        url=url_str,
        title=title,
        description=description,
        content=content,
        tags=data.tags,
    )
    db.add(bookmark)
    await db.flush()
    await db.refresh(bookmark)
    return bookmark


async def get_bookmark(
    db: AsyncSession,
    user_id: int,
    bookmark_id: int,
) -> Bookmark | None:
    """Get a bookmark by ID, scoped to user. Returns None if not found or wrong user."""
    result = await db.execute(
        select(Bookmark).where(
            Bookmark.id == bookmark_id,
            Bookmark.user_id == user_id,
        ),
    )
    return result.scalar_one_or_none()


async def search_bookmarks(
    db: AsyncSession,
    user_id: int,
    query: str | None = None,
    tags: list[str] | None = None,
    tag_match: Literal["all", "any"] = "all",
    sort_by: Literal["created_at", "title"] = "created_at",
    sort_order: Literal["asc", "desc"] = "desc",
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[Bookmark], int]:
    """
    Search and filter bookmarks for a user with pagination.

    Args:
        db: Database session
        user_id: User ID to scope bookmarks
        query: Text search across title, description, url, summary, content (ILIKE)
        tags: Filter by tags (normalized to lowercase)
        tag_match: "all" (AND - must have all tags) or "any" (OR - has any tag)
        sort_by: Field to sort by
        sort_order: Sort direction
        offset: Pagination offset
        limit: Pagination limit

    Returns:
        Tuple of (list of bookmarks, total count)
    """
    # Base query scoped to user
    base_query = select(Bookmark).where(Bookmark.user_id == user_id)

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

    # Apply tag filter
    if tags:
        # Normalize tags to lowercase for consistent matching
        normalized_tags = validate_and_normalize_tags(tags)
        if normalized_tags:
            if tag_match == "all":
                # Must have ALL specified tags (PostgreSQL @> operator)
                base_query = base_query.where(Bookmark.tags.contains(normalized_tags))
            else:
                # Must have ANY of the specified tags (PostgreSQL && operator)
                base_query = base_query.where(Bookmark.tags.overlap(normalized_tags))

    # Get total count before pagination
    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply sorting (with secondary sort by id for deterministic ordering)
    sort_column = Bookmark.created_at if sort_by == "created_at" else Bookmark.title
    if sort_order == "desc":
        base_query = base_query.order_by(sort_column.desc(), Bookmark.id.desc())
    else:
        base_query = base_query.order_by(sort_column.asc(), Bookmark.id.asc())

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
    """
    bookmark = await get_bookmark(db, user_id, bookmark_id)
    if bookmark is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(bookmark, field, value)

    await db.flush()
    await db.refresh(bookmark)
    return bookmark


async def delete_bookmark(
    db: AsyncSession,
    user_id: int,
    bookmark_id: int,
) -> bool:
    """
    Delete a bookmark. Returns True if deleted, False if not found.

    Note: Does not commit. Caller (session generator) handles commit at request end.
    """
    bookmark = await get_bookmark(db, user_id, bookmark_id)
    if bookmark is None:
        return False

    await db.delete(bookmark)
    return True
