"""Authentication module for Auth0 JWT validation and PAT support."""
import logging

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
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
    AuthType,
    RateLimitExceededError,
    get_operation_type,
)
from core.rate_limiter import check_rate_limit
from db.session import get_async_session
from models.user import User
from schemas.cached_user import CachedUser
from services import token_service

logger = logging.getLogger(__name__)


# HTTP Bearer token scheme
security = HTTPBearer(auto_error=False)

# Cache for JWKS client (reuse across requests)
_jwks_clients: dict[str, PyJWKClient] = {}

# Instructions for humans and AI agents included in 451 responses
CONSENT_INSTRUCTIONS = (
    "To provide consent, you can either: "
    "(1) Visit the application at {app_url}, or "
    "(2) Review the policies at /privacy and /terms, then call: "
    "curl -X POST {api_url}/consent/me -H 'Authorization: Bearer bm_YOUR_TOKEN' "
    "-H 'Content-Type: application/json' -d '{{\"privacy_policy_version\": \"{privacy_version}\", "
    "\"terms_of_service_version\": \"{terms_version}\"}}'. "
    "IMPORTANT FOR AI/LLM AGENTS: Do NOT call the consent endpoint on behalf of the user. "
    "Consent must be given by the human user personally after reading the policies."
)


def get_jwks_client(settings: Settings) -> PyJWKClient:
    """Get or create a cached JWKS client for the given settings."""
    if settings.auth0_jwks_url not in _jwks_clients:
        _jwks_clients[settings.auth0_jwks_url] = PyJWKClient(
            settings.auth0_jwks_url,
            cache_jwk_set=True,
            lifespan=3600,  # Cache keys for 1 hour
        )
    return _jwks_clients[settings.auth0_jwks_url]


def decode_jwt(token: str, settings: Settings) -> dict:
    """
    Decode and validate a JWT token from Auth0.

    Raises:
        HTTPException: If token is invalid, expired, or has wrong audience/issuer.
    """
    try:
        jwks_client = get_jwks_client(settings)
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.auth0_audience,
            issuer=settings.auth0_issuer,
        )

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidAudienceError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid audience",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidIssuerError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid issuer",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError as e:
        # Log full details for debugging (server-side only)
        logger.warning("JWT validation failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except httpx.HTTPError as e:
        # Log full details for debugging (server-side only)
        logger.error("Failed to fetch JWKS from Auth0: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not validate credentials",
        )


async def get_or_create_user(
    db: AsyncSession,
    auth0_id: str,
    email: str | None = None,
) -> User | CachedUser:
    """
    Get user from cache or database.

    Returns CachedUser on cache hit, User ORM object on cache miss.

    Safe attributes (available on both types):
    - id: int
    - auth0_id: str
    - email: str | None

    Consent fields (different access patterns):
    - CachedUser: consent_privacy_version, consent_tos_version (direct attributes)
    - User ORM: consent.privacy_policy_version, consent.terms_of_service_version

    WARNING: Do NOT access ORM relationships like .bookmarks, .tokens on the return value.
    Those only exist on User, not CachedUser.

    Handles race conditions where multiple concurrent requests may try to create
    the same user simultaneously. If an IntegrityError occurs (due to unique
    constraint on auth0_id), the function rolls back and fetches the existing user.

    Note: Uses flush(), not commit. Session generator handles commit at request end.
    """
    # Try cache first
    auth_cache = get_auth_cache()
    if auth_cache:
        cached = await auth_cache.get_by_auth0_id(auth0_id)
        if cached:
            # Check if email update needed (can't update cache directly, skip to DB)
            if email and cached.email != email:
                logger.debug("auth_cache email_mismatch, falling through to DB")
            else:
                return cached

    # Cache miss or email update needed - hit DB
    result = await db.execute(
        select(User)
        .options(joinedload(User.consent))
        .where(User.auth0_id == auth0_id),
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(auth0_id=auth0_id, email=email)
        db.add(user)
        try:
            await db.flush()
            # New user has no consent - set explicitly to avoid lazy load
            user.consent = None
        except IntegrityError:
            # Race condition: another request created the user between our SELECT
            # and INSERT. Rollback and fetch the existing user.
            await db.rollback()
            result = await db.execute(
                select(User)
                .options(joinedload(User.consent))
                .where(User.auth0_id == auth0_id),
            )
            user = result.scalar_one()

    # Update email if changed in Auth0 (applies to both existing users and
    # users fetched after race condition recovery)
    if email and user.email != email:
        user.email = email
        await db.flush()

    # Populate cache
    if auth_cache:
        await auth_cache.set(user, auth0_id)

    return user


async def get_or_create_dev_user(db: AsyncSession) -> User:
    """Get or create a development user for DEV_MODE."""
    dev_auth0_id = "dev|local-development-user"
    return await get_or_create_user(
        db,
        auth0_id=dev_auth0_id,
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
) -> None:
    """
    Apply rate limiting for the current request.

    Checks both per-minute and daily limits based on auth type and operation type.
    Stores rate limit info in request.state for middleware to add headers.
    Raises RateLimitExceededError if limit exceeded (handled by exception handler).
    """
    auth_type = getattr(request.state, "auth_type", AuthType.AUTH0)
    operation_type = get_operation_type(request.method, request.url.path)

    result = await check_rate_limit(user.id, auth_type, operation_type)

    # Store result in request.state for RateLimitHeadersMiddleware
    request.state.rate_limit_info = {
        "limit": result.limit,
        "remaining": result.remaining,
        "reset": result.reset,
    }

    if not result.allowed:
        raise RateLimitExceededError(result)


async def _authenticate_user(
    credentials: HTTPAuthorizationCredentials | None,
    db: AsyncSession,
    settings: Settings,
    request: Request,
    *,
    allow_pat: bool = True,
) -> User | CachedUser:
    """
    Internal: authenticate user without consent check.

    Supports both:
    - Auth0 JWTs (for web UI)
    - Personal Access Tokens (PATs) starting with 'bm_' (for CLI/MCP/scripts)

    In DEV_MODE, bypasses auth and returns a test user.

    Sets request.state.auth_type for rate limiting.

    Args:
        credentials: HTTP Authorization header credentials.
        db: Database session.
        settings: Application settings.
        request: FastAPI request object (for storing auth_type).
        allow_pat: If False, reject PAT tokens with 403 to help prevent unintended
            programmatic use. Note: does not block Auth0 JWTs used outside the browser.
    """
    if settings.dev_mode:
        # Default to AUTH0 in dev mode for rate limiting
        request.state.auth_type = AuthType.AUTH0
        return await get_or_create_dev_user(db)

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # Route to appropriate validation based on token prefix
    if token.startswith("bm_"):
        if not allow_pat:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This endpoint is not available for API tokens. Please use the web interface.",  # noqa: E501
            )
        request.state.auth_type = AuthType.PAT
        return await validate_pat(db, token)

    # Auth0 JWT validation
    request.state.auth_type = AuthType.AUTH0
    payload = decode_jwt(token, settings)

    # Extract user info from JWT claims
    auth0_id = payload.get("sub")
    if not auth0_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing sub claim",
            headers={"WWW-Authenticate": "Bearer"},
        )

    email = payload.get("email")
    return await get_or_create_user(db, auth0_id=auth0_id, email=email)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
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
    user = await _authenticate_user(credentials, db, settings, request)
    await _apply_rate_limit(user, request)
    _check_consent(user, settings)
    return user


