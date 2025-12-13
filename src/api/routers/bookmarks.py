"""Bookmark CRUD endpoints."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_async_session, get_current_user
from models.user import User
from schemas.bookmark import (
    BookmarkCreate,
    BookmarkListResponse,
    BookmarkResponse,
    BookmarkUpdate,
)
from services import bookmark_service

router = APIRouter(prefix="/bookmarks", tags=["bookmarks"])


@router.post("/", response_model=BookmarkResponse, status_code=201)
async def create_bookmark(
    data: BookmarkCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> BookmarkResponse:
    """Create a new bookmark."""
    bookmark = await bookmark_service.create_bookmark(db, current_user.id, data)
    return BookmarkResponse.model_validate(bookmark)


@router.get("/", response_model=BookmarkListResponse)
async def list_bookmarks(
    q: str | None = Query(default=None, description="Search query (matches title, description, url, summary, content)"),  # noqa: E501
    tags: list[str] = Query(default=[], description="Filter by tags"),
    tag_match: Literal["all", "any"] = Query(default="all", description="Tag matching mode: 'all' (AND) or 'any' (OR)"),  # noqa: E501
    sort_by: Literal["created_at", "title"] = Query(default="created_at", description="Sort field"),  # noqa: E501
    sort_order: Literal["asc", "desc"] = Query(default="desc", description="Sort order"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    limit: int = Query(default=50, ge=1, le=100, description="Pagination limit"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> BookmarkListResponse:
    """
    List bookmarks for the current user with search, filtering, and sorting.

    - **q**: Text search across title, description, url, summary, and content (case-insensitive)
    - **tags**: Filter by one or more tags (normalized to lowercase)
    - **tag_match**: 'all' requires bookmark to have ALL specified tags, 'any' requires ANY tag
    - **sort_by**: Sort by created_at (default) or title
    - **sort_order**: Sort ascending or descending (default: desc)
    """
    try:
        bookmarks, total = await bookmark_service.search_bookmarks(
            db=db,
            user_id=current_user.id,
            query=q,
            tags=tags if tags else None,
            tag_match=tag_match,
            sort_by=sort_by,
            sort_order=sort_order,
            offset=offset,
            limit=limit,
        )
    except ValueError as e:
        # Tag validation errors from validate_and_normalize_tags
        raise HTTPException(status_code=422, detail=str(e))
    items = [BookmarkResponse.model_validate(b) for b in bookmarks]
    has_more = offset + len(items) < total
    return BookmarkListResponse(
        items=items,
        total=total,
        offset=offset,
        limit=limit,
        has_more=has_more,
    )


@router.get("/{bookmark_id}", response_model=BookmarkResponse)
async def get_bookmark(
    bookmark_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> BookmarkResponse:
    """Get a single bookmark by ID."""
    bookmark = await bookmark_service.get_bookmark(db, current_user.id, bookmark_id)
    if bookmark is None:
        raise HTTPException(status_code=404, detail="Bookmark not found")
    return BookmarkResponse.model_validate(bookmark)


@router.patch("/{bookmark_id}", response_model=BookmarkResponse)
async def update_bookmark(
    bookmark_id: int,
    data: BookmarkUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> BookmarkResponse:
    """Update a bookmark."""
    bookmark = await bookmark_service.update_bookmark(
        db, current_user.id, bookmark_id, data,
    )
    if bookmark is None:
        raise HTTPException(status_code=404, detail="Bookmark not found")
    return BookmarkResponse.model_validate(bookmark)


@router.delete("/{bookmark_id}", status_code=204)
async def delete_bookmark(
    bookmark_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> None:
    """Delete a bookmark."""
    deleted = await bookmark_service.delete_bookmark(db, current_user.id, bookmark_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Bookmark not found")
