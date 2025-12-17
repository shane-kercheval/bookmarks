"""Bookmark list CRUD endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_async_session, get_current_user
from models.user import User
from schemas.bookmark_list import (
    BookmarkListCreate,
    BookmarkListResponse,
    BookmarkListUpdate,
)
from services import bookmark_list_service

router = APIRouter(prefix="/lists", tags=["lists"])


@router.post("/", response_model=BookmarkListResponse, status_code=201)
async def create_list(
    data: BookmarkListCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> BookmarkListResponse:
    """
    Create a new bookmark list.

    The list will be automatically added to the beginning of your tab order.
    """
    bookmark_list = await bookmark_list_service.create_list(db, current_user.id, data)
    return BookmarkListResponse.model_validate(bookmark_list)


@router.get("/", response_model=list[BookmarkListResponse])
async def get_lists(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> list[BookmarkListResponse]:
    """Get all bookmark lists for the current user."""
    lists = await bookmark_list_service.get_lists(db, current_user.id)
    return [BookmarkListResponse.model_validate(lst) for lst in lists]


@router.get("/{list_id}", response_model=BookmarkListResponse)
async def get_list(
    list_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> BookmarkListResponse:
    """Get a specific bookmark list by ID."""
    bookmark_list = await bookmark_list_service.get_list(db, current_user.id, list_id)
    if bookmark_list is None:
        raise HTTPException(status_code=404, detail="List not found")
    return BookmarkListResponse.model_validate(bookmark_list)


@router.patch("/{list_id}", response_model=BookmarkListResponse)
async def update_list(
    list_id: int,
    data: BookmarkListUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> BookmarkListResponse:
    """Update a bookmark list."""
    bookmark_list = await bookmark_list_service.update_list(
        db, current_user.id, list_id, data,
    )
    if bookmark_list is None:
        raise HTTPException(status_code=404, detail="List not found")
    return BookmarkListResponse.model_validate(bookmark_list)


@router.delete("/{list_id}", status_code=204)
async def delete_list(
    list_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> None:
    """
    Delete a bookmark list.

    The list will be automatically removed from your tab order.
    """
    deleted = await bookmark_list_service.delete_list(db, current_user.id, list_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="List not found")
