"""
The consent gate is gone: policy acceptance no longer blocks any request.

Replaces the enforcement half of the deleted `test_consent.py` (see
docs/implementation_plans/2026-08-01-consent-simplification.md). Deleting those
tests is only legitimate because the behavior they covered was deleted — so the
coverage is replaced here rather than dropped.

Consent used to be enforced on three distinct auth families (standard,
session-only, and AI), each calling `_check_consent` separately. A partial
removal that left the gate live on one family would pass a test that only
exercised another, so every case below runs against all three. The endpoints
are chosen to be cheap and side-effect free; what matters is which dependency
guards them, not what they return.

These go through the real dependency chain — real `_authenticate_user`, real
rate limiter, real cache — with only the JWT signature check stubbed. A
surviving `_check_consent` anywhere in that chain would surface as a 451.
"""
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import jwt
import pytest
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from core.policy_versions import PRIVACY_POLICY_VERSION, TERMS_OF_SERVICE_VERSION
from core.tier_limits import Tier, get_tier_limits
from models.user import User
from models.user_consent import UserConsent
from schemas.token import TokenCreate
from services.token_service import create_token

TEST_CLERK_FRONTEND_API = "test-instance.clerk.accounts.dev"
TEST_CLERK_ISSUER = f"https://{TEST_CLERK_FRONTEND_API}"

# One endpoint per auth family — the three that used to call _check_consent.
# `TestEndpointsCoverEveryAuthFamily` asserts this mapping, so re-routing one of
# these endpoints to a different dependency fails loudly instead of silently
# leaving a family untested.
FAMILY_ENDPOINTS = {
    "/users/me": "get_current_user",
    "/tokens/": "get_current_user_session_only",
    "/ai/health": "get_current_user_ai",
}
GATED_ENDPOINTS = [
    pytest.param(path, id=f"{dependency}:{path}")
    for path, dependency in FAMILY_ENDPOINTS.items()
]


def _session_token(sub: str) -> str:
    """Build a JWT whose unverified `iss` routes it to the Clerk verifier."""
    return jwt.encode(
        {"iss": TEST_CLERK_ISSUER, "sub": sub},
        "unused-test-key-0123456789abcdef",
        algorithm="HS256",
    )


async def _make_user(db_session: AsyncSession, external_auth_id: str) -> User:
    user = User(
        external_auth_id=external_auth_id,
        email=f"{external_auth_id}@test.com",
        tier=Tier.PRO.value,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def user_without_consent(db_session: AsyncSession) -> User:
    """A user who has never accepted anything — no `user_consents` row at all."""
    return await _make_user(db_session, "user_gate_no_consent")


@pytest.fixture
async def user_with_stale_consent(db_session: AsyncSession) -> User:
    """A user whose consent row names superseded policy versions."""
    user = await _make_user(db_session, "user_gate_stale_consent")
    db_session.add(UserConsent(
        user_id=user.id,
        consented_at=datetime(2025, 12, 20, tzinfo=UTC),
        privacy_policy_version="2025-12-20",
        terms_of_service_version="2025-12-20",
    ))
    await db_session.flush()
    return user


@pytest.fixture
async def api_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    """
    A client with DEV_MODE off and the test session wired in.

    Deliberately NOT pre-authenticated: `_get` attaches credentials per request,
    and one test below calls the public versions endpoint with no header at all.

    Dev mode is off deliberately: it used to skip the consent check outright,
    so a test running under it could not tell a removed gate from a bypassed
    one.
    """
    from api.main import app  # noqa: PLC0415
    from core.config import get_settings  # noqa: PLC0415
    from db.session import get_async_session  # noqa: PLC0415

    settings = MagicMock(spec=Settings)
    settings.dev_mode = False
    settings.clerk_frontend_api = TEST_CLERK_FRONTEND_API
    settings.clerk_issuer = TEST_CLERK_ISSUER
    settings.clerk_jit_create_enabled = False

    async def override_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_async_session] = override_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


async def _get(client: AsyncClient, path: str, user: User) -> int:
    """Call `path` authenticated as `user` by session token, returning the status."""
    payload = {"sub": user.external_auth_id, "email": user.email}
    with patch("core.auth.decode_clerk_jwt", return_value=payload):
        response = await client.get(
            path,
            headers={"Authorization": f"Bearer {_session_token(user.external_auth_id)}"},
        )
    return response.status_code


async def _get_with_pat(
    client: AsyncClient,
    path: str,
    user: User,
    db_session: AsyncSession,
) -> int:
    """Call `path` authenticated as `user` by Personal Access Token."""
    _, plaintext = await create_token(
        db_session,
        user.id,
        TokenCreate(name="consent-gate-check"),
        get_tier_limits(Tier.PRO),
    )
    await db_session.flush()
    response = await client.get(path, headers={"Authorization": f"Bearer {plaintext}"})
    return response.status_code


