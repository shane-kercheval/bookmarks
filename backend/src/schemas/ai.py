"""Request/response schemas for AI endpoints."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# Maximum length (in characters) accepted from clients for `content_snippet`.
# Enforced at the API boundary via the Pydantic `max_length` validator
# applied to the field below. Oversized payloads get 422.
#
# `CONTENT_SNIPPET_LLM_WINDOW_CHARS` is the window of characters actually
# used by the LLM prompt builders (see `services/llm_prompts.py`). Keeping
# the window smaller than the max ceiling bounds provider cost without
# rejecting larger client payloads outright. The gap between the two is
# load-bearing — callers can send up to the max, but must understand only
# the first `CONTENT_SNIPPET_LLM_WINDOW_CHARS` are seen by the LLM.
#
# Both values are referenced from `services/llm_prompts.py` to prevent drift.
CONTENT_SNIPPET_MAX_CHARS = 10_000
CONTENT_SNIPPET_LLM_WINDOW_CHARS = 5000


# ---------------------------------------------------------------------------
# Shared error response models
# ---------------------------------------------------------------------------


class AIErrorResponse(BaseModel):
    """
    Generic error envelope used by most AI endpoint failure paths.

    **Applies to**: 400, 401, 403, 422 (only when `error_code=llm_auth_failed`
    — BYOK provider-auth failure), 429, 502, 503, 504.

    **Does NOT apply to**:

    - `422 Unprocessable Entity` from Pydantic/FastAPI **request validation**
      — those use the standard FastAPI validation error shape:
      `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}`. The 422
      response panel for each endpoint describes both shapes.
    """

    detail: str = Field(
        ...,
        description="Human-readable error message safe to surface to end users.",
    )
    error_code: str | None = Field(
        None,
        description=(
            "Machine-readable error identifier when a typed error is raised. "
            "Values that may appear on AI endpoints: `llm_auth_failed` (422, "
            "BYOK key rejected by provider), `llm_rate_limited` (429, upstream "
            "provider throttled), `llm_timeout` (504), `llm_bad_request` (400, "
            "LLM provider rejected the shape), `llm_connection_error` (502, "
            "connection to provider failed), `llm_parse_failed` (502, LLM "
            "returned an unparseable structured response), `llm_unavailable` "
            "(503, unclassified provider failure). Absent for un-typed errors "
            "(e.g. bare Tiddly `429` rate-limit, `401` / `403` auth failures)."
        ),
    )


class TagVocabularyEntry(BaseModel):
    """A tag from the user's vocabulary with usage count."""

    name: str
    count: int


class RelationshipCandidateContext(BaseModel):
    """
    A candidate item passed to the relationship suggestion service.

    Distinct from RelationshipCandidate (the public API response schema)
    — this includes description and content_preview for prompt building.
    """

    entity_id: str
    entity_type: str
    title: str
    description: str
    content_preview: str


# ---------------------------------------------------------------------------
# Health / Models (config endpoints — no AI rate limit consumed)
# ---------------------------------------------------------------------------


