# Soft Delete and Archive Functionality for Bookmarks

## Overview

Implement soft delete and archive functionality for bookmarks. Instead of permanently deleting bookmarks, they will be marked with timestamps (`deleted_at`, `archived_at`) and hidden from the main list. Users can view and restore deleted/archived bookmarks within a 30-day window for deleted items.

**Key behaviors:**
- **Delete**: Sets `deleted_at` timestamp, hides from main list/search, restorable within 30 days
- **Archive**: Sets `archived_at` timestamp, hides from main list/search unless explicitly viewing archived, no auto-expiration
- Frontend removes confirmation dialogs in favor of toast notifications with "Undo" option

---

## Design Decisions (Resolved)

1. **Delete endpoint behavior**: Keep existing `DELETE /bookmarks/{id}` endpoint but add `permanent: bool = False` query parameter. Default is soft delete; `permanent=true` performs hard delete. Frontend uses soft delete from main view and hard delete from trash view (same delete icon, different behavior based on context).

2. **Unique URL constraint with soft delete**:
   - **Creating new bookmark**: Allowed if the same URL exists only as soft-deleted. NOT allowed if URL exists as archived (archived bookmarks count toward uniqueness).
   - **Restoring soft-deleted bookmark**: If an active bookmark with the same URL already exists, return 409 Conflict error.
   - **Frontend handling for archived URL conflict**: When backend returns error that URL exists as archived, frontend should offer option to restore/unarchive the existing archived bookmark instead.

3. **State transitions**:
   - **Restoring a deleted+archived bookmark**: Clears BOTH `deleted_at` AND `archived_at` (restores to active state, since user is explicitly indicating interest)
   - **Deleting an archived bookmark**: Sets `deleted_at` (soft delete). Bookmark moves from archive view to trash view.
   - **Archiving an already-archived bookmark**: Idempotent (return 200 with current state)
   - **Restoring a non-deleted bookmark**: Return 400 Bad Request

4. **Permanent delete access**: Only available from trash view. Same delete icon used everywhere, but behavior differs by view context.

5. **View navigation**: Tabs/dropdown within existing Bookmarks page (not separate routes).

6. **URL uniqueness implementation**: Use a partial unique index at the database level:
   ```sql
   CREATE UNIQUE INDEX uq_bookmark_user_url_active ON bookmarks(user_id, url) WHERE deleted_at IS NULL;
   ```
   This means active + archived bookmarks enforce uniqueness (both have `deleted_at IS NULL`), while soft-deleted bookmarks don't count.

7. **Error response format for URL conflicts**: Use structured error response:
   ```json
   {
     "detail": "URL already exists",
     "error_code": "ARCHIVED_URL_EXISTS",  // or "ACTIVE_URL_EXISTS"
     "existing_bookmark_id": 123
   }
   ```

8. **Permanent delete UX**: Use browser `confirm()` dialog with message: "Permanently delete this bookmark? This cannot be undone."

9. **View switching behavior**: Reset pagination (`offset=0`) when switching between views.

10. **30-day auto-expiration**: Deferred to future task. Trash view UI will mention "Items are permanently deleted after 30 days" but cleanup job not implemented yet.

---

## Milestone 1: Database Schema Changes

### Goal
Add `deleted_at` and `archived_at` nullable timestamp columns to the bookmarks table.

### Success Criteria
- Migration runs successfully
- Existing bookmarks have NULL for both columns
- New columns are queryable and can be set/unset

### Key Changes

1. **Create Alembic migration** (`make migration message="add deleted_at and archived_at to bookmarks"`)
   - Add `deleted_at: DateTime(timezone=True), nullable=True, default=None`
   - Add `archived_at: DateTime(timezone=True), nullable=True, default=None`
   - Add index on `deleted_at` for view filtering and future cleanup job
   - Drop existing `uq_bookmark_user_url` unique constraint
   - Create partial unique index: `CREATE UNIQUE INDEX uq_bookmark_user_url_active ON bookmarks(user_id, url) WHERE deleted_at IS NULL`

