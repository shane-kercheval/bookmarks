"""Tests for settings service layer functionality."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import User
from models.user_settings import UserSettings
from schemas.user_settings import UserSettingsUpdate
from services.settings_service import (
    add_list_to_tab_order,
    get_or_create_settings,
    get_settings,
    remove_list_from_tab_order,
    update_settings,
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
    settings = UserSettings(user_id=test_user.id, tab_order=["all", "archived", "trash"])
    db_session.add(settings)
    await db_session.flush()

    result = await get_settings(db_session, test_user.id)

    assert result is not None
    assert result.user_id == test_user.id
    assert result.tab_order == ["all", "archived", "trash"]


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
    settings = UserSettings(user_id=test_user.id, tab_order=["list:1", "all"])
    db_session.add(settings)
    await db_session.flush()

    result = await get_or_create_settings(db_session, test_user.id)

    assert result.tab_order == ["list:1", "all"]


# =============================================================================
# update_settings Tests
# =============================================================================


async def test__update_settings__creates_and_updates_when_not_exists(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that update_settings creates settings if none exist."""
    update_data = UserSettingsUpdate(tab_order=["list:5", "all", "archived", "trash"])

    result = await update_settings(db_session, test_user.id, update_data)

    assert result.user_id == test_user.id
    assert result.tab_order == ["list:5", "all", "archived", "trash"]


async def test__update_settings__updates_existing(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that update_settings updates existing settings."""
    settings = UserSettings(user_id=test_user.id, tab_order=["all", "archived", "trash"])
    db_session.add(settings)
    await db_session.flush()

    update_data = UserSettingsUpdate(tab_order=["trash", "all", "archived"])
    result = await update_settings(db_session, test_user.id, update_data)

    assert result.tab_order == ["trash", "all", "archived"]


async def test__update_settings__ignores_unset_fields(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that update_settings only updates fields that are set."""
    settings = UserSettings(user_id=test_user.id, tab_order=["all", "archived"])
    db_session.add(settings)
    await db_session.flush()

    # Empty update should not change anything
    update_data = UserSettingsUpdate()
    result = await update_settings(db_session, test_user.id, update_data)

    assert result.tab_order == ["all", "archived"]


# =============================================================================
# add_list_to_tab_order Tests
# =============================================================================


async def test__add_list_to_tab_order__creates_default_with_list_prepended(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test adding list when no settings exist creates default order with list first."""
    result = await add_list_to_tab_order(db_session, test_user.id, 42)

    assert result.tab_order == ["list:42", "all", "archived", "trash"]


async def test__add_list_to_tab_order__prepends_to_existing(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test adding list prepends to existing tab order."""
    settings = UserSettings(user_id=test_user.id, tab_order=["all", "archived", "trash"])
    db_session.add(settings)
    await db_session.flush()

    result = await add_list_to_tab_order(db_session, test_user.id, 99)

    assert result.tab_order == ["list:99", "all", "archived", "trash"]


async def test__add_list_to_tab_order__does_not_duplicate(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test adding list that already exists does not create duplicate."""
    settings = UserSettings(
        user_id=test_user.id,
        tab_order=["list:10", "all", "archived", "trash"],
    )
    db_session.add(settings)
    await db_session.flush()

    result = await add_list_to_tab_order(db_session, test_user.id, 10)

    assert result.tab_order == ["list:10", "all", "archived", "trash"]


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


async def test__remove_list_from_tab_order__removes_existing_list(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test removing list from tab order."""
    settings = UserSettings(
        user_id=test_user.id,
        tab_order=["list:5", "all", "list:10", "archived", "trash"],
    )
    db_session.add(settings)
    await db_session.flush()

    result = await remove_list_from_tab_order(db_session, test_user.id, 5)

    assert result is not None
    assert result.tab_order == ["all", "list:10", "archived", "trash"]


async def test__remove_list_from_tab_order__handles_nonexistent_list(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test removing list that doesn't exist in tab order is a no-op."""
    settings = UserSettings(
        user_id=test_user.id,
        tab_order=["all", "archived", "trash"],
    )
    db_session.add(settings)
    await db_session.flush()

    result = await remove_list_from_tab_order(db_session, test_user.id, 999)

    assert result is not None
    assert result.tab_order == ["all", "archived", "trash"]


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
    settings = UserSettings(user_id=test_user.id, tab_order=["all", "archived"])
    db_session.add(settings)
    await db_session.flush()
    await db_session.refresh(settings)
    original_updated_at = settings.updated_at

    # Update settings
    update_data = UserSettingsUpdate(tab_order=["trash", "all", "archived"])
    result = await update_settings(db_session, test_user.id, update_data)

    assert result.updated_at > original_updated_at


async def test__add_list_to_tab_order__updates_timestamp(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that add_list_to_tab_order updates the updated_at timestamp."""
    # Create settings first
    settings = UserSettings(user_id=test_user.id, tab_order=["all", "archived", "trash"])
    db_session.add(settings)
    await db_session.flush()
    await db_session.refresh(settings)
    original_updated_at = settings.updated_at

    # Add a list
    result = await add_list_to_tab_order(db_session, test_user.id, 42)

    assert result.updated_at > original_updated_at


async def test__remove_list_from_tab_order__updates_timestamp(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that remove_list_from_tab_order updates the updated_at timestamp."""
    # Create settings with a list
    settings = UserSettings(
        user_id=test_user.id,
        tab_order=["list:5", "all", "archived", "trash"],
    )
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
    """Test that remove_list_from_tab_order does not update timestamp when list isn't in tab_order."""
    # Create settings without the list we'll try to remove
    settings = UserSettings(
        user_id=test_user.id,
        tab_order=["all", "archived", "trash"],
    )
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

    settings = UserSettings(user_id=user.id, tab_order=["all", "archived", "trash"])
    db_session.add(settings)
    await db_session.flush()

    # Delete user
    await db_session.delete(user)
    await db_session.flush()

    # Settings should be gone
    result = await get_settings(db_session, user.id)
    assert result is None
