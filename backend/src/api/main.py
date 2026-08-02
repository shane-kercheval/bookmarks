"""FastAPI application entry point."""
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from api.routers import (
    ai,
    bookmarks,
    consent,
    content,
    filters,
    health,
    history,
    mcp,
    notes,
    prompts,
    public,
    relationships,
    settings,
    tags,
    tokens,
    users,
    webhooks,
)
from litellm.exceptions import (
    APIConnectionError as LiteLLMAPIConnectionError,
    APIError as LiteLLMAPIError,
    AuthenticationError as LiteLLMAuthenticationError,
    BadRequestError as LiteLLMBadRequestError,
    RateLimitError as LiteLLMRateLimitError,
    Timeout as LiteLLMTimeout,
)

from core.auth import DeletedIdentityError
from core.auth_cache import AuthCache, set_auth_cache
from core.config import get_settings
from core.http_cache import ETagMiddleware
from core.rate_limit_config import RateLimitExceededError
from core.redis import RedisClient, set_redis_client
from db.session import engine
from services.exceptions import FieldLimitExceededError, QuotaExceededError
from services.llm_service import LLMService, set_llm_service
from services.suggestion_service import LLMParseFailedError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    """Manage application lifespan - startup and shutdown."""
    app_settings = get_settings()

    # Startup: Connect to Redis
    redis_client = RedisClient(
        url=app_settings.redis_url,
        enabled=app_settings.redis_enabled,
        pool_size=app_settings.redis_pool_size,
    )
    await redis_client.connect()
    set_redis_client(redis_client)

    # Startup: Initialize auth cache
    auth_cache = AuthCache(redis_client)
    set_auth_cache(auth_cache)

    # Startup: Initialize LLM service
    llm_service = LLMService(app_settings)
    set_llm_service(llm_service)

    yield

    # Shutdown: Dispose database connection pool
    await engine.dispose()

    # Shutdown: Clean up LLM service, auth cache, and Redis
    set_llm_service(None)
    set_auth_cache(None)
    await redis_client.close()
    set_redis_client(None)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint,
    ) -> Response:
        """Process request and add security headers to response."""
        response = await call_next(request)
        # HSTS: enforce HTTPS for 1 year, including subdomains
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Prevent clickjacking - API shouldn't be framed
        response.headers["X-Frame-Options"] = "DENY"
        return response


class RateLimitHeadersMiddleware(BaseHTTPMiddleware):
    """Add rate limit headers to successful responses."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint,
    ) -> Response:
        """Process request and add rate limit headers to response."""
        response = await call_next(request)

        # Add headers if rate limit info was stored by dependency
        # Note: 429 responses are handled by exception handler, not middleware
        info = getattr(request.state, "rate_limit_info", None)
        if info:
            response.headers["X-RateLimit-Limit"] = str(info["limit"])
            response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
            response.headers["X-RateLimit-Reset"] = str(info["reset"])

        return response


app_settings = get_settings()


# Tag metadata surfaces as per-section introductions in the Swagger UI.
# Keep descriptions concise; point at docs/ for deeper coverage.
_OPENAPI_TAGS = [
    {
        "name": "ai",
        "description": (
            "AI-powered endpoints: tag / metadata / relationship / prompt-argument "
            "suggestions, plus supporting config endpoints (`/ai/health`, "
            "`/ai/models`, `/ai/validate-key`).\n\n"
            "### Authentication\n\n"
            "Session JWT (browser sign-in) required. Personal Access Tokens (`bm_*`) are rejected "
            "with 403 — AI features are deliberately not available to PATs as "
            "a cost-safety guard against automated scripts.\n\n"
            "### Bring-Your-Own-Key (BYOK)\n\n"
            "Optionally send `X-LLM-Api-Key: <provider key>` to use your own "
            "provider credentials instead of the platform's. BYOK calls consume "
            "the separate `AI_BYOK` rate-limit bucket (not `AI_PLATFORM`) and "
            "can select any supported `model`. Platform calls (header omitted) "
            "are silently locked to use-case defaults — the `model` request "
            "field is ignored. The header is held in request memory only — "
            "never logged, stored, or returned in error responses.\n\n"
            "### Rate limits\n\n"
            "AI endpoints use dedicated buckets (`AI_PLATFORM`, `AI_BYOK`) "
            "separate from the normal read/write quotas. Today only PRO tier "
            "has non-zero AI limits (FREE and STANDARD are `0/0` for both "
            "buckets and will always 429). Successful responses include "
            "`X-RateLimit-Limit` / `X-RateLimit-Remaining` / `X-RateLimit-Reset`. "
            "Tiddly-level 429s (tier quota exhausted) include `Retry-After`; "
            "provider-level 429s (`error_code: llm_rate_limited`) do not — "
            "use exponential backoff for those.\n\n"
            "`/ai/health` and `/ai/models` are the two exceptions — they skip "
            "the AI buckets AND the global read/write limiter entirely. Poll "
            "`/ai/health` freely to refresh quota-remaining UI; it returns "
            "both per-minute and daily remaining values.\n\n"
            "**Quota consumption vs. LLM call.** Rate-limit quota is charged "
            "*before* the handler runs (it's a FastAPI `Depends`). Even "
            "endpoints that short-circuit with an empty response (e.g. "
            "`/ai/suggest-relationships` when all inputs are empty, "
            "`/ai/suggest-prompt-arguments` when every placeholder in "
            "the template is already declared) still decrement the "
            "bucket. Only the LLM call itself is skipped.\n\n"
            "### Discovering models\n\n"
            "Call `GET /ai/models` to list supported model IDs and see the "
            "server's per-use-case defaults. The `model` field on BYOK "
            "requests must come from this list.\n\n"
            "### Error handling\n\n"
            "Most errors use a common envelope `{detail: string, error_code?: "
            "string}` — see the per-endpoint **Responses** panels for the full "
            "catalog. One shape is different:\n\n"
            "- **422** uses FastAPI's standard validation-error array: "
            "`{detail: [{loc, msg, type}, ...]}`. On suggestion endpoints, "
            "BYOK provider-auth failures also surface as 422 but with the "
            "common envelope and `error_code: llm_auth_failed`. "
            "`/ai/validate-key` is the exception — it normalizes provider "
            "auth failures to `200 {\"valid\": false}` because testing the "
            "key is the endpoint's explicit purpose.\n\n"
            "Typed `error_code` values starting with `llm_*` indicate upstream "
            "LLM provider failures (`llm_auth_failed`, `llm_rate_limited`, "
            "`llm_timeout`, `llm_bad_request`, `llm_connection_error`, "
            "`llm_parse_failed`, `llm_unavailable`)."
        ),
    },
]


_API_DESCRIPTION = """\
A content management system with tagging and search capabilities.

