"""Tests for user consent endpoints."""
from collections.abc import AsyncGenerator
from datetime import datetime, UTC

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import User
from models.user_consent import UserConsent


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user for consent tests."""
    user = User(
        auth0_id="test-auth0-id-consent",
        email="consent@test.com",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def client(
    db_session: AsyncSession,
    test_user: User,
) -> AsyncGenerator[AsyncClient]:
    """Create a test client with user override for consent tests."""
    from api.dependencies import get_current_user
    from api.main import app

    async def override_get_current_user() -> User:
        return test_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    from db.session import get_async_session

    async def override_get_async_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_async_session] = override_get_async_session

    from httpx import ASGITransport

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()


class TestCheckConsentStatus:
    """Tests for GET /consent/status endpoint."""

    async def test__check_status__no_consent_returns_needs_consent_true(
        self,
        client: AsyncClient,
    ) -> None:
        """Returns needs_consent=True when user has no consent record."""
        response = await client.get("/consent/status")

        assert response.status_code == 200
        data = response.json()
        assert data["needs_consent"] is True
        assert data["current_consent"] is None

    async def test__check_status__valid_consent_returns_needs_consent_false(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Returns needs_consent=False when consent exists with current versions."""
        # Create consent with current versions
        consent = UserConsent(
            user_id=test_user.id,
            consented_at=datetime.now(UTC),
            privacy_policy_version="2024-12-20",  # Current version
            terms_of_service_version="2024-12-20",  # Current version
        )
        db_session.add(consent)
        await db_session.commit()

        response = await client.get("/consent/status")

        assert response.status_code == 200
        data = response.json()
        assert data["needs_consent"] is False
        assert data["current_consent"] is not None
        assert data["current_consent"]["privacy_policy_version"] == "2024-12-20"

    async def test__check_status__outdated_privacy_version_returns_needs_consent_true(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Returns needs_consent=True when privacy policy version is outdated."""
        # Create consent with old privacy policy version
        consent = UserConsent(
            user_id=test_user.id,
            consented_at=datetime.now(UTC),
            privacy_policy_version="2024-01-01",  # Old version
            terms_of_service_version="2024-12-20",  # Current version
        )
        db_session.add(consent)
        await db_session.commit()

        response = await client.get("/consent/status")

        assert response.status_code == 200
        data = response.json()
        assert data["needs_consent"] is True
        assert data["current_consent"] is not None

    async def test__check_status__outdated_terms_version_returns_needs_consent_true(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Returns needs_consent=True when ToS version is outdated."""
        # Create consent with old ToS version
        consent = UserConsent(
            user_id=test_user.id,
            consented_at=datetime.now(UTC),
            privacy_policy_version="2024-12-20",  # Current version
            terms_of_service_version="2024-01-01",  # Old version
        )
        db_session.add(consent)
        await db_session.commit()

        response = await client.get("/consent/status")

        assert response.status_code == 200
        data = response.json()
        assert data["needs_consent"] is True
        assert data["current_consent"] is not None


class TestGetConsent:
    """Tests for GET /consent/me endpoint."""

    async def test__get_consent__no_consent_returns_404(
        self,
        client: AsyncClient,
    ) -> None:
        """Returns 404 when user has no consent record."""
        response = await client.get("/consent/me")

        assert response.status_code == 404
        assert "not consented" in response.json()["detail"].lower()

    async def test__get_consent__returns_existing_consent(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Returns consent record when it exists."""
        # Create consent record
        consent = UserConsent(
            user_id=test_user.id,
            consented_at=datetime.now(UTC),
            privacy_policy_version="2024-12-20",
            terms_of_service_version="2024-12-20",
            ip_address="192.168.1.1",
            user_agent="Test Browser",
        )
        db_session.add(consent)
        await db_session.commit()

        response = await client.get("/consent/me")

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == test_user.id
        assert data["privacy_policy_version"] == "2024-12-20"
        assert data["terms_of_service_version"] == "2024-12-20"
        assert data["ip_address"] == "192.168.1.1"
        assert data["user_agent"] == "Test Browser"
        assert "consented_at" in data


class TestRecordConsent:
    """Tests for POST /consent/me endpoint."""

    async def test__record_consent__creates_new_consent(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Creates new consent record when none exists."""
        consent_data = {
            "privacy_policy_version": "2024-12-20",
            "terms_of_service_version": "2024-12-20",
        }

        response = await client.post("/consent/me", json=consent_data)

        assert response.status_code == 201
        data = response.json()
        assert data["user_id"] == test_user.id
        assert data["privacy_policy_version"] == "2024-12-20"
        assert data["terms_of_service_version"] == "2024-12-20"
        assert "consented_at" in data

        # Verify in database
        result = await db_session.execute(
            select(UserConsent).where(UserConsent.user_id == test_user.id),
        )
        db_consent = result.scalar_one()
        assert db_consent.privacy_policy_version == "2024-12-20"
        assert db_consent.terms_of_service_version == "2024-12-20"

    async def test__record_consent__updates_existing_consent(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Updates existing consent when user re-consents."""
        # Create initial consent
        old_consent = UserConsent(
            user_id=test_user.id,
            consented_at=datetime(2024, 1, 1, tzinfo=UTC),
            privacy_policy_version="2024-01-01",
            terms_of_service_version="2024-01-01",
        )
        db_session.add(old_consent)
        await db_session.commit()
        old_id = old_consent.id

        # Update with new consent
        new_consent_data = {
            "privacy_policy_version": "2024-12-20",
            "terms_of_service_version": "2024-12-20",
        }

        response = await client.post("/consent/me", json=new_consent_data)

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == old_id  # Same ID (updated, not created)
        assert data["privacy_policy_version"] == "2024-12-20"
        assert data["terms_of_service_version"] == "2024-12-20"

        # Verify only one consent record exists
        result = await db_session.execute(
            select(UserConsent).where(UserConsent.user_id == test_user.id),
        )
        all_consents = result.scalars().all()
        assert len(all_consents) == 1
        assert all_consents[0].privacy_policy_version == "2024-12-20"

    async def test__record_consent__captures_ip_and_user_agent(
        self,
        client: AsyncClient,
    ) -> None:
        """Captures IP address and user agent from request headers."""
        consent_data = {
            "privacy_policy_version": "2024-12-20",
            "terms_of_service_version": "2024-12-20",
        }

        # Send request with custom headers
        response = await client.post(
            "/consent/me",
            json=consent_data,
            headers={
                "X-Forwarded-For": "203.0.113.42, 198.51.100.1",
                "User-Agent": "Mozilla/5.0 Test Browser",
            },
        )

        assert response.status_code == 201
        data = response.json()
        # Should capture first IP from X-Forwarded-For (client IP)
        assert data["ip_address"] == "203.0.113.42"
        assert data["user_agent"] == "Mozilla/5.0 Test Browser"

    async def test__record_consent__handles_missing_ip_gracefully(
        self,
        client: AsyncClient,
    ) -> None:
        """Handles missing IP/user agent gracefully (still creates consent)."""
        consent_data = {
            "privacy_policy_version": "2024-12-20",
            "terms_of_service_version": "2024-12-20",
        }

        # Note: test client may or may not have client IP
        response = await client.post("/consent/me", json=consent_data)

        # Should succeed even if IP/user agent are null
        assert response.status_code == 201
        data = response.json()
        assert data["privacy_policy_version"] == "2024-12-20"
        # IP may be None, but that's okay
        assert "ip_address" in data

    async def test__record_consent__validates_required_fields(
        self,
        client: AsyncClient,
    ) -> None:
        """Validates that version fields are required."""
        # Missing privacy_policy_version
        response = await client.post(
            "/consent/me",
            json={"terms_of_service_version": "2024-12-20"},
        )
        assert response.status_code == 422

        # Missing terms_of_service_version
        response = await client.post(
            "/consent/me",
            json={"privacy_policy_version": "2024-12-20"},
        )
        assert response.status_code == 422

        # Empty string not allowed
        response = await client.post(
            "/consent/me",
            json={
                "privacy_policy_version": "",
                "terms_of_service_version": "2024-12-20",
            },
        )
        assert response.status_code == 422


class TestConsentCascadeDelete:
    """Tests for cascade delete behavior."""

    async def test__user_delete__cascades_to_consent(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Deleting user cascades to delete their consent record."""
        # Create consent
        consent = UserConsent(
            user_id=test_user.id,
            consented_at=datetime.now(UTC),
            privacy_policy_version="2024-12-20",
            terms_of_service_version="2024-12-20",
        )
        db_session.add(consent)
        await db_session.commit()
        consent_id = consent.id

        # Delete user
        await db_session.delete(test_user)
        await db_session.commit()

        # Verify consent was deleted
        result = await db_session.execute(
            select(UserConsent).where(UserConsent.id == consent_id),
        )
        deleted_consent = result.scalar_one_or_none()
        assert deleted_consent is None


class TestIPDetection:
    """Tests for IP address detection logic."""

    async def test__ip_detection__prefers_x_forwarded_for(
        self,
        client: AsyncClient,
    ) -> None:
        """Prefers X-Forwarded-For header (for proxied requests)."""
        consent_data = {
            "privacy_policy_version": "2024-12-20",
            "terms_of_service_version": "2024-12-20",
        }

        response = await client.post(
            "/consent/me",
            json=consent_data,
            headers={
                "X-Forwarded-For": "10.0.0.1, 192.168.1.1",
                "X-Real-IP": "172.16.0.1",  # Should be ignored
            },
        )

        data = response.json()
        # Should use first IP from X-Forwarded-For
        assert data["ip_address"] == "10.0.0.1"

    async def test__ip_detection__falls_back_to_x_real_ip(
        self,
        client: AsyncClient,
    ) -> None:
        """Falls back to X-Real-IP when X-Forwarded-For not present."""
        consent_data = {
            "privacy_policy_version": "2024-12-20",
            "terms_of_service_version": "2024-12-20",
        }

        response = await client.post(
            "/consent/me",
            json=consent_data,
            headers={
                "X-Real-IP": "172.16.0.1",
            },
        )

        data = response.json()
        assert data["ip_address"] == "172.16.0.1"

    async def test__ip_detection__handles_ipv6(
        self,
        client: AsyncClient,
    ) -> None:
        """Handles IPv6 addresses correctly."""
        consent_data = {
            "privacy_policy_version": "2024-12-20",
            "terms_of_service_version": "2024-12-20",
        }

        ipv6_address = "2001:0db8:85a3:0000:0000:8a2e:0370:7334"
        response = await client.post(
            "/consent/me",
            json=consent_data,
            headers={
                "X-Forwarded-For": ipv6_address,
            },
        )

        data = response.json()
        assert data["ip_address"] == ipv6_address
