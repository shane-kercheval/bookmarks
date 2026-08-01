"""Tests for authentication when DEV_MODE is disabled."""
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings


@pytest.fixture
def non_dev_settings(database_url: str) -> Settings:
    """Create settings with DEV_MODE=False for auth testing."""
    return Settings(
        database_url=database_url,
        dev_mode=False,
        clerk_frontend_api="test-instance.clerk.accounts.dev",
        clerk_authorized_parties_str="http://localhost:5173",
    )


@pytest.fixture
async def auth_required_client(
    async_engine: object,  # noqa: ARG001 - ensures db is created
    db_session: AsyncSession,
    non_dev_settings: Settings,
) -> AsyncClient:
    """Create a test client with auth required (DEV_MODE=False)."""
    from api.main import app  # noqa: PLC0415
    from db.session import get_async_session  # noqa: PLC0415

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


# =============================================================================
# Prompts Authentication Tests
# =============================================================================


async def test__prompts__create_without_token_returns_401(
    auth_required_client: AsyncClient,
) -> None:
    """Test that POST /prompts/ returns 401 when no token is provided."""
    response = await auth_required_client.post(
        "/prompts/",
        json={"name": "test-prompt"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


async def test__prompts__list_without_token_returns_401(
    auth_required_client: AsyncClient,
) -> None:
    """Test that GET /prompts/ returns 401 when no token is provided."""
    response = await auth_required_client.get("/prompts/")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


async def test__prompts__get_without_token_returns_401(
    auth_required_client: AsyncClient,
) -> None:
    """Test that GET /prompts/{id} returns 401 when no token is provided."""
    response = await auth_required_client.get("/prompts/1")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


async def test__prompts__get_by_name_without_token_returns_401(
    auth_required_client: AsyncClient,
) -> None:
    """Test that GET /prompts/name/{name} returns 401 when no token is provided."""
    response = await auth_required_client.get("/prompts/name/test-prompt")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"
