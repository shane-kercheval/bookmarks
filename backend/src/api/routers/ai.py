"""AI feature endpoints."""
import logging
import time
from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from litellm.exceptions import AuthenticationError
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_limits_ai, get_current_user_ai
from core.rate_limit_config import OperationType, RateLimitExceededError
from core.rate_limiter import check_rate_limit, get_ai_rate_limit_status
from core.tier_limits import TierLimits, get_tier_safely
from db.session import get_async_session
from models.user import User
from schemas.ai import (
    AIErrorResponse,
    AIHealthResponse,
    AIModelsResponse,
    RelationshipCandidateContext,
    SuggestMetadataRequest,
    SuggestMetadataResponse,
    SuggestPromptArgumentFieldsRequest,
    SuggestPromptArgumentsRequest,
    SuggestPromptArgumentsResponse,
    SuggestRelationshipsRequest,
    SuggestRelationshipsResponse,
    SuggestTagsRequest,
    SuggestTagsResponse,
    TagVocabularyEntry,
    ValidateKeyRequest,
    ValidateKeyResponse,
)
from schemas.cached_user import CachedUser
from services.ai_cost_tracking import track_cost
from services.content_service import search_all_content
from services.llm_service import (
    AIUseCase,
    LLMConfig,
    LLMService,
    UnsupportedModelError,
    get_llm_service,
)
from services.suggestion_service import (
    LLMParseFailedError,
    LLMResponseParseError,
    suggest_metadata,
    suggest_prompt_argument_fields,
    suggest_prompt_arguments,
    suggest_relationships,
    suggest_tags,
)
from services.tag_service import get_user_tags_with_counts

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])


# ---------------------------------------------------------------------------
# Shared error-response schemas (populate `responses=` on each endpoint)
# ---------------------------------------------------------------------------

# Errors that every AI endpoint (config or suggestion) may return.
_BASE_AI_ERROR_RESPONSES: dict[int, dict] = {
    401: {
        "model": AIErrorResponse,
        "description": "Missing or invalid session JWT (no `Authorization` header or bad token).",
        "content": {
            "application/json": {
                "example": {
                    "detail": "Invalid token",
                },
            },
        },
    },
    403: {
        "model": AIErrorResponse,
        "description": (
            "Authenticated but not allowed. Most commonly: the caller supplied a "
            "Personal Access Token (`bm_*`). AI endpoints are session-only — PATs "
            "are rejected as a defense-in-depth signal that these endpoints are "
            "not intended for automated / programmatic use."
        ),
        "content": {
            "application/json": {
                "example": {
                    "detail": (
                        "This endpoint is not available for API tokens. "
                        "Please use the web interface."
                    ),
                },
            },
        },
    },
    422: {
        "description": (
            "FastAPI / Pydantic request validation failed (missing required "
            "field, oversized payload, values outside permitted literals, "
            "etc.). Response follows FastAPI's standard validation-error "
            "shape: `{\"detail\": [{\"loc\": [...], \"msg\": \"...\", "
            "\"type\": \"...\"}]}`, **not** the `AIErrorResponse` envelope "
            "used for other 4xx/5xx errors."
        ),
    },
    503: {
        "model": AIErrorResponse,
        "description": (
            "Auth infrastructure unavailable (JWKS fetch from the identity provider failed). "
            "`detail` is `\"Could not validate credentials\"`; no "
            "`error_code` is set for this path. Retry with backoff. "
            "Suggestion endpoints can also return 503 for LLM-provider "
            "failures (`error_code: llm_unavailable`) — that variant is "
            "documented separately in those endpoints' Responses panels."
        ),
        "content": {
            "application/json": {
                "example": {
                    "detail": "Could not validate credentials",
                },
            },
        },
    },
}

