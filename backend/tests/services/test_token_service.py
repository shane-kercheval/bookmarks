"""Tests for token service layer functionality."""
from datetime import datetime, timedelta, UTC

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.api_token import ApiToken
from models.user import User
from services.token_service import (
    create_token,
    delete_token,
    generate_token,
    get_token_by_id,
    get_tokens,
    hash_token,
    validate_token,
)
from schemas.token import TokenCreate


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(auth0_id="test-token-user-123", email="tokens@example.com")
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def other_user(db_session: AsyncSession) -> User:
    """Create another test user for isolation tests."""
    user = User(auth0_id="other-token-user-456", email="other-tokens@example.com")
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


# =============================================================================
# generate_token Tests
# =============================================================================


def test__generate_token__returns_tuple_with_prefix() -> None:
    """Test that generate_token returns a valid tuple."""
    plaintext, token_hash, prefix = generate_token()

    assert plaintext.startswith("bm_")
    assert len(plaintext) > 20  # Should be reasonably long
    assert prefix == plaintext[:12]
    assert len(token_hash) == 64  # SHA256 hex digest


def test__generate_token__produces_unique_tokens() -> None:
    """Test that generate_token produces unique tokens."""
    tokens = [generate_token()[0] for _ in range(10)]
    assert len(set(tokens)) == 10  # All unique


# =============================================================================
# hash_token Tests
# =============================================================================


def test__hash_token__produces_consistent_hash() -> None:
    """Test that hash_token produces the same hash for the same input."""
    token = "bm_test_token_12345"
    hash1 = hash_token(token)
    hash2 = hash_token(token)

    assert hash1 == hash2
    assert len(hash1) == 64  # SHA256 hex


def test__hash_token__different_tokens_produce_different_hashes() -> None:
    """Test that different tokens produce different hashes."""
    hash1 = hash_token("bm_token_one")
    hash2 = hash_token("bm_token_two")

    assert hash1 != hash2


# =============================================================================
# create_token Tests
# =============================================================================


