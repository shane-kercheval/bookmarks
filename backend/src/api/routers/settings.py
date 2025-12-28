"""User settings endpoints."""
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_async_session, get_current_user_auth0_only
from models.user import User
from schemas.user_settings import (
    SectionName,
    TabOrder,
    UserSettingsResponse,
    UserSettingsUpdate,
)
from services import content_list_service, settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


class TabOrderItem(BaseModel):
    """A single item in the computed tab order."""

    key: str  # "all", "all-bookmarks", "all-notes", "archived", "trash", or "list:{id}"
    label: str  # Display name
    type: Literal["builtin", "list"]  # Item type


class TabOrderSection(BaseModel):
    """A section in the computed tab order."""

    name: SectionName  # "shared", "bookmarks", or "notes"
    label: str  # Display label
    items: list[TabOrderItem]
    collapsible: bool  # Whether this section can be collapsed


class ComputedTabOrderResponse(BaseModel):
    """Computed tab order with resolved list names, organized by sections."""

    sections: list[TabOrderSection]
    section_order: list[SectionName]


# Labels for built-in tabs
BUILTIN_TAB_LABELS = {
    "all": "All",
    "all-bookmarks": "All Bookmarks",
    "all-notes": "All Notes",
    "archived": "Archived",
    "trash": "Trash",
}

# Labels for sections
SECTION_LABELS = {
    "shared": "Shared",
    "bookmarks": "Bookmarks",
    "notes": "Notes",
}

# Collapsible sections (type-specific sections can collapse)
COLLAPSIBLE_SECTIONS = {"bookmarks", "notes"}


@router.get("/", response_model=UserSettingsResponse)
async def get_settings(
    current_user: User = Depends(get_current_user_auth0_only),
    db: AsyncSession = Depends(get_async_session),
) -> UserSettingsResponse:
    """
    Get user settings.

    **Authentication: Auth0 only (PATs not accepted - returns 403)**

    Creates default settings if none exist.
    """
    settings = await settings_service.get_or_create_settings(db, current_user.id)
    return UserSettingsResponse.model_validate(settings)


@router.patch("/", response_model=UserSettingsResponse)
async def update_settings(
    data: UserSettingsUpdate,
    current_user: User = Depends(get_current_user_auth0_only),
    db: AsyncSession = Depends(get_async_session),
) -> UserSettingsResponse:
    """
    Update user settings.

    **Authentication: Auth0 only (PATs not accepted - returns 403)**
    """
    settings = await settings_service.update_settings(db, current_user.id, data)
    return UserSettingsResponse.model_validate(settings)


@router.get("/tab-order", response_model=ComputedTabOrderResponse)
async def get_computed_tab_order(
    current_user: User = Depends(get_current_user_auth0_only),
    db: AsyncSession = Depends(get_async_session),
) -> ComputedTabOrderResponse:
    """
    Get the computed tab order with resolved list names, organized by sections.

    **Authentication: Auth0 only (PATs not accepted - returns 403)**

    Returns the full tab order organized into sections:
    - Shared: Cross-type items (All, Archived, Trash) + mixed-content lists
    - Bookmarks: Bookmark-specific items + bookmark-only lists
    - Notes: Note-specific items + note-only lists

    Invalid list references (deleted lists) are filtered out.
    Lists not in tab_order are appended to the appropriate section based on content_types.
    """
    tab_order = await settings_service.get_tab_order(db, current_user.id)
    lists = await content_list_service.get_lists(db, current_user.id)

    # Build maps for list data
    list_name_map = {f"list:{lst.id}": lst.name for lst in lists}
    list_content_types_map = {f"list:{lst.id}": lst.content_types for lst in lists}

    # Track which lists we've seen
    seen_list_keys: set[str] = set()

    def build_section_items(section_keys: list[str]) -> list[TabOrderItem]:
        """Build list of TabOrderItem for a section's keys."""
        items = []
        for key in section_keys:
            if key in BUILTIN_TAB_LABELS:
                items.append(TabOrderItem(
                    key=key,
                    label=BUILTIN_TAB_LABELS[key],
                    type="builtin",
                ))
            elif key.startswith("list:") and key in list_name_map:
                items.append(TabOrderItem(
                    key=key,
                    label=list_name_map[key],
                    type="list",
                ))
                seen_list_keys.add(key)
            # Invalid keys (deleted lists) are silently filtered out
        return items

    # Build sections in order
    sections_data = {
        "shared": tab_order.sections.shared,
        "bookmarks": tab_order.sections.bookmarks,
        "notes": tab_order.sections.notes,
    }

    result_sections = []
    for section_name in tab_order.section_order:
        section_keys = sections_data.get(section_name, [])
        items = build_section_items(section_keys)
        result_sections.append(TabOrderSection(
            name=section_name,
            label=SECTION_LABELS.get(section_name, section_name.title()),
            items=items,
            collapsible=section_name in COLLAPSIBLE_SECTIONS,
        ))

    # Append any orphaned lists to the appropriate section
    for list_key, name in list_name_map.items():
        if list_key not in seen_list_keys:
            # Determine which section based on content_types
            content_types = list_content_types_map.get(list_key, ["bookmark", "note"])
            target_section = settings_service.determine_section_for_list(content_types)

            # Find and update the section
            for section in result_sections:
                if section.name == target_section:
                    section.items.append(TabOrderItem(
                        key=list_key,
                        label=name,
                        type="list",
                    ))
                    break

    return ComputedTabOrderResponse(
        sections=result_sections,
        section_order=tab_order.section_order,
    )


@router.get("/tab-order/raw", response_model=TabOrder)
async def get_raw_tab_order(
    current_user: User = Depends(get_current_user_auth0_only),
    db: AsyncSession = Depends(get_async_session),
) -> TabOrder:
    """
    Get the raw tab order structure without list name resolution.

    **Authentication: Auth0 only (PATs not accepted - returns 403)**

    Returns the raw tab order structure that can be used for updating.
    """
    return await settings_service.get_tab_order(db, current_user.id)


@router.put("/tab-order", response_model=TabOrder)
async def update_tab_order(
    tab_order: TabOrder,
    current_user: User = Depends(get_current_user_auth0_only),
    db: AsyncSession = Depends(get_async_session),
) -> TabOrder:
    """
    Update the tab order structure.

    **Authentication: Auth0 only (PATs not accepted - returns 403)**

    Replaces the entire tab order with the provided structure.
    """
    await settings_service.update_tab_order(db, current_user.id, tab_order)
    return await settings_service.get_tab_order(db, current_user.id)