async def get_current_user_without_consent(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> User | CachedUser:
    """
    Dependency that validates the token, applies rate limiting, and returns the user.

    Returns User ORM object on cache miss, CachedUser on cache hit.
    Auth + rate limiting, no consent check (for exempt routes like consent endpoints).
    """
    user = await _authenticate_user(credentials, db, settings, request)
    await _apply_rate_limit(user, request)
    return user


async def get_current_user_auth0_only(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> User | CachedUser:
    """
    Dependency: Auth0-only auth + rate limiting + consent check (blocks PAT access).

    Returns User ORM object on cache miss, CachedUser on cache hit.
    Use this to block PAT access and help prevent unintended programmatic use.

    Examples:
        - /bookmarks/fetch-metadata (blocks PAT-based SSRF abuse)
        - /tokens/* (prevents compromised PAT from creating more tokens)
        - /settings/* (account management)

    Note: This does NOT prevent all programmatic access. Users can still extract
    their Auth0 JWT from browser DevTools and use it in scripts. Rate limiting
    provides the additional layer to cap any abuse.

    Returns 403 Forbidden for PAT tokens.
    Returns 429 if rate limit exceeded.
    Returns 451 if user hasn't consented to privacy policy/terms.
    Use get_current_user_auth0_only_without_consent for consent-exempt routes.
    """
    user = await _authenticate_user(credentials, db, settings, request, allow_pat=False)
    await _apply_rate_limit(user, request)
    _check_consent(user, settings)
    return user


async def get_current_user_auth0_only_without_consent(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> User | CachedUser:
    """
    Dependency: Auth0-only auth + rate limiting, no consent check (blocks PAT access).

    Use to block PAT access on routes that must be accessible without consent
    (e.g., consent/settings pages).

    See get_current_user_auth0_only for details on what this does and doesn't prevent.
    """
    user = await _authenticate_user(credentials, db, settings, request, allow_pat=False)
    await _apply_rate_limit(user, request)
    return user
