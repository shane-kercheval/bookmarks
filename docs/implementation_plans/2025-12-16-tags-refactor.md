# Tags Refactor: Array to Normalized Table

## Overview

Refactor the tags system from PostgreSQL array columns to a normalized tags table with junction tables. This enables cross-entity tag consistency when notes, todos, and other entities are added in the future.

### Current State
- Tags stored as `ARRAY(String)` on `bookmarks` table
- GIN index for efficient querying
- Tags are isolated to bookmarks only

### Target State
- Central `tags` table with unique tags per user
- Junction tables (`bookmark_tags`, and future `note_tags`, `todo_tags`)
- Single source of truth for tag names
- Rename/merge operations affect all entities atomically

### Key Design Decisions
- Tag names remain lowercase alphanumeric with hyphens (existing validation unchanged)
- API response format for bookmarks stays compatible (returns tag names as string array)
- Tags are auto-created when first used (no separate "create tag" step required)
- Deleting a tag removes it from all entities

---

## Milestone 1: Database Schema Changes

### Goal
Create the new `tags` and `bookmark_tags` tables while keeping the existing `tags` array column temporarily for safe migration.

### Success Criteria
- `tags` table exists with proper constraints
- `bookmark_tags` junction table exists with foreign keys
- Existing functionality unchanged (old array column still in use)
- All migrations reversible

### Key Changes

**1. Create `tags` table:**
```python
class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Relationships
    user: Mapped["User"] = relationship(back_populates="tags")
    bookmarks: Mapped[list["Bookmark"]] = relationship(
        secondary="bookmark_tags", back_populates="tag_objects"
    )

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_tags_user_id_name"),
        Index("ix_tags_user_id", "user_id"),
    )
```

**2. Create `bookmark_tags` junction table:**
```python
bookmark_tags = Table(
    "bookmark_tags",
    Base.metadata,
    Column("bookmark_id", ForeignKey("bookmarks.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)
```

**3. Add relationship to Bookmark model (keep old `tags` column for now):**
```python
# Existing array column (temporary, will be removed in Milestone 6)
tags: Mapped[list[str]] = mapped_column(ARRAY(String), server_default="{}")

# New relationship
tag_objects: Mapped[list["Tag"]] = relationship(
    secondary="bookmark_tags", back_populates="bookmarks"
)
```

### Testing Strategy
- Migration applies cleanly (up and down)
- Existing bookmark CRUD still works with array column
- New tables exist with correct constraints
- Foreign key constraints enforced

### Dependencies
None

### Risk Factors
- Ensure migration is reversible
- Junction table naming convention (singular vs plural)

---

## Milestone 2: Data Migration

### Goal
Migrate existing tag data from the `tags` array column to the new normalized tables.

### Success Criteria
- All unique tags per user exist in `tags` table
- All bookmark-tag relationships preserved in `bookmark_tags`
- Tag counts match before and after migration
- Migration is idempotent (can run multiple times safely)

### Key Changes

**1. Create data migration script/migration:**

The migration should:
1. For each user, extract unique tags from all their bookmarks
2. Insert unique tags into `tags` table
3. Create `bookmark_tags` entries linking bookmarks to their tags

```python
# Pseudocode for migration logic
async def migrate_tags(db: AsyncSession):
    # Get all bookmarks with non-empty tags
    bookmarks = await db.execute(
        select(Bookmark).where(func.array_length(Bookmark.tags, 1) > 0)
    )

    # Track created tags per user: {(user_id, tag_name): tag_id}
    tag_cache = {}

    for bookmark in bookmarks.scalars():
        for tag_name in bookmark.tags:
            cache_key = (bookmark.user_id, tag_name)

            if cache_key not in tag_cache:
                # Create tag if not exists
                tag = Tag(user_id=bookmark.user_id, name=tag_name)
                db.add(tag)
                await db.flush()
                tag_cache[cache_key] = tag.id

            # Create junction entry
            await db.execute(
                bookmark_tags.insert().values(
                    bookmark_id=bookmark.id,
                    tag_id=tag_cache[cache_key]
                )
            )
```