class TestNoConsentRecordIsNotBlocked:
    """A user who never accepted anything gets full service."""

    @pytest.mark.parametrize("path", GATED_ENDPOINTS)
    async def test__user_without_consent__is_not_blocked(
        self,
        api_client: AsyncClient,
        user_without_consent: User,
        path: str,
    ) -> None:
        status_code = await _get(api_client, path, user_without_consent)

        assert status_code != 451, f"{path} still enforces consent"
        assert status_code == 200

    async def test__user_without_consent__is_not_blocked_via_pat(
        self,
        api_client: AsyncClient,
        user_without_consent: User,
        db_session: AsyncSession,
    ) -> None:
        """
        Not parameterised: only the standard family accepts PATs (session-only
        and AI reject them with 403 by design).

        This is the surface whose cross-client 451 plumbing motivated the whole
        refactor — CLI, MCP servers, and scripts all authenticate this way, and
        `validate_pat` carried its own consent joinedload until this milestone.
        A consent check reintroduced on the token branch would be invisible to
        every session-token case above.
        """
        status_code = await _get_with_pat(
            api_client, "/users/me", user_without_consent, db_session,
        )

        assert status_code != 451, "the PAT path still enforces consent"
        assert status_code == 200


class TestStaleConsentVersionsAreNotBlocked:
    """A user whose acceptance names superseded versions is not re-prompted."""

    @pytest.mark.parametrize("path", GATED_ENDPOINTS)
    async def test__user_with_stale_consent__is_not_blocked(
        self,
        api_client: AsyncClient,
        user_with_stale_consent: User,
        path: str,
    ) -> None:
        status_code = await _get(api_client, path, user_with_stale_consent)

        assert status_code != 451, f"{path} still compares policy versions"
        assert status_code == 200

    async def test__user_with_stale_consent__is_not_blocked_via_pat(
        self,
        api_client: AsyncClient,
        user_with_stale_consent: User,
        db_session: AsyncSession,
    ) -> None:
        """The version-comparison branch was distinct from the missing-row one."""
        status_code = await _get_with_pat(
            api_client, "/users/me", user_with_stale_consent, db_session,
        )

        assert status_code != 451, "the PAT path still compares policy versions"
        assert status_code == 200

    async def test__stale_row_really_is_stale(
        self,
        user_with_stale_consent: User,
        db_session: AsyncSession,
    ) -> None:
        """
        Guard the guard: if the fixture's versions ever matched the published
        ones, the test above would pass without exercising anything.
        """
        await db_session.refresh(user_with_stale_consent, ["consent"])
        consent = user_with_stale_consent.consent

        assert consent is not None
        assert consent.privacy_policy_version != PRIVACY_POLICY_VERSION
        assert consent.terms_of_service_version != TERMS_OF_SERVICE_VERSION


class TestPolicyVersionsEndpointSurvives:
    """The public pages still need their "Last Updated" date."""

    async def test__versions__returns_both_current_versions(
        self,
        client: AsyncClient,
    ) -> None:
        response = await client.get("/consent/versions")

        assert response.status_code == 200
        assert response.json() == {
            "privacy_policy_version": PRIVACY_POLICY_VERSION,
            "terms_of_service_version": TERMS_OF_SERVICE_VERSION,
        }

    async def test__versions__requires_no_authentication(
        self,
        api_client: AsyncClient,
    ) -> None:
        """No Authorization header at all — this feeds the public legal pages."""
        response = await api_client.get("/consent/versions")

        assert response.status_code == 200

    @pytest.mark.parametrize("path", ["/consent/status", "/consent/me"])
    async def test__removed_consent_endpoints__are_gone(
        self,
        api_client: AsyncClient,
        user_without_consent: User,
        path: str,
    ) -> None:
        """The accept/status surface is deleted, not merely unlinked."""
        assert await _get(api_client, path, user_without_consent) == 404


class TestEndpointsCoverEveryAuthFamily:
    """
    The claim above — that these cases cover all three families — rests on a
    path-to-dependency mapping nothing else enforces. Without this, re-routing
    `/tokens/` in six months would leave the suite green while testing the
    standard family twice and session-only not at all.
    """

    def test__each_endpoint_is_guarded_by_its_named_dependency(self) -> None:
        from api.main import app  # noqa: PLC0415
        from core.auth import AUTH_DEPENDENCIES  # noqa: PLC0415

        by_name = {dep.__name__: dep for dep in AUTH_DEPENDENCIES}

        def auth_dependencies(dependant: object) -> set[str]:
            found: set[str] = set()
            for dep in dependant.dependencies:  # type: ignore[attr-defined]
                if dep.call in AUTH_DEPENDENCIES:
                    found.add(dep.call.__name__)
                found |= auth_dependencies(dep)
            return found

        routes = {
            route.path: route
            for route in app.routes
            if isinstance(route, APIRoute) and "GET" in route.methods
        }

        for path, expected in FAMILY_ENDPOINTS.items():
            assert expected in by_name, f"{expected} is no longer an auth dependency"
            assert path in routes, f"{path} is no longer a GET route"
            assert auth_dependencies(routes[path].dependant) == {expected}, (
                f"{path} is no longer guarded by {expected} alone — the family "
                "coverage claim in this module is stale."
            )

    def test__every_auth_family_is_represented(self) -> None:
        """All three families that called _check_consent must appear above."""
        from core.auth import AUTH_DEPENDENCIES  # noqa: PLC0415

        assert set(FAMILY_ENDPOINTS.values()) == {d.__name__ for d in AUTH_DEPENDENCIES}
