"""Bookmark CRUD endpoints."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import (
    get_async_session,
    get_current_user,
    get_current_user_auth0_only,
)
from models.user import User
from schemas.bookmark import (
    BookmarkCreate,
    BookmarkListItem,
    BookmarkListResponse,
    BookmarkResponse,
    BookmarkUpdate,
    MetadataPreviewResponse,
)
from services.bookmark_service import (
    ArchivedUrlExistsError,
    BookmarkService,
    DuplicateUrlError,
)
from services import content_list_service
from services.exceptions import InvalidStateError
from services.url_scraper import scrape_url

router = APIRouter(prefix="/bookmarks", tags=["bookmarks"])

bookmark_service = BookmarkService()


@router.get("/fetch-metadata", response_model=MetadataPreviewResponse)
async def fetch_metadata(
    url: HttpUrl = Query(..., description="URL to fetch metadata from"),
    include_content: bool = Query(default=False, description="Also extract page content"),
    _current_user: User = Depends(get_current_user_auth0_only),
) -> MetadataPreviewResponse:
    """
    Fetch metadata from a URL without saving a bookmark.

    **Authentication: Auth0 only (PATs not accepted - returns 403)**

    Use this endpoint to preview title and description before creating a bookmark.
    The frontend can call this when the user enters a URL, then populate the form
    with the extracted values.

    Set include_content=true to also extract the main page content (useful for
    previewing before save).

    Rate limited: 30 requests per minute (Auth0), 250 per day (sensitive operation).
    """
    url_str = str(url)
    scraped = await scrape_url(url_str)

    if scraped.error:
        return MetadataPreviewResponse(
            url=url_str,
            final_url=scraped.final_url or url_str,
            title=None,
            description=None,
            error=scraped.error,
        )

    return MetadataPreviewResponse(
        url=url_str,
        final_url=scraped.final_url or url_str,
        title=scraped.metadata.title if scraped.metadata else None,
        description=scraped.metadata.description if scraped.metadata else None,
        content=scraped.text if include_content else None,
    )


@router.post("/", response_model=BookmarkResponse, status_code=201)
async def create_bookmark(
    data: BookmarkCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> BookmarkResponse:
    """Create a new bookmark."""
    try:
        bookmark = await bookmark_service.create(db, current_user.id, data)
    except ArchivedUrlExistsError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(e),
                "error_code": "ARCHIVED_URL_EXISTS",
                "existing_bookmark_id": e.existing_bookmark_id,
            },
        )
    except DuplicateUrlError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(e),
                "error_code": "ACTIVE_URL_EXISTS",
            },
        )
    return BookmarkResponse.model_validate(bookmark)


@router.get("/", response_model=BookmarkListResponse)
async def list_bookmarks(
    q: str | None = Query(default=None, description="Search query (matches title, description, url, summary, content)"),  # noqa: E501
    tags: list[str] = Query(default=[], description="Filter by tags"),
    tag_match: Literal["all", "any"] = Query(default="all", description="Tag matching mode: 'all' (AND) or 'any' (OR)"),  # noqa: E501
    sort_by: Literal["created_at", "updated_at", "last_used_at", "title", "archived_at", "deleted_at"] = Query(default="created_at", description="Sort field"),  # noqa: E501
    sort_order: Literal["asc", "desc"] = Query(default="desc", description="Sort order"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    limit: int = Query(default=50, ge=1, le=100, description="Pagination limit"),
    view: Literal["active", "archived", "deleted"] = Query(default="active", description="Which bookmarks to show: active (default), archived, or deleted"),  # noqa: E501
    list_id: int | None = Query(default=None, description="Filter by bookmark list ID"),
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
    - **view**: Which bookmarks to show - 'active' (not deleted/archived), 'archived', or 'deleted'
    - **list_id**: Filter by bookmark list (can be combined with tags for additional filtering)
    """
    # If list_id provided, fetch the list and use its filter expression
    filter_expression = None
    if list_id is not None:
        content_list = await content_list_service.get_list(db, current_user.id, list_id)
        if content_list is None:
            raise HTTPException(status_code=404, detail="List not found")
        filter_expression = content_list.filter_expression

    try:
        bookmarks, total = await bookmark_service.search(
            db=db,
            user_id=current_user.id,
            query=q,
            tags=tags if tags else None,
            tag_match=tag_match,
            sort_by=sort_by,
            sort_order=sort_order,
            offset=offset,
            limit=limit,
            view=view,
            filter_expression=filter_expression,
        )
    except ValueError as e:
        # Tag validation errors from validate_and_normalize_tags
        raise HTTPException(status_code=422, detail=str(e))
    items = [BookmarkListItem.model_validate(b) for b in bookmarks]
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
    """Get a single bookmark by ID (includes archived bookmarks)."""
    bookmark = await bookmark_service.get(
        db, current_user.id, bookmark_id, include_archived=True,
    )
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
    try:
        bookmark = await bookmark_service.update(
            db, current_user.id, bookmark_id, data,
        )
    except DuplicateUrlError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(e),
                "error_code": "ACTIVE_URL_EXISTS",
            },
        )
    if bookmark is None:
        raise HTTPException(status_code=404, detail="Bookmark not found")
    return BookmarkResponse.model_validate(bookmark)


