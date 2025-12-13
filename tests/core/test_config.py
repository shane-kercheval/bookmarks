"""Tests for application configuration."""
from core.config import Settings


class TestCorsOriginsParsing:
    """Tests for CORS origins parsing from environment variables."""

    def test_parse_single_origin_string(self) -> None:
        """Single origin string is parsed correctly."""
        settings = Settings(
            database_url="postgresql://test",
            cors_origins="http://localhost:5173",
        )
        assert settings.cors_origins == ["http://localhost:5173"]

    def test_parse_multiple_origins_comma_separated(self) -> None:
        """Multiple comma-separated origins are parsed correctly."""
        settings = Settings(
            database_url="postgresql://test",
            cors_origins="http://localhost:5173,https://example.com",
        )
        assert settings.cors_origins == [
            "http://localhost:5173",
            "https://example.com",
        ]

    def test_parse_origins_with_whitespace(self) -> None:
        """Whitespace around origins is stripped."""
        settings = Settings(
            database_url="postgresql://test",
            cors_origins="  http://localhost:5173 , https://example.com  ",
        )
        assert settings.cors_origins == [
            "http://localhost:5173",
            "https://example.com",
        ]

    def test_parse_origins_list_passthrough(self) -> None:
        """List of origins is passed through unchanged."""
        origins = ["http://localhost:5173", "https://example.com"]
        settings = Settings(
            database_url="postgresql://test",
            cors_origins=origins,
        )
        assert settings.cors_origins == origins

    def test_parse_empty_string(self) -> None:
        """Empty string results in empty list."""
        settings = Settings(
            database_url="postgresql://test",
            cors_origins="",
        )
        assert settings.cors_origins == []

    def test_parse_trailing_comma(self) -> None:
        """Trailing comma is handled (empty entries filtered)."""
        settings = Settings(
            database_url="postgresql://test",
            cors_origins="http://localhost:5173,",
        )
        assert settings.cors_origins == ["http://localhost:5173"]

    def test_default_cors_origins(self) -> None:
        """Default CORS origins is localhost:5173."""
        settings = Settings(database_url="postgresql://test")
        assert settings.cors_origins == ["http://localhost:5173"]
