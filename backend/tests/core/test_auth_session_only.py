"""Tests for session-only (PAT-blocking) authentication dependencies."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from core.config import Settings
from core.policy_versions import PRIVACY_POLICY_VERSION, TERMS_OF_SERVICE_VERSION
from models.user import User
from core.tier_limits import Tier
from models.user_consent import UserConsent


@pytest.fixture
def mock_request() -> Request:
    """Create a mock request for auth tests."""
    request = MagicMock(spec=Request)
    request.headers = {}
    request.state = MagicMock()
    return request


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user for auth tests."""
    user = User(
        external_auth_id="user_test_auth",
        email="auth@test.com",
        tier=Tier.FREE.value,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_user_with_consent(db_session: AsyncSession) -> User:
    """Create a test user with valid consent."""
    user = User(
        external_auth_id="user_test_auth_consent",
        email="authconsent@test.com",
        tier=Tier.FREE.value,
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


TEST_CLERK_FRONTEND_API = "test-instance.clerk.accounts.dev"
TEST_CLERK_ISSUER = f"https://{TEST_CLERK_FRONTEND_API}"


def clerk_dispatch_token(sub: str) -> str:
    """
    Build a JWT whose (unverified) `iss` routes it to the Clerk verifier.

    Signature is irrelevant: these tests patch decode_clerk_jwt, so only the
    dispatch peek reads this token.
    """
    return jwt.encode({"iss": TEST_CLERK_ISSUER, "sub": sub}, "unused-test-key-0123456789abcdef", algorithm="HS256")


@pytest.fixture
def mock_settings_no_dev_mode() -> Settings:
    """Create mock settings with dev_mode=False."""
    settings = MagicMock(spec=Settings)
    settings.dev_mode = False
    settings.frontend_url = "http://localhost:5173"
    settings.api_url = "http://localhost:8000"
    settings.clerk_frontend_api = TEST_CLERK_FRONTEND_API
    settings.clerk_issuer = TEST_CLERK_ISSUER
    settings.clerk_jit_create_enabled = True
    return settings


@pytest.fixture
def mock_settings_dev_mode() -> Settings:
    """Create mock settings with dev_mode=True."""
    settings = MagicMock(spec=Settings)
    settings.dev_mode = True
    return settings


class TestAuthenticateUserAllowPat:
    """Tests for _authenticate_user with allow_pat parameter."""

    async def test__allow_pat_true__accepts_pat_token(
        self,
        db_session: AsyncSession,
        test_user: User,
        mock_settings_no_dev_mode: Settings,
        mock_request: Request,
    ) -> None:
        """When allow_pat=True (default), PAT tokens are accepted."""
        from core.auth import _authenticate_user  # noqa: PLC0415

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
                mock_request, credentials, db_session, mock_settings_no_dev_mode,
                source="unknown", allow_pat=True,
            )

        assert result.id == test_user.id

    async def test__allow_pat_false__rejects_pat_token_with_403(
        self,
        db_session: AsyncSession,
        mock_settings_no_dev_mode: Settings,
        mock_request: Request,
    ) -> None:
        """When allow_pat=False, PAT tokens are rejected with 403."""
        from core.auth import _authenticate_user  # noqa: PLC0415

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="bm_any_token",
        )

        with pytest.raises(HTTPException) as exc_info:
            await _authenticate_user(
                mock_request, credentials, db_session, mock_settings_no_dev_mode,
                source="unknown", allow_pat=False,
            )

        assert exc_info.value.status_code == 403
        assert "not available for API tokens" in exc_info.value.detail
        assert "web interface" in exc_info.value.detail

    async def test__allow_pat_false__accepts_session_jwt(
        self,
        db_session: AsyncSession,
        test_user: User,
        mock_settings_no_dev_mode: Settings,
        mock_request: Request,
    ) -> None:
        """
        When allow_pat=False, Clerk session JWTs are still accepted.

        The Clerk OAuth (at+jwt) twin of this policy test lives in
        test_auth_clerk.py::TestClerkOAuthAccessTokens — it needs that
        module's real-signature JWKS infrastructure.
        """
        from core.auth import _authenticate_user  # noqa: PLC0415

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=clerk_dispatch_token(test_user.external_auth_id),
        )

        # Mock decode_clerk_jwt to return valid payload
        mock_payload = {"sub": test_user.external_auth_id, "email": test_user.email}
        with patch("core.auth.decode_clerk_jwt", return_value=mock_payload):
            result = await _authenticate_user(
                mock_request, credentials, db_session, mock_settings_no_dev_mode,
                source="unknown", allow_pat=False,
            )

        assert result.external_auth_id == test_user.external_auth_id

    async def test__allow_pat_false__dev_mode_bypasses_check(
        self,
        db_session: AsyncSession,
        mock_settings_dev_mode: Settings,
        mock_request: Request,
    ) -> None:
        """In DEV_MODE, returns dev user regardless of allow_pat setting."""
        from core.auth import _authenticate_user  # noqa: PLC0415

        # Even with a PAT-looking token, dev mode should bypass and return dev user
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="bm_should_be_rejected_but_dev_mode",
        )

        result = await _authenticate_user(
            mock_request, credentials, db_session, mock_settings_dev_mode,
            source="unknown", allow_pat=False,
        )

        # Should return dev user, not raise 403
        assert result.auth0_id == "dev|local-development-user"

    async def test__no_credentials__returns_401(
        self,
        db_session: AsyncSession,
        mock_settings_no_dev_mode: Settings,
        mock_request: Request,
    ) -> None:
        """Returns 401 when no credentials provided."""
        from core.auth import _authenticate_user  # noqa: PLC0415

        with pytest.raises(HTTPException) as exc_info:
            await _authenticate_user(
                mock_request, None, db_session, mock_settings_no_dev_mode,
                source="unknown", allow_pat=False,
            )

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Not authenticated"


