"""
Add unique constraint user_id url to bookmarks.

Revision ID: 741b520cb24b
Revises: c8d9e0f1a2b3
Create Date: 2025-12-14 09:49:15.970553

"""
from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '741b520cb24b'
down_revision: str | Sequence[str] | None = 'c8d9e0f1a2b3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_unique_constraint('uq_bookmark_user_url', 'bookmarks', ['user_id', 'url'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_bookmark_user_url', 'bookmarks', type_='unique')
