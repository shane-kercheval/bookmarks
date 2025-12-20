"""
Live penetration tests against deployed API.

These tests verify security controls by making real HTTP requests to the
deployed API with actual authentication tokens.

SETUP:
1. Create two separate user accounts in Auth0 (different logins)
2. Generate a PAT for each user via the web UI
3. Add to your .env file:

    SECURITY_TEST_USER_A_PAT=bm_xxxxxxxxxxxxxxxx
    SECURITY_TEST_USER_B_PAT=bm_yyyyyyyyyyyyyyyy

4. Run: uv run pytest backend/tests/security/test_live_penetration.py -v

Tests are skipped if the environment variables are not set (e.g., in CI/CD).

IMPORTANT: The two PATs MUST be from DIFFERENT user accounts.
"""
import os

import httpx
import pytest

# Configuration - all must be set via environment variables
API_URL = os.environ.get("SECURITY_TEST_API_URL", "")
USER_A_PAT = os.environ.get("SECURITY_TEST_USER_A_PAT", "")
USER_B_PAT = os.environ.get("SECURITY_TEST_USER_B_PAT", "")

# Skip all tests if required env vars not configured
pytestmark = pytest.mark.skipif(
    not API_URL or not USER_A_PAT or not USER_B_PAT,
    reason="Live penetration tests require SECURITY_TEST_API_URL, SECURITY_TEST_USER_A_PAT, and SECURITY_TEST_USER_B_PAT in .env",
)


@pytest.fixture
def headers_user_a() -> dict[str, str]:
    """Auth headers for User A."""
    return {"Authorization": f"Bearer {USER_A_PAT}"}


@pytest.fixture
def headers_user_b() -> dict[str, str]:
    """Auth headers for User B."""
    return {"Authorization": f"Bearer {USER_B_PAT}"}


