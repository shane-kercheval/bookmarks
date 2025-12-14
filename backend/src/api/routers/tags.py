"""Tag management endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_async_session, get_current_user
from models.bookmark import Bookmark
from models.user import User
from schemas.tag import TagCount, TagListResponse

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("/", response_model=TagListResponse)
async def list_tags(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> TagListResponse:
    """
    Get all unique tags used by the current user with their counts.

    Returns tags sorted by count (most used first), then alphabetically.
    """
    # Use unnest to expand the tags array, then group and count
    # This gives us each unique tag with its count across all bookmarks
    unnest_query = (
        select(
            func.unnest(Bookmark.tags).label("tag"),
        )
        .where(Bookmark.user_id == current_user.id)
        .subquery()
    )

    result = await db.execute(
        select(
            unnest_query.c.tag,
            func.count().label("count"),
        )
        .group_by(unnest_query.c.tag)
        .order_by(func.count().desc(), unnest_query.c.tag.asc()),
    )

    tags = [TagCount(name=row.tag, count=row.count) for row in result.all()]
    return TagListResponse(tags=tags)