@router.delete("/{bookmark_id}", status_code=204)
async def delete_bookmark(
    bookmark_id: int,
    permanent: bool = Query(default=False, description="If true, permanently delete. If false, soft delete."),  # noqa: E501
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> None:
    """
    Delete a bookmark.

    By default, performs a soft delete (sets deleted_at timestamp).
    Use ?permanent=true from the trash view to permanently remove from database.
    """
    deleted = await bookmark_service.delete(
        db, current_user.id, bookmark_id, permanent=permanent,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Bookmark not found")


@router.post("/{bookmark_id}/restore", response_model=BookmarkResponse)
async def restore_bookmark(
    bookmark_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> BookmarkResponse:
    """
    Restore a soft-deleted bookmark to active state.

    Clears both deleted_at and archived_at timestamps, returning the bookmark
    to active state (not archived).
    """
    try:
        bookmark = await bookmark_service.restore(
            db, current_user.id, bookmark_id,
        )
    except InvalidStateError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except DuplicateUrlError as e:
        raise HTTPException(status_code=409, detail=str(e))

    if bookmark is None:
        raise HTTPException(status_code=404, detail="Bookmark not found")
    return BookmarkResponse.model_validate(bookmark)


@router.post("/{bookmark_id}/archive", response_model=BookmarkResponse)
async def archive_bookmark(
    bookmark_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> BookmarkResponse:
    """
    Archive a bookmark.

    Sets archived_at timestamp. This operation is idempotent - archiving an
    already-archived bookmark returns success with the current state.
    """
    bookmark = await bookmark_service.archive(
        db, current_user.id, bookmark_id,
    )
    if bookmark is None:
        raise HTTPException(status_code=404, detail="Bookmark not found")
    return BookmarkResponse.model_validate(bookmark)


@router.post("/{bookmark_id}/unarchive", response_model=BookmarkResponse)
async def unarchive_bookmark(
    bookmark_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> BookmarkResponse:
    """
    Unarchive a bookmark.

    Clears archived_at timestamp, returning the bookmark to active state.
    """
    try:
        bookmark = await bookmark_service.unarchive(
            db, current_user.id, bookmark_id,
        )
    except InvalidStateError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if bookmark is None:
        raise HTTPException(status_code=404, detail="Bookmark not found")
    return BookmarkResponse.model_validate(bookmark)


@router.post("/{bookmark_id}/track-usage", status_code=204)
async def track_bookmark_usage(
    bookmark_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> None:
    """
    Track bookmark usage by updating last_used_at timestamp.

    This is a fire-and-forget endpoint for the frontend to call when a user
    clicks a bookmark link. Works on active, archived, and deleted bookmarks.
    """
    updated = await bookmark_service.track_usage(
        db, current_user.id, bookmark_id,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Bookmark not found")
