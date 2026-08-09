"""Unit tests for the shared MCP OAuth discovery + auth-gate module."""

import pytest
from httpx import ASGITransport, AsyncClient
from mcp.server.transport_security import TransportSecurityMiddleware
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from shared.mcp_oauth import (
    WELL_KNOWN_PATH,
    WELL_KNOWN_PATH_SUFFIXED,
    OAuthConfig,
    ProtectedResourceGate,
    build_oauth_config,
    build_protected_resource_metadata,
    build_transport_security_settings,
    cors_middleware,
    extract_bearer_token,
    is_mcp_request_path,
    make_metadata_endpoint,
    parse_allowed_origins,
    require_resource_url,
)

RESOURCE_URL = "https://content-mcp.example.com/mcp"
METADATA_URL = "https://content-mcp.example.com/.well-known/oauth-protected-resource/mcp"

CONFIG = OAuthConfig(
    resource_url=RESOURCE_URL,
    authorization_server="https://clerk.example.com",
    metadata_url=METADATA_URL,
)


# ---------------------------------------------------------------------------
# is_mcp_request_path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/mcp", True),
        ("/mcp/", True),
        ("/mcp/anything", True),
        ("/health", False),
        ("/", False),
        (WELL_KNOWN_PATH, False),
        (WELL_KNOWN_PATH_SUFFIXED, False),
        ("/mcp-not-really", False),
    ],
)
def test__is_mcp_request_path__gates_only_mcp_endpoint(path: str, expected: bool) -> None:
    assert is_mcp_request_path(path) is expected


# ---------------------------------------------------------------------------
# extract_bearer_token — the single parser shared by gate + stager + reader
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("authorization", "expected"),
    [
        ("Bearer token123", "token123"),
        ("bearer token123", "token123"),  # case-insensitive scheme
        ("Bearer\ttoken123", "token123"),  # non-space separator (the divergence case)
        ("Bearer   token123", "token123"),  # multiple spaces
        (None, None),
        ("", None),
        ("token123", None),  # no scheme
        ("Basic dXNlcjpwYXNz", None),  # wrong scheme
        ("Bearer ", None),  # empty token
        ("Bearer", None),  # scheme only
    ],
)
def test__extract_bearer_token__parses_any_whitespace_separator(
    authorization: str | None, expected: str | None,
) -> None:
    assert extract_bearer_token(authorization) == expected


# ---------------------------------------------------------------------------
# require_resource_url
# ---------------------------------------------------------------------------


def test__require_resource_url__returns_stripped_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROMPT_MCP_RESOURCE_URL", "  https://prompts.example.com/mcp/  ")

    assert require_resource_url("PROMPT_MCP_RESOURCE_URL") == "https://prompts.example.com/mcp"


@pytest.mark.parametrize("value", [None, "", "   "])
def test__require_resource_url__raises_when_unset_or_blank(
    monkeypatch: pytest.MonkeyPatch, value: str | None,
) -> None:
    if value is None:
        monkeypatch.delenv("PROMPT_MCP_RESOURCE_URL", raising=False)
    else:
        monkeypatch.setenv("PROMPT_MCP_RESOURCE_URL", value)

    with pytest.raises(RuntimeError, match="PROMPT_MCP_RESOURCE_URL must be set"):
        require_resource_url("PROMPT_MCP_RESOURCE_URL")


# ---------------------------------------------------------------------------
# build_oauth_config — resolution + validation
# ---------------------------------------------------------------------------


def test__build_oauth_config__resolves_full_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLERK_FRONTEND_API", "clerk.example.com")

    config = build_oauth_config(RESOURCE_URL)

    assert config == OAuthConfig(
        resource_url=RESOURCE_URL,
        authorization_server="https://clerk.example.com",
        metadata_url=METADATA_URL,
    )


def test__build_oauth_config__allows_localhost_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLERK_FRONTEND_API", "clerk.example.com")

    config = build_oauth_config("http://localhost:8002/mcp")

    assert config.resource_url == "http://localhost:8002/mcp"
    assert config.metadata_url == (
        "http://localhost:8002/.well-known/oauth-protected-resource/mcp"
    )


