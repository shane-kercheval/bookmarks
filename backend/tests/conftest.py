"""Pytest fixtures for testing."""
import asyncio
import os
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import patch

if TYPE_CHECKING:
    from models.user import User

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from core.auth_cache import AuthCache, set_auth_cache
from core.config import Settings, get_settings
from core.redis import RedisClient, set_redis_client
from core.tier_limits import Tier, TierLimits, get_tier_limits
from models.base import Base
from services.llm_service import LLMService, set_llm_service

def pytest_configure(config: pytest.Config) -> None:  # noqa: ARG001
    """
    Pin env vars that shadow local .env so tests are hermetic.

    Runs once at session start, before any fixture or test, regardless of
    which subset of tests is selected. Container-dependent env vars
    (DATABASE_URL, REDIS_URL) stay in the database_url fixture because they
    need the testcontainers running first.

    The MCP server respx mocks (in mcp_server/conftest.py and
    prompt_mcp_server/conftest.py) read VITE_API_URL from os.environ, so
    pinning it here means the mock base_url and the URL the server code
    actually requests cannot drift.

    The MCP OAuth discovery config is resolved+validated at server-module import
    (prompt_mcp_server.main / mcp_server), so the service resource URLs and
    CLERK_FRONTEND_API are pinned here to fixed test values — before collection —
    so those imports are deterministic regardless of a developer's real .env, and
    tests never assert against a developer's actual Clerk domain. Tests exercising
    missing/alternate values override these explicitly (monkeypatch / subprocess env).
    """
    os.environ["VITE_DEV_MODE"] = "true"
    os.environ["VITE_API_URL"] = "http://localhost:8000"
    os.environ["CLERK_FRONTEND_API"] = "test-instance.clerk.accounts.dev"
    os.environ["CONTENT_MCP_RESOURCE_URL"] = "http://localhost:8001/mcp"
    os.environ["PROMPT_MCP_RESOURCE_URL"] = "http://localhost:8002/mcp"
    # A known browser-Origin allowlist so the env->session-manager seam is exercised
    # end to end by the full-app transport-security test (import-time read).
    os.environ["MCP_ALLOWED_ORIGINS"] = "https://connector.test"


@pytest.fixture(scope="session")
def postgres_container() -> Generator[PostgresContainer]:
    """Start a PostgreSQL container for the test session."""
    with PostgresContainer("pgvector/pgvector:pg17", driver="asyncpg") as postgres:
        yield postgres


@pytest.fixture(scope="session")
def redis_container() -> Generator[RedisContainer]:
    """Start a Redis container for the test session."""
    with RedisContainer("redis:7-alpine") as redis:
        yield redis


def get_redis_url(container: RedisContainer) -> str:
    """Get Redis connection URL from container."""
    host = container.get_container_host_ip()
    port = container.get_exposed_port(6379)
    return f"redis://{host}:{port}"


@pytest.fixture(scope="session")
def database_url(postgres_container: PostgresContainer, redis_container: RedisContainer) -> str:
    """
    Get the database URL from the container and set it in environment.

    This must be set before any app imports that trigger Settings validation.
    """
    url = postgres_container.get_connection_url()
    os.environ["DATABASE_URL"] = url
    os.environ["REDIS_URL"] = get_redis_url(redis_container)
    return url


