"""
Tests verifying rate limiting is applied to all authenticated endpoints.

These tests use a low rate limit (2 requests per minute) to verify that
rate limiting is properly integrated into each endpoint via the auth dependencies.
"""
import pytest
from httpx import AsyncClient

from core.rate_limit_config import AuthType, OperationType, RateLimitConfig


# Very low limit for testing - 2 requests per minute
TEST_RATE_LIMIT = RateLimitConfig(requests_per_minute=2, requests_per_day=100)


@pytest.fixture
def low_rate_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch rate limits to be very low for testing."""
    from core import rate_limit_config

    # Create test limits with 2 requests per minute
    test_limits = {
        (AuthType.PAT, OperationType.READ): TEST_RATE_LIMIT,
        (AuthType.PAT, OperationType.WRITE): TEST_RATE_LIMIT,
        (AuthType.AUTH0, OperationType.READ): TEST_RATE_LIMIT,
        (AuthType.AUTH0, OperationType.WRITE): TEST_RATE_LIMIT,
        (AuthType.AUTH0, OperationType.SENSITIVE): TEST_RATE_LIMIT,
    }
    # Only need to patch once - rate_limiter imports RATE_LIMITS at call time
    monkeypatch.setattr(rate_limit_config, "RATE_LIMITS", test_limits)


class TestRateLimitAppliedToAllEndpoints:
    """Verify rate limiting is enforced on all authenticated endpoints."""

    async def test__bookmarks_list__rate_limited(
        self,
        client: AsyncClient,
        low_rate_limits: None,  # noqa: ARG002
    ) -> None:
        """GET /bookmarks/ is rate limited."""
        # Make 2 requests (allowed)
        for _ in range(2):
            response = await client.get("/bookmarks/")
            assert response.status_code == 200

        # 3rd request should be blocked
        response = await client.get("/bookmarks/")
        assert response.status_code == 429

    async def test__bookmarks_create__rate_limited(
        self,
        client: AsyncClient,
        low_rate_limits: None,  # noqa: ARG002
    ) -> None:
        """POST /bookmarks/ is rate limited."""
        # Make 2 requests (allowed)
        for i in range(2):
            response = await client.post(
                "/bookmarks/",
                json={"url": f"https://example.com/rate-limit-{i}", "title": f"Test {i}"},
            )
            assert response.status_code == 201

        # 3rd request should be blocked
        response = await client.post(
            "/bookmarks/",
            json={"url": "https://example.com/rate-limit-blocked", "title": "Blocked"},
        )
        assert response.status_code == 429

    async def test__bookmarks_get__rate_limited(
        self,
        client: AsyncClient,
        low_rate_limits: None,  # noqa: ARG002
    ) -> None:
        """GET /bookmarks/{id} is rate limited."""
        # Create a bookmark first (uses WRITE bucket, not READ)
        response = await client.post(
            "/bookmarks/",
            json={"url": "https://example.com/get-test", "title": "Get Test"},
        )
        assert response.status_code == 201
        bookmark_id = response.json()["id"]

        # READ operations have their own bucket - make 2 GET requests (allowed)
        for _ in range(2):
            response = await client.get(f"/bookmarks/{bookmark_id}")
            assert response.status_code == 200

        # 3rd GET request should be blocked (READ bucket exhausted)
        response = await client.get(f"/bookmarks/{bookmark_id}")
        assert response.status_code == 429

    async def test__bookmarks_update__rate_limited(
        self,
        client: AsyncClient,
        low_rate_limits: None,  # noqa: ARG002
    ) -> None:
        """PATCH /bookmarks/{id} is rate limited."""
        # Create a bookmark first
        response = await client.post(
            "/bookmarks/",
            json={"url": "https://example.com/update-test", "title": "Update Test"},
        )
        assert response.status_code == 201
        bookmark_id = response.json()["id"]

        # 1 request used, 1 remaining
        response = await client.patch(
            f"/bookmarks/{bookmark_id}",
            json={"title": "Updated 1"},
        )
        assert response.status_code == 200

        # 3rd total request should be blocked
        response = await client.patch(
            f"/bookmarks/{bookmark_id}",
            json={"title": "Blocked Update"},
        )
        assert response.status_code == 429

    async def test__bookmarks_delete__rate_limited(
        self,
        client: AsyncClient,
        low_rate_limits: None,  # noqa: ARG002
    ) -> None:
        """DELETE /bookmarks/{id} is rate limited."""
        # Create 2 bookmarks first
        bookmarks = []
        for i in range(2):
            response = await client.post(
                "/bookmarks/",
                json={"url": f"https://example.com/delete-{i}", "title": f"Delete {i}"},
            )
            # These will exhaust rate limit
            if response.status_code == 201:
                bookmarks.append(response.json()["id"])

        # We should have used up the rate limit
        # Next request should be blocked
        if len(bookmarks) >= 1:
            response = await client.delete(f"/bookmarks/{bookmarks[0]}")
            assert response.status_code == 429

    async def test__tags_list__rate_limited(
        self,
        client: AsyncClient,
        low_rate_limits: None,  # noqa: ARG002
    ) -> None:
        """GET /tags/ is rate limited."""
        # Make 2 requests (allowed)
        for _ in range(2):
            response = await client.get("/tags/")
            assert response.status_code == 200

        # 3rd request should be blocked
        response = await client.get("/tags/")
        assert response.status_code == 429

    async def test__lists_list__rate_limited(
        self,
        client: AsyncClient,
        low_rate_limits: None,  # noqa: ARG002
    ) -> None:
        """GET /lists/ is rate limited."""
        # Make 2 requests (allowed)
        for _ in range(2):
            response = await client.get("/lists/")
            assert response.status_code == 200

        # 3rd request should be blocked
        response = await client.get("/lists/")
        assert response.status_code == 429

    async def test__lists_create__rate_limited(
        self,
        client: AsyncClient,
        low_rate_limits: None,  # noqa: ARG002
    ) -> None:
        """POST /lists/ is rate limited."""
        import uuid
        # Make 2 requests (allowed) - use unique names and valid filter_expression
        filter_expr = {"groups": [{"tags": ["test"]}], "group_operator": "OR"}
        for i in range(2):
            response = await client.post(
                "/lists/",
                json={
                    "name": f"List {uuid.uuid4().hex[:8]}-{i}",
                    "filter_expression": filter_expr,
                },
            )
            assert response.status_code == 201

        # 3rd request should be blocked
        response = await client.post(
            "/lists/",
            json={
                "name": f"Blocked List {uuid.uuid4().hex[:8]}",
                "filter_expression": filter_expr,
            },
        )
        assert response.status_code == 429

    async def test__users_me__rate_limited(
        self,
        client: AsyncClient,
        low_rate_limits: None,  # noqa: ARG002
    ) -> None:
        """GET /users/me is rate limited."""
        # Make 2 requests (allowed)
        for _ in range(2):
            response = await client.get("/users/me")
            assert response.status_code == 200

        # 3rd request should be blocked
        response = await client.get("/users/me")
        assert response.status_code == 429

    async def test__consent_status__rate_limited(
        self,
        client: AsyncClient,
        low_rate_limits: None,  # noqa: ARG002
    ) -> None:
        """GET /consent/status is rate limited."""
        # Make 2 requests (allowed)
        for _ in range(2):
            response = await client.get("/consent/status")
            assert response.status_code == 200

        # 3rd request should be blocked
        response = await client.get("/consent/status")
        assert response.status_code == 429


class TestRateLimitHeadersOnAllEndpoints:
    """Verify rate limit headers are included on all authenticated endpoint responses."""

    async def test__bookmarks_list__includes_rate_limit_headers(
        self,
        client: AsyncClient,
    ) -> None:
        """GET /bookmarks/ includes rate limit headers."""
        response = await client.get("/bookmarks/")
        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers

    async def test__bookmarks_create__includes_rate_limit_headers(
        self,
        client: AsyncClient,
    ) -> None:
        """POST /bookmarks/ includes rate limit headers."""
        response = await client.post(
            "/bookmarks/",
            json={"url": "https://example.com/header-test", "title": "Header Test"},
        )
        assert response.status_code == 201
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers

    async def test__tags_list__includes_rate_limit_headers(
        self,
        client: AsyncClient,
    ) -> None:
        """GET /tags/ includes rate limit headers."""
        response = await client.get("/tags/")
        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers

    async def test__users_me__includes_rate_limit_headers(
        self,
        client: AsyncClient,
    ) -> None:
        """GET /users/me includes rate limit headers."""
        response = await client.get("/users/me")
        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers
