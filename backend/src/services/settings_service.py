"""Service layer for user settings operations."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.user_settings import UserSettings
from schemas.user_settings import UserSettingsUpdate


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


async def add_list_to_tab_order(
    db: AsyncSession,
    user_id: int,
    list_id: int,
) -> UserSettings:
    """Add a new list to the beginning of tab_order."""
    settings = await get_or_create_settings(db, user_id)

    list_key = f"list:{list_id}"
    if settings.tab_order is None:
        # Default order with new list prepended
        settings.tab_order = [list_key, "all", "archived", "trash"]
    elif list_key not in settings.tab_order:
        # Prepend to existing order (if not already present)
        settings.tab_order = [list_key, *settings.tab_order]

    # Explicitly update timestamp since TimestampMixin doesn't auto-update
    settings.updated_at = func.clock_timestamp()

    await db.flush()
    await db.refresh(settings)
    return settings


async def remove_list_from_tab_order(
    db: AsyncSession,
    user_id: int,
    list_id: int,
) -> UserSettings | None:
    """Remove a list from tab_order. Returns None if no settings exist."""
    settings = await get_settings(db, user_id)
    if settings is None or settings.tab_order is None:
        return settings

    list_key = f"list:{list_id}"
    if list_key in settings.tab_order:
        settings.tab_order = [t for t in settings.tab_order if t != list_key]
        # Explicitly update timestamp since TimestampMixin doesn't auto-update
        settings.updated_at = func.clock_timestamp()

    await db.flush()
    await db.refresh(settings)
    return settings