# Additional errors that only occur on endpoints that actually invoke an LLM
# (suggestion endpoints + validate-key). Config-only endpoints like /health and
# /models do not return these.
_LLM_CALL_ERROR_RESPONSES: dict[int, dict] = {
    400: {
        "model": AIErrorResponse,
        "description": (
            "Invalid request. Typed variants: `llm_bad_request` (LLM provider "
            "rejected the request shape). Also: the supplied `model` is not in "
            "the supported list (no `error_code`; message starts with "
            "\"Unsupported model\")."
        ),
        "content": {
            "application/json": {
                "examples": {
                    "unsupported_model": {
                        "summary": "BYOK caller passed an unsupported `model`",
                        "value": {
                            "detail": "Unsupported model: evil/attacker-model",
                        },
                    },
                    "llm_bad_request": {
                        "summary": "Provider rejected the request shape",
                        "value": {
                            "detail": "Invalid request to LLM provider.",
                            "error_code": "llm_bad_request",
                        },
                    },
                },
            },
        },
    },
    429: {
        "model": AIErrorResponse,
        "description": (
            "Two sources. (1) **Tiddly per-tier AI rate limit** — no "
            "`error_code`; bare rate-limiter message in `detail`; `Retry-After` "
            "response header present. Only PRO tier has non-zero AI quota "
            "today, so FREE and STANDARD callers always hit this variant. "
            "(2) **Upstream provider rate limit** (`error_code: llm_rate_limited`) "
            "— no `Retry-After` header is set for provider 429s; use "
            "exponential backoff."
        ),
        "content": {
            "application/json": {
                "examples": {
                    "tiddly_quota_exhausted": {
                        "summary": "Tiddly per-tier quota (includes Retry-After header)",
                        "value": {
                            "detail": "Rate limit exceeded. Please try again later.",
                        },
                    },
                    "provider_rate_limited": {
                        "summary": "Upstream LLM provider rate-limited",
                        "value": {
                            "detail": "LLM provider rate limit exceeded. Try again later.",
                            "error_code": "llm_rate_limited",
                        },
                    },
                },
            },
        },
    },
    502: {
        "model": AIErrorResponse,
        "description": (
            "LLM-side failure with two typed variants: `llm_parse_failed` "
            "(the provider returned a response that didn't match the "
            "expected structured-output schema) and `llm_connection_error` "
            "(could not reach the provider). Both are safe to retry — a "
            "different `model` often helps for parse failures."
        ),
        "content": {
            "application/json": {
                "examples": {
                    "llm_parse_failed": {
                        "summary": "Provider returned unparseable structured output",
                        "value": {
                            "detail": (
                                "LLM returned an invalid response. Try again "
                                "or use a different model."
                            ),
                            "error_code": "llm_parse_failed",
                        },
                    },
                    "llm_connection_error": {
                        "summary": "Could not reach the LLM provider",
                        "value": {
                            "detail": "Could not connect to LLM provider.",
                            "error_code": "llm_connection_error",
                        },
                    },
                },
            },
        },
    },
    503: {
        "model": AIErrorResponse,
        "description": (
            "Two sources. (1) **Auth infrastructure unavailable** — JWKS "
            "fetch from the identity provider failed. `detail` is `\"Could not validate "
            "credentials\"`; no `error_code`. (2) **Unclassified LLM "
            "provider failure** — `error_code: llm_unavailable`. Both are "
            "safe to retry with backoff."
        ),
        "content": {
            "application/json": {
                "examples": {
                    "jwks_unavailable": {
                        "summary": "JWKS fetch failed during token validation",
                        "value": {
                            "detail": "Could not validate credentials",
                        },
                    },
                    "llm_unavailable": {
                        "summary": "Unclassified LLM provider failure",
                        "value": {
                            "detail": "AI service temporarily unavailable.",
                            "error_code": "llm_unavailable",
                        },
                    },
                },
            },
        },
    },
    504: {
        "model": AIErrorResponse,
        "description": (
            "LLM request timed out (`llm_timeout`). Safe to retry.\n\n"
            "The server enforces a ~15s ceiling on the upstream LLM call with "
            "no server-side retry — the endpoint is tuned for interactive "
            "latency rather than batch resilience. Clients should set their "
            "own request timeout to at least 20s to avoid cancelling requests "
            "the server was about to answer."
        ),
        "content": {
            "application/json": {
                "example": {
                    "detail": "LLM request timed out. Try again.",
                    "error_code": "llm_timeout",
                },
            },
        },
    },
}

# BYOK authentication failure shows up on endpoints that actually use the
# BYOK key (suggestion endpoints). 422 is also the shape for Pydantic request
# validation, so the response carries two possible body shapes — distinguish
# on whether `detail` is an array (validation) or string with `error_code`
# (BYOK auth failure).
_BYOK_AUTH_422: dict[int, dict] = {
    422: {
        # Deliberately no `model:` entry. The BYOK-auth variant matches
        # `AIErrorResponse` but the Pydantic validation variant doesn't
        # (its `detail` is a list). Declaring one model would mislead
        # typed codegen tools (openapi-generator, Zod from OpenAPI, etc.)
        # into emitting a type that only handles the BYOK-auth shape.
        # The two named examples below cover both shapes for humans;
        # codegen tools correctly produce an un-schema'd 422 response.
        # Matches the base `_BASE_AI_ERROR_RESPONSES[422]` pattern.
        "description": (
            "Two possible shapes share this status: (1) FastAPI request "
            "validation errors (standard `{\"detail\": [...]}` array shape), "
            "or (2) BYOK authentication failure with the upstream LLM "
            "provider — shape `{\"detail\": \"...\", \"error_code\": "
            "\"llm_auth_failed\"}`. Clients can distinguish by the type of "
            "`detail` (list vs. string) or by the presence of `error_code`."
        ),
        "content": {
            "application/json": {
                "examples": {
                    "request_validation": {
                        "summary": "FastAPI validation error (missing / malformed field)",
                        "value": {
                            "detail": [
                                {
                                    "type": "missing",
                                    "loc": ["body", "content_type"],
                                    "msg": "Field required",
                                    "input": {},
                                },
                            ],
                        },
                    },
                    "byok_auth_failed": {
                        "summary": "Provider rejected the supplied X-LLM-Api-Key",
                        "value": {
                            "detail": "LLM authentication failed. Check your API key.",
                            "error_code": "llm_auth_failed",
                        },
                    },
                },
            },
        },
    },
}

# Suggestion endpoints surface all error classes (auth, validation,
# LLM-call failures, BYOK auth failure).
#
# Merge precedence (right wins on key collision, per Python dict-spread):
#   _BASE_AI_ERROR_RESPONSES < _LLM_CALL_ERROR_RESPONSES < _BYOK_AUTH_422
# Concretely: 422 is defined in _BASE (Pydantic-only description) and
# overridden by _BYOK_AUTH_422 (dual-shape description). 503 is in _BASE
# (JWKS-only) and overridden by _LLM_CALL_ERROR_RESPONSES (dual-source).
AI_SUGGESTION_RESPONSES: dict[int, dict] = {
    **_BASE_AI_ERROR_RESPONSES,
    **_LLM_CALL_ERROR_RESPONSES,
    **_BYOK_AUTH_422,
}

