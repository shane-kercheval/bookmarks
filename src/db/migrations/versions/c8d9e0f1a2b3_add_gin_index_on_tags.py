"""
Add GIN index on bookmarks.tags for fast tag filtering.

Revision ID: c8d9e0f1a2b3
Revises: 62fe0762a928
Create Date: 2025-12-13 14:00:00.000000
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8d9e0f1a2b3"
down_revision: str | Sequence[str] | None = "62fe0762a928"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add GIN index on tags array for fast containment queries (@> and && operators)."""
    op.create_index(
        "ix_bookmarks_tags_gin",
        "bookmarks",
        ["tags"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    """Remove GIN index on tags."""
    op.drop_index("ix_bookmarks_tags_gin", table_name="bookmarks")
