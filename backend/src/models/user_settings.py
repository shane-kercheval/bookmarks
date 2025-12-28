"""UserSettings model for storing user preferences."""
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from models.user import User


class UserSettings(Base, TimestampMixin):
    """
    User settings - stores user preferences like tab order.

    Tab Order Format:
    -----------------
    The tab_order field stores a structured JSONB object with sections:

    {
        "sections": {
            "shared": ["all", "archived", "trash", "list:456"],
            "bookmarks": ["all-bookmarks", "list:123"],
            "notes": ["all-notes", "list:234"]
        },
        "section_order": ["shared", "bookmarks", "notes"]
    }

    Section types:
    - "shared": Cross-type items (All, Archived, Trash) + mixed-content lists
    - "bookmarks": Bookmark-specific items + bookmark-only lists
    - "notes": Note-specific items + note-only lists

    Built-in keys:
    - "all": All content (deprecated, use "all-bookmarks" or "all-notes")
    - "all-bookmarks": All bookmarks view
    - "all-notes": All notes view
    - "archived": All archived items (shared section)
    - "trash": All deleted items (shared section)
    - "list:{id}": Custom list reference

    Lists are placed in sections based on their content_types:
    - ["bookmark"] -> bookmarks section
    - ["note"] -> notes section
    - ["bookmark", "note"] -> shared section
    """

    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tab_order: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Structured tab order with sections. See model docstring for format.",
    )

    user: Mapped["User"] = relationship("User", back_populates="settings")
