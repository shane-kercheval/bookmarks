# Bookmarks.tsx Refactor Plan

## Problem Statement

`Bookmarks.tsx` has grown to ~945 lines and handles too many responsibilities:
- Tab navigation and state derivation
- URL parameter management
- Search/filter handlers
- Bookmark CRUD with undo toast patterns
- Pagination logic
- Empty state rendering
- Modal state management
- Keyboard shortcuts
- 6 inline icon components

This makes the component harder to test, maintain, and understand.

## Goals

1. Reduce `Bookmarks.tsx` to under 400 lines
2. Improve testability by extracting logic into hooks
3. Make patterns reusable across future pages
4. Maintain existing behavior and test coverage

## Non-Goals

- Changing the UI/UX
- Refactoring other components
- Adding new features

---

## Extraction Plan

### 1. Extract Icons to Shared File

**New file:** `frontend/src/components/icons.tsx`

Extract these icon components:
- `SearchIcon`
- `BookmarkIcon`
- `PlusIcon`
- `CloseIcon`
- `ArchiveIcon`
- `FolderIcon`
- `TrashIcon`

**Impact:** -77 lines from Bookmarks.tsx

**Notes:**
- Icons are already used inline in other components (e.g., BookmarkCard.tsx)
- Consider consolidating all icons into this file over time
- Export as named exports for tree-shaking

---

### 2. Extract `useTabNavigation` Hook

**New file:** `frontend/src/hooks/useTabNavigation.ts`

**Responsibilities:**
- Parse `tab` URL param with fallback to first tab in order
- Derive `currentView` ('active' | 'archived' | 'deleted') from tab key
- Derive `currentListId` (number | undefined) from tab key
- Provide `handleTabChange` to update URL param
- Consume `computedTabOrder` from settingsStore internally

**Interface:**
```typescript
interface UseTabNavigationReturn {
  currentTabKey: string
  currentView: 'active' | 'archived' | 'deleted'
  currentListId: number | undefined
  computedTabOrder: TabOrderItem[]
  handleTabChange: (tabKey: string) => void
}

function useTabNavigation(): UseTabNavigationReturn
```

**Lines extracted:** ~50 lines (derivation logic + handler)

**Testing:**
- Test tab key parsing
- Test view derivation for 'all', 'archived', 'trash', 'list:N'
- Test handleTabChange updates URL correctly

---

### 3. Extract `useBookmarkUrlParams` Hook

**New file:** `frontend/src/hooks/useBookmarkUrlParams.ts`

**Responsibilities:**
- Parse all bookmark-related URL params (q, tags, tag_match, sort_by, sort_order, offset)
- Provide typed `updateParams` function
- Build `currentParams` object for API calls
- Handle debouncing of search query

**Interface:**
```typescript
interface BookmarkUrlParams {
  searchQuery: string
  debouncedSearchQuery: string
  selectedTags: string[]
  tagMatch: 'all' | 'any'
  sortBy: 'created_at' | 'updated_at' | 'last_used_at' | 'title'
  sortOrder: 'asc' | 'desc'
  offset: number
}

interface UseBookmarkUrlParamsReturn extends BookmarkUrlParams {
  updateParams: (updates: Partial<BookmarkSearchParams>) => void
  buildSearchParams: (view: string, listId?: number) => BookmarkSearchParams
  hasFilters: boolean
}

function useBookmarkUrlParams(): UseBookmarkUrlParamsReturn
```

**Lines extracted:** ~80 lines (parsing + updateParams + currentParams memo)

**Testing:**
- Test param parsing with various URL states
- Test updateParams correctly modifies URL
- Test buildSearchParams output

---

### 4. Extract `useBookmarkActions` Hook

**New file:** `frontend/src/hooks/useBookmarkActions.ts`

**Responsibilities:**
- Wrap bookmark CRUD operations with toast notifications
- Handle undo patterns for delete/archive/unarchive/restore
- Handle duplicate URL error detection and archived URL unarchive flow
- Refresh bookmarks and tags after mutations

