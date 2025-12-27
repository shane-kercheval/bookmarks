"""Service layer for note CRUD operations."""
import logging
from typing import Literal

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.note import Note
from models.tag import Tag, note_tags
from schemas.bookmark import validate_and_normalize_tags
from schemas.note import NoteCreate, NoteUpdate
from services.exceptions import InvalidStateError
from services.tag_service import get_or_create_tags, update_note_tags
from services.utils import build_tag_filter_from_expression, escape_ilike

logger = logging.getLogger(__name__)


def build_note_filter_from_expression(filter_expression: dict, user_id: int) -> list:
    """
    Build SQLAlchemy filter clauses from a filter expression for notes.

    Wrapper around the generic build_tag_filter_from_expression.
    See that function for full documentation.

    Args:
        filter_expression: Dict with "groups" list and "group_operator".
        user_id: User ID to scope tags.

    Returns:
        List of SQLAlchemy filter clauses to apply.
    """
    return build_tag_filter_from_expression(
        filter_expression=filter_expression,
        user_id=user_id,
        junction_table=note_tags,
        entity_id_column=Note.id,
    )


async def create_note(
    db: AsyncSession,
    user_id: int,
    data: NoteCreate,
) -> Note:
    """
    Create a new note for a user.

    Args:
        db: Database session.
        user_id: User ID to create the note for.
        data: Note creation data.

    Returns:
        The created note.

    Note:
        Does not commit. Caller (session generator) handles commit at request end.
    """
    # Get or create tags (via junction table)
    tag_objects = await get_or_create_tags(db, user_id, data.tags)
    note = Note(
        user_id=user_id,
        title=data.title,
        description=data.description,
        content=data.content,
        archived_at=data.archived_at,
    )
    note.tag_objects = tag_objects
    db.add(note)
    await db.flush()
    await db.refresh(note)
    # Ensure tag_objects is loaded for the response
    await db.refresh(note, attribute_names=["tag_objects"])
    # Set last_used_at to exactly match created_at for "never viewed" detection
    note.last_used_at = note.created_at
    await db.flush()
    await db.refresh(note)
    await db.refresh(note, attribute_names=["tag_objects"])
    return note


async def get_note(
    db: AsyncSession,
    user_id: int,
    note_id: int,
    include_deleted: bool = False,
    include_archived: bool = False,
) -> Note | None:
    """
    Get a note by ID, scoped to user.

    Args:
        db: Database session.
        user_id: User ID to scope the note.
        note_id: ID of the note to retrieve.
        include_deleted: If True, include soft-deleted notes. Default False.
        include_archived: If True, include archived notes. Default False.

    Returns:
        The note if found and matches filters, None otherwise.
    """
    query = (
        select(Note)
        .options(selectinload(Note.tag_objects))
        .where(
            Note.id == note_id,
            Note.user_id == user_id,
        )
    )

    if not include_deleted:
        query = query.where(Note.deleted_at.is_(None))
    if not include_archived:
        query = query.where(~Note.is_archived)

    result = await db.execute(query)
    return result.scalar_one_or_none()


