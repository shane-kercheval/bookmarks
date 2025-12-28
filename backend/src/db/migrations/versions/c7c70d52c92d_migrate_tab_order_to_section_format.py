"""migrate_tab_order_to_section_format

Revision ID: c7c70d52c92d
Revises: dc8282571684
Create Date: 2025-12-26 16:16:23.488095

Migrates user_settings.tab_order from flat list format to section-based format.

Old format:
    ["list:123", "all", "archived", "trash"]

New format:
    {
        "sections": {
            "shared": ["all", "archived", "trash"],
            "bookmarks": ["all-bookmarks", "list:123"],
            "notes": ["all-notes"]
        },
        "section_order": ["shared", "bookmarks", "notes"]
    }
"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c7c70d52c92d'
down_revision: Union[str, Sequence[str], None] = 'dc8282571684'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def get_default_new_format() -> dict:
    """Return the default new tab order format."""
    return {
        "sections": {
            "shared": ["all", "archived", "trash"],
            "bookmarks": ["all-bookmarks"],
            "notes": ["all-notes"],
        },
        "section_order": ["shared", "bookmarks", "notes"],
    }


def migrate_old_to_new(old_tab_order: list | None) -> dict:
    """
    Convert old flat list format to new section-based format.

    Old format items are placed as follows:
    - "all", "archived", "trash" -> shared section
    - "list:*" -> bookmarks section (since old lists were bookmark-only)
    - Other items preserved in shared section

    Then we add the new built-in items that didn't exist before.
    """
    if old_tab_order is None:
        return get_default_new_format()

    # Items that go to shared section
    shared_items = []
    # Items that go to bookmarks section (old list: references)
    bookmark_items = []

    # Known shared built-in keys
    shared_builtins = {"all", "archived", "trash"}

    for item in old_tab_order:
        if item in shared_builtins:
            shared_items.append(item)
        elif item.startswith("list:"):
            # Old lists were bookmark-only
            bookmark_items.append(item)
        else:
            # Unknown items go to shared
            shared_items.append(item)

    # Add all-bookmarks at the beginning of bookmarks section
    bookmark_items = ["all-bookmarks", *bookmark_items]

    return {
        "sections": {
            "shared": shared_items if shared_items else ["all", "archived", "trash"],
            "bookmarks": bookmark_items,
            "notes": ["all-notes"],
        },
        "section_order": ["shared", "bookmarks", "notes"],
    }


def migrate_new_to_old(new_tab_order: dict | None) -> list | None:
    """
    Convert new section-based format back to old flat list format.

    Flattens all sections into a single list, preserving order.
    Removes new built-in items that didn't exist in old format (all-bookmarks, all-notes).
    """
    if new_tab_order is None:
        return None

    sections = new_tab_order.get("sections", {})
    section_order = new_tab_order.get("section_order", ["shared", "bookmarks", "notes"])

    # Items that didn't exist in old format
    new_builtins = {"all-bookmarks", "all-notes"}

    result = []
    for section_name in section_order:
        section_items = sections.get(section_name, [])
        for item in section_items:
            if item not in new_builtins:
                result.append(item)

    return result if result else None


def upgrade() -> None:
    """Upgrade schema and migrate data to new format."""
    # Update comment on the column
    op.alter_column(
        'user_settings',
        'tab_order',
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        comment='Structured tab order with sections. See model docstring for format.',
        existing_nullable=True,
    )

    # Migrate existing data from old format to new format
    connection = op.get_bind()

    # Get all user_settings rows with tab_order
    result = connection.execute(
        sa.text("SELECT user_id, tab_order FROM user_settings WHERE tab_order IS NOT NULL")
    )

    for row in result:
        user_id = row[0]
        old_tab_order = row[1]

        # Check if it's already in new format (has "sections" key)
        if isinstance(old_tab_order, dict) and "sections" in old_tab_order:
            continue  # Already migrated

        # Check if it's old format (a list)
        if isinstance(old_tab_order, list):
            new_tab_order = migrate_old_to_new(old_tab_order)
            connection.execute(
                sa.text(
                    "UPDATE user_settings SET tab_order = :new_value WHERE user_id = :user_id"
                ),
                {"new_value": json.dumps(new_tab_order), "user_id": user_id},
            )


def downgrade() -> None:
    """Downgrade schema and migrate data back to old format."""
    # Migrate existing data from new format to old format
    connection = op.get_bind()

    result = connection.execute(
        sa.text("SELECT user_id, tab_order FROM user_settings WHERE tab_order IS NOT NULL")
    )

    for row in result:
        user_id = row[0]
        tab_order = row[1]

        # Check if it's in new format (has "sections" key)
        if isinstance(tab_order, dict) and "sections" in tab_order:
            old_tab_order = migrate_new_to_old(tab_order)
            if old_tab_order is None:
                connection.execute(
                    sa.text(
                        "UPDATE user_settings SET tab_order = NULL WHERE user_id = :user_id"
                    ),
                    {"user_id": user_id},
                )
            else:
                connection.execute(
                    sa.text(
                        "UPDATE user_settings SET tab_order = :old_value WHERE user_id = :user_id"
                    ),
                    {"old_value": json.dumps(old_tab_order), "user_id": user_id},
                )

    # Revert comment
    op.alter_column(
        'user_settings',
        'tab_order',
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        comment="Ordered list of tab identifiers: 'all', 'archived', 'trash', 'list:{id}'",
        existing_nullable=True,
    )
