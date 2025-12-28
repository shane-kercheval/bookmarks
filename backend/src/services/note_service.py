"""Service layer for note CRUD operations."""
import logging

from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from models.note import Note
from models.tag import note_tags
from schemas.note import NoteCreate, NoteUpdate
from services.base_entity_service import BaseEntityService
from services.tag_service import get_or_create_tags, update_note_tags

logger = logging.getLogger(__name__)


class NoteService(BaseEntityService[Note]):
    """
    Note service with full CRUD operations.

    Extends BaseEntityService with note-specific:
    - Text search fields (title, description, content)
    - Sort columns (notes always have title, no fallback needed)
    """

    model = Note
    junction_table = note_tags
    entity_name = "Note"

    def _build_text_search_filter(self, pattern: str) -> list:
        """Build text search filter for note fields."""
        return [
            or_(
                Note.title.ilike(pattern),
                Note.description.ilike(pattern),
                Note.content.ilike(pattern),
            ),
        ]

    def _get_sort_columns(self) -> dict[str, InstrumentedAttribute]:
        """Get sort columns for notes."""
        return {
            "created_at": Note.created_at,
            "updated_at": Note.updated_at,
            "last_used_at": Note.last_used_at,
            "title": Note.title,
            "archived_at": Note.archived_at,
            "deleted_at": Note.deleted_at,
        }

    async def create(
        self,
        db: AsyncSession,
        user_id: int,
        data: NoteCreate,
    ) -> Note:
        """
        Create a new note for a user.

        Args:
            db: Database session.
            user_id: User ID to create the note for.
            data: Note creation data.

        Returns:
            The created note.
        """
        tag_objects = await get_or_create_tags(db, user_id, data.tags)
        note = Note(
            user_id=user_id,
            title=data.title,
            description=data.description,
            content=data.content,
            archived_at=data.archived_at,
        )
        note.tag_objects = tag_objects
        db.add(note)
        await db.flush()
        await db.refresh(note)
        await db.refresh(note, attribute_names=["tag_objects"])
        # Set last_used_at to match created_at for "never viewed" detection
        note.last_used_at = note.created_at
        await db.flush()
        return note

    async def update(
        self,
        db: AsyncSession,
        user_id: int,
        note_id: int,
        data: NoteUpdate,
    ) -> Note | None:
        """
        Update a note.

        Args:
            db: Database session.
            user_id: User ID to scope the note.
            note_id: ID of the note to update.
            data: Update data.

        Returns:
            The updated note, or None if not found.
        """
        note = await self.get(db, user_id, note_id, include_archived=True)
        if note is None:
            return None

        update_data = data.model_dump(exclude_unset=True)
        new_tags = update_data.pop("tags", None)

        for field, value in update_data.items():
            setattr(note, field, value)

        if new_tags is not None:
            await update_note_tags(db, note, new_tags)

        note.updated_at = func.clock_timestamp()

        await db.flush()
        await self._refresh_with_tags(db, note)
        return note

