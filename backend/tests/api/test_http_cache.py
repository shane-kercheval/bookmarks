"""Tests for HTTP caching (ETag middleware and Last-Modified)."""
import asyncio
from datetime import datetime, UTC
from unittest.mock import MagicMock

from httpx import AsyncClient

from core.http_cache import (
    _etag_matches,
    _parse_if_none_match,
    check_not_modified,
    format_http_date,
    generate_etag,
    parse_http_date,
)


class TestGenerateEtag:
    """Tests for ETag generation function."""

    def test__generate_etag__same_content_same_etag(self) -> None:
        """Same content should produce identical ETags."""
        content = b'{"id": "123", "name": "test"}'
        etag1 = generate_etag(content)
        etag2 = generate_etag(content)
        assert etag1 == etag2

    def test__generate_etag__different_content_different_etag(self) -> None:
        """Different content should produce different ETags."""
        content1 = b'{"id": "123", "name": "test"}'
        content2 = b'{"id": "456", "name": "other"}'
        etag1 = generate_etag(content1)
        etag2 = generate_etag(content2)
        assert etag1 != etag2

    def test__generate_etag__weak_etag_format(self) -> None:
        """ETag should be weak (W/ prefix) and quoted."""
        content = b'{"data": "test"}'
        etag = generate_etag(content)
        assert etag.startswith('W/"')
        assert etag.endswith('"')
        # Should be 16 hex chars between quotes
        inner = etag[3:-1]  # Remove W/" and "
        assert len(inner) == 16
        assert all(c in "0123456789abcdef" for c in inner)

    def test__generate_etag__empty_content(self) -> None:
        """Empty content should still produce valid ETag."""
        etag = generate_etag(b"")
        assert etag.startswith('W/"')
        assert etag.endswith('"')


class TestParseIfNoneMatch:
    """Tests for If-None-Match header parsing."""

    def test__parse_if_none_match__single_etag(self) -> None:
        """Single ETag should be parsed correctly."""
        result = _parse_if_none_match('W/"abc123"')
        assert result == ['W/"abc123"']

    def test__parse_if_none_match__comma_separated(self) -> None:
        """Comma-separated ETags should be parsed into list."""
        result = _parse_if_none_match('W/"abc", W/"def", W/"ghi"')
        assert result == ['W/"abc"', 'W/"def"', 'W/"ghi"']

    def test__parse_if_none_match__wildcard(self) -> None:
        """Wildcard should be parsed correctly."""
        result = _parse_if_none_match("*")
        assert result == ["*"]

    def test__parse_if_none_match__empty_string(self) -> None:
        """Empty string should return empty list."""
        result = _parse_if_none_match("")
        assert result == []

    def test__parse_if_none_match__whitespace_handling(self) -> None:
        """Whitespace should be stripped from ETags."""
        result = _parse_if_none_match('  W/"abc"  ,  W/"def"  ')
        assert result == ['W/"abc"', 'W/"def"']


class TestEtagMatches:
    """Tests for ETag matching logic."""

    def test__etag_matches__exact_match(self) -> None:
        """Exact ETag match should return True."""
        assert _etag_matches('W/"abc"', ['W/"abc"']) is True

    def test__etag_matches__no_match(self) -> None:
        """Non-matching ETag should return False."""
        assert _etag_matches('W/"abc"', ['W/"def"']) is False

    def test__etag_matches__wildcard_matches_any(self) -> None:
        """Wildcard should match any ETag."""
        assert _etag_matches('W/"abc"', ["*"]) is True
        assert _etag_matches('W/"anything"', ["*"]) is True

    def test__etag_matches__match_in_list(self) -> None:
        """ETag in list should match."""
        assert _etag_matches('W/"def"', ['W/"abc"', 'W/"def"', 'W/"ghi"']) is True

    def test__etag_matches__no_match_in_list(self) -> None:
        """ETag not in list should not match."""
        assert _etag_matches('W/"xyz"', ['W/"abc"', 'W/"def"']) is False


