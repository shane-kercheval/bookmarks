"""
Shared OAuth protected-resource discovery and presence-only auth gating for the
MCP servers (the server side of the MCP authorization spec).

Three pieces, used identically by both MCP servers:

1. **Protected-resource metadata** (RFC 9728): each server advertises its own
   canonical MCP endpoint URL as the OAuth ``resource``, points at Clerk as the
   authorization server, and publishes the scopes to request, so an OAuth-capable
   client can discover where and how to sign in.
2. **A presence-only 401 gate**: a request to the MCP endpoint with no
   ``Authorization: Bearer`` header is rejected *before* MCP dispatch with a
   ``WWW-Authenticate`` pointer to the metadata (RFC 9728 §5.1) — the signal that
   triggers a client's OAuth bootstrap.
3. **CORS** (via Starlette's ``CORSMiddleware``): browser-based connectors make
   cross-origin calls to ``/mcp`` and the well-known routes; the middleware handles
   preflight and exposes ``WWW-Authenticate`` so browser JS can read the challenge.

**This module does NOT verify tokens.** The MCP servers stay proxies: a present
bearer (valid or not) flows through to the backend API, which remains the only
verifier. The gate is presence-only by design.

**Resource identity (RFC 9728 §3).** The ``resource`` MUST equal the URL clients
actually connect to — i.e. the full ``https://<host>/mcp`` endpoint, *including*
the path, not the bare origin. The metadata URL is formed by inserting the
well-known segment between host and path (``…/.well-known/oauth-protected-resource/mcp``),
so a naive ``resource_url + well_known`` concatenation would be wrong — see
:func:`build_oauth_config`.

Configuration is resolved and validated **once** into an immutable
:class:`OAuthConfig` (see :func:`build_oauth_config`); servers build it at startup
so a missing/malformed value crashes the process instead of serving a
healthy-but-broken OAuth endpoint to the first client.
"""

import ipaddress
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

from mcp.server.transport_security import TransportSecurityMiddleware, TransportSecuritySettings
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# The MCP endpoint path, single-sourced: the gate predicate, the well-known suffix, and
# the resource-URL validation all derive from it, so they can't drift. Both servers mount
# MCP at /mcp; this is not per-server configurable (a partial knob would let metadata and
# enforcement disagree).
MCP_PATH = "/mcp"

# RFC 9728 well-known path. The canonical metadata URL for the /mcp resource inserts that
# path after the well-known segment (``…/oauth-protected-resource/mcp``); the root path is
# served too as a compatibility fallback for less-strict clients.
WELL_KNOWN_PATH = "/.well-known/oauth-protected-resource"
WELL_KNOWN_PATH_SUFFIXED = f"{WELL_KNOWN_PATH}{MCP_PATH}"

# Scopes a client should request (RFC 9728 ``scopes_supported``), published so a
# spec-conforming OAuth client can derive both its DCR registration and its authorize
# request from discovery instead of guessing. This is not a permission matrix: the
# backend has no per-scope permission model (`decode_clerk_jwt` never reads
# ``scope``; identity is ``sub``) and accepts a valid token whatever scopes it
# carries. These scopes govern the client's credential lifecycle and interop, and
# both servers share one list. ``offline_access``: without it Clerk issues no
# refresh token, so authorization cannot outlive the 24h access token (lifetime
# recorded in `decode_clerk_jwt`'s docstring) — once it expires, only a fresh
# browser sign-in gets a new one. ``openid`` keeps a DCR client's registered scopes
# aligned with the OIDC-shaped authorize requests most clients send (the mismatch
# behind the known ChatGPT connector issue). ``profile``/``email`` are deliberately
# absent: observed Clerk ``at+jwt`` access tokens carry no email/profile claims
# regardless of scope — consistent with standard OIDC, where those scopes shape ID
# tokens and userinfo, neither of which the backend reads — and JIT user creation
# accepts a null email.
SCOPES_SUPPORTED = ("openid", "offline_access")

