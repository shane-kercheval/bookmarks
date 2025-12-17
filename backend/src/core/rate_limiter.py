"""Simple in-memory rate limiter for API endpoints."""
import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class RateLimitState:
    """Tracks request timestamps for a single key."""

    timestamps: list[float] = field(default_factory=list)


class RateLimiter:
    """
    Simple in-memory rate limiter using sliding window algorithm.

    Thread-safe implementation suitable for single-process deployments.
    For multi-process deployments, use Redis-based rate limiting instead.

    Example:
        limiter = RateLimiter(max_requests=10, window_seconds=60)

        # In endpoint
        if not limiter.is_allowed(user_id):
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
    """

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        """
        Initialize rate limiter.

        Args:
            max_requests: Maximum number of requests allowed in the window.
            window_seconds: Time window in seconds.
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._state: dict[str, RateLimitState] = defaultdict(RateLimitState)
        self._lock = Lock()

    def is_allowed(self, key: str) -> bool:
        """
        Check if a request is allowed for the given key.

        Args:
            key: Identifier for the rate limit (e.g., user_id).

        Returns:
            True if request is allowed, False if rate limit exceeded.
        """
        now = time.time()
        window_start = now - self.window_seconds

        with self._lock:
            state = self._state[key]

            # Remove timestamps outside the window
            state.timestamps = [ts for ts in state.timestamps if ts > window_start]

            # Check if under limit
            if len(state.timestamps) >= self.max_requests:
                return False

            # Record this request
            state.timestamps.append(now)
            return True

    def get_retry_after(self, key: str) -> int:
        """
        Get seconds until the rate limit resets for a key.

        Args:
            key: Identifier for the rate limit.

        Returns:
            Seconds until the oldest request expires from the window.
        """
        now = time.time()
        window_start = now - self.window_seconds

        with self._lock:
            state = self._state[key]
            # Filter to timestamps in window
            valid_timestamps = [ts for ts in state.timestamps if ts > window_start]

            if not valid_timestamps:
                return 0

            oldest = min(valid_timestamps)
            return max(1, int((oldest + self.window_seconds) - now))

    def reset(self, key: str) -> None:
        """
        Reset rate limit for a key (useful for testing).

        Args:
            key: Identifier to reset.
        """
        with self._lock:
            if key in self._state:
                del self._state[key]

    def clear_all(self) -> None:
        """Clear all rate limit state (useful for testing)."""
        with self._lock:
            self._state.clear()


# Singleton rate limiter for fetch-metadata endpoint
# 15 requests per minute per user
fetch_metadata_limiter = RateLimiter(max_requests=15, window_seconds=60)