async def search_notes(  # noqa: PLR0912
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
    filter_expression: dict | None = None,
) -> tuple[list[Note], int]:
    """
    Search and filter notes for a user with pagination.

    Args:
        db: Database session.
        user_id: User ID to scope notes.
        query: Text search across title, description, content (ILIKE).
        tags: Filter by tags (normalized to lowercase).
        tag_match: "all" (AND - must have all tags) or "any" (OR - has any tag).
        sort_by: Field to sort by.
        sort_order: Sort direction.
        offset: Pagination offset.
        limit: Pagination limit.
        view:
            Which notes to show:
            - "active": Not deleted and not archived (default).
            - "archived": Archived but not deleted.
            - "deleted": Soft-deleted (includes deleted+archived).
        filter_expression:
            Optional filter expression from a ContentList.
            Format: {"groups": [{"tags": ["a", "b"]}, {"tags": ["c"]}], "group_operator": "OR"}
            Can be combined with `tags` parameter for additional filtering.

    Returns:
        Tuple of (list of notes, total count).
    """
    # Base query scoped to user with eager loading of tags
    base_query = (
        select(Note)
        .options(selectinload(Note.tag_objects))
        .where(Note.user_id == user_id)
    )

    # Apply view filter
    if view == "active":
        # Active = not deleted AND not archived (includes future-scheduled)
        base_query = base_query.where(
            Note.deleted_at.is_(None),
            ~Note.is_archived,
        )
    elif view == "archived":
        # Archived = not deleted AND is archived (archived_at in the past)
        base_query = base_query.where(
            Note.deleted_at.is_(None),
            Note.is_archived,
        )
    elif view == "deleted":
        # Deleted = has deleted_at (regardless of archived_at)
        base_query = base_query.where(Note.deleted_at.is_not(None))

    # Apply text search filter
    if query:
        escaped_query = escape_ilike(query)
        search_pattern = f"%{escaped_query}%"
        base_query = base_query.where(
            or_(
                Note.title.ilike(search_pattern),
                Note.description.ilike(search_pattern),
                Note.content.ilike(search_pattern),
            ),
        )

    # Apply filter expression (from ContentList)
    if filter_expression is not None:
        filter_clauses = build_note_filter_from_expression(filter_expression, user_id)
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
                        select(note_tags.c.note_id)
                        .join(Tag, note_tags.c.tag_id == Tag.id)
                        .where(
                            note_tags.c.note_id == Note.id,
                            Tag.name == tag_name,
                            Tag.user_id == user_id,
                        )
                    )
                    base_query = base_query.where(exists(subq))
            else:
                # Must have ANY of the specified tags (via junction table)
                subq = (
                    select(note_tags.c.note_id)
                    .join(Tag, note_tags.c.tag_id == Tag.id)
                    .where(
                        note_tags.c.note_id == Note.id,
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
    sort_columns = {
        "created_at": Note.created_at,
        "updated_at": Note.updated_at,
        "last_used_at": Note.last_used_at,
        "title": Note.title,  # Notes require title, so no COALESCE needed
        "archived_at": Note.archived_at,
        "deleted_at": Note.deleted_at,
    }
    sort_column = sort_columns[sort_by]

    if sort_order == "desc":
        base_query = base_query.order_by(
            sort_column.desc(),
            Note.created_at.desc(),
            Note.id.desc(),
        )
    else:
        base_query = base_query.order_by(
            sort_column.asc(),
            Note.created_at.asc(),
            Note.id.asc(),
        )

    # Apply pagination
    base_query = base_query.offset(offset).limit(limit)

    # Execute query
    result = await db.execute(base_query)
    notes = list(result.scalars().all())

    return notes, total


async def update_note(
    db: AsyncSession,
    user_id: int,
    note_id: int,
    data: NoteUpdate,
) -> Note | None:
    """
    Update a note. Returns None if not found or wrong user.

    Note: Does not commit. Caller (session generator) handles commit at request end.
    """
    # Include archived notes - users can edit from the archived view
    note = await get_note(db, user_id, note_id, include_archived=True)
    if note is None:
        return None

    update_data = data.model_dump(exclude_unset=True)

    # Handle tag updates separately via junction table
    new_tags = update_data.pop("tags", None)

    for field, value in update_data.items():
        setattr(note, field, value)

    # Update tags via junction table if provided
    if new_tags is not None:
        await update_note_tags(db, note, new_tags)

    # Explicitly set updated_at since we removed onupdate from TimestampMixin
    # (onupdate was removed to prevent non-content changes like track_note_usage
    # from updating updated_at)
    note.updated_at = func.clock_timestamp()

    await db.flush()
    await db.refresh(note)
    # Ensure tag_objects is loaded for the response
    await db.refresh(note, attribute_names=["tag_objects"])
    return note


async def delete_note(
    db: AsyncSession,
    user_id: int,
    note_id: int,
    permanent: bool = False,
) -> bool:
    """
    Delete a note (soft or permanent).

    Args:
        db: Database session.
        user_id: User ID to scope the note.
        note_id: ID of the note to delete.
        permanent:
            If False (default), soft delete by setting deleted_at timestamp.
            If True, permanently remove from database (for trash view).

    Returns:
        True if deleted/soft-deleted, False if not found.

    Note:
        Does not commit. Caller (session generator) handles commit at request end.
    """
    # For soft delete, we need to find the note even if it's archived
    # For permanent delete (from trash), we need to find deleted notes
    note = await get_note(
        db, user_id, note_id, include_deleted=permanent, include_archived=True,
    )
    if note is None:
        return False

    if permanent:
        await db.delete(note)
    else:
        note.deleted_at = func.now()
        await db.flush()

    return True


async def restore_note(
    db: AsyncSession,
    user_id: int,
    note_id: int,
) -> Note | None:
    """
    Restore a soft-deleted note to active state.

    Clears both deleted_at AND archived_at timestamps, returning the note
    to active state (not archived).

    Args:
        db: Database session.
        user_id: User ID to scope the note.
        note_id: ID of the note to restore.

    Returns:
        The restored note, or None if not found.

    Raises:
        InvalidStateError: If the note is not deleted.

    Note:
        Does not commit. Caller (session generator) handles commit at request end.
    """
    # Find the note (must be deleted)
    result = await db.execute(
        select(Note)
        .options(selectinload(Note.tag_objects))
        .where(
            Note.id == note_id,
            Note.user_id == user_id,
            Note.deleted_at.is_not(None),  # Must be deleted
        ),
    )
    note = result.scalar_one_or_none()

    if note is None:
        # Check if note exists but is not deleted
        non_deleted = await get_note(
            db, user_id, note_id, include_archived=True,
        )
        if non_deleted is not None:
            raise InvalidStateError("Note is not deleted")
        return None

    # Restore: clear both deleted_at and archived_at
    note.deleted_at = None
    note.archived_at = None
    await db.flush()
    await db.refresh(note)
    await db.refresh(note, attribute_names=["tag_objects"])
    return note


async def archive_note(
    db: AsyncSession,
    user_id: int,
    note_id: int,
) -> Note | None:
    """
    Archive a note by setting archived_at timestamp.

    This operation is idempotent - archiving an already-archived note
    returns success with the current state.

    Args:
        db: Database session.
        user_id: User ID to scope the note.
        note_id: ID of the note to archive.

    Returns:
        The archived note, or None if not found.

    Note:
        Does not commit. Caller (session generator) handles commit at request end.
    """
    # Find active note (not deleted, not archived) OR already archived
    note = await get_note(
        db, user_id, note_id, include_archived=True,
    )
    if note is None:
        return None

    # If not already archived, set to now (overrides any future scheduled date)
    if not note.is_archived:
        note.archived_at = func.now()
        await db.flush()
        await db.refresh(note)

    return note


async def unarchive_note(
    db: AsyncSession,
    user_id: int,
    note_id: int,
) -> Note | None:
    """
    Unarchive a note by clearing archived_at timestamp.

    Args:
        db: Database session.
        user_id: User ID to scope the note.
        note_id: ID of the note to unarchive.

    Returns:
        The unarchived note, or None if not found.

    Raises:
        InvalidStateError: If the note exists but is not archived.

    Note:
        Does not commit. Caller (session generator) handles commit at request end.
    """
    # Find archived note (must be currently archived, not deleted)
    # Note: This won't match notes with future archived_at (scheduled but not yet archived)
    result = await db.execute(
        select(Note)
        .options(selectinload(Note.tag_objects))
        .where(
            Note.id == note_id,
            Note.user_id == user_id,
            Note.deleted_at.is_(None),
            Note.is_archived,
        ),
    )
    note = result.scalar_one_or_none()

    if note is None:
        # Check if note exists but is not archived
        non_archived = await get_note(db, user_id, note_id)
        if non_archived is not None:
            raise InvalidStateError("Note is not archived")
        return None

    note.archived_at = None
    await db.flush()
    await db.refresh(note)
    await db.refresh(note, attribute_names=["tag_objects"])
    return note


async def track_note_usage(
    db: AsyncSession,
    user_id: int,
    note_id: int,
) -> bool:
    """
    Update last_used_at timestamp for a note.

    This operation works on active, archived, and deleted notes,
    as users can view notes from any view.

    Args:
        db: Database session.
        user_id: User ID to scope the note.
        note_id: ID of the note to track usage for.

    Returns:
        True if updated, False if note not found.

    Note:
        Does not commit. Caller (session generator) handles commit at request end.
    """
    # Get note regardless of state (include archived and deleted)
    note = await get_note(
        db, user_id, note_id, include_archived=True, include_deleted=True,
    )
    if note is None:
        return False

    # Use clock_timestamp() to get actual wall-clock time, not transaction start time.
    # This ensures different timestamps for multiple updates within the same transaction.
    note.last_used_at = func.clock_timestamp()
    await db.flush()
    return True