# Endpoint-specific 400 override for /ai/suggest-prompt-argument-fields: adds
# the `target_index_out_of_range` example so the only endpoint that can
# return it documents it. Other suggestion endpoints keep the cleaner
# `AI_SUGGESTION_RESPONSES` variant — their Swagger no longer leaks an
# example that couldn't occur there.
#
# Composed (not copied) from the shared 400 dict — any future edit to the
# shared prose or examples flows through here automatically; only the
# target_index delta is local to this override.
_SHARED_400 = _LLM_CALL_ERROR_RESPONSES[400]
_SUGGEST_PROMPT_ARGUMENT_FIELDS_400: dict[int, dict] = {
    400: {
        **_SHARED_400,
        "description": (
            _SHARED_400["description"]
            + " Also: service-level semantic validation failures on "
              "`target_index` (the index is a valid non-negative integer "
              "but exceeds `arguments` length — no `error_code`, message "
              "in `detail`)."
        ),
        "content": {
            "application/json": {
                "examples": {
                    **_SHARED_400["content"]["application/json"]["examples"],
                    "target_index_out_of_range": {
                        "summary": "suggest-prompt-argument-fields service validation",
                        "value": {
                            "detail": "target_index 5 is out of range (arguments has 2 items)",
                        },
                    },
                },
            },
        },
    },
}
SUGGEST_PROMPT_ARGUMENT_FIELDS_RESPONSES: dict[int, dict] = {
    **AI_SUGGESTION_RESPONSES,
    **_SUGGEST_PROMPT_ARGUMENT_FIELDS_400,
}

# Config endpoints (/health, /models) surface only the shared base set plus
# the standard Pydantic validation error for 422. They never invoke an LLM.
AI_CONFIG_RESPONSES: dict[int, dict] = _BASE_AI_ERROR_RESPONSES

# /validate-key is a special case: it DOES call the LLM, but only to probe
# auth. Provider auth failures are returned as 200 {"valid": false} rather
# than 422, so the 422 variant is pure Pydantic validation here. It also has
# distinct 400 and 502 semantics vs. suggestion endpoints:
#   - 400 includes the "missing X-LLM-Api-Key header" path.
#   - 502 cannot emit `llm_parse_failed` (no `response_format` passed to
#     LLMService.complete), so only `llm_connection_error` is documented.
AI_VALIDATE_KEY_RESPONSES: dict[int, dict] = {
    **_BASE_AI_ERROR_RESPONSES,
    400: {
        "model": AIErrorResponse,
        "description": (
            "Invalid request. Typed variants: missing `X-LLM-Api-Key` header "
            "(no `error_code`; message `\"No API key provided via "
            "X-LLM-Api-Key header\"` in `detail`); `llm_bad_request` (LLM "
            "provider rejected the request shape); unsupported `model` value "
            "(no `error_code`; message starts with `\"Unsupported model\"`)."
        ),
    },
    429: _LLM_CALL_ERROR_RESPONSES[429],
    502: {
        "model": AIErrorResponse,
        "description": (
            "Could not reach the LLM provider (`error_code: "
            "llm_connection_error`). Safe to retry. Note: this endpoint "
            "never emits `llm_parse_failed` — it doesn't request structured "
            "output from the provider."
        ),
    },
    503: _LLM_CALL_ERROR_RESPONSES[503],
    504: _LLM_CALL_ERROR_RESPONSES[504],
}


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def get_llm_api_key(
    x_llm_api_key: str | None = Header(
        None,
        alias="X-LLM-Api-Key",
        description=(
            "Optional Bring-Your-Own-Key (BYOK) header. On suggestion "
            "endpoints it routes the call to the `AI_BYOK` rate-limit "
            "bucket and unlocks the `model` request field. On `/ai/health` "
            "and `/ai/models` it only affects which bucket's quota is "
            "reported — the field is not used for a provider call. See the "
            "`ai` tag description for full BYOK semantics."
        ),
    ),
) -> str | None:
    """Extract optional BYOK API key from request header."""
    return x_llm_api_key


def _resolve_config_or_400(
    llm_service: LLMService,
    use_case: AIUseCase,
    user_api_key: str | None,
    user_model: str | None,
) -> LLMConfig:
    """
    Wrapper around `LLMService.resolve_config` that converts the service's
    typed `UnsupportedModelError` into a 400 `HTTPException` with the
    unsupported-model message surfaced in `detail`.

    Intentionally does NOT catch bare `ValueError`: any other `ValueError`
    leaking from `resolve_config` (or code beneath it) represents a bug
    rather than bad client input, and should surface as a generic 500 with
    no internal message leaked to the caller.
    """
    try:
        return llm_service.resolve_config(
            use_case,
            user_api_key=user_api_key,
            user_model=user_model,
        )
    except UnsupportedModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def apply_ai_rate_limit_byok(
    request: Request,
    current_user: User | CachedUser = Depends(get_current_user_ai),
    llm_api_key: str | None = Depends(get_llm_api_key),
) -> None:
    """
    Enforce AI rate limiting for BYOK-only endpoints (e.g. validate-key).

    Returns early if no BYOK key is present (no quota consumed).
    """
    if not llm_api_key:
        return
    tier = get_tier_safely(current_user.tier)
    result = await check_rate_limit(current_user.id, OperationType.AI_BYOK, tier)
    request.state.rate_limit_info = {
        "limit": result.limit,
        "remaining": result.remaining,
        "reset": result.reset,
    }
    if not result.allowed:
        raise RateLimitExceededError(result)


async def apply_ai_rate_limit(
    request: Request,
    current_user: User | CachedUser = Depends(get_current_user_ai),
    llm_api_key: str | None = Depends(get_llm_api_key),
) -> None:
    """
    Enforce AI rate limiting for suggestion endpoints.

    Selects AI_BYOK or AI_PLATFORM bucket based on BYOK header.
    All suggestion endpoints use this — every call consumes quota.
    """
    op_type = OperationType.AI_BYOK if llm_api_key else OperationType.AI_PLATFORM
    tier = get_tier_safely(current_user.tier)
    result = await check_rate_limit(current_user.id, op_type, tier)
    request.state.rate_limit_info = {
        "limit": result.limit,
        "remaining": result.remaining,
        "reset": result.reset,
    }
    if not result.allowed:
        raise RateLimitExceededError(result)


