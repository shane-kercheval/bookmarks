"""Tests for application configuration."""
import pytest

from core.config import Settings


class TestCorsOriginsParsing:
    """Tests for CORS origins parsing from environment variables."""

    def test_parse_single_origin_string(self) -> None:
        """Single origin string is parsed correctly."""
        settings = Settings(
            _env_file=None,
            database_url="postgresql://test",
            CORS_ORIGINS="http://localhost:5173",
        )
        assert settings.cors_origins == ["http://localhost:5173"]

    def test_parse_multiple_origins_comma_separated(self) -> None:
        """Multiple comma-separated origins are parsed correctly."""
        settings = Settings(
            _env_file=None,
            database_url="postgresql://test",
            CORS_ORIGINS="http://localhost:5173,https://example.com",
        )
        assert settings.cors_origins == [
            "http://localhost:5173",
            "https://example.com",
        ]

    def test_parse_origins_with_whitespace(self) -> None:
        """Whitespace around origins is stripped."""
        settings = Settings(
            _env_file=None,
            database_url="postgresql://test",
            CORS_ORIGINS="  http://localhost:5173 , https://example.com  ",
        )
        assert settings.cors_origins == [
            "http://localhost:5173",
            "https://example.com",
        ]

    def test_parse_empty_string(self) -> None:
        """Empty string results in empty list."""
        settings = Settings(
            _env_file=None,
            database_url="postgresql://test",
            CORS_ORIGINS="",
        )
        assert settings.cors_origins == []

    def test_parse_trailing_comma(self) -> None:
        """Trailing comma is handled (empty entries filtered)."""
        settings = Settings(
            _env_file=None,
            database_url="postgresql://test",
            CORS_ORIGINS="http://localhost:5173,",
        )
        assert settings.cors_origins == ["http://localhost:5173"]

    def test_default_cors_origins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Default CORS origins is localhost:5173."""
        # Clear any CORS_ORIGINS env var that may be set
        monkeypatch.delenv("CORS_ORIGINS", raising=False)
        settings = Settings(_env_file=None, database_url="postgresql://test")
        assert settings.cors_origins == ["http://localhost:5173"]


class TestAuth0Config:
    """Tests for Auth0 configuration with VITE_ prefix aliases."""

    def test_auth0_reads_vite_prefixed_vars(self) -> None:
        """Auth0 settings can be set via VITE_AUTH0_* aliases."""
        settings = Settings(
            _env_file=None,  # Don't load from .env file
            database_url="postgresql://test",
            VITE_AUTH0_DOMAIN="test.auth0.com",
            VITE_AUTH0_CLIENT_ID="test-client-id",
            VITE_AUTH0_AUDIENCE="https://test-api",
        )
        assert settings.auth0_domain == "test.auth0.com"
        assert settings.auth0_client_id == "test-client-id"
        assert settings.auth0_audience == "https://test-api"

    def test_auth0_defaults_to_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Auth0 settings default to empty strings."""
        # Clear any Auth0 env vars that may be set in the shell
        monkeypatch.delenv("VITE_AUTH0_DOMAIN", raising=False)
        monkeypatch.delenv("VITE_AUTH0_CLIENT_ID", raising=False)
        monkeypatch.delenv("VITE_AUTH0_AUDIENCE", raising=False)

        settings = Settings(
            _env_file=None,  # Don't load from .env file
            database_url="postgresql://test",
        )
        assert settings.auth0_domain == ""
        assert settings.auth0_client_id == ""
        assert settings.auth0_audience == ""

    def test_auth0_issuer_property(self) -> None:
        """Auth0 issuer URL is derived from domain."""
        settings = Settings(
            _env_file=None,
            database_url="postgresql://test",
            VITE_AUTH0_DOMAIN="test.auth0.com",
        )
        assert settings.auth0_issuer == "https://test.auth0.com/"

    def test_auth0_jwks_url_property(self) -> None:
        """Auth0 JWKS URL is derived from domain."""
        settings = Settings(
            _env_file=None,
            database_url="postgresql://test",
            VITE_AUTH0_DOMAIN="test.auth0.com",
        )
        assert settings.auth0_jwks_url == "https://test.auth0.com/.well-known/jwks.json"
