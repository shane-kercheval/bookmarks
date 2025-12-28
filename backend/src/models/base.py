"""SQLAlchemy declarative base with common mixins."""
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


class TimestampMixin:
    """
    Mixin that adds created_at and updated_at columns.

    All timestamps are timezone-aware (stored as TIMESTAMP WITH TIME ZONE in PostgreSQL).

    Uses clock_timestamp() instead of now() to get actual wall-clock time rather than
    transaction start time. This ensures accurate timestamps when multiple operations
    occur within the same database transaction.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        nullable=False,
        index=True,  # Index for "sort by recently updated" queries
    )