class TestAuthenticationEnforcement:
    """Verify authentication is required on protected endpoints."""

    @pytest.mark.asyncio
    async def test__unauthenticated_request__returns_401(self) -> None:
        """Requests without authentication are rejected."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_URL}/users/me")

        assert response.status_code == 401
        assert response.json()["detail"] == "Not authenticated"

    @pytest.mark.asyncio
    async def test__invalid_token__returns_401(self) -> None:
        """Requests with invalid tokens are rejected."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{API_URL}/users/me",
                headers={"Authorization": "Bearer bm_invalid_token_12345"},
            )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test__valid_token__returns_user(
        self,
        headers_user_a: dict[str, str],
    ) -> None:
        """Requests with valid tokens succeed."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{API_URL}/users/me",
                headers=headers_user_a,
            )

        assert response.status_code == 200
        assert "id" in response.json()


class TestBookmarkIDOR:
    """Verify users cannot access other users' bookmarks."""

    @pytest.mark.asyncio
    async def test__cross_user_bookmark_access__returns_404(
        self,
        headers_user_a: dict[str, str],
        headers_user_b: dict[str, str],
    ) -> None:
        """User B cannot access User A's bookmark by ID."""
        async with httpx.AsyncClient() as client:
            # User A creates a bookmark
            create_response = await client.post(
                f"{API_URL}/bookmarks/",
                headers=headers_user_a,
                json={
                    "url": "https://idor-test-unique-12345.example.com/",
                    "title": "User A's Private Bookmark",
                    "tags": ["idor-test"],
                },
            )

            # Handle case where URL already exists
            if create_response.status_code == 409:
                # Clean up: find and delete existing bookmark first
                list_response = await client.get(
                    f"{API_URL}/bookmarks/",
                    headers=headers_user_a,
                    params={"q": "idor-test-unique-12345"},
                )
                if list_response.status_code == 200:
                    items = list_response.json().get("items", [])
                    for item in items:
                        await client.delete(
                            f"{API_URL}/bookmarks/{item['id']}",
                            headers=headers_user_a,
                            params={"permanent": "true"},
                        )
                # Retry creation
                create_response = await client.post(
                    f"{API_URL}/bookmarks/",
                    headers=headers_user_a,
                    json={
                        "url": "https://idor-test-unique-12345.example.com/",
                        "title": "User A's Private Bookmark",
                        "tags": ["idor-test"],
                    },
                )

            assert create_response.status_code == 201, f"Failed to create bookmark: {create_response.text}"
            bookmark_id = create_response.json()["id"]

            try:
                # User B tries to access User A's bookmark
                access_response = await client.get(
                    f"{API_URL}/bookmarks/{bookmark_id}",
                    headers=headers_user_b,
                )

                # Should return 404 (not 403) to prevent ID enumeration
                assert access_response.status_code == 404, (
                    f"SECURITY VULNERABILITY: User B accessed User A's bookmark! "
                    f"Status: {access_response.status_code}, Body: {access_response.text}"
                )

            finally:
                # Cleanup: User A deletes the bookmark
                await client.delete(
                    f"{API_URL}/bookmarks/{bookmark_id}",
                    headers=headers_user_a,
                    params={"permanent": "true"},
                )

    @pytest.mark.asyncio
    async def test__cross_user_bookmark_update__returns_404(
        self,
        headers_user_a: dict[str, str],
        headers_user_b: dict[str, str],
    ) -> None:
        """User B cannot update User A's bookmark."""
        async with httpx.AsyncClient() as client:
            # User A creates a bookmark
            create_response = await client.post(
                f"{API_URL}/bookmarks/",
                headers=headers_user_a,
                json={
                    "url": "https://idor-update-test-67890.example.com/",
                    "title": "Original Title",
                },
            )

            if create_response.status_code == 409:
                pytest.skip("Bookmark already exists, skipping test")

            assert create_response.status_code == 201
            bookmark_id = create_response.json()["id"]

            try:
                # User B tries to update User A's bookmark
                update_response = await client.patch(
                    f"{API_URL}/bookmarks/{bookmark_id}",
                    headers=headers_user_b,
                    json={"title": "HACKED BY USER B"},
                )

                assert update_response.status_code == 404, (
                    f"SECURITY VULNERABILITY: User B updated User A's bookmark! "
                    f"Status: {update_response.status_code}"
                )

                # Verify the bookmark was NOT modified
                verify_response = await client.get(
                    f"{API_URL}/bookmarks/{bookmark_id}",
                    headers=headers_user_a,
                )
                assert verify_response.json()["title"] == "Original Title"

            finally:
                await client.delete(
                    f"{API_URL}/bookmarks/{bookmark_id}",
                    headers=headers_user_a,
                    params={"permanent": "true"},
                )

    @pytest.mark.asyncio
    async def test__cross_user_bookmark_delete__returns_404(
        self,
        headers_user_a: dict[str, str],
        headers_user_b: dict[str, str],
    ) -> None:
        """User B cannot delete User A's bookmark."""
        async with httpx.AsyncClient() as client:
            # User A creates a bookmark
            create_response = await client.post(
                f"{API_URL}/bookmarks/",
                headers=headers_user_a,
                json={
                    "url": "https://idor-delete-test-11111.example.com/",
                    "title": "Should Not Be Deleted",
                },
            )

            if create_response.status_code == 409:
                pytest.skip("Bookmark already exists, skipping test")

            assert create_response.status_code == 201
            bookmark_id = create_response.json()["id"]

            try:
                # User B tries to delete User A's bookmark
                delete_response = await client.delete(
                    f"{API_URL}/bookmarks/{bookmark_id}",
                    headers=headers_user_b,
                )

                assert delete_response.status_code == 404, (
                    f"SECURITY VULNERABILITY: User B deleted User A's bookmark! "
                    f"Status: {delete_response.status_code}"
                )

                # Verify the bookmark still exists
                verify_response = await client.get(
                    f"{API_URL}/bookmarks/{bookmark_id}",
                    headers=headers_user_a,
                )
                assert verify_response.status_code == 200, "Bookmark was deleted!"

            finally:
                await client.delete(
                    f"{API_URL}/bookmarks/{bookmark_id}",
                    headers=headers_user_a,
                    params={"permanent": "true"},
                )

    @pytest.mark.asyncio
    async def test__bookmark_list__excludes_other_users_data(
        self,
        headers_user_a: dict[str, str],
        headers_user_b: dict[str, str],
    ) -> None:
        """User B's bookmark list does not include User A's bookmarks."""
        async with httpx.AsyncClient() as client:
            # User A creates a bookmark with unique identifier
            unique_tag = "isolation-test-98765"
            create_response = await client.post(
                f"{API_URL}/bookmarks/",
                headers=headers_user_a,
                json={
                    "url": "https://isolation-test-98765.example.com/",
                    "title": "User A Secret Bookmark",
                    "tags": [unique_tag],
                },
            )

            if create_response.status_code == 409:
                pytest.skip("Bookmark already exists, skipping test")

            assert create_response.status_code == 201
            bookmark_id = create_response.json()["id"]

            try:
                # User B searches for User A's bookmark
                search_response = await client.get(
                    f"{API_URL}/bookmarks/",
                    headers=headers_user_b,
                    params={"q": "isolation-test-98765"},
                )

                assert search_response.status_code == 200
                items = search_response.json()["items"]

                # User B should NOT find User A's bookmark
                found_ids = [item["id"] for item in items]
                assert bookmark_id not in found_ids, (
                    "SECURITY VULNERABILITY: User B found User A's bookmark in search!"
                )

            finally:
                await client.delete(
                    f"{API_URL}/bookmarks/{bookmark_id}",
                    headers=headers_user_a,
                    params={"permanent": "true"},
                )