# ---------------------------------------------------------------------------
# Config endpoints (no AI rate limit consumed)
# ---------------------------------------------------------------------------


@router.get(
    "/health",
    response_model=AIHealthResponse,
    responses=AI_CONFIG_RESPONSES,
    summary="AI availability and remaining quota",
)
async def ai_health(
    current_user: User | CachedUser = Depends(get_current_user_ai),
    limits: TierLimits = Depends(get_current_limits_ai),
    llm_api_key: str | None = Depends(get_llm_api_key),
) -> AIHealthResponse:
    """
    Return whether AI features are available for the caller, plus remaining
    per-minute and daily quota in the bucket that the supplied `X-LLM-Api-Key`
    header selects (present → `AI_BYOK`, absent → `AI_PLATFORM`).

    Does **not** consume quota of any kind — this endpoint skips the global
    read/write rate limiter AND does not charge the AI buckets. Safe to poll
    before each call to refresh quota-remaining UI.

    See the `ai` tag description for tier-specific AI quota details.
    """
    has_byok = llm_api_key is not None
    ai_bucket = OperationType.AI_BYOK if has_byok else OperationType.AI_PLATFORM
    quota = await get_ai_rate_limit_status(
        current_user.id, ai_bucket, get_tier_safely(current_user.tier),
    )
    # `available` requires BOTH windows non-zero for whichever bucket applies.
    # A tier with daily>0 but per-minute=0 would otherwise report available=True
    # yet always 429 on the first call — a real trap.
    platform_ok = limits.rate_ai_per_minute > 0 and limits.rate_ai_per_day > 0
    byok_ok = (
        has_byok
        and limits.rate_ai_byok_per_minute > 0
        and limits.rate_ai_byok_per_day > 0
    )
    return AIHealthResponse(
        available=platform_ok or byok_ok,
        byok=has_byok,
        remaining_per_minute=quota.remaining_per_minute,
        limit_per_minute=quota.limit_per_minute,
        remaining_per_day=quota.remaining_per_day,
        limit_per_day=quota.limit_per_day,
        resets_at=quota.resets_at,
    )


@router.post(
    "/validate-key",
    response_model=ValidateKeyResponse,
    responses=AI_VALIDATE_KEY_RESPONSES,
    summary="Probe a BYOK key against the selected provider",
)
async def validate_key(
    body: ValidateKeyRequest = ValidateKeyRequest(),
    _current_user: User | CachedUser = Depends(get_current_user_ai),
    llm_api_key: str | None = Depends(get_llm_api_key),
    _rate_limit: None = Depends(apply_ai_rate_limit_byok),
) -> ValidateKeyResponse:
    """
    Confirm that the BYOK API key supplied in `X-LLM-Api-Key` is accepted by
    the provider implied by the request's `model` (or the default if no model
    is specified). Performs a minimal 5-token completion call against the
    provider.

    Requires `X-LLM-Api-Key`; returns 400 if the header is missing **without
    consuming quota** (the rate-limit dependency short-circuits when no BYOK
    key is present).

    **Response semantics:**

    - `200 {"valid": true}` — provider accepted the key.
    - `200 {"valid": false, "error": "API key rejected by provider"}` —
      provider returned an authentication error. The 200 status reflects
      that the validation *request* succeeded; the key itself is simply
      invalid. Note this is **not** surfaced as 422 `llm_auth_failed` —
      that's the semantics on suggestion endpoints where the caller
      expects the key to work; here it's the endpoint's explicit purpose.
    - Non-200 responses (see **Responses**) indicate a failure of the
      validation process itself, not of the key.

    **Authentication, rate limits, BYOK, and error handling**: see the `ai`
    tag description at the top of this section.
    """
    if not llm_api_key:
        raise HTTPException(status_code=400, detail="No API key provided via X-LLM-Api-Key header")

    llm_service = get_llm_service()
    config = _resolve_config_or_400(
        llm_service, AIUseCase.SUGGESTIONS, llm_api_key, body.model,
    )
    try:
        await llm_service.complete(
            messages=[{"role": "user", "content": "This is a test. Respond with 'ok'."}],
            config=config,
            max_tokens=5,
            temperature=0,
        )
        return ValidateKeyResponse(valid=True)
    except AuthenticationError:
        return ValidateKeyResponse(valid=False, error="API key rejected by provider")


@router.get(
    "/models",
    response_model=AIModelsResponse,
    responses=AI_CONFIG_RESPONSES,
    summary="List supported models and per-use-case defaults",
)
async def ai_models(
    _current_user: User | CachedUser = Depends(get_current_user_ai),
) -> AIModelsResponse:
    """
    Return the curated list of supported model IDs (for use as the `model` field
    on BYOK suggestion requests) plus the server's current per-use-case default
    model IDs.

    Only GA models appear here — preview/experimental models are excluded. The
    list changes with LiteLLM version bumps and operational decisions (e.g. the
    Gemini Flash / Pro entries are deliberately omitted due to chronic 503s
    from Google's API).

    Does **not** consume quota of any kind — this endpoint skips the global
    read/write rate limiter AND does not charge the AI buckets. Authentication
    still applies.
    """
    llm_service = get_llm_service()
    return AIModelsResponse(
        models=llm_service.supported_models,
        defaults={
            uc.value: llm_service.get_model_for_use_case(uc)
            for uc in AIUseCase
        },
    )


