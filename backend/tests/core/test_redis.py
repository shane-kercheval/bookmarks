"""
Tests for the Redis client module.

Note: Basic Redis operations (get/set/delete/ping) are not tested here as they
just wrap the redis.asyncio library. We test our custom Lua scripts and
fallback behavior which contain actual business logic.
"""
import time
import uuid

from core.redis import RedisClient


class TestRedisLuaScripts:
    """Tests for custom Lua scripts used in rate limiting."""

    async def test__lua_scripts__loaded_on_connect(
        self, redis_client: RedisClient,
    ) -> None:
        """Lua scripts are loaded when connecting."""
        assert redis_client.sliding_window_sha is not None
        assert redis_client.fixed_window_sha is not None

    async def test__evalsha__sliding_window_script(
        self, redis_client: RedisClient,
    ) -> None:
        """Sliding window Lua script works correctly."""
        key = "test:sliding"
        now = int(time.time())
        window = 60  # 1 minute
        limit = 3

        # Make 3 requests - all should be allowed
        for i in range(3):
            result = await redis_client.evalsha(
                redis_client.sliding_window_sha,
                1,
                key,
                now + i,  # Slightly different timestamps
                window,
                limit,
                str(uuid.uuid4()),
            )
            assert result[0] == 1  # allowed
            assert result[1] == limit - i - 1  # remaining (2, 1, 0)

        # 4th request should be denied
        result = await redis_client.evalsha(
            redis_client.sliding_window_sha,
            1,
            key,
            now + 3,
            window,
            limit,
            str(uuid.uuid4()),
        )
        assert result[0] == 0  # denied
        assert result[1] == 0  # remaining
        assert result[2] > 0  # retry_after

    async def test__evalsha__fixed_window_script(
        self, redis_client: RedisClient,
    ) -> None:
        """Fixed window Lua script works correctly."""
        key = "test:fixed"
        limit = 3
        window = 60

        # Make 3 requests - all should be allowed
        for i in range(3):
            result = await redis_client.evalsha(
                redis_client.fixed_window_sha,
                1,
                key,
                limit,
                window,
            )
            assert result[0] == 1  # allowed
            assert result[1] == limit - i - 1  # remaining

        # 4th request should be denied
        result = await redis_client.evalsha(
            redis_client.fixed_window_sha,
            1,
            key,
            limit,
            window,
        )
        assert result[0] == 0  # denied
        assert result[1] == 0  # remaining
        assert result[3] > 0  # retry_after


class TestRedisClientDisabled:
    """Tests for disabled Redis client."""

    async def test__disabled_client__returns_false_on_ping(self) -> None:
        """Disabled client returns False on ping."""
        client = RedisClient("redis://localhost:6379", enabled=False)
        await client.connect()

        assert client.is_connected is False
        assert await client.ping() is False

        await client.close()

    async def test__disabled_client__returns_none_on_get(self) -> None:
        """Disabled client returns None on get."""
        client = RedisClient("redis://localhost:6379", enabled=False)
        await client.connect()

        result = await client.get("any:key")
        assert result is None

        await client.close()

    async def test__disabled_client__returns_false_on_setex(self) -> None:
        """Disabled client returns False on setex."""
        client = RedisClient("redis://localhost:6379", enabled=False)
        await client.connect()

        result = await client.setex("any:key", 60, "value")
        assert result is False

        await client.close()


class TestRedisClientUnavailable:
    """Tests for Redis client when server is unavailable."""

    async def test__unavailable_server__connect_fails_gracefully(self) -> None:
        """Client handles unavailable server gracefully."""
        # Use invalid port
        client = RedisClient("redis://localhost:59999", enabled=True)
        await client.connect()

        # Should not be connected but should not raise
        assert client.is_connected is False

        await client.close()

    async def test__unavailable_server__operations_fail_gracefully(self) -> None:
        """Operations return safe defaults when server unavailable."""
        client = RedisClient("redis://localhost:59999", enabled=True)
        await client.connect()

        # All operations should return safe defaults
        assert await client.ping() is False
        assert await client.get("key") is None
        assert await client.setex("key", 60, "value") is False
        assert await client.delete("key") is False
        assert await client.evalsha("sha", 1, "key") is None

        await client.close()
