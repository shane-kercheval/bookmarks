"""Tests for race condition handling in user creation."""
from unittest.mock import patch

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


@pytest.fixture
async def independent_session_factory(
    async_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """
    Create a session factory for independent sessions.

    Unlike db_session fixture, these sessions are NOT bound to a shared transaction,
    allowing us to test true concurrent behavior with separate transactions.
    """
    return async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def test__get_or_create_user__handles_integrity_error_from_race_condition(
    independent_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """
    Test that get_or_create_user handles IntegrityError from a race condition.

    This deterministically simulates the race condition by:
    1. Creating a user in one session (simulating another request that won the race)
    2. Calling get_or_create_user in another session where we patch the SELECT
       to return None (simulating stale read due to race condition)
    3. When it tries to INSERT, it gets IntegrityError from unique constraint
    4. The function should recover by fetching the existing user

    This is the exact scenario that happens in production when multiple
    API requests arrive simultaneously for a new user.
    """
    # Import here to avoid module-level import before DATABASE_URL is set by fixtures
    from core.auth import get_or_create_user
    from models.user import User

    auth0_id = "test|race-condition-integrity-error"
    email = "race@test.com"

    # Step 1: Create the user directly (simulating another concurrent request winning)
    async with independent_session_factory() as session:
        user_from_other_request = User(auth0_id=auth0_id, email=email)
        session.add(user_from_other_request)
        await session.commit()
        existing_user_id = user_from_other_request.id

    # Step 2: Call get_or_create_user in a new session where we simulate the race
    # by patching the SELECT to return None, then letting the real INSERT fail
    async with independent_session_factory() as session:
        original_execute = session.execute
        select_call_count = 0

        async def mock_execute_for_race(
            stmt: object,
            *args: object,
            **kwargs: object,
        ) -> object:
            """
            Mock that returns None for the first SELECT (simulating race condition),
            but uses real execute for subsequent calls (including the retry SELECT).
            """
            nonlocal select_call_count

            # Check if this is a SELECT on users table
            stmt_str = str(stmt)
            if 'users' in stmt_str.lower() and 'select' in stmt_str.lower():
                select_call_count += 1
                if select_call_count == 1:
                    # First SELECT: return None to simulate race condition
                    # (our transaction started before the other committed)
                    return await original_execute(
                        select(User).where(User.auth0_id == "nonexistent"),
                    )

            # All other queries use real execute
            return await original_execute(stmt, *args, **kwargs)

        with patch.object(session, 'execute', side_effect=mock_execute_for_race):
            # This should NOT raise - it should handle the IntegrityError
            # and return the existing user
            try:
                user = await get_or_create_user(session, auth0_id, email)
                # If we get here, the fix is in place - verify it returned the right user
                assert user.id == existing_user_id, (
                    f"Expected user ID {existing_user_id}, got {user.id}"
                )
            except IntegrityError:
                # Current behavior (bug): IntegrityError propagates to caller
                pytest.fail(
                    "get_or_create_user raised IntegrityError instead of "
                    "handling the race condition gracefully. "
                    "The function should catch IntegrityError and retry the SELECT.",
                )

    # Cleanup
    async with independent_session_factory() as session:
        await session.execute(
            text("DELETE FROM users WHERE auth0_id = :auth0_id"),
            {"auth0_id": auth0_id},
        )
        await session.commit()


async def test__get_or_create_user__sequential_calls_work(
    independent_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """
    Test that sequential calls to get_or_create_user work correctly.

    First call creates the user, subsequent calls return the existing user.
    """
    # Import here to avoid module-level import before DATABASE_URL is set by fixtures
    from core.auth import get_or_create_user

    auth0_id = "test|sequential-user-creation"
    email = "sequential@test.com"

    # First call - creates user
    async with independent_session_factory() as session:
        user1 = await get_or_create_user(session, auth0_id, email)
        await session.commit()
        user1_id = user1.id

    # Second call - returns existing user
    async with independent_session_factory() as session:
        user2 = await get_or_create_user(session, auth0_id, email)
        await session.commit()
        user2_id = user2.id

    assert user1_id == user2_id, "Both calls should return the same user"

    # Cleanup
    async with independent_session_factory() as session:
        await session.execute(text("DELETE FROM users WHERE auth0_id = :auth0_id"), {"auth0_id": auth0_id})
        await session.commit()
