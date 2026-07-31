"""
Authentication module: Clerk JWT verification and PAT support.

Provider seam containment (architecture-level intent — keep it this way): every
provider-specific shape in the backend lives in this module plus its immediate
collaborators (`core/config.py`, `core/auth_cache.py`, `core/request_context.py`,
`schemas/cached_user.py`). Nothing outside the seam may parse tokens, read
provider claims, or know which IdP issued a credential.

Clerk is the only accepted JWT issuer. The Auth0 verification arm from the
migration's dual-accept window (see
docs/implementation_plans/2026-07-02-clerk-migration.md) was removed at
decommission (M6b); tokens from any other issuer get a 401. User resolution is
keyed solely by users.external_auth_id (the Clerk `sub`).
"""
import logging
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from core.auth_cache import get_auth_cache
from core.config import Settings, get_settings
from core.policy_versions import PRIVACY_POLICY_VERSION, TERMS_OF_SERVICE_VERSION
from core.rate_limit_config import (
    RateLimitExceededError,
    get_operation_type,
)
from core.rate_limiter import check_rate_limit
# Import and re-export for backward compatibility
from core.request_context import AuthType, RequestContext
from core.tier_limits import get_tier_safely
from db.session import get_async_session
from models.content_history import SOURCE_MAX_LENGTH
from models.deleted_identity import DeletedIdentity
from models.user import User
from schemas.cached_user import CachedUser
from services import token_service, user_service

logger = logging.getLogger(__name__)

# Re-export for backward compatibility
__all__ = [
    "AUTH_DEPENDENCIES",
    "AuthType",
    "DeletedIdentityError",
    "RequestContext",
    "get_current_user",
    "get_current_user_ai",
    "get_current_user_session_only",
    "get_current_user_session_only_without_consent",
    "get_current_user_without_consent",
    "get_request_context",
]

# Clock-skew leeway for verifying Clerk session tokens. PyJWT defaults to 0;
# with ~60-second tokens, a slightly-fast client clock would cause spurious
# 401s that present as random logouts. 5s matches the Clerk instance's
# session.allowed_clock_skew (clerk/config.dev.json) — but the value is our
# own: Clerk's setting governs Clerk's servers, not our verification.
CLERK_CLOCK_SKEW_LEEWAY_SECONDS = 5

# Terminal "account deleted" 401 contract (M8 anti-resurrection guard).
#
# When a validly-signed token is presented for a tombstoned identity, the
# response carries the stable machine-readable ``error_code`` below alongside
# the human-readable ``detail``. Clients (web, CLI, and iOS when it ships) bind
# to the ``error_code`` — NOT the prose — to tell this *terminal* 401 apart
# from an ordinary expired-session 401: re-authenticating can never succeed for
# a deleted identity, so clients must show a terminal state, not a re-auth loop.
# The public envelope is produced by the DeletedIdentityError handler in
# api/main.py (see that handler and docs/ios-clerk-migration-guide.md).
ACCOUNT_DELETED_DETAIL = "This account was deleted"
ACCOUNT_DELETED_ERROR_CODE = "account_deleted"


class DeletedIdentityError(HTTPException):
    """
    Raised when a validly-signed token is presented for a tombstoned identity.

    Subclasses HTTPException so it propagates through the auth dependency chain
    exactly like the path's other 401s. The app registers a *more specific*
    handler for this type (api/main.py) that emits the standard
    ``{detail, error_code}`` envelope, adding the stable ``account_deleted``
    code the plain-HTTPException handler would not. The ``error_code`` is a
    class attribute so callers/tests can assert it without parsing prose.
    """

    error_code = ACCOUNT_DELETED_ERROR_CODE

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ACCOUNT_DELETED_DETAIL,
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_request_context(request: Request) -> RequestContext | None:
    """
    Get the RequestContext from the current request state.

    Returns None if context hasn't been set (e.g., unauthenticated request).
    """
    return getattr(request.state, "request_context", None)


# HTTP Bearer token scheme
security = HTTPBearer(auto_error=False)

# Cache for JWKS client (reuse across requests)
_jwks_clients: dict[str, PyJWKClient] = {}