# ---------------------------------------------------------------------------
# Suggestion endpoints (consume AI rate limit)
# ---------------------------------------------------------------------------


@router.post(
    "/suggest-tags",
    response_model=SuggestTagsResponse,
    responses=AI_SUGGESTION_RESPONSES,
    summary="Suggest tags for a bookmark, note, or prompt",
)
async def suggest_tags_endpoint(
    data: SuggestTagsRequest,
    current_user: User | CachedUser = Depends(get_current_user_ai),
    llm_api_key: str | None = Depends(get_llm_api_key),
    _rate_limit: None = Depends(apply_ai_rate_limit),
    db: AsyncSession = Depends(get_async_session),
) -> SuggestTagsResponse:
    """
    Suggest tags for a bookmark, note, or prompt based on metadata context
    and the caller's existing tag vocabulary.

    ### Request fields

    | Field | Required | Default | Purpose |
    |---|---|---|---|
    | `content_type` | **yes** | — | `"bookmark"`, `"note"`, or `"prompt"`. |
    | `title` | no | `null` | LLM context. |
    | `url` | no | `null` | LLM context (bookmarks). |
    | `description` | no | `null` | LLM context. |
    | `content_snippet` | no | `null` | Body text. 10,000 char max; 5,000 sent to LLM. |
    | `current_tags` | no | `[]` | Excluded from results (case-insensitive). |
    | `model` | no | `null` | BYOK model ID. Platform callers: ignored. |

    Supply at least one of `title` / `url` / `description` / `content_snippet`
    for useful suggestions — a request with only `content_type` will not be
    rejected but the LLM has nothing to summarize.

    ### Response

    `{"tags": [...]}` — up to 7 tags, deduped against `current_tags`,
    ordered by LLM confidence (preferred first).

    ### Server behavior (non-obvious)

    Before calling the LLM, the server loads the caller's top 100 most-used
    tags with usage counts and includes them in the prompt as
    preferred-vocabulary context. Suggestions therefore prefer existing tags
    over novel ones.

    **See the `ai` tag description at the top of this section** for
    authentication, rate limits, BYOK, and error handling.
    """
    llm_service = get_llm_service()
    config = _resolve_config_or_400(
        llm_service, AIUseCase.SUGGESTIONS, llm_api_key, data.model,
    )

    # Load user's tag vocabulary sorted by frequency (up to 100 with counts)
    # NOTE: Eval test data mirrors this structure — update evals/ai_suggestions/
    # config_suggest_tags.yaml if you change the number of entries or fields fetched.
    tag_counts = await get_user_tags_with_counts(db, current_user.id)
    tag_vocabulary = [
        TagVocabularyEntry(name=tc.name, count=tc.content_count)
        for tc in tag_counts[:100]
    ]

    start = time.monotonic()
    try:
        tags, cost = await suggest_tags(
            title=data.title,
            url=data.url,
            description=data.description,
            content_snippet=data.content_snippet,
            content_type=data.content_type,
            current_tags=data.current_tags,
            tag_vocabulary=tag_vocabulary,
            llm_service=llm_service,
            config=config,
        )
    except LLMResponseParseError as exc:
        await _handle_parse_error(exc, start=start, user_id=current_user.id, config=config)
    latency_ms = int((time.monotonic() - start) * 1000)

    await track_cost(
        user_id=current_user.id, use_case=AIUseCase.SUGGESTIONS,
        model=config.model, key_source=config.key_source,
        cost=cost, latency_ms=latency_ms,
    )

    return SuggestTagsResponse(tags=tags)


@router.post(
    "/suggest-metadata",
    response_model=SuggestMetadataResponse,
    responses=AI_SUGGESTION_RESPONSES,
    summary="Suggest name, title, and/or description for an item",
)
async def suggest_metadata_endpoint(
    data: SuggestMetadataRequest,
    current_user: User | CachedUser = Depends(get_current_user_ai),
    llm_api_key: str | None = Depends(get_llm_api_key),
    _rate_limit: None = Depends(apply_ai_rate_limit),
) -> SuggestMetadataResponse:
    """
    Generate a `name` (prompts only), `title`, or `description` for an item —
    using any supplied existing metadata as grounding context.

    ### Request fields

    | Field | Required | Default | Purpose |
    |---|---|---|---|
    | `fields` | no | `["title","description"]` | Which field(s) to **generate**. Non-empty. |
    | `url` | no | `null` | LLM context. |
    | `name` | no | `null` | Existing prompt name/slug. Prompts only. |
    | `title` | no | `null` | Existing title — see "context-vs-generate" below. |
    | `description` | no | `null` | Existing description — see "context-vs-generate" below. |
    | `content_snippet` | no | `null` | Body text. 10,000 char max; 5,000 sent to LLM. |
    | `model` | no | `null` | BYOK model ID. Platform callers: ignored. |

    ### Response

    `{"name": string | null, "title": string | null, "description": string | null}`
    — each field is populated if it appeared in the request `fields` array,
    otherwise `null`. Only the subset you asked to generate comes back.
    A generated `name` is always a valid slug (lowercase letters/numbers with
    hyphens). If the LLM returns an unusable name even after slugification,
    `name` is `null` despite being requested.

    ### Behavior: context vs. generate

    The `fields` array tells the server which fields to **generate**. Any
    `name` / `title` / `description` values you pass that are **not** in
    `fields` are used as **LLM grounding context** instead — they shape the
    output but are not regenerated and are not returned.

    Common patterns:

    - **Regenerate title + description from a URL.** Send
      `fields=["title", "description"]` and `url` (+ optionally
      `content_snippet`). Response has both fields.
    - **Suggest a prompt name from its title and description.** Send
      `fields=["name"]` with the existing `title` and `description`. Response
      has `name` populated; `title` and `description` are `null`.
    - **Regenerate only the description, keeping the title as context.**
      Send `fields=["description"]` with the existing `title` and
      `content_snippet`. The LLM uses the title to stay on-topic. The
      response has `title: null` and the new `description`. The frontend
      should display the original title unchanged.

    An empty `fields` array is rejected with 422.

    ### Item type and `name`

    This endpoint is entity-agnostic — it generates strings from whatever
    context you pass and does not check the caller's item type. The `name`
    field is intended for prompts (which have a slug-style identifier).
    Bookmarks and notes have no name field; passing `"name"` in `fields` for
    those entities will still return a plausible-looking slug, but it has no
    place to be stored and is not meaningful. Callers are expected to only
    request `"name"` when the target entity is a prompt.

    **See the `ai` tag description at the top of this section** for
    authentication, rate limits, BYOK, and error handling.
    """
    llm_service = get_llm_service()
    config = _resolve_config_or_400(
        llm_service, AIUseCase.SUGGESTIONS, llm_api_key, data.model,
    )

    start = time.monotonic()
    try:
        result, cost = await suggest_metadata(
            fields=data.fields,
            url=data.url,
            title=data.title,
            description=data.description,
            content_snippet=data.content_snippet,
            name=data.name,
            llm_service=llm_service,
            config=config,
        )
    except LLMResponseParseError as exc:
        await _handle_parse_error(exc, start=start, user_id=current_user.id, config=config)
    latency_ms = int((time.monotonic() - start) * 1000)

    await track_cost(
        user_id=current_user.id, use_case=AIUseCase.SUGGESTIONS,
        model=config.model, key_source=config.key_source,
        cost=cost, latency_ms=latency_ms,
    )

    return SuggestMetadataResponse(
        name=result.name,
        title=result.title,
        description=result.description,
    )


