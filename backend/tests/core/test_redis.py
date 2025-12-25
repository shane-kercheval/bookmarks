"""
Tests for the Redis client module.

Note: Basic Redis operations (get/set/delete/ping) are not tested here as they
just wrap the redis.asyncio library. We test our custom Lua scripts and
fallback behavior which contain actual business logic.
"""
import time
import uuid
from unittest.mock import AsyncMock, patch

from redis.exceptions import NoScriptError, RedisError

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


class TestRedisOperationFailures:
    """Tests for Redis operation failures when connected (network blips, timeouts)."""

    async def test__get__returns_none_on_redis_error(
        self, redis_client: RedisClient,
    ) -> None:
        """GET returns None when Redis raises an error mid-operation."""
        with patch.object(
            redis_client._client, "get",
            new_callable=AsyncMock,
            side_effect=RedisError("Connection lost"),
        ):
            result = await redis_client.get("any-key")

        assert result is None

    async def test__setex__returns_false_on_redis_error(
        self, redis_client: RedisClient,
    ) -> None:
        """SETEX returns False when Redis raises an error mid-operation."""
        with patch.object(
            redis_client._client, "setex",
            new_callable=AsyncMock,
            side_effect=RedisError("Connection lost"),
        ):
            result = await redis_client.setex("any-key", 60, "value")

        assert result is False

    async def test__delete__returns_false_on_redis_error(
        self, redis_client: RedisClient,
    ) -> None:
        """DELETE returns False when Redis raises an error mid-operation."""
        with patch.object(
            redis_client._client, "delete",
            new_callable=AsyncMock,
            side_effect=RedisError("Connection lost"),
        ):
            result = await redis_client.delete("any-key")

        assert result is False

    async def test__evalsha__returns_none_on_redis_error(
        self, redis_client: RedisClient,
    ) -> None:
        """EVALSHA returns None when Redis raises an error mid-operation."""
        with patch.object(
            redis_client._client, "evalsha",
            new_callable=AsyncMock,
            side_effect=RedisError("Connection lost"),
        ):
            result = await redis_client.evalsha("some-sha", 1, "key")

        assert result is None

    async def test__ping__returns_false_on_redis_error(
        self, redis_client: RedisClient,
    ) -> None:
        """PING returns False when Redis raises an error mid-operation."""
        with patch.object(
            redis_client._client, "ping",
            new_callable=AsyncMock,
            side_effect=RedisError("Connection lost"),
        ):
            result = await redis_client.ping()

        assert result is False

    async def test__flushdb__returns_false_on_redis_error(
        self, redis_client: RedisClient,
    ) -> None:
        """FLUSHDB returns False when Redis raises an error mid-operation."""
        with patch.object(
            redis_client._client, "flushdb",
            new_callable=AsyncMock,
            side_effect=RedisError("Connection lost"),
        ):
            result = await redis_client.flushdb()

        assert result is False

    async def test__script_load__returns_none_on_redis_error(
        self, redis_client: RedisClient,
    ) -> None:
        """SCRIPT LOAD returns None when Redis raises an error mid-operation."""
        with patch.object(
            redis_client._client, "script_load",
            new_callable=AsyncMock,
            side_effect=RedisError("Connection lost"),
        ):
            result = await redis_client.script_load("return 1")

        assert result is None


