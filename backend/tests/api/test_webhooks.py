"""
Tests for the Clerk webhook endpoint (POST /webhooks/clerk).

The signature tests sign requests with the real svix library against a test
secret — the endpoint's verification is exercised for real, not mocked. The
settings override injects the secret; the plain `client` fixture (no secret
configured) exercises the fail-closed path.
"""
import base64
import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from svix.webhooks import Webhook

from core.config import get_settings
from core.tier_limits import Tier
from models.bookmark import Bookmark
from models.deleted_identity import DeletedIdentity
from models.user import User

# Runtime-constructed fake (format: "whsec_" + base64, per Svix docs) so
# secret scanners don't flag a literal — this is NOT a real secret.
TEST_WEBHOOK_SECRET = "whsec_" + base64.b64encode(
    b"tiddly-test-signing-secret-not-real",
).decode()


def signed_headers(
    payload: str,
    *,
    secret: str = TEST_WEBHOOK_SECRET,
    msg_id: str = "msg_test_delivery_1",
) -> dict[str, str]:
    """Build genuine svix signature headers for a payload."""
    timestamp = datetime.now(UTC)
    signature = Webhook(secret).sign(msg_id, timestamp, payload)
    return {
        "svix-id": msg_id,
        "svix-timestamp": str(int(timestamp.timestamp())),
        "svix-signature": signature,
        "content-type": "application/json",
    }


def deletion_event(clerk_user_id: str) -> str:
    """A user.deleted payload shaped like Clerk's (data is a deleted object)."""
    return json.dumps({
        "data": {"deleted": True, "id": clerk_user_id, "object": "user"},
        "object": "event",
        "type": "user.deleted",
    })


@pytest.fixture
async def webhook_client(client: AsyncClient) -> AsyncGenerator[AsyncClient]:
    """The standard test client with the webhook signing secret configured."""
    from api.main import app  # noqa: PLC0415

    settings_with_secret = get_settings().model_copy(
        update={"clerk_webhook_signing_secret": TEST_WEBHOOK_SECRET},
    )
    app.dependency_overrides[get_settings] = lambda: settings_with_secret
    yield client
    app.dependency_overrides.pop(get_settings, None)


@pytest.fixture
async def clerk_user(db_session: AsyncSession) -> User:
    """A user provisioned via the Clerk path, with content."""
    user = User(
        external_auth_id="user_webhook_target",
        email="webhook-target@test.com",
        tier=Tier.FREE.value,
    )
    db_session.add(user)
    await db_session.flush()
    # Mark the consent relationship loaded (there is none) so AuthCache.set
    # and the cascade delete don't trigger an async lazy load.
    user.consent = None
    db_session.add(Bookmark(user_id=user.id, url="https://example.com/"))
    await db_session.flush()
    return user


async def _user_exists(db: AsyncSession, external_auth_id: str) -> bool:
    result = await db.execute(
        select(User).where(User.external_auth_id == external_auth_id),
    )
    return result.scalar_one_or_none() is not None


