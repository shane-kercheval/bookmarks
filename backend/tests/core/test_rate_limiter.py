"""Tests for the Redis-based rate limiter module."""
import time

from core.rate_limiter import (
    AuthType,
    OperationType,
    RateLimitResult,
    RedisRateLimiter,
    get_operation_type,
)
from core.redis import RedisClient


class TestGetOperationType:
    """Tests for get_operation_type function."""

    def test__get_operation_type__get_request_is_read(self) -> None:
        """GET requests are classified as READ."""
        assert get_operation_type("GET", "/bookmarks") == OperationType.READ

    def test__get_operation_type__post_request_is_write(self) -> None:
        """POST requests are classified as WRITE."""
        assert get_operation_type("POST", "/bookmarks") == OperationType.WRITE

    def test__get_operation_type__patch_request_is_write(self) -> None:
        """PATCH requests are classified as WRITE."""
        assert get_operation_type("PATCH", "/bookmarks/1") == OperationType.WRITE

    def test__get_operation_type__delete_request_is_write(self) -> None:
        """DELETE requests are classified as WRITE."""
        assert get_operation_type("DELETE", "/bookmarks/1") == OperationType.WRITE

    def test__get_operation_type__fetch_metadata_is_sensitive(self) -> None:
        """fetch-metadata endpoint is classified as SENSITIVE."""
        assert get_operation_type("GET", "/bookmarks/fetch-metadata") == OperationType.SENSITIVE


class TestRedisRateLimiter:
    """Tests for RedisRateLimiter class."""

    async def test__check__allows_request_under_limit(
        self, redis_client: RedisClient,  # noqa: ARG002
    ) -> None:
        """Requests under the limit are allowed."""
        # redis_client fixture sets global client via set_redis_client()
        limiter = RedisRateLimiter()

        result = await limiter.check(
            user_id=1,
            auth_type=AuthType.AUTH0,
            operation_type=OperationType.READ,
        )

        assert result.allowed is True
        assert result.remaining >= 0

    async def test__check__blocks_request_over_limit(
        self, redis_client: RedisClient,
    ) -> None:
        """Requests over the limit are blocked."""
        limiter = RedisRateLimiter()
        user_id = 999  # Use unique user ID for isolation

        # Make requests up to the limit (AUTH0 READ is 300/min, use smaller test)
        # We'll test with the sliding window directly for precision
        key = f"rate:{user_id}:auth0:read:min"

        # Fill up the limit by manually adding entries
        now = int(time.time())
        for i in range(300):
            await redis_client.evalsha(
                redis_client.sliding_window_sha,
                1,
                key,
                now,
                60,
                300,
                f"test-{i}",
            )

        # Next request should be blocked
        result = await limiter.check(
            user_id=user_id,
            auth_type=AuthType.AUTH0,
            operation_type=OperationType.READ,
        )

        assert result.allowed is False
        assert result.remaining == 0
        assert result.retry_after > 0

    async def test__check__different_users_have_separate_limits(
        self, redis_client: RedisClient,  # noqa: ARG002
    ) -> None:
        """Different users have separate rate limit buckets."""
        limiter = RedisRateLimiter()

        result1 = await limiter.check(
            user_id=100,
            auth_type=AuthType.AUTH0,
            operation_type=OperationType.READ,
        )
        result2 = await limiter.check(
            user_id=200,
            auth_type=AuthType.AUTH0,
            operation_type=OperationType.READ,
        )

        # Both should be allowed (separate buckets)
        assert result1.allowed is True
        assert result2.allowed is True

    async def test__check__pat_has_lower_limits_than_auth0(
        self, redis_client: RedisClient,  # noqa: ARG002
    ) -> None:
        """PAT has lower per-minute limits than Auth0."""
        limiter = RedisRateLimiter()

        # PAT READ is 120/min, AUTH0 READ is 300/min
        pat_result = await limiter.check(
            user_id=1,
            auth_type=AuthType.PAT,
            operation_type=OperationType.READ,
        )
        auth0_result = await limiter.check(
            user_id=2,
            auth_type=AuthType.AUTH0,
            operation_type=OperationType.READ,
        )

        # PAT should have lower limit
        assert pat_result.limit < auth0_result.limit

    async def test__check__sensitive_has_strictest_limits(
        self, redis_client: RedisClient,  # noqa: ARG002
    ) -> None:
        """Sensitive operations have the strictest limits."""
        limiter = RedisRateLimiter()

        # AUTH0 SENSITIVE is 30/min (strictest)
        result = await limiter.check(
            user_id=1,
            auth_type=AuthType.AUTH0,
            operation_type=OperationType.SENSITIVE,
        )

        assert result.limit == 30

    async def test__check__returns_rate_limit_info_for_headers(
        self, redis_client: RedisClient,  # noqa: ARG002
    ) -> None:
        """Check returns all info needed for rate limit headers."""
        limiter = RedisRateLimiter()

        result = await limiter.check(
            user_id=1,
            auth_type=AuthType.AUTH0,
            operation_type=OperationType.READ,
        )

        assert isinstance(result, RateLimitResult)
        assert result.limit > 0
        assert result.remaining >= 0
        assert result.reset > 0
        assert result.retry_after >= 0


class TestRateLimiterFallback:
    """Tests for rate limiter fallback when Redis unavailable."""

    async def test__check__allows_request_when_redis_unavailable(self) -> None:
        """Requests are allowed when Redis is unavailable (fail-open)."""
        # Don't set up Redis client - it will be None
        from core.redis import set_redis_client
        set_redis_client(None)

        limiter = RedisRateLimiter()
        result = await limiter.check(
            user_id=1,
            auth_type=AuthType.AUTH0,
            operation_type=OperationType.READ,
        )

        assert result.allowed is True

    async def test__check__allows_request_when_redis_disabled(self) -> None:
        """Requests are allowed when Redis is disabled (fail-open)."""
        from core.redis import set_redis_client

        # Create a disabled Redis client
        disabled_client = RedisClient("redis://localhost:6379", enabled=False)
        await disabled_client.connect()
        set_redis_client(disabled_client)

        try:
            limiter = RedisRateLimiter()
            result = await limiter.check(
                user_id=1,
                auth_type=AuthType.AUTH0,
                operation_type=OperationType.READ,
            )

            assert result.allowed is True
        finally:
            await disabled_client.close()
            set_redis_client(None)
