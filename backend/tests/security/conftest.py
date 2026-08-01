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

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from models.bookmark import Bookmark
from models.note import Note
from models.prompt import Prompt
from models.user import User
from core.tier_limits import Tier


@pytest.fixture
async def user_a(db_session: AsyncSession) -> User:
    """Create the first test user (User A)."""
    user = User(external_auth_id="legacy|user-a", email="user-a@test.com", tier=Tier.FREE.value)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def user_b(db_session: AsyncSession) -> User:
    """Create a second test user (User B) for IDOR testing."""
    user = User(external_auth_id="legacy|user-b", email="user-b@test.com", tier=Tier.FREE.value)
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
async def user_a_note(db_session: AsyncSession, user_a: User) -> Note:
    """Create a note belonging to User A."""
    note = Note(
        user_id=user_a.id,
        title="User A's Private Note",
        description="This should only be accessible to User A",
        content="Private note content for User A",
    )
    db_session.add(note)
    await db_session.flush()
    await db_session.refresh(note)
    return note


@pytest.fixture
async def user_b_note(db_session: AsyncSession, user_b: User) -> Note:
    """Create a note belonging to User B."""
    note = Note(
        user_id=user_b.id,
        title="User B's Private Note",
        description="This should only be accessible to User B",
        content="Private note content for User B",
    )
    db_session.add(note)
    await db_session.flush()
    await db_session.refresh(note)
    return note


@pytest.fixture
async def user_a_prompt(db_session: AsyncSession, user_a: User) -> Prompt:
    """Create a prompt belonging to User A."""
    prompt = Prompt(
        user_id=user_a.id,
        name="user-a-private-prompt",
        title="User A's Private Prompt",
        description="This should only be accessible to User A",
        content="Private prompt content for User A: {{ variable }}",
        arguments=[{"name": "variable", "description": "A test variable", "required": True}],
    )
    db_session.add(prompt)
    await db_session.flush()
    await db_session.refresh(prompt)
    return prompt


@pytest.fixture
async def user_b_prompt(db_session: AsyncSession, user_b: User) -> Prompt:
    """Create a prompt belonging to User B."""
    prompt = Prompt(
        user_id=user_b.id,
        name="user-b-private-prompt",
        title="User B's Private Prompt",
        description="This should only be accessible to User B",
        content="Private prompt content for User B: {{ variable }}",
        arguments=[{"name": "variable", "description": "A test variable", "required": True}],
    )
    db_session.add(prompt)
    await db_session.flush()
    await db_session.refresh(prompt)
    return prompt


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
    get_settings.cache_clear()

    from api.main import app  # noqa: PLC0415
    from core.auth import get_current_user  # noqa: PLC0415
    from db.session import get_async_session  # noqa: PLC0415

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
    get_settings.cache_clear()

    from api.main import app  # noqa: PLC0415
    from core.auth import get_current_user  # noqa: PLC0415
    from db.session import get_async_session  # noqa: PLC0415

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
    get_settings.cache_clear()

    from api.main import app  # noqa: PLC0415
    from core.auth import get_current_user  # noqa: PLC0415
    from db.session import get_async_session  # noqa: PLC0415

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
