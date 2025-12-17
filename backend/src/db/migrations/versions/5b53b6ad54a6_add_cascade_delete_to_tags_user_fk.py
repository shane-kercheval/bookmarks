"""
Add ON DELETE CASCADE to tags.user_id foreign key.

This ensures tags are automatically deleted when their user is deleted
at the database level, providing defense in depth alongside SQLAlchemy's
relationship cascade.

Revision ID: 5b53b6ad54a6
Revises: aa4537891c2c
Create Date: 2025-12-17 08:48:54.791940
"""
from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "5b53b6ad54a6"
down_revision: str | Sequence[str] | None = "aa4537891c2c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ON DELETE CASCADE to tags.user_id FK."""
    # Drop existing FK constraint and recreate with CASCADE
    op.drop_constraint("tags_user_id_fkey", "tags", type_="foreignkey")
    op.create_foreign_key(
        "tags_user_id_fkey",
        "tags",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Remove ON DELETE CASCADE from tags.user_id FK."""
    op.drop_constraint("tags_user_id_fkey", "tags", type_="foreignkey")
    op.create_foreign_key(
        "tags_user_id_fkey",
        "tags",
        "users",
        ["user_id"],
        ["id"],
    )
