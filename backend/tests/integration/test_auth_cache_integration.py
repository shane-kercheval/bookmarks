"""
Integration tests for auth caching through the HTTP layer.

These tests verify that auth caching works end-to-end with real Redis,
including cache population and invalidation.

Note: We don't test "cache hit skips DB" at the integration layer because
reliably proving zero DB queries requires invasive mocking that makes tests
fragile. The unit tests for AuthCache verify the caching logic; integration
tests verify the wiring (cache populated with the right shape).
"""
import json

from httpx import AsyncClient

from core.auth_cache import CACHE_SCHEMA_VERSION
from core.redis import RedisClient

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
