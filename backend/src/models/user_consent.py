"""User consent model for tracking privacy policy and ToS acceptance."""
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, UUIDv7Mixin


class UserConsent(Base, UUIDv7Mixin):
    """
    Historical record of policy acceptance — FROZEN as of 2026-08-01.

    Nothing writes to this table anymore. The blocking consent gate and the
    accept endpoint were removed with the consent simplification (see
    docs/implementation_plans/2026-08-01-consent-simplification.md); initial
    acceptance is now captured by Clerk as `legalAcceptedAt` at sign-up.

    The table and its data are deliberately retained as the record of what was
    accepted before that change, and rows still cascade-delete with the user.
    Read it as history, not as a live system: it holds at most one row per user
    (re-consent overwrote in place, so there is no per-version history), and the
    versions a row names are the ones accepted at that time — from 2026-08-01
    they are never the currently published pair.
    """

    __tablename__ = "user_consents"

    # id provided by UUIDv7Mixin
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        comment="Foreign key to users table - one consent record per user",
    )
    consented_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        comment="Timestamp when user accepted the terms",
    )
    privacy_policy_version: Mapped[str] = mapped_column(
        String(50),
        comment="Version of privacy policy accepted (e.g., '2024-12-20')",
    )
    terms_of_service_version: Mapped[str] = mapped_column(
        String(50),
        comment="Version of terms of service accepted (e.g., '2024-12-20')",
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45),  # IPv6 max length is 45 chars
        nullable=True,
        comment="IP address at time of consent (for legal proof)",
    )
    user_agent: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Browser user agent at time of consent (for legal proof)",
    )

    # Relationship
    user: Mapped["User"] = relationship(back_populates="consent")  # noqa: F821
