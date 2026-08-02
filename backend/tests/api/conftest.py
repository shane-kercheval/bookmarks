"""Shared fixtures for API tests."""
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from models.user import User
from core.tier_limits import Tier, get_tier_limits
from schemas.token import TokenCreate
from services.token_service import create_token

_DEV_LIMITS = get_tier_limits(Tier.DEV)


@asynccontextmanager
async def create_user2_client(
    db_session: AsyncSession,
    external_auth_id: str,
    email: str,
) -> AsyncGenerator[AsyncClient]:
    """
    Create an authenticated AsyncClient for a second user via PAT.

    Sets up a new user with a PAT, overrides FastAPI dependencies
    to disable dev_mode, and yields an AsyncClient authenticated as that user.
    Cleans up dependency overrides on exit.
    """
    # Deferred imports: api.main and db.session trigger module-level get_settings()
    # which requires DATABASE_URL. In CI, that env var is only set by the database_url
    # fixture at runtime, so importing at module level causes collection errors.
    from api.main import app  # noqa: PLC0415
    from db.session import get_async_session  # noqa: PLC0415

    user2 = User(external_auth_id=external_auth_id, email=email, tier=Tier.FREE.value)
    db_session.add(user2)
    await db_session.flush()

    _, user2_token = await create_token(
        db_session, user2.id, TokenCreate(name='Test Token'), _DEV_LIMITS,
    )
    await db_session.flush()

    get_settings.cache_clear()

    async def override_get_async_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    def override_get_settings() -> Settings:
        return Settings(
            database_url='postgresql://test',
            dev_mode=False,
            clerk_frontend_api="test-instance.clerk.accounts.dev",
            clerk_authorized_parties_str="http://localhost:5173",
        )

    app.dependency_overrides[get_async_session] = override_get_async_session
    app.dependency_overrides[get_settings] = override_get_settings

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url='http://test',
            headers={'Authorization': f'Bearer {user2_token}'},
        ) as user2_client:
            yield user2_client
    finally:
        app.dependency_overrides.clear()


# Constant for non-existent entity ID
FAKE_UUID = "00000000-0000-0000-0000-000000000000"


@pytest.fixture
async def auth_required_client(
    async_engine: object,  # noqa: ARG001 - ensures the schema is created
    db_session: AsyncSession,
    database_url: str,
) -> AsyncGenerator[AsyncClient]:
    """A client with auth enforced (dev_mode disabled, no credentials attached)."""
    from api.main import app  # noqa: PLC0415
    from db.session import get_async_session  # noqa: PLC0415

    async def override_get_async_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    def override_get_settings() -> Settings:
        return Settings(
            database_url=database_url,
            dev_mode=False,
            clerk_frontend_api="test-instance.clerk.accounts.dev",
            clerk_authorized_parties_str="http://localhost:5173",
        )

    app.dependency_overrides[get_async_session] = override_get_async_session
    app.dependency_overrides[get_settings] = override_get_settings
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
    ) as test_client:
        yield test_client
    app.dependency_overrides.clear()
