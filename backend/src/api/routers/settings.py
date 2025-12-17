"""User settings endpoints."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_async_session, get_current_user
from models.user import User
from schemas.user_settings import UserSettingsResponse, UserSettingsUpdate
from services import bookmark_list_service, settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


class TabOrderItem(BaseModel):
    """A single item in the computed tab order."""

    key: str  # "all", "archived", "trash", or "list:{id}"
    label: str  # Display name
    type: str  # "builtin" or "list"


class TabOrderResponse(BaseModel):
    """Computed tab order with resolved list names."""

    items: list[TabOrderItem]


# Default tab order when user has no custom order
DEFAULT_TAB_ORDER = ["all", "archived", "trash"]

# Labels for built-in tabs
BUILTIN_TAB_LABELS = {
    "all": "All Bookmarks",
    "archived": "Archived",
    "trash": "Trash",
}


@router.get("/", response_model=UserSettingsResponse)
async def get_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> UserSettingsResponse:
    """
    Get user settings.

    Creates default settings if none exist.
    """
    settings = await settings_service.get_or_create_settings(db, current_user.id)
    return UserSettingsResponse.model_validate(settings)


@router.patch("/", response_model=UserSettingsResponse)
async def update_settings(
    data: UserSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> UserSettingsResponse:
    """Update user settings."""
    settings = await settings_service.update_settings(db, current_user.id, data)
    return UserSettingsResponse.model_validate(settings)


@router.get("/tab-order", response_model=TabOrderResponse)
async def get_tab_order(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> TabOrderResponse:
    """
    Get the computed tab order with resolved list names.

    Returns the full tab order including:
    - Built-in tabs (All Bookmarks, Archived, Trash)
    - Custom lists with their names

    Invalid list references (deleted lists) are filtered out.
    Lists not in tab_order are appended at the end.
    """
    settings = await settings_service.get_or_create_settings(db, current_user.id)
    lists = await bookmark_list_service.get_lists(db, current_user.id)

    # Build a map of list IDs to names
    list_map = {f"list:{lst.id}": lst.name for lst in lists}

    # Get the tab order, defaulting if not set
    tab_order = settings.tab_order or DEFAULT_TAB_ORDER

    items = []
    seen_list_keys = set()

    for key in tab_order:
        if key in BUILTIN_TAB_LABELS:
            items.append(TabOrderItem(
                key=key,
                label=BUILTIN_TAB_LABELS[key],
                type="builtin",
            ))
        elif key.startswith("list:") and key in list_map:
            items.append(TabOrderItem(
                key=key,
                label=list_map[key],
                type="list",
            ))
            seen_list_keys.add(key)
        # Invalid keys (deleted lists) are silently filtered out

    # Append any lists not in tab_order (newly created lists that somehow
    # weren't added, or edge cases)
    for key, name in list_map.items():
        if key not in seen_list_keys:
            items.append(TabOrderItem(
                key=key,
                label=name,
                type="list",
            ))

    return TabOrderResponse(items=items)
