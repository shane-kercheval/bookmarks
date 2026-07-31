"""
Integration tests for auth caching through the HTTP layer.

These tests verify that auth caching works end-to-end with real Redis,
including cache population and invalidation.

Note: We don't test "cache hit skips DB" at the integration layer because
reliably proving zero DB queries requires invasive mocking that makes tests
fragile. The unit tests for AuthCache verify the caching logic; integration
tests verify the wiring (cache populated, cache invalidated on consent).
"""
import json

from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth_cache import CACHE_SCHEMA_VERSION, get_auth_cache
from core.redis import RedisClient
from models.user_consent import UserConsent

# Dev mode always uses this external_auth_id sentinel
DEV_EXTERNAL_AUTH_ID = "dev|local-development-user"


class TestAuthCachePopulation:
    """Tests for auth cache population after authenticated requests."""

    async def test__auth_cache__populated_after_authenticated_request(
        self,
        client: AsyncClient,
        redis_client: RedisClient,
    ) -> None:
        """Cache entry exists in Redis after authenticated request."""
        # First request creates+commits the dev user (a freshly-created user is
        # not cached); the second reads the committed row and caches it.
        assert (await client.get("/users/me")).status_code == 200
        response = await client.get("/users/me")
        assert response.status_code == 200

        user_data = response.json()
        user_id = user_data["id"]

        # Verify cache entry exists by user_id
        user_id_key = f"auth:v{CACHE_SCHEMA_VERSION}:user:id:{user_id}"
        cached_data = await redis_client.get(user_id_key)
        assert cached_data is not None, "Cache entry should exist for user_id"

        # Verify cache entry exists by external_auth_id
        ext_key = f"auth:v{CACHE_SCHEMA_VERSION}:user:ext:{DEV_EXTERNAL_AUTH_ID}"
        cached_data = await redis_client.get(ext_key)
        assert cached_data is not None, "Cache entry should exist for external_auth_id"

    async def test__auth_cache__contains_correct_user_data(
        self,
        client: AsyncClient,
        redis_client: RedisClient,
    ) -> None:
        """Cached data contains correct user information."""
        # First request creates+commits the dev user; the second caches it.
        await client.get("/users/me")
        response = await client.get("/users/me")
        user_data = response.json()

        # Get cached data
        user_id_key = f"auth:v{CACHE_SCHEMA_VERSION}:user:id:{user_data['id']}"
        cached_bytes = await redis_client.get(user_id_key)
        cached = json.loads(cached_bytes)

        assert cached["id"] == user_data["id"]
        assert cached["external_auth_id"] == DEV_EXTERNAL_AUTH_ID
        assert cached["email"] == user_data["email"]


class TestAuthCacheInvalidation:
    """Tests for cache invalidation on consent updates."""

    async def test__consent_update__invalidates_cache(
        self,
        client: AsyncClient,
        redis_client: RedisClient,
    ) -> None:
        """POST /consent/me clears cache entry."""
        # First request creates+commits the dev user (not cached); the second
        # reads the committed row and populates the cache.
        assert (await client.get("/users/me")).status_code == 200
        assert (await client.get("/users/me")).status_code == 200

        # Verify cache is populated
        ext_key = f"auth:v{CACHE_SCHEMA_VERSION}:user:ext:{DEV_EXTERNAL_AUTH_ID}"
        assert await redis_client.get(ext_key) is not None, "Cache should be populated"

        # Now update consent
        consent_response = await client.post(
            "/consent/me",
            json={
                "privacy_policy_version": "2025-01-01",
                "terms_of_service_version": "2025-01-01",
            },
        )
        # 201 for first consent, 200 for update
        assert consent_response.status_code in (200, 201)

        # Cache should be invalidated
        cached_after = await redis_client.get(ext_key)
        assert cached_after is None, "Cache should be cleared after consent update"

    async def test__consent_update__next_request_repopulates_cache(
        self,
        client: AsyncClient,
        redis_client: RedisClient,
    ) -> None:
        """Request after consent update repopulates cache."""
        # Populate cache
        await client.get("/users/me")
        ext_key = f"auth:v{CACHE_SCHEMA_VERSION}:user:ext:{DEV_EXTERNAL_AUTH_ID}"

        # Update consent (invalidates cache)
        await client.post(
            "/consent/me",
            json={
                "privacy_policy_version": "2025-01-01",
                "terms_of_service_version": "2025-01-01",
            },
        )

        # Verify cache is cleared
        assert await redis_client.get(ext_key) is None

        # Next request should repopulate cache
        response2 = await client.get("/users/me")
        assert response2.status_code == 200

        # Cache should be repopulated
        cached_after = await redis_client.get(ext_key)
        assert cached_after is not None, "Cache should be repopulated after next request"


class TestAuthCacheConsentData:
    """Tests for consent version data in cache."""

    async def test__auth_cache__includes_consent_versions_after_consent(
        self,
        client: AsyncClient,
        redis_client: RedisClient,
    ) -> None:
        """Cache entry includes consent versions after user provides consent."""
        # First provide consent
        await client.post(
            "/consent/me",
            json={
                "privacy_policy_version": "2025-01-01",
                "terms_of_service_version": "2025-01-01",
            },
        )

        # Make request to repopulate cache with consent data
        response = await client.get("/users/me")
        user_data = response.json()

        # Check cached data includes consent versions
        user_id_key = f"auth:v{CACHE_SCHEMA_VERSION}:user:id:{user_data['id']}"
        cached_bytes = await redis_client.get(user_id_key)
        cached = json.loads(cached_bytes)

        assert cached["consent_privacy_version"] == "2025-01-01"
        assert cached["consent_tos_version"] == "2025-01-01"

    async def test__auth_cache__user_without_consent_has_null_versions(
        self,
        client: AsyncClient,
        redis_client: RedisClient,
        db_session: AsyncSession,
    ) -> None:
        """
        New user without consent has null consent versions in cache.

        Note: In dev mode, users are auto-created without consent.
        We verify by checking a fresh cache entry before any consent is given.
        """
        # Clear existing cache to force fresh lookup
        auth_cache = get_auth_cache()
        if auth_cache:
            # Get current user info
            response = await client.get("/users/me")
            user_data = response.json()

            # Invalidate cache
            await auth_cache.invalidate(user_data["id"], DEV_EXTERNAL_AUTH_ID)

            # Also clear any consent for this test
            await db_session.execute(
                delete(UserConsent).where(UserConsent.user_id == user_data["id"]),
            )
            await db_session.commit()

            # Now make request - should create cache with no consent
            response2 = await client.get("/users/me")
            user_data2 = response2.json()

            # Check cached data
            user_id_key = f"auth:v{CACHE_SCHEMA_VERSION}:user:id:{user_data2['id']}"
            cached_bytes = await redis_client.get(user_id_key)
            cached = json.loads(cached_bytes)

            assert cached["consent_privacy_version"] is None
            assert cached["consent_tos_version"] is None
