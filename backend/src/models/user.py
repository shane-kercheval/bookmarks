"""User model for storing authenticated users."""
from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from models.api_token import ApiToken
    from models.bookmark import Bookmark
    from models.content_list import ContentList
    from models.note import Note
    from models.tag import Tag
    from models.user_consent import UserConsent
    from models.user_settings import UserSettings


class User(Base, TimestampMixin):
    """User model - stores Auth0 user info for foreign key relationships."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    auth0_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        comment="Auth0 'sub' claim - unique identifier from Auth0",
    )
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    bookmarks: Mapped[list["Bookmark"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    notes: Mapped[list["Note"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    api_tokens: Mapped[list["ApiToken"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    settings: Mapped["UserSettings | None"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
    content_lists: Mapped[list["ContentList"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    tags: Mapped[list["Tag"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    consent: Mapped["UserConsent | None"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
