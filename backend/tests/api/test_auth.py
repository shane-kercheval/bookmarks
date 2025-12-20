"""Tests for authentication when DEV_MODE is disabled."""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings


@pytest.fixture
def non_dev_settings(database_url: str) -> Settings:
    """Create settings with DEV_MODE=False for auth testing."""
    return Settings(
        database_url=database_url,
        dev_mode=False,
        auth0_domain="test.auth0.com",
        auth0_audience="https://test-api",
        auth0_client_id="test-client-id",
    )


@pytest.fixture
async def auth_required_client(
    async_engine: object,  # noqa: ARG001 - ensures db is created
    db_session: AsyncSession,
    non_dev_settings: Settings,
) -> AsyncClient:
    """Create a test client with auth required (DEV_MODE=False)."""
    from collections.abc import AsyncGenerator

    from api.main import app
    from core.config import get_settings
    from db.session import get_async_session

    async def override_get_async_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    def override_get_settings() -> Settings:
        return non_dev_settings

    app.dependency_overrides[get_async_session] = override_get_async_session
    app.dependency_overrides[get_settings] = override_get_settings

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()


async def test_get_me_without_token_returns_401(
    auth_required_client: AsyncClient,
) -> None:
    """Test that /users/me returns 401 when no token is provided."""
    response = await auth_required_client.get("/users/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


async def test_get_me_with_invalid_token_returns_401(
    auth_required_client: AsyncClient,
) -> None:
    """Test that /users/me returns 401 with invalid token."""
    response = await auth_required_client.get(
        "/users/me",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 401


async def test_invalid_token_returns_generic_error_message(
    auth_required_client: AsyncClient,
) -> None:
    """Test that invalid JWT returns generic error without leaking implementation details."""
    response = await auth_required_client.get(
        "/users/me",
        headers={"Authorization": "Bearer invalid-malformed-token"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid token"
    # Ensure no exception details are leaked
    assert "PyJWT" not in response.json()["detail"]
    assert "segments" not in response.json()["detail"]
    assert "padding" not in response.json()["detail"]


async def test_health_endpoint_does_not_require_auth(
    auth_required_client: AsyncClient,
) -> None:
    """Test that /health endpoint works without authentication."""
    response = await auth_required_client.get("/health")
    assert response.status_code == 200
