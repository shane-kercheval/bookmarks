"""BookmarkList model for storing custom bookmark lists with tag filters."""
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from models.user import User


class BookmarkList(Base, TimestampMixin):
    """
    BookmarkList model - stores custom lists with tag-based filter expressions.

    Filter expressions use AND groups combined by OR:
    {
        "groups": [
            {"tags": ["work", "priority"], "operator": "AND"},
            {"tags": ["urgent"], "operator": "AND"}
        ],
        "group_operator": "OR"
    }
    Evaluates to: (work AND priority) OR (urgent)
    """

    __tablename__ = "bookmark_lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100))
    filter_expression: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Tag filter expression with AND groups combined by OR",
    )
    default_sort_by: Mapped[str | None] = mapped_column(String(20), nullable=True)
    default_sort_ascending: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="bookmark_lists")
