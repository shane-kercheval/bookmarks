"""Redis-based rate limiter with tiered limits for different auth and operation types."""
import logging
import time
import uuid
from dataclasses import dataclass
from enum import Enum

from core.redis import get_redis_client

logger = logging.getLogger(__name__)


class AuthType(Enum):
    """Authentication type for rate limiting."""

    PAT = "pat"
    AUTH0 = "auth0"


class OperationType(Enum):
    """Operation type for rate limiting."""

    READ = "read"
    WRITE = "write"
    SENSITIVE = "sensitive"  # External HTTP calls, AI/LLM, bulk operations


@dataclass
class RateLimitConfig:
    """Rate limit configuration for a specific auth/operation combination."""

    requests_per_minute: int
    requests_per_day: int


@dataclass
class RateLimitResult:
    """Result of a rate limit check with all info needed for headers."""

    allowed: bool
    limit: int  # Max requests in current window
    remaining: int  # Requests remaining in current window
    reset: int  # Unix timestamp when window resets
    retry_after: int  # Seconds until retry allowed (0 if allowed)


class RateLimitExceededError(Exception):
    """Raised when rate limit is exceeded."""

    def __init__(self, result: RateLimitResult) -> None:
        self.result = result
        super().__init__("Rate limit exceeded")


# Rate limit configuration by (auth_type, operation_type)
# Daily caps: general (read/write) vs sensitive are tracked separately
RATE_LIMITS: dict[tuple[AuthType, OperationType], RateLimitConfig] = {
    (AuthType.PAT, OperationType.READ): RateLimitConfig(120, 2000),
    (AuthType.PAT, OperationType.WRITE): RateLimitConfig(60, 2000),
    # PAT + SENSITIVE = not allowed (handled by auth dependency, returns 403)
    (AuthType.AUTH0, OperationType.READ): RateLimitConfig(300, 4000),
    (AuthType.AUTH0, OperationType.WRITE): RateLimitConfig(90, 4000),
    (AuthType.AUTH0, OperationType.SENSITIVE): RateLimitConfig(30, 250),
}

# Endpoints classified as SENSITIVE (require Auth0, stricter limits)
# Format: (HTTP_METHOD, path_without_query_params)
SENSITIVE_ENDPOINTS: set[tuple[str, str]] = {
    ("GET", "/bookmarks/fetch-metadata"),
    # Future: AI/LLM endpoints, bulk operations
}


class RedisRateLimiter:
    """Redis-based rate limiter with sliding window (per-minute) and fixed window (daily)."""

    async def check(
        self,
        user_id: int,
        auth_type: AuthType,
        operation_type: OperationType,
    ) -> RateLimitResult:
        """
        Check if request is allowed and return full rate limit info.

        Returns RateLimitResult with allowed status and header values.
        Falls back to allowing requests if Redis is unavailable.
        """
        config = RATE_LIMITS.get((auth_type, operation_type))
        if not config:
            # No limit configured (e.g., PAT + SENSITIVE) - return permissive result
            # The auth layer should have already blocked this, but be defensive
            return RateLimitResult(
                allowed=True, limit=0, remaining=0, reset=0, retry_after=0,
            )

        redis_client = get_redis_client()
        if redis_client is None or not redis_client.is_connected:
            # Redis unavailable - fail open
            logger.warning("redis_unavailable", extra={"operation": "rate_limit"})
            return RateLimitResult(
                allowed=True,
                limit=config.requests_per_minute,
                remaining=config.requests_per_minute,
                reset=0,
                retry_after=0,
            )

        now = int(time.time())

        # Check minute limit (sliding window for precision)
        minute_key = f"rate:{user_id}:{auth_type.value}:{operation_type.value}:min"
        minute_result = await self._check_sliding_window(
            minute_key, config.requests_per_minute, 60, now,
        )
        if not minute_result.allowed:
            logger.warning(
                "rate_limit_exceeded",
                extra={
                    "user_id": user_id,
                    "operation": operation_type.value,
                    "auth_type": auth_type.value,
                    "limit_type": "per_minute",
                },
            )
            return minute_result

        # Check daily limit (fixed window - simpler, lower memory)
        daily_pool = "sensitive" if operation_type == OperationType.SENSITIVE else "general"
        day_key = f"rate:{user_id}:daily:{daily_pool}"
        day_result = await self._check_fixed_window(
            day_key, config.requests_per_day, 86400, now,
        )
        if not day_result.allowed:
            logger.warning(
                "rate_limit_exceeded",
                extra={
                    "user_id": user_id,
                    "operation": operation_type.value,
                    "auth_type": auth_type.value,
                    "limit_type": "daily",
                },
            )
            return day_result

        # Both passed - return the per-minute result (more relevant for headers)
        return minute_result

    async def _check_sliding_window(
        self, key: str, max_requests: int, window_seconds: int, now: int,
    ) -> RateLimitResult:
        """
        Sliding window check using Redis sorted set.

        More accurate than fixed window - prevents gaming at window boundaries.
        Used for per-minute limits where precision matters.
        """
        redis_client = get_redis_client()
        if redis_client is None or redis_client.sliding_window_sha is None:
            # Redis unavailable - fail open
            return RateLimitResult(
                allowed=True,
                limit=max_requests,
                remaining=max_requests,
                reset=0,
                retry_after=0,
            )

        result = await redis_client.evalsha(
            redis_client.sliding_window_sha,
            1,  # number of keys
            key,
            now,
            window_seconds,
            max_requests,
            str(uuid.uuid4()),  # unique request ID
        )

        if result is None:
            # Redis unavailable - fail open
            return RateLimitResult(
                allowed=True,
                limit=max_requests,
                remaining=max_requests,
                reset=0,
                retry_after=0,
            )

        allowed, remaining, retry_after = result
        return RateLimitResult(
            allowed=bool(allowed),
            limit=max_requests,
            remaining=max(0, remaining),
            reset=now + window_seconds,
            retry_after=max(0, retry_after) if not allowed else 0,
        )

    async def _check_fixed_window(
        self, key: str, max_requests: int, window_seconds: int, now: int,
    ) -> RateLimitResult:
        """
        Fixed window check using Lua script for atomicity.

        Simpler and lower memory than sliding window.
        Used for daily limits where slight boundary imprecision is acceptable.
        """
        redis_client = get_redis_client()
        if redis_client is None or redis_client.fixed_window_sha is None:
            # Redis unavailable - fail open
            return RateLimitResult(
                allowed=True,
                limit=max_requests,
                remaining=max_requests,
                reset=0,
                retry_after=0,
            )

        result = await redis_client.evalsha(
            redis_client.fixed_window_sha,
            1,  # number of keys
            key,
            max_requests,
            window_seconds,
        )

        if result is None:
            # Redis unavailable - fail open
            return RateLimitResult(
                allowed=True,
                limit=max_requests,
                remaining=max_requests,
                reset=0,
                retry_after=0,
            )

        allowed, remaining, ttl, retry_after = result
        return RateLimitResult(
            allowed=bool(allowed),
            limit=max_requests,
            remaining=max(0, remaining),
            reset=now + ttl if ttl > 0 else now + window_seconds,
            retry_after=max(0, retry_after) if not allowed else 0,
        )


# Global rate limiter instance
rate_limiter = RedisRateLimiter()


def get_operation_type(method: str, path: str) -> OperationType:
    """Determine operation type from HTTP method and path."""
    if (method, path) in SENSITIVE_ENDPOINTS:
        return OperationType.SENSITIVE
    if method == "GET":
        return OperationType.READ
    return OperationType.WRITE
