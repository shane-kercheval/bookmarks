"""NoteVersion model for storing note version history (future use)."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class NoteVersion(Base):
    """
    NoteVersion model - schema for future version history.

    Not actively used yet. Designed for diff-based storage:
    - Every Nth save (e.g., 10) = full snapshot
    - In-between saves = diff only (using diff-match-patch library)
    - To reconstruct version X: find nearest prior snapshot, apply diffs forward

    Version semantics:
    - Note.content is always the live/current version
    - Note.version starts at 1 for new notes
    - Version 1 has NO NoteVersion row - the Note itself is version 1
    - When a note is saved: create NoteVersion row with diff, then update Note
    """

    __tablename__ = "note_versions"
    __table_args__ = (
        # Composite index for the primary query pattern:
        # SELECT * FROM note_versions WHERE note_id = ? ORDER BY version
        Index("ix_note_versions_note_id_version", "note_id", "version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    note_id: Mapped[int] = mapped_column(
        ForeignKey("notes.id", ondelete="CASCADE"),
    )
    version: Mapped[int] = mapped_column(nullable=False)
    version_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="'snapshot' for full content, 'diff' for diff-match-patch delta",
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Full content if snapshot, diff if diff type",
    )
    saved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        nullable=False,
    )
