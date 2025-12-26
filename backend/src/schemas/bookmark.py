"""Pydantic schemas for bookmark endpoints."""
import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from core.config import get_settings

# Tag format: lowercase alphanumeric with hyphens (e.g., 'machine-learning', 'web-dev')
# Note: This pattern is intentionally duplicated in the frontend (frontend/src/utils.ts)
# for immediate UX feedback. Backend validation ensures security. Keep both in sync.
TAG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def validate_and_normalize_tag(tag: str) -> str:
    """
    Normalize and validate a single tag.

    Args:
        tag: The tag string to validate.

    Returns:
        The normalized tag (lowercase, trimmed).

    Raises:
        ValueError: If tag is empty or has invalid format.
    """
    normalized = tag.lower().strip()
    if not normalized:
        raise ValueError("Tag name cannot be empty")
    if not TAG_PATTERN.match(normalized):
        raise ValueError(
            f"Invalid tag format: '{normalized}'. "
            "Use lowercase letters, numbers, and hyphens only (e.g., 'machine-learning').",
        )
    return normalized


def validate_and_normalize_tags(tags: list[str]) -> list[str]:
    """
    Normalize and validate a list of tags.

    Args:
        tags: List of tag strings to validate.

    Returns:
        List of normalized tags (lowercase, trimmed), with empty strings filtered out.

    Raises:
        ValueError: If any tag has invalid format.
    """
    normalized = []
    for tag in tags:
        trimmed = tag.lower().strip()
        if not trimmed:
            continue  # Skip empty tags silently
        normalized.append(validate_and_normalize_tag(trimmed))
    return normalized


def validate_content_length(content: str | None) -> str | None:
    """Validate that content doesn't exceed maximum length."""
    settings = get_settings()
    if content is not None and len(content) > settings.max_content_length:
        raise ValueError(
            f"Content exceeds maximum length of {settings.max_content_length:,} characters "
            f"(got {len(content):,} characters). Consider summarizing the content.",
        )
    return content


def validate_description_length(description: str | None) -> str | None:
    """Validate that description doesn't exceed maximum length."""
    settings = get_settings()
    if description is not None and len(description) > settings.max_description_length:
        max_len = settings.max_description_length
        raise ValueError(
            f"Description exceeds maximum length of {max_len:,} characters "
            f"(got {len(description):,} characters).",
        )
    return description


def validate_title_length(title: str | None) -> str | None:
    """Validate that title doesn't exceed maximum length."""
    settings = get_settings()
    if title is not None and len(title) > settings.max_title_length:
        raise ValueError(
            f"Title exceeds maximum length of {settings.max_title_length:,} characters "
            f"(got {len(title):,} characters).",
        )
    return title


class BookmarkCreate(BaseModel):
    """Schema for creating a new bookmark."""

    # HttpUrl normalizes root domains with trailing slash (example.com -> example.com/)
    # but preserves paths as-is (example.com/page stays example.com/page)
    url: HttpUrl
    title: str | None = None
    description: str | None = None
    content: str | None = None  # User-provided or scraped content
    tags: list[str] = []
    archived_at: datetime | None = Field(
        default=None,
        description="Schedule auto-archive at this time. Accepts ISO 8601 format with timezone "
                    "(e.g., '2025-02-01T16:00:00Z'). Stored as UTC. "
                    "Future dates schedule auto-archive; past dates archive immediately.",
    )

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, v: list[str]) -> list[str]:
        """Normalize and validate tags."""
        if v is None:
            return []
        return validate_and_normalize_tags(v)

    @field_validator("title")
    @classmethod
    def check_title_length(cls, v: str | None) -> str | None:
        """Validate title length."""
        return validate_title_length(v)

    @field_validator("description")
    @classmethod
    def check_description_length(cls, v: str | None) -> str | None:
        """Validate description length."""
        return validate_description_length(v)

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
    archived_at: datetime | None = Field(
        default=None,
        description="Schedule auto-archive at this time. Omit to leave unchanged; "
                    "set to null to cancel a scheduled archive. "
                    "Accepts ISO 8601 format (e.g., '2025-02-01T16:00:00Z'). "
                    "Future dates schedule auto-archive; past dates archive immediately.",
    )

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, v: list[str] | None) -> list[str] | None:
        """Normalize and validate tags if provided."""
        if v is None:
            return None
        return validate_and_normalize_tags(v)

    @field_validator("title")
    @classmethod
    def check_title_length(cls, v: str | None) -> str | None:
        """Validate title length."""
        return validate_title_length(v)

    @field_validator("description")
    @classmethod
    def check_description_length(cls, v: str | None) -> str | None:
        """Validate description length."""
        return validate_description_length(v)

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

    Note: Uses model_validator to extract tag names from the tag_objects
    relationship when eagerly loaded.
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

    @model_validator(mode="before")
    @classmethod
    def extract_tag_names(cls, data: Any) -> Any:
        """
        Extract tag names from tag_objects relationship.

        Only accesses tag_objects if it's already loaded (not lazy) to avoid
        triggering database queries outside async context.
        """
        # Handle SQLAlchemy model objects
        if hasattr(data, "__dict__"):
            data_dict = {}
            for key in [
                "id", "url", "title", "description", "summary",
                "created_at", "updated_at", "last_used_at",
                "deleted_at", "archived_at", "content",
            ]:
                if hasattr(data, key):
                    data_dict[key] = getattr(data, key)

            # Check if tag_objects is already loaded (not lazy)
            # SQLAlchemy sets __dict__ entry when relationship is loaded
            if "tag_objects" in data.__dict__ and data.__dict__["tag_objects"] is not None:
                data_dict["tags"] = [tag.name for tag in data.__dict__["tag_objects"]]
            else:
                data_dict["tags"] = []

            return data_dict
        return data


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
