"""Bookmark model for storing user bookmarks."""
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from models.user import User


class Bookmark(Base, TimestampMixin):
    """Bookmark model - stores URLs with metadata and tags."""

    __tablename__ = "bookmarks"
    __table_args__ = (
        UniqueConstraint("user_id", "url", name="uq_bookmark_user_url"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # AI-generated (Phase 2)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), server_default="{}")

    user: Mapped["User"] = relationship(back_populates="bookmarks")
