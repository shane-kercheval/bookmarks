"""Pydantic schemas for user settings endpoints."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserSettingsUpdate(BaseModel):
    """Schema for updating user settings."""

    tab_order: list[str] | None = None


class UserSettingsResponse(BaseModel):
    """Schema for user settings responses."""

    model_config = ConfigDict(from_attributes=True)

    tab_order: list[str] | None
    updated_at: datetime
