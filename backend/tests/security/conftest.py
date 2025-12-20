"""
Security test fixtures.

These fixtures enable testing security scenarios like IDOR (Insecure Direct
Object Reference) by creating multiple users and their associated data.

Note: These tests use DEV_MODE which is set at session level in conftest.py.
Authentication enforcement tests should be run against the deployed environment
or with a separate test configuration.
"""
from collections.abc import AsyncGenerator
from collections.abc import Callable
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from models.bookmark import Bookmark
from models.user import User
from services.url_scraper import FetchResult


@pytest.fixture
async def user_a(db_session: AsyncSession) -> User:
    """Create the first test user (User A)."""
    user = User(auth0_id="auth0|user-a", email="user-a@test.com")
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def user_b(db_session: AsyncSession) -> User:
    """Create a second test user (User B) for IDOR testing."""
    user = User(auth0_id="auth0|user-b", email="user-b@test.com")
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def user_a_bookmark(db_session: AsyncSession, user_a: User) -> Bookmark:
    """Create a bookmark belonging to User A."""
    bookmark = Bookmark(
        user_id=user_a.id,
        url="https://user-a-bookmark.example.com/",
        title="User A's Private Bookmark",
        description="This should only be accessible to User A",
    )
    db_session.add(bookmark)
    await db_session.flush()
    await db_session.refresh(bookmark)
    return bookmark


@pytest.fixture
async def user_b_bookmark(db_session: AsyncSession, user_b: User) -> Bookmark:
    """Create a bookmark belonging to User B."""
    bookmark = Bookmark(
        user_id=user_b.id,
        url="https://user-b-bookmark.example.com/",
        title="User B's Private Bookmark",
        description="This should only be accessible to User B",
    )
    db_session.add(bookmark)
    await db_session.flush()
    await db_session.refresh(bookmark)
    return bookmark


@pytest.fixture
def client_factory(
    db_session: AsyncSession,
) -> Callable[[User], AsyncClient]: # type: ignore
    """
    Factory fixture that creates test clients authenticated as a specific user.

    Usage:
        client = client_factory(user_a)
        response = await client.get("/bookmarks/")
    """
    from core.config import get_settings

    get_settings.cache_clear()

    from api.main import app
    from core.auth import get_current_user
    from db.session import get_async_session

    async def override_get_async_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_async_session] = override_get_async_session

    def create_client(user: User) -> AsyncClient:
        async def override_get_current_user() -> User:
            return user

        app.dependency_overrides[get_current_user] = override_get_current_user
        return AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        )

    yield create_client

    app.dependency_overrides.clear()


@pytest.fixture
async def client_as_user_a(
    db_session: AsyncSession,
    user_a: User,
) -> AsyncGenerator[AsyncClient]:
    """Create a test client authenticated as User A."""
    from core.config import get_settings

    get_settings.cache_clear()

    from api.main import app
    from core.auth import get_current_user
    from db.session import get_async_session

    async def override_get_async_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    async def override_get_current_user() -> User:
        return user_a

    app.dependency_overrides[get_async_session] = override_get_async_session
    app.dependency_overrides[get_current_user] = override_get_current_user

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
async def client_as_user_b(
    db_session: AsyncSession,
    user_b: User,
) -> AsyncGenerator[AsyncClient]:
    """Create a test client authenticated as User B."""
    from core.config import get_settings

    get_settings.cache_clear()

    from api.main import app
    from core.auth import get_current_user
    from db.session import get_async_session

    async def override_get_async_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    async def override_get_current_user() -> User:
        return user_b

    app.dependency_overrides[get_async_session] = override_get_async_session
    app.dependency_overrides[get_current_user] = override_get_current_user

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def mock_url_fetch_security() -> AsyncGenerator[AsyncMock]: # type: ignore
    """Mock fetch_url for security tests to avoid network calls."""
    mock_result = FetchResult(
        html=None,
        final_url='',
        status_code=None,
        content_type=None,
        error='Mocked - no network call',
    )
    with patch(
        'services.bookmark_service.fetch_url',
        new_callable=AsyncMock,
        return_value=mock_result,
    ) as mock:
        yield mock
