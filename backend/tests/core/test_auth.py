"""
Tests for auth module, focusing on null email handling and edge cases.

Email is nullable by design (some Auth0 providers don't include it).
These tests verify the null email path works correctly.

Note: Imports from core.auth are done inside test methods to avoid triggering
Settings validation during test collection (before DATABASE_URL is set by fixtures).
"""
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth_cache import CACHE_SCHEMA_VERSION, get_auth_cache
from core.redis import RedisClient
from models.user import User


class TestGetOrCreateUserNullEmail:
    """Tests for get_or_create_user with null email."""

    async def test__get_or_create_user__creates_user_without_email(
        self,
        db_session: AsyncSession,
        redis_client: RedisClient,  # noqa: ARG002
    ) -> None:
        """User can be created with email=None."""
        from core.auth import get_or_create_user  # needs to be imported inside test for setting up environment variables

        auth0_id = "auth0|null-email-test-1"

        user = await get_or_create_user(db_session, auth0_id=auth0_id)
        await db_session.commit()

        assert user is not None
        assert user.auth0_id == auth0_id
        assert user.email is None

    async def test__get_or_create_user__returns_existing_user_without_email(
        self,
        db_session: AsyncSession,
        redis_client: RedisClient,  # noqa: ARG002
    ) -> None:
        """Existing user with null email can be retrieved."""
        from core.auth import get_or_create_user  # needs to be imported inside test for setting up environment variables

        auth0_id = "auth0|null-email-test-2"

        # Create user without email
        user1 = await get_or_create_user(db_session, auth0_id=auth0_id)
        await db_session.commit()
        user1_id = user1.id

        # Clear cache to force DB lookup
        auth_cache = get_auth_cache()
        if auth_cache:
            await auth_cache.invalidate(user1.id, auth0_id)

        # Get same user again
        user2 = await get_or_create_user(db_session, auth0_id=auth0_id)

        assert user2.id == user1_id
        assert user2.email is None

    async def test__get_or_create_user__updates_email_from_null_to_value(
        self,
        db_session: AsyncSession,
        redis_client: RedisClient,  # noqa: ARG002
    ) -> None:
        """User's email can be updated from null to a value."""
        from core.auth import get_or_create_user  # needs to be imported inside test for setting up environment variables

        auth0_id = "auth0|null-email-test-3"

        # Create user without email
        user1 = await get_or_create_user(db_session, auth0_id=auth0_id)
        await db_session.commit()
        assert user1.email is None

        # Clear cache
        auth_cache = get_auth_cache()
        if auth_cache:
            await auth_cache.invalidate(user1.id, auth0_id)

        # Get user with email now provided
        user2 = await get_or_create_user(
            db_session, auth0_id=auth0_id, email="newemail@test.com",
        )
        await db_session.commit()

        assert user2.id == user1.id
        assert user2.email == "newemail@test.com"

    async def test__get_or_create_user__null_email_does_not_overwrite_existing(
        self,
        db_session: AsyncSession,
        redis_client: RedisClient,  # noqa: ARG002
    ) -> None:
        """Passing email=None does not overwrite existing email."""
        from core.auth import get_or_create_user  # needs to be imported inside test for setting up environment variables

        auth0_id = "auth0|null-email-test-4"

        # Create user with email
        user1 = await get_or_create_user(
            db_session, auth0_id=auth0_id, email="existing@test.com",
        )
        await db_session.commit()
        assert user1.email == "existing@test.com"

        # Clear cache
        auth_cache = get_auth_cache()
        if auth_cache:
            await auth_cache.invalidate(user1.id, auth0_id)

        # Get user with email=None (simulating JWT without email claim)
        user2 = await get_or_create_user(db_session, auth0_id=auth0_id, email=None)

        # Email should NOT be overwritten to None
        assert user2.id == user1.id
        assert user2.email == "existing@test.com"


class TestAuthCacheNullEmail:
    """Tests for auth cache with null email users."""

    async def test__auth_cache__stores_null_email(
        self,
        db_session: AsyncSession,
        redis_client: RedisClient,
    ) -> None:
        """Cache correctly stores user with null email."""
        from core.auth import get_or_create_user  # needs to be imported inside test for setting up environment variables

        auth0_id = "auth0|cache-null-email-1"

        # Create user without email
        await get_or_create_user(db_session, auth0_id=auth0_id)
        await db_session.commit()

        # Get cached data
        auth0_key = f"auth:v{CACHE_SCHEMA_VERSION}:user:auth0:{auth0_id}"
        cached_bytes = await redis_client.get(auth0_key)

        assert cached_bytes is not None
        cached = json.loads(cached_bytes)
        assert cached["email"] is None

    async def test__auth_cache__retrieves_null_email_user(
        self,
        db_session: AsyncSession,
        redis_client: RedisClient,  # noqa: ARG002
    ) -> None:
        """Cached user with null email can be retrieved."""
        from core.auth import get_or_create_user  # needs to be imported inside test for setting up environment variables

        auth0_id = "auth0|cache-null-email-2"

        # Create user without email (populates cache)
        user1 = await get_or_create_user(db_session, auth0_id=auth0_id)
        await db_session.commit()

        # Get from cache
        auth_cache = get_auth_cache()
        cached_user = await auth_cache.get_by_auth0_id(auth0_id)

        assert cached_user is not None
        assert cached_user.id == user1.id
        assert cached_user.email is None

    async def test__auth_cache__cache_hit_with_null_email(
        self,
        db_session: AsyncSession,
        redis_client: RedisClient,  # noqa: ARG002
    ) -> None:
        """Second request for null-email user uses cache."""
        from core.auth import get_or_create_user  # needs to be imported inside test for setting up environment variables
        from schemas.cached_user import CachedUser

        auth0_id = "auth0|cache-null-email-3"

        # First request creates user and populates cache
        await get_or_create_user(db_session, auth0_id=auth0_id)
        await db_session.commit()

        # Second request should return CachedUser (not User ORM)
        result = await get_or_create_user(db_session, auth0_id=auth0_id)

        # Should be CachedUser on cache hit
        assert isinstance(result, CachedUser)
        assert result.email is None


class TestEmailMismatchCacheFallthrough:
    """Tests for email mismatch triggering cache fallthrough."""

    async def test__get_or_create_user__email_mismatch_falls_through_to_db(
        self,
        db_session: AsyncSession,
        redis_client: RedisClient,
    ) -> None:
        """
        When cached email differs from provided email, falls through to DB.

        This handles the case where Auth0 updates the user's email.
        """
        from core.auth import get_or_create_user  # needs to be imported inside test for setting up environment variables

        auth0_id = "auth0|email-mismatch-test"

        # Create user with old email (populates cache)
        user1 = await get_or_create_user(
            db_session, auth0_id=auth0_id, email="old@test.com",
        )
        await db_session.commit()

        # Verify cache has old email
        auth0_key = f"auth:v{CACHE_SCHEMA_VERSION}:user:auth0:{auth0_id}"
        cached_bytes = await redis_client.get(auth0_key)
        cached = json.loads(cached_bytes)
        assert cached["email"] == "old@test.com"

        # Now request with new email - should fall through to DB and update
        user2 = await get_or_create_user(
            db_session, auth0_id=auth0_id, email="new@test.com",
        )
        await db_session.commit()

        # Should have updated email
        assert user2.id == user1.id
        assert user2.email == "new@test.com"

        # Cache should be repopulated with new email
        cached_bytes = await redis_client.get(auth0_key)
        cached = json.loads(cached_bytes)
        assert cached["email"] == "new@test.com"

    async def test__get_or_create_user__null_to_email_triggers_db_update(
        self,
        db_session: AsyncSession,
        redis_client: RedisClient,
    ) -> None:
        """When cache has null email and request has email, updates via DB."""
        from core.auth import get_or_create_user  # needs to be imported inside test for setting up environment variables

        auth0_id = "auth0|null-to-email-test"

        # Create user without email (populates cache with null email)
        await get_or_create_user(db_session, auth0_id=auth0_id)
        await db_session.commit()

        # Verify cache has null email
        auth0_key = f"auth:v{CACHE_SCHEMA_VERSION}:user:auth0:{auth0_id}"
        cached_bytes = await redis_client.get(auth0_key)
        cached = json.loads(cached_bytes)
        assert cached["email"] is None

        # Request with email - should fall through and update
        user2 = await get_or_create_user(
            db_session, auth0_id=auth0_id, email="added@test.com",
        )
        await db_session.commit()

        assert user2.email == "added@test.com"

        # Verify DB was updated
        result = await db_session.execute(
            select(User).where(User.auth0_id == auth0_id),
        )
        db_user = result.scalar_one()
        assert db_user.email == "added@test.com"
