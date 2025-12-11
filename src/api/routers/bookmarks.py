"""Bookmark CRUD endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_async_session, get_current_user
from models.user import User
from schemas.bookmark import BookmarkCreate, BookmarkResponse, BookmarkUpdate
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


@router.get("/", response_model=list[BookmarkResponse])
async def list_bookmarks(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> list[BookmarkResponse]:
    """List all bookmarks for the current user."""
    bookmarks = await bookmark_service.get_bookmarks(db, current_user.id, offset, limit)
    return [BookmarkResponse.model_validate(b) for b in bookmarks]


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