def test__build_oauth_config__canonicalizes_case_and_default_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Uppercase host + explicit default port are canonicalized to the form clients send."""
    monkeypatch.setenv("CLERK_FRONTEND_API", "clerk.example.com")

    config = build_oauth_config("HTTPS://EXAMPLE.COM:443/mcp")

    assert config.resource_url == "https://example.com/mcp"
    assert config.metadata_url == "https://example.com/.well-known/oauth-protected-resource/mcp"
    # The advertised authority and the Host allowlist share one canonical identity;
    # both default-port serializations are accepted.
    assert build_transport_security_settings(config, []).allowed_hosts == [
        "example.com", "example.com:443",
    ]


def test__build_oauth_config__canonicalizes_ipv6_localhost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """IPv6 literal keeps its brackets in resource + allowed_hosts (no '::1:8002')."""
    monkeypatch.setenv("CLERK_FRONTEND_API", "clerk.example.com")

    config = build_oauth_config("http://[::1]:8002/mcp")

    assert config.resource_url == "http://[::1]:8002/mcp"
    assert config.metadata_url == (
        "http://[::1]:8002/.well-known/oauth-protected-resource/mcp"
    )
    # Canonical [::1] authority is included, alongside the other loopback aliases.
    assert build_transport_security_settings(config, []).allowed_hosts == [
        "[::1]:8002", "localhost:8002", "127.0.0.1:8002",
    ]


def test__build_oauth_config__does_not_alias_localhost_in_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Loopback aliases live only in allowed_hosts — the resource identity is preserved."""
    monkeypatch.setenv("CLERK_FRONTEND_API", "clerk.example.com")

    config = build_oauth_config("http://localhost:8002/mcp")

    assert config.resource_url == "http://localhost:8002/mcp"  # not rewritten to 127.0.0.1
    assert build_transport_security_settings(config, []).allowed_hosts == [
        "localhost:8002", "127.0.0.1:8002", "[::1]:8002",
    ]


def test__build_oauth_config__raises_when_clerk_frontend_api_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CLERK_FRONTEND_API", raising=False)

    with pytest.raises(RuntimeError, match="CLERK_FRONTEND_API"):
        build_oauth_config(RESOURCE_URL)


@pytest.mark.parametrize(
    "bad_clerk",
    [
        "https://clerk.example.com",  # scheme
        "clerk.example.com/oops",  # path
        "clerk.example.com:443",  # valid port — still disallowed
        "clerk.example.com:notaport",  # malformed port — must not raise raw ValueError
        "user@clerk.example.com",  # userinfo
        "clerk.example.com?x=1",  # query
    ],
)
def test__build_oauth_config__rejects_malformed_clerk_frontend_api(
    monkeypatch: pytest.MonkeyPatch, bad_clerk: str,
) -> None:
    monkeypatch.setenv("CLERK_FRONTEND_API", bad_clerk)

    with pytest.raises(RuntimeError, match="bare DNS hostname"):
        build_oauth_config(RESOURCE_URL)


def test__build_oauth_config__rejects_clerk_frontend_api_with_whitespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLERK_FRONTEND_API", "clerk .example.com")

    with pytest.raises(RuntimeError, match="whitespace, control, or backslash"):
        build_oauth_config(RESOURCE_URL)


def test__build_oauth_config__canonicalizes_clerk_hostname_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Uppercase Clerk host -> canonical (lowercase) issuer, per RFC 8414 matching."""
    monkeypatch.setenv("CLERK_FRONTEND_API", "CLERK.Example.COM")

    config = build_oauth_config(RESOURCE_URL)

    assert config.authorization_server == "https://clerk.example.com"


@pytest.mark.parametrize("bad_clerk", ["clerk.example.com.", "::1", "[::1]", "127.0.0.1"])
def test__build_oauth_config__rejects_clerk_trailing_dot_or_ip_literal(
    monkeypatch: pytest.MonkeyPatch, bad_clerk: str,
) -> None:
    monkeypatch.setenv("CLERK_FRONTEND_API", bad_clerk)

    with pytest.raises(RuntimeError, match="bare DNS hostname"):
        build_oauth_config(RESOURCE_URL)


def test__build_oauth_config__allows_valid_explicit_resource_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local/tunnel dev uses explicit ports — a valid one must pass."""
    monkeypatch.setenv("CLERK_FRONTEND_API", "clerk.example.com")

    config = build_oauth_config("https://tunnel.example.com:8443/mcp")

    assert config.resource_url == "https://tunnel.example.com:8443/mcp"
    assert config.metadata_url == (
        "https://tunnel.example.com:8443/.well-known/oauth-protected-resource/mcp"
    )


