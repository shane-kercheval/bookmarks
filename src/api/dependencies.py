"""FastAPI dependencies for injection."""
from core.auth import get_current_user
from core.config import get_settings
from db.session import get_async_session

__all__ = ["get_async_session", "get_current_user", "get_settings"]
