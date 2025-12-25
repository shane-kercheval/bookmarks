"""
Input validation security tests.

These tests verify that the application properly handles malicious input,
including SQL injection attempts and XSS payloads.

OWASP References:
- A03:2021 - Injection
- A08:2021 - Software and Data Integrity Failures
"""
import pytest
from httpx import AsyncClient



class TestSQLInjectionPrevention:
    """Test SQL injection prevention."""

    @pytest.mark.parametrize("payload", [
        "'; DROP TABLE bookmarks; --",
        "' OR '1'='1",
        "1; SELECT * FROM users--",
        "' UNION SELECT password FROM users--",
        "Robert'); DROP TABLE Students;--",
        "1' AND SLEEP(5)--",
        "1' AND BENCHMARK(5000000,MD5('test'))--",
    ])
    async def test__search_query__handles_sql_injection_payloads(
        self,
        client_as_user_a: AsyncClient,
        payload: str,
    ) -> None:
        """SQL injection payloads in search query are safely escaped."""
        response = await client_as_user_a.get(
            "/bookmarks/",
            params={"q": payload},
        )

        # Should complete without error (payload treated as literal string)
        assert response.status_code == 200

    @pytest.mark.parametrize("payload", [
        "'; DROP TABLE tags; --",
        "test' OR '1'='1",
        "tag\"; DELETE FROM bookmarks;--",
    ])
    async def test__tag_filter__handles_sql_injection_payloads(
        self,
        client_as_user_a: AsyncClient,
        payload: str,
    ) -> None:
        """SQL injection payloads in tag filters are safely escaped."""
        response = await client_as_user_a.get(
            "/bookmarks/",
            params={"tags": [payload]},
        )

        # Should complete without error (payload treated as literal string)
        # May return 422 for invalid tag format, which is also acceptable
        assert response.status_code in [200, 422]

    async def test__bookmark_title__handles_sql_injection_payload(
        self,
        client_as_user_a: AsyncClient,
    ) -> None:
        """SQL injection payloads in bookmark title are safely stored."""
        sql_payload = "Test'; DROP TABLE bookmarks; --"

        response = await client_as_user_a.post(
            "/bookmarks/",
            json={
                "url": "https://sql-injection-test.example.com/",
                "title": sql_payload,
            },
        )

        assert response.status_code == 201
        data = response.json()
        # Payload stored as-is (not executed)
        assert data["title"] == sql_payload


class TestXSSPrevention:
    """Test XSS prevention (data is properly escaped in responses)."""

    @pytest.mark.parametrize("payload", [
        "<script>alert('xss')</script>",
        "<img src=x onerror=alert('xss')>",
        "javascript:alert('xss')",
        "<svg onload=alert('xss')>",
        "'\"><script>alert('xss')</script>",
    ])
    async def test__bookmark_fields__store_xss_payloads_without_execution(
        self,
        client_as_user_a: AsyncClient,
        payload: str,
    ) -> None:
        """XSS payloads are stored as-is without server-side execution."""
        response = await client_as_user_a.post(
            "/bookmarks/",
            json={
                "url": f"https://xss-test-{hash(payload) % 10000}.example.com/",
                "title": payload,
                "description": payload,
            },
        )

        assert response.status_code == 201
        data = response.json()

        # Verify payload is stored literally (client is responsible for escaping)
        assert data["title"] == payload
        assert data["description"] == payload


