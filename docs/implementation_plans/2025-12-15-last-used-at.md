# Implementation Plan: Last Used At Feature

## Overview

Add a `last_used_at` timestamp to bookmarks that tracks when a user last clicked/opened a bookmark. This enables sorting by "recently used" and provides usage context. Also add "Last Modified" sort option.

**Key Decisions:**
- `last_used_at` defaults to `created_at` on bookmark creation (new bookmarks appear at top of "Recently used")
- "Never clicked" can be detected by checking `last_used_at == created_at` if needed
- Archived/deleted bookmarks can still have usage tracked (users can click links from those views)
- Date displayed in BookmarkCard is dynamic based on current sort option

---

## Milestone 1: Backend - Database & Model

### Goal
Add the `last_used_at` column to the bookmarks table and update the model.

### Success Criteria
- Migration runs successfully
- `last_used_at` field exists on Bookmark model
- Existing tests continue to pass

### Key Changes

1. **Create Alembic migration** (`backend/src/db/migrations/versions/`)
   - Add `last_used_at` column: `DateTime(timezone=True)`, NOT NULL, indexed
   - Set default to `created_at` for existing rows: `UPDATE bookmarks SET last_used_at = created_at`
   - Add server default for new rows (or handle in service layer)

2. **Update Bookmark model** (`backend/src/models/bookmark.py`)
   ```python
   last_used_at: Mapped[datetime] = mapped_column(
       DateTime(timezone=True),
       nullable=False,
       index=True,
   )
   ```
   - Note: No default in model - set explicitly in `create_bookmark` service to match `created_at`

3. **Update BookmarkResponse schema** (`backend/src/schemas/bookmark.py`)
   ```python
   last_used_at: datetime
   ```

4. **Update create_bookmark service** (`backend/src/services/bookmark_service.py`)
   - After creating bookmark and before flush, set `bookmark.last_used_at = bookmark.created_at`
   - Or use `func.now()` for both to ensure they match

### Testing Strategy
- Run existing tests to ensure no regressions
- Verify migration applies cleanly
- Test that new bookmarks have `last_used_at == created_at`

### Dependencies
None

### Risk Factors
- Migration on production database (low risk - adding NOT NULL with default value)

---

## Milestone 2: Backend - Track Usage Endpoint

### Goal
Add endpoint to update `last_used_at` when a bookmark is clicked.

### Success Criteria
- `POST /bookmarks/{id}/track-usage` endpoint exists
- Endpoint updates `last_used_at` to current timestamp
- Returns 204 No Content (lightweight response for fire-and-forget)
- Works for active, archived, and deleted bookmarks
- Tests cover success and not-found cases

### Key Changes

1. **Add service function** (`backend/src/services/bookmark_service.py`)
   ```python
   async def track_bookmark_usage(
       db: AsyncSession,
       user_id: int,
       bookmark_id: int,
   ) -> bool:
       """
       Update last_used_at timestamp for a bookmark.

       Returns True if updated, False if not found.
       Works on active, archived, and deleted bookmarks.
       """
   ```
   - Follow the pattern from `archive_bookmark()` (lines 449-484)
   - Get bookmark with `include_archived=True` and `include_deleted=True`
   - Update timestamp with `func.now()`, flush, refresh

2. **Add router endpoint** (`backend/src/api/routers/bookmarks.py`)
   ```python
   @router.post("/{bookmark_id}/track-usage", status_code=204)
   async def track_bookmark_usage(
       bookmark_id: int,
       current_user: User = Depends(get_current_user),
       db: AsyncSession = Depends(get_async_session),
   ) -> None:
   ```
   - Return 204 No Content (no response body needed)
   - Return 404 if bookmark not found

### Testing Strategy
- Test successful usage tracking (verify timestamp updates)
- Test not-found returns 404
- Test idempotent behavior (calling multiple times works)
- Test that archived bookmarks can be tracked
- Test that deleted bookmarks can be tracked

### Dependencies
Milestone 1 (database changes)

### Risk Factors
- None - straightforward pattern following existing endpoints

---

## Milestone 3: Backend - Sort Options (Last Used & Last Modified)