class AIHealthResponse(BaseModel):
    """Availability + remaining AI quota for the caller."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "available": True,
                    "byok": False,
                    "remaining_per_minute": 29,
                    "limit_per_minute": 30,
                    "remaining_per_day": 497,
                    "limit_per_day": 500,
                    "resets_at": "2026-04-18T10:23:45Z",
                },
                {
                    "available": True,
                    "byok": True,
                    "remaining_per_minute": 118,
                    "limit_per_minute": 120,
                    "remaining_per_day": 1998,
                    "limit_per_day": 2000,
                    "resets_at": "2026-04-18T10:23:45Z",
                },
            ],
        },
    )

    available: bool = Field(
        ...,
        description=(
            "Whether AI features are available **for this specific request**. "
            "True when BOTH the per-minute AND daily platform limits are "
            "non-zero for the caller's tier, OR the caller sent "
            "`X-LLM-Api-Key` AND both BYOK windows are non-zero. A "
            "BYOK-only tier (platform=0, BYOK>0) therefore returns `false` "
            "when called *without* the BYOK header. Both windows must be "
            "non-zero — a tier with daily>0 but per-minute=0 (or vice versa) "
            "would always 429, so we surface that as `available=false`."
        ),
    )
    byok: bool = Field(
        ...,
        description=(
            "Whether the current request carried an `X-LLM-Api-Key` header. "
            "Determines which rate-limit bucket the remaining/limit values "
            "reflect (BYOK vs platform)."
        ),
    )
    remaining_per_minute: int = Field(
        ...,
        description=(
            "Approximate remaining calls in the current 60-second sliding "
            "window for this bucket. Useful for client-side pacing during "
            "batch operations or to show a rate-limit tooltip. Zero when the "
            "tier has no quota for this bucket."
        ),
    )
    limit_per_minute: int = Field(
        ...,
        description="Per-minute limit for this bucket and tier.",
    )
    remaining_per_day: int = Field(
        ...,
        description=(
            "Remaining calls in the current 24-hour window for this bucket. "
            "The window is per-user, not a shared UTC-midnight reset: Redis "
            "fixed-window counter with an 86400-second TTL set on the first "
            "request in a window. See `resets_at` for the exact expiry "
            "timestamp."
        ),
    )
    limit_per_day: int = Field(
        ...,
        description="Per-user 24-hour limit for this bucket and tier.",
    )
    resets_at: datetime | None = Field(
        None,
        description=(
            "ISO 8601 UTC timestamp (e.g. `2026-04-18T10:23:45Z`) when this "
            "bucket's 24-hour counter expires. After that moment, the next "
            "request starts a fresh window. `null` when the counter key "
            "doesn't exist — the caller hasn't made any requests yet in the "
            "current window — or when Redis is unavailable. Clients are free "
            "to format this timestamp in the user's locale for display."
        ),
    )


class AIModelEntry(BaseModel):
    """One supported model with pricing."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "openai/gpt-5.4-nano",
                    "provider": "openai",
                    "tier": "budget",
                    "input_cost_per_million": 0.05,
                    "output_cost_per_million": 0.40,
                },
            ],
        },
    )

    id: str = Field(
        ...,
        description="Provider-prefixed model ID to pass as `model` on suggestion requests.",
    )
    provider: Literal["openai", "google", "anthropic"] = Field(
        ...,
        description="Upstream LLM provider that hosts the model.",
    )
    tier: Literal["budget", "balanced", "flagship"] = Field(
        ...,
        description="Relative quality/price tier within the provider.",
    )
    input_cost_per_million: float | None = Field(
        None,
        description=(
            "USD per million input tokens, if known. Absent only when LiteLLM "
            "doesn't have a cost entry."
        ),
    )
    output_cost_per_million: float | None = Field(
        None,
        description="USD per million output tokens, if known.",
    )


# Keys of `AIModelsResponse.defaults`. Mirrors `services.llm_service.AIUseCase`
# — if the enum grows, add the new key here too. Drift is guarded by
# `tests/schemas/test_ai_schemas.py` (test__ai_use_case_key__matches_ai_use_case_enum_values)
# which fails if the two sets don't match.
AIUseCaseKey = Literal["suggestions", "transform", "auto_complete", "chat"]