2. **Update Bookmark model** (`backend/src/models/bookmark.py`)
   ```python
   from datetime import datetime
   from sqlalchemy import DateTime, Index

   deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None, index=True)
   archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)

   # Update table args to replace old UniqueConstraint with partial unique index
   __table_args__ = (
       Index("uq_bookmark_user_url_active", "user_id", "url", unique=True, postgresql_where=text("deleted_at IS NULL")),
   )
   ```

### Testing Strategy
- Verify migration applies cleanly to existing database (local container)
- Verify existing bookmarks have NULL values for new columns
- Verify new bookmarks can be created with NULL values (default behavior)
- Verify uniqueness constraint works: cannot create duplicate URL when `deleted_at IS NULL`
- Verify soft-deleted bookmark allows creating new bookmark with same URL

### Dependencies
None

### Risk Factors
- Migration should be straightforward; low risk

---

## Milestone 2: Backend Service Layer Updates

### Goal
Update `bookmark_service.py` to implement soft delete/archive logic and filtering.

### Success Criteria
- `delete_bookmark` sets `deleted_at` instead of hard delete (by default)
- `search_bookmarks` filters out deleted AND archived bookmarks by default
- New functions exist for restore, archive, unarchive
- URL uniqueness properly handles soft-deleted vs archived bookmarks

### Key Changes

1. **Update `delete_bookmark`** - Add `permanent: bool = False` parameter:
   - If `permanent=False`: Set `deleted_at = func.now()` (soft delete)
   - If `permanent=True`: Call `db.delete(bookmark)` (hard delete, for trash view)

2. **Update `get_bookmark`** - Add optional parameter to include deleted/archived or not (default: exclude both)

3. **Update `search_bookmarks`** - Add filter to exclude deleted (`deleted_at IS NULL`) and archived (`archived_at IS NULL`) by default. Add parameter:
   - `view: Literal["active", "archived", "deleted"] = "active"`
   - "active" = `deleted_at IS NULL AND archived_at IS NULL`
   - "archived" = `deleted_at IS NULL AND archived_at IS NOT NULL`
   - "deleted" = `deleted_at IS NOT NULL` (includes both deleted-only and deleted+archived)

