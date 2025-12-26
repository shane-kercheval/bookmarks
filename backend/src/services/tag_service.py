"""Service layer for tag operations."""
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.bookmark import Bookmark
from models.tag import Tag, bookmark_tags
from schemas.bookmark import validate_and_normalize_tags
from schemas.tag import TagCount


class TagNotFoundError(Exception):
    """Raised when a tag is not found."""

    def __init__(self, tag_name: str) -> None:
        self.tag_name = tag_name
        super().__init__(f"Tag '{tag_name}' not found")


class TagAlreadyExistsError(Exception):
    """Raised when trying to rename a tag to a name that already exists."""

    def __init__(self, tag_name: str) -> None:
        self.tag_name = tag_name
        super().__init__(f"Tag '{tag_name}' already exists")


async def get_or_create_tags(
    db: AsyncSession,
    user_id: int,
    tag_names: list[str],
) -> list[Tag]:
    """
    Get existing tags or create new ones.

    Args:
        db: Database session.
        user_id: User ID to scope tags.
        tag_names: List of tag names to get or create.

    Returns:
        List of Tag objects (existing or newly created).
    """
    if not tag_names:
        return []

    normalized = validate_and_normalize_tags(tag_names)
    if not normalized:
        return []

    # Fetch existing tags
    result = await db.execute(
        select(Tag).where(
            Tag.user_id == user_id,
            Tag.name.in_(normalized),
        ),
    )
    existing_tags = {tag.name: tag for tag in result.scalars()}

    # Create missing tags
    tags = []
    for name in normalized:
        if name in existing_tags:
            tags.append(existing_tags[name])
        else:
            new_tag = Tag(user_id=user_id, name=name)
            db.add(new_tag)
            tags.append(new_tag)

    await db.flush()
    return tags


async def get_user_tags_with_counts(
    db: AsyncSession,
    user_id: int,
    include_zero_count: bool = True,
) -> list[TagCount]:
    """
    Get all tags for a user with their usage counts.

    Counts only include active bookmarks (not deleted or archived).

    Args:
        db: Database session.
        user_id: User ID to scope tags.
        include_zero_count: If True, include tags with no active bookmarks.

    Returns:
        List of TagCount objects sorted by count desc, then name asc.
    """
    if include_zero_count:
        # LEFT JOIN to include tags with zero count.
        # Count only active bookmarks (not deleted, not currently archived).
        # Future-scheduled bookmarks (archived_at in future) count as active.
        # COUNT ignores NULLs, so tags with no bookmarks get count=0.
        result = await db.execute(
            select(
                Tag.name,
                func.count(bookmark_tags.c.bookmark_id).filter(
                    Bookmark.deleted_at.is_(None),
                    ~Bookmark.is_archived,
                ).label("count"),
            )
            .outerjoin(bookmark_tags, Tag.id == bookmark_tags.c.tag_id)
            .outerjoin(Bookmark, bookmark_tags.c.bookmark_id == Bookmark.id)
            .where(Tag.user_id == user_id)
            .group_by(Tag.id, Tag.name)
            .order_by(func.count().desc(), Tag.name.asc()),
        )
    else:
        # INNER JOIN to only include tags with active bookmarks
        result = await db.execute(
            select(
                Tag.name,
                func.count(bookmark_tags.c.bookmark_id).label("count"),
            )
            .join(bookmark_tags, Tag.id == bookmark_tags.c.tag_id)
            .join(Bookmark, bookmark_tags.c.bookmark_id == Bookmark.id)
            .where(
                Tag.user_id == user_id,
                Bookmark.deleted_at.is_(None),
                ~Bookmark.is_archived,
            )
            .group_by(Tag.id, Tag.name)
            .order_by(func.count().desc(), Tag.name.asc()),
        )

    return [TagCount(name=row.name, count=row.count) for row in result]


async def get_tag_by_name(
    db: AsyncSession,
    user_id: int,
    tag_name: str,
) -> Tag | None:
    """
    Get a tag by name for a user.

    Args:
        db: Database session.
        user_id: User ID to scope the tag.
        tag_name: Name of the tag to find.

    Returns:
        The Tag if found, None otherwise.
    """
    normalized = tag_name.lower().strip()
    result = await db.execute(
        select(Tag).where(
            Tag.user_id == user_id,
            Tag.name == normalized,
        ),
    )
    return result.scalar_one_or_none()


async def rename_tag(
    db: AsyncSession,
    user_id: int,
    old_name: str,
    new_name: str,
) -> Tag:
    """
    Rename a tag.

    Args:
        db: Database session.
        user_id: User ID to scope the tag.
        old_name: Current name of the tag.
        new_name: New name for the tag.

    Returns:
        The updated Tag object.

    Raises:
        TagNotFoundError: If the tag doesn't exist.
        TagAlreadyExistsError: If a tag with the new name already exists.
    """
    # Normalize names
    old_normalized = old_name.lower().strip()
    new_normalized = new_name.lower().strip()

    # Find the existing tag
    tag = await get_tag_by_name(db, user_id, old_normalized)
    if tag is None:
        raise TagNotFoundError(old_normalized)

    # If same name (case-insensitive), no-op
    if old_normalized == new_normalized:
        return tag

    # Check if new name already exists (early check for better error message)
    existing = await get_tag_by_name(db, user_id, new_normalized)
    if existing is not None:
        raise TagAlreadyExistsError(new_normalized)

    # Rename the tag
    tag.name = new_normalized
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        # Handle race condition: another request created the tag between check and flush
        if "uq_tags_user_id_name" in str(e):
            raise TagAlreadyExistsError(new_normalized) from e
        raise
    await db.refresh(tag)
    return tag


async def delete_tag(
    db: AsyncSession,
    user_id: int,
    tag_name: str,
) -> None:
    """
    Delete a tag. Junction table entries cascade automatically.

    Args:
        db: Database session.
        user_id: User ID to scope the tag.
        tag_name: Name of the tag to delete.

    Raises:
        TagNotFoundError: If the tag doesn't exist.
    """
    normalized = tag_name.lower().strip()
    tag = await get_tag_by_name(db, user_id, normalized)
    if tag is None:
        raise TagNotFoundError(normalized)

    await db.delete(tag)
    await db.flush()


async def update_bookmark_tags(
    db: AsyncSession,
    bookmark: Bookmark,
    tag_names: list[str],
) -> None:
    """
    Update a bookmark's tags using the junction table.

    Clears existing tags and sets new ones.

    Args:
        db: Database session.
        bookmark: The bookmark to update.
        tag_names: New list of tag names.
    """
    # Get or create the tag objects
    if tag_names:
        tag_objects = await get_or_create_tags(db, bookmark.user_id, tag_names)
    else:
        tag_objects = []

    # Update the relationship
    bookmark.tag_objects = tag_objects
    await db.flush()
