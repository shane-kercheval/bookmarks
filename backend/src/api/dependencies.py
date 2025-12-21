"""FastAPI dependencies for injection."""
from core.auth import (
    get_current_user,
    get_current_user_auth0_only,
    get_current_user_auth0_only_without_consent,
    get_current_user_without_consent,
)
from core.config import get_settings
from db.session import get_async_session

__all__ = [
    "get_async_session",
    "get_current_user",
    "get_current_user_auth0_only",
    "get_current_user_auth0_only_without_consent",
    "get_current_user_without_consent",
    "get_settings",
]
