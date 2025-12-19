"""Tests for the MCP authentication utilities."""

from unittest.mock import patch

import pytest

from mcp_server.auth import AuthenticationError, get_bearer_token


def test__get_bearer_token__valid() -> None:
    """Test extracting valid Bearer token."""
    with patch("mcp_server.auth.get_http_headers") as mock_headers:
        mock_headers.return_value = {"authorization": "Bearer bm_test_token"}

        token = get_bearer_token()

        assert token == "bm_test_token"


def test__get_bearer_token__case_insensitive_bearer() -> None:
    """Test Bearer prefix is case-insensitive."""
    with patch("mcp_server.auth.get_http_headers") as mock_headers:
        mock_headers.return_value = {"authorization": "bearer bm_test_token"}

        token = get_bearer_token()

        assert token == "bm_test_token"


def test__get_bearer_token__missing_header() -> None:
    """Test error when Authorization header is missing."""
    with patch("mcp_server.auth.get_http_headers") as mock_headers:
        mock_headers.return_value = {}

        with pytest.raises(AuthenticationError, match="Missing or invalid"):
            get_bearer_token()


def test__get_bearer_token__invalid_scheme() -> None:
    """Test error when not using Bearer scheme."""
    with patch("mcp_server.auth.get_http_headers") as mock_headers:
        mock_headers.return_value = {"authorization": "Basic abc123"}

        with pytest.raises(AuthenticationError, match="Missing or invalid"):
            get_bearer_token()


def test__get_bearer_token__empty_token() -> None:
    """Test error when token is empty (Bearer with trailing space only)."""
    with patch("mcp_server.auth.get_http_headers") as mock_headers:
        mock_headers.return_value = {"authorization": "Bearer "}

        with pytest.raises(AuthenticationError, match="Missing or invalid"):
            get_bearer_token()
