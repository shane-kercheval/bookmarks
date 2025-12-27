"""Service layer for unified content operations across bookmarks and notes."""
from typing import Literal

from sqlalchemy import Row, and_, exists, func, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from models.bookmark import Bookmark
from models.note import Note
from models.tag import Tag, bookmark_tags, note_tags
from schemas.bookmark import validate_and_normalize_tags
from schemas.content import ContentListItem
from services.utils import escape_ilike


def _build_bookmark_tag_filter(
    tags: list[str],
    tag_match: Literal["all", "any"],
    user_id: int,
) -> list:
    """Build tag filter clauses for bookmarks."""
    if not tags:
        return []

    if tag_match == "all":
        # Must have ALL specified tags
        conditions = []
        for tag_name in tags:
            subq = (
                select(bookmark_tags.c.bookmark_id)
                .join(Tag, bookmark_tags.c.tag_id == Tag.id)
                .where(
                    bookmark_tags.c.bookmark_id == Bookmark.id,
                    Tag.name == tag_name,
                    Tag.user_id == user_id,
                )
            )
            conditions.append(exists(subq))
        return conditions
    # Must have ANY of the specified tags
    subq = (
        select(bookmark_tags.c.bookmark_id)
        .join(Tag, bookmark_tags.c.tag_id == Tag.id)
        .where(
            bookmark_tags.c.bookmark_id == Bookmark.id,
            Tag.name.in_(tags),
            Tag.user_id == user_id,
        )
    )
    return [exists(subq)]


def _build_note_tag_filter(
    tags: list[str],
    tag_match: Literal["all", "any"],
    user_id: int,
) -> list:
    """Build tag filter clauses for notes."""
    if not tags:
        return []

    if tag_match == "all":
        # Must have ALL specified tags
        conditions = []
        for tag_name in tags:
            subq = (
                select(note_tags.c.note_id)
                .join(Tag, note_tags.c.tag_id == Tag.id)
                .where(
                    note_tags.c.note_id == Note.id,
                    Tag.name == tag_name,
                    Tag.user_id == user_id,
                )
            )
            conditions.append(exists(subq))
        return conditions
    # Must have ANY of the specified tags
    subq = (
        select(note_tags.c.note_id)
        .join(Tag, note_tags.c.tag_id == Tag.id)
        .where(
            note_tags.c.note_id == Note.id,
            Tag.name.in_(tags),
            Tag.user_id == user_id,
        )
    )
    return [exists(subq)]


async def _get_tags_for_items(
    db: AsyncSession,
    user_id: int,
    bookmark_ids: list[int],
    note_ids: list[int],
) -> dict[tuple[str, int], list[str]]:
    """
    Fetch tags for a list of bookmarks and notes.

    Returns a dict mapping (type, id) -> list of tag names.
    """
    result: dict[tuple[str, int], list[str]] = {}

    # Initialize empty lists for all items
    for bid in bookmark_ids:
        result[("bookmark", bid)] = []
    for nid in note_ids:
        result[("note", nid)] = []

    if bookmark_ids:
        # Fetch bookmark tags
        query = (
            select(bookmark_tags.c.bookmark_id, Tag.name)
            .join(Tag, bookmark_tags.c.tag_id == Tag.id)
            .where(
                bookmark_tags.c.bookmark_id.in_(bookmark_ids),
                Tag.user_id == user_id,
            )
        )
        rows = await db.execute(query)
        for bookmark_id, tag_name in rows:
            result[("bookmark", bookmark_id)].append(tag_name)

    if note_ids:
        # Fetch note tags
        query = (
            select(note_tags.c.note_id, Tag.name)
            .join(Tag, note_tags.c.tag_id == Tag.id)
            .where(
                note_tags.c.note_id.in_(note_ids),
                Tag.user_id == user_id,
            )
        )
        rows = await db.execute(query)
        for note_id, tag_name in rows:
            result[("note", note_id)].append(tag_name)

    return result


def _row_to_content_item(row: Row, tags: list[str]) -> ContentListItem:
    """Convert a database row to a ContentListItem."""
    return ContentListItem(
        type=row.type,
        id=row.id,
        title=row.title,
        description=row.description,
        tags=tags,
        created_at=row.created_at,
        updated_at=row.updated_at,
        last_used_at=row.last_used_at,
        deleted_at=row.deleted_at,
        archived_at=row.archived_at,
        url=row.url if row.type == "bookmark" else None,
        version=row.version if row.type == "note" else None,
    )