class TestETagMiddleware:
    """Tests for ETag middleware behavior."""

    async def test__etag_middleware__get_request_receives_etag(
        self, client: AsyncClient,
    ) -> None:
        """GET request should receive ETag header in response."""
        response = await client.get("/health")
        assert response.status_code == 200
        assert "etag" in response.headers
        assert response.headers["etag"].startswith('W/"')

    async def test__etag_middleware__matching_if_none_match_returns_304(
        self, client: AsyncClient,
    ) -> None:
        """GET with matching If-None-Match should return 304."""
        # First request to get ETag
        response1 = await client.get("/health")
        assert response1.status_code == 200
        etag = response1.headers["etag"]

        # Second request with If-None-Match
        response2 = await client.get("/health", headers={"If-None-Match": etag})
        assert response2.status_code == 304
        assert response2.content == b""  # No body on 304

    async def test__etag_middleware__non_matching_if_none_match_returns_200(
        self, client: AsyncClient,
    ) -> None:
        """GET with non-matching If-None-Match should return 200 with new ETag."""
        response = await client.get(
            "/health",
            headers={"If-None-Match": 'W/"nonexistent1234"'},
        )
        assert response.status_code == 200
        assert "etag" in response.headers

    async def test__etag_middleware__post_request_no_etag(
        self, client: AsyncClient,
    ) -> None:
        """POST request should not receive ETag header."""
        response = await client.post(
            "/bookmarks/",
            json={"url": "https://example.com", "title": "Test"},
        )
        assert response.status_code == 201
        assert "etag" not in response.headers

    async def test__etag_middleware__error_response_no_etag(
        self, client: AsyncClient,
    ) -> None:
        """Error responses should not receive ETag header."""
        response = await client.get("/bookmarks/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404
        assert "etag" not in response.headers

    async def test__etag_middleware__wildcard_if_none_match_returns_304(
        self, client: AsyncClient,
    ) -> None:
        """GET with wildcard If-None-Match should return 304."""
        response = await client.get("/health", headers={"If-None-Match": "*"})
        assert response.status_code == 304

    async def test__etag_middleware__comma_separated_if_none_match_returns_304(
        self, client: AsyncClient,
    ) -> None:
        """GET with comma-separated If-None-Match containing matching ETag should return 304."""
        # First request to get ETag
        response1 = await client.get("/health")
        etag = response1.headers["etag"]

        # Second request with comma-separated list containing the ETag
        response2 = await client.get(
            "/health",
            headers={"If-None-Match": f'W/"other1", {etag}, W/"other2"'},
        )
        assert response2.status_code == 304


class TestCachingHeaders:
    """Tests for Cache-Control and Vary headers."""

    async def test__caching_headers__present_on_200_response(
        self, client: AsyncClient,
    ) -> None:
        """200 response should include Cache-Control and Vary headers."""
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.headers.get("cache-control") == "private, no-cache"
        assert response.headers.get("vary") == "Authorization"

    async def test__caching_headers__present_on_304_response(
        self, client: AsyncClient,
    ) -> None:
        """304 response should include Cache-Control and Vary headers."""
        # Get ETag first
        response1 = await client.get("/health")
        etag = response1.headers["etag"]

        # Request with matching ETag
        response2 = await client.get("/health", headers={"If-None-Match": etag})
        assert response2.status_code == 304
        assert response2.headers.get("cache-control") == "private, no-cache"
        assert response2.headers.get("vary") == "Authorization"

    async def test__caching_headers__etag_present_on_304(
        self, client: AsyncClient,
    ) -> None:
        """304 response should include ETag header."""
        response1 = await client.get("/health")
        etag = response1.headers["etag"]

        response2 = await client.get("/health", headers={"If-None-Match": etag})
        assert response2.status_code == 304
        assert response2.headers.get("etag") == etag

    async def test__caching_headers__no_cache_directive_forbids_heuristic_freshness(
        self, client: AsyncClient,
    ) -> None:
        """
        Regression: Cache-Control MUST include `no-cache` (not just `must-revalidate`).

        Per RFC 7234 §4.2.2, a response with `Last-Modified` but no explicit freshness
        is eligible for heuristic freshness — caches (notably Safari) may infer a
        lifetime of ~10% of (now - Last-Modified) and serve the entry WITHOUT contacting
        the origin during that window. `must-revalidate` alone does NOT prevent this;
        it only governs behavior after the entry is deemed stale.

        Symptom of regressing this: out-of-band edits (e.g., via MCP) are silently
        invisible on navigate-back in Safari. Recovery requires logout/login (which
        rotates the session JWT and changes the Vary cache key).

        See `backend/src/core/http_cache.py` `CACHE_HEADERS` comment for full context.
        """
        response = await client.get("/health")
        cache_control = response.headers.get("cache-control", "")
        directives = {d.strip().lower() for d in cache_control.split(",")}
        assert "no-cache" in directives, (
            f"Cache-Control must include 'no-cache' to prevent Safari heuristic "
            f"freshness; got: {cache_control!r}"
        )
        # Also assert we did NOT regress to a permissive freshness directive.
        forbidden_prefixes = ("max-age=", "s-maxage=", "stale-while-revalidate=")
        for directive in directives:
            assert not directive.startswith(forbidden_prefixes), (
                f"Cache-Control must not include {forbidden_prefixes} on "
                f"per-user API responses; got: {cache_control!r}"
            )


class TestSecurityHeadersOn304:
    """Tests to verify security headers are present on 304 responses."""

    async def test__security_headers__present_on_304_response(
        self, client: AsyncClient,
    ) -> None:
        """304 response should include security headers from SecurityHeadersMiddleware."""
        # Get ETag first
        response1 = await client.get("/health")
        etag = response1.headers["etag"]

        # Request with matching ETag
        response2 = await client.get("/health", headers={"If-None-Match": etag})
        assert response2.status_code == 304

        # Verify security headers are present
        assert "strict-transport-security" in response2.headers
        assert response2.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"
        assert response2.headers.get("x-content-type-options") == "nosniff"
        assert response2.headers.get("x-frame-options") == "DENY"


class TestETagIntegration:
    """Integration tests for ETag with real endpoints."""

    async def test__etag_integration__bookmark_crud_etag_changes(
        self, client: AsyncClient,
    ) -> None:
        """ETag should change when bookmark is updated."""
        # Create bookmark
        create_response = await client.post(
            "/bookmarks/",
            json={"url": "https://etag-test.com", "title": "Initial Title"},
        )
        assert create_response.status_code == 201
        bookmark_id = create_response.json()["id"]

        # GET bookmark, note ETag
        get_response1 = await client.get(f"/bookmarks/{bookmark_id}")
        assert get_response1.status_code == 200
        etag1 = get_response1.headers["etag"]

        # GET again with If-None-Match - should be 304
        get_response2 = await client.get(
            f"/bookmarks/{bookmark_id}",
            headers={"If-None-Match": etag1},
        )
        assert get_response2.status_code == 304

        # Update bookmark
        update_response = await client.patch(
            f"/bookmarks/{bookmark_id}",
            json={"title": "Updated Title"},
        )
        assert update_response.status_code == 200

        # GET with old ETag - should be 200 with new ETag
        get_response3 = await client.get(
            f"/bookmarks/{bookmark_id}",
            headers={"If-None-Match": etag1},
        )
        assert get_response3.status_code == 200
        etag2 = get_response3.headers["etag"]
        assert etag2 != etag1  # ETag changed

        # New ETag should work for 304
        get_response4 = await client.get(
            f"/bookmarks/{bookmark_id}",
            headers={"If-None-Match": etag2},
        )
        assert get_response4.status_code == 304

    async def test__etag_integration__list_endpoint(
        self, client: AsyncClient,
    ) -> None:
        """List endpoints should also receive ETags."""
        # Create some bookmarks
        await client.post("/bookmarks/", json={"url": "https://list1.com"})
        await client.post("/bookmarks/", json={"url": "https://list2.com"})

        # GET list
        response1 = await client.get("/bookmarks/")
        assert response1.status_code == 200
        assert "etag" in response1.headers
        etag = response1.headers["etag"]

        # GET list with If-None-Match - should be 304 (no changes)
        response2 = await client.get("/bookmarks/", headers={"If-None-Match": etag})
        assert response2.status_code == 304

    async def test__etag_integration__rate_limit_headers_preserved(
        self, rate_limit_client: AsyncClient,
    ) -> None:
        """Rate limit headers should be preserved alongside ETag headers."""
        # Use an authenticated endpoint that has rate limiting
        response = await rate_limit_client.get("/bookmarks/")
        assert response.status_code == 200

        # Both ETag and rate limit headers should be present
        assert "etag" in response.headers
        assert "x-ratelimit-limit" in response.headers
        assert "x-ratelimit-remaining" in response.headers
        assert "x-ratelimit-reset" in response.headers


class TestHttpDateFormatting:
    """Tests for HTTP date formatting and parsing."""

    def test__format_http_date__produces_valid_format(self) -> None:
        """format_http_date should produce RFC 7231 format."""
        dt = datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC)
        result = format_http_date(dt)
        # Should be in format: "Wed, 15 Jan 2026 10:30:00 GMT"
        assert "15 Jan 2026" in result
        assert "10:30:00" in result
        assert result.endswith("GMT")

    def test__parse_http_date__valid_date(self) -> None:
        """parse_http_date should parse valid HTTP date strings."""
        date_str = "Wed, 15 Jan 2026 10:30:00 GMT"
        result = parse_http_date(date_str)
        assert result is not None
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30

    def test__parse_http_date__invalid_date_returns_none(self) -> None:
        """parse_http_date should return None for invalid dates."""
        assert parse_http_date("not a date") is None
        assert parse_http_date("") is None

    def test__format_http_date__handles_naive_datetime(self) -> None:
        """format_http_date should handle naive datetimes (assumed UTC)."""
        # Naive datetime (no tzinfo)
        naive_dt = datetime(2026, 1, 15, 10, 30, 0)
        # Equivalent aware datetime
        aware_dt = datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC)

        naive_result = format_http_date(naive_dt)
        aware_result = format_http_date(aware_dt)

        # Both should produce the same output
        assert naive_result == aware_result

    def test__format_parse_roundtrip(self) -> None:
        """Formatting then parsing should return equivalent datetime."""
        original = datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC)
        formatted = format_http_date(original)
        parsed = parse_http_date(formatted)
        assert parsed is not None
        # Compare with second precision (HTTP dates don't have microseconds)
        assert parsed.replace(microsecond=0) == original.replace(microsecond=0)


