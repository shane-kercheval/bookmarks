"""Bookmark model for storing user bookmarks."""
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, and_, func, text
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql.elements import BinaryExpression

from models.base import Base, TimestampMixin
from models.tag import bookmark_tags

if TYPE_CHECKING:
    from models.tag import Tag
    from models.user import User


class Bookmark(Base, TimestampMixin):
    """Bookmark model - stores URLs with metadata and tags."""

    __tablename__ = "bookmarks"
    __table_args__ = (
        # Partial unique index: enforces uniqueness only for non-deleted bookmarks
        # This allows soft-deleted bookmarks to not count toward URL uniqueness
        Index(
            "uq_bookmark_user_url_active",
            "user_id",
            "url",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # AI-generated (Phase 2)

    # Usage tracking timestamp (defaults to current time on creation)
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        server_default=func.clock_timestamp(),
    )

    # Soft delete and archive timestamps
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None, index=True,
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None, index=True,
    )

    user: Mapped["User"] = relationship(back_populates="bookmarks")
    tag_objects: Mapped[list["Tag"]] = relationship(
        secondary=bookmark_tags,
        back_populates="bookmarks",
    )

    @hybrid_property
    def is_archived(self) -> bool:
        """
        Check if bookmark is currently archived (past or present archived_at).

        Returns False if:
        - archived_at is None (not scheduled for archive)
        - archived_at is in the future (scheduled but not yet archived)

        Returns True if:
        - archived_at is in the past or present (currently archived)
        """
        if self.archived_at is None:
            return False
        # Handle both timezone-aware and naive datetimes
        now = datetime.now(UTC)
        archived_at = self.archived_at
        if archived_at.tzinfo is None:
            archived_at = archived_at.replace(tzinfo=UTC)
        return archived_at <= now

    @is_archived.expression
    def is_archived(cls) -> BinaryExpression:  # noqa: N805
        """SQL expression for archived check - used in queries."""
        return and_(
            cls.archived_at.is_not(None),
            cls.archived_at <= func.now(),
        )
