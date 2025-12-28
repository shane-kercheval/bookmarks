"""Tests for settings service layer functionality."""
import copy

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import User
from models.user_settings import UserSettings
from schemas.user_settings import TabOrder, TabOrderSections, UserSettingsUpdate
from services.settings_service import (
    _ensure_tab_order_structure,
    add_list_to_tab_order,
    determine_section_for_list,
    get_default_tab_order,
    get_or_create_settings,
    get_settings,
    get_tab_order,
    remove_list_from_tab_order,
    update_settings,
    update_tab_order,
)


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(auth0_id="test-settings-user-123", email="settings@example.com")
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


# =============================================================================
# determine_section_for_list Tests
# =============================================================================


def test__determine_section_for_list__bookmark_only_goes_to_bookmarks() -> None:
    """Test that bookmark-only lists go to bookmarks section."""
    result = determine_section_for_list(["bookmark"])
    assert result == "bookmarks"


def test__determine_section_for_list__note_only_goes_to_notes() -> None:
    """Test that note-only lists go to notes section."""
    result = determine_section_for_list(["note"])
    assert result == "notes"


def test__determine_section_for_list__mixed_goes_to_shared() -> None:
    """Test that mixed content type lists go to shared section."""
    result = determine_section_for_list(["bookmark", "note"])
    assert result == "shared"


def test__determine_section_for_list__empty_goes_to_shared() -> None:
    """Test that empty content types go to shared section."""
    result = determine_section_for_list([])
    assert result == "shared"


# =============================================================================
# get_default_tab_order Tests
# =============================================================================


def test__get_default_tab_order__returns_correct_structure() -> None:
    """Test that get_default_tab_order returns the correct default structure."""
    result = get_default_tab_order()

    assert "sections" in result
    assert "section_order" in result
    assert result["sections"]["shared"] == ["all", "archived", "trash"]
    assert result["sections"]["bookmarks"] == ["all-bookmarks"]
    assert result["sections"]["notes"] == ["all-notes"]
    assert result["section_order"] == ["shared", "bookmarks", "notes"]


# =============================================================================
# _ensure_tab_order_structure Tests (Mutation Safety)
# =============================================================================


def test__ensure_tab_order_structure__does_not_mutate_input() -> None:
    """
    Test that _ensure_tab_order_structure does not mutate its input dict.

    This is a regression test for a bug where the function mutated the input
    in-place, which could corrupt SQLAlchemy-tracked JSONB objects.
    """
    # Create an incomplete tab_order structure
    original = {"sections": {"shared": ["all"]}}
    original_copy = copy.deepcopy(original)

    # Call the function
    result = _ensure_tab_order_structure(original)

    # Original should be unchanged
    assert original == original_copy

    # Result should have the filled-in defaults
    assert "bookmarks" in result["sections"]
    assert "notes" in result["sections"]
    assert "section_order" in result


def test__ensure_tab_order_structure__returns_new_dict() -> None:
    """Test that _ensure_tab_order_structure returns a new dict, not the input."""
    original = get_default_tab_order()

    result = _ensure_tab_order_structure(original)

    # Should be a different object
    assert result is not original
    # But with the same content
    assert result == original


# =============================================================================
# get_settings Tests
# =============================================================================


