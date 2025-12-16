"""
Add deleted_at and archived_at to bookmarks.

Revision ID: d9e8f7a6b5c4
Revises: 741b520cb24b
Create Date: 2025-12-14 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d9e8f7a6b5c4"
down_revision: str | Sequence[str] | None = "741b520cb24b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add deleted_at column with index for soft delete queries and future cleanup job
    op.add_column(
        "bookmarks",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_bookmarks_deleted_at"), "bookmarks", ["deleted_at"], unique=False,
    )

    # Add archived_at column for archive functionality
    op.add_column(
        "bookmarks",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Drop the old unique constraint that enforces uniqueness on all bookmarks
    op.drop_constraint("uq_bookmark_user_url", "bookmarks", type_="unique")

    # Create partial unique index that only enforces uniqueness for non-deleted bookmarks
    # This allows soft-deleted bookmarks to not count toward URL uniqueness,
    # while active and archived bookmarks (both have deleted_at IS NULL) still enforce uniqueness
    op.execute(
        """
        CREATE UNIQUE INDEX uq_bookmark_user_url_active
        ON bookmarks (user_id, url)
        WHERE deleted_at IS NULL
        """,
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop partial unique index
    op.drop_index("uq_bookmark_user_url_active", table_name="bookmarks")

    # Recreate original unique constraint
    op.create_unique_constraint("uq_bookmark_user_url", "bookmarks", ["user_id", "url"])

    # Drop archived_at column
    op.drop_column("bookmarks", "archived_at")

    # Drop deleted_at index and column
    op.drop_index(op.f("ix_bookmarks_deleted_at"), table_name="bookmarks")
    op.drop_column("bookmarks", "deleted_at")
