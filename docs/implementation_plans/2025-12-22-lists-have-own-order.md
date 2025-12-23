# Implementation Plan: Per-List Sort Order

## Overview

Add the ability for each bookmark list to have its own default sort order. The default should be `last_used_at desc`. This default is configurable per-list in settings. When viewing bookmarks, the frontend tracks user-selected sort orders per-list separately, so changing the sort on one list doesn't affect others, and the sort order persists across sessions.

## Current State

### Backend
- `BookmarkList` model stores `name` and `filter_expression` only
- `UserSettings` stores `tab_order` (list of tab identifiers)
- `search_bookmarks()` accepts `sort_by` and `sort_order` from request params
- No per-list sort configuration exists

### Frontend
- Sort is stored globally in `uiPreferencesStore` (localStorage key: `ui-preferences`)
- Changing sort persists globally across ALL views (lists, all, archived, trash)
- Default sort: `last_used_at desc`
- No per-list sort tracking

## Design Decisions

1. **Per-list default sort stored in backend** - Each `BookmarkList` has `default_sort_by` (string) and `default_sort_ascending` (boolean) columns
2. **User overrides stored in Zustand (persisted to localStorage)** - When a user changes sort on a specific view, it's stored in `uiPreferencesStore` which uses Zustand's `persist` middleware to sync to localStorage automatically
3. **Sort priority chain for custom lists**: User override > List default > Global default (`last_used_at desc`)
4. **Sort priority chain for built-in views**: User override > Hardcoded default (no "list default" since not in DB)
   - All Bookmarks: `last_used_at desc`
   - Archived: `archived_at desc`
   - Trash: `deleted_at desc`
5. **Context-aware sort options** - Sort dropdown shows only relevant options:
   - All Bookmarks / Custom lists: `last_used_at`, `created_at`, `updated_at`, `title`
   - Archived: above + `archived_at`
   - Trash: above + `deleted_at`
6. **Reset all overrides** - Settings includes a button to clear all user sort overrides, reverting all views to their defaults
7. **No sort in URL params** - Sort state lives in Zustand/localStorage only, not in URL. Reasoning:
   - Lists have configurable defaults, reducing need for URL-specified sort
   - Per-view overrides persist in localStorage across sessions/tabs
   - Browser back button should navigate to previous page, not undo sort changes
   - Simpler implementation without URL/store sync
8. **Shared sort constants** - Define sort options in a single file to prevent drift between store and UI
9. **Override indicator** - Show visual indicator when user has overridden the default sort

---

## Milestone 1: Backend - Add Default Sort to BookmarkList Model

### Goal
Add `default_sort_by` and `default_sort_ascending` columns to the `bookmark_lists` table with appropriate defaults.

### Success Criteria
- Database migration runs successfully
- New columns exist with correct types and defaults
- Existing lists have NULL values (will use system default)
- Unit tests pass for model changes

### Key Changes

**1. Create Alembic migration**

**always use `make migration` to generate the migration file** (see makefile for command usage)

Add nullable columns to `bookmark_lists`:
- `default_sort_by`: `VARCHAR(20)`, nullable, default NULL
- `default_sort_ascending`: `BOOLEAN`, nullable, default NULL

When NULL, the system defaults are used (`last_used_at`, descending).

**2. Update `BookmarkList` model** (`backend/src/models/bookmark_list.py`)

Add the two new columns:
```python
default_sort_by: Mapped[str | None] = mapped_column(String(20), nullable=True)
default_sort_ascending: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
# None or False = descending, True = ascending
```

### Testing Strategy
- Test that migration applies and rolls back cleanly
- Test that existing lists get NULL values for new columns
- Test model can be created with/without sort fields

### Dependencies
None

### Risk Factors
- Low risk - simple column additions with nullable defaults

---

## Milestone 2: Backend - Update Schemas, Endpoints, and Sort Options

### Goal
Update Pydantic schemas, list CRUD endpoints, and bookmark service to handle new sort fields.

### Success Criteria
- `BookmarkListCreate` accepts optional sort fields
- `BookmarkListUpdate` accepts optional sort fields
- `BookmarkListResponse` includes sort fields
- List creation/update/read endpoints work with new fields
- Validation rejects invalid sort values
- `archived_at` and `deleted_at` are valid sort options for bookmarks endpoint
- Unit tests cover all CRUD operations with sort fields

### Key Changes

**1. Update bookmark service** (`backend/src/services/bookmark_service.py`)

