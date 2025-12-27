"""Pydantic schemas for unified content endpoints."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ContentListItem(BaseModel):
    """
    Unified content item for list views.

    This schema represents both bookmarks and notes in a unified format.
    The `type` field indicates the content type, and type-specific fields
    (url for bookmarks, version for notes) may be None for other types.
    """

    type: Literal["bookmark", "note"]
    id: int
    title: str | None
    description: str | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime
    deleted_at: datetime | None = None
    archived_at: datetime | None = None

    # Bookmark-specific (None for notes)
    url: str | None = None

    # Note-specific (None for bookmarks)
    version: int | None = None


class ContentListResponse(BaseModel):
    """Schema for paginated unified content list responses."""

    items: list[ContentListItem]
    total: int  # Total count of items matching the query (before pagination)
    offset: int  # Current pagination offset
    limit: int  # Current pagination limit
    has_more: bool  # True if there are more results beyond this page
