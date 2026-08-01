"""
Tests for API token (PAT) endpoints.

Tests cover token creation, listing, deletion, and authentication flow.
"""
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, UTC
from uuid import UUID

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from core.policy_versions import PRIVACY_POLICY_VERSION, TERMS_OF_SERVICE_VERSION
from models.api_token import ApiToken
from models.user import User

from core.tier_limits import Tier, TierLimits
from models.user_consent import UserConsent
from services.token_service import hash_token


async def add_consent_for_user(db_session: AsyncSession, user: User) -> None:
    """Add valid consent record for a user (required for non-dev mode tests)."""
    consent = UserConsent(
        user_id=user.id,
        consented_at=datetime.now(UTC),
        privacy_policy_version=PRIVACY_POLICY_VERSION,
        terms_of_service_version=TERMS_OF_SERVICE_VERSION,
    )
    db_session.add(consent)
    await db_session.flush()


async def test_create_token(client: AsyncClient, db_session: AsyncSession) -> None:
    """Test creating a new API token returns plaintext and metadata."""
    response = await client.post(
        "/tokens/",
        json={"name": "CLI Token"},
    )
    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "CLI Token"
    assert "token" in data  # Plaintext token
    assert data["token"].startswith("bm_")
    assert data["token_prefix"] == data["token"][:12]
    assert data["expires_at"] is None
    assert "id" in data
    assert "created_at" in data

    # Verify in database - should store hash, not plaintext
    result = await db_session.execute(select(ApiToken).where(ApiToken.id == UUID(data["id"])))
    api_token = result.scalar_one()
    assert api_token.token_hash == hash_token(data["token"])
    assert api_token.name == "CLI Token"


async def test_create_token_with_expiration(client: AsyncClient) -> None:
    """Test creating a token with expiration date."""
    response = await client.post(
        "/tokens/",
        json={"name": "Expiring Token", "expires_in_days": 30},
    )
    assert response.status_code == 201

    data = response.json()
    assert data["expires_at"] is not None

    # Verify expiration is approximately 30 days from now
    # Parse the ISO format datetime (Python 3.11+ handles "Z" suffix)
    expires_at_str = data["expires_at"].replace("Z", "+00:00")
    expires_at = datetime.fromisoformat(expires_at_str)
    expected_expiry = datetime.now(UTC) + timedelta(days=30)
    # Allow 1 minute tolerance
    assert abs((expires_at - expected_expiry).total_seconds()) < 60


async def test_create_token_validates_name(client: AsyncClient) -> None:
    """Test that token name is required and validated."""
    # Empty name
    response = await client.post(
        "/tokens/",
        json={"name": ""},
    )
    assert response.status_code == 422

    # Missing name
    response = await client.post(
        "/tokens/",
        json={},
    )
    assert response.status_code == 422


async def test_create_token_validates_expiration(client: AsyncClient) -> None:
    """Test that expiration days must be within valid range."""
    # Zero days
    response = await client.post(
        "/tokens/",
        json={"name": "Test", "expires_in_days": 0},
    )
    assert response.status_code == 422

    # Over 365 days
    response = await client.post(
        "/tokens/",
        json={"name": "Test", "expires_in_days": 400},
    )
    assert response.status_code == 422


async def test_list_tokens(client: AsyncClient) -> None:
    """Test listing tokens returns metadata without plaintext."""
    # Create some tokens
    tokens_created = []
    for i in range(3):
        response = await client.post(
            "/tokens/",
            json={"name": f"Token {i}"},
        )
        assert response.status_code == 201
        tokens_created.append(response.json())

    # List tokens
    response = await client.get("/tokens/")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 3

    # Verify no plaintext tokens in list response
    for token in data:
        assert "token" not in token
        assert "token_prefix" in token
        assert "name" in token