Add `archived_at` and `deleted_at` to the `sort_columns` mapping in `search_bookmarks()`:
```python
sort_columns = {
    "created_at": Bookmark.created_at,
    "updated_at": Bookmark.updated_at,
    "last_used_at": Bookmark.last_used_at,
    "title": func.coalesce(Bookmark.title, Bookmark.url),
    "archived_at": Bookmark.archived_at,  # NEW
    "deleted_at": Bookmark.deleted_at,    # NEW
}
```

**2. Update bookmarks router** (`backend/src/api/routers/bookmarks.py`)

Update the `sort_by` query parameter to accept the new values.

**3. Update schemas** (`backend/src/schemas/bookmark_list.py`)

Add to `BookmarkListBase` or individual schemas:
```python
from typing import Literal

# Note: archived_at and deleted_at are valid for bookmarks endpoint but NOT for list defaults
# Lists should only use these 4 options since they show active bookmarks
SortByOption = Literal["created_at", "updated_at", "last_used_at", "title"]

class BookmarkListCreate(BaseModel):
    name: str
    filter_expression: FilterExpression
    default_sort_by: SortByOption | None = None
    default_sort_ascending: bool | None = None  # None/False = desc, True = asc

class BookmarkListUpdate(BaseModel):
    name: str | None = None
    filter_expression: FilterExpression | None = None
    default_sort_by: SortByOption | None = None
    default_sort_ascending: bool | None = None

class BookmarkListResponse(BaseModel):
    id: int
    name: str
    filter_expression: FilterExpression
    default_sort_by: str | None
    default_sort_ascending: bool | None
    created_at: datetime
    updated_at: datetime
```

**4. Update list service** (`backend/src/services/list_service.py`)

Ensure create/update functions pass through the new fields.

**5. No changes needed to `/bookmarks/` endpoint**

The frontend will determine which sort to use based on the list's defaults. The API continues to accept explicit `sort_by`/`sort_order` params.

### Testing Strategy
- Test list creation with sort fields (valid values, None, omitted)
- Test list creation with invalid sort values (should fail validation)
- Test list update with sort fields
- Test list response includes sort fields
- Test that NULL values are returned as None in response
- Test bookmarks endpoint accepts `archived_at` sort (for archived view)
- Test bookmarks endpoint accepts `deleted_at` sort (for trash view)

### Dependencies
- Milestone 1 (database columns exist)

### Risk Factors
- Low risk - standard schema/endpoint updates

---

## Milestone 3: Frontend - Per-List Sort Override Storage

### Goal
Update `uiPreferencesStore` to track sort overrides per-list and per-view, so changing sort on one view doesn't affect others.

### Success Criteria
- Shared sort constants file created with types and labels
- Store tracks sort overrides per view key (e.g., `"list:5"`, `"all"`, `"archived"`, `"trash"`)
- Changing sort on a list only affects that list
- Overrides persist in localStorage
- Clearing an override reverts to list default (or global default for built-in views)
- Unit tests cover override get/set/clear operations

### Key Changes

**1. Create shared sort constants** (`frontend/src/constants/sortOptions.ts`)

Centralize sort option definitions to prevent drift between store and UI:

```typescript
export const BASE_SORT_FIELDS = ['last_used_at', 'created_at', 'updated_at', 'title'] as const
export const ARCHIVED_SORT_FIELDS = [...BASE_SORT_FIELDS, 'archived_at'] as const
export const TRASH_SORT_FIELDS = [...BASE_SORT_FIELDS, 'deleted_at'] as const

export const SORT_FIELD_LABELS: Record<string, string> = {
  last_used_at: 'Last Used',
  created_at: 'Date Added',
  updated_at: 'Date Modified',
  title: 'Title',
  archived_at: 'Archived At',
  deleted_at: 'Deleted At',
}

export type SortByOption = typeof BASE_SORT_FIELDS[number] | 'archived_at' | 'deleted_at'
export type SortOrderOption = 'asc' | 'desc'
```

**2. Update `uiPreferencesStore`** (`frontend/src/stores/uiPreferencesStore.ts`)

Import types from shared constants. Change from single global sort to per-view overrides:

