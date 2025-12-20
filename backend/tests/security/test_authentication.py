"""
Authentication security tests.

These tests verify that authentication is properly enforced on protected
endpoints and that authentication bypass is not possible.

OWASP Reference: A07:2021 - Identification and Authentication Failures

NOTE: These tests run against the deployed environment via SECURITY_TEST_API_URL
since the test suite runs in DEV_MODE by default.
"""
import os

import httpx
import pytest


# Configuration - must be set via environment variable
API_URL = os.environ.get("SECURITY_TEST_API_URL", "")

# Skip all tests if API URL not configured
pytestmark = pytest.mark.skipif(
    not API_URL,
    reason="Authentication tests require SECURITY_TEST_API_URL in .env",
)


class TestAuthenticationEnforcementDeployed:
    """Test that authentication is required on protected endpoints (deployed)."""

    @pytest.mark.parametrize(("endpoint", "method"), [
        ("/bookmarks/", "GET"),
        ("/users/me", "GET"),
        ("/tokens/", "GET"),
        ("/tags/", "GET"),
    ])
    async def test__protected_endpoint__requires_authentication(
        self,
        endpoint: str,
        method: str,
    ) -> None:
        """Protected endpoints return 401 when accessed without authentication."""
        async with httpx.AsyncClient() as client:
            url = f"{API_URL}{endpoint}"
            if method == "GET":
                response = await client.get(url)
            elif method == "POST":
                response = await client.post(url, json={})
            else:
                pytest.fail(f"Unknown method: {method}")

        assert response.status_code == 401, (
            f"Expected 401 for unauthenticated {method} {endpoint}, "
            f"got {response.status_code}"
        )


class TestHealthEndpoint:
    """Test the health endpoint behavior (intentionally public)."""

    async def test__health__accessible_without_authentication(
        self,
    ) -> None:
        """Health endpoint is accessible without authentication (via deployed API)."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_URL}/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"
