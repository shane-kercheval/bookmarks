"""Content list CRUD endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_async_session, get_current_user
from models.user import User
from schemas.content_list import (
    ContentListCreate,
    ContentListResponse,
    ContentListUpdate,
)
from services import content_list_service

router = APIRouter(prefix="/lists", tags=["lists"])


@router.post("/", response_model=ContentListResponse, status_code=201)
async def create_list(
    data: ContentListCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> ContentListResponse:
    """
    Create a new content list.

    The list will be automatically added to the beginning of your tab order.
    """
    content_list = await content_list_service.create_list(db, current_user.id, data)
    return ContentListResponse.model_validate(content_list)


@router.get("/", response_model=list[ContentListResponse])
async def get_lists(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> list[ContentListResponse]:
    """Get all content lists for the current user."""
    lists = await content_list_service.get_lists(db, current_user.id)
    return [ContentListResponse.model_validate(lst) for lst in lists]


@router.get("/{list_id}", response_model=ContentListResponse)
async def get_list(
    list_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> ContentListResponse:
    """Get a specific content list by ID."""
    content_list = await content_list_service.get_list(db, current_user.id, list_id)
    if content_list is None:
        raise HTTPException(status_code=404, detail="List not found")
    return ContentListResponse.model_validate(content_list)


@router.patch("/{list_id}", response_model=ContentListResponse)
async def update_list(
    list_id: int,
    data: ContentListUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> ContentListResponse:
    """Update a content list."""
    content_list = await content_list_service.update_list(
        db, current_user.id, list_id, data,
    )
    if content_list is None:
        raise HTTPException(status_code=404, detail="List not found")
    return ContentListResponse.model_validate(content_list)


@router.delete("/{list_id}", status_code=204)
async def delete_list(
    list_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> None:
    """
    Delete a content list.

    The list will be automatically removed from your tab order.
    """
    deleted = await content_list_service.delete_list(db, current_user.id, list_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="List not found")
