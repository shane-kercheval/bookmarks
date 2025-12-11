"""Tests for user authentication endpoints."""
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import User


async def test_get_me_in_dev_mode_returns_dev_user(client: AsyncClient) -> None:
    """Test that /users/me returns dev user when DEV_MODE=true."""
    response = await client.get("/users/me")
    assert response.status_code == 200

    data = response.json()
    assert data["auth0_id"] == "dev|local-development-user"
    assert data["email"] == "dev@localhost"


async def test_get_me_creates_user_on_first_request(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test that user is created in database on first authenticated request."""
    # Make request
    response = await client.get("/users/me")
    assert response.status_code == 200

    # Verify user was created in database
    result = await db_session.execute(
        select(User).where(User.auth0_id == "dev|local-development-user"),
    )
    user = result.scalar_one_or_none()
    assert user is not None
    assert user.email == "dev@localhost"


async def test_get_me_returns_same_user_on_subsequent_requests(
    client: AsyncClient,
) -> None:
    """Test that the same user is returned on multiple requests."""
    response1 = await client.get("/users/me")
    response2 = await client.get("/users/me")

    assert response1.status_code == 200
    assert response2.status_code == 200

    data1 = response1.json()
    data2 = response2.json()

    # Same user ID should be returned
    assert data1["id"] == data2["id"]


async def test_get_me_response_structure(client: AsyncClient) -> None:
    """Test that /users/me returns expected response structure."""
    response = await client.get("/users/me")
    assert response.status_code == 200

    data = response.json()
    assert "id" in data
    assert "auth0_id" in data
    assert "email" in data
    assert isinstance(data["id"], int)
    assert isinstance(data["auth0_id"], str)