async def search_all_content(
    db: AsyncSession,
    user_id: int,
    query: str | None = None,
    tags: list[str] | None = None,
    tag_match: Literal["all", "any"] = "all",
    sort_by: Literal[
        "created_at", "updated_at", "last_used_at", "title", "archived_at", "deleted_at",
    ] = "created_at",
    sort_order: Literal["asc", "desc"] = "desc",
    offset: int = 0,
    limit: int = 50,
    view: Literal["active", "archived", "deleted"] = "active",
) -> tuple[list[ContentListItem], int]:
    """
    Search all content (bookmarks and notes) with unified pagination.

    Args:
        db: Database session.
        user_id: User ID to scope content.
        query: Text search across title, description, content.
        tags: Filter by tags (normalized to lowercase).
        tag_match: "all" (AND - must have all tags) or "any" (OR - has any tag).
        sort_by: Field to sort by.
        sort_order: Sort direction.
        offset: Pagination offset.
        limit: Pagination limit.
        view:
            Which content to show:
            - "active": Not deleted and not archived (default).
            - "archived": Archived but not deleted.
            - "deleted": Soft-deleted (includes deleted+archived).

    Returns:
        Tuple of (list of ContentListItems, total count).
    """
    # Normalize tags if provided
    normalized_tags = validate_and_normalize_tags(tags) if tags else None

    # Build bookmark subquery
    bookmark_filters = [Bookmark.user_id == user_id]

    # View filter for bookmarks
    if view == "active":
        bookmark_filters.extend([
            Bookmark.deleted_at.is_(None),
            ~Bookmark.is_archived,
        ])
    elif view == "archived":
        bookmark_filters.extend([
            Bookmark.deleted_at.is_(None),
            Bookmark.is_archived,
        ])
    elif view == "deleted":
        bookmark_filters.append(Bookmark.deleted_at.is_not(None))

    # Text search filter for bookmarks
    if query:
        escaped_query = escape_ilike(query)
        search_pattern = f"%{escaped_query}%"
        bookmark_filters.append(
            or_(
                Bookmark.title.ilike(search_pattern),
                Bookmark.description.ilike(search_pattern),
                Bookmark.url.ilike(search_pattern),
                Bookmark.content.ilike(search_pattern),
            ),
        )

    # Tag filter for bookmarks
    if normalized_tags:
        tag_filters = _build_bookmark_tag_filter(normalized_tags, tag_match, user_id)
        bookmark_filters.extend(tag_filters)

    bookmark_subq = (
        select(
            literal("bookmark").label("type"),
            Bookmark.id.label("id"),
            Bookmark.title.label("title"),
            Bookmark.description.label("description"),
            Bookmark.created_at.label("created_at"),
            Bookmark.updated_at.label("updated_at"),
            Bookmark.last_used_at.label("last_used_at"),
            Bookmark.deleted_at.label("deleted_at"),
            Bookmark.archived_at.label("archived_at"),
            Bookmark.url.label("url"),
            literal(None).label("version"),  # Notes have version, bookmarks don't
        )
        .where(and_(*bookmark_filters))
    )

    # Build note subquery
    note_filters = [Note.user_id == user_id]

    # View filter for notes
    if view == "active":
        note_filters.extend([
            Note.deleted_at.is_(None),
            ~Note.is_archived,
        ])
    elif view == "archived":
        note_filters.extend([
            Note.deleted_at.is_(None),
            Note.is_archived,
        ])
    elif view == "deleted":
        note_filters.append(Note.deleted_at.is_not(None))

    # Text search filter for notes
    if query:
        escaped_query = escape_ilike(query)
        search_pattern = f"%{escaped_query}%"
        note_filters.append(
            or_(
                Note.title.ilike(search_pattern),
                Note.description.ilike(search_pattern),
                Note.content.ilike(search_pattern),
            ),
        )

    # Tag filter for notes
    if normalized_tags:
        tag_filters = _build_note_tag_filter(normalized_tags, tag_match, user_id)
        note_filters.extend(tag_filters)

    note_subq = (
        select(
            literal("note").label("type"),
            Note.id.label("id"),
            Note.title.label("title"),
            Note.description.label("description"),
            Note.created_at.label("created_at"),
            Note.updated_at.label("updated_at"),
            Note.last_used_at.label("last_used_at"),
            Note.deleted_at.label("deleted_at"),
            Note.archived_at.label("archived_at"),
            literal(None).label("url"),  # Bookmarks have url, notes don't
            Note.version.label("version"),
        )
        .where(and_(*note_filters))
    )

    # Combine with UNION ALL
    combined = union_all(bookmark_subq, note_subq).subquery()

    # Get total count
    count_query = select(func.count()).select_from(combined)
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Build the final query with sorting and pagination
    # Map sort_by to the combined subquery column
    sort_column = getattr(combined.c, sort_by)
    sort_column = sort_column.desc() if sort_order == "desc" else sort_column.asc()

    # Add secondary sort by type and id for consistent ordering
    final_query = (
        select(combined)
        .order_by(sort_column, combined.c.type, combined.c.id)
        .offset(offset)
        .limit(limit)
    )

    result = await db.execute(final_query)
    rows = result.all()

    # Collect IDs for tag fetching
    bookmark_ids = [row.id for row in rows if row.type == "bookmark"]
    note_ids = [row.id for row in rows if row.type == "note"]

    # Fetch tags for all items
    tags_map = await _get_tags_for_items(db, user_id, bookmark_ids, note_ids)

    # Convert rows to ContentListItems
    items = [
        _row_to_content_item(row, tags_map[(row.type, row.id)])
        for row in rows
    ]

    return items, total
