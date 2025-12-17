"""add_tags_and_bookmark_tags_tables

Revision ID: 523af54a3049
Revises: 01f5d95139d4
Create Date: 2025-12-16 23:29:48.508161

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '523af54a3049'
down_revision: Union[str, Sequence[str], None] = '01f5d95139d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('tags',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'name', name='uq_tags_user_id_name')
    )
    op.create_index(op.f('ix_tags_user_id'), 'tags', ['user_id'], unique=False)
    op.create_table('bookmark_tags',
    sa.Column('bookmark_id', sa.Integer(), nullable=False),
    sa.Column('tag_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['bookmark_id'], ['bookmarks.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('bookmark_id', 'tag_id')
    )
    op.create_index('ix_bookmark_tags_tag_id', 'bookmark_tags', ['tag_id'], unique=False)
    # Note: Keeping ix_bookmarks_tags_gin and ix_bookmarks_updated_at until Milestone 6


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_bookmark_tags_tag_id', table_name='bookmark_tags')
    op.drop_table('bookmark_tags')
    op.drop_index(op.f('ix_tags_user_id'), table_name='tags')
    op.drop_table('tags')