# SQL for search_vector trigger functions, triggers, and GIN indexes.
# Mirrors the Alembic migration; must stay in sync with trigger field lists.
# Search field weights: title=A, description=B, summary=B (bookmarks), content=C,
# name=A (prompts). See migration c07d5e217ca3 for the canonical definitions.
# Each statement is separate because asyncpg doesn't support multi-statement prepared queries.
_SEARCH_VECTOR_TRIGGER_STATEMENTS = [
    # -- Bookmark --
    """
    CREATE OR REPLACE FUNCTION bookmarks_search_vector_update() RETURNS trigger AS $$
    BEGIN
        IF TG_OP = 'INSERT' OR
           OLD.title IS DISTINCT FROM NEW.title OR
           OLD.description IS DISTINCT FROM NEW.description OR
           OLD.summary IS DISTINCT FROM NEW.summary OR
           OLD.content IS DISTINCT FROM NEW.content THEN
            NEW.search_vector :=
                setweight(to_tsvector('english', coalesce(NEW.title, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(NEW.description, '')), 'B') ||
                setweight(to_tsvector('english', coalesce(NEW.summary, '')), 'B') ||
                setweight(to_tsvector('english', coalesce(NEW.content, '')), 'C');
        ELSE
            NEW.search_vector := OLD.search_vector;
        END IF;
        RETURN NEW;
    END
    $$ LANGUAGE plpgsql
    """,
    "DROP TRIGGER IF EXISTS bookmarks_search_vector_trigger ON bookmarks",
    """
    CREATE TRIGGER bookmarks_search_vector_trigger
        BEFORE INSERT OR UPDATE ON bookmarks
        FOR EACH ROW EXECUTE FUNCTION bookmarks_search_vector_update()
    """,
    "CREATE INDEX IF NOT EXISTS ix_bookmarks_search_vector ON bookmarks USING GIN (search_vector)",
    # -- Note --
    """
    CREATE OR REPLACE FUNCTION notes_search_vector_update() RETURNS trigger AS $$
    BEGIN
        IF TG_OP = 'INSERT' OR
           OLD.title IS DISTINCT FROM NEW.title OR
           OLD.description IS DISTINCT FROM NEW.description OR
           OLD.content IS DISTINCT FROM NEW.content THEN
            NEW.search_vector :=
                setweight(to_tsvector('english', coalesce(NEW.title, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(NEW.description, '')), 'B') ||
                setweight(to_tsvector('english', coalesce(NEW.content, '')), 'C');
        ELSE
            NEW.search_vector := OLD.search_vector;
        END IF;
        RETURN NEW;
    END
    $$ LANGUAGE plpgsql
    """,
    "DROP TRIGGER IF EXISTS notes_search_vector_trigger ON notes",
    """
    CREATE TRIGGER notes_search_vector_trigger
        BEFORE INSERT OR UPDATE ON notes
        FOR EACH ROW EXECUTE FUNCTION notes_search_vector_update()
    """,
    "CREATE INDEX IF NOT EXISTS ix_notes_search_vector ON notes USING GIN (search_vector)",
    # -- Prompt --
    """
    CREATE OR REPLACE FUNCTION prompts_search_vector_update() RETURNS trigger AS $$
    BEGIN
        IF TG_OP = 'INSERT' OR
           OLD.name IS DISTINCT FROM NEW.name OR
           OLD.title IS DISTINCT FROM NEW.title OR
           OLD.description IS DISTINCT FROM NEW.description OR
           OLD.content IS DISTINCT FROM NEW.content THEN
            NEW.search_vector :=
                setweight(to_tsvector('english', coalesce(NEW.name, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(NEW.title, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(NEW.description, '')), 'B') ||
                setweight(to_tsvector('english', coalesce(NEW.content, '')), 'C');
        ELSE
            NEW.search_vector := OLD.search_vector;
        END IF;
        RETURN NEW;
    END
    $$ LANGUAGE plpgsql
    """,
    "DROP TRIGGER IF EXISTS prompts_search_vector_trigger ON prompts",
    """
    CREATE TRIGGER prompts_search_vector_trigger
        BEFORE INSERT OR UPDATE ON prompts
        FOR EACH ROW EXECUTE FUNCTION prompts_search_vector_update()
    """,
    "CREATE INDEX IF NOT EXISTS ix_prompts_search_vector ON prompts USING GIN (search_vector)",
]


@pytest.fixture(scope="session")
def _schema_setup(database_url: str) -> None:
    """
    Run schema DDL once per test session.

    Saves ~45s across the ~3000-test suite by hoisting Base.metadata.create_all
    and the search-vector trigger DDL out of the per-test path. The Postgres
    container is session-scoped and all DDL here is idempotent (CREATE OR
    REPLACE / IF NOT EXISTS / DROP TRIGGER IF EXISTS + CREATE TRIGGER), so
    running once per session is behaviorally equivalent to running per-test.

    Sync wrapper using asyncio.run() avoids the pytest-asyncio loop-scope
    coupling: this fixture's event loop is created and torn down inside
    asyncio.run() before any test runs, so it never interacts with the
    per-test loops used by async_engine / db_connection / db_session.
    """
    async def _setup() -> None:
        engine = create_async_engine(database_url, echo=False)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                # Trigger functions, triggers, and GIN indexes are defined in the
                # Alembic migration but not in SQLAlchemy model metadata, so
                # create_all doesn't include them.
                for stmt in _SEARCH_VECTOR_TRIGGER_STATEMENTS:
                    await conn.execute(text(stmt))
        finally:
            await engine.dispose()

    asyncio.run(_setup())