@router.post(
    "/suggest-relationships",
    response_model=SuggestRelationshipsResponse,
    responses=AI_SUGGESTION_RESPONSES,
    summary="Suggest related items for a source entity",
)
async def suggest_relationships_endpoint(
    data: SuggestRelationshipsRequest,
    current_user: User | CachedUser = Depends(get_current_user_ai),
    llm_api_key: str | None = Depends(get_llm_api_key),
    _rate_limit: None = Depends(apply_ai_rate_limit),
    db: AsyncSession = Depends(get_async_session),
) -> SuggestRelationshipsResponse:
    """
    Find items in the caller's library that are conceptually related to the
    source, using a two-phase server-side search + LLM judgment pipeline.

    ### Request fields

    | Field | Required | Default | Purpose |
    |---|---|---|---|
    | `title` | at least one | `null` | Candidate search + LLM context. |
    | `description` | at least one | `null` | Candidate search + LLM context. |
    | `current_tags` | at least one | `[]` | Candidate search (tag match). |
    | `url` | no | `null` | LLM context only (not searched). |
    | `content_snippet` | no | `null` | LLM context. 10,000 char max; 5,000 sent to LLM. |
    | `source_id` | no | `null` | Source item ID; excluded from pool — see below. |
    | `existing_relationship_ids` | no | `[]` | Already-linked IDs; excluded from pool. |
    | `model` | no | `null` | BYOK model ID. Platform callers: ignored. |

    The "at least one" constraint: at least one of `title`, `description`,
    or `current_tags` must be non-empty. If all three are empty the handler
    returns `{"candidates": []}` without calling the LLM.

    ### Response

    `{"candidates": [{entity_id, entity_type, title}, ...]}` — the LLM's
    filtered subset of the candidate pool. May be empty.

    ### Server behavior

    1. **Candidate search** (no LLM): FTS over the caller's
       bookmarks/notes/prompts using `title` + `description`, plus a tag
       match using `current_tags`. Results deduplicated, capped at 10.
    2. **LLM filtering**: the candidates + source metadata are sent to the
       LLM, which returns the subset it judges actually relevant.

    ### Why pass `source_id` and `existing_relationship_ids`

    Both are applied during **candidate search**, not as a post-filter on
    the response. Passing them means the 10-candidate budget is spent on
    genuinely-new, relevant items instead of being wasted on the source
    itself or already-linked items.

    - Omit `source_id` and the source may match its own tags or title and
      consume one of the 10 slots.
    - Omit `existing_relationship_ids` and a highly-relevant already-linked
      item may consume a slot (and then you'd just re-filter it client-side).

    Filtering client-side after the response doesn't recover wasted slots.

    ### Empty response cases

    Rate-limit quota is always consumed regardless (the dependency runs
    before the handler body). Three different conditions produce
    `{"candidates": []}`:

    - **All of `title`, `description`, `current_tags` are empty** — no LLM
      call, no provider cost. Handler short-circuits before candidate
      search.
    - **Candidate search found no matches** — no LLM call, no provider cost.
    - **LLM ran but judged all candidates irrelevant** — LLM call was made,
      provider cost WAS charged, latency WAS paid. Indistinguishable from
      the other two cases in the response body; distinguishable only by
      server-side `ai_usage` records. Treat empty responses as normal;
      don't retry them expecting a non-empty answer.

    **See the `ai` tag description at the top of this section** for
    authentication, rate limits, BYOK, and error handling.
    """
    # Validate the BYOK model up front — before any early-return paths — so
    # the `400 unsupported model` contract is consistent regardless of
    # whether the search finds candidates. Previously the check only ran
    # when the LLM was actually called, letting an invalid `model` silently
    # succeed with `{"candidates": []}` if search came up empty.
    llm_service = get_llm_service()
    config = _resolve_config_or_400(
        llm_service, AIUseCase.SUGGESTIONS, llm_api_key, data.model,
    )

    if not data.title and not data.description and not data.current_tags:
        return SuggestRelationshipsResponse(candidates=[])

    candidates = await _search_relationship_candidates(db, current_user.id, data)

    if not candidates:
        return SuggestRelationshipsResponse(candidates=[])

    start = time.monotonic()
    try:
        filtered, cost = await suggest_relationships(
            title=data.title,
            url=data.url,
            description=data.description,
            content_snippet=data.content_snippet,
            candidates=candidates,
            llm_service=llm_service,
            config=config,
        )
    except LLMResponseParseError as exc:
        await _handle_parse_error(exc, start=start, user_id=current_user.id, config=config)
    latency_ms = int((time.monotonic() - start) * 1000)

    await track_cost(
        user_id=current_user.id, use_case=AIUseCase.SUGGESTIONS,
        model=config.model, key_source=config.key_source,
        cost=cost, latency_ms=latency_ms,
    )

    return SuggestRelationshipsResponse(candidates=filtered)


