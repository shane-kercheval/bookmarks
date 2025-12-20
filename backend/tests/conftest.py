"""Pytest fixtures for testing."""
import os
from collections.abc import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from models.base import Base


@pytest.fixture(scope="session")
def postgres_container() -> Generator[PostgresContainer]:
    """Start a PostgreSQL container for the test session."""
    with PostgresContainer("postgres:16", driver="asyncpg") as postgres:
        yield postgres


@pytest.fixture(scope="session")
def database_url(postgres_container: PostgresContainer) -> str:
    """
    Get the database URL from the container and set it in environment.

    This must be set before any app imports that trigger Settings validation.
    """
    url = postgres_container.get_connection_url()
    os.environ["DATABASE_URL"] = url
    # Ensure tests run in dev mode (bypasses auth) regardless of local .env
    os.environ["VITE_DEV_MODE"] = "true"
    return url


@pytest.fixture
async def async_engine(database_url: str) -> AsyncGenerator[AsyncEngine]:
    """Create an async engine for testing."""
    engine = create_async_engine(database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest.fixture
async def db_connection(async_engine: AsyncEngine) -> AsyncGenerator[AsyncConnection]:
    """
    Create a connection with a transaction that will be rolled back after the test.

    This provides test isolation - each test runs in its own transaction
    that is rolled back, so tests don't affect each other.
    """
    async with async_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            yield connection
        finally:
            await transaction.rollback()


@pytest.fixture
async def db_session(db_connection: AsyncConnection) -> AsyncGenerator[AsyncSession]:
    """
    Create an async session bound to the test transaction.

    Uses begin_nested() for savepoints, allowing the session's flush/commit
    to work within our outer test transaction.
    """
    session_factory = async_sessionmaker(
        bind=db_connection,
        class_=AsyncSession,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    async with session_factory() as session:
        yield session


@pytest.fixture
async def client(
    db_session: AsyncSession,
) -> AsyncGenerator[AsyncClient]:
    """Create a test client with database session override."""
    # Clear the settings cache so it picks up DATABASE_URL from environment
    from core.config import get_settings

    get_settings.cache_clear()

    from api.main import app
    from db.session import get_async_session

    async def override_get_async_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_async_session] = override_get_async_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()
