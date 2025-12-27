"""Note model for storing user notes with markdown content."""
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, and_, func
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql.elements import BinaryExpression

from models.base import Base, TimestampMixin
from models.tag import note_tags

if TYPE_CHECKING:
    from models.tag import Tag
    from models.user import User


class Note(Base, TimestampMixin):
    """Note model - stores user notes with markdown content and tags."""

    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)  # Required
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)  # Markdown, up to 2MB
    version: Mapped[int] = mapped_column(default=1)  # For future version history

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

    user: Mapped["User"] = relationship(back_populates="notes")
    tag_objects: Mapped[list["Tag"]] = relationship(
        secondary=note_tags,
        back_populates="notes",
    )

    @hybrid_property
    def is_archived(self) -> bool:
        """
        Check if note is currently archived (past or present archived_at).

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
