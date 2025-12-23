"""Add default sort columns to bookmark_lists

Revision ID: a78e8972446e
Revises: 18a484989bf0
Create Date: 2025-12-22 21:23:56.006940

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a78e8972446e'
down_revision: Union[str, Sequence[str], None] = '18a484989bf0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('bookmark_lists', sa.Column('default_sort_by', sa.String(length=20), nullable=True))
    op.add_column('bookmark_lists', sa.Column('default_sort_ascending', sa.Boolean(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('bookmark_lists', 'default_sort_ascending')
    op.drop_column('bookmark_lists', 'default_sort_by')
