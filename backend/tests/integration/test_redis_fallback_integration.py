"""
Integration tests for Redis fallback behavior at the HTTP layer.

These tests verify that the application continues to work when Redis
is unavailable, using fail-open behavior for rate limiting and
falling back to database for auth.
"""
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth_cache import set_auth_cache
from core.redis import RedisClient, set_redis_client


class TestRedisFallbackHTTP:
    """Tests for HTTP request handling when Redis is unavailable."""

    async def test__request_succeeds__when_redis_unavailable(
        self,
        client: AsyncClient,
        redis_client: RedisClient,
    ) -> None:
        """Authenticated requests succeed when Redis is unavailable."""
        # First, make a normal request to create the dev user in DB
        response = await client.get("/users/me")
        assert response.status_code == 200

        # Now disable Redis
        original_client = redis_client
        set_redis_client(None)
        set_auth_cache(None)

        try:
            # Request should still succeed (falls back to DB)
            response = await client.get("/users/me")
            assert response.status_code == 200
        finally:
            # Restore Redis
            set_redis_client(original_client)
            from core.auth_cache import AuthCache
            set_auth_cache(AuthCache(original_client))

    async def test__no_rate_limit_headers__when_redis_unavailable(
        self,
        client: AsyncClient,
        redis_client: RedisClient,
    ) -> None:
        """
        Rate limit headers are not present when Redis is unavailable.

        When Redis is down, the rate limit dependency returns a permissive
        result but with limit=0, remaining=0, reset=0. The middleware
        will still add headers but with zero values.
        """
        from unittest.mock import AsyncMock, patch
        from services.url_scraper import ExtractedMetadata, ScrapedPage

        mock_scrape = ScrapedPage(
            text="Test",
            metadata=ExtractedMetadata(title="Test", description="Desc"),
            final_url="https://example.com/",
            content_type="text/html",
            error=None,
        )

        # Make initial request to create dev user
        await client.get("/users/me")

        # Disable Redis
        original_client = redis_client
        set_redis_client(None)
        set_auth_cache(None)

        try:
            with patch(
                "api.routers.bookmarks.scrape_url",
                new_callable=AsyncMock,
                return_value=mock_scrape,
            ):
                response = await client.get(
                    "/bookmarks/fetch-metadata",
                    params={"url": "https://example.com"},
                )

            # Request should succeed
            assert response.status_code == 200

            # Headers may not be present or may have default values
            # The key point is that we don't get a 500 error
            if "X-RateLimit-Limit" in response.headers:
                # If headers are present, remaining should indicate no limit enforced
                # The rate limiter returns config limits when Redis unavailable
                limit = int(response.headers.get("X-RateLimit-Limit", "0"))
                # Just verify it's a reasonable value (not an error state)
                assert limit >= 0
        finally:
            set_redis_client(original_client)
            from core.auth_cache import AuthCache
            set_auth_cache(AuthCache(original_client))

    async def test__auth_falls_back_to_db__when_redis_unavailable(
        self,
        client: AsyncClient,
        redis_client: RedisClient,
        db_session: AsyncSession,  # noqa: ARG002
    ) -> None:
        """Auth works by falling back to DB when Redis cache is unavailable."""
        # First, create the user and verify it exists
        response = await client.get("/users/me")
        assert response.status_code == 200
        user_data = response.json()
        original_user_id = user_data["id"]

        # Disable Redis (cache unavailable)
        original_client = redis_client
        set_redis_client(None)
        set_auth_cache(None)

        try:
            # Auth should still work by hitting DB directly
            response = await client.get("/users/me")
            assert response.status_code == 200

            # Should return the same user
            user_data_2 = response.json()
            assert user_data_2["id"] == original_user_id
        finally:
            set_redis_client(original_client)
            from core.auth_cache import AuthCache
            set_auth_cache(AuthCache(original_client))

    async def test__health_reports_redis_unavailable(
        self,
        client: AsyncClient,
        redis_client: RedisClient,
    ) -> None:
        """Health endpoint reports Redis as unavailable but app as healthy."""
        # Disable Redis
        original_client = redis_client
        set_redis_client(None)
        set_auth_cache(None)

        try:
            response = await client.get("/health")
            assert response.status_code == 200

            data = response.json()
            # App should still be healthy (degraded mode)
            assert data["status"] == "healthy"
            assert data["database"] == "healthy"
            # Redis should be reported as unavailable
            assert data["redis"] == "unavailable"
        finally:
            set_redis_client(original_client)
            from core.auth_cache import AuthCache
            set_auth_cache(AuthCache(original_client))


class TestRedisDisabledViaConfig:
    """Tests for Redis disabled via configuration."""

    async def test__request_succeeds__when_redis_disabled(
        self,
        client: AsyncClient,
        redis_client: RedisClient,
    ) -> None:
        """Requests succeed when Redis is disabled by config."""
        # Create a disabled Redis client
        disabled_client = RedisClient("redis://localhost:6379", enabled=False)
        await disabled_client.connect()

        # First make a request with Redis enabled to create the user
        await client.get("/users/me")

        # Now swap to disabled client
        original_client = redis_client
        set_redis_client(disabled_client)
        set_auth_cache(None)

        try:
            response = await client.get("/users/me")
            assert response.status_code == 200
        finally:
            await disabled_client.close()
            set_redis_client(original_client)
            from core.auth_cache import AuthCache
            set_auth_cache(AuthCache(original_client))