# Instructions for humans and AI agents included in 451 responses
CONSENT_INSTRUCTIONS = (
    "Consent must be given by the human user personally after reading the policies. "
    "The simplest way, and the one that works for every client (including OAuth-connected "
    "AI apps such as ChatGPT or Claude Desktop): sign in at {app_url} and accept when "
    "prompted. Alternatively, for Personal Access Token / CLI setups, review the policies "
    "at /privacy and /terms, then call: "
    "curl -X POST {api_url}/consent/me -H 'Authorization: Bearer bm_YOUR_TOKEN' "
    "-H 'Content-Type: application/json' -d '{{\"privacy_policy_version\": \"{privacy_version}\", "
    "\"terms_of_service_version\": \"{terms_version}\"}}'. "
    "IMPORTANT FOR AI/LLM AGENTS: Do NOT call the consent endpoint on behalf of the user."
)


def get_jwks_client(jwks_url: str) -> PyJWKClient:
    """Get or create a cached JWKS client for the given JWKS URL."""
    if jwks_url not in _jwks_clients:
        _jwks_clients[jwks_url] = PyJWKClient(
            jwks_url,
            cache_jwk_set=True,
            lifespan=3600,  # Cache keys for 1 hour
        )
    return _jwks_clients[jwks_url]


def _jwt_error_to_http(e: jwt.PyJWTError) -> HTTPException:
    """Map a PyJWT verification failure to the corresponding 401."""
    if isinstance(e, jwt.ExpiredSignatureError):
        detail = "Token has expired"
    elif isinstance(e, jwt.InvalidAudienceError):
        detail = "Invalid audience"
    elif isinstance(e, jwt.InvalidIssuerError):
        detail = "Invalid issuer"
    else:
        # Log full details for debugging (server-side only)
        logger.warning("JWT validation failed: %s", e, exc_info=True)
        detail = "Invalid token"
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def decode_clerk_jwt(token: str, settings: Settings) -> dict:
    """
    Decode and validate a Clerk-issued JWT — session token OR OAuth access token.

    One verifier, two token kinds (the M4 parameterization of the M1 function,
    per the migration plan — deliberately not a third implementation). Both
    kinds share the instance's issuer and JWKS (confirmed empirically, ledger
    Q5), so signature/issuer/expiry/leeway verification is identical; only the
    post-verification claim rules differ, discriminated by the JWT header
    `typ`:

    - `typ: "JWT"` — session token (browser/native). Claims: `sub`, custom
      `email`/`email_verified`, `azp` on browser-origin tokens.
    - `typ: "at+jwt"` or `"application/at+jwt"` (both registered by RFC 9068
      §4) — OAuth access token (CLI M4, MCP M5). Claims: `sub` (same Clerk
      user id), `client_id`, `scope`; NO email, NO `azp`. The `client_id`
      must be present or the token is rejected.

    The header `typ` is a safe discriminator because the header is covered by
    the signature — it is read only after verification succeeds. Deliberately
    NOT discriminating on `azp` absence: that would quietly make the `azp`
    check optional across the board (the exact trap the plan's M4 step 1
    flags). Instead the `azp` rule below applies to BOTH kinds unchanged.

    `client_id` policy (decided at M4, recorded here per the security review):
    presence is required for `at+jwt`, but there is no client-id allowlist.
    Trust anchor: only OAuth apps on OUR Clerk instance can mint tokens our
    JWKS verifies, and creating such an app requires the instance secret key —
    an allowlist adds no barrier an attacker with that key couldn't clear, and
    a static list would break M5's dynamically-registered MCP clients. The
    client_id is logged for observability instead.

    Clerk-specific claim rules (established at the migration's M1; each
    verified against the live dev instance in the M0 spike):
    - No audience claim exists; the equivalent check is `azp` (authorized
      party) below.
    - `azp` rule: if present it must be in the configured allowlist; if absent
      it is tolerated. Browser-origin tokens carry `azp`; Backend-API-minted
      tokens carry none (M0 spike), and OAuth access tokens carry none (M4
      probe). Absence can't be forged onto a browser token — the token is
      signed — so present→check/absent→tolerate is safe regardless.
    - Explicit clock-skew leeway (~60s session tokens; see the constant's
      comment). Harmless for 24h OAuth tokens.

    Raises:
        HTTPException: If token is invalid, expired, has wrong issuer/azp, or
        is an OAuth access token missing `client_id`.
    """
    try:
        jwks_client = get_jwks_client(settings.clerk_jwks_url)
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.clerk_issuer,
            leeway=CLERK_CLOCK_SKEW_LEEWAY_SECONDS,
            options={
                "verify_aud": False,  # no audience on Clerk session tokens
                "require": ["exp", "iss", "sub"],
            },
        )
    # Order matters: PyJWKClientConnectionError IS a PyJWTError, so the
    # provider-unreachable case must be caught first — it's an outage (503,
    # retryable), not a bad token (401, which would sign the user out).
    except jwt.PyJWKClientConnectionError as e:
        # Log full details for debugging (server-side only)
        logger.error("Failed to fetch JWKS from Clerk: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not validate credentials",
        )
    except jwt.PyJWTError as e:
        raise _jwt_error_to_http(e)

    azp = payload.get("azp")
    if azp is not None and azp not in settings.clerk_authorized_parties:
        logger.warning("Clerk token rejected: azp %r not in authorized parties", azp)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Header read AFTER verification — the signature covers the header, so the
    # value is authentic here. RFC 9068 §4: resource servers must recognize
    # BOTH the short form ("at+jwt") and the full media type
    # ("application/at+jwt"); compare case-insensitively per RFC 7515's
    # definition of `typ`. Clerk emits the short form today (M4 probe), but
    # recognizing only that spelling would let a legal provider-side change
    # silently reroute OAuth tokens to session rules.
    header_typ = jwt.get_unverified_header(token).get("typ")
    if isinstance(header_typ, str) and header_typ.lower() in ("at+jwt", "application/at+jwt"):
        client_id = payload.get("client_id")
        if not client_id:
            logger.warning(
                "Clerk OAuth access token rejected: missing client_id (sub=%s)",
                payload.get("sub"),
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        logger.info(
            "clerk_oauth_token_accepted client_id=%s sub=%s",
            client_id,
            payload.get("sub"),
        )

    return payload


def _peek_issuer(token: str) -> str | None:
    """
    Read a JWT's `iss` claim WITHOUT verifying it — for dispatch only.

    This looks alarming but is safe: the value is used solely to select which
    verifier runs; the selected verifier then enforces signature, issuer, and
    every other claim from scratch. A forged `iss` merely routes the token to
    a verifier whose keys will reject it.

    Raises:
        HTTPException 401: if the bearer isn't parseable as a JWT at all. The
        warning log names the cause — this is the observable symptom of a
        Clerk OAuth app misconfigured to issue opaque tokens (M4/M5), and the
        log is what makes that misconfiguration diagnosable instead of a
        silent 401.
    """
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError as e:
        logger.warning(
            "Bearer token is not a PAT and not parseable as a JWT "
            "(opaque token from a misconfigured OAuth app?): %s",
            e,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload.get("iss")


async def get_or_create_user(
    db: AsyncSession,
    *,
    external_auth_id: str,
    email: str | None = None,
    email_verified: bool | None = None,
    jit_create_allowed: bool = True,
) -> User | CachedUser:
    """
    Get user from cache or database, keyed by the verified token's Clerk
    user id (`sub` → users.external_auth_id).

    Returns CachedUser on cache hit, User ORM object on cache miss.

    Safe attributes (available on both types):
    - id: UUID
    - external_auth_id: str
    - email: str | None
    - email_verified: bool | None

    Consent fields (different access patterns):
    - CachedUser: consent_privacy_version, consent_tos_version (direct attributes)
    - User ORM: consent.privacy_policy_version, consent.terms_of_service_version

    WARNING: Do NOT access ORM relationships like .bookmarks, .tokens on the return value.
    Those only exist on User, not CachedUser.

    JIT-create gating (introduced as a dual-accept window rule, AD5; now gates
    Clerk-path creation only): lookup is always allowed; when
    `jit_create_allowed` is False an unknown identity is rejected with a
    generic 401 plus a warning log naming the identity — the loud, observable
    failure mode for identities leaking past a provider-side sign-up control.

    Anti-resurrection gating (M8): before any create, the identity is checked
    against the `deleted_identities` tombstones — a still-valid token for a
    deleted account must not re-create an empty user row. Rejected with an
    explicit "this account was deleted" 401 (see _reject_deleted_identity).

    Handles race conditions where multiple concurrent requests may try to create
    the same user simultaneously. If an IntegrityError occurs (due to the unique
    constraint on the identifier column), the function rolls back and fetches
    the existing user.

    Note: Uses flush(), not commit. Session generator handles commit at request end.
    """
    lookup_column = User.external_auth_id
    identifier = external_auth_id

    # Try cache first
    cached = await _cache_lookup(external_auth_id)
    if cached:
        # Fall through to DB if email changed (can't update cache directly).
        # Note: email_verified is intentionally NOT checked here. It's an
        # informational field not used for access control, so staleness up to
        # cache TTL (5 min) is acceptable. Avoiding a DB hit on every request
        # for a rarely-changing field is the right tradeoff.
        if email and cached.email != email:
            logger.debug("auth_cache email_mismatch, falling through to DB")
        else:
            return cached

    # Cache miss or email update needed - hit DB
    result = await db.execute(
        select(User)
        .options(joinedload(User.consent))
        .where(lookup_column == identifier),
    )
    user = result.scalar_one_or_none()

    if user is None:
        # Serialize against a concurrent deletion for this identity — without
        # the lock, an unknown-identity deletion webhook and this first-ever
        # request can each pass the other's existence check and commit both a
        # tombstone and a fresh user row. Lock, then RE-READ: whichever
        # transaction held the lock first is committed and visible now.
        await user_service.acquire_identity_lock(db, "clerk", identifier)
        result = await db.execute(
            select(User)
            .options(joinedload(User.consent))
            .where(lookup_column == identifier),
        )
        user = result.scalar_one_or_none()

    created = False
    if user is None:
        # Tombstone check first: a deleted identity gets the explicit 401
        # regardless of whether JIT creation is currently enabled.
        await _reject_deleted_identity(db, external_auth_id)
        if not jit_create_allowed:
            _reject_jit_create(identifier)
        try:
            user = await user_service.create_user_with_defaults(
                db,
                external_auth_id=external_auth_id,
                email=email,
                email_verified=email_verified,
            )
            created = True
        except IntegrityError:
            # Race condition: another request created the user between our SELECT
            # and INSERT. Rollback and fetch the existing user (now committed by
            # that other transaction — safe to cache, so `created` stays False).
            await db.rollback()
            result = await db.execute(
                select(User)
                .options(joinedload(User.consent))
                .where(lookup_column == identifier),
            )
            user = result.scalar_one()

    # Update email/email_verified if changed at the IdP (applies to both existing
    # users and users fetched after race condition recovery)
    if email and user.email != email:
        user.email = email
    if email_verified is not None and user.email_verified != email_verified:
        user.email_verified = email_verified
    await db.flush()

    if created:
        # Do NOT cache a user created in THIS request: the row is only flushed,
        # not committed, and this request can still roll back (e.g. the consent
        # gate 451s a brand-new user's first-ever request — the user row never
        # commits). A cached entry would then outlive the phantom row for the
        # 5-min TTL, serving foreign-key-violating reads. The next request is a
        # cache miss that reads a now-committed row and caches it then. The
        # tombstone recheck is likewise unneeded here: the pre-create tombstone
        # check ran under the identity advisory lock we still hold, so no
        # deletion can have committed a tombstone for this identity since.
        return user

    # Populate cache (existing or race-recovered user — its row is committed)
    auth_cache = get_auth_cache()
    if auth_cache:
        await auth_cache.set(user)

    await _recheck_tombstone_after_cache_populate(db, user, external_auth_id)

    return user


async def _recheck_tombstone_after_cache_populate(
    db: AsyncSession,
    user: User,
    external_auth_id: str,
) -> None:
    """
    Post-population tombstone recheck — closes the deletion/cache-miss race
    lock-free: if the deletion committed between the user read and the cache
    write, this fresh statement (READ COMMITTED: new snapshot per statement)
    sees its tombstone and we evict our own stale entry; if the deletion
    commits after this check instead, its own post-commit invalidation
    (api/routers/webhooks.py) deletes the entry. No interleaving leaves a
    deleted identity cached. Cache HITS deliberately skip this — the hot path
    stays untouched; a hit can only exist inside the 5-min TTL of an entry
    that survived this check or predates the deletion, and the deletion's
    invalidation covers the latter.
    """
    if not await _is_identity_tombstoned(db, external_auth_id):
        return
    auth_cache = get_auth_cache()
    if auth_cache:
        evicted = await auth_cache.invalidate(
            user.id,
            external_auth_id=user.external_auth_id,
        )
        if not evicted:
            # Redis fail-open: this request still 401s, but the entry written
            # above may serve the identity for up to one TTL. Accepted,
            # documented residual (architecture.md §16): it requires a partial
            # Redis failure in this exact window; a full outage degrades safe
            # (cache reads fail too -> DB path -> tombstone 401).
            logger.error(
                "tombstone_recheck_eviction_failed sub=%s: stale cache entry "
                "may persist for up to one TTL",
                external_auth_id,
            )
    _raise_deleted_identity(external_auth_id)


async def _cache_lookup(external_auth_id: str) -> CachedUser | None:
    """Look up the auth-cache entry for the supplied identifier."""
    auth_cache = get_auth_cache()
    if not auth_cache:
        return None
    return await auth_cache.get_by_external_auth_id(external_auth_id)


async def _is_identity_tombstoned(
    db: AsyncSession,
    external_auth_id: str,
) -> bool:
    """Check the supplied identity against the deleted_identities tombstones."""
    result = await db.execute(
        select(DeletedIdentity.id)
        .where(DeletedIdentity.external_auth_id == external_auth_id)
        .limit(1),
    )
    return result.scalar_one_or_none() is not None


def _raise_deleted_identity(identifier: str) -> None:
    """
    Reject a tombstoned identity (M8 anti-resurrection guard).

    The 401 detail is deliberately explicit — a recorded exception to the
    generic-401 policy: only a holder of a validly-signed token for that exact
    identity can ever see it (M4's friendly invalid_grant message is the
    precedent), and it stops a deleted user's devices looping on an
    unexplained sign-in failure.
    """
    logger.warning(
        "Authentication rejected (identity tombstoned): sub=%s",
        identifier,
    )
    raise DeletedIdentityError()


async def _reject_deleted_identity(
    db: AsyncSession,
    external_auth_id: str,
) -> None:
    """
    Block JIT resurrection of a deleted account (M8 anti-resurrection guard).

    A deleted user's tokens can outlive the deletion — a not-yet-expired Clerk
    JWT. Without this check, the next validly-signed token would JIT-create an
    empty resurrected row. The tombstone is written by the deletion path
    (services/user_service.delete_user_by_external_auth_id).
    """
    if await _is_identity_tombstoned(db, external_auth_id):
        _raise_deleted_identity(external_auth_id)


def _reject_jit_create(identifier: str) -> None:
    """
    Reject a gated JIT creation: generic 401 + a warning log naming the
    identity (the loud, observable failure mode for identities leaking past a
    provider-side sign-up control — AD5 window rules).
    """
    logger.warning(
        "JIT user creation rejected (disabled): sub=%s",
        identifier,
    )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid token",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_or_create_dev_user(db: AsyncSession) -> User:
    """
    Get or create a development user for DEV_MODE.

    Deliberately not subject to the JIT-create gate — dev mode bypasses auth
    entirely. The sentinel keeps the historical "dev|" shape but lives in
    external_auth_id (the M6b decommission migration converts pre-existing
    dev rows; see that migration's docstring for older local databases).
    """
    return await get_or_create_user(
        db,
        external_auth_id="dev|local-development-user",
        email="dev@localhost",
    )


async def validate_pat(db: AsyncSession, token: str) -> User:
    """
    Validate a Personal Access Token (PAT) and return the associated user.

    Args:
        db: Database session.
        token: The plaintext PAT (starts with 'bm_').

    Returns:
        User associated with the token.

    Raises:
        HTTPException: If token is invalid, expired, or revoked.
    """
    api_token = await token_service.validate_token(db, token)

    if api_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Load the user associated with this token (with consent for enforcement check)
    result = await db.execute(
        select(User)
        .options(joinedload(User.consent))
        .where(User.id == api_token.user_id),
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def _check_consent(user: User | CachedUser, settings: Settings) -> None:
    """
    Verify user has valid consent.

    Works with both User ORM objects and CachedUser dataclass.

    Raises HTTP 451 if consent is missing or outdated.
    Skipped in DEV_MODE.
    """
    if settings.dev_mode:
        return

    instructions = CONSENT_INSTRUCTIONS.format(
        app_url=settings.frontend_url,
        api_url=settings.api_url,
        privacy_version=PRIVACY_POLICY_VERSION,
        terms_version=TERMS_OF_SERVICE_VERSION,
    )

    # Get consent versions - different access patterns for User vs CachedUser
    if isinstance(user, CachedUser):
        privacy_version = user.consent_privacy_version
        tos_version = user.consent_tos_version
    else:
        privacy_version = (
            user.consent.privacy_policy_version if user.consent else None
        )
        tos_version = (
            user.consent.terms_of_service_version if user.consent else None
        )

    if privacy_version is None or tos_version is None:
        raise HTTPException(
            status_code=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
            detail={
                "error": "consent_required",
                "message": "You must accept the Privacy Policy and Terms of Service.",
                "consent_url": "/consent/status",
                "instructions": instructions,
            },
        )

    if (
        privacy_version != PRIVACY_POLICY_VERSION
        or tos_version != TERMS_OF_SERVICE_VERSION
    ):
        raise HTTPException(
            status_code=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
            detail={
                "error": "consent_outdated",
                "message": "Policy versions have been updated. Please review and accept.",
                "consent_url": "/consent/status",
                "instructions": instructions,
            },
        )


async def _apply_rate_limit(
    user: User | CachedUser,
    request: Request,
    settings: Settings,
) -> None:
    """
    Apply rate limiting for the current request.

    Checks both per-minute and daily limits based on user tier and operation type.
    Stores rate limit info in request.state for middleware to add headers.
    Raises RateLimitExceededError if limit exceeded (handled by exception handler).

    In dev mode, rate limiting is disabled to allow running evals and tests
    without hitting limits.
    """
    if settings.dev_mode:
        return

    operation_type = get_operation_type(request.method, request.url.path)
    tier = get_tier_safely(user.tier)

    result = await check_rate_limit(user.id, operation_type, tier)

    # Store result in request.state for RateLimitHeadersMiddleware
    request.state.rate_limit_info = {
        "limit": result.limit,
        "remaining": result.remaining,
        "reset": result.reset,
    }

    if not result.allowed:
        raise RateLimitExceededError(result)


def get_request_source(
    x_request_source: Annotated[
        str | None,
        Header(
            description=(
                "Free-form tag identifying the calling client, recorded on content "
                "history audit rows for telemetry. Not access control (spoofable). "
                "Lowercased server-side; no allowlist; a missing header resolves to "
                f"'unknown'. Keep it to {SOURCE_MAX_LENGTH} characters or fewer — "
                "longer values are truncated. Tiddly's own clients send: web, cli, "
                "chrome-extension, mcp-content, mcp-prompt, ios."
            ),
        ),
    ] = None,
) -> str:
    """
    Resolve the request source from the X-Request-Source header for the audit trail.

    Declared as a FastAPI Header dependency (rather than read off the raw request)
    so it appears in the generated OpenAPI/Swagger reference. Truncated to
    SOURCE_MAX_LENGTH so an over-length header can never exceed the history column
    and fail a write. See docs/architecture.md "Request source" for the canonical
    behavior and first-party client values.
    """
    return (x_request_source or "").strip().lower()[:SOURCE_MAX_LENGTH] or "unknown"


async def _authenticate_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
    db: AsyncSession,
    settings: Settings,
    *,
    source: str,
    allow_pat: bool = True,
) -> User | CachedUser:
    """
    Internal: authenticate user without consent check.

    Supports:
    - Clerk-issued JWTs (session tokens and OAuth access tokens; any other
      issuer is rejected)
    - Personal Access Tokens (PATs) starting with 'bm_' (for CLI/MCP/scripts)

    In DEV_MODE, bypasses auth and returns a test user.

    Also sets request.state.request_context with source/auth tracking info
    for content versioning audit trail.

    Args:
        request: The FastAPI request object.
        credentials: HTTP Authorization header credentials.
        db: Database session.
        settings: Application settings.
        source: Resolved X-Request-Source value (see get_request_source), recorded
            on the request context for the content-versioning audit trail.
        allow_pat: If False, reject PAT tokens with 403 to help prevent unintended
            programmatic use. Note: does not block IdP JWTs used outside the browser.
            Policy decision (M4 security review, deliberate): Clerk OAuth access
            tokens (`at+jwt` — day-lived, programmatic) DO count as session auth
            on PAT-blocked surfaces (/tokens/*, fetch-metadata, AI endpoints).
            This preserved parity with the pre-migration behavior (the CLI's
            Auth0 device-flow JWTs passed these checks), and the PAT block's
            purpose is limiting leaked long-lived static credentials, not
            interactive-grade OAuth grants (which require a browser sign-in
            and expire daily).
    """
    token_prefix: str | None = None

    if settings.dev_mode:
        auth_type = AuthType.DEV
        user = await get_or_create_dev_user(db)
    elif credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    else:
        token = credentials.credentials

        # Route to appropriate validation based on token prefix
        if token.startswith("bm_"):
            if not allow_pat:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="This endpoint is not available for API tokens. Please use the web interface.",  # noqa: E501
                )
            auth_type = AuthType.PAT
            # Compute token_prefix for audit trail (e.g., "bm_a3f8...")
            # Show first 15 chars which includes prefix + partial identifier
            token_prefix = token[:15] if len(token) > 15 else token
            user = await validate_pat(db, token)
        else:
            # IdP JWT: dispatch on the (unverified) `iss` claim — see _peek_issuer
            # for why that is safe. The selected verifier enforces everything.
            # Clerk is the only accepted issuer (M6b removed the Auth0 arm);
            # any other issuer — including a still-valid Auth0 token — is a 401.
            auth_type = AuthType.SESSION
            issuer = _peek_issuer(token)

            # Clerk config is optional in dev; guard before comparing
            # clerk_issuer so an unset Frontend API doesn't route tokens into
            # a malformed Clerk verifier.
            if settings.clerk_frontend_api and issuer == settings.clerk_issuer:
                payload = decode_clerk_jwt(token, settings)

                # `sub` presence is enforced by decode_clerk_jwt's require list.
                # Email claims are the plain (non-namespaced) custom session-token
                # claims configured on the Clerk instance.
                user = await get_or_create_user(
                    db,
                    external_auth_id=payload["sub"],
                    email=payload.get("email"),
                    email_verified=payload.get("email_verified"),
                    jit_create_allowed=settings.clerk_jit_create_enabled,
                )
            else:
                logger.warning("JWT rejected: unknown or missing issuer %r", issuer)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token",
                    headers={"WWW-Authenticate": "Bearer"},
                )

    # Set request context for content versioning audit trail
    request.state.request_context = RequestContext(
        source=source,
        auth_type=auth_type,
        token_prefix=token_prefix,
    )

    return user


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
    source: str = Depends(get_request_source),
) -> User | CachedUser:
    """
    Dependency that validates the token, applies rate limiting, checks consent,
    and returns the current user.

    Returns User ORM object on cache miss, CachedUser on cache hit.
    Auth + rate limiting + consent check (default for most routes).
    Use get_current_user_without_consent for exempt routes.

    Note: Rate limiting runs before consent check so all authenticated requests
    count against limits, even from users who haven't consented yet.
    """
    user = await _authenticate_user(request, credentials, db, settings, source=source)
    await _apply_rate_limit(user, request, settings)
    _check_consent(user, settings)
    return user


