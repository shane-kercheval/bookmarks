"""Pytest fixtures for testing."""
from collections.abc import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
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
    """Get the database URL from the container."""
    return postgres_container.get_connection_url()


@pytest.fixture
async def async_engine(database_url: str) -> AsyncGenerator[AsyncEngine]:
    """Create an async engine for testing."""
    engine = create_async_engine(database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def db_session(async_engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    """Create an async session for testing."""
    session_factory = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session


@pytest.fixture
async def client(
    async_engine: AsyncEngine,  # noqa: ARG001 - ensures db is created before client
    db_session: AsyncSession,
) -> AsyncGenerator[AsyncClient]:
    """Create a test client with database session override."""
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
