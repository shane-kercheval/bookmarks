"""FastAPI dependencies for injection."""
from fastapi import Depends

from core.auth import (
    get_current_user,
    get_current_user_ai,
    get_current_user_session_only,
)
from core.config import Settings, get_settings
from core.tier_limits import Tier, TierLimits, get_tier_limits, get_tier_safely
from db.session import get_async_session
from schemas.cached_user import CachedUser


def resolve_tier_limits(user_tier: str, *, dev_mode: bool) -> TierLimits:
    """
    Convert a user's tier string to TierLimits.

    Shared logic used by all get_current_limits* dependencies.
    In dev mode, always returns DEV tier limits regardless of stored tier.
    Defaults to FREE tier on unknown values to prevent 500 errors.
    """
    if dev_mode:
        return get_tier_limits(Tier.DEV)
    return get_tier_limits(get_tier_safely(user_tier))


def get_current_limits(
    current_user: CachedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> TierLimits:
    """Get tier limits for the current user (any auth method)."""
    return resolve_tier_limits(current_user.tier, dev_mode=settings.dev_mode)


def get_current_limits_session_only(
    current_user: CachedUser = Depends(get_current_user_session_only),
    settings: Settings = Depends(get_settings),
) -> TierLimits:
    """Get tier limits for the current user (session only — rejects PATs)."""
    return resolve_tier_limits(current_user.tier, dev_mode=settings.dev_mode)


def get_current_limits_ai(
    current_user: CachedUser = Depends(get_current_user_ai),
    settings: Settings = Depends(get_settings),
) -> TierLimits:
    """Get tier limits for AI endpoints (no global rate limiting triggered)."""
    return resolve_tier_limits(current_user.tier, dev_mode=settings.dev_mode)


__all__ = [
    "get_async_session",
    "get_current_limits",
    "get_current_limits_ai",
    "get_current_limits_session_only",
    "get_current_user",
    "get_current_user_ai",
    "get_current_user_session_only",
    "get_settings",
    "resolve_tier_limits",
]
