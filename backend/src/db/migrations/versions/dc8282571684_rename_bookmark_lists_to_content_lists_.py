"""rename_bookmark_lists_to_content_lists_add_content_types

Revision ID: dc8282571684
Revises: e1954a7343da
Create Date: 2025-12-26 15:52:23.625649

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'dc8282571684'
down_revision: Union[str, Sequence[str], None] = 'e1954a7343da'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Rename the table from bookmark_lists to content_lists
    op.rename_table('bookmark_lists', 'content_lists')

    # Rename the index to match the new table name
    op.execute('ALTER INDEX ix_bookmark_lists_user_id RENAME TO ix_content_lists_user_id')

    # Add the content_types column with default ["bookmark"] for existing lists
    op.add_column(
        'content_lists',
        sa.Column(
            'content_types',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[\"bookmark\"]'::jsonb"),
            comment='Content types this list applies to: bookmark, note, todo',
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Remove the content_types column
    op.drop_column('content_lists', 'content_types')

    # Rename the index back to the old name
    op.execute('ALTER INDEX ix_content_lists_user_id RENAME TO ix_bookmark_lists_user_id')

    # Rename the table back to bookmark_lists
    op.rename_table('content_lists', 'bookmark_lists')
