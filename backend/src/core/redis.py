"""Redis client with connection pooling and graceful fallback."""
import logging
from typing import Any

from redis.asyncio import ConnectionPool, Redis
from redis.asyncio.client import Pipeline
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

# Lua script for sliding window rate limiting (per-minute limits)
# More accurate than fixed window - prevents gaming at window boundaries
SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local request_id = ARGV[4]

-- Remove old entries outside the window
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)

-- Count current entries
local count = redis.call('ZCARD', key)

if count < limit then
    -- Add new entry with UUID suffix to prevent collisions
    redis.call('ZADD', key, now, now .. ':' .. request_id)
    redis.call('EXPIRE', key, window)
    return {1, limit - count - 1, 0}  -- allowed, remaining, no retry needed
else
    -- Get oldest entry for retry-after calculation
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after = 0
    if oldest and oldest[2] then
        retry_after = math.ceil((oldest[2] + window) - now)
    end
    return {0, 0, retry_after}  -- denied, 0 remaining, retry after
end
"""

# Lua script for fixed window rate limiting (daily limits)
# Atomic: increments counter and sets expiry only on first request
FIXED_WINDOW_SCRIPT = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])

local count = redis.call('INCR', key)
if count == 1 then
    redis.call('EXPIRE', key, window)
end
local ttl = redis.call('TTL', key)

if count <= limit then
    return {1, limit - count, ttl, 0}  -- allowed, remaining, ttl, no retry
else
    return {0, 0, ttl, ttl}  -- denied, 0 remaining, ttl, retry_after=ttl
end
"""


class RedisClient:
    """Async Redis client with connection pooling and graceful fallback."""

    def __init__(self, url: str, enabled: bool = True) -> None:
        self._url = url
        self._enabled = enabled
        self._pool: ConnectionPool | None = None
        self._client: Redis | None = None
        self._sliding_window_sha: str | None = None
        self._fixed_window_sha: str | None = None

    async def connect(self) -> None:
        """Initialize connection pool and load Lua scripts."""
        if not self._enabled:
            logger.info("Redis disabled by configuration")
            return
        try:
            self._pool = ConnectionPool.from_url(self._url, max_connections=10)
            self._client = Redis(connection_pool=self._pool)
            # Verify connection
            await self._client.ping()
            # Load Lua scripts
            await self._load_scripts()
            logger.info("Redis connected successfully")
        except RedisError as e:
            logger.warning("Redis connection failed: %s", e)
            self._client = None
            self._pool = None

    async def _load_scripts(self) -> None:
        """Load Lua scripts and store their SHAs for evalsha calls."""
        if not self._client:
            return
        try:
            self._sliding_window_sha = await self._client.script_load(SLIDING_WINDOW_SCRIPT)
            self._fixed_window_sha = await self._client.script_load(FIXED_WINDOW_SCRIPT)
            logger.info("Redis Lua scripts loaded")
        except RedisError as e:
            logger.warning("Failed to load Lua scripts: %s", e)

    async def close(self) -> None:
        """Close connection pool."""
        if self._client:
            await self._client.aclose()
            self._client = None
            self._pool = None
            logger.info("Redis connection closed")

    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._client is not None

    @property
    def sliding_window_sha(self) -> str | None:
        """Get SHA for sliding window script."""
        return self._sliding_window_sha

    @property
    def fixed_window_sha(self) -> str | None:
        """Get SHA for fixed window script."""
        return self._fixed_window_sha

    async def ping(self) -> bool:
        """Check Redis connectivity."""
        if not self._client:
            return False
        try:
            return await self._client.ping()
        except RedisError:
            return False

    async def get(self, key: str) -> bytes | None:
        """Get value, returns None if Redis unavailable."""
        if not self._client:
            return None
        try:
            return await self._client.get(key)
        except RedisError as e:
            logger.warning("Redis GET failed: %s", e)
            return None

    async def setex(self, key: str, seconds: int, value: str | bytes) -> bool:
        """Set value with expiry, returns False if Redis unavailable."""
        if not self._client:
            return False
        try:
            await self._client.setex(key, seconds, value)
            return True
        except RedisError as e:
            logger.warning("Redis SETEX failed: %s", e)
            return False

    async def delete(self, *keys: str) -> bool:
        """Delete key(s), returns False if Redis unavailable."""
        if not self._client:
            return False
        try:
            await self._client.delete(*keys)
            return True
        except RedisError as e:
            logger.warning("Redis DELETE failed: %s", e)
            return False

    async def pipeline(self) -> Pipeline | None:
        """Get pipeline for batched operations, returns None if unavailable."""
        if not self._client:
            return None
        return self._client.pipeline()

    async def evalsha(self, sha: str, numkeys: int, *args: Any) -> Any:
        """Execute Lua script by SHA, returns None if Redis unavailable."""
        if not self._client:
            return None
        try:
            return await self._client.evalsha(sha, numkeys, *args)
        except RedisError as e:
            logger.warning("Redis EVALSHA failed: %s", e)
            return None

    async def script_load(self, script: str) -> str | None:
        """Load Lua script and return SHA, returns None if Redis unavailable."""
        if not self._client:
            return None
        try:
            return await self._client.script_load(script)
        except RedisError as e:
            logger.warning("Redis SCRIPT LOAD failed: %s", e)
            return None

    async def flushdb(self) -> bool:
        """Flush current database (for testing). Returns False if unavailable."""
        if not self._client:
            return False
        try:
            await self._client.flushdb()
            return True
        except RedisError as e:
            logger.warning("Redis FLUSHDB failed: %s", e)
            return False


# Global Redis client state using a container to avoid global statement
class _RedisState:
    """Container for global Redis client state."""

    client: RedisClient | None = None


_state = _RedisState()


def get_redis_client() -> RedisClient | None:
    """Get the global Redis client instance."""
    return _state.client


def set_redis_client(client: RedisClient | None) -> None:
    """Set the global Redis client instance."""
    _state.client = client
