"""Service layer for unified content operations across bookmarks and notes."""
from typing import Any, Literal

from sqlalchemy import Row, Table, and_, exists, func, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from models.bookmark import Bookmark
from models.note import Note
from models.tag import Tag, bookmark_tags, note_tags
from schemas.bookmark import validate_and_normalize_tags
from schemas.content import ContentListItem
from services.utils import build_tag_filter_from_expression, escape_ilike


def _build_tag_filter(
    tags: list[str],
    tag_match: Literal["all", "any"],
    user_id: int,
    junction_table: Table,
    entity_id_column: InstrumentedAttribute,
) -> list:
    """
    Build tag filter clauses for any entity type.

    Args:
        tags: List of tag names to filter by.
        tag_match: "all" requires all tags, "any" requires any tag.
        user_id: User ID for tag ownership.
        junction_table: The junction table (bookmark_tags or note_tags).
        entity_id_column: The entity ID column (Bookmark.id or Note.id).

    Returns:
        List of SQLAlchemy filter conditions.
    """
    if not tags:
        return []

    # Get the entity ID column name from junction table (e.g., bookmark_id, note_id)
    junction_columns = [c.name for c in junction_table.columns if c.name != "tag_id"]
    junction_entity_col = junction_table.c[junction_columns[0]]

    if tag_match == "all":
        # Must have ALL specified tags
        conditions = []
        for tag_name in tags:
            subq = (
                select(junction_entity_col)
                .join(Tag, junction_table.c.tag_id == Tag.id)
                .where(
                    junction_entity_col == entity_id_column,
                    Tag.name == tag_name,
                    Tag.user_id == user_id,
                )
            )
            conditions.append(exists(subq))
        return conditions

    # Must have ANY of the specified tags
    subq = (
        select(junction_entity_col)
        .join(Tag, junction_table.c.tag_id == Tag.id)
        .where(
            junction_entity_col == entity_id_column,
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
    filter_expression: dict[str, Any] | None = None,
    content_types: list[str] | None = None,
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
        filter_expression: Optional filter expression from a content list.
        content_types: Optional list of content types to include ("bookmark", "note").
            If None, includes both. Used by content lists to filter entity types.

    Returns:
        Tuple of (list of ContentListItems, total count).
    """
    # Normalize tags if provided
    normalized_tags = validate_and_normalize_tags(tags) if tags else None

    # Determine which content types to include
    include_bookmarks = content_types is None or "bookmark" in content_types
    include_notes = content_types is None or "note" in content_types

    # If no content types to include, return empty
    if not include_bookmarks and not include_notes:
        return [], 0

    subqueries = []

    # Build bookmark subquery if needed
    if include_bookmarks:
        bookmark_filters = _apply_entity_filters(
            filters=[Bookmark.user_id == user_id],
            model=Bookmark,
            junction_table=bookmark_tags,
            text_search_fields=[
                Bookmark.title, Bookmark.description, Bookmark.url,
                Bookmark.summary, Bookmark.content,
            ],
            view=view,
            query=query,
            normalized_tags=normalized_tags,
            tag_match=tag_match,
            user_id=user_id,
            filter_expression=filter_expression,
        )
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
                literal(None).label("version"),
            )
            .where(and_(*bookmark_filters))
        )
        subqueries.append(bookmark_subq)

    # Build note subquery if needed
    if include_notes:
        note_filters = _apply_entity_filters(
            filters=[Note.user_id == user_id],
            model=Note,
            junction_table=note_tags,
            text_search_fields=[Note.title, Note.description, Note.content],
            view=view,
            query=query,
            normalized_tags=normalized_tags,
            tag_match=tag_match,
            user_id=user_id,
            filter_expression=filter_expression,
        )
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
                literal(None).label("url"),
                Note.version.label("version"),
            )
            .where(and_(*note_filters))
        )
        subqueries.append(note_subq)

    # Combine subqueries
    if len(subqueries) == 1:
        combined = subqueries[0].subquery()
    else:
        combined = union_all(*subqueries).subquery()

    # Get total count
    count_query = select(func.count()).select_from(combined)
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Build the final query with sorting and pagination
    sort_column = getattr(combined.c, sort_by)
    sort_column = sort_column.desc() if sort_order == "desc" else sort_column.asc()

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


def _apply_entity_filters(
    filters: list,
    model: type,
    junction_table: Table,
    text_search_fields: list[InstrumentedAttribute],
    view: Literal["active", "archived", "deleted"],
    query: str | None,
    normalized_tags: list[str] | None,
    tag_match: Literal["all", "any"],
    user_id: int,
    filter_expression: dict[str, Any] | None,
) -> list:
    """
    Apply view, search, tag, and filter expression filters for any entity type.

    Args:
        filters: Base filter list to extend.
        model: The SQLAlchemy model class (Bookmark or Note).
        junction_table: The tag junction table (bookmark_tags or note_tags).
        text_search_fields: List of model columns to search (e.g., [Bookmark.title, ...]).
        view: Which entities to show (active/archived/deleted).
        query: Text search query.
        normalized_tags: List of normalized tag names to filter by.
        tag_match: Tag matching mode ("all" or "any").
        user_id: User ID for scoping.
        filter_expression: Optional filter expression from content list.

    Returns:
        Extended filter list.
    """
    # View filter
    if view == "active":
        filters.extend([model.deleted_at.is_(None), ~model.is_archived])
    elif view == "archived":
        filters.extend([model.deleted_at.is_(None), model.is_archived])
    elif view == "deleted":
        filters.append(model.deleted_at.is_not(None))

    # Text search filter
    if query:
        escaped_query = escape_ilike(query)
        search_pattern = f"%{escaped_query}%"
        filters.append(
            or_(*[field.ilike(search_pattern) for field in text_search_fields]),
        )

    # Tag filter from query params
    if normalized_tags:
        tag_filters = _build_tag_filter(
            normalized_tags, tag_match, user_id, junction_table, model.id,
        )
        filters.extend(tag_filters)

    # Filter expression from content list
    if filter_expression:
        expr_filters = build_tag_filter_from_expression(
            filter_expression, user_id, junction_table, model.id,
        )
        filters.extend(expr_filters)

    return filters