class AIModelsResponse(BaseModel):
    """Curated list of supported models and per-use-case defaults."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "models": [
                        {
                            "id": "openai/gpt-5.4-nano",
                            "provider": "openai",
                            "tier": "budget",
                            "input_cost_per_million": 0.05,
                            "output_cost_per_million": 0.40,
                        },
                    ],
                    "defaults": {
                        "suggestions": "openai/gpt-5.4-nano",
                        "transform": "gemini/gemini-flash-lite-latest",
                        "auto_complete": "gemini/gemini-flash-lite-latest",
                        "chat": "openai/gpt-5.4-mini",
                    },
                },
            ],
        },
    )

    models: list[AIModelEntry] = Field(
        ...,
        description="All supported models (GA only, no preview/experimental).",
    )
    defaults: dict[AIUseCaseKey, str] = Field(
        ...,
        description=(
            "Per-use-case default model ID. Keys correspond to the `AIUseCase` "
            "enum. Platform callers (no BYOK key) are always routed to the "
            "default for the endpoint's use case regardless of the `model` "
            "field they send."
        ),
    )


# ---------------------------------------------------------------------------
# Validate Key
# ---------------------------------------------------------------------------


class ValidateKeyResponse(BaseModel):
    """Result of probing a BYOK key against the selected provider."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"valid": True},
                {"valid": False, "error": "API key rejected by provider"},
            ],
        },
    )

    valid: bool = Field(..., description="Whether the provider accepted the key.")
    error: Literal["API key rejected by provider"] | None = Field(
        None,
        description=(
            "Reason string when `valid` is false. Currently only one value "
            "ever appears; additional values in the future would be a "
            "documented schema addition. Never echoes the key itself."
        ),
    )


class ValidateKeyRequest(BaseModel):
    """Request for key validation. Model determines which provider to test against."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"model": "openai/gpt-5.4-nano"},
                {"model": "anthropic/claude-haiku-4-5"},
            ],
        },
    )

    model: str | None = Field(
        None,
        description=(
            "Optional supported model ID used to pick the provider to validate "
            "the supplied `X-LLM-Api-Key` against. If omitted, the server "
            "validates using a default model. Call `GET /ai/models` for the "
            "supported list."
        ),
    )


# ---------------------------------------------------------------------------
# Suggest Tags
# ---------------------------------------------------------------------------


ContentTypeLiteral = Literal["bookmark", "note", "prompt"]


class SuggestTagsRequest(BaseModel):
    """Request body for `POST /ai/suggest-tags`."""

    # Primary example: every request field populated with a realistic value,
    # so a reader looking at Swagger's "Example Value" immediately sees the
    # full shape. `model` is included so BYOK users see that field exists.
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "model": "openai/gpt-5.4-mini",
                    "content_type": "bookmark",
                    "title": "How async/await works under the hood",
                    "url": "https://example.com/posts/async-internals",
                    "description": "A deep dive into Python's event loop.",
                    "content_snippet": "The event loop sits at the heart of asyncio...",
                    "current_tags": ["python"],
                },
            ],
        },
    )

    model: str | None = Field(
        None,
        description=(
            "Optional supported model ID (e.g. `openai/gpt-5.4-mini`). Only "
            "honored when a BYOK key is supplied via `X-LLM-Api-Key`; platform "
            "callers are silently locked to the use-case default. Call "
            "`GET /ai/models` for the supported list."
        ),
    )
    content_type: ContentTypeLiteral = Field(
        ...,
        description="Entity type being tagged. Determines the prompt template used.",
    )
    title: str | None = Field(
        None, max_length=500,
        description="Entity title used as LLM context.",
    )
    url: str | None = Field(
        None, max_length=2048,
        description="Bookmark URL used as LLM context. Typically omitted for notes/prompts.",
    )
    description: str | None = Field(
        None, max_length=2000,
        description="Entity description used as LLM context.",
    )
    content_snippet: str | None = Field(
        None, max_length=CONTENT_SNIPPET_MAX_CHARS,
        description=(
            "Body text passed as LLM context. Accepts up to 10,000 "
            "characters, but only the first 5,000 are sent to the LLM — "
            "sending more is wasted bandwidth. Send the opening / most "
            "representative portion (callers are responsible for "
            "truncation). Oversized payloads are rejected with 422. "
            "See `CONTENT_SNIPPET_MAX_CHARS` and "
            "`CONTENT_SNIPPET_LLM_WINDOW_CHARS` in `schemas/ai.py`."
        ),
    )
    current_tags: list[str] = Field(
        default_factory=list,
        description="Tags already applied to the entity. Excluded from the suggestion set.",
    )


class SuggestTagsResponse(BaseModel):
    """Response with suggested tags."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"tags": ["async", "python", "event-loop", "concurrency"]}],
        },
    )

    tags: list[str] = Field(
        ...,
        description=(
            "Suggested tags, already filtered to exclude `current_tags`. Order "
            "is LLM-provided and loosely represents confidence — preferred "
            "tags first."
        ),
    )


