"""
Tests for Prompt model.

Tests model instantiation, relationships, hybrid properties, cascade behavior,
and the partial unique index for name uniqueness.
"""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.prompt import Prompt
from models.tag import Tag, prompt_tags
from models.user import User
from core.tier_limits import Tier


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(external_auth_id="test-user-prompt-model-123", email="prompt-model@example.com", tier=Tier.FREE.value)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_prompt(db_session: AsyncSession, test_user: User) -> Prompt:
    """Create a test prompt."""
    prompt = Prompt(
        user_id=test_user.id,
        name="test-prompt",
        title="Test Prompt",
        description="A test prompt",
        content="Hello {{ name }}!",
        arguments=[{"name": "name", "description": "The name", "required": True}],
    )
    db_session.add(prompt)
    await db_session.flush()
    await db_session.refresh(prompt)
    return prompt


# =============================================================================
# Model Instantiation Tests
# =============================================================================


async def test__prompt_model__creates_with_required_fields(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that prompt can be created with only required fields (name, user_id)."""
    prompt = Prompt(
        user_id=test_user.id,
        name="minimal-prompt",
    )
    db_session.add(prompt)
    await db_session.flush()
    await db_session.refresh(prompt)

    assert prompt.id is not None
    assert prompt.user_id == test_user.id
    assert prompt.name == "minimal-prompt"
    assert prompt.title is None
    assert prompt.description is None
    assert prompt.content is None
    assert prompt.created_at is not None
    assert prompt.updated_at is not None
    assert prompt.last_used_at is not None
    assert prompt.deleted_at is None
    assert prompt.archived_at is None


async def test__prompt_model__creates_with_all_fields(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that prompt can be created with all fields populated."""
    arguments = [
        {"name": "code", "description": "The code to review", "required": True},
        {"name": "language", "description": "Programming language", "required": False},
    ]
    prompt = Prompt(
        user_id=test_user.id,
        name="code-review",
        title="Code Review Assistant",
        description="Reviews code for issues",
        content="Please review the following {{ language }} code:\n\n{{ code }}",
        arguments=arguments,
    )
    db_session.add(prompt)
    await db_session.flush()
    await db_session.refresh(prompt)

    assert prompt.id is not None
    assert prompt.name == "code-review"
    assert prompt.title == "Code Review Assistant"
    assert prompt.description == "Reviews code for issues"
    assert prompt.content == "Please review the following {{ language }} code:\n\n{{ code }}"
    assert prompt.arguments == arguments


async def test__prompt_model__arguments_server_default(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """
    Test that arguments gets server_default of [] after flush.

    Note: Python-side defaults are handled by Pydantic schemas (PromptCreate),
    not the SQLAlchemy model. Before flush, arguments is None. After flush,
    the server_default provides [].
    """
    prompt = Prompt(
        user_id=test_user.id,
        name="no-args-prompt",
    )

    # Before flush, Python-side value is None (no Python default set)
    assert prompt.arguments is None

    db_session.add(prompt)
    await db_session.flush()
    await db_session.refresh(prompt)

    # After flush, server_default provides []
    assert prompt.arguments == []


async def test__prompt_model__arguments_explicit_empty_list(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that explicitly setting arguments=[] works correctly."""
    prompt = Prompt(
        user_id=test_user.id,
        name="explicit-empty-args",
        arguments=[],
    )

    assert prompt.arguments == []

    db_session.add(prompt)
    await db_session.flush()
    await db_session.refresh(prompt)

    assert prompt.arguments == []


# =============================================================================
# Relationship Tests
# =============================================================================


async def test__prompt_model__user_relationship(
    db_session: AsyncSession,
    test_user: User,
    test_prompt: Prompt,
) -> None:
    """Test that prompt.user returns the associated User."""
    await db_session.refresh(test_prompt, attribute_names=["user"])

    assert test_prompt.user is not None
    assert test_prompt.user.id == test_user.id
    assert test_prompt.user.external_auth_id == test_user.external_auth_id


async def test__prompt_model__tag_objects_relationship(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that prompt.tag_objects returns associated tags."""
    # Create tags
    tag1 = Tag(user_id=test_user.id, name="coding")
    tag2 = Tag(user_id=test_user.id, name="ai")
    db_session.add_all([tag1, tag2])
    await db_session.flush()

    # Create prompt with tags
    prompt = Prompt(
        user_id=test_user.id,
        name="tagged-prompt",
        tag_objects=[tag1, tag2],
    )
    db_session.add(prompt)
    await db_session.flush()
    await db_session.refresh(prompt, attribute_names=["tag_objects"])

    assert len(prompt.tag_objects) == 2
    tag_names = [t.name for t in prompt.tag_objects]
    assert "coding" in tag_names
    assert "ai" in tag_names


# =============================================================================
# Hybrid Property Tests (is_archived)
# =============================================================================


async def test__prompt_model__is_archived_false_when_archived_at_null(
    db_session: AsyncSession,  # noqa: ARG001
    test_prompt: Prompt,
) -> None:
    """Test that is_archived returns False when archived_at is None."""
    assert test_prompt.archived_at is None
    assert test_prompt.is_archived is False


async def test__prompt_model__is_archived_true_when_archived_at_set(
    db_session: AsyncSession,
    test_prompt: Prompt,
) -> None:
    """Test that is_archived returns True when archived_at is in the past."""
    test_prompt.archived_at = datetime.now(UTC) - timedelta(hours=1)
    await db_session.flush()
    await db_session.refresh(test_prompt)

    assert test_prompt.is_archived is True


async def test__prompt_model__is_archived_false_when_archived_at_future(
    db_session: AsyncSession,
    test_prompt: Prompt,
) -> None:
    """Test that is_archived returns False when archived_at is in the future."""
    test_prompt.archived_at = datetime.now(UTC) + timedelta(days=1)
    await db_session.flush()
    await db_session.refresh(test_prompt)

    assert test_prompt.is_archived is False


# =============================================================================
# CASCADE Behavior Tests
# =============================================================================


async def test__prompt_model__cascade_delete_user_removes_prompts(
    db_session: AsyncSession,
) -> None:
    """Test that deleting a user cascades to delete their prompts."""
    # Create user and prompt
    user = User(external_auth_id="cascade-test-user", email="cascade@example.com", tier=Tier.FREE.value)
    db_session.add(user)
    await db_session.flush()

    prompt = Prompt(user_id=user.id, name="will-be-deleted")
    db_session.add(prompt)
    await db_session.flush()
    prompt_id = prompt.id

    # Delete user
    await db_session.delete(user)
    await db_session.flush()

    # Verify prompt is gone
    result = await db_session.execute(select(Prompt).where(Prompt.id == prompt_id))
    assert result.scalar_one_or_none() is None


async def test__prompt_model__cascade_delete_prompt_removes_prompt_tags(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that deleting a prompt cascades to remove prompt_tags entries."""
    # Create tag
    tag = Tag(user_id=test_user.id, name="test-tag")
    db_session.add(tag)
    await db_session.flush()

    # Create prompt with tag
    prompt = Prompt(user_id=test_user.id, name="tagged-prompt")
    prompt.tag_objects = [tag]
    db_session.add(prompt)
    await db_session.flush()
    prompt_id = prompt.id

    # Verify prompt_tags entry exists
    result = await db_session.execute(
        select(prompt_tags).where(prompt_tags.c.prompt_id == prompt_id),
    )
    assert result.first() is not None

    # Delete prompt
    await db_session.delete(prompt)
    await db_session.flush()

    # Verify prompt_tags entry is gone
    result = await db_session.execute(
        select(prompt_tags).where(prompt_tags.c.prompt_id == prompt_id),
    )
    assert result.first() is None


# =============================================================================
# Partial Unique Index Tests
# =============================================================================


async def test__prompt_model__unique_name_per_user_for_active(
    db_session: AsyncSession,
    test_user: User,
    test_prompt: Prompt,  # noqa: ARG001
) -> None:
    """Test that duplicate name for same user raises IntegrityError."""
    # test_prompt already has name="test-prompt"
    duplicate = Prompt(user_id=test_user.id, name="test-prompt")
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test__prompt_model__same_name_allowed_after_soft_delete(
    db_session: AsyncSession,
    test_user: User,
    test_prompt: Prompt,
) -> None:
    """Test that name can be reused after original prompt is soft-deleted."""
    # Soft delete the original
    test_prompt.deleted_at = func.now()
    await db_session.flush()

    # Create new prompt with same name - should succeed
    new_prompt = Prompt(user_id=test_user.id, name="test-prompt")
    db_session.add(new_prompt)
    await db_session.flush()

    assert new_prompt.id is not None
    assert new_prompt.name == "test-prompt"


async def test__prompt_model__same_name_allowed_different_users(
    db_session: AsyncSession,
    test_user: User,  # noqa: ARG001
    test_prompt: Prompt,  # noqa: ARG001
) -> None:
    """Test that different users can have prompts with the same name."""
    # Create another user
    other_user = User(external_auth_id="other-user-prompt-123", email="other@example.com", tier=Tier.FREE.value)
    db_session.add(other_user)
    await db_session.flush()

    # Create prompt with same name for different user - should succeed
    other_prompt = Prompt(user_id=other_user.id, name="test-prompt")
    db_session.add(other_prompt)
    await db_session.flush()

    assert other_prompt.id is not None
    assert other_prompt.name == "test-prompt"
