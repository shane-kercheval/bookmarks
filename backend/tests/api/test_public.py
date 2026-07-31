"""Tests for the unauthenticated public share read endpoints (/public/*)."""
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from core.tier_limits import Tier, TierLimits
from models.bookmark import Bookmark
from models.note import Note
from models.prompt import Prompt
from models.user import User


async def _make_user(db: AsyncSession, suffix: str) -> User:
    """Create and flush a user to own published items."""
    user = User(
        external_auth_id=f"auth0|public-{suffix}",
        email=f"public-{suffix}@test.local",
        tier=Tier.FREE.value,
    )
    db.add(user)
    await db.flush()
    return user


async def _publish_bookmark(db: AsyncSession, user_id: object, token: str, **kwargs: object) -> Bookmark:
    item = Bookmark(
        user_id=user_id,
        url=kwargs.get("url", "https://example.com/article"),
        title=kwargs.get("title", "Public Bookmark"),
        description=kwargs.get("description", "A shared bookmark"),
        content=kwargs.get("content", "Scraped page content\nsecond line"),
        is_public=kwargs.get("is_public", True),
        public_token=token,
        archived_at=kwargs.get("archived_at"),
        deleted_at=kwargs.get("deleted_at"),
    )
    db.add(item)
    await db.flush()
    return item


async def _publish_note(db: AsyncSession, user_id: object, token: str, **kwargs: object) -> Note:
    item = Note(
        user_id=user_id,
        title=kwargs.get("title", "Public Note"),
        description=kwargs.get("description", "A shared note"),
        content=kwargs.get("content", "# Heading\n\nNote body"),
        is_public=kwargs.get("is_public", True),
        public_token=token,
        archived_at=kwargs.get("archived_at"),
        deleted_at=kwargs.get("deleted_at"),
    )
    db.add(item)
    await db.flush()
    return item


async def _publish_prompt(db: AsyncSession, user_id: object, token: str, **kwargs: object) -> Prompt:
    item = Prompt(
        user_id=user_id,
        name=kwargs.get("name", "public-prompt"),
        title=kwargs.get("title", "Public Prompt"),
        description=kwargs.get("description", "A shared prompt"),
        content=kwargs.get("content", "Summarize {{ topic }}"),
        arguments=kwargs.get("arguments", [{"name": "topic", "description": "the topic", "required": True}]),
        is_public=kwargs.get("is_public", True),
        public_token=token,
        archived_at=kwargs.get("archived_at"),
        deleted_at=kwargs.get("deleted_at"),
    )
    db.add(item)
    await db.flush()
    return item


# (type label, publish helper, url path segment, identifying field name + expected value)
_TYPES: list[tuple[str, Callable[..., Awaitable[object]], str]] = [
    ("bookmark", _publish_bookmark, "bookmarks"),
    ("note", _publish_note, "notes"),
    ("prompt", _publish_prompt, "prompts"),
]


