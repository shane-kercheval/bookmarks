"""Tag management endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_async_session, get_current_user
from models.user import User
from schemas.tag import TagListResponse, TagRenameRequest, TagResponse
from services.tag_service import (
    TagAlreadyExistsError,
    TagNotFoundError,
    delete_tag,
    get_user_tags_with_counts,
    rename_tag,
)

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("/", response_model=TagListResponse)
async def list_tags(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> TagListResponse:
    """
    Get all tags for the current user with their usage counts.

    Returns all tags (including those with zero active content) sorted by
    count (most used first), then alphabetically.

    Counts include active bookmarks and notes (not deleted or archived).
    """
    tags = await get_user_tags_with_counts(db, current_user.id, include_zero_count=True)
    return TagListResponse(tags=tags)


@router.patch("/{tag_name}", response_model=TagResponse)
async def rename_tag_endpoint(
    tag_name: str,
    rename_request: TagRenameRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> TagResponse:
    """
    Rename a tag.

    All bookmarks and notes using this tag will automatically reflect the new name.

    Returns 404 if the tag doesn't exist.
    Returns 409 if a tag with the new name already exists.
    """
    try:
        tag = await rename_tag(
            db, current_user.id, tag_name, rename_request.new_name,
        )
        return TagResponse.model_validate(tag)
    except TagNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except TagAlreadyExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from e


@router.delete("/{tag_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag_endpoint(
    tag_name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> None:
    """
    Delete a tag.

    This removes the tag from all bookmarks and notes, then deletes the tag itself.

    Returns 204 if successful, 404 if the tag doesn't exist.
    """
    try:
        await delete_tag(db, current_user.id, tag_name)
    except TagNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