class TestCheckNotModified:
    """Tests for check_not_modified helper function."""

    def test__check_not_modified__no_header_returns_none(self) -> None:
        """Returns None when If-Modified-Since header is absent."""
        request = MagicMock()
        request.headers = {}
        updated_at = datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC)

        result = check_not_modified(request, updated_at)
        assert result is None

    def test__check_not_modified__if_none_match_present_returns_none(self) -> None:
        """Returns None when If-None-Match is present (ETag takes precedence)."""
        request = MagicMock()
        request.headers = {
            "if-none-match": 'W/"abc123"',
            "if-modified-since": "Wed, 15 Jan 2026 10:30:00 GMT",
        }
        updated_at = datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC)

        result = check_not_modified(request, updated_at)
        assert result is None

    def test__check_not_modified__resource_not_modified_returns_304(self) -> None:
        """Returns 304 response when resource hasn't been modified."""
        request = MagicMock()
        request.headers = {"if-modified-since": "Wed, 15 Jan 2026 10:30:00 GMT"}
        # Same time as client's cached version
        updated_at = datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC)

        result = check_not_modified(request, updated_at)
        assert result is not None
        assert result.status_code == 304

    def test__check_not_modified__resource_modified_returns_none(self) -> None:
        """Returns None when resource has been modified since client's version."""
        request = MagicMock()
        request.headers = {"if-modified-since": "Wed, 15 Jan 2026 10:30:00 GMT"}
        # Resource updated after client's cached version
        updated_at = datetime(2026, 1, 15, 10, 31, 0, tzinfo=UTC)

        result = check_not_modified(request, updated_at)
        assert result is None

    def test__check_not_modified__304_includes_caching_headers(self) -> None:
        """304 response should include Cache-Control and Vary headers."""
        request = MagicMock()
        request.headers = {"if-modified-since": "Wed, 15 Jan 2026 10:30:00 GMT"}
        updated_at = datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC)

        result = check_not_modified(request, updated_at)
        assert result is not None
        assert result.headers.get("cache-control") == "private, no-cache"
        assert result.headers.get("vary") == "Authorization"
        assert "last-modified" in result.headers

    def test__check_not_modified__invalid_date_returns_none(self) -> None:
        """Returns None when If-Modified-Since header is malformed."""
        request = MagicMock()
        request.headers = {"if-modified-since": "not a valid date"}
        updated_at = datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC)

        result = check_not_modified(request, updated_at)
        assert result is None

    def test__check_not_modified__naive_updated_at_treated_as_utc(self) -> None:
        """Naive updated_at should be treated as UTC."""
        request = MagicMock()
        # Client has cached version from 10:30:00 UTC
        request.headers = {"if-modified-since": "Wed, 15 Jan 2026 10:30:00 GMT"}

        # Naive datetime (no tzinfo) - same time, should be treated as UTC
        naive_updated_at = datetime(2026, 1, 15, 10, 30, 0)

        result = check_not_modified(request, naive_updated_at)
        # Should return 304 since times match (naive treated as UTC)
        assert result is not None
        assert result.status_code == 304