class TestSignatureVerification:
    """The endpoint verifies the Svix signature before doing anything."""

    async def test__unsigned_request__rejected_400(
        self,
        webhook_client: AsyncClient,
        db_session: AsyncSession,
        clerk_user: User,
    ) -> None:
        """A request with no svix headers is rejected and deletes nothing."""
        response = await webhook_client.post(
            "/webhooks/clerk",
            content=deletion_event(clerk_user.external_auth_id),
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 400
        assert await _user_exists(db_session, clerk_user.external_auth_id)

    async def test__wrong_secret__rejected_400(
        self,
        webhook_client: AsyncClient,
        db_session: AsyncSession,
        clerk_user: User,
    ) -> None:
        """A signature from the wrong secret is rejected."""
        payload = deletion_event(clerk_user.external_auth_id)
        headers = signed_headers(
            payload,
            secret="whsec_" + base64.b64encode(b"the-wrong-secret-000000").decode(),
        )
        response = await webhook_client.post(
            "/webhooks/clerk",
            content=payload,
            headers=headers,
        )
        assert response.status_code == 400
        assert await _user_exists(db_session, clerk_user.external_auth_id)

    async def test__tampered_body__rejected_400(
        self,
        webhook_client: AsyncClient,
        db_session: AsyncSession,
        clerk_user: User,
    ) -> None:
        """A validly-signed payload altered in transit fails verification."""
        payload = deletion_event("user_someone_else")
        headers = signed_headers(payload)
        tampered = deletion_event(clerk_user.external_auth_id)
        response = await webhook_client.post(
            "/webhooks/clerk",
            content=tampered,
            headers=headers,
        )
        assert response.status_code == 400
        assert await _user_exists(db_session, clerk_user.external_auth_id)

    async def test__no_secret_configured__fails_closed_503(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        clerk_user: User,
    ) -> None:
        """Without CLERK_WEBHOOK_SIGNING_SECRET the endpoint refuses everything."""
        from api.main import app  # noqa: PLC0415

        # Force an empty secret rather than relying on the ambient env — a
        # developer running the M8 manual drill sets a real secret in .env,
        # which the plain `client` fixture would otherwise pick up.
        settings_no_secret = get_settings().model_copy(
            update={"clerk_webhook_signing_secret": ""},
        )
        app.dependency_overrides[get_settings] = lambda: settings_no_secret
        try:
            payload = deletion_event(clerk_user.external_auth_id)
            response = await client.post(
                "/webhooks/clerk",
                content=payload,
                headers=signed_headers(payload),
            )
            assert response.status_code == 503
            assert await _user_exists(db_session, clerk_user.external_auth_id)
        finally:
            app.dependency_overrides.pop(get_settings, None)


class TestUserDeletedHandling:
    """Verified user.deleted events delete the user, idempotently."""

    async def test__user_deleted__removes_user_content_and_tombstones(
        self,
        webhook_client: AsyncClient,
        db_session: AsyncSession,
        clerk_user: User,
    ) -> None:
        """The full deletion path: user row, owned content, tombstone."""
        external_auth_id = clerk_user.external_auth_id
        user_id = clerk_user.id
        payload = deletion_event(external_auth_id)

        response = await webhook_client.post(
            "/webhooks/clerk",
            content=payload,
            headers=signed_headers(payload),
        )
        assert response.status_code == 200
        assert response.json()["deleted_user"] is True

        assert not await _user_exists(db_session, external_auth_id)
        bookmarks = await db_session.execute(
            select(Bookmark).where(Bookmark.user_id == user_id),
        )
        assert bookmarks.scalars().all() == []
        (await db_session.execute(
            select(DeletedIdentity).where(
                DeletedIdentity.external_auth_id == external_auth_id,
            ),
        )).scalar_one()

    async def test__replayed_delivery__idempotent_two_successes(
        self,
        webhook_client: AsyncClient,
        db_session: AsyncSession,
        clerk_user: User,
    ) -> None:
        """Svix delivery is at-least-once: the same event twice → two 200s."""
        external_auth_id = clerk_user.external_auth_id
        payload = deletion_event(external_auth_id)
        headers = signed_headers(payload)

        first = await webhook_client.post(
            "/webhooks/clerk", content=payload, headers=headers,
        )
        second = await webhook_client.post(
            "/webhooks/clerk", content=payload, headers=headers,
        )
        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["deleted_user"] is False

        tombstones = (await db_session.execute(
            select(DeletedIdentity).where(
                DeletedIdentity.external_auth_id == external_auth_id,
            ),
        )).scalars().all()
        assert len(tombstones) == 1

    async def test__unknown_user__tombstoned_and_succeeds(
        self,
        webhook_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """A deletion for an identity we never provisioned still tombstones."""
        payload = deletion_event("user_never_seen")
        response = await webhook_client.post(
            "/webhooks/clerk",
            content=payload,
            headers=signed_headers(payload),
        )
        assert response.status_code == 200
        assert response.json()["deleted_user"] is False
        (await db_session.execute(
            select(DeletedIdentity).where(
                DeletedIdentity.external_auth_id == "user_never_seen",
            ),
        )).scalar_one()

    async def test__other_event_type__200_noop(
        self,
        webhook_client: AsyncClient,
        db_session: AsyncSession,
        clerk_user: User,
    ) -> None:
        """A non-deletion event is acknowledged without touching anything."""
        payload = json.dumps({
            "data": {"id": clerk_user.external_auth_id, "object": "user"},
            "object": "event",
            "type": "user.updated",
        })
        response = await webhook_client.post(
            "/webhooks/clerk",
            content=payload,
            headers=signed_headers(payload),
        )
        assert response.status_code == 200
        assert response.json()["handled"] is False
        assert await _user_exists(db_session, clerk_user.external_auth_id)
        tombstones = (await db_session.execute(
            select(DeletedIdentity),
        )).scalars().all()
        assert tombstones == []

    async def test__deletion_event_without_user_id__400(
        self,
        webhook_client: AsyncClient,
    ) -> None:
        """An authentic but malformed deletion event is rejected, not 500."""
        payload = json.dumps({
            "data": {"deleted": True, "object": "user"},
            "object": "event",
            "type": "user.deleted",
        })
        response = await webhook_client.post(
            "/webhooks/clerk",
            content=payload,
            headers=signed_headers(payload),
        )
        assert response.status_code == 400

    async def test__deletion_invalidates_auth_cache(
        self,
        webhook_client: AsyncClient,
        db_session: AsyncSession,  # noqa: ARG002
        clerk_user: User,
    ) -> None:
        """A cached identity stops resolving the moment deletion lands."""
        from core.auth_cache import get_auth_cache  # noqa: PLC0415

        external_auth_id = clerk_user.external_auth_id
        user_id = clerk_user.id
        auth_cache = get_auth_cache()
        assert auth_cache is not None
        await auth_cache.set(clerk_user)
        assert await auth_cache.get_by_external_auth_id(external_auth_id) is not None

        payload = deletion_event(external_auth_id)
        response = await webhook_client.post(
            "/webhooks/clerk",
            content=payload,
            headers=signed_headers(payload),
        )
        assert response.status_code == 200
        assert await auth_cache.get_by_external_auth_id(external_auth_id) is None
        assert await auth_cache.get_by_user_id(user_id) is None


class TestCacheInvalidationFailure:
    """
    The Redis client fails open (returns False, never raises). A deletion
    whose cache invalidation fails must NOT hide behind a 200 — the route
    returns 503 so Svix retries, and the idempotent replay re-invalidates.
    """

    async def test__failed_invalidation__503_then_successful_replay_200(
        self,
        webhook_client: AsyncClient,
        db_session: AsyncSession,
        clerk_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from core.redis import RedisClient  # noqa: PLC0415

        external_auth_id = clerk_user.external_auth_id
        payload = deletion_event(external_auth_id)
        headers = signed_headers(payload)

        async def failing_delete(self: RedisClient, *keys: str) -> bool:  # noqa: ARG001
            return False

        monkeypatch.setattr(RedisClient, "delete", failing_delete)
        first = await webhook_client.post(
            "/webhooks/clerk", content=payload, headers=headers,
        )
        assert first.status_code == 503
        # The DB work is committed regardless: user gone, tombstone present
        assert not await _user_exists(db_session, external_auth_id)
        tombstone = (await db_session.execute(
            select(DeletedIdentity).where(
                DeletedIdentity.external_auth_id == external_auth_id,
            ),
        )).scalar_one_or_none()
        assert tombstone is not None

        # Redis recovers; the Svix retry (idempotent replay) succeeds
        monkeypatch.undo()
        second = await webhook_client.post(
            "/webhooks/clerk", content=payload, headers=headers,
        )
        assert second.status_code == 200
        assert second.json()["deleted_user"] is False
