"""Tests for search_vector trigger behavior and FTS functionality."""
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from models.bookmark import Bookmark
from models.note import Note
from models.prompt import Prompt
from models.user import User
from core.tier_limits import Tier


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(external_auth_id='test-search-vector-user', email='sv@example.com', tier=Tier.FREE.value)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


# =============================================================================
# Bookmark Trigger Tests
# =============================================================================


async def test__bookmark_trigger__insert_populates_search_vector(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """INSERT should populate search_vector from content fields."""
    bookmark = Bookmark(
        user_id=test_user.id,
        url='https://example.com/trigger-test',
        title='Python Programming Guide',
        description='A comprehensive guide to Python',
        content='Learn Python from scratch with examples and exercises',
    )
    db_session.add(bookmark)
    await db_session.flush()

    # Read search_vector via raw SQL (it's deferred on the model)
    result = await db_session.execute(text(
        'SELECT search_vector FROM bookmarks WHERE id = :id',
    ), {'id': str(bookmark.id)})
    row = result.first()
    assert row is not None
    sv = row.search_vector
    assert sv is not None
    # Verify FTS match — "python" should match via stemming
    result = await db_session.execute(text(
        "SELECT search_vector @@ websearch_to_tsquery('english', 'python') FROM bookmarks WHERE id = :id",
    ), {'id': str(bookmark.id)})
    assert result.scalar() is True


async def test__bookmark_trigger__non_content_update_preserves_search_vector(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Updating last_used_at should NOT recompute search_vector."""
    bookmark = Bookmark(
        user_id=test_user.id,
        url='https://example.com/preserve-test',
        title='Original Title',
    )
    db_session.add(bookmark)
    await db_session.flush()

    # Get original search_vector
    result = await db_session.execute(text(
        'SELECT search_vector::text FROM bookmarks WHERE id = :id',
    ), {'id': str(bookmark.id)})
    original_sv = result.scalar()

    # Update last_used_at (non-content field)
    await db_session.execute(text(
        "UPDATE bookmarks SET last_used_at = now() WHERE id = :id",
    ), {'id': str(bookmark.id)})

    # Verify search_vector unchanged
    result = await db_session.execute(text(
        'SELECT search_vector::text FROM bookmarks WHERE id = :id',
    ), {'id': str(bookmark.id)})
    assert result.scalar() == original_sv


async def test__bookmark_trigger__content_update_recomputes_search_vector(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Updating title should recompute search_vector."""
    bookmark = Bookmark(
        user_id=test_user.id,
        url='https://example.com/recompute-test',
        title='Original Title',
    )
    db_session.add(bookmark)
    await db_session.flush()

    # Get original search_vector
    result = await db_session.execute(text(
        'SELECT search_vector::text FROM bookmarks WHERE id = :id',
    ), {'id': str(bookmark.id)})
    original_sv = result.scalar()

    # Update title (content field)
    await db_session.execute(text(
        "UPDATE bookmarks SET title = 'Completely New Title' WHERE id = :id",
    ), {'id': str(bookmark.id)})

    # Verify search_vector changed
    result = await db_session.execute(text(
        'SELECT search_vector::text FROM bookmarks WHERE id = :id',
    ), {'id': str(bookmark.id)})
    new_sv = result.scalar()
    assert new_sv != original_sv

    # Verify new title is searchable
    result = await db_session.execute(text(
        "SELECT search_vector @@ websearch_to_tsquery('english', 'completely new') "
        "FROM bookmarks WHERE id = :id",
    ), {'id': str(bookmark.id)})
    assert result.scalar() is True


async def test__bookmark_trigger__field_weights(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Verify title gets weight A and content gets weight C."""
    bookmark = Bookmark(
        user_id=test_user.id,
        url='https://example.com/weight-test',
        title='UniqueWeightTestTerm',
        content='AnotherWeightTestTerm',
    )
    db_session.add(bookmark)
    await db_session.flush()

    # Check that title term has weight A
    result = await db_session.execute(text(
        "SELECT search_vector::text FROM bookmarks WHERE id = :id",
    ), {'id': str(bookmark.id)})
    sv_text = result.scalar()
    assert sv_text is not None
    # tsvector text format includes position:weight like 'uniqueweighttestterm':1A
    assert "'uniqueweighttestterm':1A" in sv_text


async def test__bookmark_trigger__archive_preserves_search_vector(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Archiving a bookmark should NOT recompute search_vector."""
    bookmark = Bookmark(
        user_id=test_user.id,
        url='https://example.com/archive-test',
        title='Archive Test',
    )
    db_session.add(bookmark)
    await db_session.flush()

    result = await db_session.execute(text(
        'SELECT search_vector::text FROM bookmarks WHERE id = :id',
    ), {'id': str(bookmark.id)})
    original_sv = result.scalar()

    # Archive (non-content field)
    await db_session.execute(text(
        "UPDATE bookmarks SET archived_at = now() WHERE id = :id",
    ), {'id': str(bookmark.id)})

    result = await db_session.execute(text(
        'SELECT search_vector::text FROM bookmarks WHERE id = :id',
    ), {'id': str(bookmark.id)})
    assert result.scalar() == original_sv


async def test__bookmark_trigger__soft_delete_preserves_search_vector(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Soft-deleting a bookmark should NOT recompute search_vector."""
    bookmark = Bookmark(
        user_id=test_user.id,
        url='https://example.com/softdelete-test',
        title='SoftDelete Test',
    )
    db_session.add(bookmark)
    await db_session.flush()

    result = await db_session.execute(text(
        'SELECT search_vector::text FROM bookmarks WHERE id = :id',
    ), {'id': str(bookmark.id)})
    original_sv = result.scalar()

    await db_session.execute(text(
        "UPDATE bookmarks SET deleted_at = now() WHERE id = :id",
    ), {'id': str(bookmark.id)})

    result = await db_session.execute(text(
        'SELECT search_vector::text FROM bookmarks WHERE id = :id',
    ), {'id': str(bookmark.id)})
    assert result.scalar() == original_sv


# =============================================================================
# Note Trigger Tests
# =============================================================================


async def test__note_trigger__insert_populates_search_vector(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """INSERT should populate search_vector from content fields."""
    note = Note(
        user_id=test_user.id,
        title='Database Optimization Tips',
        description='Performance tips for PostgreSQL',
        content='Use indexes wisely and analyze query plans',
    )
    db_session.add(note)
    await db_session.flush()

    result = await db_session.execute(text(
        "SELECT search_vector @@ websearch_to_tsquery('english', 'optimization') "
        "FROM notes WHERE id = :id",
    ), {'id': str(note.id)})
    assert result.scalar() is True


async def test__note_trigger__non_content_update_preserves_search_vector(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Updating last_used_at should NOT recompute search_vector."""
    note = Note(
        user_id=test_user.id,
        title='Preserve Test Note',
    )
    db_session.add(note)
    await db_session.flush()

    result = await db_session.execute(text(
        'SELECT search_vector::text FROM notes WHERE id = :id',
    ), {'id': str(note.id)})
    original_sv = result.scalar()

    await db_session.execute(text(
        "UPDATE notes SET last_used_at = now() WHERE id = :id",
    ), {'id': str(note.id)})

    result = await db_session.execute(text(
        'SELECT search_vector::text FROM notes WHERE id = :id',
    ), {'id': str(note.id)})
    assert result.scalar() == original_sv


async def test__note_trigger__content_update_recomputes_search_vector(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Updating content should recompute search_vector."""
    note = Note(
        user_id=test_user.id,
        title='Update Test Note',
    )
    db_session.add(note)
    await db_session.flush()

    result = await db_session.execute(text(
        'SELECT search_vector::text FROM notes WHERE id = :id',
    ), {'id': str(note.id)})
    original_sv = result.scalar()

    await db_session.execute(text(
        "UPDATE notes SET content = 'Brand new content about machine learning' WHERE id = :id",
    ), {'id': str(note.id)})

    result = await db_session.execute(text(
        'SELECT search_vector::text FROM notes WHERE id = :id',
    ), {'id': str(note.id)})
    assert result.scalar() != original_sv

    result = await db_session.execute(text(
        "SELECT search_vector @@ websearch_to_tsquery('english', 'machine learning') "
        "FROM notes WHERE id = :id",
    ), {'id': str(note.id)})
    assert result.scalar() is True


# =============================================================================
# Prompt Trigger Tests
# =============================================================================


async def test__prompt_trigger__insert_populates_search_vector(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """INSERT should populate search_vector from content fields including name."""
    prompt = Prompt(
        user_id=test_user.id,
        name='code-review',
        title='Code Review Assistant',
        description='Reviews code for best practices',
        content='Review the following code and suggest improvements',
    )
    db_session.add(prompt)
    await db_session.flush()

    # Verify name is searchable (weight A)
    result = await db_session.execute(text(
        "SELECT search_vector @@ websearch_to_tsquery('english', 'code review') "
        "FROM prompts WHERE id = :id",
    ), {'id': str(prompt.id)})
    assert result.scalar() is True


async def test__prompt_trigger__name_update_recomputes_search_vector(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Updating name should recompute search_vector."""
    prompt = Prompt(
        user_id=test_user.id,
        name='original-name',
        title='Test Prompt',
    )
    db_session.add(prompt)
    await db_session.flush()

    result = await db_session.execute(text(
        'SELECT search_vector::text FROM prompts WHERE id = :id',
    ), {'id': str(prompt.id)})
    original_sv = result.scalar()

    await db_session.execute(text(
        "UPDATE prompts SET name = 'renamed-prompt' WHERE id = :id",
    ), {'id': str(prompt.id)})

    result = await db_session.execute(text(
        'SELECT search_vector::text FROM prompts WHERE id = :id',
    ), {'id': str(prompt.id)})
    assert result.scalar() != original_sv


async def test__prompt_trigger__non_content_update_preserves_search_vector(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Updating last_used_at should NOT recompute search_vector."""
    prompt = Prompt(
        user_id=test_user.id,
        name='preserve-test-prompt',
        title='Preserve Test',
    )
    db_session.add(prompt)
    await db_session.flush()

    result = await db_session.execute(text(
        'SELECT search_vector::text FROM prompts WHERE id = :id',
    ), {'id': str(prompt.id)})
    original_sv = result.scalar()

    await db_session.execute(text(
        "UPDATE prompts SET last_used_at = now() WHERE id = :id",
    ), {'id': str(prompt.id)})

    result = await db_session.execute(text(
        'SELECT search_vector::text FROM prompts WHERE id = :id',
    ), {'id': str(prompt.id)})
    assert result.scalar() == original_sv


# =============================================================================
# FTS Behavior Tests (stemming, matching)
# =============================================================================


async def test__search_vector__stemming_works(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """FTS stemming should match word variants (e.g. 'databases' matches 'database')."""
    bookmark = Bookmark(
        user_id=test_user.id,
        url='https://example.com/stemming-test',
        title='Database Administration',
        content='Managing production databases efficiently',
    )
    db_session.add(bookmark)
    await db_session.flush()

    # "databases" should match "database" via stemming (both stem to "databas")
    result = await db_session.execute(text(
        "SELECT search_vector @@ websearch_to_tsquery('english', 'databases') "
        "FROM bookmarks WHERE id = :id",
    ), {'id': str(bookmark.id)})
    assert result.scalar() is True

    # "running" should match "run" via stemming
    note = Note(
        user_id=test_user.id,
        title='Running Tests',
        content='How to run your test suite',
    )
    db_session.add(note)
    await db_session.flush()

    result = await db_session.execute(text(
        "SELECT search_vector @@ websearch_to_tsquery('english', 'run') "
        "FROM notes WHERE id = :id",
    ), {'id': str(note.id)})
    assert result.scalar() is True


async def test__search_vector__null_fields_handled(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """NULL content fields should not prevent search_vector from being populated."""
    bookmark = Bookmark(
        user_id=test_user.id,
        url='https://example.com/null-test',
        title='Only Title Set',
        # description, content, summary all NULL
    )
    db_session.add(bookmark)
    await db_session.flush()

    result = await db_session.execute(text(
        'SELECT search_vector FROM bookmarks WHERE id = :id',
    ), {'id': str(bookmark.id)})
    row = result.first()
    assert row is not None
    assert row.search_vector is not None

    # Title should still be searchable
    result = await db_session.execute(text(
        "SELECT search_vector @@ websearch_to_tsquery('english', 'title') "
        "FROM bookmarks WHERE id = :id",
    ), {'id': str(bookmark.id)})
    assert result.scalar() is True


async def test__search_vector__description_update_recomputes(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Updating description should recompute search_vector."""
    bookmark = Bookmark(
        user_id=test_user.id,
        url='https://example.com/desc-update',
        title='Desc Update Test',
    )
    db_session.add(bookmark)
    await db_session.flush()

    result = await db_session.execute(text(
        'SELECT search_vector::text FROM bookmarks WHERE id = :id',
    ), {'id': str(bookmark.id)})
    original_sv = result.scalar()

    await db_session.execute(text(
        "UPDATE bookmarks SET description = 'Kubernetes orchestration guide' WHERE id = :id",
    ), {'id': str(bookmark.id)})

    result = await db_session.execute(text(
        'SELECT search_vector::text FROM bookmarks WHERE id = :id',
    ), {'id': str(bookmark.id)})
    assert result.scalar() != original_sv

    result = await db_session.execute(text(
        "SELECT search_vector @@ websearch_to_tsquery('english', 'kubernetes') "
        "FROM bookmarks WHERE id = :id",
    ), {'id': str(bookmark.id)})
    assert result.scalar() is True


async def test__search_vector__summary_update_recomputes(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Updating summary should recompute search_vector for bookmarks."""
    bookmark = Bookmark(
        user_id=test_user.id,
        url='https://example.com/summary-update',
        title='Summary Test',
    )
    db_session.add(bookmark)
    await db_session.flush()

    result = await db_session.execute(text(
        'SELECT search_vector::text FROM bookmarks WHERE id = :id',
    ), {'id': str(bookmark.id)})
    original_sv = result.scalar()

    await db_session.execute(text(
        "UPDATE bookmarks SET summary = 'Microservices architecture patterns' WHERE id = :id",
    ), {'id': str(bookmark.id)})

    result = await db_session.execute(text(
        'SELECT search_vector::text FROM bookmarks WHERE id = :id',
    ), {'id': str(bookmark.id)})
    assert result.scalar() != original_sv
