"""Authentication module for Auth0 JWT validation and PAT support."""
import logging

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from db.session import get_async_session
from models.user import User
from services import token_service

logger = logging.getLogger(__name__)


# HTTP Bearer token scheme
security = HTTPBearer(auto_error=False)

# Cache for JWKS client (reuse across requests)
_jwks_clients: dict[str, PyJWKClient] = {}


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
) -> User:
    """
    Get existing user or create new one from Auth0 claims.

    Note: Uses flush(), not commit. Session generator handles commit at request end.
    """
    result = await db.execute(select(User).where(User.auth0_id == auth0_id))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(auth0_id=auth0_id, email=email)
        db.add(user)
        await db.flush()
    elif email and user.email != email:
        # Update email if changed in Auth0
        user.email = email
        await db.flush()

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

    # Load the user associated with this token
    result = await db.execute(select(User).where(User.id == api_token.user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> User:
    """
    Dependency that validates the token and returns the current user.

    Supports both:
    - Auth0 JWTs (for web UI)
    - Personal Access Tokens (PATs) starting with 'bm_' (for CLI/MCP/scripts)

    In DEV_MODE, bypasses auth and returns a test user.
    """
    if settings.dev_mode:
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
        return await validate_pat(db, token)

    # Auth0 JWT validation
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