@pytest.mark.parametrize(
    ("bad_url", "match"),
    [
        ("ftp://host/mcp", "absolute http"),
        ("not-a-url/mcp", "absolute http"),
        ("https://:443/mcp", "host"),  # host-less authority
        ("http://host/mcp", "HTTPS"),  # non-localhost http
        ("https://user@host/mcp", "userinfo"),
        ("https://host:notaport/mcp", "invalid port"),  # deferred-parse port footgun
        ("https://host:0/mcp", "1-65535"),  # port 0 parses but isn't connectable
        ("https://host/mcp?x=1", "query or fragment"),
        ("https://host/mcp#frag", "query or fragment"),
        ("https://host/other", "path must be"),
        ("https://host", "path must be"),  # bare origin — the item-1 footgun
    ],
)
def test__build_oauth_config__rejects_malformed_resource_url(
    monkeypatch: pytest.MonkeyPatch, bad_url: str, match: str,
) -> None:
    monkeypatch.setenv("CLERK_FRONTEND_API", "clerk.example.com")

    with pytest.raises(RuntimeError, match=match):
        build_oauth_config(bad_url)


def test__build_protected_resource_metadata__has_spec_fields() -> None:
    assert build_protected_resource_metadata(CONFIG) == {
        "resource": RESOURCE_URL,
        "authorization_servers": ["https://clerk.example.com"],
        "bearer_methods_supported": ["header"],
        "scopes_supported": ["openid", "offline_access"],
    }


# ---------------------------------------------------------------------------
# metadata endpoint (served through CORS middleware)
# ---------------------------------------------------------------------------


def _metadata_app() -> Starlette:
    endpoint = make_metadata_endpoint(CONFIG)
    return Starlette(
        routes=[
            Route(WELL_KNOWN_PATH_SUFFIXED, endpoint, methods=["GET"]),
            Route(WELL_KNOWN_PATH, endpoint, methods=["GET"]),
        ],
        middleware=[cors_middleware()],
    )


@pytest.mark.parametrize("path", [WELL_KNOWN_PATH, WELL_KNOWN_PATH_SUFFIXED])
async def test__metadata_endpoint__get_returns_metadata(path: str) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_metadata_app()),
        base_url="http://test",
    ) as client:
        response = await client.get(path, headers={"Origin": "https://client.example"})

    assert response.status_code == 200
    assert response.json() == {
        "resource": RESOURCE_URL,
        "authorization_servers": ["https://clerk.example.com"],
        "bearer_methods_supported": ["header"],
        "scopes_supported": ["openid", "offline_access"],
    }
    assert response.headers["access-control-allow-origin"] == "*"


async def test__metadata_endpoint__cors_preflight_allowed() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_metadata_app()),
        base_url="http://test",
    ) as client:
        response = await client.options(
            WELL_KNOWN_PATH_SUFFIXED,
            headers={
                "Origin": "https://client.example",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"


# ---------------------------------------------------------------------------
# ProtectedResourceGate (presence-only 401 gate) + CORS on the challenge
# ---------------------------------------------------------------------------


def _gated_app() -> Starlette:
    """A minimal app whose /mcp routes are gated, wrapped in CORS like the real app."""
    async def ok(request: Request) -> JSONResponse:  # noqa: ARG001
        return JSONResponse({"reached": True})

    return Starlette(
        routes=[
            Route("/mcp", ok, methods=["GET", "POST"]),
            Route("/mcp/{path:path}", ok, methods=["GET", "POST"]),
            Route("/health", ok, methods=["GET"]),
        ],
        middleware=[
            cors_middleware(),
            Middleware(ProtectedResourceGate, config=CONFIG),
        ],
    )


async def test__gate__mcp_without_bearer_returns_401_with_www_authenticate() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_gated_app()),
        base_url="http://test",
    ) as client:
        response = await client.post("/mcp")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == (
        f'Bearer resource_metadata="{METADATA_URL}"'
    )


async def test__gate__mcp_subpath_without_bearer_returns_401() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_gated_app()),
        base_url="http://test",
    ) as client:
        response = await client.post("/mcp/messages")

    assert response.status_code == 401


async def test__gate__present_bearer_passes_through() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_gated_app()),
        base_url="http://test",
    ) as client:
        response = await client.post("/mcp", headers={"Authorization": "Bearer bm_token"})

    assert response.status_code == 200
    assert response.json() == {"reached": True}