async def test__get_settings__returns_none_when_not_exists(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that get_settings returns None when no settings exist."""
    result = await get_settings(db_session, test_user.id)
    assert result is None


async def test__get_settings__returns_settings_when_exists(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that get_settings returns existing settings."""
    tab_order = get_default_tab_order()
    settings = UserSettings(user_id=test_user.id, tab_order=tab_order)
    db_session.add(settings)
    await db_session.flush()

    result = await get_settings(db_session, test_user.id)

    assert result is not None
    assert result.user_id == test_user.id
    assert result.tab_order == tab_order


# =============================================================================
# get_or_create_settings Tests
# =============================================================================


async def test__get_or_create_settings__creates_when_not_exists(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that get_or_create creates settings with defaults when none exist."""
    result = await get_or_create_settings(db_session, test_user.id)

    assert result is not None
    assert result.user_id == test_user.id
    assert result.tab_order is None  # Default is null


async def test__get_or_create_settings__returns_existing(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that get_or_create returns existing settings without modification."""
    tab_order = get_default_tab_order()
    tab_order["sections"]["bookmarks"].insert(0, "list:1")
    settings = UserSettings(user_id=test_user.id, tab_order=tab_order)
    db_session.add(settings)
    await db_session.flush()

    result = await get_or_create_settings(db_session, test_user.id)

    assert result.tab_order == tab_order


# =============================================================================
# get_tab_order Tests
# =============================================================================


async def test__get_tab_order__returns_defaults_when_no_settings(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that get_tab_order returns defaults when no settings exist."""
    result = await get_tab_order(db_session, test_user.id)

    assert isinstance(result, TabOrder)
    assert result.sections.shared == ["all", "archived", "trash"]
    assert result.sections.bookmarks == ["all-bookmarks"]
    assert result.sections.notes == ["all-notes"]
    assert result.section_order == ["shared", "bookmarks", "notes"]


async def test__get_tab_order__returns_stored_tab_order(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that get_tab_order returns stored tab order."""
    tab_order = get_default_tab_order()
    tab_order["sections"]["bookmarks"].insert(0, "list:5")
    settings = UserSettings(user_id=test_user.id, tab_order=tab_order)
    db_session.add(settings)
    await db_session.flush()

    result = await get_tab_order(db_session, test_user.id)

    assert "list:5" in result.sections.bookmarks


async def test__get_tab_order__does_not_mutate_stored_settings(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """
    Test that get_tab_order does not mutate the stored tab_order.

    This is a regression test for a bug where get_tab_order could mutate the
    SQLAlchemy-tracked JSONB object, potentially causing unintended database writes.
    """
    # Create settings with an incomplete structure (missing some sections)
    incomplete_tab_order = {"sections": {"shared": ["all", "archived", "trash"]}}
    settings = UserSettings(user_id=test_user.id, tab_order=incomplete_tab_order)
    db_session.add(settings)
    await db_session.flush()

    # Store the original value
    original_stored = copy.deepcopy(settings.tab_order)

    # Call get_tab_order (which fills in defaults)
    result = await get_tab_order(db_session, test_user.id)

    # The result should have filled-in defaults
    assert result.sections.bookmarks == ["all-bookmarks"]
    assert result.sections.notes == ["all-notes"]

    # But the stored settings should NOT have been mutated
    await db_session.refresh(settings)
    assert settings.tab_order == original_stored
    assert "bookmarks" not in settings.tab_order["sections"]


# =============================================================================
# update_tab_order Tests
# =============================================================================


async def test__update_tab_order__creates_and_stores(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that update_tab_order creates settings if none exist and stores tab order."""
    tab_order = TabOrder(
        sections=TabOrderSections(
            shared=["archived", "trash", "all"],
            bookmarks=["list:5", "all-bookmarks"],
            notes=["all-notes"],
        ),
        section_order=["bookmarks", "shared", "notes"],
    )

    result = await update_tab_order(db_session, test_user.id, tab_order)

    assert result.user_id == test_user.id
    assert result.tab_order["sections"]["shared"] == ["archived", "trash", "all"]
    assert result.tab_order["section_order"] == ["bookmarks", "shared", "notes"]


# =============================================================================
# update_settings Tests
# =============================================================================


async def test__update_settings__creates_and_updates_when_not_exists(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that update_settings creates settings if none exist."""
    tab_order = TabOrder(
        sections=TabOrderSections(
            shared=["all", "archived", "trash"],
            bookmarks=["list:5", "all-bookmarks"],
            notes=["all-notes"],
        ),
    )
    update_data = UserSettingsUpdate(tab_order=tab_order)

    result = await update_settings(db_session, test_user.id, update_data)

    assert result.user_id == test_user.id
    assert result.tab_order["sections"]["bookmarks"] == ["list:5", "all-bookmarks"]


async def test__update_settings__updates_existing(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that update_settings updates existing settings."""
    initial_tab_order = get_default_tab_order()
    settings = UserSettings(user_id=test_user.id, tab_order=initial_tab_order)
    db_session.add(settings)
    await db_session.flush()

    new_tab_order = TabOrder(
        sections=TabOrderSections(
            shared=["trash", "all", "archived"],
            bookmarks=["all-bookmarks"],
            notes=["all-notes"],
        ),
    )
    update_data = UserSettingsUpdate(tab_order=new_tab_order)
    result = await update_settings(db_session, test_user.id, update_data)

    assert result.tab_order["sections"]["shared"] == ["trash", "all", "archived"]


async def test__update_settings__ignores_unset_fields(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that update_settings only updates fields that are set."""
    tab_order = get_default_tab_order()
    settings = UserSettings(user_id=test_user.id, tab_order=tab_order)
    db_session.add(settings)
    await db_session.flush()

    # Empty update should not change anything
    update_data = UserSettingsUpdate()
    result = await update_settings(db_session, test_user.id, update_data)

    assert result.tab_order == tab_order


# =============================================================================
# add_list_to_tab_order Tests
# =============================================================================


async def test__add_list_to_tab_order__creates_default_with_list_in_shared(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test adding mixed list when no settings creates default with list in shared."""
    result = await add_list_to_tab_order(
        db_session, test_user.id, 42, content_types=["bookmark", "note"],
    )

    assert result.tab_order is not None
    assert "list:42" in result.tab_order["sections"]["shared"]


async def test__add_list_to_tab_order__adds_bookmark_list_to_bookmarks_section(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that bookmark-only list is added to bookmarks section."""
    result = await add_list_to_tab_order(
        db_session, test_user.id, 42, content_types=["bookmark"],
    )

    assert result.tab_order is not None
    assert "list:42" in result.tab_order["sections"]["bookmarks"]
    assert "list:42" not in result.tab_order["sections"]["shared"]


async def test__add_list_to_tab_order__adds_note_list_to_notes_section(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that note-only list is added to notes section."""
    result = await add_list_to_tab_order(
        db_session, test_user.id, 42, content_types=["note"],
    )

    assert result.tab_order is not None
    assert "list:42" in result.tab_order["sections"]["notes"]
    assert "list:42" not in result.tab_order["sections"]["shared"]


async def test__add_list_to_tab_order__prepends_to_existing_section(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test adding list prepends to existing section."""
    tab_order = get_default_tab_order()
    settings = UserSettings(user_id=test_user.id, tab_order=tab_order)
    db_session.add(settings)
    await db_session.flush()

    result = await add_list_to_tab_order(
        db_session, test_user.id, 99, content_types=["bookmark"],
    )

    # List should be prepended (before all-bookmarks)
    assert result.tab_order["sections"]["bookmarks"][0] == "list:99"


async def test__add_list_to_tab_order__does_not_duplicate(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test adding list that already exists does not create duplicate."""
    tab_order = get_default_tab_order()
    tab_order["sections"]["bookmarks"].insert(0, "list:10")
    settings = UserSettings(user_id=test_user.id, tab_order=tab_order)
    db_session.add(settings)
    await db_session.flush()

    result = await add_list_to_tab_order(
        db_session, test_user.id, 10, content_types=["bookmark"],
    )

    # Should only appear once
    count = result.tab_order["sections"]["bookmarks"].count("list:10")
    assert count == 1


async def test__add_list_to_tab_order__defaults_to_shared_when_no_content_types(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that list without explicit content_types goes to shared section."""
    result = await add_list_to_tab_order(db_session, test_user.id, 42)

    assert result.tab_order is not None
    assert "list:42" in result.tab_order["sections"]["shared"]


# =============================================================================
# remove_list_from_tab_order Tests
# =============================================================================


async def test__remove_list_from_tab_order__returns_none_when_no_settings(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test removing list when no settings exist returns None."""
    result = await remove_list_from_tab_order(db_session, test_user.id, 1)
    assert result is None


async def test__remove_list_from_tab_order__removes_from_bookmarks_section(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test removing list from bookmarks section."""
    tab_order = get_default_tab_order()
    tab_order["sections"]["bookmarks"].insert(0, "list:5")
    settings = UserSettings(user_id=test_user.id, tab_order=tab_order)
    db_session.add(settings)
    await db_session.flush()

    result = await remove_list_from_tab_order(db_session, test_user.id, 5)

    assert result is not None
    assert "list:5" not in result.tab_order["sections"]["bookmarks"]


async def test__remove_list_from_tab_order__removes_from_shared_section(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test removing list from shared section."""
    tab_order = get_default_tab_order()
    tab_order["sections"]["shared"].append("list:10")
    settings = UserSettings(user_id=test_user.id, tab_order=tab_order)
    db_session.add(settings)
    await db_session.flush()

    result = await remove_list_from_tab_order(db_session, test_user.id, 10)

    assert result is not None
    assert "list:10" not in result.tab_order["sections"]["shared"]


async def test__remove_list_from_tab_order__handles_nonexistent_list(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test removing list that doesn't exist in tab order is a no-op."""
    tab_order = get_default_tab_order()
    settings = UserSettings(user_id=test_user.id, tab_order=tab_order)
    db_session.add(settings)
    await db_session.flush()

    result = await remove_list_from_tab_order(db_session, test_user.id, 999)

    assert result is not None
    # Tab order should be unchanged
    assert result.tab_order == tab_order


async def test__remove_list_from_tab_order__handles_null_tab_order(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test removing list when tab_order is null returns settings unchanged."""
    settings = UserSettings(user_id=test_user.id, tab_order=None)
    db_session.add(settings)
    await db_session.flush()

    result = await remove_list_from_tab_order(db_session, test_user.id, 1)

    assert result is not None
    assert result.tab_order is None


# =============================================================================
# updated_at Timestamp Tests
# =============================================================================


async def test__update_settings__updates_timestamp(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that update_settings updates the updated_at timestamp."""
    # Create settings first
    tab_order = get_default_tab_order()
    settings = UserSettings(user_id=test_user.id, tab_order=tab_order)
    db_session.add(settings)
    await db_session.flush()
    await db_session.refresh(settings)
    original_updated_at = settings.updated_at

    # Update settings
    new_tab_order = TabOrder(
        sections=TabOrderSections(
            shared=["trash", "all", "archived"],
            bookmarks=["all-bookmarks"],
            notes=["all-notes"],
        ),
    )
    update_data = UserSettingsUpdate(tab_order=new_tab_order)
    result = await update_settings(db_session, test_user.id, update_data)

    assert result.updated_at > original_updated_at


async def test__add_list_to_tab_order__updates_timestamp(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that add_list_to_tab_order updates the updated_at timestamp."""
    # Create settings first
    tab_order = get_default_tab_order()
    settings = UserSettings(user_id=test_user.id, tab_order=tab_order)
    db_session.add(settings)
    await db_session.flush()
    await db_session.refresh(settings)
    original_updated_at = settings.updated_at

    # Add a list
    result = await add_list_to_tab_order(
        db_session, test_user.id, 42, content_types=["bookmark"],
    )

    assert result.updated_at > original_updated_at


async def test__remove_list_from_tab_order__updates_timestamp(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that remove_list_from_tab_order updates the updated_at timestamp."""
    # Create settings with a list
    tab_order = get_default_tab_order()
    tab_order["sections"]["bookmarks"].insert(0, "list:5")
    settings = UserSettings(user_id=test_user.id, tab_order=tab_order)
    db_session.add(settings)
    await db_session.flush()
    await db_session.refresh(settings)
    original_updated_at = settings.updated_at

    # Remove the list
    result = await remove_list_from_tab_order(db_session, test_user.id, 5)

    assert result is not None
    assert result.updated_at > original_updated_at


async def test__remove_list_from_tab_order__does_not_update_timestamp_when_list_not_present(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test remove_list_from_tab_order does not update timestamp when list isn't present."""
    # Create settings without the list we'll try to remove
    tab_order = get_default_tab_order()
    settings = UserSettings(user_id=test_user.id, tab_order=tab_order)
    db_session.add(settings)
    await db_session.flush()
    await db_session.refresh(settings)
    original_updated_at = settings.updated_at

    # Try to remove a list that doesn't exist
    result = await remove_list_from_tab_order(db_session, test_user.id, 999)

    assert result is not None
    # Timestamp should NOT be updated since no change was made
    assert result.updated_at == original_updated_at


# =============================================================================
# Cascade Delete Tests
# =============================================================================


async def test__user_delete__cascades_to_settings(
    db_session: AsyncSession,
) -> None:
    """Test that deleting a user cascades to delete their settings."""
    user = User(auth0_id="cascade-test-user", email="cascade@example.com")
    db_session.add(user)
    await db_session.flush()

    tab_order = get_default_tab_order()
    settings = UserSettings(user_id=user.id, tab_order=tab_order)
    db_session.add(settings)
    await db_session.flush()

    # Delete user
    await db_session.delete(user)
    await db_session.flush()

    # Settings should be gone
    result = await get_settings(db_session, user.id)
    assert result is None