### Goal
Add "last_used_at" and "updated_at" as sort options in `search_bookmarks`, with `created_at` as tiebreaker.

### Success Criteria
- Can sort by `last_used_at` ascending or descending
- Can sort by `updated_at` ascending or descending
- Ties broken by `created_at` (then `id` for deterministic ordering)
- Tests verify sorting works correctly

### Key Changes

1. **Update search_bookmarks** (`backend/src/services/bookmark_service.py`, lines 291-301)
   ```python
   # Determine sort column
   if sort_by == "created_at":
       sort_column = Bookmark.created_at
   elif sort_by == "updated_at":
       sort_column = Bookmark.updated_at
   elif sort_by == "last_used_at":
       sort_column = Bookmark.last_used_at
   else:  # title
       sort_column = func.coalesce(Bookmark.title, Bookmark.url)

   # Apply sorting with tiebreakers
   if sort_order == "desc":
       base_query = base_query.order_by(
           sort_column.desc(),
           Bookmark.created_at.desc(),
           Bookmark.id.desc(),
       )
   else:
       base_query = base_query.order_by(
           sort_column.asc(),
           Bookmark.created_at.asc(),
           Bookmark.id.asc(),
       )
   ```

2. **Update type annotation if needed** for `sort_by` parameter to include `"updated_at"` and `"last_used_at"`

### Testing Strategy
- Test sorting by last_used_at desc (most recently used first)
- Test sorting by last_used_at asc (least recently used first)
- Test sorting by updated_at desc/asc
- Test tiebreaker behavior (same timestamp -> ordered by created_at)

### Dependencies
Milestone 1 (database changes)

### Risk Factors
- None - simplified by having no NULL values

---

## Milestone 4: Frontend - API & Types

### Goal
Add frontend support for tracking usage and the new sort options.

### Success Criteria
- `trackBookmarkUsage` function exists in hooks
- Bookmark type includes `last_used_at`
- All sort options appear in dropdown (including new ones)

### Key Changes

1. **Update Bookmark interface** (`frontend/src/types.ts`)
   ```typescript
   last_used_at: string
   ```

2. **Add trackBookmarkUsage function** (`frontend/src/hooks/useBookmarks.ts`)
   ```typescript
   const trackBookmarkUsage = useCallback((id: number): void => {
     // Fire-and-forget: no await, no error handling
     api.post(`/bookmarks/${id}/track-usage`).catch(() => {
       // Silently ignore errors - this is non-critical
     })
   }, [])
   ```
   - **Important**: Do NOT await this call or update any state
   - Catch and swallow errors silently

3. **Update useBookmarks return** to include `trackBookmarkUsage`

4. **Update sort dropdown** (`frontend/src/pages/Bookmarks.tsx`, around line 783)
   ```tsx
   <option value="created_at-desc">Newest first</option>
   <option value="created_at-asc">Oldest first</option>
   <option value="updated_at-desc">Recently modified</option>
   <option value="updated_at-asc">Least recently modified</option>
   <option value="last_used_at-desc">Recently used</option>
   <option value="last_used_at-asc">Least recently used</option>
   <option value="title-asc">Title A-Z</option>
   <option value="title-desc">Title Z-A</option>
   ```

5. **Update type definition for sortBy** (line 135)
   - Change to: `'created_at' | 'updated_at' | 'last_used_at' | 'title'`

### Testing Strategy
- Test that trackBookmarkUsage makes API call
- Test that sort dropdown includes all options
- Test that sort parameter is passed to API correctly

### Dependencies
Milestones 1-3 (backend complete)

### Risk Factors
- Type definitions may need updates in multiple places

---

## Milestone 5: Frontend - Dynamic Date Display

### Goal
Display contextual date in BookmarkCard based on current sort option.

### Success Criteria
- When sorting by created_at: show "Created: [date]"
- When sorting by updated_at: show "Modified: [date]"
- When sorting by last_used_at: show "Used: [date]"
- When sorting by title: show "Created: [date]" (default)

### Key Changes