**2. Add verification query:**
```sql
-- Verify tag counts match
SELECT user_id, COUNT(DISTINCT tag) as old_count
FROM bookmarks, unnest(tags) as tag
GROUP BY user_id;

SELECT user_id, COUNT(*) as new_count
FROM tags
GROUP BY user_id;
```

### Testing Strategy
- Test with empty database (no-op)
- Test with single user, single bookmark, single tag
- Test with multiple users (isolation)
- Test with duplicate tags across bookmarks (deduplication)
- Verify junction table entries match original arrays
- Test idempotency (running twice doesn't duplicate)

### Dependencies
- Milestone 1 complete

### Risk Factors
- Large datasets may need batching
- Case sensitivity (should already be normalized, but verify)

---

## Milestone 3: Backend Model and Schema Updates

### Goal
Update SQLAlchemy models and Pydantic schemas to support the new tag structure while maintaining API compatibility.

### Success Criteria
- Models use relationships instead of array column
- Schemas handle conversion between Tag objects and string arrays
- Existing API response format unchanged

### Key Changes

**1. Update Tag schemas (`backend/src/schemas/tag.py`):**
```python
class TagBase(BaseModel):
    name: str

class TagCreate(TagBase):
    pass

class TagResponse(TagBase):
    id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class TagRenameRequest(BaseModel):
    new_name: str = Field(..., pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")

# Keep existing TagCount and TagListResponse for GET /tags endpoint
```

**2. Update Bookmark model to use relationship for tag access:**
```python
@property
def tag_names(self) -> list[str]:
    """Return tag names as list of strings for API compatibility."""
    return [tag.name for tag in self.tag_objects]
```

**3. Update BookmarkResponse schema:**
```python
class BookmarkResponse(BookmarkBase):
    # ... existing fields ...
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode='before')
    @classmethod
    def extract_tag_names(cls, data):
        if hasattr(data, 'tag_objects'):
            data = dict(data.__dict__)
            data['tags'] = [tag.name for tag in data.get('tag_objects', [])]
        return data
```

### Testing Strategy
- Tag model CRUD operations
- Bookmark serialization includes tag names correctly
- Tag name validation (pattern matching)
- Relationship loading (avoid N+1 queries)

### Dependencies
- Milestone 2 complete

### Risk Factors
- Pydantic v2 `from_attributes` behavior with relationships
- Eager loading configuration to avoid N+1

---

## Milestone 4: Backend Service and API Updates

### Goal
Update bookmark service and tags router to use the new normalized tables.

### Success Criteria
- Bookmark CRUD operations use junction table
- Tag filtering works with new schema
- GET /tags returns data from tags table
- New tag management endpoints available (rename, delete)
- All existing tests pass

### Key Changes

**1. Update `bookmark_service.py`:**

Replace array operations with relationship operations:

```python
async def create_bookmark(
    db: AsyncSession,
    bookmark_data: BookmarkCreate,
    user_id: uuid.UUID,
) -> Bookmark:
    # ... existing validation ...

    # Get or create tags
    tag_objects = await get_or_create_tags(db, user_id, bookmark_data.tags)

    bookmark = Bookmark(
        user_id=user_id,
        url=str(bookmark_data.url),
        # ... other fields ...
    )
    bookmark.tag_objects = tag_objects

    db.add(bookmark)
    await db.commit()
    return bookmark

async def get_or_create_tags(
    db: AsyncSession,
    user_id: uuid.UUID,
    tag_names: list[str]
) -> list[Tag]:
    """Get existing tags or create new ones."""
    if not tag_names:
        return []

    normalized = validate_and_normalize_tags(tag_names)

    # Fetch existing tags
    result = await db.execute(
        select(Tag).where(
            Tag.user_id == user_id,
            Tag.name.in_(normalized)
        )
    )
    existing_tags = {tag.name: tag for tag in result.scalars()}

    # Create missing tags
    tags = []
    for name in normalized:
        if name in existing_tags:
            tags.append(existing_tags[name])
        else:
            new_tag = Tag(user_id=user_id, name=name)
            db.add(new_tag)
            tags.append(new_tag)

    await db.flush()
    return tags
```

**2. Update tag filtering in queries:**

```python
# Replace array containment with EXISTS subquery
if tags:
    if tag_match == "all":
        # Must have ALL specified tags
        for tag_name in normalized_tags:
            subq = (
                select(bookmark_tags.c.bookmark_id)
                .join(Tag)
                .where(
                    bookmark_tags.c.bookmark_id == Bookmark.id,
                    Tag.name == tag_name,
                    Tag.user_id == user_id
                )
            )
            base_query = base_query.where(subq.exists())
    else:
        # Must have ANY of the specified tags
        subq = (
            select(bookmark_tags.c.bookmark_id)
            .join(Tag)
            .where(
                bookmark_tags.c.bookmark_id == Bookmark.id,
                Tag.name.in_(normalized_tags),
                Tag.user_id == user_id
            )
        )
        base_query = base_query.where(subq.exists())
```

**3. Update `tags.py` router:**

```python
@router.get("/", response_model=TagListResponse)
async def get_tags(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> TagListResponse:
    """Get all tags for the current user with usage counts."""
    # Count from junction table, excluding deleted/archived bookmarks
    result = await db.execute(
        select(Tag.name, func.count(bookmark_tags.c.bookmark_id).label("count"))
        .join(bookmark_tags, Tag.id == bookmark_tags.c.tag_id)
        .join(Bookmark, bookmark_tags.c.bookmark_id == Bookmark.id)
        .where(
            Tag.user_id == current_user.id,
            Bookmark.deleted_at.is_(None),
            Bookmark.archived_at.is_(None),
        )
        .group_by(Tag.id, Tag.name)
        .order_by(func.count().desc(), Tag.name.asc())
    )

    tags = [TagCount(name=row.name, count=row.count) for row in result]
    return TagListResponse(tags=tags)

@router.patch("/{tag_name}", response_model=TagResponse)
async def rename_tag(
    tag_name: str,
    rename_request: TagRenameRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> TagResponse:
    """Rename a tag. Affects all bookmarks using this tag."""
    # Implementation: single UPDATE on tags table
    ...

@router.delete("/{tag_name}", status_code=204)
async def delete_tag(
    tag_name: str,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a tag. Removes from all bookmarks."""
    # Implementation: DELETE cascades via FK
    ...
```

**4. Update filter expressions for bookmark lists:**

Update `build_filter_from_expression` to use joins instead of array containment.

### Testing Strategy
- All existing bookmark tests should pass (API compatibility)
- All existing tag tests should pass
- New tests for:
  - Tag rename (verify bookmarks reflect new name)
  - Tag delete (verify removed from bookmarks)
  - Tag auto-creation on bookmark create
  - Tag filtering with joins
  - Filter expressions with new schema
- Performance test for tag filtering (compare with GIN index)

### Dependencies
- Milestone 3 complete

### Risk Factors
- Query performance without GIN index (add indexes on junction table)
- Bookmark list filter expressions need careful migration
- Ensure eager loading to avoid N+1 queries

---

## Milestone 5: Frontend Updates

### Goal
Update frontend to work with API changes and add a Tags management page accessible from the navigation menu.

### Success Criteria
- All existing tag functionality works (filtering, autocomplete, display)
- "Tags" menu item in navigation
- Tags management page with rename and delete functionality
- No regressions in bookmark filtering

### Key Changes

**1. Verify API compatibility:**

The bookmark API response format should be unchanged (tags as string array). Verify:
- `BookmarkCard` displays tags correctly
- `TagInput` autocomplete works
- `TagFilterInput` filtering works
- URL params for tag filters work

**2. Add Tags page (`frontend/src/pages/Tags.tsx`):**

Simple tag management interface:
- List all tags with usage counts (table or card layout)
- Inline rename: click tag name to edit, Enter to save, Escape to cancel
- Delete button with confirmation modal ("This will remove the tag from X bookmarks")
- Sort by name or count

**3. Add navigation menu item:**

Add "Tags" to the sidebar/nav menu alongside Bookmarks, Lists, Settings, etc.

**4. Add API functions (`frontend/src/services/api.ts` or new `tags.ts`):**

```typescript
export async function renameTag(oldName: string, newName: string): Promise<Tag> {
  const response = await api.patch(`/tags/${encodeURIComponent(oldName)}`, {
    new_name: newName
  })
  return response.data
}

export async function deleteTag(name: string): Promise<void> {
  await api.delete(`/tags/${encodeURIComponent(name)}`)
}
```

**5. Update tags store to support mutations:**

```typescript
interface TagsStore {
  tags: TagCount[]
  isLoading: boolean
  error: string | null
  fetchTags: () => Promise<void>
  renameTag: (oldName: string, newName: string) => Promise<void>
  deleteTag: (name: string) => Promise<void>
  clearError: () => void
}
```

**6. Update types if needed (`frontend/src/types.ts`):**

```typescript
// Existing TagCount should still work
export interface TagCount {
  name: string
  count: number
}

// For rename response
export interface Tag {
  id: string
  name: string
  created_at: string
}
```

### Testing Strategy
- Existing frontend tests pass
- New tests for Tags page:
  - Renders tag list with counts
  - Rename flow (click, edit, save)
  - Delete flow (click, confirm, removed from list)
  - Error handling (duplicate name, network error)
- Manual testing of tag workflows end-to-end

### Dependencies
- Milestone 4 complete

### Risk Factors
- Minimal if API response format unchanged
- Tag rename validation (can't rename to existing tag name)

---

## Milestone 6: Cleanup

### Goal
Remove the old `tags` array column from bookmarks and finalize the migration.

### Success Criteria
- Old `tags` column removed
- GIN index removed
- All code references to old column removed
- Database is clean

### Key Changes

**1. Create migration to drop old column:**
```python
def upgrade():
    op.drop_index("ix_bookmarks_tags_gin", table_name="bookmarks")
    op.drop_column("bookmarks", "tags")

def downgrade():
    op.add_column("bookmarks", sa.Column("tags", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False))
    op.create_index("ix_bookmarks_tags_gin", "bookmarks", ["tags"], postgresql_using="gin")
```

**2. Remove any remaining code references:**
- Remove `tags` column from Bookmark model
- Remove any migration compatibility code
- Update any raw SQL queries

**3. Add indexes for query performance:**
```python
# Ensure junction table has proper indexes (should exist from FK, but verify)
Index("ix_bookmark_tags_bookmark_id", bookmark_tags.c.bookmark_id)
Index("ix_bookmark_tags_tag_id", bookmark_tags.c.tag_id)
```

### Testing Strategy
- Migration applies cleanly
- All tests pass
- No references to old array column

### Dependencies
- Milestones 1-5 complete
- Verification that production data is migrated

### Risk Factors
- Irreversible in production (ensure data migration verified first)
- Coordinate deployment timing

---

## Summary

| Milestone | Focus | Risk |
|-----------|-------|------|
| 1 | Schema creation | Low |
| 2 | Data migration | Medium |
| 3 | Model/schema updates | Low |
| 4 | Service/API updates | Medium |
| 5 | Frontend + Tags page | Low |
| 6 | Cleanup | Low |

**Total scope:** Backend-heavy refactor with a new Tags management page in the frontend.

**Key risk:** Query performance after removing GIN index. Mitigation: proper indexes on junction table and benchmark testing in Milestone 4.