### Authentication

Every authenticated endpoint accepts a bearer token (an IdP session/OAuth JWT,
or a `bm_` Personal Access Token). Most auth failures are ordinary `401`s —
refresh or re-authenticate. **One `401` is terminal: `error_code:
"account_deleted"`** (in the standard `{detail, error_code}` envelope). The token
is valid but its account was deleted, so re-authenticating can never succeed (it
loops). Clients must match the machine-readable `error_code` — **not** the
human-readable `detail`, which may change — then clear local state and show a
deleted-account end state.

### Caching & conditional requests

Item reads (`GET /{type}/{id}` and `GET /{type}/{id}/metadata`) return **both** an
`ETag` and a `Last-Modified` header. **Revalidate with the `ETag` (`If-None-Match`) —
do not rely on `Last-Modified` / `If-Modified-Since` alone.**

Status changes — sharing (`POST`/`DELETE /{type}/{id}/share`,
`POST /{type}/{id}/rotate-share-token`) and lifecycle (archive, delete) —
intentionally do **not** bump `updated_at`, because they are not content edits
(it keeps the displayed "last updated" date honest). Consequently a
`Last-Modified`-only conditional request can return `304 Not Modified` even
though `is_public` / `public_token` (or `archived_at` / `deleted_at`) changed.
The `ETag` is computed from the full response body and always reflects these
changes, so an `If-None-Match` revalidation is correct in every case.

Note: this only affects how a *client caches its own reads*. Public-link access
control is always enforced live server-side — unpublishing or rotating a token
revokes the old URL immediately, regardless of any client or proxy cache.
"""


app = FastAPI(
    title="Tiddly API",
    description=_API_DESCRIPTION,
    version="0.1.0",
    lifespan=lifespan,
    openapi_tags=_OPENAPI_TAGS,
)


@app.exception_handler(RateLimitExceededError)
async def rate_limit_exception_handler(
    _request: Request, exc: RateLimitExceededError,
) -> JSONResponse:
    """Handle rate limit exceeded with proper headers."""
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please try again later."},
        headers={
            "Retry-After": str(exc.result.retry_after),
            "X-RateLimit-Limit": str(exc.result.limit),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(exc.result.reset),
        },
    )


@app.exception_handler(QuotaExceededError)
async def quota_exceeded_exception_handler(
    _request: Request, exc: QuotaExceededError,
) -> JSONResponse:
    """Handle quota exceeded errors with structured response."""
    return JSONResponse(
        status_code=402,
        content={
            "detail": str(exc),
            "error_code": "QUOTA_EXCEEDED",
            "resource": exc.resource,
            "current": exc.current,
            "limit": exc.limit,
        },
    )


@app.exception_handler(DeletedIdentityError)
async def deleted_identity_exception_handler(
    _request: Request, exc: DeletedIdentityError,
) -> JSONResponse:
    """
    Terminal deleted-account 401 (M8 anti-resurrection guard).

    Adds the stable ``account_deleted`` error_code to the standard
    ``{detail, error_code}`` envelope so clients distinguish this terminal 401
    from an ordinary expired-session 401, and preserves the exception's
    ``WWW-Authenticate`` header (a bare JSONResponse would otherwise drop it).
    Contract: core.auth.DeletedIdentityError, docs/ios-clerk-migration-guide.md.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "error_code": exc.error_code},
        headers=exc.headers,
    )


