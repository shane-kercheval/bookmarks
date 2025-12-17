"""
Remove tags array column and GIN index from bookmarks table.

After Milestone 6 of the tags refactor, the normalized tags table and
bookmark_tags junction table are the source of truth. This migration
removes the legacy PostgreSQL ARRAY column.

Revision ID: aa4537891c2c
Revises: 3ce8365d1b3b
Create Date: 2025-12-17 00:20:18.579129
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY


# revision identifiers, used by Alembic.
revision: str = "aa4537891c2c"
down_revision: str | Sequence[str] | None = "3ce8365d1b3b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop GIN index and tags array column."""
    # Drop GIN index first (depends on the column)
    op.drop_index("ix_bookmarks_tags_gin", table_name="bookmarks")

    # Drop the tags array column
    op.drop_column("bookmarks", "tags")


def downgrade() -> None:
    """Restore tags array column and GIN index."""
    # Add back the tags array column
    op.add_column(
        "bookmarks",
        sa.Column(
            "tags",
            ARRAY(sa.String()),
            server_default="{}",
            nullable=True,
        ),
    )

    # Recreate the GIN index
    op.create_index(
        "ix_bookmarks_tags_gin",
        "bookmarks",
        ["tags"],
        unique=False,
        postgresql_using="gin",
    )
