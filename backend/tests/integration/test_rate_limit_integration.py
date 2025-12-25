"""
Integration tests for rate limiting through the HTTP layer.

These tests verify that rate limiting works end-to-end with real Redis,
not mocked. They test the full flow: HTTP request → auth → rate limit check → response headers.
"""
import time
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from core.rate_limit_config import RATE_LIMITS, AuthType, OperationType
from core.redis import RedisClient
from services.url_scraper import ExtractedMetadata, ScrapedPage

# Reference configuration for SENSITIVE operations (used by fetch-metadata)
AUTH0_SENSITIVE_CONFIG = RATE_LIMITS[(AuthType.AUTH0, OperationType.SENSITIVE)]


@pytest.fixture
def mock_scrape_response() -> ScrapedPage:
    """Mock response for URL scraping to avoid real HTTP calls."""
    return ScrapedPage(
        text="Test content",
        metadata=ExtractedMetadata(title="Test Title", description="Test description"),
        final_url="https://example.com/",
        content_type="text/html",
        error=None,
    )


class TestRateLimitHeaders:
    """Tests for rate limit headers on successful responses."""

    async def test__rate_limit_headers__present_on_successful_request(
        self,
        client: AsyncClient,
        redis_client: RedisClient,  # noqa: ARG002
        mock_scrape_response: ScrapedPage,
    ) -> None:
        """Rate limit headers are included on successful responses."""
        with patch(
            "api.routers.bookmarks.scrape_url",
            new_callable=AsyncMock,
            return_value=mock_scrape_response,
        ):
            response = await client.get(
                "/bookmarks/fetch-metadata",
                params={"url": "https://example.com"},
            )

        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers

    async def test__rate_limit_headers__remaining_decreases_with_requests(
        self,
        client: AsyncClient,
        redis_client: RedisClient,  # noqa: ARG002
        mock_scrape_response: ScrapedPage,
    ) -> None:
        """Remaining count decreases with each request."""
        with patch(
            "api.routers.bookmarks.scrape_url",
            new_callable=AsyncMock,
            return_value=mock_scrape_response,
        ):
            # First request
            response1 = await client.get(
                "/bookmarks/fetch-metadata",
                params={"url": "https://example.com/page1"},
            )
            remaining1 = int(response1.headers["X-RateLimit-Remaining"])

            # Second request
            response2 = await client.get(
                "/bookmarks/fetch-metadata",
                params={"url": "https://example.com/page2"},
            )
            remaining2 = int(response2.headers["X-RateLimit-Remaining"])

        assert remaining2 < remaining1, "Remaining should decrease with each request"

    async def test__rate_limit_headers__limit_matches_sensitive_operation(
        self,
        client: AsyncClient,
        redis_client: RedisClient,  # noqa: ARG002
        mock_scrape_response: ScrapedPage,
    ) -> None:
        """fetch-metadata is a SENSITIVE operation with configured limit for Auth0."""
        with patch(
            "api.routers.bookmarks.scrape_url",
            new_callable=AsyncMock,
            return_value=mock_scrape_response,
        ):
            response = await client.get(
                "/bookmarks/fetch-metadata",
                params={"url": "https://example.com"},
            )

        expected_limit = AUTH0_SENSITIVE_CONFIG.requests_per_minute
        assert int(response.headers["X-RateLimit-Limit"]) == expected_limit

    async def test__rate_limit_headers__reset_is_future_timestamp(
        self,
        client: AsyncClient,
        redis_client: RedisClient,  # noqa: ARG002
        mock_scrape_response: ScrapedPage,
    ) -> None:
        """Reset header contains a future Unix timestamp."""
        now = int(time.time())

        with patch(
            "api.routers.bookmarks.scrape_url",
            new_callable=AsyncMock,
            return_value=mock_scrape_response,
        ):
            response = await client.get(
                "/bookmarks/fetch-metadata",
                params={"url": "https://example.com"},
            )

        reset = int(response.headers["X-RateLimit-Reset"])
        assert reset > now, "Reset should be a future timestamp"
        assert reset <= now + 60, "Reset should be within the 1-minute window"


