"""
Tests for auth module, focusing on null email handling and edge cases.

Email is nullable by design (OAuth access tokens carry no email claim).
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
from schemas.cached_user import CachedUser


async def _prime_cache(db: AsyncSession, **identity: object) -> None:
    """
    Resolve a committed user once so its row lands in the auth cache.

    A freshly-created user is deliberately NOT cached — its row is only flushed
    and the request can still roll back (see get_or_create_user's phantom-cache
    guard). The cache is populated on the first *post-commit* read. Tests that
    assert cache state right after creating a user call this to perform that
    read (pass the same identity + email so it's a plain cache-populating
    lookup, not an email-change fallthrough).
    """
    from core.auth import get_or_create_user  # noqa: PLC0415

    await get_or_create_user(db, **identity)


class TestGetOrCreateUserNullEmail:
    """Tests for get_or_create_user with null email."""

    async def test__get_or_create_user__creates_user_without_email(
        self,
        db_session: AsyncSession,
        redis_client: RedisClient,  # noqa: ARG002
    ) -> None:
        """User can be created with email=None."""
        from core.auth import get_or_create_user  # noqa: PLC0415

        external_auth_id = "auth0|null-email-test-1"

        user = await get_or_create_user(db_session, external_auth_id=external_auth_id)
        await db_session.commit()

        assert user is not None
        assert user.external_auth_id == external_auth_id
        assert user.email is None

    async def test__get_or_create_user__returns_existing_user_without_email(
        self,
        db_session: AsyncSession,
        redis_client: RedisClient,  # noqa: ARG002
    ) -> None:
        """Existing user with null email can be retrieved."""
        from core.auth import get_or_create_user  # noqa: PLC0415

        external_auth_id = "auth0|null-email-test-2"

        # Create user without email
        user1 = await get_or_create_user(db_session, external_auth_id=external_auth_id)
        await db_session.commit()
        user1_id = user1.id

        # Clear cache to force DB lookup
        auth_cache = get_auth_cache()
        if auth_cache:
            await auth_cache.invalidate(user1.id, external_auth_id)

        # Get same user again
        user2 = await get_or_create_user(db_session, external_auth_id=external_auth_id)

        assert user2.id == user1_id
        assert user2.email is None

    async def test__get_or_create_user__updates_email_from_null_to_value(
        self,
        db_session: AsyncSession,
        redis_client: RedisClient,  # noqa: ARG002
    ) -> None:
        """User's email can be updated from null to a value."""
        from core.auth import get_or_create_user  # noqa: PLC0415

        external_auth_id = "auth0|null-email-test-3"

        # Create user without email
        user1 = await get_or_create_user(db_session, external_auth_id=external_auth_id)
        await db_session.commit()
        assert user1.email is None

        # Clear cache
        auth_cache = get_auth_cache()
        if auth_cache:
            await auth_cache.invalidate(user1.id, external_auth_id)

        # Get user with email now provided
        user2 = await get_or_create_user(
            db_session, external_auth_id=external_auth_id, email="newemail@test.com",
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
        from core.auth import get_or_create_user  # noqa: PLC0415

        external_auth_id = "auth0|null-email-test-4"

        # Create user with email
        user1 = await get_or_create_user(
            db_session, external_auth_id=external_auth_id, email="existing@test.com",
        )
        await db_session.commit()
        assert user1.email == "existing@test.com"

        # Clear cache
        auth_cache = get_auth_cache()
        if auth_cache:
            await auth_cache.invalidate(user1.id, external_auth_id)

        # Get user with email=None (simulating JWT without email claim)
        user2 = await get_or_create_user(db_session, external_auth_id=external_auth_id, email=None)

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
        from core.auth import get_or_create_user  # noqa: PLC0415

        external_auth_id = "auth0|cache-null-email-1"

        # Create user without email
        await get_or_create_user(db_session, external_auth_id=external_auth_id)
        await db_session.commit()
        await _prime_cache(db_session, external_auth_id=external_auth_id)  # post-commit read caches

        # Get cached data
        ext_key = f"auth:v{CACHE_SCHEMA_VERSION}:user:ext:{external_auth_id}"
        cached_bytes = await redis_client.get(ext_key)

        assert cached_bytes is not None
        cached = json.loads(cached_bytes)
        assert cached["email"] is None

    async def test__auth_cache__retrieves_null_email_user(
        self,
        db_session: AsyncSession,
        redis_client: RedisClient,  # noqa: ARG002
    ) -> None:
        """Cached user with null email can be retrieved."""
        from core.auth import get_or_create_user  # noqa: PLC0415

        external_auth_id = "auth0|cache-null-email-2"

        # Create user without email, then a post-commit read populates cache
        user1 = await get_or_create_user(db_session, external_auth_id=external_auth_id)
        await db_session.commit()
        await _prime_cache(db_session, external_auth_id=external_auth_id)

        # Get from cache
        auth_cache = get_auth_cache()
        cached_user = await auth_cache.get_by_external_auth_id(external_auth_id)

        assert cached_user is not None
        assert cached_user.id == user1.id
        assert cached_user.email is None

    async def test__auth_cache__cache_hit_with_null_email(
        self,
        db_session: AsyncSession,
        redis_client: RedisClient,  # noqa: ARG002
    ) -> None:
        """Second request for null-email user uses cache."""
        from core.auth import get_or_create_user  # noqa: PLC0415

        external_auth_id = "auth0|cache-null-email-3"

        # First request creates the user; a post-commit read then caches it
        await get_or_create_user(db_session, external_auth_id=external_auth_id)
        await db_session.commit()
        await _prime_cache(db_session, external_auth_id=external_auth_id)

        # Next request should return CachedUser (not User ORM)
        result = await get_or_create_user(db_session, external_auth_id=external_auth_id)

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

        This handles the case where the IdP updates the user's email.
        """
        from core.auth import get_or_create_user  # noqa: PLC0415

        external_auth_id = "auth0|email-mismatch-test"

        # Create user with old email, then a post-commit read caches it
        user1 = await get_or_create_user(
            db_session, external_auth_id=external_auth_id, email="old@test.com",
        )
        await db_session.commit()
        await _prime_cache(db_session, external_auth_id=external_auth_id, email="old@test.com")

        # Verify cache has old email
        ext_key = f"auth:v{CACHE_SCHEMA_VERSION}:user:ext:{external_auth_id}"
        cached_bytes = await redis_client.get(ext_key)
        cached = json.loads(cached_bytes)
        assert cached["email"] == "old@test.com"

        # Now request with new email - should fall through to DB and update
        user2 = await get_or_create_user(
            db_session, external_auth_id=external_auth_id, email="new@test.com",
        )
        await db_session.commit()

        # Should have updated email
        assert user2.id == user1.id
        assert user2.email == "new@test.com"

        # Cache should be repopulated with new email
        cached_bytes = await redis_client.get(ext_key)
        cached = json.loads(cached_bytes)
        assert cached["email"] == "new@test.com"

    async def test__get_or_create_user__null_to_email_triggers_db_update(
        self,
        db_session: AsyncSession,
        redis_client: RedisClient,
    ) -> None:
        """When cache has null email and request has email, updates via DB."""
        from core.auth import get_or_create_user  # noqa: PLC0415

        external_auth_id = "auth0|null-to-email-test"

        # Create user without email, then a post-commit read caches null email
        await get_or_create_user(db_session, external_auth_id=external_auth_id)
        await db_session.commit()
        await _prime_cache(db_session, external_auth_id=external_auth_id)

        # Verify cache has null email
        ext_key = f"auth:v{CACHE_SCHEMA_VERSION}:user:ext:{external_auth_id}"
        cached_bytes = await redis_client.get(ext_key)
        cached = json.loads(cached_bytes)
        assert cached["email"] is None

        # Request with email - should fall through and update
        user2 = await get_or_create_user(
            db_session, external_auth_id=external_auth_id, email="added@test.com",
        )
        await db_session.commit()

        assert user2.email == "added@test.com"

        # Verify DB was updated
        result = await db_session.execute(
            select(User).where(User.external_auth_id == external_auth_id),
        )
        db_user = result.scalar_one()
        assert db_user.email == "added@test.com"


class TestGetOrCreateUserEmailVerified:
    """Tests for get_or_create_user with email_verified."""

    async def test__creates_user_with_email_verified_true(
        self,
        db_session: AsyncSession,
        redis_client: RedisClient,  # noqa: ARG002
    ) -> None:
        """User can be created with email_verified=True."""
        from core.auth import get_or_create_user  # noqa: PLC0415

        external_auth_id = "auth0|ev-test-1"
        user = await get_or_create_user(
            db_session, external_auth_id=external_auth_id, email="ev@test.com", email_verified=True,
        )
        await db_session.commit()

        assert user.email_verified is True

    async def test__creates_user_with_email_verified_none(
        self,
        db_session: AsyncSession,
        redis_client: RedisClient,  # noqa: ARG002
    ) -> None:
        """User created without email_verified has None."""
        from core.auth import get_or_create_user  # noqa: PLC0415

        external_auth_id = "auth0|ev-test-2"
        user = await get_or_create_user(db_session, external_auth_id=external_auth_id)
        await db_session.commit()

        assert user.email_verified is None

    async def test__updates_email_verified_from_none_to_true(
        self,
        db_session: AsyncSession,
        redis_client: RedisClient,  # noqa: ARG002
    ) -> None:
        """email_verified can be updated from None to True on subsequent login."""
        from core.auth import get_or_create_user  # noqa: PLC0415

        external_auth_id = "auth0|ev-test-3"
        user1 = await get_or_create_user(db_session, external_auth_id=external_auth_id, email="ev@test.com")
        await db_session.commit()
        assert user1.email_verified is None

        auth_cache = get_auth_cache()
        if auth_cache:
            await auth_cache.invalidate(user1.id, external_auth_id)

        user2 = await get_or_create_user(
            db_session, external_auth_id=external_auth_id, email="ev@test.com", email_verified=True,
        )
        await db_session.commit()

        assert user2.id == user1.id
        assert user2.email_verified is True

    async def test__updates_email_verified_from_false_to_true(
        self,
        db_session: AsyncSession,
        redis_client: RedisClient,  # noqa: ARG002
    ) -> None:
        """email_verified can be updated from False to True."""
        from core.auth import get_or_create_user  # noqa: PLC0415

        external_auth_id = "auth0|ev-test-4"
        user1 = await get_or_create_user(
            db_session, external_auth_id=external_auth_id, email="ev@test.com", email_verified=False,
        )
        await db_session.commit()
        assert user1.email_verified is False

        auth_cache = get_auth_cache()
        if auth_cache:
            await auth_cache.invalidate(user1.id, external_auth_id)

        user2 = await get_or_create_user(
            db_session, external_auth_id=external_auth_id, email="ev@test.com", email_verified=True,
        )
        await db_session.commit()

        assert user2.id == user1.id
        assert user2.email_verified is True

    async def test__email_verified_not_overwritten_with_none(
        self,
        db_session: AsyncSession,
        redis_client: RedisClient,  # noqa: ARG002
    ) -> None:
        """email_verified is NOT overwritten with None when claim is missing."""
        from core.auth import get_or_create_user  # noqa: PLC0415

        external_auth_id = "auth0|ev-test-5"
        user1 = await get_or_create_user(
            db_session, external_auth_id=external_auth_id, email="ev@test.com", email_verified=True,
        )
        await db_session.commit()

        auth_cache = get_auth_cache()
        if auth_cache:
            await auth_cache.invalidate(user1.id, external_auth_id)

        user2 = await get_or_create_user(
            db_session, external_auth_id=external_auth_id, email="ev@test.com", email_verified=None,
        )

        assert user2.id == user1.id
        assert user2.email_verified is True

    async def test__email_and_email_verified_updated_together(
        self,
        db_session: AsyncSession,
        redis_client: RedisClient,  # noqa: ARG002
    ) -> None:
        """Email and email_verified are updated together when email changes."""
        from core.auth import get_or_create_user  # noqa: PLC0415

        external_auth_id = "auth0|ev-test-6"
        user1 = await get_or_create_user(
            db_session, external_auth_id=external_auth_id, email="old@test.com", email_verified=False,
        )
        await db_session.commit()

        auth_cache = get_auth_cache()
        if auth_cache:
            await auth_cache.invalidate(user1.id, external_auth_id)

        user2 = await get_or_create_user(
            db_session, external_auth_id=external_auth_id, email="new@test.com", email_verified=True,
        )
        await db_session.commit()

        assert user2.id == user1.id
        assert user2.email == "new@test.com"
        assert user2.email_verified is True

    async def test__email_verified_stale_on_cache_hit(
        self,
        db_session: AsyncSession,
        redis_client: RedisClient,  # noqa: ARG002
    ) -> None:
        """
        email_verified is NOT updated on cache hit (by design).

        email_verified is informational and not used for access control,
        so staleness up to cache TTL (5 min) is acceptable. This test
        documents that intentional behavior.
        """
        from core.auth import get_or_create_user  # noqa: PLC0415

        external_auth_id = "auth0|ev-test-stale"

        # Create user with email_verified=False, then a post-commit read caches
        user1 = await get_or_create_user(
            db_session, external_auth_id=external_auth_id, email="ev@test.com", email_verified=False,
        )
        await db_session.commit()
        assert user1.email_verified is False
        await _prime_cache(
            db_session, external_auth_id=external_auth_id, email="ev@test.com", email_verified=False,
        )

        # Second call with email_verified=True but same email — cache hit
        result = await get_or_create_user(
            db_session, external_auth_id=external_auth_id, email="ev@test.com", email_verified=True,
        )

        # Returns cached user with stale email_verified
        assert isinstance(result, CachedUser)
        assert result.email_verified is False