**Interface:**
```typescript
interface UseBookmarkActionsOptions {
  fetchBookmarks: () => void
  fetchTags: () => void
  onCloseAddModal?: () => void
  onCloseEditModal?: () => void
}

interface UseBookmarkActionsReturn {
  handleAddBookmark: (data: BookmarkCreate) => Promise<void>
  handleEditBookmark: (bookmarkId: number, data: BookmarkUpdate) => Promise<void>
  handleDeleteBookmark: (bookmark: Bookmark, view: string) => Promise<void>
  handleArchiveBookmark: (bookmark: Bookmark) => Promise<void>
  handleUnarchiveBookmark: (bookmark: Bookmark) => Promise<void>
  handleRestoreBookmark: (bookmark: Bookmark) => Promise<void>
  isSubmitting: boolean
}

function useBookmarkActions(options: UseBookmarkActionsOptions): UseBookmarkActionsReturn
```

**Lines extracted:** ~250 lines (all CRUD handlers with toast/undo logic)

**Testing:**
- Test success toast shown on each operation
- Test undo functionality triggers correct reverse operation
- Test error handling for 409 conflicts
- Test isSubmitting state management

---

### 5. Extract Tab Bar Component

**New file:** `frontend/src/components/TabBar.tsx`

**Responsibilities:**
- Render tab navigation UI
- Handle fallback tabs when computedTabOrder not loaded
- Highlight active tab

**Interface:**
```typescript
interface TabBarProps {
  tabs: TabOrderItem[]
  activeTabKey: string
  onTabChange: (key: string) => void
  fallbackTabs?: TabOrderItem[]
}

function TabBar({ tabs, activeTabKey, onTabChange, fallbackTabs }: TabBarProps): ReactNode
```

**Lines extracted:** ~55 lines (tab rendering)

**Notes:**
- Reusable for any tabbed interface
- Could be used in Settings page if needed

---

## Implementation Order

1. **Extract icons** - Lowest risk, purely mechanical
2. **Extract TabBar component** - Simple UI extraction
3. **Extract useTabNavigation** - Moderate complexity, clear boundaries
4. **Extract useBookmarkUrlParams** - Moderate complexity
5. **Extract useBookmarkActions** - Highest complexity, most logic

Each step should:
- Be a separate commit
- Maintain all existing tests passing
- Not change any visible behavior

---

## Resulting Structure

After refactoring:

```
frontend/src/
├── components/
│   ├── icons.tsx              # Shared icons (NEW)
│   ├── TabBar.tsx             # Tab navigation UI (NEW)
│   └── ...
├── hooks/
│   ├── useTabNavigation.ts    # Tab state management (NEW)
│   ├── useBookmarkUrlParams.ts # URL param handling (NEW)
│   ├── useBookmarkActions.ts  # CRUD with toasts (NEW)
│   └── ...
└── pages/
    └── Bookmarks.tsx          # ~350 lines (down from ~945)
```

---

## Estimated Line Counts

| Extraction | Lines Removed | New File Lines |
|------------|---------------|----------------|
| Icons | -77 | ~85 |
| TabBar | -55 | ~65 |
| useTabNavigation | -50 | ~70 |
| useBookmarkUrlParams | -80 | ~100 |
| useBookmarkActions | -250 | ~280 |
| **Total** | **-512** | ~600 |

**Final Bookmarks.tsx:** ~430 lines (primarily JSX rendering and wiring)

---

## Testing Strategy

1. **Existing tests remain green** - No behavior changes
2. **New unit tests for each hook** - Test logic in isolation
3. **Consider integration test** - Verify hooks work together correctly

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Breaking existing behavior | Run full test suite after each extraction |
| Over-abstraction | Keep interfaces simple, don't over-generalize |
| Prop drilling | Hooks consume stores directly where appropriate |
| Circular dependencies | Keep clear dependency direction: hooks -> stores -> api |