```typescript
interface SortOverride {
  sortBy: SortByOption
  sortOrder: SortOrderOption
}

interface UIPreferencesState {
  // Keep existing global defaults
  bookmarkSortBy: SortByOption  // Global default (last_used_at)
  bookmarkSortOrder: SortOrderOption  // Global default (desc)

  // Add per-view overrides
  sortOverrides: Record<string, SortOverride>  // keyed by view: "all", "archived", "trash", "list:5"

  // Actions
  setSortOverride: (viewKey: string, sortBy: SortByOption, sortOrder: SortOrderOption) => void
  clearSortOverride: (viewKey: string) => void
  clearAllSortOverrides: () => void  // Reset button clears all overrides
  getSortOverride: (viewKey: string) => SortOverride | undefined
}
```

**3. Create helper to derive view key**

The view key identifies the current view:
- `"all"` for `/app/bookmarks`
- `"archived"` for `/app/bookmarks/archived`
- `"trash"` for `/app/bookmarks/trash`
- `"list:5"` for `/app/bookmarks/lists/5`

This can be derived from `currentView` and `currentListId` from `useBookmarkView`.

### Testing Strategy
- Test setting/getting overrides for different view keys
- Test that overrides persist after reload
- Test clearing an override
- Test that different view keys are isolated

### Dependencies
None

### Risk Factors
- Low risk - extending existing store pattern

---

## Milestone 4: Frontend - Integrate Per-List Sort in Bookmarks Page

### Goal
Update the bookmarks page to use the sort priority chain: User override > List default > Global default.

### Success Criteria
- When viewing a list, the effective sort is determined by the priority chain
- Sort dropdown shows the current effective sort
- Changing sort updates the override for the current view only
- Navigating to another list shows that list's effective sort (not the previous list's)
- Built-in views (all, archived, trash) work with overrides and global default
- Visual indicator shown when user has overridden the default sort (with option to reset)
- Unit/integration tests cover sort resolution logic

### Key Changes

**1. Create a hook to resolve effective sort** (`frontend/src/hooks/useEffectiveSort.ts`)

```typescript
interface UseEffectiveSortResult {
  sortBy: SortByOption
  sortOrder: SortOrderOption
  setSort: (sortBy: SortByOption, sortOrder: SortOrderOption) => void
  isOverridden: boolean  // True if using user override (vs list default or hardcoded default)
  clearOverride: () => void
  availableSortOptions: SortByOption[]  // Context-aware options for current view
}

function useEffectiveSort(
  viewKey: string,
  currentView: 'active' | 'archived' | 'deleted',
  listDefault?: { sortBy?: string, ascending?: boolean }
): UseEffectiveSortResult
```

