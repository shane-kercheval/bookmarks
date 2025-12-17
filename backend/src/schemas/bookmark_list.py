"""Pydantic schemas for bookmark list endpoints."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from schemas.bookmark import validate_and_normalize_tags


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


class BookmarkListUpdate(BaseModel):
    """Schema for updating an existing bookmark list."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    filter_expression: FilterExpression | None = None


class BookmarkListResponse(BaseModel):
    """Schema for bookmark list responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    filter_expression: FilterExpression
    created_at: datetime
    updated_at: datetime