class TestTokenIDOR:
    """Verify users cannot access other users' tokens."""

    @pytest.mark.asyncio
    async def test__token_list__excludes_other_users_tokens(
        self,
        headers_user_a: dict[str, str],
        headers_user_b: dict[str, str],
    ) -> None:
        """User B's token list does not include User A's tokens."""
        async with httpx.AsyncClient() as client:
            # Get User A's token list
            response_a = await client.get(
                f"{API_URL}/tokens/",
                headers=headers_user_a,
            )
            assert response_a.status_code == 200
            token_ids_a = {t["id"] for t in response_a.json()}

            # Get User B's token list
            response_b = await client.get(
                f"{API_URL}/tokens/",
                headers=headers_user_b,
            )
            assert response_b.status_code == 200
            token_ids_b = {t["id"] for t in response_b.json()}

            # There should be no overlap
            overlap = token_ids_a & token_ids_b
            assert not overlap, (
                f"SECURITY VULNERABILITY: Users share token IDs: {overlap}"
            )


class TestCORSProtection:
    """Verify CORS is properly configured."""

    @pytest.mark.asyncio
    async def test__malicious_origin__is_rejected(self) -> None:
        """Requests from unauthorized origins are rejected."""
        async with httpx.AsyncClient() as client:
            response = await client.options(
                f"{API_URL}/bookmarks/",
                headers={
                    "Origin": "https://evil-attacker-site.com",
                    "Access-Control-Request-Method": "POST",
                },
            )

        # Should either return 400 or not include CORS headers
        if response.status_code == 200:
            # If 200, should NOT have Access-Control-Allow-Origin for evil domain
            allowed_origin = response.headers.get("Access-Control-Allow-Origin", "")
            assert "evil-attacker-site.com" not in allowed_origin, (
                "SECURITY VULNERABILITY: Malicious origin is allowed!"
            )
        else:
            # 400 is the expected response for disallowed origins
            assert response.status_code == 400


class TestTokenRevocation:
    """Verify revoked tokens are immediately invalidated."""

    @pytest.mark.asyncio
    async def test__revoked_token__returns_401(
        self,
        headers_user_a: dict[str, str],
    ) -> None:
        """Deleted tokens are immediately invalidated."""
        async with httpx.AsyncClient() as client:
            # Create a new token using existing PAT
            create_resp = await client.post(
                f"{API_URL}/tokens/",
                headers=headers_user_a,
                json={"name": "revocation-test-token"},
            )
            assert create_resp.status_code == 201
            new_token = create_resp.json()["token"]
            token_id = create_resp.json()["id"]

            # Verify new token works
            verify_resp = await client.get(
                f"{API_URL}/users/me",
                headers={"Authorization": f"Bearer {new_token}"},
            )
            assert verify_resp.status_code == 200

            # Revoke it (using original PAT)
            delete_resp = await client.delete(
                f"{API_URL}/tokens/{token_id}",
                headers=headers_user_a,
            )
            assert delete_resp.status_code == 204

            # Verify revoked token fails
            fail_resp = await client.get(
                f"{API_URL}/users/me",
                headers={"Authorization": f"Bearer {new_token}"},
            )
            assert fail_resp.status_code == 401, (
                "SECURITY VULNERABILITY: Revoked token still works!"
            )