class TestGetCurrentUserSessionOnly:
    """Tests for get_current_user_session_only dependency."""

    async def test__with_pat__returns_403(
        self,
        db_session: AsyncSession,
        mock_settings_no_dev_mode: Settings,
        mock_request: Request,
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
        from core.auth import _authenticate_user  # noqa: PLC0415

        with pytest.raises(HTTPException) as exc_info:
            await _authenticate_user(
                mock_request, credentials, db_session, mock_settings_no_dev_mode,
                source="unknown", allow_pat=False,
            )

        assert exc_info.value.status_code == 403

    async def test__with_session_jwt_and_valid_consent__returns_user(
        self,
        db_session: AsyncSession,
        test_user_with_consent: User,
        mock_settings_no_dev_mode: Settings,
        mock_request: Request,
    ) -> None:
        """A Clerk session JWT with valid consent returns user successfully."""
        from core.auth import _authenticate_user, _check_consent  # noqa: PLC0415

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=clerk_dispatch_token(test_user_with_consent.external_auth_id),
        )

        mock_payload = {
            "sub": test_user_with_consent.external_auth_id,
            "email": test_user_with_consent.email,
        }
        with patch("core.auth.decode_clerk_jwt", return_value=mock_payload):
            user = await _authenticate_user(
                mock_request, credentials, db_session, mock_settings_no_dev_mode,
                source="unknown", allow_pat=False,
            )

        # Reload user with consent for check
        result = await db_session.execute(
            select(User).options(joinedload(User.consent)).where(User.id == user.id),
        )
        user_with_consent = result.scalar_one()

        # Should not raise - valid consent
        _check_consent(user_with_consent, mock_settings_no_dev_mode)

    async def test__with_session_jwt_no_consent__returns_451(
        self,
        db_session: AsyncSession,
        test_user: User,
        mock_settings_no_dev_mode: Settings,
        mock_request: Request,
    ) -> None:
        """A Clerk session JWT without consent returns 451."""
        from core.auth import _authenticate_user, _check_consent  # noqa: PLC0415

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=clerk_dispatch_token(test_user.external_auth_id),
        )

        mock_payload = {"sub": test_user.external_auth_id, "email": test_user.email}
        with patch("core.auth.decode_clerk_jwt", return_value=mock_payload):
            user = await _authenticate_user(
                mock_request, credentials, db_session, mock_settings_no_dev_mode,
                source="unknown", allow_pat=False,
            )

        # User has no consent
        user.consent = None

        with pytest.raises(HTTPException) as exc_info:
            _check_consent(user, mock_settings_no_dev_mode)

        assert exc_info.value.status_code == 451


class TestGetCurrentUserSessionOnlyWithoutConsent:
    """Tests for get_current_user_session_only_without_consent dependency."""

    async def test__with_pat__returns_403(
        self,
        db_session: AsyncSession,
        mock_settings_no_dev_mode: Settings,
        mock_request: Request,
    ) -> None:
        """PAT tokens are rejected with 403."""
        from core.auth import _authenticate_user  # noqa: PLC0415

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="bm_token_should_fail",
        )

        with pytest.raises(HTTPException) as exc_info:
            await _authenticate_user(
                mock_request, credentials, db_session, mock_settings_no_dev_mode,
                source="unknown", allow_pat=False,
            )

        assert exc_info.value.status_code == 403

    async def test__with_session_jwt_no_consent__returns_user(
        self,
        db_session: AsyncSession,
        test_user: User,
        mock_settings_no_dev_mode: Settings,
        mock_request: Request,
    ) -> None:
        """A Clerk session JWT without consent still returns user (no consent check)."""
        from core.auth import _authenticate_user  # noqa: PLC0415

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=clerk_dispatch_token(test_user.external_auth_id),
        )

        mock_payload = {"sub": test_user.external_auth_id, "email": test_user.email}
        with patch("core.auth.decode_clerk_jwt", return_value=mock_payload):
            # This simulates get_current_user_session_only_without_consent
            # which calls _authenticate_user with allow_pat=False but no consent check
            user = await _authenticate_user(
                mock_request, credentials, db_session, mock_settings_no_dev_mode,
                source="unknown", allow_pat=False,
            )

        # Should succeed even without consent
        assert user.external_auth_id == test_user.external_auth_id


class TestErrorMessages:
    """Tests for error message clarity."""

    async def test__pat_rejection_message__is_user_friendly(
        self,
        db_session: AsyncSession,
        mock_settings_no_dev_mode: Settings,
        mock_request: Request,
    ) -> None:
        """PAT rejection message explains the issue clearly."""
        from core.auth import _authenticate_user  # noqa: PLC0415

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="bm_rejected_token",
        )

        with pytest.raises(HTTPException) as exc_info:
            await _authenticate_user(
                mock_request, credentials, db_session, mock_settings_no_dev_mode,
                source="unknown", allow_pat=False,
            )

        error_message = exc_info.value.detail
        # Should mention it's about API tokens
        assert "API tokens" in error_message
        # Should suggest using web interface
        assert "web interface" in error_message
        # Should NOT leak internal implementation details
        assert "PAT" not in error_message
        assert "allow_pat" not in error_message
