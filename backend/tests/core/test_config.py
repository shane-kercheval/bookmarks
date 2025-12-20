"""Tests for application configuration."""
import pytest

from core.config import Settings


class TestCorsOriginsParsing:
    """Tests for CORS origins parsing from environment variables."""

    def test_parse_single_origin_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Single origin string is parsed correctly."""
        monkeypatch.delenv("VITE_DEV_MODE", raising=False)
        settings = Settings(
            _env_file=None,
            database_url="postgresql://test",
            CORS_ORIGINS="http://localhost:5173",
            VITE_DEV_MODE="false",
        )
        assert settings.cors_origins == ["http://localhost:5173"]

    def test_parse_multiple_origins_comma_separated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Multiple comma-separated origins are parsed correctly."""
        monkeypatch.delenv("VITE_DEV_MODE", raising=False)
        settings = Settings(
            _env_file=None,
            database_url="postgresql://test",
            CORS_ORIGINS="http://localhost:5173,https://example.com",
            VITE_DEV_MODE="false",
        )
        assert settings.cors_origins == [
            "http://localhost:5173",
            "https://example.com",
        ]

    def test_parse_origins_with_whitespace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Whitespace around origins is stripped."""
        monkeypatch.delenv("VITE_DEV_MODE", raising=False)
        settings = Settings(
            _env_file=None,
            database_url="postgresql://test",
            CORS_ORIGINS="  http://localhost:5173 , https://example.com  ",
            VITE_DEV_MODE="false",
        )
        assert settings.cors_origins == [
            "http://localhost:5173",
            "https://example.com",
        ]

    def test_parse_empty_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty string results in empty list."""
        monkeypatch.delenv("VITE_DEV_MODE", raising=False)
        settings = Settings(
            _env_file=None,
            database_url="postgresql://test",
            CORS_ORIGINS="",
            VITE_DEV_MODE="false",
        )
        assert settings.cors_origins == []

    def test_parse_trailing_comma(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Trailing comma is handled (empty entries filtered)."""
        monkeypatch.delenv("VITE_DEV_MODE", raising=False)
        settings = Settings(
            _env_file=None,
            database_url="postgresql://test",
            CORS_ORIGINS="http://localhost:5173,",
            VITE_DEV_MODE="false",
        )
        assert settings.cors_origins == ["http://localhost:5173"]

    def test_default_cors_origins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Default CORS origins is localhost:5173."""
        # Clear any CORS_ORIGINS env var that may be set
        monkeypatch.delenv("CORS_ORIGINS", raising=False)
        monkeypatch.delenv("VITE_DEV_MODE", raising=False)
        settings = Settings(
            _env_file=None,
            database_url="postgresql://test",
            VITE_DEV_MODE="false",
        )
        assert settings.cors_origins == ["http://localhost:5173"]


class TestAuth0Config:
    """Tests for Auth0 configuration with VITE_ prefix aliases."""

    def test_auth0_reads_vite_prefixed_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Auth0 settings can be set via VITE_AUTH0_* aliases."""
        monkeypatch.delenv("VITE_DEV_MODE", raising=False)
        settings = Settings(
            _env_file=None,  # Don't load from .env file
            database_url="postgresql://test",
            VITE_AUTH0_DOMAIN="test.auth0.com",
            VITE_AUTH0_CLIENT_ID="test-client-id",
            VITE_AUTH0_AUDIENCE="https://test-api",
            VITE_DEV_MODE="false",
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
        monkeypatch.delenv("VITE_DEV_MODE", raising=False)

        settings = Settings(
            _env_file=None,  # Don't load from .env file
            database_url="postgresql://test",
            VITE_DEV_MODE="false",
        )
        assert settings.auth0_domain == ""
        assert settings.auth0_client_id == ""
        assert settings.auth0_audience == ""

    def test_auth0_issuer_property(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Auth0 issuer URL is derived from domain."""
        monkeypatch.delenv("VITE_DEV_MODE", raising=False)
        settings = Settings(
            _env_file=None,
            database_url="postgresql://test",
            VITE_AUTH0_DOMAIN="test.auth0.com",
            VITE_DEV_MODE="false",
        )
        assert settings.auth0_issuer == "https://test.auth0.com/"

    def test_auth0_jwks_url_property(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Auth0 JWKS URL is derived from domain."""
        monkeypatch.delenv("VITE_DEV_MODE", raising=False)
        settings = Settings(
            _env_file=None,
            database_url="postgresql://test",
            VITE_AUTH0_DOMAIN="test.auth0.com",
            VITE_DEV_MODE="false",
        )
        assert settings.auth0_jwks_url == "https://test.auth0.com/.well-known/jwks.json"


class TestDevModeSecurityValidation:
    """Tests for DEV_MODE security guard against production database usage."""

    def test__dev_mode_allowed_with_localhost_database(self) -> None:
        """DEV_MODE can be enabled with localhost database."""
        settings = Settings(
            _env_file=None,
            database_url="postgresql://localhost:5432/test",
            VITE_DEV_MODE="true",
        )
        assert settings.dev_mode is True

    def test__dev_mode_allowed_with_127_0_0_1_database(self) -> None:
        """DEV_MODE can be enabled with 127.0.0.1 database."""
        settings = Settings(
            _env_file=None,
            database_url="postgresql://127.0.0.1:5432/test",
            VITE_DEV_MODE="true",
        )
        assert settings.dev_mode is True

    def test__dev_mode_allowed_with_ipv6_localhost(self) -> None:
        """DEV_MODE can be enabled with IPv6 localhost."""
        settings = Settings(
            _env_file=None,
            database_url="postgresql://[::1]:5432/test",
            VITE_DEV_MODE="true",
        )
        assert settings.dev_mode is True

    def test__dev_mode_blocked_with_production_database(self) -> None:
        """DEV_MODE raises error when enabled with production database."""
        with pytest.raises(
            ValueError,
            match="DEV_MODE cannot be enabled with a non-local database",
        ):
            Settings(
                _env_file=None,
                database_url="postgresql://prod-db.railway.app:5432/bookmarks",
                VITE_DEV_MODE="true",
            )

    def test__dev_mode_blocked_with_remote_ip_address(self) -> None:
        """DEV_MODE raises error with remote IP address."""
        with pytest.raises(
            ValueError,
            match="DEV_MODE cannot be enabled with a non-local database",
        ):
            Settings(
                _env_file=None,
                database_url="postgresql://192.168.1.100:5432/test",
                VITE_DEV_MODE="true",
            )

    def test__dev_mode_disabled_allows_production_database(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Production database is allowed when DEV_MODE is disabled."""
        monkeypatch.delenv("VITE_DEV_MODE", raising=False)
        settings = Settings(
            _env_file=None,
            database_url="postgresql://prod-db.railway.app:5432/bookmarks",
            VITE_DEV_MODE="false",
        )
        assert settings.dev_mode is False

    def test__dev_mode_blocked_with_empty_hostname(self) -> None:
        """DEV_MODE blocked when database URL has no hostname (fail-safe behavior)."""
        # PostgreSQL URL with empty host (triple slash means no host specified)
        # This should be blocked to ensure fail-safe behavior
        with pytest.raises(
            ValueError,
            match="DEV_MODE cannot be enabled with a non-local database",
        ):
            Settings(
                _env_file=None,
                database_url="postgresql:///database",
                VITE_DEV_MODE="true",
            )
