"""
Tests for user_service.delete_user_by_external_auth_id — the application-level
delete-user path (called by the Clerk webhook handler). The deep per-table
cascade behavior is covered by test_user_cascade.py; these tests cover the
service semantics wrapped around it: tombstones, idempotency, scaling.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from models.bookmark import Bookmark
from models.deleted_identity import DeletedIdentity
from models.user import User
from services.user_service import delete_user_by_external_auth_id


async def _make_user(
    db: AsyncSession,
    *,
    external_auth_id: str,
) -> User:
    user = User(
        external_auth_id=external_auth_id,
        email=f"{external_auth_id}@test.com",
    )
    db.add(user)
    await db.flush()
    db.add(Bookmark(user_id=user.id, url="https://example.com/"))
    await db.flush()
    return user


async def test__existing_user__deleted_with_content_and_tombstoned(
    db_session: AsyncSession,
) -> None:
    """The row and its content go; the tombstone carries the Clerk id."""
    user = await _make_user(db_session, external_auth_id="user_svc_delete")
    user_id = user.id

    assert (await delete_user_by_external_auth_id(db_session, "user_svc_delete")).deleted is True

    users = await db_session.execute(
        select(User).where(User.external_auth_id == "user_svc_delete"),
    )
    assert users.scalar_one_or_none() is None
    bookmarks = await db_session.execute(
        select(Bookmark).where(Bookmark.user_id == user_id),
    )
    assert bookmarks.scalars().all() == []
    (await db_session.execute(
        select(DeletedIdentity).where(
            DeletedIdentity.external_auth_id == "user_svc_delete",
        ),
    )).scalar_one()


async def test__unknown_identity__tombstoned_returns_false(
    db_session: AsyncSession,
) -> None:
    """An identity we never provisioned still gets a Clerk-id tombstone."""
    assert (await delete_user_by_external_auth_id(db_session, "user_svc_ghost")).deleted is False

    (await db_session.execute(
        select(DeletedIdentity).where(
            DeletedIdentity.external_auth_id == "user_svc_ghost",
        ),
    )).scalar_one()


async def test__repeat_deletion__idempotent_single_tombstone(
    db_session: AsyncSession,
) -> None:
    """Deleting twice (webhook replay) succeeds both times, one tombstone."""
    await _make_user(db_session, external_auth_id="user_svc_replay")

    assert (await delete_user_by_external_auth_id(db_session, "user_svc_replay")).deleted is True
    assert (await delete_user_by_external_auth_id(db_session, "user_svc_replay")).deleted is False

    tombstones = (await db_session.execute(
        select(DeletedIdentity).where(
            DeletedIdentity.external_auth_id == "user_svc_replay",
        ),
    )).scalars().all()
    assert len(tombstones) == 1


async def test__other_users_unaffected(db_session: AsyncSession) -> None:
    """Deletion is scoped to the one identity."""
    await _make_user(db_session, external_auth_id="user_svc_victim")
    bystander = await _make_user(db_session, external_auth_id="user_svc_bystander")
    bystander_id = bystander.id

    await delete_user_by_external_auth_id(db_session, "user_svc_victim")

    users = await db_session.execute(
        select(User).where(User.external_auth_id == "user_svc_bystander"),
    )
    assert users.scalar_one_or_none() is not None
    bookmarks = await db_session.execute(
        select(Bookmark).where(Bookmark.user_id == bystander_id),
    )
    assert len(bookmarks.scalars().all()) == 1


async def test__deletion_resolves_restrict_edge__filter_group_referencing_tag(
    db_session: AsyncSession,
) -> None:
    """
    The one FK a pure DB cascade cannot resolve: filter_group_tags.tag_id is
    ondelete=RESTRICT, and Postgres checks it per internal cascade statement —
    users -> tags can trip it before the content_filters chain has removed the
    association rows (verified empirically; even NO ACTION fails, the timing
    is cascade-order-dependent). The service path must therefore ORM-delete
    the filter chain first, then let the DB cascade everything else. This
    test is the regression gate: a user whose filter group references a tag
    must delete cleanly.
    """
    from models.content_filter import ContentFilter  # noqa: PLC0415
    from models.filter_group import FilterGroup  # noqa: PLC0415
    from models.tag import Tag, filter_group_tags  # noqa: PLC0415

    user = await _make_user(db_session, external_auth_id="user_restrict_edge")
    user_id = user.id

    tag = Tag(user_id=user_id, name="restrict-edge")
    db_session.add(tag)
    await db_session.flush()
    content_filter = ContentFilter(
        user_id=user_id,
        name="cascade-filter",
        content_types=["bookmarks"],
    )
    db_session.add(content_filter)
    await db_session.flush()
    group = FilterGroup(filter_id=content_filter.id, position=0)
    group.tag_objects = [tag]
    db_session.add(group)
    await db_session.flush()
    group_id = group.id

    result = await delete_user_by_external_auth_id(db_session, "user_restrict_edge")
    assert result.deleted is True

    for model, label in [(Tag, "tags"), (ContentFilter, "content_filters")]:
        rows = (await db_session.execute(
            select(model).where(model.user_id == user_id),
        )).scalars().all()
        assert rows == [], f"{label} rows survived deletion"
    associations = (await db_session.execute(
        select(filter_group_tags).where(filter_group_tags.c.group_id == group_id),
    )).all()
    assert associations == []


async def test__deletion_query_count_does_not_scale_with_account_size(
    db_session: AsyncSession,
    async_engine: AsyncEngine,
) -> None:
    """
    Account deletion must not scale with account size (Svix expects a webhook
    response within its delivery timeout): every collection is
    passive_deletes=True and the filter chain is bulk-deleted set-based, so
    nothing the ORM issues grows with the account. Comparative assertion —
    deleting an account with 6x the content AND 6x the filter graph (filters,
    groups, tagged groups: the review-round finding — filters have no quota,
    so they are just as unbounded as bookmarks) must issue exactly the same
    number of SQL statements.
    """
    from sqlalchemy import event  # noqa: PLC0415

    from models.content_filter import ContentFilter  # noqa: PLC0415
    from models.filter_group import FilterGroup  # noqa: PLC0415
    from models.note import Note  # noqa: PLC0415
    from models.tag import Tag  # noqa: PLC0415

    async def seed(external_auth_id: str, size: int) -> None:
        user = await _make_user(db_session, external_auth_id=external_auth_id)
        tag = Tag(user_id=user.id, name=f"tag-{external_auth_id}")
        db_session.add(tag)
        await db_session.flush()
        for i in range(size):
            db_session.add(Bookmark(user_id=user.id, url=f"https://example.com/{i}"))
            db_session.add(Note(user_id=user.id, title=f"note-{i}"))
            content_filter = ContentFilter(
                user_id=user.id,
                name=f"filter-{i}",
                content_types=["bookmarks"],
            )
            db_session.add(content_filter)
            await db_session.flush()
            group = FilterGroup(filter_id=content_filter.id, position=0)
            group.tag_objects = [tag]
            db_session.add(group)
        await db_session.flush()

    await seed("user_small_account", 2)
    await seed("user_large_account", 12)
    db_session.expunge_all()

    statements: list[str] = []

    def count_statement(
        conn: object,  # noqa: ARG001
        cursor: object,  # noqa: ARG001
        statement: str,
        parameters: object,  # noqa: ARG001
        context: object,  # noqa: ARG001
        executemany: bool,  # noqa: ARG001
    ) -> None:
        statements.append(statement)

    event.listen(async_engine.sync_engine, "after_cursor_execute", count_statement)
    try:
        assert (await delete_user_by_external_auth_id(
            db_session, "user_small_account",
        )).deleted is True
        small_count = len(statements)
        statements.clear()
        assert (await delete_user_by_external_auth_id(
            db_session, "user_large_account",
        )).deleted is True
        large_count = len(statements)
    finally:
        event.remove(async_engine.sync_engine, "after_cursor_execute", count_statement)

    assert small_count == large_count, (
        f"deletion issued {large_count} statements for the large account vs "
        f"{small_count} for the small one — a heavy collection is being "
        "ORM-loaded (passive_deletes removed?)"
    )