class TestLastModifiedIntegration:
    """Integration tests for Last-Modified with real endpoints."""

    async def test__last_modified__bookmark_returns_header(
        self, client: AsyncClient,
    ) -> None:
        """GET /bookmarks/{id} should include Last-Modified header."""
        # Create bookmark
        create_response = await client.post(
            "/bookmarks/",
            json={"url": "https://lastmod-test.com", "title": "Test"},
        )
        assert create_response.status_code == 201
        bookmark_id = create_response.json()["id"]

        # GET bookmark should include Last-Modified
        response = await client.get(f"/bookmarks/{bookmark_id}")
        assert response.status_code == 200
        assert "last-modified" in response.headers

    async def test__last_modified__if_modified_since_returns_304(
        self, client: AsyncClient,
    ) -> None:
        """GET with If-Modified-Since should return 304 if unchanged."""
        # Create bookmark
        create_response = await client.post(
            "/bookmarks/",
            json={"url": "https://lastmod-304.com", "title": "Test"},
        )
        bookmark_id = create_response.json()["id"]

        # GET to get Last-Modified
        response1 = await client.get(f"/bookmarks/{bookmark_id}")
        last_modified = response1.headers["last-modified"]

        # GET with If-Modified-Since (and no If-None-Match) should return 304
        response2 = await client.get(
            f"/bookmarks/{bookmark_id}",
            headers={"If-Modified-Since": last_modified},
        )
        assert response2.status_code == 304

    async def test__last_modified__etag_takes_precedence(
        self, client: AsyncClient,
    ) -> None:
        """If-None-Match should take precedence over If-Modified-Since."""
        # Create bookmark
        create_response = await client.post(
            "/bookmarks/",
            json={"url": "https://precedence-test.com", "title": "Test"},
        )
        bookmark_id = create_response.json()["id"]

        # GET to get headers
        response1 = await client.get(f"/bookmarks/{bookmark_id}")
        etag = response1.headers["etag"]
        last_modified = response1.headers["last-modified"]

        # With both headers, ETag (If-None-Match) should be used
        response2 = await client.get(
            f"/bookmarks/{bookmark_id}",
            headers={
                "If-None-Match": etag,
                "If-Modified-Since": last_modified,
            },
        )
        # Should be 304 from ETag match (via middleware)
        assert response2.status_code == 304
        # Should have ETag in response (from middleware)
        assert "etag" in response2.headers

    async def test__last_modified__note_returns_header(
        self, client: AsyncClient,
    ) -> None:
        """GET /notes/{id} should include Last-Modified header."""
        # Create note
        create_response = await client.post(
            "/notes/",
            json={"title": "Test Note", "content": "Content"},
        )
        assert create_response.status_code == 201
        note_id = create_response.json()["id"]

        # GET note should include Last-Modified
        response = await client.get(f"/notes/{note_id}")
        assert response.status_code == 200
        assert "last-modified" in response.headers

    async def test__last_modified__prompt_by_id_returns_header(
        self, client: AsyncClient,
    ) -> None:
        """GET /prompts/{id} should include Last-Modified header."""
        # Create prompt
        create_response = await client.post(
            "/prompts/",
            json={
                "name": "test-prompt",
                "content": "Hello {{ name }}",
                "arguments": [{"name": "name", "required": True}],
            },
        )
        assert create_response.status_code == 201
        prompt_id = create_response.json()["id"]

        # GET prompt by ID should include Last-Modified
        response = await client.get(f"/prompts/{prompt_id}")
        assert response.status_code == 200
        assert "last-modified" in response.headers

    async def test__last_modified__prompt_by_name_returns_header(
        self, client: AsyncClient,
    ) -> None:
        """GET /prompts/name/{name} should include Last-Modified header."""
        # Create prompt
        await client.post(
            "/prompts/",
            json={
                "name": "named-prompt",
                "content": "Hello {{ name }}",
                "arguments": [{"name": "name", "required": True}],
            },
        )

        # GET prompt by name should include Last-Modified
        response = await client.get("/prompts/name/named-prompt")
        assert response.status_code == 200
        assert "last-modified" in response.headers

    async def test__last_modified__304_has_security_headers(
        self, client: AsyncClient,
    ) -> None:
        """304 from Last-Modified should include security headers."""
        # Create bookmark
        create_response = await client.post(
            "/bookmarks/",
            json={"url": "https://security-304.com", "title": "Test"},
        )
        bookmark_id = create_response.json()["id"]

        # GET to get Last-Modified
        response1 = await client.get(f"/bookmarks/{bookmark_id}")
        last_modified = response1.headers["last-modified"]

        # GET with If-Modified-Since
        response2 = await client.get(
            f"/bookmarks/{bookmark_id}",
            headers={"If-Modified-Since": last_modified},
        )
        assert response2.status_code == 304

        # Security headers should be present
        assert "strict-transport-security" in response2.headers
        assert response2.headers.get("x-content-type-options") == "nosniff"
        assert response2.headers.get("x-frame-options") == "DENY"

    async def test__last_modified__404_for_nonexistent(
        self, client: AsyncClient,
    ) -> None:
        """Non-existent resource should return 404, not 304."""
        response = await client.get(
            "/bookmarks/00000000-0000-0000-0000-000000000000",
            headers={"If-Modified-Since": "Wed, 15 Jan 2026 10:30:00 GMT"},
        )
        assert response.status_code == 404

    async def test__last_modified__changes_after_update(
        self, client: AsyncClient,
    ) -> None:
        """Last-Modified should change after resource update, invalidating cache."""
        # Create bookmark
        create_response = await client.post(
            "/bookmarks/",
            json={"url": "https://lastmod-update-test.com", "title": "Original"},
        )
        bookmark_id = create_response.json()["id"]

        # GET to get initial Last-Modified
        response1 = await client.get(f"/bookmarks/{bookmark_id}")
        last_modified_1 = response1.headers["last-modified"]

        # Verify 304 works with current Last-Modified
        response2 = await client.get(
            f"/bookmarks/{bookmark_id}",
            headers={"If-Modified-Since": last_modified_1},
        )
        assert response2.status_code == 304

        # Wait to ensure update happens in a different second (HTTP dates have second precision)
        await asyncio.sleep(1.1)

        # Update the bookmark
        await client.patch(
            f"/bookmarks/{bookmark_id}",
            json={"title": "Updated Title"},
        )

        # Request with OLD Last-Modified should return 200 (cache invalidated)
        response3 = await client.get(
            f"/bookmarks/{bookmark_id}",
            headers={"If-Modified-Since": last_modified_1},
        )
        assert response3.status_code == 200

        # New Last-Modified should be different
        last_modified_2 = response3.headers["last-modified"]
        assert last_modified_2 != last_modified_1

        # New Last-Modified should work for 304
        response4 = await client.get(
            f"/bookmarks/{bookmark_id}",
            headers={"If-Modified-Since": last_modified_2},
        )
        assert response4.status_code == 304

    async def test__last_modified__soft_deleted_resource_supports_caching(
        self, client: AsyncClient,
    ) -> None:
        """Soft-deleted resources should still support Last-Modified caching."""
        # Create bookmark
        create_response = await client.post(
            "/bookmarks/",
            json={"url": "https://soft-delete-cache.com", "title": "To Delete"},
        )
        bookmark_id = create_response.json()["id"]

        # GET to get Last-Modified
        response1 = await client.get(f"/bookmarks/{bookmark_id}")
        assert response1.status_code == 200
        response1.headers["last-modified"]

        # Soft delete the bookmark
        delete_response = await client.delete(f"/bookmarks/{bookmark_id}")
        assert delete_response.status_code == 204

        # GET deleted bookmark should still work (endpoint includes deleted)
        response2 = await client.get(f"/bookmarks/{bookmark_id}")
        assert response2.status_code == 200
        assert "last-modified" in response2.headers

        # If-Modified-Since should work on deleted resource
        # Note: delete updates the timestamp, so we need the new Last-Modified
        new_last_modified = response2.headers["last-modified"]
        response3 = await client.get(
            f"/bookmarks/{bookmark_id}",
            headers={"If-Modified-Since": new_last_modified},
        )
        assert response3.status_code == 304
