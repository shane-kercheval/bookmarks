"""FastAPI dependencies for injection."""
from fastapi import Depends, Request

from core.auth import (
    get_current_user,
    get_current_user_auth0_only,
    get_current_user_auth0_only_without_consent,
    get_current_user_without_consent,
)
from core.config import get_settings
from core.rate_limiter import (
    AuthType,
    RateLimitExceededError,
    RateLimitResult,
    get_operation_type,
    rate_limiter,
)
from db.session import get_async_session
from models.user import User


async def check_rate_limit(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> RateLimitResult:
    """
    Dependency that enforces rate limits.

    Reads auth_type from request.state (set by auth dependency).
    Stores result in request.state for middleware to add headers.
    Raises RateLimitExceeded for 429 responses (handled by exception handler).
    """
    auth_type = getattr(request.state, "auth_type", AuthType.AUTH0)
    operation_type = get_operation_type(request.method, request.url.path)

    result = await rate_limiter.check(
        current_user.id, auth_type, operation_type,
    )

    if not result.allowed:
        raise RateLimitExceededError(result)

    # Store result in request.state for RateLimitHeadersMiddleware
    request.state.rate_limit_info = {
        "limit": result.limit,
        "remaining": result.remaining,
        "reset": result.reset,
    }

    return result


__all__ = [
    "check_rate_limit",
    "get_async_session",
    "get_current_user",
    "get_current_user_auth0_only",
    "get_current_user_auth0_only_without_consent",
    "get_current_user_without_consent",
    "get_settings",
]