@pytest.fixture
async def async_engine(
    database_url: str,
    _schema_setup: None,
) -> AsyncGenerator[AsyncEngine]:
    """Create an async engine for testing. DDL is handled by _schema_setup."""
    engine = create_async_engine(database_url, echo=False)
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
def db_session_factory(db_connection: AsyncConnection) -> async_sessionmaker:
    """Session factory bound to the test transaction for concurrent query tests."""
    return async_sessionmaker(
        bind=db_connection,
        class_=AsyncSession,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )


# ---------------------------------------------------------------------------
# Concurrent-session fixtures (real cross-transaction lock contention)
# ---------------------------------------------------------------------------
# These fixtures provide independent database connections suitable for
# exercising real Postgres row-lock behavior (`SELECT ... FOR UPDATE`).
#
# Why they are separate from `db_session` / `db_session_factory`:
#   - The standard fixtures bind every session to a single AsyncConnection
#     wrapped in an outer transaction that is rolled back after each test
#     (`join_transaction_mode="create_savepoint"`). All "concurrent" sessions
#     therefore share one transaction and cannot contend for row locks.
#   - To test FOR UPDATE we need independent backends/transactions, which
#     requires a separate engine with no outer-transaction wrapper.
#
# Tests using `concurrent_session_factory` must clean up their data. Use
# `concurrent_test_user` to get a fresh User scoped to the test; data created
# under that user_id is removed automatically (ON DELETE CASCADE handles
# bookmarks/notes/prompts/history).


@pytest.fixture
async def concurrent_engine(
    database_url: str,
    _schema_setup: None,
) -> AsyncGenerator[AsyncEngine]:
    """
    Independent async engine for tests that need real lock contention.

    Function-scoped because pytest-asyncio creates a fresh event loop per
    test; asyncpg connections in the pool are bound to the loop they were
    created in and cannot be reused across loops.
    """
    engine = create_async_engine(
        database_url,
        echo=False,
        pool_size=4,
        max_overflow=2,
        pool_pre_ping=True,
    )
    yield engine
    await engine.dispose()