@router.post(
    "/suggest-prompt-arguments",
    response_model=SuggestPromptArgumentsResponse,
    responses=AI_SUGGESTION_RESPONSES,
    summary="Suggest all new prompt-template arguments from placeholders",
)
async def suggest_prompt_arguments_endpoint(
    data: SuggestPromptArgumentsRequest,
    current_user: User | CachedUser = Depends(get_current_user_ai),
    llm_api_key: str | None = Depends(get_llm_api_key),
    _rate_limit: None = Depends(apply_ai_rate_limit),
) -> SuggestPromptArgumentsResponse:
    """
    Generate `{name, description, required}` entries for every
    `{{ placeholder }}` in a Jinja2 prompt template that is not already
    declared in `arguments`.

    ### Request fields

    | Field | Required | Default | Purpose |
    |---|---|---|---|
    | `prompt_content` | **yes** | — | Jinja2 template, 50 KB max. Whitespace-stripped. |
    | `arguments` | no | `[]` | Existing `{name, description}` — names skip extraction. |
    | `model` | no | `null` | BYOK model ID. Platform callers: ignored. |

    ### Response

    `{"arguments": [{name, description, required}, ...]}` — one entry per
    new placeholder detected in `prompt_content`. Returned in the order
    the placeholders first appear in the template.

    ### Empty-response cases

    Rate-limit quota is always consumed (the dependency runs before the
    handler), so `{"arguments": []}` is not a free response. There are
    two distinct ways to get it:

    **No LLM call, no provider cost.** The server short-circuits before
    talking to the LLM:

    - `prompt_content` contains no `{{ }}` placeholders at all.
    - Every extracted placeholder is already declared in `arguments` by
      name (case-insensitive).

    **LLM call made, provider cost charged.** The LLM ran but produced
    no usable output:

    - Every generated argument name failed identifier validation
      (`lowercase_with_underscores`, must start with a letter). Rare —
      usually indicates a very weak model or a pathological template.

    ### Related

    Use `POST /ai/suggest-prompt-argument-fields` to refine the `name` or
    `description` (or both) of a single specific argument row.

    **See the `ai` tag description at the top of this section** for
    authentication, rate limits, BYOK, and error handling.
    """
    llm_service = get_llm_service()
    config = _resolve_config_or_400(
        llm_service, AIUseCase.SUGGESTIONS, llm_api_key, data.model,
    )

    start = time.monotonic()
    try:
        valid_args, cost = await suggest_prompt_arguments(
            prompt_content=data.prompt_content,
            arguments=data.arguments,
            llm_service=llm_service,
            config=config,
        )
    except LLMResponseParseError as exc:
        await _handle_parse_error(exc, start=start, user_id=current_user.id, config=config)
    latency_ms = int((time.monotonic() - start) * 1000)

    # `suggest_prompt_arguments` returns `cost=None` on its no-LLM-call
    # short-circuit paths (no placeholders in the template; every
    # placeholder already declared). Skip cost tracking in that case —
    # otherwise `track_cost` would emit an `llm_call` log and increment
    # the Redis call counter for a call that never happened. If a provider
    # ever returns `cost=None` after a real LLM call (rare for current
    # providers), that observability log is missed; revisit by returning
    # an explicit `llm_called` flag from the service if this becomes a gap.
    if cost is not None:
        await track_cost(
            user_id=current_user.id, use_case=AIUseCase.SUGGESTIONS,
            model=config.model, key_source=config.key_source,
            cost=cost, latency_ms=latency_ms,
        )

    return SuggestPromptArgumentsResponse(arguments=valid_args)


