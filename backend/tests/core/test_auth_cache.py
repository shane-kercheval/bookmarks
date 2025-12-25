"""Tests for the auth caching module."""
import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from core.auth_cache import CACHE_SCHEMA_VERSION, AuthCache, get_auth_cache, set_auth_cache
from core.redis import RedisClient
from models.user import User
from models.user_consent import UserConsent
from schemas.cached_user import CachedUser


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user for cache tests (with consent loaded)."""
    user = User(
        auth0_id="auth0|cache-test-user",
        email="cachetest@example.com",
    )
    db_session.add(user)
    await db_session.flush()

    # Re-fetch with consent relationship loaded
    result = await db_session.execute(
        select(User).options(joinedload(User.consent)).where(User.id == user.id),
    )
    return result.scalar_one()


@pytest.fixture
async def test_user_with_consent(db_session: AsyncSession) -> User:
    """Create a test user with consent for cache tests."""
    user = User(
        auth0_id="auth0|cache-test-user-consent",
        email="cachetestconsent@example.com",
    )
    db_session.add(user)
    await db_session.flush()

    consent = UserConsent(
        user_id=user.id,
        consented_at=datetime.now(UTC),
        privacy_policy_version="2025-01-01",
        terms_of_service_version="2025-01-01",
    )
    db_session.add(consent)
    await db_session.flush()

    # Re-fetch with consent relationship loaded
    result = await db_session.execute(
        select(User).options(joinedload(User.consent)).where(User.id == user.id),
    )
    return result.scalar_one()


class TestAuthCache:
    """Tests for AuthCache class."""

    async def test__get_by_auth0_id__returns_none_on_miss(
        self, redis_client: RedisClient,
    ) -> None:
        """Cache miss returns None."""
        cache = AuthCache(redis_client)

        result = await cache.get_by_auth0_id("auth0|nonexistent")

        assert result is None

    async def test__get_by_user_id__returns_none_on_miss(
        self, redis_client: RedisClient,
    ) -> None:
        """Cache miss returns None."""
        cache = AuthCache(redis_client)

        result = await cache.get_by_user_id(99999)

        assert result is None

    async def test__set__caches_user_by_user_id(
        self,
        redis_client: RedisClient,
        test_user: User,
    ) -> None:
        """User can be cached and retrieved by user ID."""
        cache = AuthCache(redis_client)

        await cache.set(test_user)
        result = await cache.get_by_user_id(test_user.id)

        assert result is not None
        assert isinstance(result, CachedUser)
        assert result.id == test_user.id
        assert result.auth0_id == test_user.auth0_id
        assert result.email == test_user.email

    async def test__set__caches_user_by_auth0_id(
        self,
        redis_client: RedisClient,
        test_user: User,
    ) -> None:
        """User can be cached and retrieved by Auth0 ID."""
        cache = AuthCache(redis_client)

        await cache.set(test_user, auth0_id=test_user.auth0_id)
        result = await cache.get_by_auth0_id(test_user.auth0_id)

        assert result is not None
        assert isinstance(result, CachedUser)
        assert result.id == test_user.id
        assert result.auth0_id == test_user.auth0_id

    async def test__set__includes_consent_versions(
        self,
        redis_client: RedisClient,
        test_user_with_consent: User,
    ) -> None:
        """Cached user includes consent version fields."""
        cache = AuthCache(redis_client)

        await cache.set(test_user_with_consent, auth0_id=test_user_with_consent.auth0_id)
        result = await cache.get_by_auth0_id(test_user_with_consent.auth0_id)

        assert result is not None
        assert result.consent_privacy_version == "2025-01-01"
        assert result.consent_tos_version == "2025-01-01"

    async def test__set__handles_user_without_consent(
        self,
        redis_client: RedisClient,
        test_user: User,
    ) -> None:
        """User without consent has None consent versions."""
        cache = AuthCache(redis_client)

        await cache.set(test_user, auth0_id=test_user.auth0_id)
        result = await cache.get_by_auth0_id(test_user.auth0_id)

        assert result is not None
        assert result.consent_privacy_version is None
        assert result.consent_tos_version is None

    async def test__invalidate__removes_by_user_id(
        self,
        redis_client: RedisClient,
        test_user: User,
    ) -> None:
        """Invalidate removes cache entry by user ID."""
        cache = AuthCache(redis_client)

        await cache.set(test_user)
        await cache.invalidate(test_user.id)
        result = await cache.get_by_user_id(test_user.id)

        assert result is None

    async def test__invalidate__removes_by_auth0_id(
        self,
        redis_client: RedisClient,
        test_user: User,
    ) -> None:
        """Invalidate removes cache entry by Auth0 ID when provided."""
        cache = AuthCache(redis_client)

        await cache.set(test_user, auth0_id=test_user.auth0_id)
        await cache.invalidate(test_user.id, auth0_id=test_user.auth0_id)
        result = await cache.get_by_auth0_id(test_user.auth0_id)

        assert result is None

    async def test__cache_key__includes_schema_version(
        self,
        redis_client: RedisClient,
    ) -> None:
        """Cache keys include schema version for migration safety."""
        cache = AuthCache(redis_client)

        auth0_key = cache._cache_key_auth0("auth0|test")
        user_id_key = cache._cache_key_user_id(123)

        assert f"v{CACHE_SCHEMA_VERSION}" in auth0_key
        assert f"v{CACHE_SCHEMA_VERSION}" in user_id_key


class TestAuthCacheSchemaVersioning:
    """Tests for schema versioning in auth cache."""

    async def test__old_version_key__not_found(
        self,
        redis_client: RedisClient,
        test_user: User,
    ) -> None:
        """Old schema version keys are not retrieved by current code."""
        cache = AuthCache(redis_client)

        # Manually write a cache entry with old version (v0)
        old_key = "auth:v0:user:auth0:auth0|old-version"
        old_data = json.dumps({
            "id": test_user.id,
            "auth0_id": "auth0|old-version",
            "email": "old@test.com",
            "consent_privacy_version": None,
            "consent_tos_version": None,
        })
        await redis_client.setex(old_key, 300, old_data)

        # Current code uses v1, should not find old v0 key
        result = await cache.get_by_auth0_id("auth0|old-version")

        assert result is None


class TestAuthCacheFallback:
    """Tests for auth cache fallback when Redis unavailable."""

    async def test__get__returns_none_when_redis_unavailable(self) -> None:
        """Cache operations return None when Redis is unavailable."""
        # Create a disabled Redis client
        disabled_client = RedisClient("redis://localhost:6379", enabled=False)
        await disabled_client.connect()

        try:
            cache = AuthCache(disabled_client)

            result = await cache.get_by_auth0_id("auth0|any")

            assert result is None
        finally:
            await disabled_client.close()


class TestGlobalAuthCache:
    """Tests for global auth cache getter/setter."""

    async def test__get_auth_cache__returns_set_value(
        self,
        redis_client: RedisClient,
    ) -> None:
        """get_auth_cache returns the value set by set_auth_cache."""
        cache = AuthCache(redis_client)
        original = get_auth_cache()

        try:
            set_auth_cache(cache)
            result = get_auth_cache()

            assert result is cache
        finally:
            set_auth_cache(original)

    async def test__get_auth_cache__returns_none_when_not_set(self) -> None:
        """get_auth_cache returns None when not set."""
        original = get_auth_cache()

        try:
            set_auth_cache(None)
            result = get_auth_cache()

            assert result is None
        finally:
            set_auth_cache(original)