async def test__create_token__creates_token_with_hash(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that create_token stores hash and returns plaintext."""
    data = TokenCreate(name="Test Token")

    api_token, plaintext = await create_token(db_session, test_user.id, data)

    assert api_token.name == "Test Token"
    assert api_token.user_id == test_user.id
    assert api_token.token_hash == hash_token(plaintext)
    assert api_token.token_prefix == plaintext[:12]
    assert api_token.expires_at is None
    assert api_token.last_used_at is None


async def test__create_token__with_expiration(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that create_token sets expiration correctly."""
    data = TokenCreate(name="Expiring Token", expires_in_days=30)

    api_token, _ = await create_token(db_session, test_user.id, data)

    assert api_token.expires_at is not None
    expected_expiry = datetime.now(UTC) + timedelta(days=30)
    # Allow 1 minute tolerance
    assert abs((api_token.expires_at - expected_expiry).total_seconds()) < 60


async def test__create_token__returns_unique_tokens(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that create_token generates unique tokens each time."""
    data = TokenCreate(name="Token")

    _, plaintext1 = await create_token(db_session, test_user.id, data)
    _, plaintext2 = await create_token(db_session, test_user.id, data)

    assert plaintext1 != plaintext2


# =============================================================================
# get_tokens Tests
# =============================================================================


async def test__get_tokens__returns_user_tokens(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that get_tokens returns all tokens for a user."""
    # Create multiple tokens
    for i in range(3):
        data = TokenCreate(name=f"Token {i}")
        await create_token(db_session, test_user.id, data)
    await db_session.flush()

    tokens = await get_tokens(db_session, test_user.id)

    assert len(tokens) == 3
    assert all(t.user_id == test_user.id for t in tokens)


async def test__get_tokens__returns_empty_list_when_no_tokens(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that get_tokens returns empty list for user with no tokens."""
    tokens = await get_tokens(db_session, test_user.id)

    assert tokens == []


async def test__get_tokens__orders_by_created_at_desc(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that get_tokens returns tokens in reverse chronological order."""
    for name in ["First", "Second", "Third"]:
        data = TokenCreate(name=name)
        await create_token(db_session, test_user.id, data)
    await db_session.flush()

    tokens = await get_tokens(db_session, test_user.id)

    # Most recently created should be first
    assert tokens[0].name == "Third"
    assert tokens[1].name == "Second"
    assert tokens[2].name == "First"


async def test__get_tokens__user_isolation(
    db_session: AsyncSession,
    test_user: User,
    other_user: User,
) -> None:
    """Test that get_tokens only returns tokens for the specified user."""
    await create_token(db_session, test_user.id, TokenCreate(name="User1 Token"))
    await create_token(db_session, other_user.id, TokenCreate(name="User2 Token"))
    await db_session.flush()

    user1_tokens = await get_tokens(db_session, test_user.id)
    user2_tokens = await get_tokens(db_session, other_user.id)

    assert len(user1_tokens) == 1
    assert len(user2_tokens) == 1
    assert user1_tokens[0].name == "User1 Token"
    assert user2_tokens[0].name == "User2 Token"


# =============================================================================
# get_token_by_id Tests
# =============================================================================


async def test__get_token_by_id__returns_token_if_exists(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that get_token_by_id returns the token if it exists."""
    api_token, _ = await create_token(
        db_session, test_user.id, TokenCreate(name="Test"),
    )
    await db_session.flush()

    result = await get_token_by_id(db_session, test_user.id, api_token.id)

    assert result is not None
    assert result.id == api_token.id
    assert result.name == "Test"


async def test__get_token_by_id__returns_none_if_not_exists(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that get_token_by_id returns None for non-existent token."""
    result = await get_token_by_id(db_session, test_user.id, 99999)

    assert result is None


async def test__get_token_by_id__returns_none_for_other_users_token(
    db_session: AsyncSession,
    test_user: User,
    other_user: User,
) -> None:
    """Test that get_token_by_id enforces user scope."""
    api_token, _ = await create_token(
        db_session, other_user.id, TokenCreate(name="Other's Token"),
    )
    await db_session.flush()

    # Try to get other user's token
    result = await get_token_by_id(db_session, test_user.id, api_token.id)

    assert result is None


# =============================================================================
# delete_token Tests
# =============================================================================


async def test__delete_token__removes_token_and_returns_true(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that delete_token removes the token and returns True."""
    api_token, _ = await create_token(
        db_session, test_user.id, TokenCreate(name="To Delete"),
    )
    await db_session.flush()
    token_id = api_token.id

    result = await delete_token(db_session, test_user.id, token_id)
    await db_session.flush()

    assert result is True
    # Verify token is gone
    check = await get_token_by_id(db_session, test_user.id, token_id)
    assert check is None


async def test__delete_token__returns_false_if_not_exists(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that delete_token returns False for non-existent token."""
    result = await delete_token(db_session, test_user.id, 99999)

    assert result is False


async def test__delete_token__enforces_user_scope(
    db_session: AsyncSession,
    test_user: User,
    other_user: User,
) -> None:
    """Test that delete_token only deletes tokens owned by the user."""
    api_token, _ = await create_token(
        db_session, other_user.id, TokenCreate(name="Other's Token"),
    )
    await db_session.flush()

    # Try to delete other user's token
    result = await delete_token(db_session, test_user.id, api_token.id)

    assert result is False
    # Token should still exist
    check = await get_token_by_id(db_session, other_user.id, api_token.id)
    assert check is not None


# =============================================================================
# validate_token Tests
# =============================================================================


async def test__validate_token__returns_token_for_valid_plaintext(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that validate_token returns the token for valid plaintext."""
    api_token, plaintext = await create_token(
        db_session, test_user.id, TokenCreate(name="Valid Token"),
    )
    await db_session.flush()

    result = await validate_token(db_session, plaintext)

    assert result is not None
    assert result.id == api_token.id


async def test__validate_token__returns_none_for_invalid_token(
    db_session: AsyncSession,
) -> None:
    """Test that validate_token returns None for invalid token."""
    result = await validate_token(db_session, "bm_invalid_token_here")
    assert result is None


async def test__validate_token__returns_none_for_expired_token(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that validate_token returns None for expired token."""
    api_token, plaintext = await create_token(
        db_session, test_user.id, TokenCreate(name="Expiring", expires_in_days=1),
    )
    # Set expiration to the past
    api_token.expires_at = datetime.now(UTC) - timedelta(hours=1)
    await db_session.flush()

    result = await validate_token(db_session, plaintext)

    assert result is None


async def test__validate_token__updates_last_used_at(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that validate_token updates last_used_at on successful validation."""
    api_token, plaintext = await create_token(
        db_session, test_user.id, TokenCreate(name="Track Usage"),
    )
    await db_session.flush()

    assert api_token.last_used_at is None

    result = await validate_token(db_session, plaintext)

    assert result is not None
    assert result.last_used_at is not None
    assert result.last_used_at <= datetime.now(UTC)


async def test__validate_token__accepts_token_without_expiration(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that validate_token accepts tokens without expiration date."""
    api_token, plaintext = await create_token(
        db_session, test_user.id, TokenCreate(name="No Expiry"),
    )
    await db_session.flush()

    assert api_token.expires_at is None

    result = await validate_token(db_session, plaintext)

    assert result is not None
    assert result.id == api_token.id


# =============================================================================
# Cascade Delete Tests
# =============================================================================


async def test__user_delete__cascades_to_tokens(
    db_session: AsyncSession,
) -> None:
    """Test that deleting a user cascades to delete their tokens."""
    user = User(auth0_id="cascade-token-user", email="cascade-tokens@example.com")
    db_session.add(user)
    await db_session.flush()

    api_token, _ = await create_token(db_session, user.id, TokenCreate(name="Token"))
    await db_session.flush()
    token_id = api_token.id

    # Delete user
    await db_session.delete(user)
    await db_session.flush()

    # Token should be gone
    result = await db_session.execute(
        select(ApiToken).where(ApiToken.id == token_id),
    )
    remaining = result.scalar_one_or_none()
    assert remaining is None
