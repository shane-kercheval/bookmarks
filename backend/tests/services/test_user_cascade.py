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
from models.content_list import ContentList
from models.note import Note
from models.note_version import NoteVersion
from models.tag import Tag, bookmark_tags, note_tags
from models.user import User
from models.user_settings import UserSettings


async def test__user_delete__cascades_to_all_user_data(
    db_session: AsyncSession,
) -> None:
    """
    Comprehensive test: deleting a user removes ALL associated data.

    This test creates a user with:
    - Multiple bookmarks (active, archived, deleted)
    - Multiple notes (active, archived, deleted)
    - Multiple tags associated with bookmarks and notes
    - Note versions (for testing cascade from notes)
    - API tokens
    - User settings
    - Content lists

    Then verifies that deleting the user removes ALL of this data,
    including junction table entries (bookmark_tags, note_tags).
    """
    # ==========================================================================
    # Setup: Create a user with data across all tables
    # ==========================================================================

    user = User(auth0_id="cascade-test-user", email="cascade@example.com")
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

    # Create a note version (to test cascade from note deletion)
    note_version = NoteVersion(
        note_id=note_active.id,
        version=1,
        version_type="snapshot",
        content="Initial snapshot content",
    )
    db_session.add(note_version)
    await db_session.flush()
    note_version_id = note_version.id

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
        tab_order=["all", "archived"],
    )
    db_session.add(settings)
    await db_session.flush()

    # Create content lists
    list1 = ContentList(
        user_id=user_id,
        name="Work",
        content_types=["bookmark", "note"],
        filter_expression={"groups": [{"tags": ["python"]}], "group_operator": "OR"},
    )
    list2 = ContentList(
        user_id=user_id,
        name="Personal",
        content_types=["bookmark"],
        filter_expression={"groups": [{"tags": ["web"]}], "group_operator": "OR"},
    )
    db_session.add_all([list1, list2])
    await db_session.flush()
    list_ids = [list1.id, list2.id]

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

    # Verify note versions exist
    result = await db_session.execute(
        select(NoteVersion).where(NoteVersion.id == note_version_id),
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

    # Verify content lists exist
    result = await db_session.execute(
        select(ContentList).where(ContentList.id.in_(list_ids)),
    )
    assert len(result.scalars().all()) == 2

    # ==========================================================================
    # Action: Delete the user
    # ==========================================================================

    await db_session.delete(user)
    await db_session.flush()

    # ==========================================================================
    # Verify: ALL user data is deleted
    # ==========================================================================

    # User should be gone
    result = await db_session.execute(
        select(User).where(User.id == user_id),
    )
    assert result.scalar_one_or_none() is None

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

    # Note versions should be gone
    result = await db_session.execute(
        select(NoteVersion).where(NoteVersion.id == note_version_id),
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

    # Content lists should be gone
    result = await db_session.execute(
        select(ContentList).where(ContentList.id.in_(list_ids)),
    )
    assert len(result.scalars().all()) == 0


async def test__user_delete__does_not_affect_other_users_data(
    db_session: AsyncSession,
) -> None:
    """
    Verify that deleting one user does not affect another user's data.

    This is a sanity check to ensure cascade deletes are properly scoped
    to the deleted user only.
    """
    # Create two users
    user1 = User(auth0_id="user1-cascade", email="user1@example.com")
    user2 = User(auth0_id="user2-cascade", email="user2@example.com")
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