class TestRaceConditions:
    """Test for race condition vulnerabilities."""

    @pytest.mark.asyncio
    async def test__concurrent_bookmark_creation__no_duplicates(
        self,
        headers_user_a: dict[str, str],
    ) -> None:
        """Rapid duplicate POSTs don't create multiple bookmarks."""
        import asyncio

        url = "https://race-condition-test-unique.example.com/"

        async def create_bookmark() -> httpx.Response:
            async with httpx.AsyncClient() as client:
                return await client.post(
                    f"{API_URL}/bookmarks/",
                    headers=headers_user_a,
                    json={"url": url},
                )

        # Fire 5 concurrent requests
        results = await asyncio.gather(
            *[create_bookmark() for _ in range(5)],
            return_exceptions=True,
        )

        # Expect exactly 1 success (201), rest should be 409 conflict
        status_codes = [r.status_code for r in results if isinstance(r, httpx.Response)]
        assert status_codes.count(201) == 1, (
            f"Race condition: expected 1 success, got {status_codes.count(201)}! "
            f"Statuses: {status_codes}"
        )
        assert all(code in (201, 409) for code in status_codes), (
            f"Unexpected status codes: {status_codes}"
        )

        # Cleanup
        async with httpx.AsyncClient() as client:
            search = await client.get(
                f"{API_URL}/bookmarks/",
                headers=headers_user_a,
                params={"q": "race-condition-test-unique"},
            )
            for item in search.json().get("items", []):
                await client.delete(
                    f"{API_URL}/bookmarks/{item['id']}",
                    headers=headers_user_a,
                    params={"permanent": "true"},
                )

    @pytest.mark.asyncio
    async def test__concurrent_token_deletion__handles_gracefully(
        self,
        headers_user_a: dict[str, str],
    ) -> None:
        """Deleting the same token twice concurrently doesn't cause errors."""
        import asyncio

        async with httpx.AsyncClient() as client:
            # Create a token
            create_resp = await client.post(
                f"{API_URL}/tokens/",
                headers=headers_user_a,
                json={"name": "race-delete-test"},
            )
            assert create_resp.status_code == 201
            token_id = create_resp.json()["id"]

        # Try to delete it 3 times concurrently
        async def delete_token() -> httpx.Response:
            async with httpx.AsyncClient() as client:
                return await client.delete(
                    f"{API_URL}/tokens/{token_id}",
                    headers=headers_user_a,
                )

        results = await asyncio.gather(
            *[delete_token() for _ in range(3)],
            return_exceptions=True,
        )

        # One should succeed (204), others should get 404
        codes = [r.status_code for r in results if isinstance(r, httpx.Response)]
        assert 204 in codes, f"No deletion succeeded: {codes}"
        assert all(c in (204, 404) for c in codes), (
            f"Unexpected status codes in concurrent delete: {codes}"
        )


class TestRateLimiting:
    """Verify rate limiting is in place."""

    @pytest.mark.asyncio
    async def test__fetch_metadata__has_rate_limit(
        self,
        headers_user_a: dict[str, str],
    ) -> None:
        """The fetch-metadata endpoint has rate limiting."""
        async with httpx.AsyncClient() as client:
            # Make many rapid requests
            responses = []
            for i in range(20):
                response = await client.get(
                    f"{API_URL}/bookmarks/fetch-metadata",
                    headers=headers_user_a,
                    params={"url": f"https://rate-limit-test-{i}.example.com/"},
                )
                responses.append(response)

            # At least some should be rate limited (429)
            status_codes = [r.status_code for r in responses]
            rate_limited = status_codes.count(429)

            # We expect rate limiting after 15 requests per minute
            assert rate_limited > 0, (
                f"No rate limiting detected after 20 requests. "
                f"Status codes: {status_codes}"
            )


if __name__ == "__main__":
    # Allow running directly: python test_live_penetration.py
    pytest.main([__file__, "-v"])