@app.exception_handler(FieldLimitExceededError)
async def field_limit_exceeded_exception_handler(
    _request: Request, exc: FieldLimitExceededError,
) -> JSONResponse:
    """Handle field length limit exceeded errors."""
    return JSONResponse(
        status_code=400,
        content={
            "detail": str(exc),
            "error_code": "FIELD_LIMIT_EXCEEDED",
            "field": exc.field,
            "current": exc.current,
            "limit": exc.limit,
        },
    )


# LiteLLM exception handlers — map provider errors to HTTP responses.
# Defined inline to match the pattern of existing exception handlers above.
# All LLM errors use llm_* error codes so the frontend can distinguish them
# from platform auth errors (which use HTTP 401).


@app.exception_handler(LiteLLMAuthenticationError)
async def llm_auth_exception_handler(
    _request: Request, exc: LiteLLMAuthenticationError,
) -> JSONResponse:
    """LLM authentication failed (bad API key) → 422."""
    logger.warning("llm_auth_failed", extra={"error": str(exc)})
    return JSONResponse(
        status_code=422,
        content={
            "detail": "LLM authentication failed. Check your API key.",
            "error_code": "llm_auth_failed",
        },
    )


@app.exception_handler(LiteLLMBadRequestError)
async def llm_bad_request_exception_handler(
    _request: Request, exc: LiteLLMBadRequestError,
) -> JSONResponse:
    """Invalid request to LLM provider → 400."""
    logger.warning("llm_bad_request", extra={"error": str(exc)})
    return JSONResponse(
        status_code=400,
        content={"detail": "Invalid request to LLM provider.", "error_code": "llm_bad_request"},
    )


@app.exception_handler(LiteLLMRateLimitError)
async def llm_rate_limit_exception_handler(
    _request: Request, exc: LiteLLMRateLimitError,
) -> JSONResponse:
    """LLM provider rate limit exceeded → 429."""
    logger.warning("llm_rate_limited", extra={"error": str(exc)})
    return JSONResponse(
        status_code=429,
        content={
            "detail": "LLM provider rate limit exceeded. Try again later.",
            "error_code": "llm_rate_limited",
        },
    )


@app.exception_handler(LiteLLMTimeout)
async def llm_timeout_exception_handler(
    _request: Request, exc: LiteLLMTimeout,
) -> JSONResponse:
    """LLM request timed out → 504."""
    logger.warning("llm_timeout", extra={"error": str(exc)})
    return JSONResponse(
        status_code=504,
        content={"detail": "LLM request timed out. Try again.", "error_code": "llm_timeout"},
    )


@app.exception_handler(LiteLLMAPIConnectionError)
async def llm_connection_exception_handler(
    _request: Request, exc: LiteLLMAPIConnectionError,
) -> JSONResponse:
    """Could not connect to LLM provider → 502."""
    logger.warning("llm_connection_error", extra={"error": str(exc)})
    return JSONResponse(
        status_code=502,
        content={
            "detail": "Could not connect to LLM provider.",
            "error_code": "llm_connection_error",
        },
    )


@app.exception_handler(LiteLLMAPIError)
async def llm_unavailable_exception_handler(
    _request: Request, exc: LiteLLMAPIError,
) -> JSONResponse:
    """Catch-all for unknown LiteLLM errors → 503."""
    logger.warning("llm_unavailable", extra={"error": str(exc)})
    return JSONResponse(
        status_code=503,
        content={"detail": "AI service temporarily unavailable.", "error_code": "llm_unavailable"},
    )


@app.exception_handler(LLMParseFailedError)
async def llm_parse_failed_exception_handler(
    _request: Request, exc: LLMParseFailedError,
) -> JSONResponse:
    """LLM returned an unparseable structured-output response → 502."""
    logger.warning("llm_parse_failed", extra={"error": exc.message})
    return JSONResponse(
        status_code=502,
        content={"detail": exc.message, "error_code": "llm_parse_failed"},
    )


# Rate limit headers middleware (innermost, runs first on response)
app.add_middleware(RateLimitHeadersMiddleware)

# ETag middleware (generates ETags, returns 304 when content unchanged)
# Added before SecurityHeadersMiddleware so 304 responses get security headers
app.add_middleware(ETagMiddleware)

# Security headers middleware (adds HSTS, X-Frame-Options, etc. to all responses)
app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=app_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=3600,
)

app.include_router(ai.router)
app.include_router(health.router)
app.include_router(users.router)
app.include_router(consent.router)
app.include_router(bookmarks.router)
app.include_router(notes.router)
app.include_router(prompts.router)
app.include_router(public.router)
app.include_router(content.router)
app.include_router(tags.router)
app.include_router(tokens.router)
app.include_router(filters.router)
app.include_router(settings.router)
app.include_router(history.router)
app.include_router(relationships.router)
app.include_router(mcp.router)
app.include_router(webhooks.router)
