"""Health check endpoints."""
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.redis import get_redis_client
from db.session import get_async_session


logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    database: str
    redis: str


async def check_redis_health() -> str:
    """Check Redis connectivity. Returns 'connected' or 'unavailable'."""
    redis_client = get_redis_client()
    if redis_client is None:
        return "unavailable"
    try:
        if await redis_client.ping():
            return "connected"
        return "unavailable"
    except Exception:
        return "unavailable"


@router.get("/health", response_model=HealthResponse)
async def health_check(
    db: AsyncSession = Depends(get_async_session),
) -> HealthResponse:
    """
    Check application and database health.

    Note: App returns 'healthy' even if Redis is unavailable (degraded mode).
    Redis unavailability means no rate limiting, but app is fully functional.
    """
    db_status = "healthy"
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Database health check failed")
        db_status = "unhealthy"

    redis_status = await check_redis_health()

    # App is healthy if DB is healthy (Redis unavailability = degraded, not unhealthy)
    return HealthResponse(
        status="healthy" if db_status == "healthy" else "degraded",
        database=db_status,
        redis=redis_status,
    )
