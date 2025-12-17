"""Add CASCADE delete to bookmarks.user_id FK.

This ensures bookmarks are automatically deleted when their user is deleted
at the database level, providing defense in depth alongside SQLAlchemy's
relationship cascade.

Revision ID: abefe96a197f
Revises: 5b53b6ad54a6
Create Date: 2025-12-17 09:09:18.434393

"""
from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "abefe96a197f"
down_revision: str | Sequence[str] | None = "5b53b6ad54a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ON DELETE CASCADE to bookmarks.user_id FK."""
    op.drop_constraint("bookmarks_user_id_fkey", "bookmarks", type_="foreignkey")
    op.create_foreign_key(
        "bookmarks_user_id_fkey",
        "bookmarks",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Remove ON DELETE CASCADE from bookmarks.user_id FK."""
    op.drop_constraint("bookmarks_user_id_fkey", "bookmarks", type_="foreignkey")
    op.create_foreign_key(
        "bookmarks_user_id_fkey",
        "bookmarks",
        "users",
        ["user_id"],
        ["id"],
    )
