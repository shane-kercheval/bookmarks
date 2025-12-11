"""Service layer for bookmark CRUD operations."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.bookmark import Bookmark
from schemas.bookmark import BookmarkCreate, BookmarkUpdate


async def create_bookmark(
    db: AsyncSession,
    user_id: int,
    data: BookmarkCreate,
) -> Bookmark:
    """Create a new bookmark for a user."""
    bookmark = Bookmark(
        user_id=user_id,
        url=str(data.url),
        title=data.title,
        description=data.description,
        content=data.content,
        tags=data.tags,
    )
    db.add(bookmark)
    await db.commit()
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


async def get_bookmarks(
    db: AsyncSession,
    user_id: int,
    offset: int = 0,
    limit: int = 50,
) -> list[Bookmark]:
    """Get all bookmarks for a user with pagination."""
    result = await db.execute(
        select(Bookmark)
        .where(Bookmark.user_id == user_id)
        .order_by(Bookmark.created_at.desc())
        .offset(offset)
        .limit(limit),
    )
    return list(result.scalars().all())


async def update_bookmark(
    db: AsyncSession,
    user_id: int,
    bookmark_id: int,
    data: BookmarkUpdate,
) -> Bookmark | None:
    """Update a bookmark. Returns None if not found or wrong user."""
    bookmark = await get_bookmark(db, user_id, bookmark_id)
    if bookmark is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(bookmark, field, value)

    await db.commit()
    await db.refresh(bookmark)
    return bookmark


async def delete_bookmark(
    db: AsyncSession,
    user_id: int,
    bookmark_id: int,
) -> bool:
    """Delete a bookmark. Returns True if deleted, False if not found."""
    bookmark = await get_bookmark(db, user_id, bookmark_id)
    if bookmark is None:
        return False

    await db.delete(bookmark)
    await db.commit()
    return True