async def test__gate__invalid_bearer_still_passes_through() -> None:
    """Presence-only: an invalid/garbage bearer is the backend's job to reject."""
    async with AsyncClient(
        transport=ASGITransport(app=_gated_app()),
        base_url="http://test",
    ) as client:
        response = await client.post("/mcp", headers={"Authorization": "Bearer not-real"})

    assert response.status_code == 200


@pytest.mark.parametrize("auth", ["Basic dXNlcjpwYXNz", "Bearer ", "Bearer"])
async def test__gate__missing_or_non_bearer_returns_401(auth: str) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_gated_app()),
        base_url="http://test",
    ) as client:
        response = await client.post("/mcp", headers={"Authorization": auth})

    assert response.status_code == 401


async def test__gate__non_mcp_path_is_not_gated() -> None:
    """Health (and any non-/mcp path) is never gated, even with no bearer."""
    async with AsyncClient(
        transport=ASGITransport(app=_gated_app()),
        base_url="http://test",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200


async def test__gate__browser_preflight_on_mcp_is_allowed_without_bearer() -> None:
    """
    A CORS preflight (OPTIONS, never carries the bearer) must be answered by CORS,
    not 401'd by the gate — otherwise an authenticated browser POST is blocked before
    it is ever sent. The real request's methods/headers must be allowed.
    """
    async with AsyncClient(
        transport=ASGITransport(app=_gated_app()),
        base_url="http://test",
    ) as client:
        response = await client.options(
            "/mcp",
            headers={
                "Origin": "https://client.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization, content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
    assert "POST" in response.headers["access-control-allow-methods"]
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


async def test__gate__401_challenge_exposes_www_authenticate_to_browser() -> None:
    """A cross-origin unauthenticated POST gets a browser-readable 401 challenge."""
    async with AsyncClient(
        transport=ASGITransport(app=_gated_app()),
        base_url="http://test",
    ) as client:
        response = await client.post("/mcp", headers={"Origin": "https://client.example"})

    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == "*"
    assert "www-authenticate" in response.headers["access-control-expose-headers"].lower()


# ---------------------------------------------------------------------------
# transport security (DNS-rebinding Host/Origin) — parse_allowed_origins +
# build_transport_security_settings, verified through the SDK middleware.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, []),
        ("", []),
        ("  ", []),
        ("https://a.example", ["https://a.example"]),
        (" https://a.example , https://b.example ", ["https://a.example", "https://b.example"]),
        # canonicalization: trailing slash stripped, host lowercased, default port dropped
        ("https://Connector.Example/", ["https://connector.example"]),
        ("https://a.example:443", ["https://a.example"]),
        ("http://localhost:80", ["http://localhost"]),  # http allowed for loopback; :80 stripped
        # order-preserving dedupe after canonicalization
        ("https://a.example/, https://A.EXAMPLE", ["https://a.example"]),
        # non-default port preserved
        ("http://localhost:6274", ["http://localhost:6274"]),
    ],
)
def test__parse_allowed_origins__parses_and_canonicalizes(
    monkeypatch: pytest.MonkeyPatch, raw: str | None, expected: list[str],
) -> None:
    if raw is None:
        monkeypatch.delenv("MCP_ALLOWED_ORIGINS", raising=False)
    else:
        monkeypatch.setenv("MCP_ALLOWED_ORIGINS", raw)

    assert parse_allowed_origins() == expected


@pytest.mark.parametrize(
    "bad",
    [
        "connector.example",  # no scheme
        "ftp://connector.example",  # bad scheme
        "https://user@connector.example",  # userinfo
        "https://connector.example/app",  # path
        "https://connector.example?x=1",  # query
        "https://connector.example:notaport",  # malformed port
        "https://connector.example:0",  # port 0
        "https://connector .example",  # whitespace
        "http://connector.example",  # remote http — not TLS
    ],
)
def test__parse_allowed_origins__rejects_malformed(
    monkeypatch: pytest.MonkeyPatch, bad: str,
) -> None:
    monkeypatch.setenv("MCP_ALLOWED_ORIGINS", bad)

    with pytest.raises(RuntimeError, match="MCP_ALLOWED_ORIGINS"):
        parse_allowed_origins()


@pytest.mark.parametrize(
    "origin",
    ["http://localhost:6274", "http://127.0.0.1:6274", "http://[::1]:6274"],
)
def test__parse_allowed_origins__allows_http_for_loopback(
    monkeypatch: pytest.MonkeyPatch, origin: str,
) -> None:
    """Plain http is permitted for loopback dev origins only."""
    monkeypatch.setenv("MCP_ALLOWED_ORIGINS", origin)

    assert parse_allowed_origins() == [origin]


def test__transport_security__derives_host_from_production_resource() -> None:
    settings = build_transport_security_settings(CONFIG, [])

    assert settings.enable_dns_rebinding_protection is True
    # Default-port (https) endpoint: accept both Host serializations.
    assert settings.allowed_hosts == ["content-mcp.example.com", "content-mcp.example.com:443"]
    assert settings.allowed_origins == []


def test__transport_security__default_port_expands_every_loopback_alias() -> None:
    """Default-port loopback: each alias gets both the bare and explicit-default form."""
    cfg = OAuthConfig(
        resource_url="http://localhost/mcp",
        authorization_server="https://clerk.example.com",
        metadata_url="http://localhost/.well-known/oauth-protected-resource/mcp",
    )

    assert build_transport_security_settings(cfg, []).allowed_hosts == [
        "localhost", "localhost:80",
        "127.0.0.1", "127.0.0.1:80",
        "[::1]", "[::1]:80",
    ]


def test__transport_security__non_default_port_is_sole_authority() -> None:
    """A non-default explicit port authorizes only that exact authority (no bare host)."""
    cfg = OAuthConfig(
        resource_url="https://host.example.com:8443/mcp",
        authorization_server="https://clerk.example.com",
        metadata_url="https://host.example.com:8443/.well-known/oauth-protected-resource/mcp",
    )

    assert build_transport_security_settings(cfg, []).allowed_hosts == ["host.example.com:8443"]


def test__transport_security__adds_loopback_siblings_for_localhost() -> None:
    local = OAuthConfig(
        resource_url="http://localhost:8002/mcp",
        authorization_server="https://clerk.example.com",
        metadata_url="http://localhost:8002/.well-known/oauth-protected-resource/mcp",
    )

    settings = build_transport_security_settings(local, [])

    assert settings.allowed_hosts == ["localhost:8002", "127.0.0.1:8002", "[::1]:8002"]


def _post_request(headers: dict[str, str]) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "method": "POST", "headers": raw})