# ---------------------------------------------------------------------------
# Suggest Metadata
# ---------------------------------------------------------------------------


class SuggestMetadataRequest(BaseModel):
    """Request body for `POST /ai/suggest-metadata`."""

    # Primary example: every request field populated with a realistic value.
    # This is the "full shape" reference — the fact that `title` and
    # `description` appear here makes the endpoint's context-vs-generate
    # pattern visible (see endpoint docstring).
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "model": "openai/gpt-5.4-mini",
                    "fields": ["title", "description"],
                    "url": "https://example.com/posts/async-internals",
                    "title": "Async internals",
                    "description": "Deep dive into Python's event loop.",
                    "content_snippet": "The event loop sits at the heart of asyncio...",
                },
                {
                    "model": "openai/gpt-5.4-mini",
                    "fields": ["name"],
                    "title": "Weekly status update",
                    "description": "Template for our team's weekly status report.",
                    "content_snippet": "## This week\n- ...\n\n## Next week\n- ...",
                },
            ],
        },
    )

    model: str | None = Field(
        None,
        description=(
            "Optional supported model ID. Only honored when a BYOK key is "
            "supplied via `X-LLM-Api-Key`; platform callers are silently "
            "locked to the use-case default. Call `GET /ai/models`."
        ),
    )
    fields: list[Literal["name", "title", "description"]] = Field(
        default_factory=lambda: ["title", "description"],
        min_length=1,
        description=(
            "Non-empty list of field names to generate; each element must be "
            "`\"name\"`, `\"title\"`, or `\"description\"`. Fields not listed "
            "here are used as LLM context when supplied but are not returned "
            "in the response. `\"name\"` is only meaningful for prompts; "
            "bookmarks and notes don't have a name field."
        ),
    )
    url: str | None = Field(
        None, max_length=2048,
        description="Bookmark URL used as LLM context.",
    )
    name: str | None = Field(
        None, max_length=255,
        description=(
            "Existing prompt name/slug used as LLM context. Not returned "
            "unless `name` is included in `fields`. Only meaningful for "
            "prompts; bookmarks and notes don't have a name field."
        ),
    )
    title: str | None = Field(
        None, max_length=500,
        description=(
            "Existing title used as LLM context. Not returned unless `title` "
            "is included in `fields`."
        ),
    )
    description: str | None = Field(
        None, max_length=2000,
        description=(
            "Existing description used as LLM context. Not returned unless "
            "`description` is included in `fields`."
        ),
    )
    content_snippet: str | None = Field(
        None, max_length=CONTENT_SNIPPET_MAX_CHARS,
        description=(
            "Body text passed as LLM context. Accepts up to 10,000 "
            "characters, but only the first 5,000 are sent to the LLM. "
            "Oversized payloads are rejected with 422."
        ),
    )


class SuggestMetadataResponse(BaseModel):
    """Response with suggested name, title, and/or description."""

    # Kept a single non-null example; the `title: null` case is documented
    # in the `title` field description instead. FastAPI's OpenAPI
    # post-processor strips `None` values from schema examples, so a
    # dual-example array with `"title": null` would render identically to a
    # single-example array anyway.
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "async-await-internals",
                    "title": "Async/await internals in Python",
                    "description": "A walkthrough of how the event loop schedules coroutines.",
                },
            ],
        },
    )

    name: str | None = Field(
        None,
        description=(
            "Generated prompt name/slug (lowercase letters/numbers with "
            "hyphens). `null` unless `name` was in the request `fields`, or "
            "if the LLM produced no usable value after slugification."
        ),
    )
    title: str | None = Field(
        None,
        description="Generated title. `null` unless `title` was in the request `fields`.",
    )
    description: str | None = Field(
        None,
        description=(
            "Generated description. `null` unless `description` was in the "
            "request `fields`."
        ),
    )


