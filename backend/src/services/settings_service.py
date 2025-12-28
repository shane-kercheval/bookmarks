"""Service layer for user settings operations."""
import copy

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from models.user_settings import UserSettings
from schemas.user_settings import (
    DEFAULT_SECTION_ORDER,
    SectionName,
    TabOrder,
    TabOrderSections,
    UserSettingsUpdate,
)


def get_default_tab_order() -> dict:
    """Return the default tab order structure."""
    return {
        "sections": {
            "shared": ["all", "archived", "trash"],
            "bookmarks": ["all-bookmarks"],
            "notes": ["all-notes"],
        },
        "section_order": list(DEFAULT_SECTION_ORDER),
    }


def determine_section_for_list(content_types: list[str]) -> SectionName:
    """
    Determine which section a list belongs to based on its content_types.

    Args:
        content_types: List of content types the list applies to.

    Returns:
        The section name where this list should be placed.
    """
    if len(content_types) == 1:
        if content_types[0] == "bookmark":
            return "bookmarks"
        if content_types[0] == "note":
            return "notes"
    # Mixed content types or unknown -> shared section
    return "shared"


def _ensure_tab_order_structure(tab_order: dict | None) -> dict:
    """
    Ensure tab_order has the correct structure, filling in defaults.

    Always returns a NEW dict to avoid mutating the input. This makes the
    function safe to use regardless of whether the caller passes a tracked
    SQLAlchemy object or not.
    """
    if tab_order is None:
        return get_default_tab_order()

    # Create a deep copy to avoid mutating the input
    result = copy.deepcopy(tab_order)

    # Ensure sections exist
    if "sections" not in result:
        result["sections"] = {}

    sections = result["sections"]
    if "shared" not in sections:
        sections["shared"] = ["all", "archived", "trash"]
    if "bookmarks" not in sections:
        sections["bookmarks"] = ["all-bookmarks"]
    if "notes" not in sections:
        sections["notes"] = ["all-notes"]

    # Ensure section_order exists
    if "section_order" not in result:
        result["section_order"] = list(DEFAULT_SECTION_ORDER)

    return result


def _list_key_in_any_section(tab_order: dict, list_key: str) -> str | None:
    """Check if a list key exists in any section. Returns section name or None."""
    sections = tab_order.get("sections", {})
    for section_name, items in sections.items():
        if list_key in items:
            return section_name
    return None


async def get_settings(db: AsyncSession, user_id: int) -> UserSettings | None:
    """Get user settings, returns None if not exists."""
    query = select(UserSettings).where(UserSettings.user_id == user_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_or_create_settings(db: AsyncSession, user_id: int) -> UserSettings:
    """Get user settings, creating default if not exists."""
    settings = await get_settings(db, user_id)
    if settings is None:
        settings = UserSettings(user_id=user_id, tab_order=None)
        db.add(settings)
        await db.flush()
        await db.refresh(settings)
    return settings


async def update_settings(
    db: AsyncSession,
    user_id: int,
    data: UserSettingsUpdate,
) -> UserSettings:
    """Update user settings (creates if not exists)."""
    settings = await get_or_create_settings(db, user_id)

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(settings, field, value)

    # Explicitly update timestamp since TimestampMixin doesn't auto-update
    settings.updated_at = func.clock_timestamp()

    await db.flush()
    await db.refresh(settings)
    return settings


async def get_tab_order(db: AsyncSession, user_id: int) -> TabOrder:
    """
    Get the tab order for a user, returning defaults if not set.

    Returns a properly structured TabOrder with all sections.
    """
    settings = await get_or_create_settings(db, user_id)
    tab_order_dict = _ensure_tab_order_structure(settings.tab_order)
    sections = TabOrderSections(**tab_order_dict["sections"])
    return TabOrder(
        sections=sections,
        section_order=tab_order_dict["section_order"],
    )


async def update_tab_order(
    db: AsyncSession,
    user_id: int,
    tab_order: TabOrder,
) -> UserSettings:
    """
    Update the tab order for a user.

    Args:
        db: Database session.
        user_id: User ID.
        tab_order: The new tab order structure.

    Returns:
        Updated UserSettings.
    """
    settings = await get_or_create_settings(db, user_id)
    settings.tab_order = tab_order.model_dump()
    flag_modified(settings, "tab_order")
    settings.updated_at = func.clock_timestamp()

    await db.flush()
    await db.refresh(settings)
    return settings


async def add_list_to_tab_order(
    db: AsyncSession,
    user_id: int,
    list_id: int,
    content_types: list[str] | None = None,
) -> UserSettings:
    """
    Add a new list to the appropriate section in tab_order.

    The list is placed in a section based on its content_types:
    - ["bookmark"] -> bookmarks section
    - ["note"] -> notes section
    - ["bookmark", "note"] or other -> shared section

    Args:
        db: Database session.
        user_id: User ID.
        list_id: The list ID to add.
        content_types: The content types for the list. Defaults to ["bookmark", "note"].

    Returns:
        Updated UserSettings.
    """
    settings = await get_or_create_settings(db, user_id)

    list_key = f"list:{list_id}"
    if content_types is None:
        content_types = ["bookmark", "note"]

    # Get or create tab order structure (_ensure_tab_order_structure handles the copy)
    tab_order = _ensure_tab_order_structure(settings.tab_order)

    # Check if list already exists in any section
    if _list_key_in_any_section(tab_order, list_key) is not None:
        # List already exists, no change needed
        return settings

    # Determine which section to add the list to
    section = determine_section_for_list(content_types)

    # Prepend to the appropriate section
    tab_order["sections"][section] = [list_key, *tab_order["sections"][section]]

    settings.tab_order = tab_order
    flag_modified(settings, "tab_order")
    settings.updated_at = func.clock_timestamp()

    await db.flush()
    await db.refresh(settings)
    return settings


async def remove_list_from_tab_order(
    db: AsyncSession,
    user_id: int,
    list_id: int,
) -> UserSettings | None:
    """
    Remove a list from tab_order.

    Searches all sections and removes the list from wherever it's found.

    Args:
        db: Database session.
        user_id: User ID.
        list_id: The list ID to remove.

    Returns:
        Updated UserSettings, or None if no settings exist.
    """
    settings = await get_settings(db, user_id)
    if settings is None or settings.tab_order is None:
        return settings

    list_key = f"list:{list_id}"
    # Deep copy to avoid mutation issues with SQLAlchemy JSONB
    tab_order = copy.deepcopy(settings.tab_order)

    # Find and remove from whichever section it's in
    section_name = _list_key_in_any_section(tab_order, list_key)
    if section_name is not None:
        tab_order["sections"][section_name] = [
            t for t in tab_order["sections"][section_name] if t != list_key
        ]
        settings.tab_order = tab_order
        flag_modified(settings, "tab_order")
        settings.updated_at = func.clock_timestamp()

    await db.flush()
    await db.refresh(settings)
    return settings