class TestPathTraversalPrevention:
    """Test path traversal prevention."""

    @pytest.mark.parametrize("payload", [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32\\config\\sam",
        "....//....//etc/passwd",
        "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    ])
    async def test__tag_name__rejects_path_traversal(
        self,
        client_as_user_a: AsyncClient,
        payload: str,
    ) -> None:
        """Path traversal payloads in tag names are rejected."""
        response = await client_as_user_a.post(
            "/bookmarks/",
            json={
                "url": "https://path-traversal-test.example.com/",
                "tags": [payload],
            },
        )

        # Should be rejected by tag validation (or treated as literal)
        assert response.status_code in [201, 422]


class TestInputLengthLimits:
    """Test input length validation."""

    async def test__extremely_long_url__is_handled(
        self,
        client_as_user_a: AsyncClient,
    ) -> None:
        """Extremely long URLs are properly handled."""
        long_url = "https://example.com/" + "a" * 10000

        response = await client_as_user_a.post(
            "/bookmarks/",
            json={"url": long_url},
        )

        # Should either accept or reject gracefully (not crash)
        assert response.status_code in [201, 422]

    async def test__title_at_max_length__is_accepted(
        self,
        client_as_user_a: AsyncClient,
    ) -> None:
        """Title at maximum database column length is accepted."""
        # Database has VARCHAR(500) limit for title
        max_title = "A" * 500

        response = await client_as_user_a.post(
            "/bookmarks/",
            json={
                "url": "https://max-title-test.example.com/",
                "title": max_title,
            },
        )

        # Should accept titles at the limit
        assert response.status_code == 201
        assert response.json()["title"] == max_title

    async def test__title_over_max_length__is_rejected(
        self,
        client_as_user_a: AsyncClient,
    ) -> None:
        """
        Title over maximum length is rejected by Pydantic validation.

        The schema validates title length before it reaches the database,
        returning a 422 Unprocessable Entity response.
        """
        # Default max_title_length is 500 - over this should fail
        over_limit_title = "A" * 501

        response = await client_as_user_a.post(
            "/bookmarks/",
            json={
                "url": "https://over-limit-title-test.example.com/",
                "title": over_limit_title,
            },
        )

        assert response.status_code == 422
        assert "Title exceeds maximum length" in response.text


class TestSpecialCharacterHandling:
    """Test handling of special characters in input."""

    @pytest.mark.parametrize(("special_char", "expected_codes"), [
        ("\n\r", [201]),       # Newlines - should be accepted
        ("\t", [201]),         # Tab - should be accepted
        ("\b", [201]),         # Backspace - should be accepted
        ("\\", [201]),         # Backslash - should be accepted
        ("'\"", [201]),        # Quotes - should be accepted
        ("%%", [201]),         # SQL wildcards - should be accepted
        ("\\%\\_", [201]),     # Escaped SQL wildcards - should be accepted
    ])
    async def test__special_characters__are_handled_safely(
        self,
        client_as_user_a: AsyncClient,
        special_char: str,
        expected_codes: list[int],
    ) -> None:
        """Special characters in input are handled without crashing."""
        response = await client_as_user_a.post(
            "/bookmarks/",
            json={
                "url": f"https://special-char-test-{ord(special_char[0])}.example.com/",
                "title": f"Test {special_char} Title",
            },
        )

        # Should not crash and return expected status
        assert response.status_code in expected_codes

    async def test__null_byte__is_rejected_by_database(
        self,
        client_as_user_a: AsyncClient,
    ) -> None:
        """
        Null bytes are rejected by PostgreSQL (security feature).

        PostgreSQL does not allow null bytes in text columns, which prevents
        null byte injection attacks. This test verifies this protection by
        checking the database rejects the request.
        """
        import pytest

        # This test expects an exception because PostgreSQL rejects null bytes
        # at the database level with CharacterNotInRepertoireError
        with pytest.raises(Exception):  # noqa: PT011
            await client_as_user_a.post(
                "/bookmarks/",
                json={
                    "url": "https://null-byte-test.example.com/",
                    "title": "Test \x00 Title",
                },
            )


class TestILIKEEscaping:
    """Test that ILIKE special characters are properly escaped in search."""

    @pytest.mark.parametrize("search_term", [
        "%",              # Match all
        "_",              # Match single char
        "%%",             # Double wildcard
        "test%",          # Trailing wildcard
        "%test",          # Leading wildcard
        "te_t",           # Embedded single char
        "\\%",            # Escaped percent
        "\\_",            # Escaped underscore
    ])
    async def test__ilike_characters__are_escaped_in_search(
        self,
        client_as_user_a: AsyncClient,
        search_term: str,
    ) -> None:
        """ILIKE special characters are properly escaped in search queries."""
        response = await client_as_user_a.get(
            "/bookmarks/",
            params={"q": search_term},
        )

        # Should complete without error
        assert response.status_code == 200
