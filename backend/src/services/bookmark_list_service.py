"""Service layer for bookmark list operations."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.bookmark_list import BookmarkList
from schemas.bookmark_list import BookmarkListCreate, BookmarkListUpdate
from services.settings_service import add_list_to_tab_order, remove_list_from_tab_order


async def create_list(
    db: AsyncSession,
    user_id: int,
    data: BookmarkListCreate,
) -> BookmarkList:
    """
    Create a new bookmark list and add it to the user's tab_order.

    The new list is prepended to the beginning of tab_order.
    """
    bookmark_list = BookmarkList(
        user_id=user_id,
        name=data.name,
        filter_expression=data.filter_expression.model_dump(),
        default_sort_by=data.default_sort_by,
        default_sort_ascending=data.default_sort_ascending,
    )
    db.add(bookmark_list)
    await db.flush()
    await db.refresh(bookmark_list)

    # Add to tab_order (prepends to beginning)
    await add_list_to_tab_order(db, user_id, bookmark_list.id)

    return bookmark_list


async def get_lists(db: AsyncSession, user_id: int) -> list[BookmarkList]:
    """Get all bookmark lists for a user, ordered by creation date."""
    query = (
        select(BookmarkList)
        .where(BookmarkList.user_id == user_id)
        .order_by(BookmarkList.created_at)
    )
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_list(
    db: AsyncSession,
    user_id: int,
    list_id: int,
) -> BookmarkList | None:
    """Get a single bookmark list by ID, scoped to user."""
    query = select(BookmarkList).where(
        BookmarkList.id == list_id,
        BookmarkList.user_id == user_id,
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def update_list(
    db: AsyncSession,
    user_id: int,
    list_id: int,
    data: BookmarkListUpdate,
) -> BookmarkList | None:
    """Update a bookmark list. Returns None if not found."""
    bookmark_list = await get_list(db, user_id, list_id)
    if bookmark_list is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "filter_expression" and value is not None:
            # Convert Pydantic model to dict for JSONB storage
            setattr(bookmark_list, field, value)
        else:
            setattr(bookmark_list, field, value)

    # Explicitly update timestamp since TimestampMixin doesn't auto-update
    bookmark_list.updated_at = func.clock_timestamp()

    await db.flush()
    await db.refresh(bookmark_list)
    return bookmark_list


async def delete_list(
    db: AsyncSession,
    user_id: int,
    list_id: int,
) -> bool:
    """
    Delete a bookmark list and remove it from tab_order.

    Returns True if deleted, False if not found.
    """
    bookmark_list = await get_list(db, user_id, list_id)
    if bookmark_list is None:
        return False

    # Remove from tab_order first
    await remove_list_from_tab_order(db, user_id, list_id)

    await db.delete(bookmark_list)
    await db.flush()
    return True
