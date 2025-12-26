"""Pydantic schemas for note endpoints."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.config import get_settings
from schemas.bookmark import (
    validate_and_normalize_tags,
    validate_description_length,
    validate_title_length,
)


def validate_note_content_length(content: str | None) -> str | None:
    """Validate that note content doesn't exceed maximum length (2MB)."""
    settings = get_settings()
    if content is not None and len(content) > settings.max_note_content_length:
        raise ValueError(
            f"Content exceeds maximum length of {settings.max_note_content_length:,} characters "
            f"(got {len(content):,} characters).",
        )
    return content


class NoteCreate(BaseModel):
    """Schema for creating a new note."""

    title: str  # Required for notes
    description: str | None = None
    content: str | None = None  # Markdown content, up to 2MB
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
    def check_title_length(cls, v: str) -> str:
        """Validate title is not empty and doesn't exceed max length."""
        if not v or not v.strip():
            raise ValueError("Title cannot be empty")
        # validate_title_length only returns None if input is None,
        # but we've already validated v is non-empty above
        return validate_title_length(v)  # type: ignore[return-value]

    @field_validator("description")
    @classmethod
    def check_description_length(cls, v: str | None) -> str | None:
        """Validate description length."""
        return validate_description_length(v)

    @field_validator("content")
    @classmethod
    def check_content_length(cls, v: str | None) -> str | None:
        """Validate content length."""
        return validate_note_content_length(v)


class NoteUpdate(BaseModel):
    """Schema for updating an existing note."""

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
        """Validate title is not empty (if provided) and doesn't exceed max length."""
        if v is not None:
            if not v.strip():
                raise ValueError("Title cannot be empty")
            return validate_title_length(v)
        return v

    @field_validator("description")
    @classmethod
    def check_description_length(cls, v: str | None) -> str | None:
        """Validate description length."""
        return validate_description_length(v)

    @field_validator("content")
    @classmethod
    def check_content_length(cls, v: str | None) -> str | None:
        """Validate content length."""
        return validate_note_content_length(v)


class NoteListItem(BaseModel):
    """
    Schema for note list items (excludes content for performance).

    The content field can be up to 2MB per note, making list responses
    unnecessarily large. Use GET /notes/:id to fetch full note with content.

    Note: Uses model_validator to extract tag names from the tag_objects
    relationship when eagerly loaded.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime
    deleted_at: datetime | None = None
    archived_at: datetime | None = None
    version: int

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
                "id", "title", "description",
                "created_at", "updated_at", "last_used_at",
                "deleted_at", "archived_at", "version", "content",
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


class NoteResponse(NoteListItem):
    """
    Schema for full note responses (includes content).

    Returned by GET /notes/:id and mutation endpoints.
    """

    content: str | None


class NoteListResponse(BaseModel):
    """Schema for paginated note list responses with search/filter metadata."""

    items: list[NoteListItem]
    total: int  # Total count of notes matching the query (before pagination)
    offset: int  # Current pagination offset
    limit: int  # Current pagination limit
    has_more: bool  # True if there are more results beyond this page