@pytest.mark.parametrize(("label", "publish", "segment"), _TYPES)
async def test_get_published_item_returns_content(
    client: AsyncClient,
    db_session: AsyncSession,
    label: str,
    publish: Callable[..., Awaitable[object]],
    segment: str,
) -> None:
    """A published, active item is returned with its content and is_archived=false."""
    user = await _make_user(db_session, f"{label}-active")
    token = f"tok-active-{label}"
    await publish(db_session, user.id, token)

    resp = await client.get(f"/public/{segment}/{token}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] is not None
    assert data["is_archived"] is False
    assert "created_at" in data
    assert "updated_at" in data


async def test_get_public_bookmark_includes_url(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """The public bookmark response includes url (core content of a bookmark)."""
    user = await _make_user(db_session, "bm-url")
    await _publish_bookmark(db_session, user.id, "tok-url", url="https://example.com/page")

    resp = await client.get("/public/bookmarks/tok-url")

    assert resp.status_code == 200
    assert resp.json()["url"] == "https://example.com/page"


async def test_get_public_prompt_includes_name_and_arguments(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """The public prompt response includes name and arguments (functional content)."""
    user = await _make_user(db_session, "pr-args")
    await _publish_prompt(db_session, user.id, "tok-pr-args")

    resp = await client.get("/public/prompts/tok-pr-args")

    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "public-prompt"
    assert data["arguments"][0]["name"] == "topic"


@pytest.mark.parametrize(("label", "publish", "segment"), _TYPES)
async def test_archived_item_returns_is_archived_true(
    client: AsyncClient,
    db_session: AsyncSession,
    label: str,
    publish: Callable[..., Awaitable[object]],
    segment: str,
) -> None:
    """A published but archived item is still served, flagged is_archived=true."""
    user = await _make_user(db_session, f"{label}-archived")
    token = f"tok-archived-{label}"
    await publish(db_session, user.id, token, archived_at=datetime.now(UTC) - timedelta(days=1))

    resp = await client.get(f"/public/{segment}/{token}")

    assert resp.status_code == 200
    assert resp.json()["is_archived"] is True


async def test_future_archive_reports_not_archived(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """A future-dated archived_at (scheduled archive) is reported is_archived=false."""
    user = await _make_user(db_session, "future-archive")
    await _publish_note(
        db_session, user.id, "tok-future", archived_at=datetime.now(UTC) + timedelta(days=7),
    )

    resp = await client.get("/public/notes/tok-future")

    assert resp.status_code == 200
    assert resp.json()["is_archived"] is False


@pytest.mark.parametrize(("label", "publish", "segment"), _TYPES)
async def test_unknown_token_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,  # noqa: ARG001 - keeps DB wired for the override
    label: str,
    publish: Callable[..., Awaitable[object]],  # noqa: ARG001 - bundled in _TYPES parametrize
    segment: str,
) -> None:
    """An unknown share token returns 404."""
    resp = await client.get(f"/public/{segment}/does-not-exist-{label}")
    assert resp.status_code == 404


@pytest.mark.parametrize(("label", "publish", "segment"), _TYPES)
async def test_unpublished_token_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    label: str,
    publish: Callable[..., Awaitable[object]],
    segment: str,
) -> None:
    """A valid token on an item with is_public=False returns 404."""
    user = await _make_user(db_session, f"{label}-unpub")
    token = f"tok-unpub-{label}"
    await publish(db_session, user.id, token, is_public=False)

    resp = await client.get(f"/public/{segment}/{token}")
    assert resp.status_code == 404


@pytest.mark.parametrize(("label", "publish", "segment"), _TYPES)
async def test_soft_deleted_item_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    label: str,
    publish: Callable[..., Awaitable[object]],
    segment: str,
) -> None:
    """A soft-deleted item returns 404 even with a valid, published token."""
    user = await _make_user(db_session, f"{label}-deleted")
    token = f"tok-deleted-{label}"
    await publish(db_session, user.id, token, deleted_at=datetime.now(UTC))

    resp = await client.get(f"/public/{segment}/{token}")
    assert resp.status_code == 404


async def test_response_excludes_owner_fields(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """The public response must not leak owner/organizational/operational fields."""
    user = await _make_user(db_session, "no-leak")
    await _publish_bookmark(db_session, user.id, "tok-no-leak")

    resp = await client.get("/public/bookmarks/tok-no-leak")

    assert resp.status_code == 200
    data = resp.json()
    for forbidden in (
        "id", "user_id", "tags", "relationships", "archived_at", "deleted_at",
        "is_public", "public_token", "summary", "last_used_at",
    ):
        assert forbidden not in data, f"{forbidden} leaked into public response"


async def test_public_response_uses_public_cache_headers(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """Public responses are publicly cacheable with revalidation and no Vary: Authorization."""
    user = await _make_user(db_session, "cache")
    await _publish_note(db_session, user.id, "tok-cache")

    resp = await client.get("/public/notes/tok-cache")

    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "public, max-age=0, must-revalidate"
    assert "authorization" not in resp.headers.get("vary", "").lower()


async def test_public_endpoint_304_keeps_public_headers(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """A matching If-None-Match yields 304 that still carries the public cache headers."""
    user = await _make_user(db_session, "etag")
    await _publish_note(db_session, user.id, "tok-etag")

    first = await client.get("/public/notes/tok-etag")
    assert first.status_code == 200
    etag = first.headers["etag"]

    second = await client.get("/public/notes/tok-etag", headers={"If-None-Match": etag})
    assert second.status_code == 304
    assert second.headers["cache-control"] == "public, max-age=0, must-revalidate"
    assert "authorization" not in second.headers.get("vary", "").lower()


async def test_authenticated_endpoint_keeps_private_headers(
    client: AsyncClient,
) -> None:
    """Regression: authed (non-public) GETs still get private, no-cache + Vary: Authorization."""
    created = await client.post("/bookmarks/", json={"url": "https://private.example.com"})
    assert created.status_code == 201
    bookmark_id = created.json()["id"]

    resp = await client.get(f"/bookmarks/{bookmark_id}")

    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "private, no-cache"
    assert resp.headers.get("vary") == "Authorization"


async def test_ip_rate_limit_returns_429_and_is_keyed_by_forwarded_ip(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per-IP limit returns 429 past the cap, and distinct X-Forwarded-For IPs get own buckets."""
    monkeypatch.setattr("core.rate_limiter.PUBLIC_IP_RATE_LIMIT_PER_MINUTE", 2)
    user = await _make_user(db_session, "ratelimit")
    await _publish_bookmark(db_session, user.id, "tok-rl")
    url = "/public/bookmarks/tok-rl"
    ip_a = {"X-Forwarded-For": "203.0.113.10"}
    ip_b = {"X-Forwarded-For": "203.0.113.99"}

    assert (await client.get(url, headers=ip_a)).status_code == 200
    assert (await client.get(url, headers=ip_a)).status_code == 200
    blocked = await client.get(url, headers=ip_a)
    assert blocked.status_code == 429
    assert "retry-after" in blocked.headers

    # A different forwarded IP is an independent bucket and is still allowed.
    assert (await client.get(url, headers=ip_b)).status_code == 200


async def test_x_real_ip_takes_precedence_and_resists_xff_spoof(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When X-Real-IP is present, it keys the bucket and a rotating spoofed XFF can't dodge it."""
    monkeypatch.setattr("core.rate_limiter.PUBLIC_IP_RATE_LIMIT_PER_MINUTE", 2)
    user = await _make_user(db_session, "realip")
    await _publish_bookmark(db_session, user.id, "tok-realip")
    url = "/public/bookmarks/tok-realip"

    # Same real client (X-Real-IP) but a different forged X-Forwarded-For each
    # time: all share one bucket, so the third request is blocked despite the
    # rotating spoof — proving XFF can't be used to mint fresh buckets.
    def headers(spoof: str) -> dict[str, str]:
        return {"X-Real-IP": "198.51.100.7", "X-Forwarded-For": spoof}

    assert (await client.get(url, headers=headers("1.1.1.1"))).status_code == 200
    assert (await client.get(url, headers=headers("2.2.2.2"))).status_code == 200
    assert (await client.get(url, headers=headers("3.3.3.3"))).status_code == 429


async def test_public_response_includes_content_metadata(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """content_metadata reports the full line range for the returned content."""
    user = await _make_user(db_session, "cmeta")
    await _publish_note(db_session, user.id, "tok-cmeta", content="line1\nline2\nline3")

    resp = await client.get("/public/notes/tok-cmeta")

    assert resp.status_code == 200
    meta = resp.json()["content_metadata"]
    assert meta is not None
    assert meta["total_lines"] == 3
    assert meta["start_line"] == 1
    assert meta["end_line"] == 3
    assert meta["is_partial"] is False


async def test_public_response_with_empty_content(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """An item with no content returns content/content_metadata as null, not an error."""
    user = await _make_user(db_session, "empty")
    await _publish_note(db_session, user.id, "tok-empty", content=None)

    resp = await client.get("/public/notes/tok-empty")

    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] is None
    assert data["content_metadata"] is None


# =============================================================================
# Clone ("Save a copy") endpoints
# =============================================================================
#
# The `client` fixture authenticates as the dev user; sources are published by a
# separate owner, so these exercise the realistic "clone someone else's shared
# item into my account" path.


async def test_clone_note_creates_independent_copy(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """Cloning a public note creates a fresh, clean, owned copy."""
    owner = await _make_user(db_session, "clone-note-src")
    await _publish_note(
        db_session, owner.id, "tok-clone-note",
        title="Shared Note", description="desc", content="line1\nline2",
    )

    resp = await client.post("/public/notes/tok-clone-note/save")

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["title"] == "Shared Note"
    assert data["description"] == "desc"
    assert data["content"] == "line1\nline2"
    # Clean & independent: no organizational metadata, active, unshared.
    assert data["tags"] == []
    assert data["relationships"] == []
    assert data["archived_at"] is None
    assert data["is_public"] is False
    assert data["public_token"] is None
    # It is a real item owned by the cloner.
    assert (await client.get(f"/notes/{data['id']}")).status_code == 200


async def test_clone_bookmark_copies_url(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """Cloning a public bookmark copies its url and starts unshared."""
    owner = await _make_user(db_session, "clone-bm-src")
    await _publish_bookmark(
        db_session, owner.id, "tok-clone-bm", url="https://example.com/cloneme",
    )

    resp = await client.post("/public/bookmarks/tok-clone-bm/save")

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["url"] == "https://example.com/cloneme"
    assert data["is_public"] is False
    assert data["public_token"] is None
    assert data["tags"] == []


async def test_clone_prompt_unique_name(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """Cloning a public prompt whose name the cloner lacks uses the original name."""
    owner = await _make_user(db_session, "clone-pr-src")
    await _publish_prompt(
        db_session, owner.id, "tok-clone-pr",
        name="shared-prompt", content="Summarize the text.", arguments=[],
    )

    resp = await client.post("/public/prompts/tok-clone-pr/save")

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "shared-prompt"
    assert data["is_public"] is False


async def test_clone_prompt_name_conflict_uses_copy_suffix(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """If the cloner already owns the name, the clone is saved as '{name}-copy'."""
    owner = await _make_user(db_session, "clone-pr-conf")
    await _publish_prompt(
        db_session, owner.id, "tok-clone-pr-conf",
        name="dup-prompt", content="Summarize the text.", arguments=[],
    )
    pre = await client.post("/prompts/", json={"name": "dup-prompt", "content": "x"})
    assert pre.status_code == 201

    resp = await client.post("/public/prompts/tok-clone-pr-conf/save")

    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == "dup-prompt-copy"


async def test_clone_prompt_double_conflict_returns_409(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """If both '{name}' and '{name}-copy' are taken, the clone returns a descriptive 409."""
    owner = await _make_user(db_session, "clone-pr-dbl")
    await _publish_prompt(
        db_session, owner.id, "tok-clone-pr-dbl",
        name="taken", content="Summarize the text.", arguments=[],
    )
    for name in ("taken", "taken-copy"):
        r = await client.post("/prompts/", json={"name": name, "content": "x"})
        assert r.status_code == 201

    resp = await client.post("/public/prompts/tok-clone-pr-dbl/save")

    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["error_code"] == "NAME_CONFLICT"
    assert "taken-copy" in detail["message"]


@pytest.mark.parametrize(("label", "publish", "segment"), _TYPES)
async def test_clone_unknown_token_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,  # noqa: ARG001 - keeps DB wired for the override
    label: str,
    publish: Callable[..., Awaitable[object]],  # noqa: ARG001 - bundled in _TYPES parametrize
    segment: str,
) -> None:
    """Cloning an unknown token returns 404."""
    resp = await client.post(f"/public/{segment}/nonexistent-{label}/save")
    assert resp.status_code == 404


@pytest.mark.parametrize(("label", "publish", "segment"), _TYPES)
async def test_clone_unpublished_token_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    label: str,
    publish: Callable[..., Awaitable[object]],
    segment: str,
) -> None:
    """Cloning a token whose item is not public returns 404."""
    owner = await _make_user(db_session, f"clone-unpub-{label}")
    await publish(db_session, owner.id, f"tok-clone-unpub-{label}", is_public=False)
    resp = await client.post(f"/public/{segment}/tok-clone-unpub-{label}/save")
    assert resp.status_code == 404


@pytest.mark.parametrize(("label", "publish", "segment"), _TYPES)
async def test_clone_soft_deleted_token_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    label: str,
    publish: Callable[..., Awaitable[object]],
    segment: str,
) -> None:
    """Cloning a soft-deleted item's token returns 404."""
    owner = await _make_user(db_session, f"clone-del-{label}")
    await publish(
        db_session, owner.id, f"tok-clone-del-{label}", deleted_at=datetime.now(UTC),
    )
    resp = await client.post(f"/public/{segment}/tok-clone-del-{label}/save")
    assert resp.status_code == 404


@pytest.mark.parametrize(("label", "publish", "segment"), _TYPES)
async def test_clone_unauthenticated_returns_401(
    auth_required_client: AsyncClient,
    db_session: AsyncSession,  # noqa: ARG001 - keeps DB wired for the override
    label: str,
    publish: Callable[..., Awaitable[object]],  # noqa: ARG001 - bundled in _TYPES parametrize
    segment: str,
) -> None:
    """Clone endpoints are auth-required despite the /public prefix."""
    resp = await auth_required_client.post(f"/public/{segment}/any-token-{label}/save")
    assert resp.status_code == 401


async def test_clone_bookmark_active_url_conflict_returns_409(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """Cloning a bookmark whose URL the cloner already has active returns 409, not 500."""
    owner = await _make_user(db_session, "clone-bm-active")
    await _publish_bookmark(
        db_session, owner.id, "tok-bm-active", url="https://dup.example.com/active",
    )
    pre = await client.post("/bookmarks/", json={"url": "https://dup.example.com/active"})
    assert pre.status_code == 201

    resp = await client.post("/public/bookmarks/tok-bm-active/save")

    assert resp.status_code == 409
    assert resp.json()["detail"]["error_code"] == "ACTIVE_URL_EXISTS"
    assert resp.json()["detail"]["message"] == "You already have this bookmark."


async def test_clone_bookmark_archived_url_conflict_returns_409(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """Cloning a bookmark whose URL the cloner has archived returns 409, not 500."""
    owner = await _make_user(db_session, "clone-bm-arch")
    await _publish_bookmark(
        db_session, owner.id, "tok-bm-arch", url="https://dup.example.com/archived",
    )
    pre = await client.post("/bookmarks/", json={"url": "https://dup.example.com/archived"})
    assert pre.status_code == 201
    assert (await client.post(f"/bookmarks/{pre.json()['id']}/archive")).status_code == 200

    resp = await client.post("/public/bookmarks/tok-bm-arch/save")

    assert resp.status_code == 409
    assert resp.json()["detail"]["error_code"] == "ARCHIVED_URL_EXISTS"
    assert resp.json()["detail"]["message"] == "You already have this bookmark — it's in your archive."


async def test_clone_exceeding_field_limit_returns_400(
    client: AsyncClient, db_session: AsyncSession, low_limits: TierLimits,
) -> None:
    """Cloning content larger than the cloner's tier limit returns 400, not 500."""
    owner = await _make_user(db_session, "clone-fieldlimit")
    long_content = "x" * (low_limits.max_note_content_length + 1)
    await _publish_note(
        db_session, owner.id, "tok-fieldlimit", title="t", content=long_content,
    )

    resp = await client.post("/public/notes/tok-fieldlimit/save")

    assert resp.status_code == 400
    assert resp.json()["error_code"] == "FIELD_LIMIT_EXCEEDED"


async def test_clone_quota_exceeded_returns_402(
    client: AsyncClient, db_session: AsyncSession, low_limits: TierLimits,
) -> None:
    """Cloning when the cloner is already at their item quota returns 402."""
    owner = await _make_user(db_session, "clone-quota")
    await _publish_note(db_session, owner.id, "tok-quota", title="t", content="c")
    for i in range(low_limits.max_notes):
        r = await client.post("/notes/", json={"title": f"N{i}", "content": "c"})
        assert r.status_code == 201

    resp = await client.post("/public/notes/tok-quota/save")

    assert resp.status_code == 402
    assert resp.json()["error_code"] == "QUOTA_EXCEEDED"


async def test_clone_prompt_preserves_arguments(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """A prompt clone round-trips its argument definitions (ORM JSON -> PromptCreate)."""
    owner = await _make_user(db_session, "clone-pr-args")
    await _publish_prompt(
        db_session, owner.id, "tok-pr-args2",
        name="arg-prompt", content="Summarize {{ topic }}",
        arguments=[{"name": "topic", "description": "the subject", "required": True}],
    )

    resp = await client.post("/public/prompts/tok-pr-args2/save")

    assert resp.status_code == 201, resp.text
    args = resp.json()["arguments"]
    assert len(args) == 1
    assert args[0]["name"] == "topic"
    assert args[0]["description"] == "the subject"
    assert args[0]["required"] is True


async def test_clone_drops_source_tags_and_relationships(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """
    The clone copies content, NOT the owner's organization graph.

    The source genuinely HAS a tag and a relationship, so this is a real strip
    check (not a default-empty check) of the privacy/ownership boundary.
    """
    src = (await client.post(
        "/notes/", json={"title": "Src", "content": "body", "tags": ["work"]},
    )).json()
    other = (await client.post("/notes/", json={"title": "Other"})).json()
    rel = await client.post("/relationships/", json={
        "source_type": "note", "source_id": src["id"],
        "target_type": "note", "target_id": other["id"],
        "relationship_type": "related",
    })
    assert rel.status_code in (200, 201), rel.text
    # Publish the source directly.
    note = await db_session.get(Note, UUID(src["id"]))
    note.is_public = True
    note.public_token = "tok-strip"
    await db_session.flush()

    resp = await client.post("/public/notes/tok-strip/save")

    assert resp.status_code == 201, resp.text
    clone = resp.json()
    assert clone["tags"] == []
    assert clone["relationships"] == []
    # Confirm persisted, not just response-shaped.
    refetch = (await client.get(f"/notes/{clone['id']}")).json()
    assert refetch["tags"] == []
    assert refetch["relationships"] == []


@pytest.mark.parametrize(("label", "publish", "segment"), _TYPES)
async def test_clone_archived_source_creates_active_copy(
    client: AsyncClient,
    db_session: AsyncSession,
    label: str,
    publish: Callable[..., Awaitable[object]],
    segment: str,
) -> None:
    """An archived shared item is cloneable; the copy starts active and unshared."""
    owner = await _make_user(db_session, f"clone-archived-{label}")
    await publish(
        db_session, owner.id, f"tok-clone-archived-{label}",
        archived_at=datetime.now(UTC) - timedelta(days=1),
    )

    resp = await client.post(f"/public/{segment}/tok-clone-archived-{label}/save")

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["archived_at"] is None
    assert data["is_public"] is False


async def test_clone_prompt_with_null_content_returns_422(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """A published prompt with null content can't be copied — 422, not a 500."""
    owner = await _make_user(db_session, "clone-null-content")
    await _publish_prompt(
        db_session, owner.id, "tok-null-content",
        name="empty-prompt", content=None, arguments=[],
    )

    resp = await client.post("/public/prompts/tok-null-content/save")

    assert resp.status_code == 422
    assert resp.json()["detail"]["error_code"] == "SOURCE_PROMPT_UNCOPYABLE"


async def test_clone_prompt_with_malformed_arguments_returns_422(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """Malformed stored arguments (no DB schema guarantee) yield 422, not a 500."""
    owner = await _make_user(db_session, "clone-bad-args")
    await _publish_prompt(
        db_session, owner.id, "tok-bad-args",
        name="bad-args-prompt", content="Summarize the text.",
        arguments=[{"description": "missing the required name field"}],
    )

    resp = await client.post("/public/prompts/tok-bad-args/save")

    assert resp.status_code == 422
    assert resp.json()["detail"]["error_code"] == "SOURCE_PROMPT_UNCOPYABLE"
