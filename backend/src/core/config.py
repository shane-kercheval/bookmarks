"""Application configuration using pydantic-settings."""
import socket
from functools import lru_cache
from urllib.parse import urlparse

from pydantic import Field, model_validator
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
    db_pool_size: int = Field(default=10, validation_alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=10, validation_alias="DB_MAX_OVERFLOW")
    db_pool_recycle: int = Field(default=3600, validation_alias="DB_POOL_RECYCLE")

    # Clerk — the sole IdP
    # Frontend API domain of the Clerk instance (e.g. "clerk.tiddly.me" in
    # production, "<slug>.clerk.accounts.dev" for the dev instance); issuer and
    # JWKS URL are derived from it.
    clerk_frontend_api: str = Field(default="", validation_alias="CLERK_FRONTEND_API")
    # Comma-separated web origins accepted as the `azp` (authorized party) claim
    # on Clerk session tokens. Clerk session tokens carry no audience; azp is
    # the equivalent check. Tokens without azp (non-browser clients) are
    # tolerated - see core/auth.py.
    clerk_authorized_parties_str: str = Field(
        default="",
        validation_alias="CLERK_AUTHORIZED_PARTIES",
    )
    # JIT user-creation flag (introduced as an AD5 migration-window rule).
    # Lookup is always allowed; this gates only *creation* of new user rows.
    # Kept post-migration as a sign-up kill switch: flipping it off stops new
    # accounts without touching existing users.
    clerk_jit_create_enabled: bool = Field(
        default=False,
        validation_alias="CLERK_JIT_CREATE_ENABLED",
    )
    # Svix signing secret ("whsec_...") for the Clerk webhook endpoint
    # (POST /webhooks/clerk), per environment - each Clerk instance's webhook
    # endpoint has its own secret (Dashboard -> Webhooks -> endpoint). Empty
    # means webhooks are unconfigured: the endpoint fails closed with 503.
    clerk_webhook_signing_secret: str = Field(
        default="",
        validation_alias="CLERK_WEBHOOK_SIGNING_SECRET",
    )

    # Development mode - bypasses auth for local development (shared with frontend)
    dev_mode: bool = Field(default=False, validation_alias="VITE_DEV_MODE")

    # URLs - used in consent enforcement error messages
    api_url: str = Field(
        default="http://localhost:8000",
        validation_alias="VITE_API_URL",
    )
    frontend_url: str = Field(
        default="http://localhost:5173",
        validation_alias="VITE_FRONTEND_URL",
    )

    # CORS - comma-separated list of allowed origins (stored as string, parsed via property)
    cors_origins_str: str = Field(
        default="http://localhost:5173",
        validation_alias="CORS_ORIGINS",
    )

    # Redis - for rate limiting and auth caching
    redis_url: str = Field(default="redis://localhost:6379", validation_alias="REDIS_URL")
    redis_enabled: bool = Field(default=True, validation_alias="REDIS_ENABLED")
    redis_pool_size: int = Field(default=5, validation_alias="REDIS_POOL_SIZE")

    # LLM models per use case
    llm_model_suggestions: str = Field(
        default="openai/gpt-5.4-nano",
        validation_alias="LLM_MODEL_SUGGESTIONS",
    )
    llm_model_transform: str = Field(
        default="gemini/gemini-flash-lite-latest",
        validation_alias="LLM_MODEL_TRANSFORM",
    )
    llm_model_auto_complete: str = Field(
        default="gemini/gemini-flash-lite-latest",
        validation_alias="LLM_MODEL_AUTO_COMPLETE",
    )
    llm_model_chat: str = Field(
        default="openai/gpt-5.4-mini",
        validation_alias="LLM_MODEL_CHAT",
    )

    # Provider API keys (only needed for providers referenced by models above)
    gemini_api_key: str = Field(default="", validation_alias="GEMINI_API_KEY")
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")

    # LLM call timeouts (seconds)
    llm_timeout_default: int = Field(default=30, validation_alias="LLM_TIMEOUT_DEFAULT")
    llm_timeout_streaming: int = Field(default=60, validation_alias="LLM_TIMEOUT_STREAMING")

    # Note: Field length limits moved to core/tier_limits.py (tier-based)

    @model_validator(mode="after")
    def validate_settings(self) -> "Settings":
        """
        Validate cross-field settings constraints.

        - Require the Clerk settings in production (prevents silent auth
          breakage)
        - Prevent DEV_MODE with non-local databases (auth bypass safety)
        """
        if not self.dev_mode:
            # Fail loudly at startup instead of silently rejecting every Clerk
            # token — Clerk is the sole IdP, so an unset Frontend API would be
            # a fully broken deployment.
            if not self.clerk_frontend_api:
                raise ValueError(
                    "CLERK_FRONTEND_API is required when DEV_MODE is disabled. "
                    "Without it, Clerk session tokens cannot be verified.",
                )
            if not self.clerk_authorized_parties:
                raise ValueError(
                    "CLERK_AUTHORIZED_PARTIES is required when DEV_MODE is disabled. "
                    "With an empty allowlist, every browser-issued Clerk token "
                    "(azp present) would be rejected.",
                )
            return self

        # Parse database URL to extract hostname
        try:
            parsed = urlparse(self.database_url)
            hostname = parsed.hostname or ""
        except Exception:
            # If we can't parse the URL, block DEV_MODE (fail-safe)
            hostname = ""

        # Check if database is on localhost
        local_hosts = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
        if hostname.lower() not in local_hosts:
            raise ValueError(
                f"DEV_MODE cannot be enabled with a non-local database. "
                f"Database host '{hostname}' appears to be a production database. "
                f"DEV_MODE bypasses all authentication and must only be used locally.",
            )

        return self

    @property
    def cors_origins(self) -> list[str]:
        """
        Parse comma-separated CORS origins string into a list.

        In dev mode, automatically includes origins for all local network IPs
        so the frontend can be accessed from a VM host without manual CORS config.
        """
        origins = []
        if self.cors_origins_str:
            origins = [
                origin.strip()
                for origin in self.cors_origins_str.split(",")
                if origin.strip()
            ]

        if self.dev_mode:
            for ip in _get_local_ips():
                origin = f"http://{ip}:5173"
                if origin not in origins:
                    origins.append(origin)

        return origins

    @property
    def clerk_issuer(self) -> str:
        """Get the Clerk issuer URL (no trailing slash)."""
        return f"https://{self.clerk_frontend_api}"

    @property
    def clerk_jwks_url(self) -> str:
        """Get the Clerk JWKS URL for fetching public keys."""
        return f"https://{self.clerk_frontend_api}/.well-known/jwks.json"

    @property
    def clerk_authorized_parties(self) -> list[str]:
        """Parse comma-separated authorized-party origins into a list."""
        return [
            party.strip()
            for party in self.clerk_authorized_parties_str.split(",")
            if party.strip()
        ]


def _get_local_ips() -> list[str]:
    """
    Return non-loopback IPv4 addresses for this machine.

    Uses UDP connect trick to discover routable IPs — works reliably
    across Linux distributions regardless of /etc/hosts configuration.
    """
    ips: list[str] = []
    # Connect a UDP socket to a public IP (no traffic sent) to discover
    # which local IP the OS would route through.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('8.8.8.8', 80))
            addr = s.getsockname()[0]
            if not addr.startswith('127.'):
                ips.append(addr)
    except OSError:
        pass
    return ips


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