@router.post(
    "/suggest-prompt-argument-fields",
    response_model=SuggestPromptArgumentsResponse,
    responses=SUGGEST_PROMPT_ARGUMENT_FIELDS_RESPONSES,
    summary="Refine the name and/or description of one prompt-template argument",
)
async def suggest_prompt_argument_fields_endpoint(
    data: SuggestPromptArgumentFieldsRequest,
    current_user: User | CachedUser = Depends(get_current_user_ai),
    llm_api_key: str | None = Depends(get_llm_api_key),
    _rate_limit: None = Depends(apply_ai_rate_limit),
) -> SuggestPromptArgumentsResponse:
    """
    Refine one specific argument row by generating one or both of its
    fields. `target_fields` makes caller intent explicit — the server
    does not infer which field to regenerate from which fields are blank.

    ### Request fields

    | Field | Required | Default | Purpose |
    |---|---|---|---|
    | `arguments` | **yes** | — | Non-empty list. Entries may have `null` fields. |
    | `target_index` | **yes** | — | Row index to refine. Must be within bounds. |
    | `target_fields` | **yes** | — | 1-2 unique from `{"name","description"}`. Canonicalized. |
    | `prompt_content` | conditional | `null` | Grounding. Required for two-field; `""` → `null`. |
    | `model` | no | `null` | BYOK model ID. Platform callers: ignored. |

    ### Response

    `{"arguments": [{name, description, required}, ...]}` — a
    single-element list containing the refined entry.

    Rate-limit quota is always consumed (the dependency runs before the
    handler), so `{"arguments": []}` is not a free response. There are
    two distinct ways to get it:

    **No LLM call, no provider cost.** Only the two-field path can
    short-circuit here:

    - `target_fields=["name", "description"]` but every placeholder in
      the template is already claimed by another row — the LLM has no
      unclaimed name to assign. Single-field paths always call the LLM.

    **LLM call made, provider cost charged.** The LLM ran but its
    response was rejected:

    - Generated name failed identifier validation
      (`lowercase_with_underscores`, must start with a letter).
    - Two-field path: the LLM returned a name that collides with
      another row's existing name despite the pre-filter (defensive
      backstop against LLMs ignoring the unclaimed-only prompt).

    ### Grounding rules

    At least one of the following must hold for each requested field
    (enforced at schema boundary; 422 on failure):

    - `target_fields: ["name"]` — the target row's `description` is
      non-empty, OR `prompt_content` is non-empty.
    - `target_fields: ["description"]` — the target row's `name` is
      non-empty, OR `prompt_content` is non-empty.
    - `target_fields: ["name", "description"]` — `prompt_content` is
      non-empty. (The two-field path regenerates the whole row from
      template context.)

    ### Overwrite semantics (explicit opt-in)

    Requesting a field that is already populated on the target row does
    **not** short-circuit. The LLM is called and the response overwrites
    the existing value(s). There is no silent inference — callers decide
    which fields to regenerate.

    ### Related

    Use `POST /ai/suggest-prompt-arguments` to propose entries for every
    new placeholder in a template.

    **See the `ai` tag description at the top of this section** for
    authentication, rate limits, BYOK, and error handling.
    """
    llm_service = get_llm_service()
    config = _resolve_config_or_400(
        llm_service, AIUseCase.SUGGESTIONS, llm_api_key, data.model,
    )

    start = time.monotonic()
    try:
        valid_args, cost = await suggest_prompt_argument_fields(
            prompt_content=data.prompt_content,
            arguments=data.arguments,
            target_index=data.target_index,
            target_fields=data.target_fields,
            llm_service=llm_service,
            config=config,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LLMResponseParseError as exc:
        await _handle_parse_error(exc, start=start, user_id=current_user.id, config=config)
    latency_ms = int((time.monotonic() - start) * 1000)

    # `suggest_prompt_argument_fields` returns `cost=None` on the two-field
    # all-claimed short-circuit (every template placeholder already owned
    # by another row → no LLM call). Same contract as the plural handler
    # above: skip cost tracking when cost is None to avoid phantom
    # `llm_call` logs. See the plural handler for the edge-case caveat.
    if cost is not None:
        await track_cost(
            user_id=current_user.id, use_case=AIUseCase.SUGGESTIONS,
            model=config.model, key_source=config.key_source,
            cost=cost, latency_ms=latency_ms,
        )

    return SuggestPromptArgumentsResponse(arguments=valid_args)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _handle_parse_error(
    exc: LLMResponseParseError,
    *,
    start: float,
    user_id: UUID,
    config: LLMConfig,
) -> NoReturn:
    """Track cost from failed LLM parse and raise `LLMParseFailedError` → 502."""
    latency_ms = int((time.monotonic() - start) * 1000)
    try:
        await track_cost(
            user_id=user_id, use_case=AIUseCase.SUGGESTIONS,
            model=config.model, key_source=config.key_source,
            cost=exc.cost, latency_ms=latency_ms,
        )
    except Exception:
        logger.warning("track_cost_failed_on_parse_error", exc_info=True)
    raise LLMParseFailedError(
        "LLM returned an invalid response. Try again or use a different model.",
    ) from exc


async def _search_relationship_candidates(
    db: AsyncSession,
    user_id: int,
    data: SuggestRelationshipsRequest,
) -> list[RelationshipCandidateContext]:
    """Search for relationship candidates by title+description and tags, deduped."""
    # Search by title+description (relevance-ranked) then tags (recency-ranked).
    search_results: list[tuple] = []
    query_parts = [p for p in (data.title, data.description) if p]
    if query_parts:
        query = " ".join(query_parts)
        search_results.append(await search_all_content(
            db=db, user_id=user_id, query=query,
            sort_by="relevance", limit=10,
        ))
    if data.current_tags:
        search_results.append(await search_all_content(
            db=db, user_id=user_id, tags=data.current_tags,
            tag_match="any", sort_by="updated_at", limit=10,
        ))

    # Dedup by ID, title results first (highest signal)
    exclude_ids = set(data.existing_relationship_ids)
    if data.source_id:
        exclude_ids.add(data.source_id)
    seen_ids: set[str] = set()
    candidates: list[RelationshipCandidateContext] = []
    for items, _total in search_results:
        for item in items:
            item_id = str(item.id)
            if item_id in exclude_ids or item_id in seen_ids:
                continue
            seen_ids.add(item_id)
            candidates.append(RelationshipCandidateContext(
                entity_id=item_id,
                entity_type=item.type,
                title=item.title or "",
                description=item.description or "",
                content_preview=item.content_preview or "",
            ))
            if len(candidates) >= 10:
                break
        if len(candidates) >= 10:
            break
    return candidates


