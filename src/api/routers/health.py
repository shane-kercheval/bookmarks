"""Health check endpoints."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_async_session


router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    database: str


@router.get("/health", response_model=HealthResponse)
async def health_check(
    db: AsyncSession = Depends(get_async_session),
) -> HealthResponse:
    """Check application and database health."""
    db_status = "healthy"
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_status = "unhealthy"

    return HealthResponse(
        status="healthy" if db_status == "healthy" else "degraded",
        database=db_status,
    )