# ---------------------------------------------------------------------------
# Suggest Relationships
# ---------------------------------------------------------------------------


class SuggestRelationshipsRequest(BaseModel):
    """Request body for `POST /ai/suggest-relationships`."""

    # Primary example: every request field populated. `existing_relationship_ids`
    # uses a sample UUID so readers see the list isn't just empty-by-convention.
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "model": "openai/gpt-5.4-mini",
                    "source_id": "01920000-0000-7000-8000-000000000001",
                    "title": "How async/await works under the hood",
                    "url": "https://example.com/posts/async-internals",
                    "description": "A deep dive into Python's event loop.",
                    "content_snippet": "The event loop sits at the heart of asyncio...",
                    "current_tags": ["python", "async"],
                    "existing_relationship_ids": [
                        "01920000-0000-7000-8000-0000000000aa",
                    ],
                },
            ],
        },
    )

    model: str | None = Field(
        None,
        description=(
            "Optional supported model ID. Only honored with BYOK. Call "
            "`GET /ai/models` for the supported list."
        ),
    )
    source_id: str | None = Field(
        None,
        description=(
            "ID of the item being related (the source). If supplied, it is "
            "excluded from candidate results so the item never suggests "
            "itself as a relation."
        ),
    )
    title: str | None = Field(
        None, max_length=500,
        description=(
            "Title of the source item. Used for both candidate search and "
            "LLM grounding."
        ),
    )
    url: str | None = Field(
        None, max_length=2048,
        description="URL of the source item. Used as LLM context.",
    )
    description: str | None = Field(
        None, max_length=2000,
        description=(
            "Description of the source item. Used for both candidate search "
            "and LLM grounding."
        ),
    )
    content_snippet: str | None = Field(
        None, max_length=CONTENT_SNIPPET_MAX_CHARS,
        description=(
            "Body text passed as LLM context (not used in candidate search). "
            "Accepts up to 10,000 characters, but only the first 5,000 are "
            "sent to the LLM."
        ),
    )
    current_tags: list[str] = Field(
        default_factory=list,
        description=(
            "Tags on the source item. Used to find tag-based candidates in "
            "addition to the title/description FTS search."
        ),
    )
    existing_relationship_ids: list[str] = Field(
        default_factory=list,
        description=(
            "IDs of items already linked to the source. Excluded from "
            "candidate results so the response only contains *new* potential "
            "relationships."
        ),
    )


class RelationshipCandidate(BaseModel):
    """A candidate item for a relationship suggestion."""

    entity_id: str = Field(..., description="UUID of the candidate item.")
    entity_type: ContentTypeLiteral = Field(..., description="Type of the candidate item.")
    title: str = Field(..., description="Candidate's title, for display.")