class TestNoScriptErrorHandling:
    """Tests for NOSCRIPT error handling (script reload after Redis restart)."""

    async def test__eval_sliding_window__reloads_on_noscript(
        self, redis_client: RedisClient,
    ) -> None:
        """Sliding window reloads scripts on NOSCRIPT error and retries."""
        key = "test:noscript:sliding"
        now = int(time.time())

        # First call raises NOSCRIPT, simulating Redis restart
        call_count = 0
        original_evalsha = redis_client._client.evalsha

        async def mock_evalsha(*args: object, **kwargs: object) -> list[int]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise NoScriptError("NOSCRIPT No matching script")
            return await original_evalsha(*args, **kwargs)

        with patch.object(redis_client._client, "evalsha", side_effect=mock_evalsha):
            result = await redis_client.eval_sliding_window(
                key=key,
                now=now,
                window_seconds=60,
                max_requests=10,
                request_id="test-uuid",
            )

        # Should succeed after reload and retry
        assert result is not None
        assert result[0] == 1  # allowed
        assert call_count == 2  # First call failed, second succeeded

    async def test__eval_fixed_window__reloads_on_noscript(
        self, redis_client: RedisClient,
    ) -> None:
        """Fixed window reloads scripts on NOSCRIPT error and retries."""
        key = "test:noscript:fixed"

        call_count = 0
        original_evalsha = redis_client._client.evalsha

        async def mock_evalsha(*args: object, **kwargs: object) -> list[int]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise NoScriptError("NOSCRIPT No matching script")
            return await original_evalsha(*args, **kwargs)

        with patch.object(redis_client._client, "evalsha", side_effect=mock_evalsha):
            result = await redis_client.eval_fixed_window(
                key=key,
                max_requests=10,
                window_seconds=60,
            )

        # Should succeed after reload and retry
        assert result is not None
        assert result[0] == 1  # allowed
        assert call_count == 2

    async def test__eval_sliding_window__returns_none_if_retry_fails(
        self, redis_client: RedisClient,
    ) -> None:
        """Returns None if retry also fails after reload."""
        with patch.object(
            redis_client._client, "evalsha",
            new_callable=AsyncMock,
            side_effect=NoScriptError("NOSCRIPT No matching script"),
        ):
            # Script reload will work but evalsha keeps failing
            result = await redis_client.eval_sliding_window(
                key="test:fail",
                now=int(time.time()),
                window_seconds=60,
                max_requests=10,
                request_id="test-uuid",
            )

        # Should return None after retry fails
        assert result is None

    async def test__eval_fixed_window__returns_none_if_retry_fails(
        self, redis_client: RedisClient,
    ) -> None:
        """Returns None if retry also fails after reload."""
        with patch.object(
            redis_client._client, "evalsha",
            new_callable=AsyncMock,
            side_effect=NoScriptError("NOSCRIPT No matching script"),
        ):
            result = await redis_client.eval_fixed_window(
                key="test:fail",
                max_requests=10,
                window_seconds=60,
            )

        assert result is None

    async def test__eval_sliding_window__returns_none_when_not_connected(
        self,
    ) -> None:
        """Returns None when client is not connected."""
        client = RedisClient("redis://localhost:6379", enabled=False)
        await client.connect()

        result = await client.eval_sliding_window(
            key="test:key",
            now=int(time.time()),
            window_seconds=60,
            max_requests=10,
            request_id="test-uuid",
        )

        assert result is None
        await client.close()

    async def test__eval_fixed_window__returns_none_when_not_connected(
        self,
    ) -> None:
        """Returns None when client is not connected."""
        client = RedisClient("redis://localhost:6379", enabled=False)
        await client.connect()

        result = await client.eval_fixed_window(
            key="test:key",
            max_requests=10,
            window_seconds=60,
        )

        assert result is None
        await client.close()


class TestEvalScriptMethods:
    """Tests for the new eval_sliding_window and eval_fixed_window methods."""

    async def test__eval_sliding_window__works_correctly(
        self, redis_client: RedisClient,
    ) -> None:
        """Sliding window method works correctly."""
        key = "test:eval:sliding"
        now = int(time.time())

        # Make 3 requests - all should be allowed
        for i in range(3):
            result = await redis_client.eval_sliding_window(
                key=key,
                now=now + i,
                window_seconds=60,
                max_requests=3,
                request_id=str(uuid.uuid4()),
            )
            assert result is not None
            assert result[0] == 1  # allowed
            assert result[1] == 3 - i - 1  # remaining

        # 4th request should be denied
        result = await redis_client.eval_sliding_window(
            key=key,
            now=now + 3,
            window_seconds=60,
            max_requests=3,
            request_id=str(uuid.uuid4()),
        )
        assert result is not None
        assert result[0] == 0  # denied

    async def test__eval_fixed_window__works_correctly(
        self, redis_client: RedisClient,
    ) -> None:
        """Fixed window method works correctly."""
        key = "test:eval:fixed"

        # Make 3 requests - all should be allowed
        for i in range(3):
            result = await redis_client.eval_fixed_window(
                key=key,
                max_requests=3,
                window_seconds=60,
            )
            assert result is not None
            assert result[0] == 1  # allowed
            assert result[1] == 3 - i - 1  # remaining

        # 4th request should be denied
        result = await redis_client.eval_fixed_window(
            key=key,
            max_requests=3,
            window_seconds=60,
        )
        assert result is not None
        assert result[0] == 0  # denied
