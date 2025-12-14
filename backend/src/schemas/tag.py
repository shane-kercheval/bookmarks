"""Pydantic schemas for tag endpoints."""
from pydantic import BaseModel


class TagCount(BaseModel):
    """Schema for a tag with its usage count."""

    name: str
    count: int


class TagListResponse(BaseModel):
    """Schema for the tags list response."""

    tags: list[TagCount]