async def test__transport_security__allows_canonical_host_no_origin() -> None:
    """Server-side connector: canonical Host, no Origin, JSON body -> passes."""
    mw = TransportSecurityMiddleware(build_transport_security_settings(CONFIG, []))

    result = await mw.validate_request(
        _post_request({"host": "content-mcp.example.com", "content-type": "application/json"}),
        is_post=True,
    )

    assert result is None


async def test__transport_security__accepts_explicit_default_port_host() -> None:
    """A client that serializes Host with the explicit default port still matches."""
    mw = TransportSecurityMiddleware(build_transport_security_settings(CONFIG, []))

    result = await mw.validate_request(
        _post_request({
            "host": "content-mcp.example.com:443",
            "content-type": "application/json",
        }),
        is_post=True,
    )

    assert result is None


async def test__transport_security__rejects_foreign_host() -> None:
    mw = TransportSecurityMiddleware(build_transport_security_settings(CONFIG, []))

    result = await mw.validate_request(
        _post_request({"host": "evil.example.com", "content-type": "application/json"}),
        is_post=True,
    )

    assert result is not None
    assert result.status_code == 421


async def test__transport_security__origin_fails_closed_by_default() -> None:
    """An unknown browser Origin is rejected (403) when the allowlist is empty."""
    mw = TransportSecurityMiddleware(build_transport_security_settings(CONFIG, []))

    result = await mw.validate_request(
        _post_request({
            "host": "content-mcp.example.com",
            "origin": "https://attacker.example",
            "content-type": "application/json",
        }),
        is_post=True,
    )

    assert result is not None
    assert result.status_code == 403


async def test__transport_security__allows_allowlisted_origin() -> None:
    mw = TransportSecurityMiddleware(
        build_transport_security_settings(CONFIG, ["https://client.example"]),
    )

    result = await mw.validate_request(
        _post_request({
            "host": "content-mcp.example.com",
            "origin": "https://client.example",
            "content-type": "application/json",
        }),
        is_post=True,
    )

    assert result is None
