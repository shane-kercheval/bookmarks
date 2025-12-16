"""
Add last_used_at column and fix timestamp timezone handling.

Revision ID: 84ef82c5cbe7
Revises: d9e8f7a6b5c4
Create Date: 2025-12-15 20:08:40.447027

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "84ef82c5cbe7"
down_revision: str | Sequence[str] | None = "d9e8f7a6b5c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Fix timestamp columns to use timezone-aware timestamps (TIMESTAMP WITH TIME ZONE)
    # This ensures consistent timezone handling across all datetime fields

    # api_tokens table
    op.alter_column('api_tokens', 'created_at',
               existing_type=postgresql.TIMESTAMP(),
               type_=sa.DateTime(timezone=True),
               existing_nullable=False,
               existing_server_default=sa.text('now()'))
    op.alter_column('api_tokens', 'updated_at',
               existing_type=postgresql.TIMESTAMP(),
               type_=sa.DateTime(timezone=True),
               existing_nullable=False,
               existing_server_default=sa.text('now()'))

    # bookmarks table - fix existing timestamp columns
    op.alter_column('bookmarks', 'created_at',
               existing_type=postgresql.TIMESTAMP(),
               type_=sa.DateTime(timezone=True),
               existing_nullable=False,
               existing_server_default=sa.text('now()'))
    op.alter_column('bookmarks', 'updated_at',
               existing_type=postgresql.TIMESTAMP(),
               type_=sa.DateTime(timezone=True),
               existing_nullable=False,
               existing_server_default=sa.text('now()'))

    # bookmarks table - add last_used_at column for usage tracking
    # Step 1: Add column as nullable
    op.add_column(
        "bookmarks",
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Step 2: Backfill existing rows with created_at value
    op.execute('UPDATE bookmarks SET last_used_at = created_at')

    # Step 3: Make column NOT NULL and add server default for new rows
    op.alter_column('bookmarks', 'last_used_at',
               nullable=False,
               server_default=sa.text('clock_timestamp()'))

    # Add indexes for sorting
    op.create_index(op.f('ix_bookmarks_last_used_at'), 'bookmarks', ['last_used_at'], unique=False)
    op.create_index(op.f('ix_bookmarks_updated_at'), 'bookmarks', ['updated_at'], unique=False)

    # users table
    op.alter_column('users', 'created_at',
               existing_type=postgresql.TIMESTAMP(),
               type_=sa.DateTime(timezone=True),
               existing_nullable=False,
               existing_server_default=sa.text('now()'))
    op.alter_column('users', 'updated_at',
               existing_type=postgresql.TIMESTAMP(),
               type_=sa.DateTime(timezone=True),
               existing_nullable=False,
               existing_server_default=sa.text('now()'))


def downgrade() -> None:
    """Downgrade schema."""
    # users table
    op.alter_column('users', 'updated_at',
               existing_type=sa.DateTime(timezone=True),
               type_=postgresql.TIMESTAMP(),
               existing_nullable=False,
               existing_server_default=sa.text('now()'))
    op.alter_column('users', 'created_at',
               existing_type=sa.DateTime(timezone=True),
               type_=postgresql.TIMESTAMP(),
               existing_nullable=False,
               existing_server_default=sa.text('now()'))

    # bookmarks table - remove last_used_at and indexes
    op.drop_index(op.f('ix_bookmarks_updated_at'), table_name='bookmarks')
    op.drop_index(op.f('ix_bookmarks_last_used_at'), table_name='bookmarks')
    op.drop_column('bookmarks', 'last_used_at')

    # bookmarks table - revert timestamp columns
    op.alter_column('bookmarks', 'updated_at',
               existing_type=sa.DateTime(timezone=True),
               type_=postgresql.TIMESTAMP(),
               existing_nullable=False,
               existing_server_default=sa.text('now()'))
    op.alter_column('bookmarks', 'created_at',
               existing_type=sa.DateTime(timezone=True),
               type_=postgresql.TIMESTAMP(),
               existing_nullable=False,
               existing_server_default=sa.text('now()'))

    # api_tokens table
    op.alter_column('api_tokens', 'updated_at',
               existing_type=sa.DateTime(timezone=True),
               type_=postgresql.TIMESTAMP(),
               existing_nullable=False,
               existing_server_default=sa.text('now()'))
    op.alter_column('api_tokens', 'created_at',
               existing_type=sa.DateTime(timezone=True),
               type_=postgresql.TIMESTAMP(),
               existing_nullable=False,
               existing_server_default=sa.text('now()'))
