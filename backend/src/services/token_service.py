"""Service layer for API token (PAT) operations."""
import hashlib
import secrets
from datetime import datetime, timedelta, UTC

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.api_token import ApiToken
from schemas.token import TokenCreate


def generate_token() -> tuple[str, str, str]:
    """
    Generate a secure API token.

    Returns:
        Tuple of (plaintext_token, token_hash, token_prefix).
        The plaintext should only be shown once at creation.
    """
    raw = secrets.token_urlsafe(32)
    plaintext = f"bm_{raw}"
    token_hash = hashlib.sha256(plaintext.encode()).hexdigest()
    token_prefix = plaintext[:12]  # "bm_" + first 9 chars of raw
    return plaintext, token_hash, token_prefix


def hash_token(token: str) -> str:
    """Hash a token for comparison against stored hashes."""
    return hashlib.sha256(token.encode()).hexdigest()


async def create_token(
    db: AsyncSession,
    user_id: int,
    data: TokenCreate,
) -> tuple[ApiToken, str]:
    """
    Create a new API token for a user.

    Args:
        db: Database session.
        user_id: ID of the user creating the token.
        data: Token creation data (name, optional expiration).

    Returns:
        Tuple of (ApiToken model, plaintext_token).
        The plaintext token is only available at creation time.

    Note:
        Does not commit. Caller (session generator) handles commit at request end.
    """
    plaintext, token_hash, token_prefix = generate_token()

    expires_at = None
    if data.expires_in_days is not None:
        expires_at = datetime.now(UTC) + timedelta(days=data.expires_in_days)

    api_token = ApiToken(
        user_id=user_id,
        name=data.name,
        token_hash=token_hash,
        token_prefix=token_prefix,
        expires_at=expires_at,
    )
    db.add(api_token)
    await db.flush()
    await db.refresh(api_token)

    return api_token, plaintext


async def get_tokens(
    db: AsyncSession,
    user_id: int,
) -> list[ApiToken]:
    """
    Get all API tokens for a user.

    Args:
        db: Database session.
        user_id: ID of the user.

    Returns:
        List of ApiToken models (without plaintext tokens).
    """
    result = await db.execute(
        select(ApiToken)
        .where(ApiToken.user_id == user_id)
        .order_by(ApiToken.created_at.desc()),
    )
    return list(result.scalars().all())


async def get_token_by_id(
    db: AsyncSession,
    user_id: int,
    token_id: int,
) -> ApiToken | None:
    """
    Get a specific token by ID, scoped to user.

    Args:
        db: Database session.
        user_id: ID of the user.
        token_id: ID of the token.

    Returns:
        ApiToken if found and belongs to user, None otherwise.
    """
    result = await db.execute(
        select(ApiToken).where(
            ApiToken.id == token_id,
            ApiToken.user_id == user_id,
        ),
    )
    return result.scalar_one_or_none()


async def delete_token(
    db: AsyncSession,
    user_id: int,
    token_id: int,
) -> bool:
    """
    Delete (revoke) an API token.

    Args:
        db: Database session.
        user_id: ID of the user.
        token_id: ID of the token to delete.

    Returns:
        True if deleted, False if not found.

    Note:
        Does not commit. Caller (session generator) handles commit at request end.
    """
    token = await get_token_by_id(db, user_id, token_id)
    if token is None:
        return False

    await db.delete(token)
    return True


async def validate_token(
    db: AsyncSession,
    plaintext_token: str,
) -> ApiToken | None:
    """
    Validate a plaintext token and return the associated ApiToken if valid.

    Hashes the input token before database lookup, preventing timing attacks
    since attackers cannot correlate response time with token validity.

    Args:
        db: Database session.
        plaintext_token: The plaintext token to validate.

    Returns:
        ApiToken if valid and not expired, None otherwise.

    Note:
        Updates last_used_at on successful validation (uses flush, not commit).
    """
    # SECURITY: Hash before lookup to prevent timing attacks. The database query
    # time is constant regardless of whether the token exists, since we're always
    # comparing hashes (not doing early-return on plaintext mismatch).
    token_hash = hash_token(plaintext_token)

    result = await db.execute(
        select(ApiToken).where(ApiToken.token_hash == token_hash),
    )
    api_token = result.scalar_one_or_none()

    if api_token is None:
        return None

    # Check expiration
    if api_token.expires_at is not None and datetime.now(UTC) > api_token.expires_at:
        return None

    # Update last_used_at
    api_token.last_used_at = datetime.now(UTC)
    await db.flush()

    return api_token
