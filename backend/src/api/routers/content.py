"""
Router for unified content endpoints.

Provides endpoints for searching across all content types (bookmarks, notes)
with unified pagination and sorting.
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_async_session, get_current_user
from models.user import User
from schemas.content import ContentListResponse
from services import content_list_service
from services.content_service import search_all_content

router = APIRouter(prefix="/content", tags=["content"])


@router.get("/", response_model=ContentListResponse)
async def list_all_content(
    q: str | None = Query(
        default=None, description="Search query for title, description, content",
    ),
    tags: list[str] | None = Query(default=None, description="Filter by tags"),
    tag_match: Literal["all", "any"] = Query(
        default="all",
        description="Tag matching mode: 'all' requires all tags, 'any' requires any tag",
    ),
    sort_by: Literal[
        "created_at", "updated_at", "last_used_at", "title", "archived_at", "deleted_at",
    ] = Query(default="created_at", description="Field to sort by"),
    sort_order: Literal["asc", "desc"] = Query(default="desc", description="Sort direction"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    limit: int = Query(default=50, ge=1, le=100, description="Pagination limit"),
    view: Literal["active", "archived", "deleted"] = Query(
        default="active",
        description="View: 'active' (not deleted/archived), 'archived', or 'deleted'",
    ),
    list_id: int | None = Query(default=None, description="Filter by content list ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> ContentListResponse:
    """
    List all content (bookmarks and notes) with unified pagination.

    Returns a unified list of content items sorted by the specified field.
    Each item includes a `type` field indicating whether it's a "bookmark" or "note".

    Use this endpoint for:
    - Shared "All", "Archived", and "Trash" views (no list_id)
    - Custom content lists with mixed types (with list_id)

    When list_id is provided:
    - The list's filter_expression is applied
    - The list's content_types determines which entity types are returned
    """
    # If list_id provided, fetch the list and use its filter expression + content_types
    filter_expression = None
    content_types: list[str] | None = None
    if list_id is not None:
        content_list = await content_list_service.get_list(db, current_user.id, list_id)
        if content_list is None:
            raise HTTPException(status_code=404, detail="List not found")
        filter_expression = content_list.filter_expression
        content_types = content_list.content_types

    items, total = await search_all_content(
        db=db,
        user_id=current_user.id,
        query=q,
        tags=tags,
        tag_match=tag_match,
        sort_by=sort_by,
        sort_order=sort_order,
        offset=offset,
        limit=limit,
        view=view,
        filter_expression=filter_expression,
        content_types=content_types,
    )

    return ContentListResponse(
        items=items,
        total=total,
        offset=offset,
        limit=limit,
        has_more=(offset + len(items)) < total,
    )
