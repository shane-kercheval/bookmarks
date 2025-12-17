"""migrate_tags_data_to_normalized_tables

Revision ID: 3ce8365d1b3b
Revises: 523af54a3049
Create Date: 2025-12-16 23:58:46.510156

Data migration to populate the new tags and bookmark_tags tables
from the existing bookmarks.tags array column.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3ce8365d1b3b'
down_revision: Union[str, Sequence[str], None] = '523af54a3049'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Migrate tag data from bookmarks.tags array to normalized tables."""
    conn = op.get_bind()

    # Step 1: Insert unique tags per user into tags table
    # Uses ON CONFLICT DO NOTHING for idempotency
    conn.execute(sa.text("""
        INSERT INTO tags (user_id, name, created_at)
        SELECT DISTINCT
            b.user_id,
            unnest(b.tags) as tag_name,
            NOW()
        FROM bookmarks b
        WHERE array_length(b.tags, 1) > 0
        ON CONFLICT (user_id, name) DO NOTHING
    """))

    # Step 2: Create bookmark_tags junction entries
    # Uses ON CONFLICT DO NOTHING for idempotency
    conn.execute(sa.text("""
        INSERT INTO bookmark_tags (bookmark_id, tag_id)
        SELECT
            b.id as bookmark_id,
            t.id as tag_id
        FROM bookmarks b
        CROSS JOIN LATERAL unnest(b.tags) as tag_name
        JOIN tags t ON t.user_id = b.user_id AND t.name = tag_name
        WHERE array_length(b.tags, 1) > 0
        ON CONFLICT (bookmark_id, tag_id) DO NOTHING
    """))


def downgrade() -> None:
    """Remove migrated data (tags table data only, structure preserved)."""
    conn = op.get_bind()

    # Delete junction entries first (FK constraint)
    conn.execute(sa.text("DELETE FROM bookmark_tags"))

    # Delete tags
    conn.execute(sa.text("DELETE FROM tags"))
