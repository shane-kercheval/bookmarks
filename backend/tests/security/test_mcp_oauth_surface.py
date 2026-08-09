"""
Security review of the MCP servers' new unauthenticated HTTP surface (M5 OAuth).

The OAuth discovery metadata and the 401 challenge are the first new *unauthenticated*
HTTP surface on the MCP servers. These adversarial checks assert the surface is minimal
and can't be walked into tool dispatch, across BOTH servers (they share the mcp_oauth
module but are assembled differently — hand-built Starlette vs FastMCP http_app):

- the metadata discloses exactly the RFC 9728 spec fields and nothing else;
- ``/health`` and the well-known routes are the only public surface;
- an unauthenticated request to the MCP endpoint (or any subpath) is rejected with the
  401 discovery challenge before reaching dispatch — the challenge pointer is the only
  thing disclosed.

Token *verification* is the backend API's job (AD10) and is covered by the backend auth
suite; the MCP proxy deliberately does not verify, so it is not re-asserted here.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from mcp_server.app import app as content_app
from prompt_mcp_server.main import app as prompt_app

APPS = [
    pytest.param(content_app, id="content"),
    pytest.param(prompt_app, id="prompt"),
]
WELL_KNOWN = [
    "/.well-known/oauth-protected-resource/mcp",
    "/.well-known/oauth-protected-resource",
]
_SPEC_FIELDS = {"resource", "authorization_servers", "bearer_methods_supported", "scopes_supported"}


@pytest.mark.parametrize("app", APPS)
@pytest.mark.parametrize("path", WELL_KNOWN)
async def test__metadata__discloses_only_spec_fields(app: object, path: str) -> None:
    """Metadata is public by necessity, so content is the only control: no leakage."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(path)

    assert response.status_code == 200
    assert set(response.json().keys()) == _SPEC_FIELDS


@pytest.mark.parametrize("app", APPS)
async def test__health__public_and_minimal(app: object) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


@pytest.mark.parametrize("app", APPS)
@pytest.mark.parametrize("path", ["/mcp", "/mcp/", "/mcp/messages"])
async def test__mcp_endpoint__unauthenticated_cannot_reach_dispatch(
    app: object, path: str,
) -> None:
    """
    No bearer on the MCP endpoint or any subpath -> 401 challenge before dispatch;
    the only thing disclosed is the WWW-Authenticate metadata pointer.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(path, json={"jsonrpc": "2.0", "method": "tools/list", "id": 1})

    assert response.status_code == 401
    www_auth = response.headers.get("www-authenticate", "")
    assert www_auth.startswith("Bearer resource_metadata=")
