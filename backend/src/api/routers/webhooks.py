"""
Clerk webhook endpoint — the first inbound provider-calls-us surface.

Security posture: an unauthenticated webhook endpoint that deletes users is an
attacker-triggerable "delete this user" button, so the Svix signature is
verified on the RAW request body before anything is parsed or touched. There
is deliberately no Pydantic body model on the route — body parsing happens
only after verification succeeds. The body read itself is bounded (this is
the one unauthenticated body-reading route in the app, so it cannot rely on
auth rejecting oversized garbage first). If no signing secret is configured
the endpoint fails closed (503). Svix retries any non-2xx on a finite
schedule — see the delivery-failure runbook in README_DEPLOY.

Webhooks are sync convenience, never source of truth: JIT provisioning remains
the only creation path; this endpoint only handles `user.deleted` (and is the
natural future home for billing/org events). The dashboard subscription is
scoped to `user.deleted`, and the handler defensively no-ops anything else, so
broadening the subscription later needs a code change here, not a hotfix.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from svix.webhooks import Webhook, WebhookVerificationError

from api.dependencies import get_async_session
from core.auth_cache import get_auth_cache
from core.config import Settings, get_settings
from services import user_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# Bound on the raw body read. Clerk's user.* event payloads are a few KB (the
# largest is a full User object on user.created/updated; user.deleted is a
# 3-field deleted object); Svix itself caps message payloads well below this.
# Anything larger is not a webhook we could ever handle.
MAX_BODY_BYTES = 256 * 1024


async def _read_body_bounded(request: Request) -> bytes:
    """
    Read the raw body, rejecting oversized requests with 413.

    Checks the declared Content-Length first (cheap early reject), then
    enforces the limit on the actually-received bytes — a chunked or
    dishonestly-declared request cannot bypass the cap.
    """
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Payload too large",
        )
    chunks: list[bytes] = []
    received = 0
    async for chunk in request.stream():
        received += len(chunk)
        if received > MAX_BODY_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Payload too large",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/clerk")
async def clerk_webhook(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    """
    Receive a Clerk webhook event (Svix-delivered).

    Verifies the Svix signature first, then handles `user.deleted` by
    tombstoning the identity and cascade-deleting the user's data (see
    user_service.delete_user_by_external_auth_id). All other event types
    return a 200 no-op. Idempotent: Svix delivery is at-least-once, and
    replays of the same deletion succeed without touching anything.

    Error semantics: every 4xx here is a *classification*, not a retry
    suppressor — Svix treats any non-2xx as a failed attempt and retries on
    its schedule, so a permanently bad message still exhausts its retries;
    the 400s just make the failure legible instead of a stack trace.
    """
    secret = settings.clerk_webhook_signing_secret
    if not secret:
        logger.error(
            "clerk_webhook_rejected: CLERK_WEBHOOK_SIGNING_SECRET is not "
            "configured; failing closed",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook endpoint not configured",
        )

    # Verify against the raw body — the signature covers the exact bytes sent,
    # so the body must not be parsed (or re-serialized) before this point.
    payload = await _read_body_bounded(request)
    try:
        event = Webhook(secret).verify(payload, dict(request.headers))
    except (WebhookVerificationError, ValueError):
        # ValueError covers everything the svix parser leaks besides its own
        # error type: a malformed svix-signature header (bare tuple-unpack /
        # base64 errors — attacker-reachable, no valid signature needed), and
        # the post-signature body decode (UnicodeDecodeError, JSONDecodeError
        # — both ValueError subclasses). Same clean 400 rejection.
        logger.warning("clerk_webhook_rejected: signature verification failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature",
        ) from None

    if not isinstance(event, dict):
        # Authentic but not an event object (e.g. a signed JSON array).
        logger.error("clerk_webhook_malformed: non-object event payload")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed event payload",
        )

    event_type = event.get("type")
    if event_type != "user.deleted":
        # Defensive no-op: the dashboard subscription is scoped to
        # user.deleted, but a broadened subscription must not 500 here —
        # unknown event types stay harmless regardless of payload shape.
        logger.info("clerk_webhook_ignored type=%s", event_type)
        return {"received": True, "handled": False}

    data = event.get("data")
    external_auth_id = data.get("id") if isinstance(data, dict) else None
    # A string id within the column limit, or it never reaches SQL binding —
    # a signed numeric/list/oversized id must be a 400, not a driver error.
    if (
        not isinstance(external_auth_id, str)
        or not external_auth_id
        or len(external_auth_id) > 255
    ):
        # Authentic but malformed — retrying will not improve it.
        logger.error("clerk_webhook_malformed: user.deleted without usable data.id")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Event has no usable user id",
        )

    result = await user_service.delete_user_by_external_auth_id(
        session,
        external_auth_id,
    )

    # Commit BEFORE invalidating the auth cache (the consent router's
    # established pattern): invalidating first opens a window where a
    # concurrent request re-reads the still-visible row and repopulates the
    # cache with a user whose deletion is about to commit.
    await session.commit()

    # The Redis client fails open (returns False, never raises), so a failed
    # invalidation must be turned into an explicit 503 here — otherwise a
    # stale cache entry survives behind a 200. The 503 makes Svix retry; the
    # replay lands in the idempotent unknown-identity branch, which
    # re-attempts the invalidation. (Review-round finding: the docs claimed
    # this self-healing, the fail-open client silently prevented it.)
    invalidated = True
    auth_cache = get_auth_cache()
    if auth_cache:
        if result.deleted:
            invalidated = await auth_cache.invalidate(
                result.user_id,
                external_auth_id=result.external_auth_id,
            )
        else:
            # Unknown identity: the row is gone (or never existed), so the
            # cache is the only place its identifiers might live.
            cached = await auth_cache.get_by_external_auth_id(external_auth_id)
            if cached:
                invalidated = await auth_cache.invalidate(
                    cached.id,
                    external_auth_id=cached.external_auth_id,
                )
    if not invalidated:
        logger.error(
            "clerk_webhook_cache_invalidation_failed external_auth_id=%s "
            "(user deleted and tombstoned; returning 503 so Svix replays)",
            external_auth_id,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cache invalidation failed; delivery will be retried",
        )

    return {"received": True, "handled": True, "deleted_user": result.deleted}
