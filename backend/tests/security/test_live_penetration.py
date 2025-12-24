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


class TestConsentEnforcement:
    """Verify consent enforcement is working in production."""

    @pytest.mark.asyncio
    async def test__consent_status__returns_valid_structure(
        self,
        headers_user_a: dict[str, str],
    ) -> None:
        """GET /consent/status returns expected structure."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{API_URL}/consent/status",
                headers=headers_user_a,
            )

        assert response.status_code == 200
        data = response.json()
        # Verify expected fields exist
        assert "needs_consent" in data
        assert "current_privacy_version" in data
        assert "current_terms_version" in data
        assert "current_consent" in data
        # Test user should have consented (needs_consent = False)
        assert data["needs_consent"] is False, (
            "Test user hasn't consented - protected endpoint tests may fail with 451"
        )

    @pytest.mark.asyncio
    async def test__authenticated_user_with_consent__not_blocked(
        self,
        headers_user_a: dict[str, str],
    ) -> None:
        """Users with valid consent can access protected endpoints (no 451)."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{API_URL}/bookmarks/",
                headers=headers_user_a,
            )

        # Should NOT get 451 (consent required)
        assert response.status_code != 451, (
            f"User got 451 despite having PAT. Response: {response.json()}"
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test__consent_can_be_updated(
        self,
        headers_user_a: dict[str, str],
    ) -> None:
        """User can re-consent (update their consent record)."""
        async with httpx.AsyncClient() as client:
            # Get current versions
            status_resp = await client.get(
                f"{API_URL}/consent/status",
                headers=headers_user_a,
            )
            assert status_resp.status_code == 200
            current_versions = status_resp.json()

            # Re-consent with current versions
            consent_resp = await client.post(
                f"{API_URL}/consent/me",
                headers=headers_user_a,
                json={
                    "privacy_policy_version": current_versions["current_privacy_version"],
                    "terms_of_service_version": current_versions["current_terms_version"],
                },
            )

            assert consent_resp.status_code == 201
            data = consent_resp.json()
            assert data["privacy_policy_version"] == current_versions["current_privacy_version"]
            assert data["terms_of_service_version"] == current_versions["current_terms_version"]

    @pytest.mark.asyncio
    async def test__unauthenticated_consent_status__returns_401(self) -> None:
        """Consent status requires authentication."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_URL}/consent/status")

        assert response.status_code == 401


class TestPATRestrictedEndpoints:
    """
    Verify PAT-restricted endpoints reject PAT tokens.

    These endpoints require Auth0 authentication and block Personal Access Tokens
    to help prevent unintended programmatic use. Note: this does NOT prevent all
    programmatic access - users can extract Auth0 JWTs from browser DevTools.
    Rate limiting provides the additional layer to cap any abuse.
    """

    @pytest.mark.asyncio
    async def test__fetch_metadata__rejects_pat(
        self,
        headers_user_a: dict[str, str],
    ) -> None:
        """
        The fetch-metadata endpoint rejects PAT tokens with 403.

        This endpoint blocks PAT access to help prevent PAT-based SSRF abuse.
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{API_URL}/bookmarks/fetch-metadata",
                headers=headers_user_a,
                params={"url": "https://example.com/"},
            )

        assert response.status_code == 403, (
            f"SECURITY: fetch-metadata should reject PATs with 403. "
            f"Got {response.status_code}: {response.text}"
        )
        assert "not available for API tokens" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test__tokens_create__rejects_pat(
        self,
        headers_user_a: dict[str, str],
    ) -> None:
        """Token creation endpoint rejects PATs - prevents token proliferation attacks."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{API_URL}/tokens/",
                headers=headers_user_a,
                json={"name": "should-not-be-created"},
            )

        assert response.status_code == 403, (
            f"SECURITY: POST /tokens/ should reject PATs with 403. "
            f"Got {response.status_code}: {response.text}"
        )
        assert "not available for API tokens" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test__tokens_list__rejects_pat(
        self,
        headers_user_a: dict[str, str],
    ) -> None:
        """Token listing endpoint rejects PATs."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{API_URL}/tokens/",
                headers=headers_user_a,
            )

        assert response.status_code == 403, (
            f"SECURITY: GET /tokens/ should reject PATs with 403. "
            f"Got {response.status_code}: {response.text}"
        )
        assert "not available for API tokens" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test__tokens_delete__rejects_pat(
        self,
        headers_user_a: dict[str, str],
    ) -> None:
        """Token deletion endpoint rejects PATs."""
        async with httpx.AsyncClient() as client:
            # Try to delete a non-existent token - should get 403 before 404
            response = await client.delete(
                f"{API_URL}/tokens/99999",
                headers=headers_user_a,
            )

        assert response.status_code == 403, (
            f"SECURITY: DELETE /tokens/{{id}} should reject PATs with 403. "
            f"Got {response.status_code}: {response.text}"
        )
        assert "not available for API tokens" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test__settings_get__rejects_pat(
        self,
        headers_user_a: dict[str, str],
    ) -> None:
        """Settings GET endpoint rejects PATs."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{API_URL}/settings/",
                headers=headers_user_a,
            )

        assert response.status_code == 403, (
            f"SECURITY: GET /settings/ should reject PATs with 403. "
            f"Got {response.status_code}: {response.text}"
        )
        assert "not available for API tokens" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test__settings_update__rejects_pat(
        self,
        headers_user_a: dict[str, str],
    ) -> None:
        """Settings PATCH endpoint rejects PATs."""
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{API_URL}/settings/",
                headers=headers_user_a,
                json={"theme": "dark"},
            )

        assert response.status_code == 403, (
            f"SECURITY: PATCH /settings/ should reject PATs with 403. "
            f"Got {response.status_code}: {response.text}"
        )
        assert "not available for API tokens" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test__settings_tab_order__rejects_pat(
        self,
        headers_user_a: dict[str, str],
    ) -> None:
        """Settings tab-order endpoint rejects PATs."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{API_URL}/settings/tab-order",
                headers=headers_user_a,
            )

        assert response.status_code == 403, (
            f"SECURITY: GET /settings/tab-order should reject PATs with 403. "
            f"Got {response.status_code}: {response.text}"
        )
        assert "not available for API tokens" in response.json()["detail"]


if __name__ == "__main__":
    # Allow running directly: python test_live_penetration.py
    pytest.main([__file__, "-v"])