async def test_delete_token(client: AsyncClient) -> None:
    """Test deleting (revoking) a token."""
    # Create a token
    create_response = await client.post(
        "/tokens/",
        json={"name": "To Delete"},
    )
    token_id = create_response.json()["id"]

    # Delete it
    response = await client.delete(f"/tokens/{token_id}")
    assert response.status_code == 204

    # Verify it's gone from list
    list_response = await client.get("/tokens/")
    token_ids = [t["id"] for t in list_response.json()]
    assert token_id not in token_ids


async def test_delete_token_not_found(client: AsyncClient) -> None:
    """Test deleting a non-existent token returns 404."""
    response = await client.delete("/tokens/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["detail"] == "Token not found"


async def test_authenticate_with_pat(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test that a valid PAT can be used for authentication."""
    # Create a token
    create_response = await client.post(
        "/tokens/",
        json={"name": "Auth Test Token"},
    )
    plaintext_token = create_response.json()["token"]

    # Get the dev user and add consent (required when dev_mode=False)
    dev_user = await db_session.execute(
        select(User).where(User.external_auth_id == "dev|local-development-user"),
    )
    user = dev_user.scalar_one()
    await add_consent_for_user(db_session, user)

    # Use the PAT to access a protected endpoint with dev_mode=False
    from api.main import app  # noqa: PLC0415

    get_settings.cache_clear()

    async def override_get_async_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    def override_get_settings() -> Settings:
        return Settings(
            database_url="postgresql://test",
            dev_mode=False,
            clerk_frontend_api="test-instance.clerk.accounts.dev",
            clerk_authorized_parties_str="http://localhost:5173",
        )

    from db.session import get_async_session  # noqa: PLC0415

    app.dependency_overrides[get_async_session] = override_get_async_session
    app.dependency_overrides[get_settings] = override_get_settings

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {plaintext_token}"},
    ) as pat_client:
        # Access bookmarks endpoint (requires auth via PAT)
        response = await pat_client.get("/bookmarks/")
        assert response.status_code == 200

    app.dependency_overrides.clear()


async def test_authenticate_with_invalid_pat(db_session: AsyncSession) -> None:
    """Test that an invalid PAT is rejected."""
    from api.main import app  # noqa: PLC0415

    get_settings.cache_clear()

    async def override_get_async_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    def override_get_settings() -> Settings:
        return Settings(
            database_url="postgresql://test",
            dev_mode=False,
            clerk_frontend_api="test-instance.clerk.accounts.dev",
            clerk_authorized_parties_str="http://localhost:5173",
        )

    from db.session import get_async_session  # noqa: PLC0415

    app.dependency_overrides[get_async_session] = override_get_async_session
    app.dependency_overrides[get_settings] = override_get_settings

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer bm_invalid_token_here"},
    ) as invalid_client:
        response = await invalid_client.get("/bookmarks/")
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid or expired token"

    app.dependency_overrides.clear()


async def test_authenticate_with_expired_pat(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test that an expired PAT is rejected."""
    # Create a token that expires in 1 day
    create_response = await client.post(
        "/tokens/",
        json={"name": "Expiring Token", "expires_in_days": 1},
    )
    token_id = create_response.json()["id"]
    plaintext_token = create_response.json()["token"]

    # Manually set the expiration to the past
    result = await db_session.execute(select(ApiToken).where(ApiToken.id == token_id))
    api_token = result.scalar_one()
    api_token.expires_at = datetime.now(UTC) - timedelta(hours=1)
    await db_session.flush()

    # Try to use the expired token
    from api.main import app  # noqa: PLC0415

    get_settings.cache_clear()

    async def override_get_async_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    def override_get_settings() -> Settings:
        return Settings(
            database_url="postgresql://test",
            dev_mode=False,
            clerk_frontend_api="test-instance.clerk.accounts.dev",
            clerk_authorized_parties_str="http://localhost:5173",
        )

    from db.session import get_async_session  # noqa: PLC0415

    app.dependency_overrides[get_async_session] = override_get_async_session
    app.dependency_overrides[get_settings] = override_get_settings

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {plaintext_token}"},
    ) as expired_client:
        response = await expired_client.get("/bookmarks/")
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid or expired token"

    app.dependency_overrides.clear()


async def test_pat_updates_last_used_at(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test that using a PAT updates last_used_at timestamp."""
    # Create a token
    create_response = await client.post(
        "/tokens/",
        json={"name": "Track Usage Token"},
    )
    token_id = create_response.json()["id"]
    plaintext_token = create_response.json()["token"]

    # Verify last_used_at is initially None
    result = await db_session.execute(select(ApiToken).where(ApiToken.id == token_id))
    api_token = result.scalar_one()
    assert api_token.last_used_at is None

    # Use the token
    from api.main import app  # noqa: PLC0415

    get_settings.cache_clear()

    async def override_get_async_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    def override_get_settings() -> Settings:
        return Settings(
            database_url="postgresql://test",
            dev_mode=False,
            clerk_frontend_api="test-instance.clerk.accounts.dev",
            clerk_authorized_parties_str="http://localhost:5173",
        )

    from db.session import get_async_session  # noqa: PLC0415

    app.dependency_overrides[get_async_session] = override_get_async_session
    app.dependency_overrides[get_settings] = override_get_settings

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {plaintext_token}"},
    ) as pat_client:
        await pat_client.get("/bookmarks/")

    # Refresh and check last_used_at is now set
    await db_session.refresh(api_token)
    assert api_token.last_used_at is not None
    assert api_token.last_used_at <= datetime.now(UTC)

    app.dependency_overrides.clear()


# =============================================================================
# Rename Token Tests
# =============================================================================


async def test_rename_token_success(client: AsyncClient) -> None:
    """Test renaming a token updates the name."""
    create_response = await client.post(
        "/tokens/",
        json={"name": "Original Name"},
    )
    token_id = create_response.json()["id"]

    response = await client.patch(
        f"/tokens/{token_id}",
        json={"new_name": "Updated Name"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["id"] == token_id
    assert "token" not in data  # Should not expose plaintext

    # Verify via list endpoint
    list_response = await client.get("/tokens/")
    token = next(t for t in list_response.json() if t["id"] == token_id)
    assert token["name"] == "Updated Name"


async def test_rename_token_not_found(client: AsyncClient) -> None:
    """Test renaming a non-existent token returns 404."""
    response = await client.patch(
        "/tokens/00000000-0000-0000-0000-000000000000",
        json={"new_name": "New Name"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Token not found"


async def test_rename_token_other_users_token(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test that renaming another user's token returns 404."""
    # Create a token owned by a different user directly at model level
    other_user = User(external_auth_id="other-rename-user", email="other-rename@example.com", tier=Tier.FREE.value)
    db_session.add(other_user)
    await db_session.flush()

    other_token = ApiToken(
        user_id=other_user.id,
        name="Other's Token",
        token_hash="fake_hash_for_test",
        token_prefix="bm_fake12345",
    )
    db_session.add(other_token)
    await db_session.flush()

    response = await client.patch(
        f"/tokens/{other_token.id}",
        json={"new_name": "Hijacked Name"},
    )
    assert response.status_code == 404


async def test_rename_token_validates_name(client: AsyncClient) -> None:
    """Test that rename validates the new name."""
    create_response = await client.post(
        "/tokens/",
        json={"name": "Test Token"},
    )
    token_id = create_response.json()["id"]

    # Empty name
    response = await client.patch(
        f"/tokens/{token_id}",
        json={"new_name": ""},
    )
    assert response.status_code == 422

    # Whitespace-only name (stripped to empty)
    response = await client.patch(
        f"/tokens/{token_id}",
        json={"new_name": "   "},
    )
    assert response.status_code == 422

    # Name too long
    response = await client.patch(
        f"/tokens/{token_id}",
        json={"new_name": "x" * 101},
    )
    assert response.status_code == 422


async def test_rename_token_strips_whitespace(client: AsyncClient) -> None:
    """Test that rename strips leading/trailing whitespace."""
    create_response = await client.post(
        "/tokens/",
        json={"name": "Test Token"},
    )
    token_id = create_response.json()["id"]

    response = await client.patch(
        f"/tokens/{token_id}",
        json={"new_name": "  Trimmed Name  "},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Trimmed Name"


async def test_rename_token_same_name(client: AsyncClient) -> None:
    """Test that renaming to the same name succeeds (no-op)."""
    create_response = await client.post(
        "/tokens/",
        json={"name": "Same Name"},
    )
    token_id = create_response.json()["id"]

    response = await client.patch(
        f"/tokens/{token_id}",
        json={"new_name": "Same Name"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Same Name"


async def test_rename_token_rejects_pat_auth(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Test that PAT authentication is rejected for the rename endpoint."""
    # Create a token
    create_response = await client.post(
        "/tokens/",
        json={"name": "PAT Auth Test"},
    )
    token_id = create_response.json()["id"]
    plaintext_token = create_response.json()["token"]

    # Get the dev user and add consent (required when dev_mode=False)
    dev_user = await db_session.execute(
        select(User).where(User.external_auth_id == "dev|local-development-user"),
    )
    user = dev_user.scalar_one()
    await add_consent_for_user(db_session, user)

    from api.main import app  # noqa: PLC0415

    get_settings.cache_clear()

    async def override_get_async_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    def override_get_settings() -> Settings:
        return Settings(
            database_url="postgresql://test",
            dev_mode=False,
            clerk_frontend_api="test-instance.clerk.accounts.dev",
            clerk_authorized_parties_str="http://localhost:5173",
        )

    from db.session import get_async_session  # noqa: PLC0415

    app.dependency_overrides[get_async_session] = override_get_async_session
    app.dependency_overrides[get_settings] = override_get_settings

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {plaintext_token}"},
    ) as pat_client:
        response = await pat_client.patch(
            f"/tokens/{token_id}",
            json={"new_name": "Should Fail"},
        )
        assert response.status_code == 403

    app.dependency_overrides.clear()


# =============================================================================
# Create Token Whitespace Validation Tests
# =============================================================================


async def test_create_token_strips_whitespace(client: AsyncClient) -> None:
    """Test that token creation strips leading/trailing whitespace from name."""
    response = await client.post(
        "/tokens/",
        json={"name": "  Padded Name  "},
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Padded Name"


async def test_create_token_rejects_whitespace_only(client: AsyncClient) -> None:
    """Test that whitespace-only names are rejected on create."""
    response = await client.post(
        "/tokens/",
        json={"name": "   "},
    )
    assert response.status_code == 422


# =============================================================================
# User Scoping Tests
# =============================================================================


async def test_tokens_are_user_scoped(client: AsyncClient) -> None:
    """Test that users can only see/delete their own tokens."""
    # Create a token as the dev user
    create_response = await client.post(
        "/tokens/",
        json={"name": "User1 Token"},
    )
    token_id = create_response.json()["id"]

    # List tokens - should see our token
    list_response = await client.get("/tokens/")
    token_ids = [t["id"] for t in list_response.json()]
    assert token_id in token_ids

    # Tokens created by this user should be accessible
    # (Verifying same user can delete)
    delete_response = await client.delete(f"/tokens/{token_id}")
    assert delete_response.status_code == 204


# =============================================================================
# PAT Quota Enforcement Tests (API Layer)
# =============================================================================


async def test__create_token__quota_exceeded__returns_402(
    client: AsyncClient, low_limits: TierLimits,
) -> None:
    """Test that exceeding max_pats returns 402 with QUOTA_EXCEEDED error."""
    # Create tokens up to the limit
    for i in range(low_limits.max_pats):
        response = await client.post("/tokens/", json={"name": f"Token {i}"})
        assert response.status_code == 201

    # One more should fail with 402
    response = await client.post("/tokens/", json={"name": "Over limit"})
    assert response.status_code == 402

    data = response.json()
    assert data["error_code"] == "QUOTA_EXCEEDED"
    assert data["resource"] == "token"
    assert data["current"] == low_limits.max_pats
    assert data["limit"] == low_limits.max_pats
