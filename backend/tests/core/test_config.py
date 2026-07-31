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
            CLERK_FRONTEND_API="test-instance.clerk.accounts.dev",
            CLERK_AUTHORIZED_PARTIES="http://localhost:5173",
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
            CLERK_FRONTEND_API="test-instance.clerk.accounts.dev",
            CLERK_AUTHORIZED_PARTIES="http://localhost:5173",
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
            CLERK_FRONTEND_API="test-instance.clerk.accounts.dev",
            CLERK_AUTHORIZED_PARTIES="http://localhost:5173",
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
            CLERK_FRONTEND_API="test-instance.clerk.accounts.dev",
            CLERK_AUTHORIZED_PARTIES="http://localhost:5173",
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
            CLERK_FRONTEND_API="test-instance.clerk.accounts.dev",
            CLERK_AUTHORIZED_PARTIES="http://localhost:5173",
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
            CLERK_FRONTEND_API="test-instance.clerk.accounts.dev",
            CLERK_AUTHORIZED_PARTIES="http://localhost:5173",
        )
        assert settings.cors_origins == ["http://localhost:5173"]


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
            CLERK_FRONTEND_API="test-instance.clerk.accounts.dev",
            CLERK_AUTHORIZED_PARTIES="http://localhost:5173",
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


class TestClerkConfig:
    """Tests for the Clerk settings (M1; sole IdP since M6b)."""

    def _base_kwargs(self) -> dict:
        return {
            "_env_file": None,
            "database_url": "postgresql://test",
            "VITE_DEV_MODE": "false",
        }

    def test__production_requires_clerk_frontend_api(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Non-dev mode fails loudly at startup when CLERK_FRONTEND_API is missing."""
        monkeypatch.delenv("VITE_DEV_MODE", raising=False)
        monkeypatch.delenv("CLERK_FRONTEND_API", raising=False)
        monkeypatch.delenv("CLERK_AUTHORIZED_PARTIES", raising=False)
        with pytest.raises(ValueError, match="CLERK_FRONTEND_API is required"):
            Settings(**self._base_kwargs())

    def test__production_requires_authorized_parties(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Non-dev mode fails when the azp allowlist is empty (would reject all
        browser tokens).
        """
        monkeypatch.delenv("VITE_DEV_MODE", raising=False)
        monkeypatch.delenv("CLERK_AUTHORIZED_PARTIES", raising=False)
        with pytest.raises(ValueError, match="CLERK_AUTHORIZED_PARTIES is required"):
            Settings(
                **self._base_kwargs(),
                CLERK_FRONTEND_API="test-instance.clerk.accounts.dev",
            )

    def test__dev_mode_allows_missing_clerk_settings(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Dev mode requires no Clerk settings (auth is bypassed)."""
        monkeypatch.delenv("CLERK_FRONTEND_API", raising=False)
        monkeypatch.delenv("CLERK_AUTHORIZED_PARTIES", raising=False)
        settings = Settings(
            _env_file=None,
            database_url="postgresql://localhost:5432/test",
            VITE_DEV_MODE="true",
        )
        assert settings.clerk_frontend_api == ""

    def test__derived_issuer_and_jwks_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Issuer (no trailing slash — Clerk's format) and JWKS URL derive from
        the Frontend API domain.
        """
        monkeypatch.delenv("VITE_DEV_MODE", raising=False)
        settings = Settings(
            **self._base_kwargs(),
            CLERK_FRONTEND_API="test-instance.clerk.accounts.dev",
            CLERK_AUTHORIZED_PARTIES="http://localhost:5173",
        )
        assert settings.clerk_issuer == "https://test-instance.clerk.accounts.dev"
        assert settings.clerk_jwks_url == (
            "https://test-instance.clerk.accounts.dev/.well-known/jwks.json"
        )

    def test__authorized_parties_parsed_from_csv(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Comma-separated authorized parties parse with whitespace stripped."""
        monkeypatch.delenv("VITE_DEV_MODE", raising=False)
        settings = Settings(
            **self._base_kwargs(),
            CLERK_FRONTEND_API="test-instance.clerk.accounts.dev",
            CLERK_AUTHORIZED_PARTIES=" https://tiddly.me , http://localhost:5173 ",
        )
        assert settings.clerk_authorized_parties == [
            "https://tiddly.me",
            "http://localhost:5173",
        ]

    def test__jit_create_flag_defaults_production_safe(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """
        Default: Clerk-create OFF — a fresh deployment cannot mint accounts
        until the flag is deliberately enabled (kept as a sign-up kill switch).
        """
        monkeypatch.delenv("VITE_DEV_MODE", raising=False)
        monkeypatch.delenv("CLERK_JIT_CREATE_ENABLED", raising=False)
        settings = Settings(
            **self._base_kwargs(),
            CLERK_FRONTEND_API="test-instance.clerk.accounts.dev",
            CLERK_AUTHORIZED_PARTIES="https://tiddly.me",
        )
        assert settings.clerk_jit_create_enabled is False
