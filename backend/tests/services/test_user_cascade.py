"""
Comprehensive test for user deletion cascade behavior.

This test verifies that when a user is deleted, ALL of their data is properly
cascade-deleted at both the ORM and database levels.
"""
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.api_token import ApiToken
from models.bookmark import Bookmark
from models.content_filter import ContentFilter
from models.content_history import ActionType, ContentHistory, EntityType
from models.content_relationship import ContentRelationship
from models.deleted_identity import DeletedIdentity
from models.filter_group import FilterGroup
from models.note import Note
from models.prompt import Prompt
from models.tag import Tag, bookmark_tags, filter_group_tags, note_tags, prompt_tags
from models.user import User
from core.tier_limits import Tier
from models.user_consent import UserConsent
from models.user_settings import UserSettings
from services.user_service import delete_user_by_external_auth_id


async def test__user_delete__cascades_to_all_user_data(
    db_session: AsyncSession,
) -> None:
    """
    Comprehensive test: deleting a user removes ALL associated data.

    Exercises the production deletion path — `delete_user_by_external_auth_id`
    (the webhook's service call), not a bare `session.delete(user)` — against a
    user with data across **every** owned table:
    - Multiple bookmarks (active, archived, deleted) with tags
    - Multiple notes (active, archived, deleted) with tags
    - A prompt with tags (prompt_tags junction)
    - Tags associated with bookmarks, notes, prompts, and a filter group
    - A content filter with a group referencing a tag (the filter_group_tags
      RESTRICT edge — the one FK a single-statement cascade can't resolve)
    - A content relationship
    - Content history, API tokens, user settings, user consent

    Then verifies the user, all data, and every junction entry are gone, and a
    tombstone was written.
    """
    # ==========================================================================
    # Setup: Create a user with data across all tables
    # ==========================================================================

    user = User(
        external_auth_id="user_cascade_all",
        email="cascade@example.com",
        tier=Tier.FREE.value,
    )
    db_session.add(user)
    await db_session.flush()
    user_id = user.id

    # Create tags
    tag1 = Tag(user_id=user_id, name="python")
    tag2 = Tag(user_id=user_id, name="web")
    tag3 = Tag(user_id=user_id, name="orphan-tag")  # Tag with no bookmarks
    db_session.add_all([tag1, tag2, tag3])
    await db_session.flush()
    tag_ids = [tag1.id, tag2.id, tag3.id]

    # Create bookmarks with tags
    bookmark_active = Bookmark(user_id=user_id, url="https://active.com/")
    bookmark_active.tag_objects = [tag1, tag2]

    bookmark_archived = Bookmark(
        user_id=user_id,
        url="https://archived.com/",
        archived_at=datetime.now(UTC),
    )
    bookmark_archived.tag_objects = [tag1]

    bookmark_deleted = Bookmark(
        user_id=user_id,
        url="https://deleted.com/",
        deleted_at=datetime.now(UTC),
    )
    bookmark_deleted.tag_objects = [tag2]

    db_session.add_all([bookmark_active, bookmark_archived, bookmark_deleted])
    await db_session.flush()
    bookmark_ids = [bookmark_active.id, bookmark_archived.id, bookmark_deleted.id]

    # Create notes with tags
    note_active = Note(user_id=user_id, title="Active Note", content="# Test content")
    note_active.tag_objects = [tag1, tag2]

    note_archived = Note(
        user_id=user_id,
        title="Archived Note",
        archived_at=datetime.now(UTC),
    )
    note_archived.tag_objects = [tag1]

    note_deleted = Note(
        user_id=user_id,
        title="Deleted Note",
        deleted_at=datetime.now(UTC),
    )
    note_deleted.tag_objects = [tag2]

    db_session.add_all([note_active, note_archived, note_deleted])
    await db_session.flush()
    note_ids = [note_active.id, note_archived.id, note_deleted.id]

    # Create content history records (to test cascade from user deletion)
    content_history = ContentHistory(
        user_id=user_id,
        entity_type=EntityType.NOTE,
        entity_id=note_active.id,
        action=ActionType.CREATE,
        version=1,
        content_snapshot="Initial snapshot content",
        metadata_snapshot={"title": "Active Note"},
        source="web",
        auth_type="session",
    )
    db_session.add(content_history)
    await db_session.flush()
    content_history_id = content_history.id

    # Create API tokens
    token1 = ApiToken(
        user_id=user_id,
        name="Test Token 1",
        token_hash="hash1",
        token_prefix="bm_test1",
    )
    token2 = ApiToken(
        user_id=user_id,
        name="Test Token 2",
        token_hash="hash2",
        token_prefix="bm_test2",
    )
    db_session.add_all([token1, token2])
    await db_session.flush()
    token_ids = [token1.id, token2.id]

    # Create user settings (uses user_id as PK, no separate id)
    settings = UserSettings(
        user_id=user_id,
        sidebar_order={"version": 1, "items": [{"type": "builtin", "key": "all"}]},
    )
    db_session.add(settings)
    await db_session.flush()

    # Create content filters (groups are stored separately, not as filter_expression)
    list1 = ContentFilter(
        user_id=user_id,
        name="Work",
        content_types=["bookmark", "note"],
        group_operator="OR",
    )
    list2 = ContentFilter(
        user_id=user_id,
        name="Personal",
        content_types=["bookmark"],
        group_operator="OR",
    )
    db_session.add_all([list1, list2])
    await db_session.flush()
    filter_ids = [list1.id, list2.id]

    # Filter group referencing a tag — the filter_group_tags.tag_id RESTRICT
    # edge that a single-statement DB cascade can't resolve (the service's
    # set-based content_filters pre-delete is what makes this deletable).
    filter_group = FilterGroup(filter_id=list1.id, position=0)
    filter_group.tag_objects = [tag1]
    db_session.add(filter_group)
    await db_session.flush()
    filter_group_id = filter_group.id

    # Prompt with tags (prompt_tags junction)
    prompt = Prompt(user_id=user_id, name="test-prompt", content="Hello {{ name }}")
    prompt.tag_objects = [tag1, tag3]
    db_session.add(prompt)
    await db_session.flush()
    prompt_id = prompt.id

    # Content relationship (bookmark -> note)
    relationship = ContentRelationship(
        user_id=user_id,
        source_type="bookmark",
        source_id=bookmark_active.id,
        target_type="note",
        target_id=note_active.id,
        relationship_type="related",
    )
    db_session.add(relationship)
    await db_session.flush()
    relationship_id = relationship.id

    # User consent
    consent = UserConsent(
        user_id=user_id,
        consented_at=datetime.now(UTC),
        privacy_policy_version="2025-01-01",
        terms_of_service_version="2025-01-01",
    )
    db_session.add(consent)
    await db_session.flush()

    # ==========================================================================
    # Verify: All data exists before deletion
    # ==========================================================================

    # Verify bookmarks exist
    result = await db_session.execute(
        select(Bookmark).where(Bookmark.id.in_(bookmark_ids)),
    )
    assert len(result.scalars().all()) == 3

    # Verify tags exist
    result = await db_session.execute(
        select(Tag).where(Tag.id.in_(tag_ids)),
    )
    assert len(result.scalars().all()) == 3

    # Verify bookmark_tags junction entries exist
    result = await db_session.execute(
        select(bookmark_tags).where(bookmark_tags.c.bookmark_id.in_(bookmark_ids)),
    )
    assert len(result.fetchall()) == 4  # 2 + 1 + 1 = 4 associations

    # Verify notes exist
    result = await db_session.execute(
        select(Note).where(Note.id.in_(note_ids)),
    )
    assert len(result.scalars().all()) == 3

    # Verify note_tags junction entries exist
    result = await db_session.execute(
        select(note_tags).where(note_tags.c.note_id.in_(note_ids)),
    )
    assert len(result.fetchall()) == 4  # 2 + 1 + 1 = 4 associations

    # Verify content history records exist
    result = await db_session.execute(
        select(ContentHistory).where(ContentHistory.id == content_history_id),
    )
    assert result.scalar_one_or_none() is not None

    # Verify API tokens exist
    result = await db_session.execute(
        select(ApiToken).where(ApiToken.id.in_(token_ids)),
    )
    assert len(result.scalars().all()) == 2

    # Verify settings exist
    result = await db_session.execute(
        select(UserSettings).where(UserSettings.user_id == user_id),
    )
    assert result.scalar_one_or_none() is not None

    # Verify content filters exist
    result = await db_session.execute(
        select(ContentFilter).where(ContentFilter.id.in_(filter_ids)),
    )
    assert len(result.scalars().all()) == 2

    # ==========================================================================
    # Action: Delete the user via the production service path
    # ==========================================================================

    deletion = await delete_user_by_external_auth_id(db_session, "user_cascade_all")
    assert deletion.deleted is True
    await db_session.flush()

    # ==========================================================================
    # Verify: ALL user data is deleted
    # ==========================================================================

    # User should be gone
    result = await db_session.execute(
        select(User).where(User.id == user_id),
    )
    assert result.scalar_one_or_none() is None

    # A tombstone was written carrying both identity columns
    tombstone = (await db_session.execute(
        select(DeletedIdentity).where(
            DeletedIdentity.external_auth_id == "user_cascade_all",
        ),
    )).scalar_one()
    assert tombstone.external_auth_id == "user_cascade_all"

    # Bookmarks should be gone
    result = await db_session.execute(
        select(Bookmark).where(Bookmark.id.in_(bookmark_ids)),
    )
    assert len(result.scalars().all()) == 0

    # Tags should be gone
    result = await db_session.execute(
        select(Tag).where(Tag.id.in_(tag_ids)),
    )
    assert len(result.scalars().all()) == 0

    # Junction table entries should be gone (cascade from both bookmark and tag deletion)
    result = await db_session.execute(
        select(bookmark_tags).where(bookmark_tags.c.bookmark_id.in_(bookmark_ids)),
    )
    assert len(result.fetchall()) == 0

    # Notes should be gone
    result = await db_session.execute(
        select(Note).where(Note.id.in_(note_ids)),
    )
    assert len(result.scalars().all()) == 0

    # Note_tags junction entries should be gone
    result = await db_session.execute(
        select(note_tags).where(note_tags.c.note_id.in_(note_ids)),
    )
    assert len(result.fetchall()) == 0

    # Content history records should be gone
    result = await db_session.execute(
        select(ContentHistory).where(ContentHistory.id == content_history_id),
    )
    assert result.scalar_one_or_none() is None

    # API tokens should be gone
    result = await db_session.execute(
        select(ApiToken).where(ApiToken.id.in_(token_ids)),
    )
    assert len(result.scalars().all()) == 0

    # Settings should be gone
    result = await db_session.execute(
        select(UserSettings).where(UserSettings.user_id == user_id),
    )
    assert result.scalar_one_or_none() is None

    # Content filters should be gone
    result = await db_session.execute(
        select(ContentFilter).where(ContentFilter.id.in_(filter_ids)),
    )
    assert len(result.scalars().all()) == 0

    # Filter group and its tag junction should be gone (the RESTRICT edge)
    result = await db_session.execute(
        select(FilterGroup).where(FilterGroup.id == filter_group_id),
    )
    assert result.scalar_one_or_none() is None
    result = await db_session.execute(
        select(filter_group_tags).where(
            filter_group_tags.c.group_id == filter_group_id,
        ),
    )
    assert len(result.fetchall()) == 0

    # Prompt and its tag junction should be gone
    result = await db_session.execute(
        select(Prompt).where(Prompt.id == prompt_id),
    )
    assert result.scalar_one_or_none() is None
    result = await db_session.execute(
        select(prompt_tags).where(prompt_tags.c.prompt_id == prompt_id),
    )
    assert len(result.fetchall()) == 0

    # Content relationship should be gone
    result = await db_session.execute(
        select(ContentRelationship).where(ContentRelationship.id == relationship_id),
    )
    assert result.scalar_one_or_none() is None

    # User consent should be gone
    result = await db_session.execute(
        select(UserConsent).where(UserConsent.user_id == user_id),
    )
    assert result.scalar_one_or_none() is None


