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


class TestDailyLimits:
    """Tests for daily rate limit enforcement."""

    async def test__check__daily_limit_blocks_after_minute_limit_passes(
        self, redis_client: RedisClient,
    ) -> None:
        """
        Daily limit blocks requests even when per-minute limit has room.

        Scenario: User exhausts daily limit over multiple minute windows.
        Per-minute sliding window resets, but daily fixed window still blocks.
        """
        limiter = RedisRateLimiter()
        user_id = 5000  # Unique user for isolation

        # AUTH0 READ: 300/min, 4000/day
        # Pre-fill the daily limit directly using the fixed window key
        daily_key = f"rate:{user_id}:daily:general"

        # Exhaust daily limit by incrementing counter to 4000
        for _ in range(4000):
            await redis_client.evalsha(
                redis_client.fixed_window_sha,
                1,
                daily_key,
                4000,  # limit
                86400,  # window (24 hours)
            )

        # The per-minute limit should still have room (we haven't used it)
        # But daily limit is exhausted, so request should be blocked
        result = await limiter.check(
            user_id=user_id,
            auth_type=AuthType.AUTH0,
            operation_type=OperationType.READ,
        )

        assert result.allowed is False, "Should be blocked by daily limit"
        # Daily limit retry_after should be much longer than minute limit
        assert result.retry_after > 60, "Daily retry_after should be > 60 seconds"

    async def test__check__general_and_sensitive_have_separate_daily_pools(
        self, redis_client: RedisClient,
    ) -> None:
        """
        READ/WRITE share 'general' daily pool, SENSITIVE has separate pool.

        Exhausting general daily limit should not affect sensitive limit.
        """
        limiter = RedisRateLimiter()
        user_id = 5001  # Unique user for isolation

        # Exhaust the general daily pool (READ/WRITE share this)
        general_key = f"rate:{user_id}:daily:general"
        for _ in range(4000):
            await redis_client.evalsha(
                redis_client.fixed_window_sha,
                1,
                general_key,
                4000,
                86400,
            )

        # READ should be blocked (uses general pool)
        read_result = await limiter.check(
            user_id=user_id,
            auth_type=AuthType.AUTH0,
            operation_type=OperationType.READ,
        )
        assert read_result.allowed is False, "READ should be blocked (general pool exhausted)"

        # SENSITIVE should still be allowed (separate pool)
        sensitive_result = await limiter.check(
            user_id=user_id,
            auth_type=AuthType.AUTH0,
            operation_type=OperationType.SENSITIVE,
        )
        assert sensitive_result.allowed is True, "SENSITIVE should be allowed (separate pool)"

    async def test__check__sensitive_daily_pool_is_independent(
        self, redis_client: RedisClient,
    ) -> None:
        """Exhausting sensitive daily limit does not affect general pool."""
        limiter = RedisRateLimiter()
        user_id = 5002  # Unique user for isolation

        # Exhaust the sensitive daily pool (250/day for Auth0)
        sensitive_key = f"rate:{user_id}:daily:sensitive"
        for _ in range(250):
            await redis_client.evalsha(
                redis_client.fixed_window_sha,
                1,
                sensitive_key,
                250,
                86400,
            )

        # SENSITIVE should be blocked
        sensitive_result = await limiter.check(
            user_id=user_id,
            auth_type=AuthType.AUTH0,
            operation_type=OperationType.SENSITIVE,
        )
        assert sensitive_result.allowed is False, "SENSITIVE should be blocked"

        # READ should still be allowed (general pool is separate)
        read_result = await limiter.check(
            user_id=user_id,
            auth_type=AuthType.AUTH0,
            operation_type=OperationType.READ,
        )
        assert read_result.allowed is True, "READ should be allowed (general pool not affected)"

    async def test__check__daily_limit_reset_is_future_timestamp(
        self, redis_client: RedisClient,  # noqa: ARG002
    ) -> None:
        """Daily limit returns reset timestamp in the future (within 24 hours)."""
        limiter = RedisRateLimiter()
        user_id = 5003
        now = int(time.time())

        # Make a request to trigger daily limit tracking
        result = await limiter.check(
            user_id=user_id,
            auth_type=AuthType.AUTH0,
            operation_type=OperationType.READ,
        )

        # Reset should be in the future but within 24 hours
        # Note: The per-minute result is returned when both pass, so check that
        assert result.reset > now
        assert result.reset <= now + 86400, "Reset should be within 24 hours"

    async def test__check__write_operations_share_general_daily_pool(
        self, redis_client: RedisClient,
    ) -> None:
        """WRITE operations use the same 'general' daily pool as READ."""
        limiter = RedisRateLimiter()
        user_id = 5004

        # Exhaust general daily pool
        general_key = f"rate:{user_id}:daily:general"
        for _ in range(4000):
            await redis_client.evalsha(
                redis_client.fixed_window_sha,
                1,
                general_key,
                4000,
                86400,
            )

        # WRITE should be blocked (shares general pool with READ)
        write_result = await limiter.check(
            user_id=user_id,
            auth_type=AuthType.AUTH0,
            operation_type=OperationType.WRITE,
        )
        assert write_result.allowed is False, "WRITE should be blocked (general pool exhausted)"


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

    async def test__check__allows_request_when_script_sha_not_loaded(
        self, redis_client: RedisClient,
    ) -> None:
        """
        Requests are allowed when Lua scripts failed to load (fail-open).

        This handles the edge case where Redis connects but script loading fails.
        """
        # Save original SHAs
        original_sliding = redis_client._sliding_window_sha
        original_fixed = redis_client._fixed_window_sha

        # Simulate scripts not loaded
        redis_client._sliding_window_sha = None
        redis_client._fixed_window_sha = None

        try:
            limiter = RedisRateLimiter()
            result = await limiter.check(
                user_id=1,
                auth_type=AuthType.AUTH0,
                operation_type=OperationType.READ,
            )

            # Should fail open
            assert result.allowed is True
        finally:
            # Restore SHAs
            redis_client._sliding_window_sha = original_sliding
            redis_client._fixed_window_sha = original_fixed