1. **Update BookmarkCard props** (`frontend/src/components/BookmarkCard.tsx`)
   ```typescript
   interface BookmarkCardProps {
     // ... existing props
     sortBy?: 'created_at' | 'updated_at' | 'last_used_at' | 'title'
   }
   ```

2. **Add date display logic in BookmarkCard**
   ```tsx
   const getDateDisplay = () => {
     switch (sortBy) {
       case 'updated_at':
         return `Modified: ${formatDate(bookmark.updated_at)}`
       case 'last_used_at':
         return `Used: ${formatDate(bookmark.last_used_at)}`
       case 'created_at':
       case 'title':
       default:
         return `Created: ${formatDate(bookmark.created_at)}`
     }
   }
   ```

3. **Update date display** (around line 239)
   - Replace `{formatDate(bookmark.created_at)}` with `{getDateDisplay()}`

4. **Pass sortBy to BookmarkCard** in `Bookmarks.tsx`
   ```tsx
   <BookmarkCard
     // ... existing props
     sortBy={sortBy}
   />
   ```

### Testing Strategy
- Test that correct date label shows for each sort option

### Dependencies
Milestone 4 (frontend types and sort options)

### Risk Factors
- None

---

## Milestone 6: Frontend - Track Usage on Click

### Goal
Call `trackBookmarkUsage` when user clicks bookmark links (unless holding modifier key).

### Success Criteria
- Clicking bookmark link calls trackBookmarkUsage
- Cmd+click (Mac) or Ctrl+click (Windows) does NOT call trackBookmarkUsage
- Works for all three link types (favicon, title, URL)

### Key Changes

1. **Update BookmarkCard props** (`frontend/src/components/BookmarkCard.tsx`)
   ```typescript
   interface BookmarkCardProps {
     // ... existing props
     onLinkClick?: (bookmark: Bookmark) => void
   }
   ```

2. **Add click handler for links**
   ```tsx
   const handleLinkClick = (e: React.MouseEvent) => {
     // Skip tracking if modifier key held (cmd/ctrl+click)
     if (e.metaKey || e.ctrlKey) {
       return
     }
     onLinkClick?.(bookmark)
   }
   ```

3. **Apply onClick to all three `<a>` tags** (lines 55-90)
   ```tsx
   <a
     href={bookmark.url}
     target="_blank"
     rel="noopener noreferrer"
     onClick={handleLinkClick}
     // ... rest of props
   >
   ```

4. **Pass trackBookmarkUsage in Bookmarks.tsx**
   ```tsx
   <BookmarkCard
     // ... existing props
     onLinkClick={(bookmark) => trackBookmarkUsage(bookmark.id)}
   />
   ```

### Testing Strategy
- Test that clicking link calls onLinkClick
- Test that cmd+click does NOT call onLinkClick
- Test that ctrl+click does NOT call onLinkClick

### Dependencies
Milestone 4 (frontend API support)

### Risk Factors
- Cross-browser modifier key detection (metaKey for Mac, ctrlKey for Windows)
- Need to ensure click handler doesn't interfere with default link behavior

---

## Summary

| Milestone | Description | Est. Files Changed |
|-----------|-------------|-------------------|
| 1 | Database & Model | 3 (migration, model, schema) |
| 2 | Track Usage Endpoint | 2 (service, router) + tests |
| 3 | Sort Options (Last Used & Modified) | 1 (service) + tests |
| 4 | Frontend API & Types | 3 (types, hooks, Bookmarks.tsx) |
| 5 | Dynamic Date Display | 2 (BookmarkCard, Bookmarks.tsx) |
| 6 | Track on Click | 2 (BookmarkCard, Bookmarks.tsx) + tests |

## Implementation Notes

- The endpoint returns 204 No Content to minimize response size for fire-and-forget calls
- The frontend makes the API call but does not await it or handle errors
- Modifier key (Cmd/Ctrl) + click skips tracking, allowing power users to open links without updating the timestamp
- `last_used_at` defaults to `created_at` on creation - no NULL handling needed, new bookmarks appear at top of "Recently used"
- Ties in sorting are broken by `created_at`, then `id` for deterministic ordering
- Date display is contextual: shows the date field that matches current sort option