async def get_current_user_without_consent(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
    source: str = Depends(get_request_source),
) -> User | CachedUser:
    """
    Dependency that validates the token, applies rate limiting, and returns the user.

    Returns User ORM object on cache miss, CachedUser on cache hit.
    Auth + rate limiting, no consent check (for exempt routes like consent endpoints).
    """
    user = await _authenticate_user(request, credentials, db, settings, source=source)
    await _apply_rate_limit(user, request, settings)
    return user


async def get_current_user_session_only(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
    source: str = Depends(get_request_source),
) -> User | CachedUser:
    """
    Dependency: session-only auth + rate limiting + consent check (blocks PAT access).

    "Session" = a Clerk-issued JWT (session token or OAuth access token), as
    opposed to a PAT. Returns User ORM object on cache miss, CachedUser on cache hit.
    Use this to block PAT access and help prevent unintended programmatic use.

    Examples:
        - /bookmarks/fetch-metadata (blocks PAT-based SSRF abuse)
        - /tokens/* (prevents compromised PAT from creating more tokens)
        - /settings/* (account management)

    Note: This does NOT prevent all programmatic access. Users can still extract
    their session JWT from browser DevTools and use it in scripts. Rate limiting
    provides the additional layer to cap any abuse.

    Returns 403 Forbidden for PAT tokens.
    Returns 429 if rate limit exceeded.
    Returns 451 if user hasn't consented to privacy policy/terms.
    Use get_current_user_session_only_without_consent for consent-exempt routes.
    """
    user = await _authenticate_user(
        request, credentials, db, settings, source=source, allow_pat=False,
    )
    await _apply_rate_limit(user, request, settings)
    _check_consent(user, settings)
    return user


