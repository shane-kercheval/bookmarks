"""Pydantic schemas for user settings endpoints."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


# Valid section names
SectionName = Literal["shared", "bookmarks", "notes"]

# Valid built-in tab keys
VALID_BUILTIN_KEYS = {"all", "all-bookmarks", "all-notes", "archived", "trash"}

# Default section order
DEFAULT_SECTION_ORDER: list[SectionName] = ["shared", "bookmarks", "notes"]


class TabOrderSections(BaseModel):
    """The sections within a tab order structure."""

    shared: list[str] = []
    bookmarks: list[str] = []
    notes: list[str] = []


class TabOrder(BaseModel):
    """
    Structured tab order with sections.

    Example:
        {
            "sections": {
                "shared": ["all", "archived", "trash", "list:456"],
                "bookmarks": ["all-bookmarks", "list:123"],
                "notes": ["all-notes", "list:234"]
            },
            "section_order": ["shared", "bookmarks", "notes"]
        }
    """

    sections: TabOrderSections = TabOrderSections()
    section_order: list[SectionName] = DEFAULT_SECTION_ORDER.copy()

    @field_validator("section_order")
    @classmethod
    def validate_section_order(cls, v: list[SectionName]) -> list[SectionName]:
        """Ensure section_order contains only valid section names."""
        valid_sections = {"shared", "bookmarks", "notes"}
        for section in v:
            if section not in valid_sections:
                msg = f"Invalid section name: {section}"
                raise ValueError(msg)
        return v


class UserSettingsUpdate(BaseModel):
    """Schema for updating user settings."""

    tab_order: TabOrder | None = None


class UserSettingsResponse(BaseModel):
    """Schema for user settings responses."""

    model_config = ConfigDict(from_attributes=True)

    tab_order: TabOrder | None
    updated_at: datetime
