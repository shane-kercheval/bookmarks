"""Application configuration using pydantic-settings."""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # Database
    database_url: str

    # Auth0 - shared with frontend (VITE_ prefix for Vite exposure)
    auth0_domain: str = Field(default="", validation_alias="VITE_AUTH0_DOMAIN")
    auth0_audience: str = Field(default="", validation_alias="VITE_AUTH0_AUDIENCE")
    auth0_client_id: str = Field(default="", validation_alias="VITE_AUTH0_CLIENT_ID")

    # Development mode - bypasses auth for local development (shared with frontend)
    dev_mode: bool = Field(default=False, validation_alias="VITE_DEV_MODE")

    # CORS - comma-separated list of allowed origins (stored as string, parsed via property)
    cors_origins_str: str = Field(
        default="http://localhost:5173",
        validation_alias="CORS_ORIGINS",
    )

    @property
    def cors_origins(self) -> list[str]:
        """Parse comma-separated CORS origins string into a list."""
        if not self.cors_origins_str:
            return []
        return [origin.strip() for origin in self.cors_origins_str.split(",") if origin.strip()]

    @property
    def auth0_issuer(self) -> str:
        """Get the Auth0 issuer URL."""
        return f"https://{self.auth0_domain}/"

    @property
    def auth0_jwks_url(self) -> str:
        """Get the Auth0 JWKS URL for fetching public keys."""
        return f"https://{self.auth0_domain}/.well-known/jwks.json"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
