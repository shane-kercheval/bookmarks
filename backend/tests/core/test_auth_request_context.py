"""
Tests for RequestContext functionality in the auth module.

Imports from core.auth are deferred to inside test functions because
core.auth -> db.session -> get_settings() at module level, which requires
DATABASE_URL. Deferring avoids collection failures in CI where the env var
isn't set until the test session fixtures run.
"""
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi import Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import User

if TYPE_CHECKING:
    from core.config import Settings


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
        external_auth_id="user_test_context",
        email="context@test.com",
    )
    db_session.add(user)
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
def mock_settings_no_dev_mode() -> "Settings":
    """Create mock settings with dev_mode=False."""
    settings = MagicMock()
    settings.dev_mode = False
    settings.frontend_url = "http://localhost:5173"
    settings.api_url = "http://localhost:8000"
    settings.clerk_frontend_api = TEST_CLERK_FRONTEND_API
    settings.clerk_issuer = TEST_CLERK_ISSUER
    settings.clerk_jit_create_enabled = True
    return settings


@pytest.fixture
def mock_settings_dev_mode() -> "Settings":
    """Create mock settings with dev_mode=True."""
    settings = MagicMock()
    settings.dev_mode = True
    return settings


class TestGetRequestSource:
    """
    Tests for the get_request_source Header dependency.

    get_request_source resolves the X-Request-Source header value (passed by
    FastAPI from the declared Header parameter) into the stored source string.
    The value is free-form (no allowlist), trimmed, and lowercased; a missing
    or blank header resolves to 'unknown'.
    """

    def test__get_request_source__web_header(self) -> None:
        """X-Request-Source: web resolves to 'web'."""
        from core.auth import get_request_source  # noqa: PLC0415
        assert get_request_source("web") == "web"

    def test__get_request_source__ios_header(self) -> None:
        """A first-party client value (ios) passes through as-is."""
        from core.auth import get_request_source  # noqa: PLC0415
        assert get_request_source("ios") == "ios"

    def test__get_request_source__mcp_content_header(self) -> None:
        """X-Request-Source: mcp-content passes through as-is."""
        from core.auth import get_request_source  # noqa: PLC0415
        assert get_request_source("mcp-content") == "mcp-content"

    def test__get_request_source__mcp_prompt_header(self) -> None:
        """X-Request-Source: mcp-prompt passes through as-is."""
        from core.auth import get_request_source  # noqa: PLC0415
        assert get_request_source("mcp-prompt") == "mcp-prompt"

    def test__get_request_source__missing_header_defaults_to_unknown(self) -> None:
        """A missing (None) header defaults to 'unknown'."""
        from core.auth import get_request_source  # noqa: PLC0415
        assert get_request_source(None) == "unknown"

    def test__get_request_source__blank_header_defaults_to_unknown(self) -> None:
        """A blank/whitespace-only header defaults to 'unknown'."""
        from core.auth import get_request_source  # noqa: PLC0415
        assert get_request_source("   ") == "unknown"

    def test__get_request_source__unrecognized_value_passes_through(self) -> None:
        """No allowlist: any free-form client value passes through as-is."""
        from core.auth import get_request_source  # noqa: PLC0415
        assert get_request_source("some-custom-client") == "some-custom-client"

    def test__get_request_source__case_and_whitespace_normalized(self) -> None:
        """Header value is lowercased and trimmed."""
        from core.auth import get_request_source  # noqa: PLC0415
        assert get_request_source("WEB") == "web"
        assert get_request_source("  MCP-Content  ") == "mcp-content"

    def test__get_request_source__over_length_value_is_truncated(self) -> None:
        """A value longer than the source column is truncated so it can never 500."""
        from core.auth import get_request_source  # noqa: PLC0415
        from models.content_history import SOURCE_MAX_LENGTH  # noqa: PLC0415

        long_value = "a" * (SOURCE_MAX_LENGTH + 10)
        result = get_request_source(long_value)
        assert result == "a" * SOURCE_MAX_LENGTH
        assert len(result) == SOURCE_MAX_LENGTH


