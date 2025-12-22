"""Tests for Auth0-only authentication dependencies."""
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from core.policy_versions import PRIVACY_POLICY_VERSION, TERMS_OF_SERVICE_VERSION
from models.user import User
from models.user_consent import UserConsent

if TYPE_CHECKING:
    from core.config import Settings


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user for auth tests."""
    user = User(
        auth0_id="test-auth0-id-auth",
        email="auth@test.com",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_user_with_consent(db_session: AsyncSession) -> User:
    """Create a test user with valid consent."""
    user = User(
        auth0_id="test-auth0-id-auth-consent",
        email="authconsent@test.com",
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
def mock_settings_no_dev_mode() -> "Settings":
    """Create mock settings with dev_mode=False."""
    from core.config import Settings

    settings = MagicMock(spec=Settings)
    settings.dev_mode = False
    settings.frontend_url = "http://localhost:5173"
    settings.api_url = "http://localhost:8000"
    return settings


@pytest.fixture
def mock_settings_dev_mode() -> "Settings":
    """Create mock settings with dev_mode=True."""
    from core.config import Settings

    settings = MagicMock(spec=Settings)
    settings.dev_mode = True
    return settings


class TestAuthenticateUserAllowPat:
    """Tests for _authenticate_user with allow_pat parameter."""

    @pytest.mark.asyncio
    async def test__allow_pat_true__accepts_pat_token(
        self,
        db_session: AsyncSession,
        test_user: User,
        mock_settings_no_dev_mode: "Settings",
    ) -> None:
        """When allow_pat=True (default), PAT tokens are accepted."""
        from unittest.mock import AsyncMock, patch

        from core.auth import _authenticate_user

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="bm_valid_token",
        )

        # Mock validate_pat to return our test user
        with patch(
            "core.auth.validate_pat",
            new_callable=AsyncMock,
            return_value=test_user,
        ):
            result = await _authenticate_user(
                credentials, db_session, mock_settings_no_dev_mode, allow_pat=True,
            )

        assert result.id == test_user.id

    @pytest.mark.asyncio
    async def test__allow_pat_false__rejects_pat_token_with_403(
        self,
        db_session: AsyncSession,
        mock_settings_no_dev_mode: "Settings",
    ) -> None:
        """When allow_pat=False, PAT tokens are rejected with 403."""
        from core.auth import _authenticate_user

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="bm_any_token",
        )

        with pytest.raises(HTTPException) as exc_info:
            await _authenticate_user(
                credentials, db_session, mock_settings_no_dev_mode, allow_pat=False,
            )

        assert exc_info.value.status_code == 403
        assert "not available for API tokens" in exc_info.value.detail
        assert "web interface" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test__allow_pat_false__accepts_auth0_jwt(
        self,
        db_session: AsyncSession,
        test_user: User,
        mock_settings_no_dev_mode: "Settings",
    ) -> None:
        """When allow_pat=False, Auth0 JWTs are still accepted."""
        from unittest.mock import patch

        from core.auth import _authenticate_user

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.valid_jwt",
        )

        # Mock decode_jwt to return valid payload
        mock_payload = {"sub": test_user.auth0_id, "email": test_user.email}
        with patch("core.auth.decode_jwt", return_value=mock_payload):
            result = await _authenticate_user(
                credentials, db_session, mock_settings_no_dev_mode, allow_pat=False,
            )

        assert result.auth0_id == test_user.auth0_id

    @pytest.mark.asyncio
    async def test__allow_pat_false__dev_mode_bypasses_check(
        self,
        db_session: AsyncSession,
        mock_settings_dev_mode: "Settings",
    ) -> None:
        """In DEV_MODE, returns dev user regardless of allow_pat setting."""
        from core.auth import _authenticate_user

        # Even with a PAT-looking token, dev mode should bypass and return dev user
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="bm_should_be_rejected_but_dev_mode",
        )

        result = await _authenticate_user(
            credentials, db_session, mock_settings_dev_mode, allow_pat=False,
        )

        # Should return dev user, not raise 403
        assert result.auth0_id == "dev|local-development-user"

    @pytest.mark.asyncio
    async def test__no_credentials__returns_401(
        self,
        db_session: AsyncSession,
        mock_settings_no_dev_mode: "Settings",
    ) -> None:
        """Returns 401 when no credentials provided."""
        from core.auth import _authenticate_user

        with pytest.raises(HTTPException) as exc_info:
            await _authenticate_user(
                None, db_session, mock_settings_no_dev_mode, allow_pat=False,
            )

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Not authenticated"


class TestGetCurrentUserAuth0Only:
    """Tests for get_current_user_auth0_only dependency."""

    @pytest.mark.asyncio
    async def test__with_pat__returns_403(
        self,
        db_session: AsyncSession,
        mock_settings_no_dev_mode: "Settings",
    ) -> None:
        """PAT tokens are rejected with 403 before consent check."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="bm_token_should_fail",
        )

        # We need to call the internal logic directly since the dependency
        # uses FastAPI's Depends which we can't easily invoke in unit tests.
        # The dependency just calls _authenticate_user with allow_pat=False
        # and then _check_consent, so we test that flow.
        from core.auth import _authenticate_user

        with pytest.raises(HTTPException) as exc_info:
            await _authenticate_user(
                credentials, db_session, mock_settings_no_dev_mode, allow_pat=False,
            )

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test__with_auth0_jwt_and_valid_consent__returns_user(
        self,
        db_session: AsyncSession,
        test_user_with_consent: User,
        mock_settings_no_dev_mode: "Settings",
    ) -> None:
        """Auth0 JWT with valid consent returns user successfully."""
        from unittest.mock import patch

        from core.auth import _authenticate_user, _check_consent

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.valid",
        )

        mock_payload = {
            "sub": test_user_with_consent.auth0_id,
            "email": test_user_with_consent.email,
        }
        with patch("core.auth.decode_jwt", return_value=mock_payload):
            user = await _authenticate_user(
                credentials, db_session, mock_settings_no_dev_mode, allow_pat=False,
            )

        # Reload user with consent for check
        from sqlalchemy import select
        from sqlalchemy.orm import joinedload

        result = await db_session.execute(
            select(User).options(joinedload(User.consent)).where(User.id == user.id),
        )
        user_with_consent = result.scalar_one()

        # Should not raise - valid consent
        _check_consent(user_with_consent, mock_settings_no_dev_mode)

    @pytest.mark.asyncio
    async def test__with_auth0_jwt_no_consent__returns_451(
        self,
        db_session: AsyncSession,
        test_user: User,
        mock_settings_no_dev_mode: "Settings",
    ) -> None:
        """Auth0 JWT without consent returns 451."""
        from unittest.mock import patch

        from core.auth import _authenticate_user, _check_consent

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.valid",
        )

        mock_payload = {"sub": test_user.auth0_id, "email": test_user.email}
        with patch("core.auth.decode_jwt", return_value=mock_payload):
            user = await _authenticate_user(
                credentials, db_session, mock_settings_no_dev_mode, allow_pat=False,
            )

        # User has no consent
        user.consent = None

        with pytest.raises(HTTPException) as exc_info:
            _check_consent(user, mock_settings_no_dev_mode)

        assert exc_info.value.status_code == 451


