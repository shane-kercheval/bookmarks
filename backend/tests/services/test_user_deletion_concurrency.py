"""
Concurrency tests for account deletion vs authentication (M8 review round).

These use `concurrent_session_factory` — fully independent connections and
REAL commits — because the races under test are cross-transaction by nature;
the shared-savepoint `db_session` fixture cannot express them. Each test
reproduces one exact interleaving deterministically by injecting the
deletion at the vulnerable instant via a patch, rather than hoping a sleep
lands in the window.

Cleanup: committed rows (users, deleted_identities) are removed in finally
blocks; Redis is flushed by the redis_client fixture teardown.
"""
from collections.abc import AsyncGenerator, Callable, Coroutine

import pytest
from fastapi import HTTPException
from sqlalchemy import delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.auth import get_or_create_user
from core.auth_cache import AuthCache, get_auth_cache
from models.deleted_identity import DeletedIdentity
from models.user import User
from services import user_service


@pytest.fixture
async def cleanup_identities(
    concurrent_session_factory: async_sessionmaker,
) -> AsyncGenerator[list[str]]:
    """Register identifiers here; rows are removed after the test, committed."""
    identifiers: list[str] = []
    yield identifiers
    async with concurrent_session_factory() as session:
        await session.execute(
            sa_delete(DeletedIdentity).where(
                DeletedIdentity.external_auth_id.in_(identifiers),
            ),
        )
        await session.execute(
            sa_delete(User).where(User.external_auth_id.in_(identifiers)),
        )
        await session.commit()


async def _run_deletion_with_route_semantics(
    factory: async_sessionmaker,
    external_auth_id: str,
) -> None:
    """Run a deletion exactly as the webhook route does: commit, THEN invalidate."""
    async with factory() as session:
        result = await user_service.delete_user_by_external_auth_id(
            session, external_auth_id,
        )
        await session.commit()
    auth_cache = get_auth_cache()
    if auth_cache and result.deleted:
        await auth_cache.invalidate(
            result.user_id,
            external_auth_id=result.external_auth_id,
        )


async def test__deletion_commits_between_db_read_and_cache_write__no_stale_entry(
    concurrent_session_factory: async_sessionmaker,
    redis_client: object,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
    cleanup_identities: list[str],
) -> None:
    """
    The late-cache-write ordering (review round, reviewer-3's exact sequence).

    1. Authentication misses Redis and reads the existing user row.
    2. The deletion commits and invalidates Redis.
    3. Authentication writes its (now stale) user into Redis.

    The post-population tombstone recheck must catch step 3: the request gets
    the deleted-account 401 and the stale entry does not survive.
    """
    sub = "user_race_late_cache_write"
    cleanup_identities.append(sub)
    async with concurrent_session_factory() as session:
        session.add(User(external_auth_id=sub, email="race1@test.com"))
        await session.commit()

    real_set = AuthCache.set
    fired = False

    async def set_with_deletion_in_the_gap(self: AuthCache, user: User) -> None:
        """The instant between the DB read and the cache write: deletion lands."""
        nonlocal fired
        if not fired and user.external_auth_id == sub:
            fired = True
            await _run_deletion_with_route_semantics(
                concurrent_session_factory, sub,
            )
        await real_set(self, user)

    monkeypatch.setattr(AuthCache, "set", set_with_deletion_in_the_gap)

    async with concurrent_session_factory() as auth_session:
        with pytest.raises(HTTPException) as exc_info:
            await get_or_create_user(auth_session, external_auth_id=sub)

    assert fired, "the injected deletion never ran — the test lost its premise"
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "This account was deleted"
    assert exc_info.value.error_code == "account_deleted"
    auth_cache = get_auth_cache()
    assert auth_cache is not None
    assert await auth_cache.get_by_external_auth_id(sub) is None


async def test__jit_create_racing_unknown_identity_deletion__no_user_row(
    concurrent_session_factory: async_sessionmaker,
    redis_client: object,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
    cleanup_identities: list[str],
) -> None:
    """
    The unknown-identity race (review round): a user.deleted webhook for an
    identity we never provisioned, interleaved with that identity's first-ever
    API request. Without the identity lock + re-read, both existence checks
    pass and both a tombstone AND a fresh user row commit. Here the deletion
    is injected after JIT's initial user SELECT (found nothing) at the moment
    it reaches for the lock — the lock-then-recheck must see the committed
    tombstone and reject, leaving no user row.
    """
    sub = "user_race_jit_vs_deletion"
    cleanup_identities.append(sub)

    real_lock: Callable[..., Coroutine] = user_service.acquire_identity_lock
    fired = False

    async def lock_with_deletion_first(
        db: AsyncSession, provider: str, identifier: str,
    ) -> None:
        nonlocal fired
        if not fired and identifier == sub:
            fired = True
            # The webhook wins the race: tombstone committed before JIT locks
            await _run_deletion_with_route_semantics(
                concurrent_session_factory, sub,
            )
        await real_lock(db, provider, identifier)

    monkeypatch.setattr(
        user_service, "acquire_identity_lock", lock_with_deletion_first,
    )

    async with concurrent_session_factory() as auth_session:
        with pytest.raises(HTTPException) as exc_info:
            await get_or_create_user(
                auth_session, external_auth_id=sub, email="race2@test.com",
            )

    assert fired
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "This account was deleted"
    assert exc_info.value.error_code == "account_deleted"

    async with concurrent_session_factory() as check:
        from sqlalchemy import select  # noqa: PLC0415
        users = (await check.execute(
            select(User).where(User.external_auth_id == sub),
        )).scalars().all()
        tombstones = (await check.execute(
            select(DeletedIdentity).where(
                DeletedIdentity.external_auth_id == sub,
            ),
        )).scalars().all()
    assert users == [], "user row and tombstone coexist — the race is open"
    assert len(tombstones) == 1


async def test__deletion_blocks_behind_in_flight_creation_lock(
    concurrent_session_factory: async_sessionmaker,
    redis_client: object,  # noqa: ARG001
    cleanup_identities: list[str],
) -> None:
    """
    The serialization property itself: while a transaction holds the identity
    lock (as JIT creation does for the duration of its request transaction),
    a deletion for the same identity cannot proceed — it blocks on the lock
    instead of interleaving. Released at commit, after which the deletion
    completes normally.
    """
    import asyncio  # noqa: PLC0415

    sub = "user_race_lock_blocks"
    cleanup_identities.append(sub)

    async def attempt_deletion() -> None:
        async with concurrent_session_factory() as session:
            await user_service.delete_user_by_external_auth_id(session, sub)
            await session.commit()

    task: asyncio.Task | None = None
    try:
        async with concurrent_session_factory() as holder:
            # Stand in for an in-flight JIT creation: lock held, txn open
            await user_service.acquire_identity_lock(holder, "clerk", sub)

            task = asyncio.create_task(attempt_deletion())
            # Give the deletion real time to reach (and block on) the lock
            await asyncio.sleep(0.5)
            assert not task.done(), (
                "deletion completed while the identity lock was held — "
                "the serialization property is broken"
            )

            await holder.commit()  # releases the xact-scoped lock

        # With the lock released, the owned task must complete normally
        await asyncio.wait_for(task, timeout=10.0)
    finally:
        if task is not None and not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    async with concurrent_session_factory() as check:
        from sqlalchemy import select  # noqa: PLC0415
        tombstones = (await check.execute(
            select(DeletedIdentity).where(
                DeletedIdentity.external_auth_id == sub,
            ),
        )).scalars().all()
    assert len(tombstones) == 1
