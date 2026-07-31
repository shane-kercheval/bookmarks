"""Tests for settings service layer functionality."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.tier_limits import Tier
from models.user import User
from models.user_settings import UserSettings
from services.settings_service import (
    get_or_create_settings,
    get_settings,
)


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(external_auth_id="test-settings-user-123", email="settings@example.com", tier=Tier.FREE.value)
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
    settings = UserSettings(user_id=test_user.id)
    db_session.add(settings)
    await db_session.flush()

    result = await get_settings(db_session, test_user.id)

    assert result is not None
    assert result.user_id == test_user.id


# =============================================================================
# get_or_create_settings Tests
# =============================================================================


async def test__get_or_create_settings__creates_when_not_exists(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that get_or_create creates settings when none exist."""
    result = await get_or_create_settings(db_session, test_user.id)

    assert result is not None
    assert result.user_id == test_user.id


async def test__get_or_create_settings__returns_existing(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that get_or_create returns existing settings without modification."""
    sidebar_order = {"version": 1, "items": [{"type": "builtin", "key": "all"}]}
    settings = UserSettings(user_id=test_user.id, sidebar_order=sidebar_order)
    db_session.add(settings)
    await db_session.flush()

    result = await get_or_create_settings(db_session, test_user.id)

    assert result.sidebar_order == sidebar_order


# =============================================================================
# Cascade Delete Tests
# =============================================================================


async def test__user_delete__cascades_to_settings(
    db_session: AsyncSession,
) -> None:
    """Test that deleting a user cascades to delete their settings."""
    user = User(external_auth_id="cascade-test-user", email="cascade@example.com", tier=Tier.FREE.value)
    db_session.add(user)
    await db_session.flush()

    settings = UserSettings(user_id=user.id)
    db_session.add(settings)
    await db_session.flush()

    # Delete user
    await db_session.delete(user)
    await db_session.flush()

    # Settings should be gone
    result = await get_settings(db_session, user.id)
    assert result is None
