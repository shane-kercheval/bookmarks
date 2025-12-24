"""
Rate limiting configuration and types.

This module contains the policy configuration for rate limiting - the "what" limits
to apply, separate from the "how" (enforcement logic in rate_limiter.py).

To adjust rate limits, modify RATE_LIMITS below.
To add new sensitive endpoints, add them to SENSITIVE_ENDPOINTS.
"""
from dataclasses import dataclass
from enum import Enum


class AuthType(Enum):
    """Authentication type for rate limiting."""

    PAT = "pat"
    AUTH0 = "auth0"


class OperationType(Enum):
    """Operation type for rate limiting."""

    READ = "read"
    WRITE = "write"
    SENSITIVE = "sensitive"  # External HTTP calls, AI/LLM, bulk operations


@dataclass
class RateLimitConfig:
    """Rate limit configuration for a specific auth/operation combination."""

    requests_per_minute: int
    requests_per_day: int


@dataclass
class RateLimitResult:
    """Result of a rate limit check with all info needed for headers."""

    allowed: bool
    limit: int  # Max requests in current window
    remaining: int  # Requests remaining in current window
    reset: int  # Unix timestamp when window resets
    retry_after: int  # Seconds until retry allowed (0 if allowed)


class RateLimitExceededError(Exception):
    """Raised when rate limit is exceeded."""

    def __init__(self, result: RateLimitResult) -> None:
        self.result = result
        super().__init__("Rate limit exceeded")


# ---------------------------------------------------------------------------
# Rate Limit Policy Configuration
# ---------------------------------------------------------------------------
# Modify these values to adjust rate limits.
# Daily caps: general (read/write) vs sensitive are tracked separately.

RATE_LIMITS: dict[tuple[AuthType, OperationType], RateLimitConfig] = {
    # PAT limits
    (AuthType.PAT, OperationType.READ): RateLimitConfig(requests_per_minute=240, requests_per_day=4000),  # noqa
    (AuthType.PAT, OperationType.WRITE): RateLimitConfig(requests_per_minute=120, requests_per_day=4000),  # noqa
    # PAT + SENSITIVE = not allowed (handled by auth dependency, returns 403)

    # Auth0 limits (probably originated from browser end-users)
    (AuthType.AUTH0, OperationType.READ): RateLimitConfig(requests_per_minute=180, requests_per_day=4000),  # noqa
    (AuthType.AUTH0, OperationType.WRITE): RateLimitConfig(requests_per_minute=120, requests_per_day=4000),  # noqa
    (AuthType.AUTH0, OperationType.SENSITIVE): RateLimitConfig(requests_per_minute=30, requests_per_day=250),  # noqa
}


# ---------------------------------------------------------------------------
# Sensitive Endpoints
# ---------------------------------------------------------------------------
# Endpoints that make external HTTP requests or are resource-intensive.
# These get stricter rate limits and are blocked for PAT auth.
# Format: (HTTP_METHOD, path_without_query_params)

SENSITIVE_ENDPOINTS: set[tuple[str, str]] = {
    ("GET", "/bookmarks/fetch-metadata"),
    # Future: AI/LLM endpoints, bulk import/export
}


def get_operation_type(method: str, path: str) -> OperationType:
    """Determine operation type from HTTP method and path."""
    if (method, path) in SENSITIVE_ENDPOINTS:
        return OperationType.SENSITIVE
    if method == "GET":
        return OperationType.READ
    return OperationType.WRITE
