"""
Unit tests for filter_utils helper functions.

Tests cover the resolve_filter_and_sorting helper which resolves filter sort defaults.
"""
from uuid import UUID

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.helpers.filter_utils import ResolvedFilter, resolve_filter_and_sorting
from models.user import User
from schemas.content_filter import ContentFilterCreate, FilterExpression
from services import content_filter_service
from tests.api.conftest import add_consent_for_user


@pytest.fixture
async def user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(
        external_auth_id="test|unit-filter-utils",
        email="filter-utils@test.com",
    )
    db_session.add(user)
    await db_session.flush()
    await add_consent_for_user(db_session, user)
    return user


async def test__resolve_filter_and_sorting__no_filter_no_params__returns_global_defaults(
    db_session: AsyncSession,
    user: User,
) -> None:
    """When no filter_id and no explicit params, returns global defaults."""
    result = await resolve_filter_and_sorting(
        db=db_session,
        user_id=user.id,
        filter_id=None,
        sort_by=None,
        sort_order=None,
    )

    assert isinstance(result, ResolvedFilter)
    assert result.filter_expression is None
    assert result.sort_by == "created_at"
    assert result.sort_order == "desc"
    assert result.content_types is None


async def test__resolve_filter_and_sorting__no_filter__content_types_is_none(
    db_session: AsyncSession,
    user: User,
) -> None:
    """When no filter_id, content_types is always None."""
    result = await resolve_filter_and_sorting(
        db=db_session,
        user_id=user.id,
        filter_id=None,
        sort_by="title",
        sort_order="asc",
    )

    assert result.content_types is None


async def test__resolve_filter_and_sorting__no_filter_with_explicit_params__uses_explicit(
    db_session: AsyncSession,
    user: User,
) -> None:
    """When no filter_id but explicit params provided, uses explicit values."""
    result = await resolve_filter_and_sorting(
        db=db_session,
        user_id=user.id,
        filter_id=None,
        sort_by="title",
        sort_order="asc",
    )

    assert result.filter_expression is None
    assert result.sort_by == "title"
    assert result.sort_order == "asc"


async def test__resolve_filter_and_sorting__filter_with_sort_defaults__uses_filter_values(
    db_session: AsyncSession,
    user: User,
) -> None:
    """When filter has sort defaults, uses filter's sort settings."""
    data = ContentFilterCreate(
        name="Test Filter",
        content_types=["bookmark", "note"],
        filter_expression=FilterExpression(groups=[{"tags": ["test"]}]),
        default_sort_by="title",
        default_sort_ascending=True,
    )
    content_filter = await content_filter_service.create_filter(db_session, user.id, data)

    result = await resolve_filter_and_sorting(
        db=db_session,
        user_id=user.id,
        filter_id=content_filter.id,
        sort_by=None,
        sort_order=None,
    )

    assert result.filter_expression == content_filter.filter_expression
    assert result.sort_by == "title"
    assert result.sort_order == "asc"
    assert result.content_types == ["bookmark", "note"]


async def test__resolve_filter_and_sorting__filter_sort_ascending_false__returns_desc(
    db_session: AsyncSession,
    user: User,
) -> None:
    """When filter has default_sort_ascending=False, returns sort_order='desc'."""
    data = ContentFilterCreate(
        name="Desc Filter",
        content_types=["bookmark"],
        filter_expression=FilterExpression(groups=[]),
        default_sort_by="updated_at",
        default_sort_ascending=False,
    )
    content_filter = await content_filter_service.create_filter(db_session, user.id, data)

    result = await resolve_filter_and_sorting(
        db=db_session,
        user_id=user.id,
        filter_id=content_filter.id,
        sort_by=None,
        sort_order=None,
    )

    assert result.sort_by == "updated_at"
    assert result.sort_order == "desc"


async def test__resolve_filter_and_sorting__explicit_params_override_filter(
    db_session: AsyncSession,
    user: User,
) -> None:
    """Explicit params take priority over filter defaults."""
    data = ContentFilterCreate(
        name="Override Filter",
        content_types=["note"],
        filter_expression=FilterExpression(groups=[{"tags": ["work"]}]),
        default_sort_by="title",
        default_sort_ascending=True,
    )
    content_filter = await content_filter_service.create_filter(db_session, user.id, data)

    result = await resolve_filter_and_sorting(
        db=db_session,
        user_id=user.id,
        filter_id=content_filter.id,
        sort_by="created_at",
        sort_order="desc",
    )

    # Filter expression still used
    assert result.filter_expression == content_filter.filter_expression
    # But sort is overridden
    assert result.sort_by == "created_at"
    assert result.sort_order == "desc"


