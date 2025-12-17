"""User model for storing authenticated users."""
from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from models.api_token import ApiToken
    from models.bookmark import Bookmark
    from models.bookmark_list import BookmarkList
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

    bookmarks: Mapped[list["Bookmark"]] = relationship(back_populates="user")
    api_tokens: Mapped[list["ApiToken"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    settings: Mapped["UserSettings | None"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
    bookmark_lists: Mapped[list["BookmarkList"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
