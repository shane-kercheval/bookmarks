"""Tests for user consent endpoints."""
from collections.abc import AsyncGenerator
from datetime import datetime, UTC
from typing import TYPE_CHECKING

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.policy_versions import PRIVACY_POLICY_VERSION, TERMS_OF_SERVICE_VERSION
from models.user import User
from models.user_consent import UserConsent

if TYPE_CHECKING:
    from core.config import Settings


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
    from api.dependencies import get_current_user_without_consent
    from api.main import app

    async def override_get_current_user_without_consent() -> User:
        return test_user

    app.dependency_overrides[get_current_user_without_consent] = (
        override_get_current_user_without_consent
    )

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


class TestPolicyVersions:
    """Tests for GET /consent/versions endpoint (public, no auth required)."""

    async def test__get_versions__returns_current_versions(
        self,
        client: AsyncClient,
    ) -> None:
        """Returns current policy versions without requiring authentication."""
        response = await client.get("/consent/versions")

        assert response.status_code == 200
        data = response.json()
        assert data["privacy_policy_version"] == PRIVACY_POLICY_VERSION
        assert data["terms_of_service_version"] == TERMS_OF_SERVICE_VERSION


class TestPolicyVersionConstants:
    """Tests to ensure policy version constants are valid for testing."""

    def test__current_versions__are_not_the_outdated_test_version(self) -> None:
        """
        Verify the 'outdated' version used in tests differs from current constants.

        This prevents tests from silently becoming meaningless if someone
        accidentally sets the policy version constants to our test value.
        """
        outdated_test_version = "2024-01-01"
        assert outdated_test_version != PRIVACY_POLICY_VERSION, (
            f"PRIVACY_POLICY_VERSION ({PRIVACY_POLICY_VERSION}) must differ from "
            f"the outdated test version ({outdated_test_version})"
        )
        assert outdated_test_version != TERMS_OF_SERVICE_VERSION, (
            f"TERMS_OF_SERVICE_VERSION ({TERMS_OF_SERVICE_VERSION}) must differ from "
            f"the outdated test version ({outdated_test_version})"
        )

    def test__current_versions__are_valid_date_format(self) -> None:
        """Verify policy versions follow expected YYYY-MM-DD format."""
        import re

        date_pattern = r"^\d{4}-\d{2}-\d{2}$"
        assert re.match(date_pattern, PRIVACY_POLICY_VERSION), (
            f"PRIVACY_POLICY_VERSION ({PRIVACY_POLICY_VERSION}) should be YYYY-MM-DD format"
        )
        assert re.match(date_pattern, TERMS_OF_SERVICE_VERSION), (
            f"TERMS_OF_SERVICE_VERSION ({TERMS_OF_SERVICE_VERSION}) should be YYYY-MM-DD format"
        )


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
        # Verify current versions are returned (single source of truth)
        assert data["current_privacy_version"] == PRIVACY_POLICY_VERSION
        assert data["current_terms_version"] == TERMS_OF_SERVICE_VERSION

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
            privacy_policy_version=PRIVACY_POLICY_VERSION,
            terms_of_service_version=TERMS_OF_SERVICE_VERSION,
        )
        db_session.add(consent)
        await db_session.commit()

        response = await client.get("/consent/status")

        assert response.status_code == 200
        data = response.json()
        assert data["needs_consent"] is False
        assert data["current_consent"] is not None
        assert data["current_consent"]["privacy_policy_version"] == PRIVACY_POLICY_VERSION
        # Verify current versions are returned (single source of truth)
        assert data["current_privacy_version"] == PRIVACY_POLICY_VERSION
        assert data["current_terms_version"] == TERMS_OF_SERVICE_VERSION

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
            terms_of_service_version=TERMS_OF_SERVICE_VERSION,
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
            privacy_policy_version=PRIVACY_POLICY_VERSION,
            terms_of_service_version="2024-01-01",  # Old version
        )
        db_session.add(consent)
        await db_session.commit()

        response = await client.get("/consent/status")

        assert response.status_code == 200
        data = response.json()
        assert data["needs_consent"] is True
        assert data["current_consent"] is not None


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
            "privacy_policy_version": PRIVACY_POLICY_VERSION,
            "terms_of_service_version": TERMS_OF_SERVICE_VERSION,
        }

        response = await client.post("/consent/me", json=consent_data)

        assert response.status_code == 201
        data = response.json()
        assert data["user_id"] == test_user.id
        assert data["privacy_policy_version"] == PRIVACY_POLICY_VERSION
        assert data["terms_of_service_version"] == TERMS_OF_SERVICE_VERSION
        assert "consented_at" in data

        # Verify in database
        result = await db_session.execute(
            select(UserConsent).where(UserConsent.user_id == test_user.id),
        )
        db_consent = result.scalar_one()
        assert db_consent.privacy_policy_version == PRIVACY_POLICY_VERSION
        assert db_consent.terms_of_service_version == TERMS_OF_SERVICE_VERSION

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
            "privacy_policy_version": PRIVACY_POLICY_VERSION,
            "terms_of_service_version": TERMS_OF_SERVICE_VERSION,
        }

        response = await client.post("/consent/me", json=new_consent_data)

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == old_id  # Same ID (updated, not created)
        assert data["privacy_policy_version"] == PRIVACY_POLICY_VERSION
        assert data["terms_of_service_version"] == TERMS_OF_SERVICE_VERSION

        # Verify only one consent record exists
        result = await db_session.execute(
            select(UserConsent).where(UserConsent.user_id == test_user.id),
        )
        all_consents = result.scalars().all()
        assert len(all_consents) == 1
        assert all_consents[0].privacy_policy_version == PRIVACY_POLICY_VERSION

    async def test__record_consent__captures_ip_and_user_agent(
        self,
        client: AsyncClient,
    ) -> None:
        """Captures IP address and user agent from request headers."""
        consent_data = {
            "privacy_policy_version": PRIVACY_POLICY_VERSION,
            "terms_of_service_version": TERMS_OF_SERVICE_VERSION,
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
            "privacy_policy_version": PRIVACY_POLICY_VERSION,
            "terms_of_service_version": TERMS_OF_SERVICE_VERSION,
        }

        # Note: test client may or may not have client IP
        response = await client.post("/consent/me", json=consent_data)

        # Should succeed even if IP/user agent are null
        assert response.status_code == 201
        data = response.json()
        assert data["privacy_policy_version"] == PRIVACY_POLICY_VERSION
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
            json={"terms_of_service_version": TERMS_OF_SERVICE_VERSION},
        )
        assert response.status_code == 422

        # Missing terms_of_service_version
        response = await client.post(
            "/consent/me",
            json={"privacy_policy_version": PRIVACY_POLICY_VERSION},
        )
        assert response.status_code == 422

        # Empty string not allowed
        response = await client.post(
            "/consent/me",
            json={
                "privacy_policy_version": "",
                "terms_of_service_version": TERMS_OF_SERVICE_VERSION,
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
            privacy_policy_version=PRIVACY_POLICY_VERSION,
            terms_of_service_version=TERMS_OF_SERVICE_VERSION,
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
            "privacy_policy_version": PRIVACY_POLICY_VERSION,
            "terms_of_service_version": TERMS_OF_SERVICE_VERSION,
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
            "privacy_policy_version": PRIVACY_POLICY_VERSION,
            "terms_of_service_version": TERMS_OF_SERVICE_VERSION,
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
            "privacy_policy_version": PRIVACY_POLICY_VERSION,
            "terms_of_service_version": TERMS_OF_SERVICE_VERSION,
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


class TestConsentEnforcement:
    """Tests for backend consent enforcement via get_current_user."""

    @pytest.fixture
    def mock_settings_no_dev_mode(self) -> "Settings":
        """Create mock settings with dev_mode=False for testing consent enforcement."""
        from core.config import Settings
        from unittest.mock import MagicMock

        settings = MagicMock(spec=Settings)
        settings.dev_mode = False
        settings.frontend_url = "http://localhost:5173"
        settings.api_url = "http://localhost:8000"
        return settings

    @pytest.fixture
    def mock_settings_dev_mode(self) -> "Settings":
        """Create mock settings with dev_mode=True for testing DEV_MODE bypass."""
        from core.config import Settings
        from unittest.mock import MagicMock

        settings = MagicMock(spec=Settings)
        settings.dev_mode = True
        return settings

    @pytest.fixture
    def user_without_consent(self, test_user: User) -> User:
        """User without consent record."""
        test_user.consent = None
        return test_user

    @pytest.fixture
    def user_with_valid_consent(self, test_user: User) -> User:
        """User with valid consent matching current versions."""
        test_user.consent = UserConsent(
            id=1,
            user_id=test_user.id,
            consented_at=datetime.now(UTC),
            privacy_policy_version=PRIVACY_POLICY_VERSION,
            terms_of_service_version=TERMS_OF_SERVICE_VERSION,
        )
        return test_user

    @pytest.fixture
    def user_with_outdated_privacy(self, test_user: User) -> User:
        """User with outdated privacy policy version."""
        test_user.consent = UserConsent(
            id=1,
            user_id=test_user.id,
            consented_at=datetime.now(UTC),
            privacy_policy_version="2024-01-01",  # Outdated
            terms_of_service_version=TERMS_OF_SERVICE_VERSION,
        )
        return test_user

    @pytest.fixture
    def user_with_outdated_terms(self, test_user: User) -> User:
        """User with outdated terms version."""
        test_user.consent = UserConsent(
            id=1,
            user_id=test_user.id,
            consented_at=datetime.now(UTC),
            privacy_policy_version=PRIVACY_POLICY_VERSION,
            terms_of_service_version="2024-01-01",  # Outdated
        )
        return test_user

    @pytest.fixture
    def user_with_both_outdated(self, test_user: User) -> User:
        """User with both policy versions outdated."""
        test_user.consent = UserConsent(
            id=1,
            user_id=test_user.id,
            consented_at=datetime.now(UTC),
            privacy_policy_version="2024-01-01",  # Outdated
            terms_of_service_version="2024-01-01",  # Outdated
        )
        return test_user

    def test__check_consent__raises_451_without_consent(
        self,
        user_without_consent: User,
        mock_settings_no_dev_mode: "Settings",
    ) -> None:
        """Returns HTTP 451 when user has no consent record."""
        from core.auth import _check_consent
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _check_consent(user_without_consent, mock_settings_no_dev_mode)

        assert exc_info.value.status_code == 451
        assert exc_info.value.detail["error"] == "consent_required"
        assert "Privacy Policy" in exc_info.value.detail["message"]

    def test__check_consent__raises_451_with_outdated_privacy_version(
        self,
        user_with_outdated_privacy: User,
        mock_settings_no_dev_mode: "Settings",
    ) -> None:
        """Returns HTTP 451 when privacy policy version is outdated."""
        from core.auth import _check_consent
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _check_consent(user_with_outdated_privacy, mock_settings_no_dev_mode)

        assert exc_info.value.status_code == 451
        assert exc_info.value.detail["error"] == "consent_outdated"
        assert "updated" in exc_info.value.detail["message"]

    def test__check_consent__raises_451_with_outdated_terms_version(
        self,
        user_with_outdated_terms: User,
        mock_settings_no_dev_mode: "Settings",
    ) -> None:
        """Returns HTTP 451 when terms version is outdated."""
        from core.auth import _check_consent
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _check_consent(user_with_outdated_terms, mock_settings_no_dev_mode)

        assert exc_info.value.status_code == 451
        assert exc_info.value.detail["error"] == "consent_outdated"

    def test__check_consent__raises_451_with_both_versions_outdated(
        self,
        user_with_both_outdated: User,
        mock_settings_no_dev_mode: "Settings",
    ) -> None:
        """Returns HTTP 451 when both policy versions are outdated."""
        from core.auth import _check_consent
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _check_consent(user_with_both_outdated, mock_settings_no_dev_mode)

        assert exc_info.value.status_code == 451
        assert exc_info.value.detail["error"] == "consent_outdated"

    def test__check_consent__allows_access_with_valid_consent(
        self,
        user_with_valid_consent: User,
        mock_settings_no_dev_mode: "Settings",
    ) -> None:
        """Allows access when consent is valid and current."""
        from core.auth import _check_consent

        # Should not raise - valid consent
        _check_consent(user_with_valid_consent, mock_settings_no_dev_mode)

    def test__check_consent__bypasses_in_dev_mode(
        self,
        user_without_consent: User,
        mock_settings_dev_mode: "Settings",
    ) -> None:
        """Skips consent check in DEV_MODE."""
        from core.auth import _check_consent

        # Should not raise - DEV_MODE bypasses consent check
        _check_consent(user_without_consent, mock_settings_dev_mode)

    def test__451_response__includes_instructions_and_ai_warning(
        self,
        user_without_consent: User,
        mock_settings_no_dev_mode: "Settings",
    ) -> None:
        """451 response includes instructions for humans and AI warning."""
        from core.auth import _check_consent
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _check_consent(user_without_consent, mock_settings_no_dev_mode)

        instructions = exc_info.value.detail["instructions"]
        # Check instructions include curl example
        assert "curl -X POST" in instructions
        assert "/consent/me" in instructions
        # Check AI warning is included
        assert "AI/LLM AGENTS" in instructions
        assert "Do NOT call the consent endpoint on behalf of the user" in instructions

    def test__451_response__includes_consent_url(
        self,
        user_without_consent: User,
        mock_settings_no_dev_mode: "Settings",
    ) -> None:
        """451 response includes consent_url for programmatic handling."""
        from core.auth import _check_consent
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _check_consent(user_without_consent, mock_settings_no_dev_mode)

        assert exc_info.value.detail["consent_url"] == "/consent/status"


class TestConsentEnforcementIntegration:
    """Integration tests for consent enforcement on protected endpoints."""

    @pytest.fixture
    async def user_with_consent(
        self,
        db_session: AsyncSession,
    ) -> User:
        """Create a user with valid consent."""
        user = User(
            auth0_id="test-auth0-id-with-consent",
            email="consented@test.com",
        )
        db_session.add(user)
        await db_session.flush()

        consent = UserConsent(
            user_id=user.id,
            consented_at=datetime.now(UTC),
            privacy_policy_version=PRIVACY_POLICY_VERSION,
            terms_of_service_version=TERMS_OF_SERVICE_VERSION,
        )
        db_session.add(consent)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    @pytest.fixture
    async def user_no_consent(
        self,
        db_session: AsyncSession,
    ) -> User:
        """Create a user without consent."""
        user = User(
            auth0_id="test-auth0-id-no-consent",
            email="noconsent@test.com",
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    @pytest.fixture
    async def client_with_consent_user(
        self,
        db_session: AsyncSession,
        user_with_consent: User,
    ) -> AsyncGenerator[AsyncClient]:
        """Client with a user that has valid consent, DEV_MODE disabled."""
        from unittest.mock import MagicMock

        from api.dependencies import get_current_user, get_current_user_without_consent
        from api.main import app
        from core.auth import _check_consent
        from core.config import Settings, get_settings
        from db.session import get_async_session
        from httpx import ASGITransport
        from sqlalchemy.orm import joinedload

        # Reload user with consent eagerly loaded
        result = await db_session.execute(
            select(User)
            .options(joinedload(User.consent))
            .where(User.id == user_with_consent.id),
        )
        user = result.scalar_one()

        # Create mock settings for consent check
        original_settings = get_settings()
        mock_settings = MagicMock(spec=Settings)
        mock_settings.dev_mode = False
        mock_settings.frontend_url = original_settings.frontend_url
        mock_settings.api_url = original_settings.api_url

        async def override_get_current_user() -> User:
            # Must call _check_consent to test enforcement
            _check_consent(user, mock_settings)
            return user

        async def override_get_current_user_without_consent() -> User:
            return user

        def override_get_settings() -> Settings:
            return mock_settings

        async def override_get_async_session() -> AsyncGenerator[AsyncSession]:
            yield db_session

        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_current_user_without_consent] = (
            override_get_current_user_without_consent
        )
        app.dependency_overrides[get_settings] = override_get_settings
        app.dependency_overrides[get_async_session] = override_get_async_session

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as test_client:
            yield test_client

        app.dependency_overrides.clear()

    @pytest.fixture
    async def client_without_consent_user(
        self,
        db_session: AsyncSession,
        user_no_consent: User,
    ) -> AsyncGenerator[AsyncClient]:
        """Client with a user that has no consent, DEV_MODE disabled."""
        from unittest.mock import MagicMock

        from api.dependencies import get_current_user, get_current_user_without_consent
        from api.main import app
        from core.auth import _check_consent
        from core.config import Settings, get_settings
        from db.session import get_async_session
        from httpx import ASGITransport
        from sqlalchemy.orm import joinedload

        # Reload user with consent eagerly loaded (will be None)
        result = await db_session.execute(
            select(User)
            .options(joinedload(User.consent))
            .where(User.id == user_no_consent.id),
        )
        user = result.scalar_one()

        # Create mock settings for consent check
        original_settings = get_settings()
        mock_settings = MagicMock(spec=Settings)
        mock_settings.dev_mode = False
        mock_settings.frontend_url = original_settings.frontend_url
        mock_settings.api_url = original_settings.api_url

        async def override_get_current_user() -> User:
            # Must call _check_consent to test enforcement
            _check_consent(user, mock_settings)
            return user

        async def override_get_current_user_without_consent() -> User:
            return user

        def override_get_settings() -> Settings:
            return mock_settings

        async def override_get_async_session() -> AsyncGenerator[AsyncSession]:
            yield db_session

        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_current_user_without_consent] = (
            override_get_current_user_without_consent
        )
        app.dependency_overrides[get_settings] = override_get_settings
        app.dependency_overrides[get_async_session] = override_get_async_session

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as test_client:
            yield test_client

        app.dependency_overrides.clear()

    async def test__protected_route__returns_451_without_consent(
        self,
        client_without_consent_user: AsyncClient,
    ) -> None:
        """Protected route returns 451 when user has no consent."""
        response = await client_without_consent_user.get("/users/me")

        assert response.status_code == 451
        data = response.json()
        assert data["detail"]["error"] == "consent_required"

    async def test__protected_route__allows_access_with_valid_consent(
        self,
        client_with_consent_user: AsyncClient,
    ) -> None:
        """Protected route allows access when user has valid consent."""
        response = await client_with_consent_user.get("/users/me")

        assert response.status_code == 200
        data = response.json()
        assert "email" in data

    async def test__consent_status__works_without_consent(
        self,
        client_without_consent_user: AsyncClient,
    ) -> None:
        """GET /consent/status works without consent (exempt route)."""
        # The fixture already overrides get_current_user_without_consent
        response = await client_without_consent_user.get("/consent/status")

        assert response.status_code == 200
        data = response.json()
        assert data["needs_consent"] is True