class TestRateLimitEnforcement:
    """Tests for rate limit enforcement (429 responses)."""

    async def _get_user_id_and_prefill_limit(
        self,
        client: AsyncClient,
        redis_client: RedisClient,
        mock_scrape_response: ScrapedPage,
    ) -> int:
        """
        Make one request to get user ID, then pre-fill to the limit.

        Returns the user ID discovered from the first request.
        """
        limit = AUTH0_SENSITIVE_CONFIG.requests_per_minute

        # First, make a request to get the user ID and see the rate limit key pattern
        with patch(
            "api.routers.bookmarks.scrape_url",
            new_callable=AsyncMock,
            return_value=mock_scrape_response,
        ):
            response = await client.get(
                "/bookmarks/fetch-metadata",
                params={"url": "https://example.com/discover"},
            )

        assert response.status_code == 200

        # Get user ID from /users/me
        user_response = await client.get("/users/me")
        user_id = user_response.json()["id"]

        # Now pre-fill the remaining slots (we already used 1)
        now = int(time.time())
        key = f"rate:{user_id}:auth0:sensitive:min"

        # Fill up the remaining slots (limit - 1 we already used)
        for i in range(limit - 1):
            await redis_client.evalsha(
                redis_client.sliding_window_sha,
                1,
                key,
                now,
                60,  # window
                limit,
                f"prefill-{i}",  # unique request ID
            )

        return user_id

    async def test__rate_limit__returns_429_when_limit_exceeded(
        self,
        client: AsyncClient,
        redis_client: RedisClient,
        mock_scrape_response: ScrapedPage,
    ) -> None:
        """Request returns 429 when rate limit is exceeded."""
        await self._get_user_id_and_prefill_limit(
            client, redis_client, mock_scrape_response,
        )

        # Next request should be blocked
        with patch(
            "api.routers.bookmarks.scrape_url",
            new_callable=AsyncMock,
            return_value=mock_scrape_response,
        ):
            response = await client.get(
                "/bookmarks/fetch-metadata",
                params={"url": "https://example.com/blocked"},
            )

        assert response.status_code == 429
        assert "Rate limit exceeded" in response.json()["detail"]

    async def test__rate_limit__429_includes_retry_after_header(
        self,
        client: AsyncClient,
        redis_client: RedisClient,
        mock_scrape_response: ScrapedPage,
    ) -> None:
        """429 response includes Retry-After header."""
        await self._get_user_id_and_prefill_limit(
            client, redis_client, mock_scrape_response,
        )

        with patch(
            "api.routers.bookmarks.scrape_url",
            new_callable=AsyncMock,
            return_value=mock_scrape_response,
        ):
            response = await client.get(
                "/bookmarks/fetch-metadata",
                params={"url": "https://example.com/retry"},
            )

        assert response.status_code == 429
        assert "Retry-After" in response.headers
        retry_after = int(response.headers["Retry-After"])
        assert retry_after > 0, "Retry-After should be positive"
        assert retry_after <= 60, "Retry-After should be within the window"

    async def test__rate_limit__429_includes_all_rate_limit_headers(
        self,
        client: AsyncClient,
        redis_client: RedisClient,
        mock_scrape_response: ScrapedPage,
    ) -> None:
        """429 response includes all X-RateLimit-* headers."""
        await self._get_user_id_and_prefill_limit(
            client, redis_client, mock_scrape_response,
        )

        with patch(
            "api.routers.bookmarks.scrape_url",
            new_callable=AsyncMock,
            return_value=mock_scrape_response,
        ):
            response = await client.get(
                "/bookmarks/fetch-metadata",
                params={"url": "https://example.com/headers"},
            )

        assert response.status_code == 429
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers
        assert response.headers["X-RateLimit-Remaining"] == "0"

    async def test__rate_limit__real_requests_eventually_blocked(
        self,
        client: AsyncClient,
        redis_client: RedisClient,  # noqa: ARG002
        mock_scrape_response: ScrapedPage,
    ) -> None:
        """
        Making real requests eventually hits the rate limit.

        This is a more thorough test that doesn't pre-populate Redis.
        It makes limit+1 requests and verifies the last is blocked.
        """
        limit = AUTH0_SENSITIVE_CONFIG.requests_per_minute
        blocked = False
        request_count = 0

        with patch(
            "api.routers.bookmarks.scrape_url",
            new_callable=AsyncMock,
            return_value=mock_scrape_response,
        ):
            # Make limit+1 requests
            for i in range(limit + 1):
                response = await client.get(
                    "/bookmarks/fetch-metadata",
                    params={"url": f"https://example.com/page{i}"},
                )
                request_count += 1

                if response.status_code == 429:
                    blocked = True
                    break

        assert blocked, f"Should have been blocked after {limit} requests, made {request_count}"
        assert request_count == limit + 1, f"Should have been blocked on request {limit + 1}"


class TestRateLimitUserIsolation:
    """Tests for user isolation in rate limiting."""

    async def test__rate_limit__different_users_have_separate_limits(
        self,
        client: AsyncClient,  # noqa: ARG002
        redis_client: RedisClient,
        mock_scrape_response: ScrapedPage,  # noqa: ARG002
    ) -> None:
        """
        Different users have independent rate limit buckets.

        Note: In dev mode, all requests use the same dev user, so this test
        verifies isolation by checking different user_id keys in Redis directly.
        """
        limit = AUTH0_SENSITIVE_CONFIG.requests_per_minute
        now = int(time.time())

        # Pre-fill user 100's bucket to the limit
        key_user_100 = "rate:100:auth0:sensitive:min"
        for i in range(limit):
            await redis_client.evalsha(
                redis_client.sliding_window_sha,
                1,
                key_user_100,
                now,
                60,
                limit,
                f"user100-{i}",
            )

        # User 200's bucket should still have room
        key_user_200 = "rate:200:auth0:sensitive:min"
        result = await redis_client.evalsha(
            redis_client.sliding_window_sha,
            1,
            key_user_200,
            now,
            60,
            limit,
            "user200-first",
        )

        # result[0] = allowed (1 or 0)
        assert result[0] == 1, "User 200 should be allowed (separate bucket)"
