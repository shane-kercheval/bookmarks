"""User model for storing authenticated users."""
from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin, UUIDv7Mixin

if TYPE_CHECKING:
    from models.api_token import ApiToken
    from models.bookmark import Bookmark
    from models.content_filter import ContentFilter
    from models.content_history import ContentHistory
    from models.note import Note
    from models.prompt import Prompt
    from models.tag import Tag
    from models.user_settings import UserSettings


class User(Base, UUIDv7Mixin, TimestampMixin):
    """
    User model - stores identity-provider linkage for foreign key relationships.

    Keyed by `external_auth_id` (the IdP token's `sub`; currently the Clerk
    user ID) — NOT NULL and unique since the M6b decommission migration
    dropped the migration-era `auth0_id` column.
    """

    __tablename__ = "users"

    # id provided by UUIDv7Mixin
    external_auth_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
        comment=(
            "The 'sub' claim of verified IdP tokens (currently the Clerk user ID). "
            "Provider-neutral name, provider-specific value - never parse its format."
        ),
    )
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_verified: Mapped[bool | None] = mapped_column(nullable=True, default=None)
    tier: Mapped[str] = mapped_column(
        String(50),
        # BETA: default to "pro" during beta. Revert to "free" when beta ends.
        default="pro",
        server_default="pro",
        comment="User subscription tier (e.g., 'free', 'standard', 'pro')",
    )

    # passive_deletes=True on every collection: account deletion
    # (services/user_service.delete_user_by_external_auth_id) must not scale
    # with account size — the DB's ON DELETE CASCADE FKs do the work instead
    # of the ORM loading rows, and NO collection here is actually bounded
    # (filters/groups have no quota either — review-round finding). The one
    # cascade the DB cannot do in a single user-delete statement is the
    # filter chain (filter_group_tags.tag_id is ondelete=RESTRICT and trips
    # per internal cascade statement — see models/tag.py), so the deletion
    # service bulk-deletes content_filters FIRST as its own set-based
    # statement (its cascades stop at the association rows), then deletes the
    # user. Two constant statements; the statement-count test in
    # tests/services/test_user_deletion.py guards this in both dimensions.
    bookmarks: Mapped[list["Bookmark"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    notes: Mapped[list["Note"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    prompts: Mapped[list["Prompt"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    api_tokens: Mapped[list["ApiToken"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    settings: Mapped["UserSettings | None"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
        passive_deletes=True,
    )
    content_filters: Mapped[list["ContentFilter"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    tags: Mapped[list["Tag"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    content_history: Mapped[list["ContentHistory"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
