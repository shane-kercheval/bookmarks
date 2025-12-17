"""Pydantic schemas for bookmark endpoints."""
import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, HttpUrl, field_validator


# Maximum content length: 500KB (sufficient for articles, prevents storing megabytes)
MAX_CONTENT_LENGTH = 512_000


def validate_and_normalize_tags(tags: list[str]) -> list[str]:
    """
    Normalize tags: lowercase, validate format (alphanumeric + hyphens only).

    Note: This validation is intentionally duplicated in the frontend (frontend/src/utils.ts)
    for immediate UX feedback. Backend validation ensures security. Keep both in sync if
    changing the tag format rules.

    Format: lowercase alphanumeric with hyphens (e.g., 'machine-learning', 'web-dev')
    Pattern: ^[a-z0-9]+(-[a-z0-9]+)*$
    """
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


def validate_content_length(content: str | None) -> str | None:
    """Validate that content doesn't exceed maximum length."""
    if content is not None and len(content) > MAX_CONTENT_LENGTH:
        raise ValueError(
            f"Content exceeds maximum length of {MAX_CONTENT_LENGTH:,} characters "
            f"(got {len(content):,} characters). Consider summarizing the content.",
        )
    return content


class BookmarkCreate(BaseModel):
    """Schema for creating a new bookmark."""

    # HttpUrl normalizes root domains with trailing slash (example.com -> example.com/)
    # but preserves paths as-is (example.com/page stays example.com/page)
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

    @field_validator("content")
    @classmethod
    def check_content_length(cls, v: str | None) -> str | None:
        """Validate content length."""
        return validate_content_length(v)


class BookmarkUpdate(BaseModel):
    """Schema for updating an existing bookmark."""

    # See BookmarkCreate for HttpUrl normalization behavior
    url: HttpUrl | None = None
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

    @field_validator("content")
    @classmethod
    def check_content_length(cls, v: str | None) -> str | None:
        """Validate content length."""
        return validate_content_length(v)


class BookmarkListItem(BaseModel):
    """
    Schema for bookmark list items (excludes content for performance).

    The content field can be up to 500KB per bookmark, making list responses
    unnecessarily large. Use GET /bookmarks/:id to fetch full bookmark with content.
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
    last_used_at: datetime
    deleted_at: datetime | None = None
    archived_at: datetime | None = None


class BookmarkResponse(BookmarkListItem):
    """
    Schema for full bookmark responses (includes content).

    Returned by GET /bookmarks/:id and mutation endpoints.
    """

    content: str | None


class BookmarkListResponse(BaseModel):
    """Schema for paginated bookmark list responses with search/filter metadata."""

    items: list[BookmarkListItem]
    total: int  # Total count of bookmarks matching the query (before pagination)
    offset: int  # Current pagination offset
    limit: int  # Current pagination limit
    has_more: bool  # True if there are more results beyond this page


class MetadataPreviewResponse(BaseModel):
    """Schema for URL metadata preview (before saving bookmark)."""

    url: str  # Original URL requested
    final_url: str  # URL after following redirects
    title: str | None
    description: str | None
    content: str | None = None  # Extracted page content (when include_content=True)
    error: str | None = None  # Error message if fetch failed
