"""Tombstones for deleted identities (anti-resurrection guard)."""
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin, UUIDv7Mixin


class DeletedIdentity(Base, UUIDv7Mixin, TimestampMixin):
    """
    Tombstone for a deleted user's provider identities.

    Written by the account-deletion path (Clerk `user.deleted` webhook) and
    checked by JIT provisioning before creating a user: a still-live token for
    a deleted identity (a not-yet-expired Clerk JWT) must not resurrect an
    empty user row.

    Tombstones block dead credentials, not people: providers never reuse
    identity IDs, so a deleted user who signs up again arrives as a brand-new
    identity no tombstone matches.

    Retention: rows older than 30 days are swept by the daily cleanup task
    (tasks/cleanup.py) — safe since M6b removed the Auth0 auth path, whose
    tombstones needed an open-ended lifetime; 30 days far exceeds the ~1-day
    maximum Clerk token lifetime.

    Keyed by external_auth_id — NOT NULL and unique since the M6b
    decommission migration dropped the migration-era auth0_id column.
    """

    __tablename__ = "deleted_identities"

    # id provided by UUIDv7Mixin
    external_auth_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
        comment="Clerk user ID ('sub') of the deleted user - blocks the Clerk JIT path",
    )