async def get_current_user_session_only_without_consent(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
    source: str = Depends(get_request_source),
) -> User | CachedUser:
    """
    Dependency: session-only auth + rate limiting, no consent check (blocks PAT access).

    Use to block PAT access on routes that must be accessible without consent
    (e.g., consent/settings pages).

    See get_current_user_session_only for details on what this does and doesn't prevent.
    """
    user = await _authenticate_user(
        request, credentials, db, settings, source=source, allow_pat=False,
    )
    await _apply_rate_limit(user, request, settings)
    return user


async def get_current_user_ai(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
    source: str = Depends(get_request_source),
) -> User | CachedUser:
    """
    Dependency: session-only auth + consent check, NO global rate limiting.

    Used by /ai/* endpoints. Skips _apply_rate_limit() to avoid consuming
    READ/WRITE quota — AI endpoints have their own rate limit buckets
    (AI_PLATFORM / AI_BYOK) enforced by a separate dependency.

    Returns 403 Forbidden for PAT tokens.
    Returns 451 if user hasn't consented to privacy policy/terms.
    """
    user = await _authenticate_user(
        request, credentials, db, settings, source=source, allow_pat=False,
    )
    _check_consent(user, settings)
    return user


# The authoritative set of authentication dependencies — every route entry
# point that resolves the current user. This is the single source of truth for
# "what counts as an auth dependency"; the invariant guard
# (tests/core/test_auth_dependency_invariant.py) iterates it to prove no route
# executes authentication more than once per request (the phantom-cache fix in
# get_or_create_user relies on that — see its comments). A completeness test
# there asserts this tuple equals every `get_current_user*` callable in this
# module, so a new variant that follows the naming convention cannot silently
# escape the guard; a differently-named auth dependency still must be added
# here by hand.
AUTH_DEPENDENCIES = (
    get_current_user,
    get_current_user_without_consent,
    get_current_user_session_only,
    get_current_user_session_only_without_consent,
    get_current_user_ai,
)
