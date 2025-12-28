"""
Base service class for entity CRUD operations.

Provides shared logic for Bookmark, Note, and future entity types (Todo).
Entity-specific behavior is defined via abstract methods and class attributes.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Generic, Literal, Protocol, TypeVar

from sqlalchemy import Table, exists, func, select
from sqlalchemy.sql import Select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, selectinload

from models.tag import Tag
from schemas.bookmark import validate_and_normalize_tags
from services.exceptions import InvalidStateError
from services.utils import build_tag_filter_from_expression, escape_ilike


class TaggableEntity(Protocol):
    """Protocol defining the interface for entities that support tagging and soft-delete."""

    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime
    deleted_at: datetime | None
    archived_at: datetime | None
    tag_objects: list

    @property
    def is_archived(self) -> bool:
        """Check if entity is currently archived."""
        ...


T = TypeVar("T", bound=TaggableEntity)


class BaseEntityService(ABC, Generic[T]):
    """
    Abstract base class for entity CRUD operations.

    Subclasses must define:
    - model: The SQLAlchemy model class
    - junction_table: The tag junction table (e.g., bookmark_tags)
    - entity_name: Human-readable name for error messages (e.g., "Bookmark")

    Subclasses must implement:
    - _build_text_search_filter(): Entity-specific search fields
    - _get_sort_columns(): Entity-specific sort column mapping

    Note: create() is NOT in base class - it has entity-specific logic
    (e.g., bookmark URL uniqueness checks).
    """

    # Class attributes to be defined by subclasses
    model: type[T]
    junction_table: Table
    entity_name: str  # For error messages: "Bookmark", "Note", etc.

    # --- Helper Methods ---

    def _get_junction_entity_id_column(self) -> InstrumentedAttribute:
        """Get the entity ID column from the junction table (e.g., bookmark_id, note_id)."""
        junction_columns = [c.name for c in self.junction_table.columns if c.name != "tag_id"]
        return self.junction_table.c[junction_columns[0]]

    async def _refresh_with_tags(self, db: AsyncSession, entity: T) -> None:
        """Refresh entity and eagerly load tag_objects relationship."""
        await db.refresh(entity)
        await db.refresh(entity, attribute_names=["tag_objects"])

    # --- Abstract Methods (entity-specific) ---

    @abstractmethod
    def _build_text_search_filter(self, pattern: str) -> list:
        """
        Build text search filter for entity-specific fields.

        Args:
            pattern: The ILIKE pattern (already escaped and wrapped with %).

        Returns:
            List of SQLAlchemy OR conditions for text search.

        Example for Bookmark:
            return [or_(
                Bookmark.title.ilike(pattern),
                Bookmark.description.ilike(pattern),
                Bookmark.url.ilike(pattern),
            )]
        """
        ...

    @abstractmethod
    def _get_sort_columns(self) -> dict[str, InstrumentedAttribute]:
        """
        Get mapping of sort field names to SQLAlchemy columns.

        Returns:
            Dict mapping sort_by parameter values to columns.

        Example for Bookmark:
            return {
                "created_at": Bookmark.created_at,
                "title": func.coalesce(Bookmark.title, Bookmark.url),
                ...
            }
        """
        ...

    # --- Common CRUD Operations ---

    async def get(
        self,
        db: AsyncSession,
        user_id: int,
        entity_id: int,
        include_deleted: bool = False,
        include_archived: bool = False,
    ) -> T | None:
        """
        Get an entity by ID, scoped to user.

        Args:
            db: Database session.
            user_id: User ID to scope the entity.
            entity_id: ID of the entity to retrieve.
            include_deleted: If True, include soft-deleted entities. Default False.
            include_archived: If True, include archived entities. Default False.

        Returns:
            The entity if found and matches filters, None otherwise.
        """
        query = (
            select(self.model)
            .options(selectinload(self.model.tag_objects))
            .where(
                self.model.id == entity_id,
                self.model.user_id == user_id,
            )
        )

        if not include_deleted:
            query = query.where(self.model.deleted_at.is_(None))
        if not include_archived:
            query = query.where(~self.model.is_archived)

        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def search(
        self,
        db: AsyncSession,
        user_id: int,
        query: str | None = None,
        tags: list[str] | None = None,
        tag_match: Literal["all", "any"] = "all",
        sort_by: Literal[
            "created_at", "updated_at", "last_used_at", "title", "archived_at", "deleted_at",
        ] = "created_at",
        sort_order: Literal["asc", "desc"] = "desc",
        offset: int = 0,
        limit: int = 50,
        view: Literal["active", "archived", "deleted"] = "active",
        filter_expression: dict | None = None,
    ) -> tuple[list[T], int]:
        """
        Search and filter entities for a user with pagination.

        Args:
            db: Database session.
            user_id: User ID to scope entities.
            query: Text search (uses entity-specific _build_text_search_filter).
            tags: Filter by tags (normalized to lowercase).
            tag_match: "all" (AND) or "any" (OR) for tag matching.
            sort_by: Field to sort by (entity-specific via _get_sort_columns).
            sort_order: Sort direction.
            offset: Pagination offset.
            limit: Pagination limit.
            view: "active", "archived", or "deleted".
            filter_expression: Optional ContentList filter expression.

        Returns:
            Tuple of (list of entities, total count).
        """
        # Base query scoped to user with eager loading of tags
        base_query = (
            select(self.model)
            .options(selectinload(self.model.tag_objects))
            .where(self.model.user_id == user_id)
        )

        # Apply view filter
        base_query = self._apply_view_filter(base_query, view)

        # Apply text search filter
        if query:
            escaped_query = escape_ilike(query)
            search_pattern = f"%{escaped_query}%"
            text_filters = self._build_text_search_filter(search_pattern)
            for text_filter in text_filters:
                base_query = base_query.where(text_filter)

        # Apply filter expression (from ContentList)
        if filter_expression is not None:
            filter_clauses = build_tag_filter_from_expression(
                filter_expression=filter_expression,
                user_id=user_id,
                junction_table=self.junction_table,
                entity_id_column=self.model.id,
            )
            for clause in filter_clauses:
                base_query = base_query.where(clause)

        # Apply tag filter
        if tags:
            base_query = self._apply_tag_filter(base_query, user_id, tags, tag_match)

        # Get total count before pagination
        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply sorting with tiebreakers
        base_query = self._apply_sorting(base_query, sort_by, sort_order)

        # Apply pagination
        base_query = base_query.offset(offset).limit(limit)

        # Execute query
        result = await db.execute(base_query)
        entities = list(result.scalars().all())

        return entities, total

    async def delete(
        self,
        db: AsyncSession,
        user_id: int,
        entity_id: int,
        permanent: bool = False,
    ) -> bool:
        """
        Delete an entity (soft or permanent).

        Args:
            db: Database session.
            user_id: User ID to scope the entity.
            entity_id: ID of the entity to delete.
            permanent: If False, soft delete. If True, permanent delete.

        Returns:
            True if deleted, False if not found.
        """
        entity = await self.get(
            db, user_id, entity_id, include_deleted=permanent, include_archived=True,
        )
        if entity is None:
            return False

        if permanent:
            await db.delete(entity)
        else:
            entity.deleted_at = func.now()
            await db.flush()

        return True

    async def restore(
        self,
        db: AsyncSession,
        user_id: int,
        entity_id: int,
    ) -> T | None:
        """
        Restore a soft-deleted entity to active state.

        Clears both deleted_at AND archived_at timestamps.

        Args:
            db: Database session.
            user_id: User ID to scope the entity.
            entity_id: ID of the entity to restore.

        Returns:
            The restored entity, or None if not found.

        Raises:
            InvalidStateError: If the entity is not deleted.
        """
        # Find the entity (must be deleted)
        result = await db.execute(
            select(self.model)
            .options(selectinload(self.model.tag_objects))
            .where(
                self.model.id == entity_id,
                self.model.user_id == user_id,
                self.model.deleted_at.is_not(None),
            ),
        )
        entity = result.scalar_one_or_none()

        if entity is None:
            # Check if entity exists but is not deleted
            non_deleted = await self.get(db, user_id, entity_id, include_archived=True)
            if non_deleted is not None:
                raise InvalidStateError(f"{self.entity_name} is not deleted")
            return None

        # Restore: clear both deleted_at and archived_at
        entity.deleted_at = None
        entity.archived_at = None
        await db.flush()
        await self._refresh_with_tags(db, entity)
        return entity

    async def archive(
        self,
        db: AsyncSession,
        user_id: int,
        entity_id: int,
    ) -> T | None:
        """
        Archive an entity by setting archived_at timestamp.

        This operation is idempotent.

        Args:
            db: Database session.
            user_id: User ID to scope the entity.
            entity_id: ID of the entity to archive.

        Returns:
            The archived entity, or None if not found.
        """
        entity = await self.get(db, user_id, entity_id, include_archived=True)
        if entity is None:
            return None

        if not entity.is_archived:
            entity.archived_at = func.now()
            await db.flush()
            await db.refresh(entity)

        return entity

    async def unarchive(
        self,
        db: AsyncSession,
        user_id: int,
        entity_id: int,
    ) -> T | None:
        """
        Unarchive an entity by clearing archived_at timestamp.

        Args:
            db: Database session.
            user_id: User ID to scope the entity.
            entity_id: ID of the entity to unarchive.

        Returns:
            The unarchived entity, or None if not found.

        Raises:
            InvalidStateError: If the entity is not archived.
        """
        # Find archived entity
        result = await db.execute(
            select(self.model)
            .options(selectinload(self.model.tag_objects))
            .where(
                self.model.id == entity_id,
                self.model.user_id == user_id,
                self.model.deleted_at.is_(None),
                self.model.is_archived,
            ),
        )
        entity = result.scalar_one_or_none()

        if entity is None:
            # Check if entity exists but is not archived
            non_archived = await self.get(db, user_id, entity_id)
            if non_archived is not None:
                raise InvalidStateError(f"{self.entity_name} is not archived")
            return None

        entity.archived_at = None
        await db.flush()
        await self._refresh_with_tags(db, entity)
        return entity

    async def track_usage(
        self,
        db: AsyncSession,
        user_id: int,
        entity_id: int,
    ) -> bool:
        """
        Update last_used_at timestamp for an entity.

        Works on active, archived, and deleted entities.

        Args:
            db: Database session.
            user_id: User ID to scope the entity.
            entity_id: ID of the entity to track usage for.

        Returns:
            True if updated, False if not found.
        """
        entity = await self.get(
            db, user_id, entity_id, include_archived=True, include_deleted=True,
        )
        if entity is None:
            return False

        entity.last_used_at = func.clock_timestamp()
        await db.flush()
        return True

    # --- Private Helper Methods ---

    def _apply_view_filter(
        self,
        query: Select[tuple[T]],
        view: Literal["active", "archived", "deleted"],
    ) -> Select[tuple[T]]:
        """Apply view filter (active/archived/deleted) to query."""
        if view == "active":
            return query.where(
                self.model.deleted_at.is_(None),
                ~self.model.is_archived,
            )
        if view == "archived":
            return query.where(
                self.model.deleted_at.is_(None),
                self.model.is_archived,
            )
        # deleted
        return query.where(self.model.deleted_at.is_not(None))

    def _apply_tag_filter(
        self,
        query: Select[tuple[T]],
        user_id: int,
        tags: list[str],
        tag_match: Literal["all", "any"],
    ) -> Select[tuple[T]]:
        """Apply tag filter to query."""
        normalized_tags = validate_and_normalize_tags(tags)
        if not normalized_tags:
            return query

        junction_entity_id_col = self._get_junction_entity_id_column()

        if tag_match == "all":
            # Must have ALL specified tags
            for tag_name in normalized_tags:
                subq = (
                    select(junction_entity_id_col)
                    .join(Tag, self.junction_table.c.tag_id == Tag.id)
                    .where(
                        junction_entity_id_col == self.model.id,
                        Tag.name == tag_name,
                        Tag.user_id == user_id,
                    )
                )
                query = query.where(exists(subq))
        else:
            # Must have ANY of the specified tags
            subq = (
                select(junction_entity_id_col)
                .join(Tag, self.junction_table.c.tag_id == Tag.id)
                .where(
                    junction_entity_id_col == self.model.id,
                    Tag.name.in_(normalized_tags),
                    Tag.user_id == user_id,
                )
            )
            query = query.where(exists(subq))

        return query

    def _apply_sorting(
        self,
        query: Select[tuple[T]],
        sort_by: str,
        sort_order: Literal["asc", "desc"],
    ) -> Select[tuple[T]]:
        """Apply sorting with tiebreakers (created_at, then id)."""
        sort_columns = self._get_sort_columns()
        sort_column = sort_columns.get(sort_by, self.model.created_at)

        if sort_order == "desc":
            return query.order_by(
                sort_column.desc(),
                self.model.created_at.desc(),
                self.model.id.desc(),
            )
        return query.order_by(
            sort_column.asc(),
            self.model.created_at.asc(),
            self.model.id.asc(),
        )