async def test__resolve_filter_and_sorting__partial_override_sort_by(
    db_session: AsyncSession,
    user: User,
) -> None:
    """Only sort_by overridden, sort_order from filter."""
    data = ContentFilterCreate(
        name="Partial Override Filter",
        content_types=["bookmark"],
        filter_expression=FilterExpression(groups=[]),
        default_sort_by="title",
        default_sort_ascending=True,  # asc
    )
    content_filter = await content_filter_service.create_filter(db_session, user.id, data)

    result = await resolve_filter_and_sorting(
        db=db_session,
        user_id=user.id,
        filter_id=content_filter.id,
        sort_by="updated_at",  # Override sort_by only
        sort_order=None,  # Use filter default
    )

    assert result.sort_by == "updated_at"
    assert result.sort_order == "asc"  # From filter


async def test__resolve_filter_and_sorting__partial_override_sort_order(
    db_session: AsyncSession,
    user: User,
) -> None:
    """Only sort_order overridden, sort_by from filter."""
    data = ContentFilterCreate(
        name="Partial Override Order Filter",
        content_types=["prompt"],
        filter_expression=FilterExpression(groups=[]),
        default_sort_by="last_used_at",
        default_sort_ascending=True,  # asc
    )
    content_filter = await content_filter_service.create_filter(db_session, user.id, data)

    result = await resolve_filter_and_sorting(
        db=db_session,
        user_id=user.id,
        filter_id=content_filter.id,
        sort_by=None,  # Use filter default
        sort_order="desc",  # Override sort_order only
    )

    assert result.sort_by == "last_used_at"  # From filter
    assert result.sort_order == "desc"


async def test__resolve_filter_and_sorting__filter_not_found__raises_404(
    db_session: AsyncSession,
    user: User,
) -> None:
    """When filter_id not found, raises HTTPException 404."""
    fake_filter_id = UUID("00000000-0000-0000-0000-000000000000")

    with pytest.raises(HTTPException) as exc_info:
        await resolve_filter_and_sorting(
            db=db_session,
            user_id=user.id,
            filter_id=fake_filter_id,
            sort_by=None,
            sort_order=None,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Filter not found"


async def test__resolve_filter_and_sorting__filter_no_sort_defaults__uses_global(
    db_session: AsyncSession,
    user: User,
) -> None:
    """Filter exists but has null sort fields, uses global defaults."""
    data = ContentFilterCreate(
        name="No Sort Defaults Filter",
        content_types=["bookmark", "note"],
        filter_expression=FilterExpression(groups=[{"tags": ["important"]}]),
        default_sort_by=None,
        default_sort_ascending=None,
    )
    content_filter = await content_filter_service.create_filter(db_session, user.id, data)

    result = await resolve_filter_and_sorting(
        db=db_session,
        user_id=user.id,
        filter_id=content_filter.id,
        sort_by=None,
        sort_order=None,
    )

    # Filter expression is used
    assert result.filter_expression == content_filter.filter_expression
    # But sort falls back to global defaults
    assert result.sort_by == "created_at"
    assert result.sort_order == "desc"


async def test__resolve_filter_and_sorting__filter_has_sort_by_but_null_ascending(
    db_session: AsyncSession,
    user: User,
) -> None:
    """Filter has default_sort_by but null default_sort_ascending."""
    data = ContentFilterCreate(
        name="Sort By Only Filter",
        content_types=["bookmark"],
        filter_expression=FilterExpression(groups=[]),
        default_sort_by="title",
        default_sort_ascending=None,  # No ascending preference
    )
    content_filter = await content_filter_service.create_filter(db_session, user.id, data)

    result = await resolve_filter_and_sorting(
        db=db_session,
        user_id=user.id,
        filter_id=content_filter.id,
        sort_by=None,
        sort_order=None,
    )

    assert result.sort_by == "title"  # From filter
    assert result.sort_order == "desc"  # Global fallback


async def test__resolve_filter_and_sorting__filter_has_ascending_but_null_sort_by(
    db_session: AsyncSession,
    user: User,
) -> None:
    """Filter has default_sort_ascending but null default_sort_by."""
    data = ContentFilterCreate(
        name="Ascending Only Filter",
        content_types=["note"],
        filter_expression=FilterExpression(groups=[]),
        default_sort_by=None,  # No sort field preference
        default_sort_ascending=True,  # But has ascending preference
    )
    content_filter = await content_filter_service.create_filter(db_session, user.id, data)

    result = await resolve_filter_and_sorting(
        db=db_session,
        user_id=user.id,
        filter_id=content_filter.id,
        sort_by=None,
        sort_order=None,
    )

    assert result.sort_by == "created_at"  # Global fallback
    assert result.sort_order == "asc"  # From filter


async def test__resolve_filter_and_sorting__returns_filter_content_types(
    db_session: AsyncSession,
    user: User,
) -> None:
    """Filter's content_types are included in result."""
    data = ContentFilterCreate(
        name="Content Types Filter",
        content_types=["bookmark", "prompt"],
        filter_expression=FilterExpression(groups=[]),
        default_sort_by=None,
        default_sort_ascending=None,
    )
    content_filter = await content_filter_service.create_filter(db_session, user.id, data)

    result = await resolve_filter_and_sorting(
        db=db_session,
        user_id=user.id,
        filter_id=content_filter.id,
        sort_by=None,
        sort_order=None,
    )

    assert result.content_types == ["bookmark", "prompt"]
