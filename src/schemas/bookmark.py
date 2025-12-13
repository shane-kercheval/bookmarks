"""Pydantic schemas for bookmark endpoints."""
import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, HttpUrl, field_validator


def validate_and_normalize_tags(tags: list[str]) -> list[str]:
    """Normalize tags: lowercase, validate format (alphanumeric + hyphens only)."""
    normalized = []
    for tag in tags:
        normalized_tag = tag.lower().strip()
        if not normalized_tag:
            continue
        if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", normalized_tag):
            raise ValueError(
                f"Invalid tag format: '{normalized_tag}'. "
                "Use lowercase letters, numbers, and hyphens only (e.g., 'machine-learning').",
            )
        normalized.append(normalized_tag)
    return normalized


class BookmarkCreate(BaseModel):
    """Schema for creating a new bookmark."""

    url: HttpUrl
    title: str | None = None
    description: str | None = None
    content: str | None = None  # User-provided content (e.g., for paywalled sites)
    tags: list[str] = []
    store_content: bool = True  # Whether to persist scraped content

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, v: list[str]) -> list[str]:
        """Normalize and validate tags."""
        if v is None:
            return []
        return validate_and_normalize_tags(v)


class BookmarkUpdate(BaseModel):
    """Schema for updating an existing bookmark."""

    title: str | None = None
    description: str | None = None
    content: str | None = None
    tags: list[str] | None = None

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, v: list[str] | None) -> list[str] | None:
        """Normalize and validate tags if provided."""
        if v is None:
            return None
        return validate_and_normalize_tags(v)


class BookmarkResponse(BaseModel):
    """
    Schema for bookmark responses.

    Note: `content` field is intentionally excluded to keep list responses small.
    Content can be large (full page text). Add a BookmarkDetailResponse or
    ?include_content=true parameter if full content is needed in responses.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    title: str | None
    description: str | None
    summary: str | None  # AI-generated summary (Phase 2)
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class BookmarkListResponse(BaseModel):
    """Schema for paginated bookmark list responses with search/filter metadata."""

    items: list[BookmarkResponse]
    total: int  # Total count of bookmarks matching the query (before pagination)
    offset: int  # Current pagination offset
    limit: int  # Current pagination limit
    has_more: bool  # True if there are more results beyond this page