class SuggestRelationshipsResponse(BaseModel):
    """Response with relationship candidates."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "candidates": [
                        {
                            "entity_id": "01920000-0000-7000-8000-000000000001",
                            "entity_type": "bookmark",
                            "title": "Python asyncio documentation",
                        },
                    ],
                },
                {"candidates": []},
            ],
        },
    )

    candidates: list[RelationshipCandidate] = Field(
        ...,
        description=(
            "LLM-filtered relevant candidates. Empty list if no candidates "
            "were found, or if the source item had no "
            "`title`/`description`/`current_tags` to match against (in which "
            "case no LLM call is made; see the request model for the full "
            "list of LLM-skip cases)."
        ),
    )


# ---------------------------------------------------------------------------
# Suggest Prompt Arguments / Suggest Prompt Argument Fields
# ---------------------------------------------------------------------------


class ArgumentInput(BaseModel):
    """
    An existing argument provided for context.

    Whitespace handling: `name` and `description` are normalized at the
    schema boundary via a `mode="before"` validator — leading/trailing
    whitespace is stripped, and whitespace-only strings become `None`.
    Downstream consumers (prompt builder, LLM call, logs, tests, evals)
    never see leading/trailing whitespace or whitespace-only strings.
    """

    name: str | None = Field(
        None, max_length=200,
        description="Argument identifier as used in the prompt template (e.g. `user_query`).",
    )
    description: str | None = Field(
        None, max_length=500,
        description="Human-readable description of what the argument represents.",
    )

    @field_validator("name", "description", mode="before")
    @classmethod
    def _normalize_whitespace(cls, v: object) -> object:
        if not isinstance(v, str):
            return v
        stripped = v.strip()
        return stripped or None


class SuggestPromptArgumentsRequest(BaseModel):
    """Request body for `POST /ai/suggest-prompt-arguments` (generate-all)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "model": "openai/gpt-5.4-mini",
                    "prompt_content": (
                        "Summarize {{ document }} in {{ num_sentences }} sentences."
                    ),
                    "arguments": [
                        {
                            "name": "document",
                            "description": "The source text to summarize.",
                        },
                    ],
                },
            ],
        },
    )

    model: str | None = Field(
        None,
        description=(
            "Optional supported model ID. Only honored with BYOK. Call "
            "`GET /ai/models` for the supported list."
        ),
    )
    prompt_content: str = Field(
        ..., min_length=1, max_length=50_000,
        description=(
            "The prompt template text (Jinja2). Required; up to 50 KB. "
            "Leading/trailing whitespace is stripped before length validation."
        ),
    )
    arguments: list[ArgumentInput] = Field(
        default_factory=list,
        description=(
            "Existing `{name, description}` entries. Names are excluded from "
            "placeholder extraction (case-insensitive) so only new "
            "placeholders are proposed."
        ),
    )

    @field_validator("prompt_content", mode="before")
    @classmethod
    def _strip_prompt_content(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v


class SuggestPromptArgumentFieldsRequest(BaseModel):
    """
    Request body for `POST /ai/suggest-prompt-argument-fields` (refine one row).

    `target_fields` is a 1- or 2-element list drawn from `{"name", "description"}`.
    The grounding-signal rules (enforced by a `model_validator`) require the LLM
    has at least one signal for each requested field:

    - `["name"]`: `arguments[target_index].description` or `prompt_content` non-empty.
    - `["description"]`: `arguments[target_index].name` or `prompt_content` non-empty.
    - `["name", "description"]`: `prompt_content` non-empty.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "model": "openai/gpt-5.4-mini",
                    "prompt_content": (
                        "Summarize {{ document }} in {{ num_sentences }} sentences."
                    ),
                    "arguments": [
                        {
                            "name": "document",
                            "description": "The source text to summarize.",
                        },
                        {
                            "name": None,
                            "description": "How many sentences the summary should be.",
                        },
                    ],
                    "target_index": 1,
                    "target_fields": ["name"],
                },
            ],
        },
    )

    model: str | None = Field(
        None,
        description=(
            "Optional supported model ID. Only honored with BYOK. Call "
            "`GET /ai/models` for the supported list."
        ),
    )
    prompt_content: str | None = Field(
        None, min_length=1, max_length=50_000,
        description=(
            "Optional Jinja2 template used as grounding context. `null` is "
            "allowed, but the empty string (or whitespace-only after "
            "stripping) is rejected as 422."
        ),
    )
    arguments: list[ArgumentInput] = Field(
        ...,
        description=(
            "Existing `{name, description}` entries. The list must be "
            "non-empty (caller must provide the entry being refined at "
            "`target_index`). Individual entries may have `null` / empty "
            "`name` and/or `description` — the grounding-signal rule "
            "governs which combinations are accepted, not a per-field "
            "non-null requirement."
        ),
    )
    target_index: int = Field(
        ..., ge=0,
        description=(
            "Index into `arguments` identifying the row to refine. "
            "Must be within bounds (out-of-range returns 400)."
        ),
    )
    target_fields: list[Literal["name", "description"]] = Field(
        ...,
        description=(
            "Which fields on the target row to generate. Non-empty, 1 or 2 "
            "unique elements from `{\"name\", \"description\"}`. Server "
            "canonicalizes to the fixed order `[\"name\", \"description\"]`."
        ),
    )

    @field_validator("prompt_content", mode="before")
    @classmethod
    def _normalize_prompt_content(cls, v: object) -> object:
        if not isinstance(v, str):
            return v
        stripped = v.strip()
        return stripped or None

    @field_validator("arguments")
    @classmethod
    def _arguments_not_empty(cls, v: list[ArgumentInput]) -> list[ArgumentInput]:
        if not v:
            raise ValueError("arguments must contain at least one entry")
        return v

    @field_validator("target_fields")
    @classmethod
    def _target_fields_valid(
        cls, v: list[Literal["name", "description"]],
    ) -> list[Literal["name", "description"]]:
        if not v:
            raise ValueError("target_fields must contain at least one of 'name' or 'description'")
        if len(set(v)) != len(v):
            raise ValueError("target_fields must not contain duplicates")
        order = {"name": 0, "description": 1}
        return sorted(v, key=order.__getitem__)

    @model_validator(mode="after")
    def _has_grounding_signal(self) -> "SuggestPromptArgumentFieldsRequest":
        # Safe from IndexError here: `_arguments_not_empty` and
        # `target_index: Field(..., ge=0)` both run as field-level validation
        # before this runs. The early-return below guards the upper bound. If
        # a future edit relaxes either of those invariants, this validator
        # needs a defensive check added — do not rely on ordering quietly.
        if self.target_index >= len(self.arguments):
            return self  # service-layer 400 handles out-of-range
        target = self.arguments[self.target_index]
        wants_name = "name" in self.target_fields
        wants_description = "description" in self.target_fields
        # `has_template` is trivially `bool(self.prompt_content)` because the
        # `mode="before"` validator converted whitespace-only strings to None.
        # Same for `target.name` / `target.description` via ArgumentInput's
        # normalizer. Single canonicalization point.
        has_template = bool(self.prompt_content)
        if wants_name and wants_description:
            if not has_template:
                raise ValueError(
                    "Cannot generate both name and description without prompt_content "
                    "as grounding.",
                )
        elif wants_name:
            if not target.description and not has_template:
                raise ValueError(
                    "Cannot suggest 'name': arguments[target_index].description is empty "
                    "and prompt_content is empty. LLM has no grounding signal.",
                )
        elif not target.name and not has_template:
            raise ValueError(
                "Cannot suggest 'description': arguments[target_index].name is empty "
                "and prompt_content is empty. LLM has no grounding signal.",
            )
        return self


class ArgumentSuggestion(BaseModel):
    """A suggested argument with name, description, and required flag."""

    name: str = Field(
        ...,
        description="Argument identifier (lowercase with underscores — e.g. `code_to_review`).",
    )
    description: str = Field(
        ...,
        description="Plain-language description of what the argument represents.",
    )
    required: bool = Field(
        False,
        description="Whether the template appears to treat this argument as required.",
    )


class SuggestPromptArgumentsResponse(BaseModel):
    """
    Response for both `/ai/suggest-prompt-arguments` (generate-all, N
    entries) and `/ai/suggest-prompt-argument-fields` (refine, 1 entry).
    The N-vs-1 semantic lives in the router docstrings.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "arguments": [
                        {
                            "name": "document",
                            "description": "The source text to summarize.",
                            "required": True,
                        },
                        {
                            "name": "num_sentences",
                            "description": "How many sentences to produce.",
                            "required": True,
                        },
                    ],
                },
            ],
        },
    )

    arguments: list[ArgumentSuggestion] = Field(
        ...,
        description=(
            "On `/ai/suggest-prompt-arguments`: one entry per new "
            "placeholder detected in `prompt_content`. On "
            "`/ai/suggest-prompt-argument-fields`: a single-element list "
            "containing the refined entry (or empty if the generated name "
            "failed validation)."
        ),
    )
