"""Shared utility functions for service layer."""
from typing import Any

from sqlalchemy import Table, and_, exists, or_, select
from sqlalchemy.orm import InstrumentedAttribute

from models.tag import Tag


def escape_ilike(value: str) -> str:
    r"""
    Escape special ILIKE characters for safe use in LIKE/ILIKE patterns.

    PostgreSQL LIKE/ILIKE treats these characters specially:
    - % matches any sequence of characters
    - _ matches any single character
    - \\ is the escape character

    This function escapes them so they match literally.
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def build_tag_filter_from_expression(
    filter_expression: dict[str, Any],
    user_id: int,
    junction_table: Table,
    entity_id_column: InstrumentedAttribute,
) -> list:
    """
    Build SQLAlchemy filter clauses from a tag filter expression.

    Generic implementation for both bookmarks and notes. Converts:
        {"groups": [{"tags": ["a", "b"]}, {"tags": ["c"]}], "group_operator": "OR"}
    To:
        EXISTS subqueries checking tag relationships via junction table.

    Each group uses AND internally (entity must have ALL tags in the group).
    Groups are combined with OR.

    Args:
        filter_expression: Dict with "groups" list and "group_operator".
        user_id: User ID to scope tags.
        junction_table: The junction table (bookmark_tags or note_tags).
        entity_id_column: The entity's ID column (Bookmark.id or Note.id).

    Returns:
        List of SQLAlchemy filter clauses to apply.

    Example:
        >>> from models.bookmark import Bookmark
        >>> from models.tag import bookmark_tags
        >>> filters = build_tag_filter_from_expression(
        ...     {"groups": [{"tags": ["python"]}]},
        ...     user_id=1,
        ...     junction_table=bookmark_tags,
        ...     entity_id_column=Bookmark.id,
        ... )
    """
    groups = filter_expression.get("groups", [])
    if not groups:
        return []

    # Get the entity ID column name from the junction table (e.g., "bookmark_id" or "note_id")
    # Junction tables have two columns: entity_id and tag_id
    junction_columns = [c.name for c in junction_table.columns if c.name != "tag_id"]
    if not junction_columns:
        return []
    junction_entity_id_col = junction_table.c[junction_columns[0]]

    # Build OR conditions for each group
    group_conditions = []
    for group in groups:
        tags = group.get("tags", [])
        if tags:
            # Build AND conditions for all tags in the group
            tag_conditions = []
            for tag_name in tags:
                # EXISTS subquery: check entity has this tag via junction table
                subq = (
                    select(junction_entity_id_col)
                    .join(Tag, junction_table.c.tag_id == Tag.id)
                    .where(
                        junction_entity_id_col == entity_id_column,
                        Tag.name == tag_name,
                        Tag.user_id == user_id,
                    )
                )
                tag_conditions.append(exists(subq))

            if len(tag_conditions) == 1:
                group_conditions.append(tag_conditions[0])
            else:
                group_conditions.append(and_(*tag_conditions))

    if not group_conditions:
        return []

    # Combine groups with OR
    if len(group_conditions) == 1:
        return [group_conditions[0]]
    return [or_(*group_conditions)]
