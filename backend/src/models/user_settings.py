"""UserSettings model for storing user preferences."""
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from models.user import User


class UserSettings(Base, TimestampMixin):
    """User settings - stores user preferences like tab order."""

    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tab_order: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Ordered list of tab identifiers: 'all', 'archived', 'trash', 'list:{id}'",
    )

    user: Mapped["User"] = relationship("User", back_populates="settings")