4. **Update `create_bookmark`** - Modify duplicate URL check:
   - Only check against bookmarks where `deleted_at IS NULL` (soft-deleted don't count)
   - Archived bookmarks DO count toward uniqueness
   - If URL exists as archived, raise a specific error (e.g., `ArchivedUrlExistsError`) so frontend can handle differently

5. **Add new service functions:**
   ```python
   async def restore_bookmark(db: AsyncSession, user_id: int, bookmark_id: int) -> Bookmark | None:
       """
       Restore a soft-deleted bookmark by clearing deleted_at AND archived_at.

       Raises:
           DuplicateUrlError: If an active bookmark with the same URL already exists.
           InvalidStateError: If bookmark is not deleted.
       """

   async def archive_bookmark(db: AsyncSession, user_id: int, bookmark_id: int) -> Bookmark | None:
       """Archive a bookmark by setting archived_at. Idempotent."""

   async def unarchive_bookmark(db: AsyncSession, user_id: int, bookmark_id: int) -> Bookmark | None:
       """Unarchive a bookmark by clearing archived_at."""
   ```

### Testing Strategy

**Soft delete tests:**
- Test soft delete sets `deleted_at` and doesn't remove from DB
- Test soft delete on archived bookmark sets `deleted_at` (moves to trash)
- Test hard delete (`permanent=True`) removes bookmark from DB

**Search/filter tests:**
- Test `search_bookmarks` with `view="active"` excludes deleted AND archived
- Test `search_bookmarks` with `view="deleted"` returns only deleted bookmarks
- Test `search_bookmarks` with `view="archived"` returns only archived (not deleted)
- Test search query and tag filters work with all view modes

**Restore tests:**
- Test restore clears `deleted_at` and bookmark appears in active list
- Test restore of deleted+archived bookmark clears BOTH timestamps (restores to active)
- Test restore when active bookmark with same URL exists returns 409 Conflict
- Test restore of non-deleted bookmark returns 400 Bad Request

**Archive tests:**
- Test archive sets `archived_at` and bookmark disappears from active list
- Test archiving already-archived bookmark is idempotent (returns 200)
- Test unarchive clears `archived_at`

**URL uniqueness edge cases:**
- Test creating bookmark succeeds when same URL exists only as soft-deleted
- Test creating bookmark fails (409) when same URL exists as archived
- Test creating bookmark fails (409) when same URL exists as active
- Test the error response distinguishes between "archived" vs "active" duplicate

### Dependencies
- Milestone 1 (database schema)

### Risk Factors
- Need to ensure duplicate URL check logic correctly distinguishes soft-deleted vs archived vs active
- Restore operation needs to re-check uniqueness before clearing `deleted_at`

---

## Milestone 3: Backend API Endpoint Updates

### Goal
Update existing endpoints and add new endpoints for archive/restore operations.

### Success Criteria
- `DELETE /bookmarks/{id}` supports `permanent` query parameter
- `GET /bookmarks/` supports `view` query parameter
- New endpoints for restore/archive/unarchive actions
- Proper error responses for state transition errors

### Key Changes

1. **Update `DELETE /bookmarks/{bookmark_id}`** - Add query parameter:
   ```python
   @router.delete("/{bookmark_id}", status_code=204)
   async def delete_bookmark(
       bookmark_id: int,
       permanent: bool = Query(default=False, description="If true, permanently delete. If false, soft delete."),
       ...
   ) -> None:
   ```

2. **Update `GET /bookmarks/`** - Add query parameter:
   ```python
   view: Literal["active", "archived", "deleted"] = Query(default="active", description="Which bookmarks to show")
   ```

3. **Add new endpoints:**
   ```python
   @router.post("/{bookmark_id}/restore", response_model=BookmarkResponse)
   async def restore_bookmark(bookmark_id: int, ...) -> BookmarkResponse:
       """Restore a soft-deleted bookmark to active state."""
       # Returns 400 if not deleted, 409 if URL conflict

   @router.post("/{bookmark_id}/archive", response_model=BookmarkResponse)
   async def archive_bookmark(bookmark_id: int, ...) -> BookmarkResponse:
       """Archive a bookmark. Idempotent."""

   @router.post("/{bookmark_id}/unarchive", response_model=BookmarkResponse)
   async def unarchive_bookmark(bookmark_id: int, ...) -> BookmarkResponse:
       """Unarchive a bookmark."""
   ```

4. **Update `BookmarkResponse` schema** - Add fields:
   ```python
   deleted_at: datetime | None = None
   archived_at: datetime | None = None
   ```

5. **Update `POST /bookmarks/`** (create) - Return different error code/message when URL exists as archived vs active, so frontend can offer to restore.

### Testing Strategy

**Delete endpoint tests:**
- Test `DELETE /bookmarks/{id}` (default) soft-deletes bookmark
- Test `DELETE /bookmarks/{id}?permanent=true` hard-deletes bookmark
- Test delete of non-existent bookmark returns 404

**List endpoint tests:**
- Test `GET /bookmarks/` (default) excludes deleted and archived
- Test `GET /bookmarks/?view=archived` returns only archived
- Test `GET /bookmarks/?view=deleted` returns only deleted
- Test search (`q=`) and tag filters work with each view mode

**Restore endpoint tests:**
- Test `POST /bookmarks/{id}/restore` on deleted bookmark restores it
- Test restore on deleted+archived bookmark restores to active (clears both)
- Test restore on non-deleted bookmark returns 400
- Test restore when URL already exists as active returns 409
- Test restore on non-existent bookmark returns 404

**Archive endpoint tests:**
- Test `POST /bookmarks/{id}/archive` archives bookmark
- Test archive on already-archived bookmark returns 200 (idempotent)
- Test `POST /bookmarks/{id}/unarchive` unarchives bookmark
- Test archive/unarchive on non-existent bookmark returns 404
- Test unarchive on non-archived bookmark returns 400 (consistent with restore behavior)

**Create endpoint edge cases:**
- Test create with URL that exists as soft-deleted succeeds
- Test create with URL that exists as archived returns 409 with specific message
- Test create with URL that exists as active returns 409

### Dependencies
- Milestone 2 (service layer)

### Risk Factors
- Error response format needs to be clear enough for frontend to distinguish error types

---

## Milestone 4: Frontend Types and API Service Updates

### Goal
Update TypeScript types and API service layer to support new endpoints and response fields.

### Success Criteria
- Types include `deleted_at` and `archived_at` fields
- API hooks support new endpoints (restore, archive, unarchive)
- Delete hook supports `permanent` parameter
- Search params support `view` parameter

### Key Changes

1. **Update `types.ts`:**
   ```typescript
   export interface Bookmark {
     // ... existing fields
     deleted_at: string | null
     archived_at: string | null
   }

   export interface BookmarkSearchParams {
     // ... existing fields
     view?: 'active' | 'archived' | 'deleted'
   }
   ```

2. **Update `useBookmarks.ts` hook** - Add/modify functions:
   ```typescript
   deleteBookmark: (id: number, permanent?: boolean) => Promise<void>
   restoreBookmark: (id: number) => Promise<Bookmark>
   archiveBookmark: (id: number) => Promise<Bookmark>
   unarchiveBookmark: (id: number) => Promise<Bookmark>
   ```

3. **Update `fetchBookmarks`** - Support `view` parameter in query string

### Testing Strategy
- Unit tests for new API calls (mock responses)
- Test that `view` parameter is correctly added to query string
- Test that `permanent` parameter is correctly added to delete call

### Dependencies
- Milestone 3 (backend API)

### Risk Factors
- Low risk; straightforward type and API updates

---

## Milestone 5: Frontend UI Updates - Main Bookmarks View

### Goal
Update the main bookmarks page to support delete/archive with undo toasts instead of confirmation dialogs.

### Success Criteria
- Delete button triggers soft delete with toast + undo option
- Archive button added to BookmarkCard with toast + undo option
- No confirmation dialogs for delete/archive
- Undo reverts the action within toast timeout window

### Key Changes

1. **Update `BookmarkCard.tsx`:**
   - Add archive button (icon: box/archive icon)
   - Remove confirmation from delete handler
   - Add `onArchive` prop
   - Accept `view` prop to control which buttons are shown (prep for Milestone 6)

2. **Update `Bookmarks.tsx`:**
   - Remove `confirm()` dialog from `handleDeleteBookmark`
   - Add `handleArchiveBookmark` function
   - Implement undo functionality using `react-hot-toast`:
     ```typescript
     const handleDeleteBookmark = async (bookmark: Bookmark): Promise<void> => {
       await deleteBookmark(bookmark.id) // soft delete
       toast.success(
         (t) => (
           <span>
             Bookmark deleted.{' '}
             <button
               onClick={async () => {
                 await restoreBookmark(bookmark.id)
                 toast.dismiss(t.id)
                 fetchBookmarks(currentParams)
               }}
               className="underline font-medium"
             >
               Undo
             </button>
           </span>
         ),
         { duration: 5000 }
       )
       fetchBookmarks(currentParams)
     }
     ```

3. **Handle archived URL conflict on create:**
   - When create fails with "URL exists as archived" error, show option to restore
   - Could be a toast with "Restore existing?" button, or modify the error display

### Testing Strategy
- Test delete triggers soft delete (not hard delete)
- Test archive sets archived_at
- Test undo within timeout restores/unarchives the bookmark
- Test undo after navigating away handles gracefully (404 is acceptable)
- Visual testing for toast appearance and undo button

### Dependencies
- Milestone 4 (frontend types/hooks)

### Risk Factors
- Toast undo timing: if user clicks undo after toast dismisses, no action (acceptable)
- Need to refresh list after undo to show restored bookmark

---

## Milestone 6: Frontend UI - Trash and Archive Views

### Goal
Add tab selector for viewing and managing deleted (trash) and archived bookmarks.

### Success Criteria
- Tab/dropdown selector to switch between "All", "Archived", "Trash" views
- Trash view shows deleted bookmarks with restore/permanent delete options
- Archive view shows archived bookmarks with unarchive/delete options
- Views support search and filtering (same as main view)
- Clear visual indication of current view

### Key Changes

1. **Add view selector to `Bookmarks.tsx`:**
   - Tab bar or dropdown: "All Bookmarks" | "Archived" | "Trash"
   - Store in URL params (`?view=active|archived|deleted`) for shareability
   - Pass view to `fetchBookmarks`

2. **Update UI based on current view:**
   - **"active" view**: show edit/archive/delete (soft) buttons
   - **"archived" view**: show edit/unarchive/delete (soft) buttons
   - **"trash" view**: show restore/delete (permanent) buttons, NO edit

3. **Update `BookmarkCard.tsx`** with `view` prop:
   ```typescript
   interface BookmarkCardProps {
     bookmark: Bookmark
     view: 'active' | 'archived' | 'deleted'
     onEdit?: (bookmark: Bookmark) => void
     onDelete: (bookmark: Bookmark) => void
     onArchive?: (bookmark: Bookmark) => void
     onUnarchive?: (bookmark: Bookmark) => void
     onRestore?: (bookmark: Bookmark) => void
     onTagClick?: (tag: string) => void
   }
   ```

4. **Update empty states per view:**
   - Active: "No bookmarks yet. Add your first bookmark."
   - Archived: "No archived bookmarks."
   - Trash: "Trash is empty." (maybe add note about 30-day auto-delete)

5. **Delete button behavior by view:**
   - In active/archived view: calls `deleteBookmark(id, false)` (soft delete) with undo toast
   - In trash view: calls `deleteBookmark(id, true)` (permanent) with confirmation toast (no undo)

### Testing Strategy
- Test switching between views shows correct bookmarks
- Test actions in each view work correctly:
  - Active: edit, archive, soft-delete all work
  - Archived: edit, unarchive, soft-delete all work
  - Trash: restore, permanent-delete work; no edit option
- Test permanent delete from trash shows confirmation (not undo)
- Test empty states for each view
- Test search/filter works within each view
- Test URL state (`?view=`) persists across page refresh

### Dependencies
- Milestone 5 (main view updates)

### Risk Factors
- Need clear visual distinction between views so user knows context
- Permanent delete should have some friction (confirmation, not just undo)

---

## Summary of New/Modified Files

### Backend
- `backend/src/models/bookmark.py` - Add deleted_at, archived_at columns
- `backend/src/schemas/bookmark.py` - Add fields to response schema
- `backend/src/services/bookmark_service.py` - Update delete, add restore/archive/unarchive, update URL checking
- `backend/src/api/routers/bookmarks.py` - Update delete endpoint, add view param, add new endpoints
- `backend/src/db/migrations/versions/xxx_add_deleted_archived.py` - New migration
- `backend/tests/api/test_bookmarks.py` - Update existing tests, add comprehensive new tests

### Frontend
- `frontend/src/types.ts` - Add new fields and types
- `frontend/src/hooks/useBookmarks.ts` - Add new API functions, update delete
- `frontend/src/components/BookmarkCard.tsx` - Add archive button, accept view prop, conditional actions
- `frontend/src/pages/Bookmarks.tsx` - Add view selector, undo toasts, archive handler, view-specific behavior
