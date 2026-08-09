"""
OAuth discovery + auth-gate integration tests for the Prompt MCP server app.

Exercises the real Starlette app (``prompt_mcp_server.main.app``): the well-known
protected-resource metadata routes, the presence-only 401 gate on ``/mcp``, browser
CORS, and startup config validation — proving the shared ``mcp_oauth`` pieces are
wired in. Values are pinned to fixed test values by the root conftest, so assertions
use fixed literals (not the module's own constants, and not a developer's real .env).
"""

import os
import subprocess
import sys
from pathlib import Path

import prompt_mcp_server
from httpx import ASGITransport, AsyncClient

from prompt_mcp_server.main import app
from shared.mcp_oauth import WELL_KNOWN_PATH, WELL_KNOWN_PATH_SUFFIXED

# Fixed values pinned by backend/tests/conftest.py::pytest_configure.
EXPECTED_RESOURCE = "http://localhost:8002/mcp"
EXPECTED_AUTH_SERVER = "https://test-instance.clerk.accounts.dev"
EXPECTED_METADATA_URL = "http://localhost:8002/.well-known/oauth-protected-resource/mcp"

_SRC_DIR = str(Path(prompt_mcp_server.__file__).resolve().parent.parent)


def _import_main_with_env(**overrides: str | None) -> subprocess.CompletedProcess[str]:
    """
    Import prompt_mcp_server.main (what uvicorn does at boot) in a subprocess with a
    deliberately constructed environment — never the developer's — so startup-validation
    behavior is deterministic. ``overrides`` with a None value are left unset.
    """
    env = {"PYTHONPATH": _SRC_DIR, "PATH": os.environ.get("PATH", "")}
    for key, value in overrides.items():
        if value is not None:
            env[key] = value
    return subprocess.run(
        [sys.executable, "-c", "import prompt_mcp_server.main"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


async def _get(path: str, **kwargs: object) -> object:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.get(path, **kwargs)


async def test__protected_resource_metadata__served_at_suffixed_path() -> None:
    """Canonical (/mcp-suffixed) path serves the full-endpoint resource + Clerk issuer."""
    response = await _get(WELL_KNOWN_PATH_SUFFIXED)

    assert response.status_code == 200
    body = response.json()
    assert body["resource"] == EXPECTED_RESOURCE
    assert body["authorization_servers"] == [EXPECTED_AUTH_SERVER]
    assert body["bearer_methods_supported"] == ["header"]
    assert body["scopes_supported"] == ["openid", "offline_access"]


async def test__protected_resource_metadata__served_at_root_compat_path() -> None:
    """Root well-known path is served too, as a compatibility fallback."""
    response = await _get(WELL_KNOWN_PATH)

    assert response.status_code == 200
    assert response.json()["resource"] == EXPECTED_RESOURCE


async def test__mcp_endpoint__rejects_missing_bearer_with_discovery_pointer() -> None:
    """No bearer on /mcp -> 401 with the RFC 9728 resource_metadata pointer (suffixed URL)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/mcp", json={"jsonrpc": "2.0", "method": "x", "id": 1})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == (
        f'Bearer resource_metadata="{EXPECTED_METADATA_URL}"'
    )


async def test__mcp_endpoint__browser_preflight_allowed_without_bearer() -> None:
    """A browser preflight for an authenticated POST is answered by CORS, not gated."""
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
    """Cross-origin unauthenticated POST -> 401 that exposes WWW-Authenticate."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/mcp", headers={"Origin": "https://client.example"})

    assert response.status_code == 401
    assert "www-authenticate" in response.headers["access-control-expose-headers"].lower()


def test__startup__crashes_without_clerk_frontend_api() -> None:
    """Importing the module (uvicorn's boot path) with CLERK_FRONTEND_API unset crashes."""
    result = _import_main_with_env(
        PROMPT_MCP_RESOURCE_URL="https://prompts.example.com/mcp",
        CLERK_FRONTEND_API=None,
    )

    assert result.returncode != 0
    assert "CLERK_FRONTEND_API" in result.stderr


def test__startup__crashes_without_resource_url() -> None:
    """A missing PROMPT_MCP_RESOURCE_URL crashes the process (no silent fallback)."""
    result = _import_main_with_env(
        CLERK_FRONTEND_API="clerk.example.com",
        PROMPT_MCP_RESOURCE_URL=None,
    )

    assert result.returncode != 0
    assert "PROMPT_MCP_RESOURCE_URL" in result.stderr


# The bearer-passes-the-gate regression (an existing `tiddly mcp configure`-style
# bearer config reaching MCP dispatch on its first request) is proven end-to-end by
# `test_integration.py::test__mcp_endpoint__exists`, which sends a bearer and owns the
# single allowed `session_manager.run()` lifespan; and at the gate boundary by
# `tests/shared/test_mcp_oauth.py::test__gate__present_bearer_passes_through`.