async def test__user_delete__does_not_affect_other_users_data(
    db_session: AsyncSession,
) -> None:
    """
    Verify that deleting one user does not affect another user's data.

    This is a sanity check to ensure cascade deletes are properly scoped
    to the deleted user only.
    """
    # Create two users
    user1 = User(external_auth_id="user1-cascade", email="user1@example.com", tier=Tier.FREE.value)
    user2 = User(external_auth_id="user2-cascade", email="user2@example.com", tier=Tier.FREE.value)
    db_session.add_all([user1, user2])
    await db_session.flush()

    # Create data for both users
    tag1 = Tag(user_id=user1.id, name="user1-tag")
    tag2 = Tag(user_id=user2.id, name="user2-tag")
    db_session.add_all([tag1, tag2])
    await db_session.flush()

    bookmark1 = Bookmark(user_id=user1.id, url="https://user1.com/")
    bookmark1.tag_objects = [tag1]
    bookmark2 = Bookmark(user_id=user2.id, url="https://user2.com/")
    bookmark2.tag_objects = [tag2]
    db_session.add_all([bookmark1, bookmark2])
    await db_session.flush()

    note1 = Note(user_id=user1.id, title="User1 Note")
    note1.tag_objects = [tag1]
    note2 = Note(user_id=user2.id, title="User2 Note")
    note2.tag_objects = [tag2]
    db_session.add_all([note1, note2])
    await db_session.flush()

    user2_bookmark_id = bookmark2.id
    user2_note_id = note2.id
    user2_tag_id = tag2.id

    # Delete user1
    await db_session.delete(user1)
    await db_session.flush()

    # User2's data should be intact
    result = await db_session.execute(
        select(Bookmark).where(Bookmark.id == user2_bookmark_id),
    )
    assert result.scalar_one_or_none() is not None

    result = await db_session.execute(
        select(Note).where(Note.id == user2_note_id),
    )
    assert result.scalar_one_or_none() is not None

    result = await db_session.execute(
        select(Tag).where(Tag.id == user2_tag_id),
    )
    assert result.scalar_one_or_none() is not None