@pytest.fixture
def concurrent_session_factory(
    concurrent_engine: AsyncEngine,
) -> async_sessionmaker:
    """
    Session factory backed by the independent engine.

    Each session opens its own transaction. Sessions/transactions are fully
    independent and commits are real (not rolled back at end of test).
    Use with `concurrent_test_user` for automatic data cleanup.
    """
    return async_sessionmaker(
        concurrent_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest.fixture
async def concurrent_test_user(
    concurrent_session_factory: async_sessionmaker,
) -> "AsyncGenerator[User]":
    """
    Create a fresh User on the concurrent engine; cascade-delete on teardown.

    Yields the User row (with a fresh `id`). Any bookmarks/notes/prompts/
    content_history created under this user_id are removed by FK cascade
    when the user is deleted.
    """
    # Local import to avoid loading models at collection time / module import.
    from models.user import User  # noqa: PLC0415

    async with concurrent_session_factory() as session:
        user = User(
            external_auth_id=f"concurrent-test-{os.urandom(8).hex()}",
            email=f"concurrent-{os.urandom(4).hex()}@test.local",
            # PRO tier so concurrency tests aren't constrained by FREE-tier quotas.
            tier=Tier.PRO.value,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    try:
        yield user
    finally:
        async with concurrent_session_factory() as session:
            await session.execute(
                text("DELETE FROM users WHERE id = :uid"),
                {"uid": user.id},
            )
            await session.commit()


@pytest.fixture
async def concurrent_client(
    concurrent_session_factory: async_sessionmaker,
    concurrent_test_user: "User",
    redis_client: RedisClient,  # noqa: ARG001
) -> AsyncGenerator[AsyncClient]:
    """
    HTTP client where each request opens its own DB session from the concurrent engine.

    Unlike the standard `client` fixture (single shared session, rollback
    isolation), this fixture wires `get_async_session` to
    `concurrent_session_factory` so that concurrent HTTP requests actually
    contend at the database level — necessary for testing row-locking.

    Authenticates via PAT against `concurrent_test_user` (not dev-mode). The
    user cascades on teardown, removing the PAT, consent, and all created
    content.
    """
    # Imports stay inline: `api.main` runs `get_settings()` at import time,
    # which validates `DATABASE_URL`. That env var is only set at runtime by
    # the `database_url` fixture, so a module-level import would fail at
    # collection time. Same constraint applies to anything that transitively
    # touches Settings or db.session.
    from api.main import app  # noqa: PLC0415
    from core.policy_versions import (  # noqa: PLC0415
        PRIVACY_POLICY_VERSION,
        TERMS_OF_SERVICE_VERSION,
    )
    from db.session import get_async_session, get_session_factory  # noqa: PLC0415
    from models.user_consent import UserConsent  # noqa: PLC0415
    from schemas.token import TokenCreate  # noqa: PLC0415
    from services.token_service import create_token  # noqa: PLC0415

    # Seed consent and PAT in their own committed transaction so subsequent
    # per-request sessions can see them. DEV-tier limits here cover only the
    # PAT-count quota check at creation time; the user's runtime tier (which
    # governs rate limiting) stays PRO as set in `concurrent_test_user`.
    # N=5 concurrent writes is well under PRO's 200/min write rate limit.
    async with concurrent_session_factory() as session:
        session.add(UserConsent(
            user_id=concurrent_test_user.id,
            consented_at=datetime.now(UTC),
            privacy_policy_version=PRIVACY_POLICY_VERSION,
            terms_of_service_version=TERMS_OF_SERVICE_VERSION,
        ))
        _, plaintext_token = await create_token(
            session,
            concurrent_test_user.id,
            TokenCreate(name="concurrency-test"),
            get_tier_limits(Tier.DEV),
        )
        await session.commit()

    # `get_settings` is `@lru_cache`'d. Without `cache_clear()`, the override
    # below won't take effect because the cached Settings (populated by an
    # earlier fixture) is still served. After this fixture's teardown, the
    # next `get_settings()` call repopulates from env vars (pinned by
    # `pytest_configure` to dev-mode=True) — so other tests are unaffected.
    get_settings.cache_clear()

    async def override_get_async_session() -> AsyncGenerator[AsyncSession]:
        """Mirror production `get_async_session`: open, commit, close per request."""
        async with concurrent_session_factory() as request_session:
            try:
                yield request_session
                await request_session.commit()
            except Exception:
                await request_session.rollback()
                raise

    # `dev_mode=False` is the load-bearing setting: it forces the PAT auth
    # path (the production shape for MCP callers) instead of the dev-user
    # bypass. The other fields are just minimum-required Settings fields.
    def override_get_settings() -> Settings:
        return Settings(
            database_url="postgresql://test",
            dev_mode=False,
            clerk_frontend_api="test-instance.clerk.accounts.dev",
            clerk_authorized_parties_str="http://localhost:5173",
        )

    app.dependency_overrides[get_async_session] = override_get_async_session
    app.dependency_overrides[get_session_factory] = lambda: concurrent_session_factory
    app.dependency_overrides[get_settings] = override_get_settings

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {plaintext_token}"},
        ) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        # Defensive teardown-clear: this fixture churns Settings more aggressively
        # than the standard `client` fixture (it overrides dev_mode and direct
        # `get_settings()` calls during the test could repopulate the cache with
        # post-override env state). Clear so the next test starts fresh. The
        # standard `client` fixture does NOT do this — it only churns dev-mode
        # parity, so its setup-side clear is sufficient.
        get_settings.cache_clear()


@pytest.fixture
async def redis_client(redis_container: RedisContainer) -> AsyncGenerator[RedisClient]:
    """Create a Redis client connected to the test container and set as global."""
    client = RedisClient(get_redis_url(redis_container))
    await client.connect()
    set_redis_client(client)  # Set as global for rate limiter

    # Set up auth cache
    auth_cache = AuthCache(client)
    set_auth_cache(auth_cache)

    yield client

    await client.flushdb()  # Clean up after each test
    await client.close()
    set_auth_cache(None)
    set_redis_client(None)


@pytest.fixture
async def client(
    db_session: AsyncSession,
    db_session_factory: async_sessionmaker,
    redis_client: RedisClient,
) -> AsyncGenerator[AsyncClient]:
    """Create a test client with database session and Redis overrides."""
    # Clear the settings cache so it picks up DATABASE_URL from environment
    get_settings.cache_clear()

    from api.main import app  # noqa: PLC0415
    from api.routers.mcp import get_concurrent_queries  # noqa: PLC0415
    from db.session import get_async_session, get_session_factory  # noqa: PLC0415

    async def override_get_async_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_async_session] = override_get_async_session
    app.dependency_overrides[get_session_factory] = lambda: db_session_factory
    app.dependency_overrides[get_concurrent_queries] = lambda: False

    # Set the global Redis client and auth cache for the test
    # (redis_client fixture already sets these, but we ensure they're set here too)
    set_redis_client(redis_client)
    auth_cache = AuthCache(redis_client)
    set_auth_cache(auth_cache)

    # Initialize LLM service for tests
    test_settings = get_settings()
    llm_service = LLMService(test_settings)
    set_llm_service(llm_service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    set_llm_service(None)
    set_auth_cache(None)
    set_redis_client(None)


@pytest.fixture
async def rate_limit_client(
    client: AsyncClient,
) -> AsyncGenerator[AsyncClient]:
    """
    Wrap the standard test client to enable rate limiting.

    The standard client uses dev_mode=True which bypasses rate limiting.
    This fixture patches _apply_rate_limit to NOT skip rate limiting,
    while keeping auth in dev mode (so dev user still works).
    """
    from core import auth  # noqa: PLC0415

    # Store the original function
    original_apply_rate_limit = auth._apply_rate_limit

    async def patched_apply_rate_limit(
        user: object,
        request: object,
        settings: Settings,
    ) -> None:
        """Apply rate limiting even in dev mode."""
        # Temporarily pretend we're not in dev mode for rate limiting
        original_dev_mode = settings.dev_mode
        try:
            # Use object.__setattr__ to bypass frozen settings if needed
            object.__setattr__(settings, "dev_mode", False)
            await original_apply_rate_limit(user, request, settings)
        finally:
            object.__setattr__(settings, "dev_mode", original_dev_mode)

    # Patch the function
    auth._apply_rate_limit = patched_apply_rate_limit
    try:
        yield client
    finally:
        # Restore original
        auth._apply_rate_limit = original_apply_rate_limit


# Low limits for testing tier-based limits with small values
LOW_TIER_LIMITS = TierLimits(
    max_bookmarks=2,
    max_notes=2,
    max_prompts=2,
    max_pats=2,
    max_title_length=10,
    max_description_length=50,
    max_tag_name_length=10,
    max_bookmark_content_length=100,
    max_note_content_length=100,
    max_prompt_content_length=100,
    max_url_length=100,
    max_prompt_name_length=10,
    max_argument_name_length=10,
    max_argument_description_length=20,
    # Rate limits - low values for testing
    rate_read_per_minute=5,
    rate_read_per_day=20,
    rate_write_per_minute=3,
    rate_write_per_day=10,
    rate_sensitive_per_minute=2,
    rate_sensitive_per_day=5,
    # AI rate limits - low values for testing
    rate_ai_per_minute=3,
    rate_ai_per_day=10,
    rate_ai_byok_per_minute=5,
    rate_ai_byok_per_day=20,
    # Relationship limits - low values for testing
    max_relationships_per_entity=3,
    # History retention - low values for testing
    history_retention_days=7,
    max_history_per_entity=5,
)


@pytest.fixture
def default_limits() -> TierLimits:
    """
    Get the default tier limits for testing.

    Use this fixture when calling service methods that require a limits parameter
    but you don't need to test limit enforcement.
    """
    return get_tier_limits(Tier.DEV)


@pytest.fixture
def low_limits() -> Generator[TierLimits]:
    """
    Override TIER_LIMITS with restrictive limits for testing.

    Use this fixture to test quota and field limit enforcement without
    depending on actual production limit values. Patches both FREE and DEV
    tiers since get_current_limits() resolves to DEV in dev mode.
    """
    with patch.dict(
        "core.tier_limits.TIER_LIMITS",
        {
            Tier.FREE: LOW_TIER_LIMITS,
            Tier.STANDARD: LOW_TIER_LIMITS,
            Tier.PRO: LOW_TIER_LIMITS,
            Tier.DEV: LOW_TIER_LIMITS,
        },
    ):
        yield LOW_TIER_LIMITS