# CORS for browser-based connectors. A cross-origin request that sets Authorization
# is a "non-simple" request and preflights; the preflight (OPTIONS) never carries the
# bearer, so it must be answered by CORS handling, not the gate. WWW-Authenticate is
# not on the response-header safelist, so it must be explicitly exposed for browser JS
# to read the discovery pointer off the 401 challenge. MCP-Session-Id: no session id is
# issued today (both transports are stateless), but it is exposed so a future stateful
# transport doesn't fail cross-origin-only (browser JS couldn't read it off initialize).
_ALLOW_METHODS = ["GET", "POST", "DELETE", "OPTIONS"]
_ALLOW_HEADERS = ["Authorization", "Content-Type", "MCP-Protocol-Version", "MCP-Session-Id"]
_EXPOSE_HEADERS = ["WWW-Authenticate", "MCP-Session-Id"]

_LOCALHOST_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_DEFAULT_PORTS = {"http": 80, "https": 443}


@dataclass(frozen=True)
class OAuthConfig:
    """Validated, immutable OAuth discovery configuration for one MCP server."""

    resource_url: str  # this server's canonical MCP endpoint, e.g. https://host/mcp
    authorization_server: str  # the Clerk issuer, https://{CLERK_FRONTEND_API}
    metadata_url: str  # {origin}/.well-known/oauth-protected-resource{path}


def is_mcp_request_path(path: str) -> bool:
    """
    True for the MCP endpoint paths that must be auth-gated.

    Matches ``/mcp`` exactly and any ``/mcp/`` sub-path. The health check and the
    well-known metadata paths are intentionally excluded — they stay public.
    """
    return path == MCP_PATH or path.startswith(f"{MCP_PATH}/")


def require_resource_url(env_var: str) -> str:
    """
    Read a server's **required** canonical MCP endpoint URL from its env var.

    Each MCP service sets its own service-specific variable (e.g.
    ``PROMPT_MCP_RESOURCE_URL`` / ``CONTENT_MCP_RESOURCE_URL``) to its full ``/mcp``
    endpoint — required in *every* environment (local dev gets it from
    ``.env.example``). There is deliberately no localhost fallback: a missing value
    raises at startup so a misconfigured service crashes on boot rather than
    advertising a placeholder resource that silently breaks OAuth discovery.
    """
    value = os.getenv(env_var)
    if not value or not value.strip():
        raise RuntimeError(
            f"{env_var} must be set to this MCP server's canonical /mcp endpoint URL "
            "(e.g. https://prompts-mcp.tiddly.me/mcp). See .env.example.",
        )
    return value.strip().rstrip("/")


def _reject_bad_authority_chars(raw: str, var_name: str) -> None:
    """
    Reject copy-paste noise (whitespace, control characters, backslash) that
    ``urlsplit`` would silently fold into the hostname and publish as broken metadata.
    """
    if any(ch.isspace() or ord(ch) < 0x20 or ch == "\\" for ch in raw):
        raise RuntimeError(
            f"{var_name} must not contain whitespace, control, or backslash "
            f"characters — got {raw!r}.",
        )


def _has_port_component(parts: SplitResult) -> bool:
    """
    Whether the authority carries a port, treating a malformed port as present too.

    ``urlsplit`` defers port parsing, so ``.port`` raises ``ValueError`` on a
    non-numeric/out-of-range port — that still means a port component is present.
    """
    try:
        return parts.port is not None
    except ValueError:
        return True


def _validated_port(parts: SplitResult, label: str) -> int | None:
    """
    Return the authority's port, forcing ``urlsplit``'s deferred parse and rejecting
    unusable values with a clear startup error.

    ``urlsplit`` raises ``ValueError`` for a non-numeric or out-of-range (>65535)
    port; port ``0`` parses fine but is not a connectable TCP port. A valid explicit
    port (1-65535) is permitted — local/tunnel dev use one. Returns ``None`` when no
    port is present.
    """
    try:
        port = parts.port
    except ValueError:
        raise RuntimeError(f"{label} has an invalid port — got {parts.netloc!r}.") from None
    if port == 0:
        raise RuntimeError(f"{label} port must be 1-65535 — got 0 in {parts.netloc!r}.")
    return port


def _is_ip_literal(host: str) -> bool:
    """True if ``host`` is an IPv4/IPv6 literal (``CLERK_FRONTEND_API`` must be a DNS name)."""
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _canonical_scheme_netloc(parts: SplitResult) -> tuple[str, str]:
    """
    Canonicalize an authority: lowercase scheme + host, drop the scheme's default
    port, keep a non-default port, and bracket IPv6 literals.

    URI normalization *permits* omitting the default port and lowercasing host/scheme,
    so the security layer must not depend on a client's Host serialization — deriving
    one canonical authority (used for both the advertised ``resource`` and Host
    validation) keeps discovery and enforcement from drifting apart. Assumes the port
    has already been validated (``.port`` will not raise here).
    """
    scheme = parts.scheme.lower()
    hostname = (parts.hostname or "").lower()
    # urlsplit strips IPv6 brackets from .hostname; re-add them, or "::1:8002" results.
    host = f"[{hostname}]" if ":" in hostname else hostname
    port = parts.port
    netloc = host if port is None or port == _DEFAULT_PORTS.get(scheme) else f"{host}:{port}"
    return scheme, netloc


def _clerk_authorization_server() -> str:
    """
    Resolve and validate the Clerk issuer URL from ``CLERK_FRONTEND_API``.

    The value is contractually a bare hostname; parse it as an authority and reject
    anything else (scheme, port, path, userinfo, query, fragment, or stray
    characters), so a malformed setting fails at startup instead of advertising a
    broken authorization server.
    """
    frontend_api = os.getenv("CLERK_FRONTEND_API", "").strip().rstrip("/")
    if not frontend_api:
        raise RuntimeError(
            "CLERK_FRONTEND_API must be set to serve MCP OAuth protected-resource "
            "metadata (it is the authorization-server URL clients discover).",
        )
    _reject_bad_authority_chars(frontend_api, "CLERK_FRONTEND_API")
    authority = urlsplit(f"//{frontend_api}")
    if (
        authority.scheme
        or authority.path
        or authority.query
        or authority.fragment
        or authority.username
        or authority.password
        or _has_port_component(authority)
        or not authority.hostname
        # Contractually a Clerk DNS hostname: reject a trailing root dot (would make the
        # issuer differ from Clerk's published, canonical one) and IP literals (Clerk is
        # a DNS-only issuer and an IP can't form the issuer clients discover).
        or authority.hostname.endswith(".")
        or _is_ip_literal(authority.hostname)
    ):
        raise RuntimeError(
            "CLERK_FRONTEND_API must be a bare DNS hostname (no scheme, port, path, "
            "userinfo, query, fragment, trailing dot, or IP literal), e.g. "
            f"'clerk.example.com' — got {frontend_api!r}.",
        )
    # Build from the parsed, lowercased hostname so the advertised authorization-server
    # issuer is canonical (RFC 8414 requires code-point-identical issuer comparison).
    return f"https://{authority.hostname}"


def build_oauth_config(resource_url: str) -> OAuthConfig:
    """
    Validate the resource URL and Clerk config, and resolve them once into an
    immutable :class:`OAuthConfig`.

    Raises ``RuntimeError`` (loudly, at startup when called from a server's module
    load) for a misconfiguration that would otherwise publish unusable metadata:
    a non-absolute or non-HTTP(S) URL, a non-HTTPS resource off localhost, a URL
    carrying a query/fragment, or a path other than the MCP endpoint (:data:`MCP_PATH`).
    """
    _reject_bad_authority_chars(resource_url, "MCP resource URL")
    parts = urlsplit(resource_url)
    if parts.scheme not in ("http", "https"):
        raise RuntimeError(
            f"MCP resource URL must be an absolute http(s) URL — got {resource_url!r}.",
        )
    if not parts.hostname:
        raise RuntimeError(
            f"MCP resource URL must include a host — got {resource_url!r}.",
        )
    if parts.username or parts.password:
        raise RuntimeError(
            f"MCP resource URL must not include userinfo — got {resource_url!r}.",
        )
    _validated_port(parts, "MCP resource URL")
    is_localhost = parts.hostname in _LOCALHOST_HOSTS
    if parts.scheme != "https" and not is_localhost:
        raise RuntimeError(
            f"MCP resource URL must be HTTPS (except localhost dev) — got {resource_url!r}.",
        )
    if parts.query or parts.fragment:
        raise RuntimeError(
            f"MCP resource URL must not carry a query or fragment — got {resource_url!r}.",
        )
    if parts.path != MCP_PATH:
        raise RuntimeError(
            f"MCP resource URL path must be {MCP_PATH!r} (the MCP endpoint) — "
            f"got {parts.path!r} in {resource_url!r}.",
        )

    # Canonicalize the authority once (lowercase host, drop default port, bracket
    # IPv6) so the advertised resource and the derived allowed-hosts share one
    # identity and match the Host clients actually send. The path is preserved as-is.
    scheme, netloc = _canonical_scheme_netloc(parts)
    canonical_resource = urlunsplit((scheme, netloc, parts.path, "", ""))
    # RFC 9728 §3.1: insert the well-known segment between host and the resource path.
    metadata_url = urlunsplit((scheme, netloc, f"{WELL_KNOWN_PATH}{parts.path}", "", ""))
    return OAuthConfig(
        resource_url=canonical_resource,
        authorization_server=_clerk_authorization_server(),
        metadata_url=metadata_url,
    )


def build_protected_resource_metadata(config: OAuthConfig) -> dict[str, Any]:
    """Build the RFC 9728 protected-resource metadata document."""
    return {
        "resource": config.resource_url,
        "authorization_servers": [config.authorization_server],
        "bearer_methods_supported": ["header"],
        "scopes_supported": list(SCOPES_SUPPORTED),
    }


def make_metadata_endpoint(
    config: OAuthConfig,
) -> Callable[[Request], Awaitable[Response]]:
    """
    Build the well-known metadata route handler for a server's config.

    Returns a Starlette-style async handler usable both as a Starlette ``Route``
    (prompt server) and a FastMCP ``@custom_route`` (content server). CORS and
    OPTIONS preflight are handled by :func:`cors_middleware`, not here.
    """
    async def endpoint(request: Request) -> Response:  # noqa: ARG001
        return JSONResponse(build_protected_resource_metadata(config))

    return endpoint


def cors_middleware() -> Middleware:
    """
    CORS middleware for the MCP OAuth surface, mounted **outermost**.

    Handles browser preflight and injects CORS headers on every downstream
    response — including the gate's 401 challenge — in one place, and exposes
    ``WWW-Authenticate`` so browser clients can read the discovery pointer. This is
    the same ``CORSMiddleware`` pattern the main API uses.
    """
    return Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=_ALLOW_METHODS,
        allow_headers=_ALLOW_HEADERS,
        expose_headers=_EXPOSE_HEADERS,
    )


def _normalize_origin(value: str, env_var: str) -> str:
    """
    Validate and canonicalize one browser-``Origin`` allowlist entry.

    A browser serializes ``Origin`` as a bare ``scheme://host[:port]`` (no path, no
    trailing slash, lowercase, default port omitted). So a raw operator value like
    ``https://connector.example/`` would never match — canonicalize to that form and
    reject anything that isn't an origin (path, userinfo, query, fragment, stray
    characters, bad scheme/port). SDK ``:*`` wildcard-port patterns are deliberately
    not supported — list exact origins.
    """
    _reject_bad_authority_chars(value, env_var)
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https"):
        raise RuntimeError(
            f"{env_var} entries must be http(s) origins — got {value!r}.",
        )
    if not parts.hostname:
        raise RuntimeError(f"{env_var} entries must include a host — got {value!r}.")
    if parts.username or parts.password:
        raise RuntimeError(f"{env_var} entries must not include userinfo — got {value!r}.")
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise RuntimeError(
            f"{env_var} entries must be bare origins with no path/query/fragment — "
            f"got {value!r}.",
        )
    # A browser origin that can make authenticated cross-origin calls must be TLS —
    # a plain-HTTP remote origin is network-tamperable. Only loopback may use http.
    if parts.scheme != "https" and parts.hostname not in _LOCALHOST_HOSTS:
        raise RuntimeError(
            f"{env_var} entries must be HTTPS (except loopback dev origins) — got {value!r}.",
        )
    _validated_port(parts, f"{env_var} entry")
    scheme, netloc = _canonical_scheme_netloc(parts)
    return f"{scheme}://{netloc}"


def parse_allowed_origins(env_var: str = "MCP_ALLOWED_ORIGINS") -> list[str]:
    """
    Parse, validate, and canonicalize the comma-separated browser-``Origin`` allowlist
    for the ``/mcp`` transport.

    Empty by default — the Origin policy fails closed (see
    :func:`build_transport_security_settings`): server-side connectors omit ``Origin``
    and are unaffected; browser origins must be explicitly allowlisted. A malformed
    entry raises at startup (fail fast) rather than silently never matching. Production
    origins are populated here during the connector verification ladder. Order-preserving
    dedupe.
    """
    raw = os.getenv(env_var, "")
    origins = [_normalize_origin(item.strip(), env_var) for item in raw.split(",") if item.strip()]
    return list(dict.fromkeys(origins))


def build_transport_security_settings(
    config: OAuthConfig, allowed_origins: list[str],
) -> TransportSecuritySettings:
    """
    Build the MCP SDK's DNS-rebinding protection for the ``/mcp`` transport.

    ``allowed_hosts`` is the canonical authority of the (already-canonicalized) resource
    URL — the ``host[:port]`` clients connect to — always included, plus loopback
    aliases (``localhost``/``127.0.0.1``/``[::1]`` on the same port) when the resource
    host is a loopback form, so any local access path works. It is not
    connector-dependent. The ``Origin`` policy **fails closed**: a request with no
    ``Origin`` (server-side connectors) passes, but a browser ``Origin`` must be in
    ``allowed_origins`` — otherwise the SDK rejects it (``403``). Host mismatch is
    rejected (``421``). Applies only to the MCP transport, not ``/health`` or the public
    well-known metadata routes.
    """
    parts = urlsplit(config.resource_url)  # already canonical (default port stripped)
    hostname = parts.hostname or ""
    host = f"[{hostname}]" if ":" in hostname else hostname  # bracket IPv6 for the authority
    port = parts.port

    # Base authority hosts: the canonical host, plus loopback aliases when local.
    bases = [host]
    if hostname in _LOCALHOST_HOSTS:
        bases += ["localhost", "127.0.0.1", "[::1]"]

    # One port rule applied uniformly to every base: a default-port endpoint accepts
    # both the bare and explicit-default Host serializations (same endpoint, no
    # security cost); a non-default port is mandatory on every base.
    allowed_hosts: list[str] = []
    for base in bases:
        if port is None:
            allowed_hosts += [base, f"{base}:{_DEFAULT_PORTS[parts.scheme]}"]
        else:
            allowed_hosts.append(f"{base}:{port}")

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=list(dict.fromkeys(allowed_hosts)),
        allowed_origins=list(allowed_origins),
    )


def extract_bearer_token(authorization: str | None) -> str | None:
    """
    Extract the token from an ``Authorization`` header value, or ``None``.

    Case-insensitive scheme; any whitespace separates scheme and token (RFC 9110).
    This is the **single** bearer parser shared by the 401 gate, the prompt server's
    token stager, and the content server's token reader — so the gate can never admit
    a header that the stager/reader then drops (a divergent parser once did exactly
    that for a tab-separated header). Presence/format only; the token is NOT verified
    here — that is the backend's job.
    """
    if not authorization:
        return None
    parts = authorization.split(maxsplit=1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def _request_has_bearer(raw_headers: list[tuple[bytes, bytes]]) -> bool:
    """Presence check for a bearer token, using the shared :func:`extract_bearer_token`."""
    for name, value in raw_headers:
        if name.lower() == b"authorization":
            return extract_bearer_token(value.decode("latin-1")) is not None
    return False


class ProtectedResourceGate:
    """
    ASGI middleware: presence-only bearer gate on the MCP endpoint.

    A request to an MCP path (:func:`is_mcp_request_path`) with no bearer token is
    answered with ``401`` and a ``WWW-Authenticate: Bearer resource_metadata=...``
    header pointing at this server's protected-resource metadata (RFC 9728 §5.1),
    *before* any MCP dispatch — this is what triggers a client's OAuth bootstrap.

    A present bearer (valid or invalid) passes through untouched: the backend API
    is the only verifier (the proxy must not become one). ``/health`` and the
    well-known metadata paths are never gated. CORS/preflight is handled by the
    outer :func:`cors_middleware`, so a browser preflight (which carries no bearer)
    never reaches this gate.
    """

    def __init__(self, app: Any, config: OAuthConfig) -> None:
        self.app = app
        self._www_authenticate = f'Bearer resource_metadata="{config.metadata_url}"'

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        """Reject bearer-less MCP requests; pass everything else through."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if is_mcp_request_path(scope.get("path", "")) and not _request_has_bearer(
            scope.get("headers", []),
        ):
            response = JSONResponse(
                {
                    "error": "unauthorized",
                    "error_description": (
                        "Authentication required. Discover the authorization server "
                        "via the resource metadata in the WWW-Authenticate header."
                    ),
                },
                status_code=401,
                headers={"WWW-Authenticate": self._www_authenticate},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


class TransportSecurityGate:
    """
    ASGI middleware applying MCP DNS-rebinding Host/Origin validation on ``/mcp``.

    The prompt server passes :class:`TransportSecuritySettings` natively to its
    ``StreamableHTTPSessionManager``. The content server can't: FastMCP's
    ``http_app()`` constructs the session manager internally without exposing
    ``security_settings`` (and re-creates it each startup). So this gate applies the
    SDK's *own* ``TransportSecurityMiddleware`` validation, with the **same** settings
    (:func:`build_transport_security_settings`), at the ASGI layer — identical
    Host (``421``) / Origin (``403``) enforcement, only a different injection point.

    Runs after the presence gate (so a bearer-less request still gets the 401 discovery
    pointer first, matching the prompt server, where transport security sits inside the
    session manager past the gate). Non-``/mcp`` paths pass through untouched.
    """

    def __init__(self, app: Any, settings: TransportSecuritySettings) -> None:
        self.app = app
        self._validator = TransportSecurityMiddleware(settings)

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        """Validate Host/Origin on MCP requests; pass everything else through."""
        if scope["type"] != "http" or not is_mcp_request_path(scope.get("path", "")):
            await self.app(scope, receive, send)
            return

        # validate_request reads only headers (from scope), never the body, so the
        # receive channel is left intact for the downstream app.
        request = Request(scope, receive)
        is_post = scope.get("method", "").upper() == "POST"
        error = await self._validator.validate_request(request, is_post=is_post)
        if error is not None:
            await error(scope, receive, send)
            return

        await self.app(scope, receive, send)
