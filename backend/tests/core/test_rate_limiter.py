"""Tests for the rate limiter module."""
import time

from core.rate_limiter import RateLimiter


class TestRateLimiter:
    """Tests for RateLimiter class."""

    def test__is_allowed__under_limit(self) -> None:
        """Requests under the limit are allowed."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)

        for _ in range(5):
            assert limiter.is_allowed("user1") is True

    def test__is_allowed__at_limit(self) -> None:
        """Request at the limit is blocked."""
        limiter = RateLimiter(max_requests=3, window_seconds=60)

        # First 3 should be allowed
        assert limiter.is_allowed("user1") is True
        assert limiter.is_allowed("user1") is True
        assert limiter.is_allowed("user1") is True

        # 4th should be blocked
        assert limiter.is_allowed("user1") is False

    def test__is_allowed__separate_keys(self) -> None:
        """Different keys have separate limits."""
        limiter = RateLimiter(max_requests=2, window_seconds=60)

        # User 1 hits limit
        assert limiter.is_allowed("user1") is True
        assert limiter.is_allowed("user1") is True
        assert limiter.is_allowed("user1") is False

        # User 2 still has quota
        assert limiter.is_allowed("user2") is True
        assert limiter.is_allowed("user2") is True
        assert limiter.is_allowed("user2") is False

    def test__is_allowed__window_expiry(self) -> None:
        """Requests are allowed after window expires."""
        limiter = RateLimiter(max_requests=2, window_seconds=1)

        # Hit the limit
        assert limiter.is_allowed("user1") is True
        assert limiter.is_allowed("user1") is True
        assert limiter.is_allowed("user1") is False

        # Wait for window to expire
        time.sleep(1.1)

        # Should be allowed again
        assert limiter.is_allowed("user1") is True

    def test__is_allowed__sliding_window(self) -> None:
        """Sliding window correctly expires old requests."""
        limiter = RateLimiter(max_requests=3, window_seconds=2)

        # Make 2 requests
        assert limiter.is_allowed("user1") is True
        assert limiter.is_allowed("user1") is True

        # Wait a bit
        time.sleep(1.1)

        # Make 1 more (should work - total 3 in window)
        assert limiter.is_allowed("user1") is True

        # This should fail (4 in window)
        assert limiter.is_allowed("user1") is False

        # Wait for first 2 to expire
        time.sleep(1.0)

        # Should work again
        assert limiter.is_allowed("user1") is True

    def test__get_retry_after__no_requests(self) -> None:
        """Returns 0 when no requests have been made."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        assert limiter.get_retry_after("user1") == 0

    def test__get_retry_after__under_limit(self) -> None:
        """Returns time until oldest request expires."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)

        limiter.is_allowed("user1")
        retry_after = limiter.get_retry_after("user1")

        # Should be close to window_seconds
        assert 55 < retry_after <= 60

    def test__get_retry_after__at_limit(self) -> None:
        """Returns correct time when at limit."""
        limiter = RateLimiter(max_requests=2, window_seconds=10)

        # Hit the limit
        limiter.is_allowed("user1")
        time.sleep(0.5)
        limiter.is_allowed("user1")

        # Get retry after
        retry_after = limiter.get_retry_after("user1")

        # Should be close to time until first request expires (around 9.5 seconds)
        assert 8 < retry_after <= 10

    def test__reset__clears_key(self) -> None:
        """Reset clears the state for a key."""
        limiter = RateLimiter(max_requests=2, window_seconds=60)

        # Hit the limit
        limiter.is_allowed("user1")
        limiter.is_allowed("user1")
        assert limiter.is_allowed("user1") is False

        # Reset
        limiter.reset("user1")

        # Should be allowed again
        assert limiter.is_allowed("user1") is True

    def test__clear_all__clears_all_state(self) -> None:
        """clear_all clears all keys."""
        limiter = RateLimiter(max_requests=1, window_seconds=60)

        # Hit limits for multiple users
        limiter.is_allowed("user1")
        limiter.is_allowed("user2")
        assert limiter.is_allowed("user1") is False
        assert limiter.is_allowed("user2") is False

        # Clear all
        limiter.clear_all()

        # All users should be allowed
        assert limiter.is_allowed("user1") is True
        assert limiter.is_allowed("user2") is True

    def test__thread_safety(self) -> None:
        """Rate limiter is thread-safe."""
        import threading

        limiter = RateLimiter(max_requests=100, window_seconds=60)
        results: list[bool] = []
        lock = threading.Lock()

        def make_requests() -> None:
            for _ in range(20):
                result = limiter.is_allowed("user1")
                with lock:
                    results.append(result)

        threads = [threading.Thread(target=make_requests) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have exactly 100 allowed, rest blocked
        allowed = sum(1 for r in results if r)
        blocked = sum(1 for r in results if not r)

        assert allowed == 100
        assert blocked == 100  # 200 total requests - 100 allowed = 100 blocked
