"""
Model-layer tests for the public-sharing schema invariants.

These guard the two database guarantees the sharing feature relies on, on every
content table:
  - CHECK ck_{type}_public_requires_token: a published item (is_public=true)
    must have a public_token — a "shared" item can never be unreachable.
  - Partial unique index uq_{type}_public_token: a non-null token is unique
    within the table, while many unpublished (null-token) rows may coexist.
"""
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.tier_limits import Tier
from models.bookmark import Bookmark
from models.note import Note
from models.prompt import Prompt
from models.user import User

# (param label, builder, check-constraint name, unique-index name)
_TYPES = ["bookmark", "note", "prompt"]
_CHECK_NAME = {
    "bookmark": "ck_bookmark_public_requires_token",
    "note": "ck_note_public_requires_token",
    "prompt": "ck_prompt_public_requires_token",
}
_UNIQUE_NAME = {
    "bookmark": "uq_bookmark_public_token",
    "note": "uq_note_public_token",
    "prompt": "uq_prompt_public_token",
}


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a user to own the items under test."""
    user = User(
        external_auth_id="test-auth0-id-public-sharing",
        email="public-sharing@test.local",
        tier=Tier.FREE.value,
    )
    db_session.add(user)
    await db_session.flush()
    return user


def _make_item(
    item_type: str,
    user_id: object,
    *,
    is_public: bool,
    public_token: str | None,
    unique: str,
) -> Bookmark | Note | Prompt:
    """
    Build an unsaved item of the given type with distinct unique-key fields.

    `unique` keeps url/name distinct so the only constraint a test can trip is
    the sharing one under test, not bookmark-url / prompt-name uniqueness.
    """
    if item_type == "bookmark":
        return Bookmark(
            user_id=user_id,
            url=f"https://example.com/{unique}",
            is_public=is_public,
            public_token=public_token,
        )
    if item_type == "note":
        return Note(
            user_id=user_id,
            title=f"note-{unique}",
            is_public=is_public,
            public_token=public_token,
        )
    return Prompt(
        user_id=user_id,
        name=f"prompt-{unique}",
        is_public=is_public,
        public_token=public_token,
    )


@pytest.mark.parametrize("item_type", _TYPES)
async def test__published_without_token__rejected(
    db_session: AsyncSession, test_user: User, item_type: str,
) -> None:
    """is_public=true with a null token violates the CHECK constraint."""
    db_session.add(
        _make_item(item_type, test_user.id, is_public=True, public_token=None, unique="a"),
    )
    with pytest.raises(IntegrityError) as exc:
        await db_session.flush()
    assert _CHECK_NAME[item_type] in str(exc.value)


@pytest.mark.parametrize("item_type", _TYPES)
async def test__published_with_token__succeeds(
    db_session: AsyncSession, test_user: User, item_type: str,
) -> None:
    """is_public=true with a token is the valid published state (positive control)."""
    item = _make_item(item_type, test_user.id, is_public=True, public_token="tok-ok", unique="a")
    db_session.add(item)
    await db_session.flush()
    assert item.id is not None


@pytest.mark.parametrize("item_type", _TYPES)
async def test__duplicate_token__rejected(
    db_session: AsyncSession, test_user: User, item_type: str,
) -> None:
    """Two items sharing a non-null token violate the partial unique index."""
    db_session.add(
        _make_item(item_type, test_user.id, is_public=True, public_token="dup", unique="a"),
    )
    await db_session.flush()

    db_session.add(
        _make_item(item_type, test_user.id, is_public=True, public_token="dup", unique="b"),
    )
    with pytest.raises(IntegrityError) as exc:
        await db_session.flush()
    assert _UNIQUE_NAME[item_type] in str(exc.value)


@pytest.mark.parametrize("item_type", _TYPES)
async def test__multiple_null_tokens__allowed(
    db_session: AsyncSession, test_user: User, item_type: str,
) -> None:
    """Many unpublished (null-token) rows coexist — the index is partial on non-null."""
    for unique in ("a", "b", "c"):
        db_session.add(
            _make_item(
                item_type, test_user.id, is_public=False, public_token=None, unique=unique,
            ),
        )
    await db_session.flush()  # no IntegrityError == pass
