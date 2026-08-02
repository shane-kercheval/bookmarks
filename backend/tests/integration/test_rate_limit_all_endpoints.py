"""
Tests verifying rate limiting is applied to all authenticated endpoints.

These tests use a low rate limit (2 requests per minute) to verify that
rate limiting is properly integrated into each endpoint via the auth dependencies.
"""
import uuid

import pytest
from httpx import AsyncClient

from core import tier_limits
from core.tier_limits import Tier, TierLimits


@pytest.fixture
def low_rate_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch tier limits to have very low rate limits for testing."""
    test_limits = TierLimits(
        max_bookmarks=100,
        max_notes=100,
        max_prompts=100,
        max_pats=100,
        max_title_length=200,
        max_description_length=1000,
        max_tag_name_length=50,
        max_bookmark_content_length=100_000,
        max_note_content_length=100_000,
        max_prompt_content_length=100_000,
        max_url_length=2048,
        max_prompt_name_length=100,
        max_argument_name_length=100,
        max_argument_description_length=500,
        rate_read_per_minute=2,
        rate_read_per_day=100,
        rate_write_per_minute=2,
        rate_write_per_day=100,
        rate_sensitive_per_minute=2,
        rate_sensitive_per_day=100,
        rate_ai_per_minute=2,
        rate_ai_per_day=100,
        rate_ai_byok_per_minute=2,
        rate_ai_byok_per_day=100,
        max_relationships_per_entity=50,
        history_retention_days=30,
        max_history_per_entity=100,
    )
    monkeypatch.setattr(tier_limits, "TIER_LIMITS", {
        Tier.FREE: test_limits,
        Tier.STANDARD: test_limits,
        Tier.PRO: test_limits,
        Tier.DEV: test_limits,
    })


class TestRateLimitAppliedToAllEndpoints:
    """Verify rate limiting is enforced on all authenticated endpoints."""

    async def test__bookmarks_list__rate_limited(
        self,
        rate_limit_client: AsyncClient,
        low_rate_limits: None,  # noqa: ARG002
    ) -> None:
        """GET /bookmarks/ is rate limited."""
        # Make 2 requests (allowed)
        for _ in range(2):
            response = await rate_limit_client.get("/bookmarks/")
            assert response.status_code == 200

        # 3rd request should be blocked
        response = await rate_limit_client.get("/bookmarks/")
        assert response.status_code == 429

    async def test__bookmarks_create__rate_limited(
        self,
        rate_limit_client: AsyncClient,
        low_rate_limits: None,  # noqa: ARG002
    ) -> None:
        """POST /bookmarks/ is rate limited."""
        # Make 2 requests (allowed)
        for i in range(2):
            response = await rate_limit_client.post(
                "/bookmarks/",
                json={"url": f"https://example.com/rate-limit-{i}", "title": f"Test {i}"},
            )
            assert response.status_code == 201

        # 3rd request should be blocked
        response = await rate_limit_client.post(
            "/bookmarks/",
            json={"url": "https://example.com/rate-limit-blocked", "title": "Blocked"},
        )
        assert response.status_code == 429

    async def test__bookmarks_get__rate_limited(
        self,
        rate_limit_client: AsyncClient,
        low_rate_limits: None,  # noqa: ARG002
    ) -> None:
        """GET /bookmarks/{id} is rate limited."""
        # Create a bookmark first (uses WRITE bucket, not READ)
        response = await rate_limit_client.post(
            "/bookmarks/",
            json={"url": "https://example.com/get-test", "title": "Get Test"},
        )
        assert response.status_code == 201
        bookmark_id = response.json()["id"]

        # READ operations have their own bucket - make 2 GET requests (allowed)
        for _ in range(2):
            response = await rate_limit_client.get(f"/bookmarks/{bookmark_id}")
            assert response.status_code == 200

        # 3rd GET request should be blocked (READ bucket exhausted)
        response = await rate_limit_client.get(f"/bookmarks/{bookmark_id}")
        assert response.status_code == 429

    async def test__bookmarks_update__rate_limited(
        self,
        rate_limit_client: AsyncClient,
        low_rate_limits: None,  # noqa: ARG002
    ) -> None:
        """PATCH /bookmarks/{id} is rate limited."""
        # Create a bookmark first
        response = await rate_limit_client.post(
            "/bookmarks/",
            json={"url": "https://example.com/update-test", "title": "Update Test"},
        )
        assert response.status_code == 201
        bookmark_id = response.json()["id"]

        # 1 request used, 1 remaining
        response = await rate_limit_client.patch(
            f"/bookmarks/{bookmark_id}",
            json={"title": "Updated 1"},
        )
        assert response.status_code == 200

        # 3rd total request should be blocked
        response = await rate_limit_client.patch(
            f"/bookmarks/{bookmark_id}",
            json={"title": "Blocked Update"},
        )
        assert response.status_code == 429

    async def test__bookmarks_delete__rate_limited(
        self,
        rate_limit_client: AsyncClient,
        low_rate_limits: None,  # noqa: ARG002
    ) -> None:
        """DELETE /bookmarks/{id} is rate limited."""
        # Create 2 bookmarks first
        bookmarks = []
        for i in range(2):
            response = await rate_limit_client.post(
                "/bookmarks/",
                json={"url": f"https://example.com/delete-{i}", "title": f"Delete {i}"},
            )
            # These will exhaust rate limit
            if response.status_code == 201:
                bookmarks.append(response.json()["id"])

        # We should have used up the rate limit
        # Next request should be blocked
        if len(bookmarks) >= 1:
            response = await rate_limit_client.delete(f"/bookmarks/{bookmarks[0]}")
            assert response.status_code == 429

    async def test__tags_list__rate_limited(
        self,
        rate_limit_client: AsyncClient,
        low_rate_limits: None,  # noqa: ARG002
    ) -> None:
        """GET /tags/ is rate limited."""
        # Make 2 requests (allowed)
        for _ in range(2):
            response = await rate_limit_client.get("/tags/")
            assert response.status_code == 200

        # 3rd request should be blocked
        response = await rate_limit_client.get("/tags/")
        assert response.status_code == 429

    async def test__lists_list__rate_limited(
        self,
        rate_limit_client: AsyncClient,
        low_rate_limits: None,  # noqa: ARG002
    ) -> None:
        """GET /filters/ is rate limited."""
        # Make 2 requests (allowed)
        for _ in range(2):
            response = await rate_limit_client.get("/filters/")
            assert response.status_code == 200

        # 3rd request should be blocked
        response = await rate_limit_client.get("/filters/")
        assert response.status_code == 429

    async def test__lists_create__rate_limited(
        self,
        rate_limit_client: AsyncClient,
        low_rate_limits: None,  # noqa: ARG002
    ) -> None:
        """POST /filters/ is rate limited."""
        # Make 2 requests (allowed) - use unique names and valid filter_expression
        filter_expr = {"groups": [{"tags": ["test"]}], "group_operator": "OR"}
        for i in range(2):
            response = await rate_limit_client.post(
                "/filters/",
                json={
                    "name": f"List {uuid.uuid4().hex[:8]}-{i}",
                    "filter_expression": filter_expr,
                },
            )
            assert response.status_code == 201

        # 3rd request should be blocked
        response = await rate_limit_client.post(
            "/filters/",
            json={
                "name": f"Blocked List {uuid.uuid4().hex[:8]}",
                "filter_expression": filter_expr,
            },
        )
        assert response.status_code == 429

    async def test__users_me__rate_limited(
        self,
        rate_limit_client: AsyncClient,
        low_rate_limits: None,  # noqa: ARG002
    ) -> None:
        """GET /users/me is rate limited."""
        # Make 2 requests (allowed)
        for _ in range(2):
            response = await rate_limit_client.get("/users/me")
            assert response.status_code == 200

        # 3rd request should be blocked
        response = await rate_limit_client.get("/users/me")
        assert response.status_code == 429

    async def test__tokens_create__rate_limited(
        self,
        rate_limit_client: AsyncClient,
        low_rate_limits: None,  # noqa: ARG002
    ) -> None:
        """
        POST /tokens/ is rate limited and consumes only 1 slot per request.

        This also serves as a regression test: prior to the
        get_current_limits_session_only dependency, the token creation
        endpoint ran both get_current_user_session_only and get_current_user
        (via get_current_limits), consuming 2 rate limit slots per request.
        With the fix, both dependencies share get_current_user_session_only,
        so only 1 slot is consumed.
        """
        # Make 2 requests (allowed — write limit is 2/min)
        for i in range(2):
            response = await rate_limit_client.post(
                "/tokens/",
                json={"name": f"Rate Limit Token {i}"},
            )
            assert response.status_code == 201, (
                f"Request {i + 1} failed with {response.status_code} "
                f"(double rate-limit bug may still be present)"
            )

        # 3rd request should be blocked
        response = await rate_limit_client.post(
            "/tokens/",
            json={"name": "Blocked Token"},
        )
        assert response.status_code == 429


class TestRateLimitHeadersOnAllEndpoints:
    """Verify rate limit headers are included on all authenticated endpoint responses."""

    async def test__bookmarks_list__includes_rate_limit_headers(
        self,
        rate_limit_client: AsyncClient,
    ) -> None:
        """GET /bookmarks/ includes rate limit headers."""
        response = await rate_limit_client.get("/bookmarks/")
        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers

    async def test__bookmarks_create__includes_rate_limit_headers(
        self,
        rate_limit_client: AsyncClient,
    ) -> None:
        """POST /bookmarks/ includes rate limit headers."""
        response = await rate_limit_client.post(
            "/bookmarks/",
            json={"url": "https://example.com/header-test", "title": "Header Test"},
        )
        assert response.status_code == 201
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers

    async def test__tags_list__includes_rate_limit_headers(
        self,
        rate_limit_client: AsyncClient,
    ) -> None:
        """GET /tags/ includes rate limit headers."""
        response = await rate_limit_client.get("/tags/")
        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers

    async def test__users_me__includes_rate_limit_headers(
        self,
        rate_limit_client: AsyncClient,
    ) -> None:
        """GET /users/me includes rate limit headers."""
        response = await rate_limit_client.get("/users/me")
        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers
