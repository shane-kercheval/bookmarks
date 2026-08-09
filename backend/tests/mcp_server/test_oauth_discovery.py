"""
OAuth discovery + auth-gate + transport-security tests for the Content MCP server app.

Exercises the real FastMCP-derived ASGI app (``mcp_server.app.app``): the well-known
metadata routes, the presence-only 401 gate, browser CORS, and the DNS-rebinding
Host/Origin gate (applied at the ASGI layer here, since FastMCP's http_app() does not
expose the session manager's security_settings). Values are pinned to fixed test values
by the root conftest, so assertions use fixed literals.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import mcp_server
import pytest
import respx
from httpx import ASGITransport, AsyncClient, Response

from mcp_server.app import app

EXPECTED_RESOURCE = "http://localhost:8001/mcp"
EXPECTED_AUTH_SERVER = "https://test-instance.clerk.accounts.dev"
EXPECTED_METADATA_URL = "http://localhost:8001/.well-known/oauth-protected-resource/mcp"

_SRC_DIR = str(Path(mcp_server.__file__).resolve().parent.parent)

_INIT = {
    "jsonrpc": "2.0", "method": "initialize", "id": 1,
    "params": {"protocolVersion": "2024-11-05", "capabilities": {},
               "clientInfo": {"name": "test", "version": "1.0.0"}},
}
_MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Authorization": "Bearer bm_test",
}


_WELL_KNOWN_PATHS = [
    "/.well-known/oauth-protected-resource/mcp",
    "/.well-known/oauth-protected-resource",
]


@pytest.mark.parametrize("path", _WELL_KNOWN_PATHS)
async def test__protected_resource_metadata__served_with_cors(path: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(path, headers={"Origin": "https://client.example"})

    assert response.status_code == 200
    body = response.json()
    assert body["resource"] == EXPECTED_RESOURCE
    assert body["authorization_servers"] == [EXPECTED_AUTH_SERVER]
    assert body["bearer_methods_supported"] == ["header"]
    assert body["scopes_supported"] == ["openid", "offline_access"]
    assert response.headers["access-control-allow-origin"] == "*"


@pytest.mark.parametrize("path", _WELL_KNOWN_PATHS)
async def test__protected_resource_metadata__cors_preflight(path: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.options(
            path,
            headers={
                "Origin": "https://client.example",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"


async def test__health__reachable_without_auth() -> None:
    """Railway liveness: /health is public through the assembled app."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


async def test__mcp_endpoint__rejects_missing_bearer_with_discovery_pointer() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/mcp", json={"jsonrpc": "2.0", "method": "x", "id": 1})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == (
        f'Bearer resource_metadata="{EXPECTED_METADATA_URL}"'
    )


async def test__mcp_endpoint__browser_preflight_allowed() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.options(
            "/mcp",
            headers={
                "Origin": "https://client.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization, content-type",
            },
        )

    assert response.status_code == 200
    assert "POST" in response.headers["access-control-allow-methods"]


async def test__mcp_endpoint__401_challenge_is_browser_readable() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/mcp", headers={"Origin": "https://client.example"})

    assert response.status_code == 401
    assert "www-authenticate" in response.headers["access-control-expose-headers"].lower()


async def test__transport_security__rejects_foreign_host() -> None:
    """A bearer-carrying request (past the presence gate) with a foreign Host -> 421."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost:8001") as c:
        response = await c.post(
            "/mcp", json=_INIT, headers={**_MCP_HEADERS, "Host": "evil.example.com"},
        )

    assert response.status_code == 421


async def test__transport_security__unknown_origin_fails_closed() -> None:
    """A bearer-carrying request with an unknown browser Origin -> 403."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost:8001") as c:
        response = await c.post(
            "/mcp", json=_INIT, headers={**_MCP_HEADERS, "Origin": "https://attacker.test"},
        )

    assert response.status_code == 403


async def test__mcp_endpoint__bearer_config_reaches_dispatch() -> None:
    """
    Regression: an existing bearer config reaches FastMCP tool dispatch through the new
    ASGI layer (entrypoint change from mcp.run to http_app didn't break normal use).
    Needs the app lifespan to initialize FastMCP's session manager.
    """
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://localhost:8001",
        ) as client:
            response = await client.post("/mcp", json=_INIT, headers=_MCP_HEADERS)

    # FastMCP's default transport streams the JSON-RPC result as SSE (event: message).
    assert response.status_code == 200
    assert '"jsonrpc":"2.0"' in response.text
    assert '"result"' in response.text


def _sse_json(text: str) -> list[dict[str, Any]]:
    """Extract JSON objects from a streamable-HTTP SSE body's ``data:`` lines."""
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        if line.startswith("data:"):
            payload = line[len("data:"):].strip()
            if payload:
                out.append(json.loads(payload))
    return out


async def test__tools_call__forwards_caller_bearer_to_backend(
    mock_api: respx.MockRouter, sample_bookmark_list: dict[str, Any],
) -> None:
    """
    Regression for the mcp.run()->http_app() switch: a real tool call through the
    composed ASGI app resolves the caller's bearer via the genuine get_http_headers()
    path (not patched) and forwards that exact token to the backend API.
    """
    token = "bm_distinctive_regression_token"
    route = mock_api.get("/bookmarks/").mock(return_value=Response(200, json=sample_bookmark_list))
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://localhost:8001",
        ) as client:
            init = await client.post("/mcp", json=_INIT, headers=headers)
            assert init.status_code == 200
            session = {"mcp-session-id": init.headers["mcp-session-id"]} \
                if "mcp-session-id" in init.headers else {}
            await client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                headers={**headers, **session},
            )
            call = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0", "method": "tools/call", "id": 2,
                    "params": {"name": "search_items", "arguments": {"type": "bookmark"}},
                },
                headers={**headers, **session},
            )

    assert call.status_code == 200
    results = _sse_json(call.text)
    assert results  # a JSON-RPC response came back
    assert "result" in results[-1]  # a tool result, not an error
    # The proxied backend request carried the caller's exact bearer.
    assert route.called
    assert route.calls.last.request.headers["authorization"] == f"Bearer {token}"


def test__startup__crashes_without_resource_url() -> None:
    """Importing the server module (uvicorn's boot path) without its resource URL crashes."""
    env = {"PYTHONPATH": _SRC_DIR, "CLERK_FRONTEND_API": "clerk.example.com"}
    result = subprocess.run(
        [sys.executable, "-c", "import mcp_server.app"],
        env=env, capture_output=True, text=True, check=False,
    )

    assert result.returncode != 0
    assert "CONTENT_MCP_RESOURCE_URL" in result.stderr