**Priority chain for custom lists:**
1. Check `sortOverrides[viewKey]` - if exists, use it
2. Check `listDefault` (from list's `default_sort_by`/`default_sort_order`) - if exists, use it
3. Fall back to global default (`last_used_at desc`)

**Priority chain for built-in views:**
1. Check `sortOverrides[viewKey]` - if exists, use it
2. Fall back to hardcoded default:
   - All Bookmarks (`active` without listId): `last_used_at desc`
   - Archived: `archived_at desc`
   - Trash: `deleted_at desc`

**Context-aware sort options:**
```typescript
const baseSortOptions = ['last_used_at', 'created_at', 'updated_at', 'title']

function getAvailableSortOptions(currentView: string): SortByOption[] {
  if (currentView === 'archived') return [...baseSortOptions, 'archived_at']
  if (currentView === 'deleted') return [...baseSortOptions, 'deleted_at']
  return baseSortOptions
}
```

**2. Update `Bookmarks.tsx`**

- Derive `viewKey` from `currentView` and `currentListId`
- Get current list's defaults from `lists` store (if viewing a list)
- Use `useEffectiveSort(viewKey, currentView, listDefault)` to get effective sort
- Pass effective sort to `fetchBookmarks()` calls
- Wire sort dropdown to `setSort` from the hook
- **Render sort dropdown dynamically from `availableSortOptions`**:
  - Use `SORT_FIELD_LABELS` from shared constants for display text
  - Each field renders as two options: `{field}-desc` ("Label ↓") and `{field}-asc` ("Label ↑")
  - Archived view includes "Archived At ↓/↑", Trash includes "Deleted At ↓/↑"
- **Show override indicator when `isOverridden` is true**:
  - Display a reset icon/button next to the dropdown
  - Clicking it calls `clearOverride()` to revert to default
  - Optional: tooltip explaining "Custom sort - click to reset to default"

**3. Update `useBookmarkUrlParams.ts`**

Remove sort from URL params entirely:
- Delete `sort_by` and `sort_order` from URL param handling
- Sort state now lives exclusively in Zustand store (persisted to localStorage)
- This simplifies implementation and avoids URL/store sync issues

### Testing Strategy
- Test viewing a custom list with no override uses list default
- Test viewing a custom list with no override and no list default uses global default (`last_used_at desc`)
- Test changing sort creates an override for the current view only
- Test navigating between lists shows each list's effective sort
- Test clearing override reverts to list default (or hardcoded default for built-in views)
- Test built-in view defaults:
  - All Bookmarks defaults to `last_used_at desc`
  - Archived defaults to `archived_at desc`
  - Trash defaults to `deleted_at desc`
- Test context-aware sort options:
  - Archived view shows "Archived At ↓/↑" options
  - Trash view shows "Deleted At ↓/↑" options
  - All Bookmarks and custom lists do NOT show "Archived At" or "Deleted At"
- Test override indicator:
  - Not shown when using default sort
  - Shown when user has changed sort
  - Clicking reset clears override and reverts to default

### Dependencies
- Milestone 2 (list response includes sort defaults)
- Milestone 3 (store supports per-view overrides)

### Risk Factors
- Medium risk - touches core sorting logic used throughout the app
- Need to ensure no regressions in existing sort behavior

---

## Milestone 5: Frontend - Configure List Default Sort in Settings

### Goal
Add UI to configure the default sort order for each list in the settings/list edit modal.

### Success Criteria
- List create/edit modal includes sort configuration fields
- Sort configuration shows current defaults (or "System default" when NULL)
- Saving updates the list's default sort
- Changes reflect immediately when viewing that list
- "Reset All Sort Orders" button clears all user overrides
- After reset, all views revert to their list defaults (or global default)

### Key Changes

**1. Update `ListModal.tsx`**

Add sort configuration section below filter expression:

```tsx
<div className="space-y-2">
  <label>Default Sort</label>
  <select value={sortBy ?? ''} onChange={...}>
    <option value="">System default (Last Used ↓)</option>
    <option value="last_used_at">Last Used</option>
    <option value="created_at">Date Added</option>
    <option value="updated_at">Date Modified</option>
    <option value="title">Title</option>
  </select>
  {sortBy && (
    <label className="flex items-center gap-2">
      <input
        type="checkbox"
        checked={ascending ?? false}
        onChange={(e) => setAscending(e.target.checked)}
      />
      Ascending
    </label>
  )}
</div>
```

Note: The ascending checkbox only appears when a sort field is selected (not using system default).

**2. Update list create/update API calls**

Include `default_sort_by` and `default_sort_ascending` in the request payload.

**3. Add "Reset All Sort Orders" button** (`frontend/src/pages/settings/SettingsBookmarks.tsx`)

Add a section or button in settings that clears all user sort overrides:

```tsx
<Button
  variant="outline"
  onClick={() => clearAllSortOverrides()}
>
  Reset All Sort Orders to Defaults
</Button>
```

This calls `clearAllSortOverrides()` from the store, which sets `sortOverrides` to `{}`. All views will then use their list defaults (or global default).

**4. Update types** (`frontend/src/types.ts`)

Add to `BookmarkList` interface:
```typescript
interface BookmarkList {
  id: number
  name: string
  filter_expression: FilterExpression
  default_sort_by: string | null
  default_sort_ascending: boolean | null  // null/false = desc, true = asc
  created_at: string
  updated_at: string
}
```

### Testing Strategy
- Test creating a list with custom sort defaults
- Test editing a list's sort defaults
- Test that "System default" option sends NULL
- Test that changes to list defaults affect viewing that list
- Test "Reset All Sort Orders" button clears all overrides
- Test that after reset, views use list defaults (or global default)

### Dependencies
- Milestone 2 (backend accepts sort fields)
- Milestone 4 (frontend uses list defaults)

### Risk Factors
- Low risk - standard form field additions

---

## Summary

| Milestone | Scope | Estimated Complexity |
|-----------|-------|---------------------|
| 1 | Backend - Migration & Model | Low |
| 2 | Backend - Schemas, Endpoints & Sort Options (`archived_at`, `deleted_at`) | Low |
| 3 | Frontend - Store per-view overrides | Low |
| 4 | Frontend - Integrate in Bookmarks page (priority chain, context-aware options) | Medium |
| 5 | Frontend - Settings UI (list defaults, reset button) | Low |

## Out of Scope

- Syncing user sort overrides to backend (they stay in Zustand/localStorage)
- Configurable defaults for built-in views (they use hardcoded defaults)
- Sharing sort order via URL (sort is not in URL)
