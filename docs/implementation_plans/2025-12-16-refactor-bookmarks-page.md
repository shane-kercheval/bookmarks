# Bookmarks.tsx Refactor Plan

## Problem Statement

`Bookmarks.tsx` handles multiple concerns that should be separated for better testability, reusability, and maintainability:

- URL parameter parsing/updating mixed with rendering
- Tab-to-view business logic embedded in component
- Tab UI that could be reused elsewhere
- Bookmark CRUD handlers (intentionally explicit - keep as-is)

## Goals

1. **Testability**: Extract logic into hooks that can be unit tested without rendering
2. **Reusability**: Create patterns and components usable across the application
3. **Separation of Concerns**: Business logic separate from UI, URL state separate from rendering
4. **Maintainability**: Changes to one concern shouldn't risk breaking unrelated code

## Non-Goals

- Reducing line count for its own sake
- Abstracting the bookmark action handlers (they're intentionally explicit)
- Changing UI/UX behavior

---

## Extractions

### 1. `useTabNavigation` Hook

**File:** `frontend/src/hooks/useTabNavigation.ts`

**Design Rationale:** The mapping from `tabKey` to `{view, listId}` is business logic that should be:
- Unit testable independently
- Reusable if needed for deep linking, analytics, etc.
- Separated from rendering concerns

**Responsibilities:**
- Parse `tab` URL param with fallback to first tab in order
- Derive `currentView` ('active' | 'archived' | 'deleted') from tab key
- Derive `currentListId` (number | undefined) from tab key
- Provide `handleTabChange` to update URL param
- Consume `computedTabOrder` from settingsStore

**Interface:**
```typescript
interface UseTabNavigationReturn {
  currentTabKey: string
  currentView: 'active' | 'archived' | 'deleted'
  currentListId: number | undefined
  handleTabChange: (tabKey: string) => void
}

function useTabNavigation(): UseTabNavigationReturn
```

**Tests:**
- `deriveViewFromTabKey('all')` → `{ view: 'active', listId: undefined }`
- `deriveViewFromTabKey('archived')` → `{ view: 'archived', listId: undefined }`
- `deriveViewFromTabKey('trash')` → `{ view: 'deleted', listId: undefined }`
- `deriveViewFromTabKey('list:5')` → `{ view: 'active', listId: 5 }`
- `deriveViewFromTabKey('list:invalid')` → `{ view: 'active', listId: undefined }`
- `handleTabChange` updates URL correctly
- Falls back to first tab when no tab param and computedTabOrder loaded

---

### 2. `useBookmarkUrlParams` Hook

**File:** `frontend/src/hooks/useBookmarkUrlParams.ts`

**Design Rationale:** URL state management is a cross-cutting concern that should be:
- Testable in isolation (URL transformations without rendering)
- A reusable pattern for other pages
- Separated from component rendering logic

**Responsibilities:**
- Parse bookmark-related URL params (q, tags, tag_match, sort_by, sort_order, offset)
- Provide typed `updateParams` function with smart defaults
- Build `currentParams` object for API calls
- Handle memoization of array params (tags)

**Interface:**
```typescript
interface BookmarkUrlParams {
  searchQuery: string
  selectedTags: string[]
  tagMatch: 'all' | 'any'
  sortBy: 'created_at' | 'updated_at' | 'last_used_at' | 'title'
  sortOrder: 'asc' | 'desc'
  offset: number
}

interface UseBookmarkUrlParamsReturn extends BookmarkUrlParams {
  updateParams: (updates: Partial<BookmarkUrlParams>) => void
  hasFilters: boolean
}

function useBookmarkUrlParams(): UseBookmarkUrlParamsReturn
```

**Tests:**
- Parse params from URL correctly
- `updateParams({ q: 'test' })` sets q param
- `updateParams({ q: '' })` removes q param (not stores empty string)
- `updateParams({ tags: ['a', 'b'] })` handles array params
- `updateParams({ offset: 0 })` removes offset (default value optimization)
- `selectedTags` memoization prevents infinite re-renders
- `hasFilters` correctly reflects search/tag state

---

### 3. `TabBar` Component

**File:** `frontend/src/components/TabBar.tsx`

**Design Rationale:** Pure presentational component that:
- Knows nothing about bookmarks
- Can be reused for any tabbed interface
- Has clear, simple props interface

**Responsibilities:**
- Render horizontal tab navigation
- Handle active tab styling
- Support optional fallback tabs while loading

**Interface:**
```typescript
interface Tab {
  key: string
  label: string
}

interface TabBarProps {
  tabs: Tab[]
  activeTabKey: string
  onTabChange: (key: string) => void
  fallbackTabs?: Tab[]
}

function TabBar({ tabs, activeTabKey, onTabChange, fallbackTabs }: TabBarProps): ReactNode
```

**Tests:**
- Renders all provided tabs
- Applies active styling to current tab
- Calls onTabChange with correct key on click
- Renders fallbackTabs when tabs array is empty

---

### 4. Keep Action Handlers Inline

**Rationale:** The bookmark action handlers (`handleAddBookmark`, `handleEditBookmark`, `handleDeleteBookmark`, `handleArchiveBookmark`, `handleUnarchiveBookmark`, `handleRestoreBookmark`) should remain in `Bookmarks.tsx`.

**Why not extract:**
- Each handler has meaningful differences in error handling, confirmation dialogs, and undo semantics
- Abstracting would require complex configuration or callbacks that duplicate current logic
- Explicit handlers improve debuggability and make each operation's behavior obvious
- The pattern prioritizes clarity over DRYness for user-facing actions with side effects

---

## Implementation Order

1. **Extract `useTabNavigation`** - Pure business logic, easy to test
2. **Extract `useBookmarkUrlParams`** - URL state management
3. **Extract `TabBar`** - Pure UI component

Each step:
- Separate commit
- All existing tests pass
- Add unit tests for extracted code
- No behavior changes

---

## Testing Strategy

### New Unit Tests

**`useTabNavigation.test.ts`:**
- Test `deriveViewFromTabKey` pure function for all tab types
- Test hook integration with URL params
- Test fallback behavior

**`useBookmarkUrlParams.test.ts`:**
- Test URL parsing for each param type
- Test `updateParams` URL modifications
- Test memoization behavior
- Test default value handling

**`TabBar.test.tsx`:**
- Test rendering with various tab configurations
- Test click handlers
- Test active state styling
- Test fallback tabs

### Existing Tests

The existing `Bookmarks.test.tsx` integration tests should continue to pass unchanged, validating that the refactoring preserves behavior.

---

## Resulting Structure

```
frontend/src/
├── components/
│   ├── TabBar.tsx              # Reusable tab navigation (NEW)
│   └── ...
├── hooks/
│   ├── useTabNavigation.ts     # Tab state + view derivation (NEW)
│   ├── useBookmarkUrlParams.ts # URL param management (NEW)
│   ├── useBookmarks.ts         # Bookmark CRUD (existing)
│   └── ...
└── pages/
    └── Bookmarks.tsx           # Orchestration + action handlers
```

---

## Success Criteria

1. All existing tests pass
2. New hooks have unit test coverage for core logic
3. TabBar is reusable (no bookmark-specific knowledge)
4. URL param logic is testable without rendering components
5. Tab→view derivation is testable as pure function