class TestRequestContextWithSessionJWT:
    """Tests for RequestContext being set correctly with a Clerk session JWT."""

    async def test__session_jwt__sets_auth_type_session(
        self,
        db_session: AsyncSession,
        test_user: User,
        mock_settings_no_dev_mode: "Settings",
        mock_request: Request,
    ) -> None:
        """A Clerk session JWT sets auth_type to SESSION (provider-neutral)."""
        from core.auth import AuthType, _authenticate_user  # noqa: PLC0415

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=clerk_dispatch_token(test_user.external_auth_id),
        )

        mock_payload = {"sub": test_user.external_auth_id, "email": test_user.email}
        with patch("core.auth.decode_clerk_jwt", return_value=mock_payload):
            await _authenticate_user(
                mock_request, credentials, db_session, mock_settings_no_dev_mode,
                source="unknown",
            )

        # Check that request_context was set
        context = mock_request.state.request_context
        assert context.auth_type == AuthType.SESSION
        assert context.token_prefix is None

    async def test__session_jwt__sets_source_from_param(
        self,
        db_session: AsyncSession,
        test_user: User,
        mock_settings_no_dev_mode: "Settings",
        mock_request: Request,
    ) -> None:
        """A Clerk session JWT records the resolved request source on the context."""
        from core.auth import AuthType, _authenticate_user  # noqa: PLC0415

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=clerk_dispatch_token(test_user.external_auth_id),
        )

        mock_payload = {"sub": test_user.external_auth_id, "email": test_user.email}
        with patch("core.auth.decode_clerk_jwt", return_value=mock_payload):
            await _authenticate_user(
                mock_request, credentials, db_session, mock_settings_no_dev_mode,
                source="web",
            )

        context = mock_request.state.request_context
        assert context.source == "web"
        assert context.auth_type == AuthType.SESSION


class TestRequestContextWithPAT:
    """Tests for RequestContext being set correctly with PAT."""

    async def test__pat__sets_auth_type_pat(
        self,
        db_session: AsyncSession,
        test_user: User,
        mock_settings_no_dev_mode: "Settings",
        mock_request: Request,
    ) -> None:
        """PAT sets auth_type to PAT."""
        from core.auth import AuthType, _authenticate_user  # noqa: PLC0415

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="bm_valid_token_12345",
        )

        with patch(
            "core.auth.validate_pat",
            new_callable=AsyncMock,
            return_value=test_user,
        ):
            await _authenticate_user(
                mock_request, credentials, db_session, mock_settings_no_dev_mode,
                source="unknown",
            )

        context = mock_request.state.request_context
        assert context.auth_type == AuthType.PAT

    async def test__pat__sets_token_prefix(
        self,
        db_session: AsyncSession,
        test_user: User,
        mock_settings_no_dev_mode: "Settings",
        mock_request: Request,
    ) -> None:
        """PAT sets token_prefix to first 15 chars of token."""
        from core.auth import _authenticate_user  # noqa: PLC0415

        token = "bm_a3f8xyz123456789abcdef"
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=token,
        )

        with patch(
            "core.auth.validate_pat",
            new_callable=AsyncMock,
            return_value=test_user,
        ):
            await _authenticate_user(
                mock_request, credentials, db_session, mock_settings_no_dev_mode,
                source="unknown",
            )

        context = mock_request.state.request_context
        # First 15 chars: "bm_a3f8xyz12345"
        assert context.token_prefix == "bm_a3f8xyz12345"
        assert len(context.token_prefix) == 15

    async def test__pat__short_token_uses_full_token_as_prefix(
        self,
        db_session: AsyncSession,
        test_user: User,
        mock_settings_no_dev_mode: "Settings",
        mock_request: Request,
    ) -> None:
        """PAT shorter than 15 chars uses full token as prefix."""
        from core.auth import _authenticate_user  # noqa: PLC0415

        token = "bm_short"  # 8 chars
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=token,
        )

        with patch(
            "core.auth.validate_pat",
            new_callable=AsyncMock,
            return_value=test_user,
        ):
            await _authenticate_user(
                mock_request, credentials, db_session, mock_settings_no_dev_mode,
                source="unknown",
            )

        context = mock_request.state.request_context
        assert context.token_prefix == "bm_short"

    async def test__pat__sets_source_from_param(
        self,
        db_session: AsyncSession,
        test_user: User,
        mock_settings_no_dev_mode: "Settings",
        mock_request: Request,
    ) -> None:
        """PAT records the resolved request source on the context."""
        from core.auth import AuthType, _authenticate_user  # noqa: PLC0415

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="bm_valid_token",
        )

        with patch(
            "core.auth.validate_pat",
            new_callable=AsyncMock,
            return_value=test_user,
        ):
            await _authenticate_user(
                mock_request, credentials, db_session, mock_settings_no_dev_mode,
                source="mcp-content",
            )

        context = mock_request.state.request_context
        assert context.source == "mcp-content"
        assert context.auth_type == AuthType.PAT


