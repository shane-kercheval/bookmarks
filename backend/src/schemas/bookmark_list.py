"""Pydantic schemas for bookmark list endpoints."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from schemas.bookmark import validate_and_normalize_tags

# Sort options for list defaults
# Note: archived_at/deleted_at are valid for bookmarks API but NOT for list defaults
ListSortByOption = Literal["created_at", "updated_at", "last_used_at", "title"]


class FilterGroup(BaseModel):
    """A group of tags combined with AND logic."""

    tags: list[str] = Field(min_length=1)
    operator: Literal["AND"] = "AND"

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, v: list[str]) -> list[str]:
        """Normalize and validate tags."""
        if v is None:
            return []
        return validate_and_normalize_tags(v)


class FilterExpression(BaseModel):
    """
    Filter expression with AND groups combined by OR.

    Example: {"groups": [{"tags": ["a", "b"]}, {"tags": ["c"]}], "group_operator": "OR"}
    Evaluates to: (a AND b) OR (c)
    """

    groups: list[FilterGroup] = Field(min_length=1)
    group_operator: Literal["OR"] = "OR"


class BookmarkListCreate(BaseModel):
    """Schema for creating a new bookmark list."""

    name: str = Field(min_length=1, max_length=100)
    filter_expression: FilterExpression
    default_sort_by: ListSortByOption | None = None
    default_sort_ascending: bool | None = None  # None/False = desc, True = asc


class BookmarkListUpdate(BaseModel):
    """Schema for updating an existing bookmark list."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    filter_expression: FilterExpression | None = None
    default_sort_by: ListSortByOption | None = None
    default_sort_ascending: bool | None = None


class BookmarkListResponse(BaseModel):
    """Schema for bookmark list responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    filter_expression: FilterExpression
    default_sort_by: str | None
    default_sort_ascending: bool | None
    created_at: datetime
    updated_at: datetime
