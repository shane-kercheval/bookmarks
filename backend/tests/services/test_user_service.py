"""
Tests for user creation defaults and the identity invariant.

Note: Imports from core.auth are done inside test methods to avoid triggering
Settings validation during test collection (before DATABASE_URL is set by fixtures).
"""
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.content_filter import ContentFilter
from models.user import User
from services import user_service


async def _get_user_filters(db_session: AsyncSession, user_id: UUID) -> list[ContentFilter]:
    result = await db_session.execute(
        select(ContentFilter).where(ContentFilter.user_id == user_id),
    )
    return list(result.scalars().all())


async def test__create_user_with_defaults__creates_default_filters(
    db_session: AsyncSession,
) -> None:
    user = await user_service.create_user_with_defaults(
        db_session,
        external_auth_id="test|default-lists",
        email="default-lists@test.com",
    )

    lists = await _get_user_filters(db_session, user.id)
    names = {lst.name for lst in lists}
    assert names == {"All Bookmarks", "All Notes", "All Prompts"}
    for lst in lists:
        assert lst.filter_expression == {"groups": [], "group_operator": "OR"}
        assert lst.default_sort_by == "last_used_at"
        assert lst.default_sort_ascending is False


async def test__create_user_with_defaults__does_not_recreate_deleted_defaults(
    db_session: AsyncSession,
) -> None:
    from core.auth import get_or_create_user  # noqa: PLC0415

    user = await get_or_create_user(
        db_session,
        external_auth_id="test|default-lists-delete",
        email="default-lists-delete@test.com",
    )

    lists = await _get_user_filters(db_session, user.id)
    assert len(lists) == 3

    await db_session.delete(lists[0])
    await db_session.flush()

    user_again = await get_or_create_user(
        db_session,
        external_auth_id="test|default-lists-delete",
        email="default-lists-delete@test.com",
    )
    assert user_again.id == user.id

    lists_after = await _get_user_filters(db_session, user.id)
    assert len(lists_after) == 2


class TestIdentityKeying:
    """User creation is keyed by external_auth_id (the Clerk `sub`)."""

    async def test__clerk_keyed_creation(
        self,
        db_session: AsyncSession,
    ) -> None:
        user = await user_service.create_user_with_defaults(
            db_session, external_auth_id="user_invariant_clerk",
        )
        assert user.external_auth_id == "user_invariant_clerk"

    async def test__duplicate_identifier__unique_constraint_rejects(
        self,
        db_session: AsyncSession,
    ) -> None:
        """The unique index on external_auth_id is the identity invariant now."""
        await user_service.create_user_with_defaults(
            db_session, external_auth_id="user_invariant_dup",
        )
        db_session.add(User(external_auth_id="user_invariant_dup"))
        with pytest.raises(IntegrityError):
            await db_session.flush()
        await db_session.rollback()