class TestRequestContextWithDevMode:
    """Tests for RequestContext in DEV_MODE."""

    async def test__dev_mode__sets_auth_type_dev(
        self,
        db_session: AsyncSession,
        mock_settings_dev_mode: "Settings",
        mock_request: Request,
    ) -> None:
        """DEV_MODE sets auth_type to DEV."""
        from core.auth import AuthType, _authenticate_user  # noqa: PLC0415

        # Credentials don't matter in dev mode
        await _authenticate_user(
            mock_request, None, db_session, mock_settings_dev_mode,
            source="unknown",
        )

        context = mock_request.state.request_context
        assert context.auth_type == AuthType.DEV
        assert context.token_prefix is None

    async def test__dev_mode__sets_source_from_param(
        self,
        db_session: AsyncSession,
        mock_settings_dev_mode: "Settings",
        mock_request: Request,
    ) -> None:
        """DEV_MODE records the resolved request source on the context."""
        from core.auth import AuthType, _authenticate_user  # noqa: PLC0415

        await _authenticate_user(
            mock_request, None, db_session, mock_settings_dev_mode,
            source="web",
        )

        context = mock_request.state.request_context
        assert context.source == "web"
        assert context.auth_type == AuthType.DEV


class TestRequestSourceOpenAPISchema:
    """
    Guards that X-Request-Source is discoverable in the generated OpenAPI schema.

    The header is declared as a Header(...) dependency precisely so it shows up in
    the Swagger reference for API integrators (KAN-157). If someone reverts it to a
    raw request.headers read, it would vanish from the schema and this test fails.
    """

    # db_session is load-bearing despite being unused in the body: it transitively
    # starts the Postgres container that sets DATABASE_URL, which importing
    # api.main.app (below) requires for Settings validation. Don't remove it.
    @pytest.mark.usefixtures("db_session")
    async def test__x_request_source__declared_as_header_param_in_openapi(
        self,
    ) -> None:
        """X-Request-Source appears as a header parameter on authenticated routes."""
        from core.config import get_settings  # noqa: PLC0415
        get_settings.cache_clear()
        from api.main import app  # noqa: PLC0415

        schema = app.openapi()

        # Collect every header parameter name across all operations (case-insensitive:
        # FastAPI emits the converted header name, e.g. 'x-request-source').
        header_params: set[str] = set()
        for path_item in schema["paths"].values():
            for operation in path_item.values():
                if not isinstance(operation, dict):
                    continue
                for param in operation.get("parameters", []):
                    if param.get("in") == "header":
                        header_params.add(param["name"].lower())

        assert "x-request-source" in header_params


class TestGetRequestContext:
    """Tests for get_request_context helper function."""

    def test__get_request_context__returns_context_when_set(
        self,
        mock_request: Request,
    ) -> None:
        """get_request_context returns the context when set."""
        from core.auth import AuthType, RequestContext, get_request_context  # noqa: PLC0415

        expected_context = RequestContext(
            source="web",
            auth_type=AuthType.SESSION,
            token_prefix=None,
        )
        mock_request.state.request_context = expected_context

        context = get_request_context(mock_request)
        assert context == expected_context

    def test__get_request_context__returns_none_when_not_set(self) -> None:
        """get_request_context returns None when context not set."""
        from core.auth import get_request_context  # noqa: PLC0415

        request = MagicMock(spec=Request)
        request.state = MagicMock(spec=[])  # Empty spec means no attributes

        context = get_request_context(request)
        assert context is None