class TestGetCurrentUserAuth0OnlyWithoutConsent:
    """Tests for get_current_user_auth0_only_without_consent dependency."""

    @pytest.mark.asyncio
    async def test__with_pat__returns_403(
        self,
        db_session: AsyncSession,
        mock_settings_no_dev_mode: "Settings",
    ) -> None:
        """PAT tokens are rejected with 403."""
        from core.auth import _authenticate_user

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="bm_token_should_fail",
        )

        with pytest.raises(HTTPException) as exc_info:
            await _authenticate_user(
                credentials, db_session, mock_settings_no_dev_mode, allow_pat=False,
            )

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test__with_auth0_jwt_no_consent__returns_user(
        self,
        db_session: AsyncSession,
        test_user: User,
        mock_settings_no_dev_mode: "Settings",
    ) -> None:
        """Auth0 JWT without consent still returns user (no consent check)."""
        from unittest.mock import patch

        from core.auth import _authenticate_user

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.valid",
        )

        mock_payload = {"sub": test_user.auth0_id, "email": test_user.email}
        with patch("core.auth.decode_jwt", return_value=mock_payload):
            # This simulates get_current_user_auth0_only_without_consent
            # which calls _authenticate_user with allow_pat=False but no consent check
            user = await _authenticate_user(
                credentials, db_session, mock_settings_no_dev_mode, allow_pat=False,
            )

        # Should succeed even without consent
        assert user.auth0_id == test_user.auth0_id


class TestErrorMessages:
    """Tests for error message clarity."""

    @pytest.mark.asyncio
    async def test__pat_rejection_message__is_user_friendly(
        self,
        db_session: AsyncSession,
        mock_settings_no_dev_mode: "Settings",
    ) -> None:
        """PAT rejection message explains the issue clearly."""
        from core.auth import _authenticate_user

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="bm_rejected_token",
        )

        with pytest.raises(HTTPException) as exc_info:
            await _authenticate_user(
                credentials, db_session, mock_settings_no_dev_mode, allow_pat=False,
            )

        error_message = exc_info.value.detail
        # Should mention it's about API tokens
        assert "API tokens" in error_message
        # Should suggest using web interface
        assert "web interface" in error_message
        # Should NOT leak internal implementation details
        assert "PAT" not in error_message
        assert "allow_pat" not in error_message
