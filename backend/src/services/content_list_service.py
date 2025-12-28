"""Service layer for content list operations."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.content_list import ContentList
from schemas.content_list import ContentListCreate, ContentListUpdate
from services.settings_service import add_list_to_tab_order, remove_list_from_tab_order


async def create_list(
    db: AsyncSession,
    user_id: int,
    data: ContentListCreate,
) -> ContentList:
    """
    Create a new content list and add it to the user's tab_order.

    The new list is prepended to the beginning of tab_order.
    """
    content_list = ContentList(
        user_id=user_id,
        name=data.name,
        content_types=data.content_types,
        filter_expression=data.filter_expression.model_dump(),
        default_sort_by=data.default_sort_by,
        default_sort_ascending=data.default_sort_ascending,
    )
    db.add(content_list)
    await db.flush()
    await db.refresh(content_list)

    # Add to tab_order (prepends to appropriate section based on content_types)
    await add_list_to_tab_order(db, user_id, content_list.id, data.content_types)

    return content_list


async def get_lists(db: AsyncSession, user_id: int) -> list[ContentList]:
    """Get all content lists for a user, ordered by creation date."""
    query = (
        select(ContentList)
        .where(ContentList.user_id == user_id)
        .order_by(ContentList.created_at)
    )
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_list(
    db: AsyncSession,
    user_id: int,
    list_id: int,
) -> ContentList | None:
    """Get a single content list by ID, scoped to user."""
    query = select(ContentList).where(
        ContentList.id == list_id,
        ContentList.user_id == user_id,
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def update_list(
    db: AsyncSession,
    user_id: int,
    list_id: int,
    data: ContentListUpdate,
) -> ContentList | None:
    """Update a content list. Returns None if not found."""
    content_list = await get_list(db, user_id, list_id)
    if content_list is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(content_list, field, value)

    # Explicitly update timestamp since TimestampMixin doesn't auto-update
    content_list.updated_at = func.clock_timestamp()

    await db.flush()
    await db.refresh(content_list)
    return content_list


async def delete_list(
    db: AsyncSession,
    user_id: int,
    list_id: int,
) -> bool:
    """
    Delete a content list and remove it from tab_order.

    Returns True if deleted, False if not found.
    """
    content_list = await get_list(db, user_id, list_id)
    if content_list is None:
        return False

    # Remove from tab_order first
    await remove_list_from_tab_order(db, user_id, list_id)

    await db.delete(content_list)
    await db.flush()
    return True
