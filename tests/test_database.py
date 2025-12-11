"""Tests for database connection and session."""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def test_database_connection(db_session: AsyncSession) -> None:
    """Test that we can connect to the database."""
    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar() == 1


async def test_database_session_is_async(db_session: AsyncSession) -> None:
    """Test that the session is an async session."""
    assert isinstance(db_session, AsyncSession)
