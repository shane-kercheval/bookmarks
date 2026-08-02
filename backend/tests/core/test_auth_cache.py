"""Tests for the auth caching module."""
import json
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth_cache import CACHE_SCHEMA_VERSION, AuthCache, get_auth_cache, set_auth_cache
from core.redis import RedisClient
from models.user import User
from core.tier_limits import Tier
from schemas.cached_user import CachedUser


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user for cache tests."""
    user = User(
        external_auth_id="legacy|cache-test-user",
        email="cachetest@example.com",
        tier=Tier.FREE.value,
    )
    db_session.add(user)
    await db_session.flush()
    return user


class TestAuthCache:
    """Tests for AuthCache class."""

    async def test__get_by_external_auth_id__returns_none_on_miss(
        self, redis_client: RedisClient,
    ) -> None:
        """Cache miss returns None."""
        cache = AuthCache(redis_client)

        result = await cache.get_by_external_auth_id("legacy|nonexistent")

        assert result is None

    async def test__get_by_user_id__returns_none_on_miss(
        self, redis_client: RedisClient,
    ) -> None:
        """Cache miss returns None."""
        cache = AuthCache(redis_client)

        result = await cache.get_by_user_id(uuid4())

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
        assert result.external_auth_id == test_user.external_auth_id
        assert result.email == test_user.email

    async def test__set__caches_user_by_external_auth_id(
        self,
        redis_client: RedisClient,
        test_user: User,
    ) -> None:
        """User can be cached and retrieved by external auth ID."""
        cache = AuthCache(redis_client)

        await cache.set(test_user)
        result = await cache.get_by_external_auth_id(test_user.external_auth_id)

        assert result is not None
        assert isinstance(result, CachedUser)
        assert result.id == test_user.id
        assert result.external_auth_id == test_user.external_auth_id

    async def test__set__includes_email_verified(
        self,
        redis_client: RedisClient,
        test_user: User,
    ) -> None:
        """Cached user includes email_verified field."""
        cache = AuthCache(redis_client)

        test_user.email_verified = True
        await cache.set(test_user)
        result = await cache.get_by_external_auth_id(test_user.external_auth_id)

        assert result is not None
        assert result.email_verified is True

    async def test__set__handles_null_email_verified(
        self,
        redis_client: RedisClient,
        test_user: User,
    ) -> None:
        """User without email_verified has None in cache."""
        cache = AuthCache(redis_client)

        await cache.set(test_user)
        result = await cache.get_by_external_auth_id(test_user.external_auth_id)

        assert result is not None
        assert result.email_verified is None

    async def test__invalidate__removes_by_user_id(
        self,
        redis_client: RedisClient,
        test_user: User,
    ) -> None:
        """Invalidate removes the user-id segment entry."""
        cache = AuthCache(redis_client)

        await cache.set(test_user)
        await cache.invalidate(test_user.id, external_auth_id=test_user.external_auth_id)
        result = await cache.get_by_user_id(test_user.id)

        assert result is None

    async def test__invalidate__removes_by_external_auth_id(
        self,
        redis_client: RedisClient,
        test_user: User,
    ) -> None:
        """Invalidate removes the ext-segment entry when provided."""
        cache = AuthCache(redis_client)

        await cache.set(test_user)
        await cache.invalidate(test_user.id, external_auth_id=test_user.external_auth_id)
        result = await cache.get_by_external_auth_id(test_user.external_auth_id)

        assert result is None

    async def test__cache_key__includes_schema_version(
        self,
        redis_client: RedisClient,
    ) -> None:
        """Cache keys include schema version for migration safety."""
        cache = AuthCache(redis_client)

        ext_key = cache._cache_key_external("legacy|test")
        user_id_key = cache._cache_key_user_id(uuid4())

        assert f"v{CACHE_SCHEMA_VERSION}" in ext_key
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

        # A v7 entry in the PREVIOUS shape: it still carries the consent
        # fields removed at v8. Deserializing one into today's CachedUser would
        # raise, so the version-in-key must make it unaddressable by
        # construction rather than merely unused.
        #
        # Pinned, not derived. Deriving the key from CACHE_SCHEMA_VERSION - 1
        # while leaving this payload hardcoded would silently relabel a v7 body
        # as v8 at the next bump and keep passing — the test would survive as
        # "some old key isn't found" instead of "the outgoing shape isn't
        # readable", which is the property that protects a running deployment.
        # This assertion forces a deliberate payload refresh instead.
        assert CACHE_SCHEMA_VERSION == 8, (
            "Cache schema bumped: update the payload below to the OUTGOING "
            "shape (the one this version replaces) and re-pin this assertion."
        )
        old_key = "auth:v7:user:ext:user_old_version"
        old_data = json.dumps({
            "id": str(test_user.id),
            "external_auth_id": "user_old_version",
            "email": "old@test.com",
            "email_verified": True,
            "consent_privacy_version": None,
            "consent_tos_version": None,
            "tier": "pro",
        })
        await redis_client.setex(old_key, 300, old_data)

        # Current code is v8 and must not find the v7 key
        result = await cache.get_by_external_auth_id("user_old_version")

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

            result = await cache.get_by_external_auth_id("legacy|any")

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
