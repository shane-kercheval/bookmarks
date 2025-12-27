"""
Add archived_at and updated_at indexes for query performance.

- archived_at indexes on bookmarks/notes: Enables efficient filtering of archived views
- updated_at indexes on all timestamp tables: Enables "sort by recently updated" queries
- Drop redundant user_consents unique constraint (ix_user_consents_user_id already enforces uniqueness)

Revision ID: 9b814e3de951
Revises: c7c70d52c92d
Create Date: 2025-12-27 12:25:04.037735

"""
from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "9b814e3de951"
down_revision: str | Sequence[str] | None = "c7c70d52c92d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add archived_at indexes for bookmark/note archive view queries
    op.create_index(
        op.f("ix_bookmarks_archived_at"), "bookmarks", ["archived_at"], unique=False,
    )
    op.create_index(
        op.f("ix_notes_archived_at"), "notes", ["archived_at"], unique=False,
    )

    # Add updated_at indexes to all TimestampMixin tables for "sort by updated" queries
    op.create_index(
        op.f("ix_api_tokens_updated_at"), "api_tokens", ["updated_at"], unique=False,
    )
    op.create_index(
        op.f("ix_content_lists_updated_at"), "content_lists", ["updated_at"], unique=False,
    )
    op.create_index(
        op.f("ix_notes_updated_at"), "notes", ["updated_at"], unique=False,
    )
    op.create_index(
        op.f("ix_user_settings_updated_at"), "user_settings", ["updated_at"], unique=False,
    )
    op.create_index(
        op.f("ix_users_updated_at"), "users", ["updated_at"], unique=False,
    )

    # Drop redundant unique constraint - ix_user_consents_user_id (unique index) already enforces this
    op.drop_constraint("user_consents_user_id_key", "user_consents", type_="unique")


def downgrade() -> None:
    """Downgrade schema."""
    # Restore redundant unique constraint
    op.create_unique_constraint(
        "user_consents_user_id_key", "user_consents", ["user_id"],
    )

    # Drop updated_at indexes
    op.drop_index(op.f("ix_users_updated_at"), table_name="users")
    op.drop_index(op.f("ix_user_settings_updated_at"), table_name="user_settings")
    op.drop_index(op.f("ix_notes_updated_at"), table_name="notes")
    op.drop_index(op.f("ix_content_lists_updated_at"), table_name="content_lists")
    op.drop_index(op.f("ix_api_tokens_updated_at"), table_name="api_tokens")

    # Drop archived_at indexes
    op.drop_index(op.f("ix_notes_archived_at"), table_name="notes")
    op.drop_index(op.f("ix_bookmarks_archived_at"), table_name="bookmarks")
