# Frontend Caching with TanStack Query

## Overview

Replace the current `useBookmarks` hook's manual state management with TanStack Query to enable automatic caching, background refetching, and declarative cache invalidation.

**Problem:** Switching between views (All Bookmarks, Archived, Trash) triggers fresh API calls even when data hasn't changed. This creates unnecessary network traffic and slower perceived performance.

**Solution:** TanStack Query provides:
- Automatic caching with configurable stale times
- Background refetching when data might be stale
- Declarative cache invalidation on mutations
- Built-in loading/error states

**Documentation:** Read before implementing:
- https://tanstack.com/query/latest/docs/framework/react/overview
- https://tanstack.com/query/latest/docs/framework/react/guides/query-keys
- https://tanstack.com/query/latest/docs/framework/react/guides/invalidations-from-mutations
- https://tanstack.com/query/latest/docs/framework/react/guides/testing

---

## Design Decisions

### 1. Query Key Structure

```typescript
// For fetching - includes all params
['bookmarks', 'list', { view, q, tags, tag_match, sort_by, sort_order, offset, limit, list_id }]

// For invalidation by view
['bookmarks', 'active']
['bookmarks', 'archived']
['bookmarks', 'deleted']
['bookmarks', 'list']  // Invalidates all custom lists
```

### 2. Configuration

```typescript
{
  staleTime: 1000 * 60 * 5,        // 5 minutes
  gcTime: 1000 * 60 * 10,          // 10 minutes
  retry: 1,
  refetchOnWindowFocus: 'always',  // Always refetch on focus for multi-tab sync
}
```

**Why `refetchOnWindowFocus: 'always'`:** Ensures users always see fresh data when returning to a tab/window, even if another tab made changes within the staleTime window. The cost is one API call per focus event - negligible.

### 3. View Switching Behavior

- **Different view (e.g., All → Archived):** Show spinner if no cached data for that view
- **Pagination:** Show spinner when loading a different page (user clicked a button, expects new content)
- **Return to previously visited view:** Show cached data immediately, background refetch

### 4. Loading States

- **`isLoading`** = true when NO cached data exists (show spinner)
- **`isFetching`** = true during any fetch including background (optional subtle indicator)
- Never show spinner when cached data exists - use stale-while-revalidate pattern

### 5. Edit Modal Fetch

`fetchBookmark(id)` is NOT cached. Call API service directly. Cache miss rate would be high and we always want fresh data when editing.

### 6. Error Handling

Mutations throw errors, component catches and handles via `onError` callback or try/catch around `mutateAsync`. Keep `throwOnError: false` (default) for queries.

### 7. Undo Toast Pattern

Mutation hooks are called at component level. Toast callbacks use the returned `mutateAsync` function:
```typescript
const archiveMutation = useArchiveBookmark()
// In toast onClick:
() => archiveMutation.mutateAsync(id)
```

### 8. Tags Store Integration

Import `useTagsStore` directly in mutation hooks and call `fetchTags()` in `onSuccess` for mutations that might add/remove tags.

---

## User Experience Scenarios

### Scenario 1: First Visit to a View
**Action:** User opens app, views "All Bookmarks" for the first time
**Experience:** Spinner shown while data loads, then bookmarks appear
**Why:** No cached data exists (`isLoading: true`)

### Scenario 2: Switching Between Views (First Time)
**Action:** User switches from "All Bookmarks" to "Archived" (never visited before)
**Experience:** Spinner shown while archived data loads
**Why:** Different query key, no cache for "archived" yet

### Scenario 3: Switching Between Previously Visited Views
**Action:** User visited "All" and "Archived", now switches between them
**Experience:** Cached data shown immediately, background refetch happens silently
**Why:** Cache exists, `refetchOnWindowFocus: 'always'` triggers background update

### Scenario 4: Pagination Within a View
**Action:** User clicks "Next" to go to page 2
**Experience:** Spinner shown while page 2 loads, then new content appears
**Why:** User clicked a button expecting new content - spinner provides clear feedback

### Scenario 5: Return to Tab After Brief Absence
**Action:** User switches to another app for 30 seconds, returns
**Experience:** Cached data shown immediately, background refetch happens
**Why:** Focus event triggers refetch, but cached data displayed instantly (no spinner)

### Scenario 6: Multi-Tab Editing
**Action:** User has two tabs open. Edits bookmark in Tab A, switches to Tab B
**Experience:** Tab B shows cached data immediately, then updates when background fetch completes
**Why:** `refetchOnWindowFocus: 'always'` ensures fresh data on focus, stale-while-revalidate shows cached data first

### Scenario 7: Mutation with Undo
**Action:** User archives a bookmark, sees toast with "Undo" button
**Experience:** Bookmark disappears from list, toast appears. If Undo clicked, bookmark reappears
**Why:** Cache invalidation removes bookmark from "active" query, undo triggers unarchive mutation which invalidates both "active" and "archived"

### Scenario 8: Cache Expiration
**Action:** User leaves tab open but inactive for 15 minutes, then interacts
**Experience:** Cached data shown immediately (if within gcTime), background refetch updates it
**Why:** gcTime (10 min) controls when cache is garbage collected; staleTime (5 min) controls when background refetch happens

---

## Cache Invalidation Strategy

When a bookmark mutation occurs, invalidate caches as follows:

| Mutation | Invalidate |
|----------|-----------|
| Create bookmark | `['bookmarks', 'active']`, `['bookmarks', 'list']` (all custom lists) |
| Update bookmark | `['bookmarks', 'active']`, `['bookmarks', 'archived']`, `['bookmarks', 'list']` |
| Delete (soft) | `['bookmarks', 'active']`, `['bookmarks', 'deleted']`, `['bookmarks', 'list']` |
| Delete (permanent) | `['bookmarks', 'deleted']` |
| Archive | `['bookmarks', 'active']`, `['bookmarks', 'archived']`, `['bookmarks', 'list']` |
| Unarchive | `['bookmarks', 'active']`, `['bookmarks', 'archived']`, `['bookmarks', 'list']` |
| Restore | `['bookmarks', 'active']`, `['bookmarks', 'deleted']`, `['bookmarks', 'list']` |

**Note:** Custom lists are invalidated aggressively (all lists on any mutation) because determining which lists are affected by a bookmark's tags would add significant complexity. This is a reasonable tradeoff - lists will refetch in the background when accessed.

---

## Testing Approach

Use a fresh `QueryClient` per test to avoid cache pollution between tests. We test OUR invalidation logic, not TanStack Query itself.

```typescript
const createTestQueryClient = () => new QueryClient({
  defaultOptions: {
    queries: { retry: false },
    mutations: { retry: false },
  },
})

const wrapper = ({ children }) => (
  <QueryClientProvider client={createTestQueryClient()}>
    {children}
  </QueryClientProvider>
)
```

---

## Milestone 1: Install and Configure TanStack Query

### Goal
Set up TanStack Query infrastructure without changing existing functionality.

### Success Criteria
- `@tanstack/react-query` installed
- `QueryClientProvider` wraps the app
- React Query DevTools available in development
- Existing functionality unchanged

### Key Changes

1. **Install packages:**
   ```bash
   npm install @tanstack/react-query
   npm install -D @tanstack/react-query-devtools
   ```

2. **Create `src/lib/queryClient.ts`** with configuration from Design Decisions above

3. **Update `src/main.tsx`** - Wrap app with `QueryClientProvider`

4. **Add DevTools** - Include `ReactQueryDevtools` in development only

### Testing Strategy
- Verify app renders without errors
- Verify DevTools appear in development
- Run existing test suite to ensure nothing broke

### Dependencies
None

### Risk Factors
Low risk - additive change only

---

## Milestone 2: Create Bookmark Query Hook

### Goal
Create TanStack Query hook for fetching bookmarks, replacing the fetch logic in `useBookmarks`.

### Success Criteria
- `useBookmarksQuery` hook fetches and caches bookmark lists
- Query keys encode view, search, tags, sort, pagination (per structure above)
- Loading and error states work correctly
- Switching views uses cached data when available

### Key Changes

1. **Create `src/hooks/useBookmarksQuery.ts`** with:
   - Query key factory (`bookmarkKeys`) for consistent cache keys
   - Hook that accepts `BookmarkSearchParams` and returns query result
   - Properly distinguish `isLoading` vs `isFetching`

2. **Update `Bookmarks.tsx`**:
   - Use new query hook instead of `useBookmarks().fetchBookmarks`
   - Remove `clearAndSetLoading` pattern - rely on TanStack Query's loading states
   - Use `isLoading` for spinner (no cached data)
   - Optionally show subtle indicator for `isFetching && !isLoading` (background refresh)

3. **Keep mutation functions in `useBookmarks` temporarily** - Will migrate in Milestone 3

### Testing Strategy
- Test that switching views uses cached data (when cache exists)
- Test `isLoading` is true when no cache exists (first visit to a view)
- Test `isLoading` is true when pagination offset changes (spinner on page change)
- Test `isFetching` is true during background refetch (cache exists, refetching)
- Test error handling when API fails
- Test query keys properly differentiate between views/params

### Dependencies
Milestone 1

### Risk Factors
- Need to ensure debounced search value is used in query key (matches current behavior)

---

## Milestone 3: Create Bookmark Mutation Hooks

### Goal
Create TanStack Query mutation hooks for all bookmark operations with proper cache invalidation.

### Success Criteria
- All mutations (create, update, delete, archive, unarchive, restore) use TanStack mutations
- Cache is invalidated correctly after each mutation (per strategy table above)
- Tag store is refreshed after mutations that affect tags
- Undo functionality continues to work
- 409 conflict errors are thrown for component to handle

### Key Changes

1. **Create `src/hooks/useBookmarkMutations.ts`** with:
   - Hooks for each mutation type (useCreateBookmark, useUpdateBookmark, etc.)
   - Cache invalidation in `onSuccess` per strategy table
   - Import `useTagsStore` and call `fetchTags()` where appropriate
   - Mutations throw errors - component handles 409 conflicts

2. **Create invalidation helper:**
   ```typescript
   function invalidateBookmarkQueries(
     queryClient: QueryClient,
     views: Array<'active' | 'archived' | 'deleted' | 'lists'>
   ) { ... }
   ```

3. **Update `Bookmarks.tsx`**:
   - Replace mutation calls with new hooks
   - Call hooks at component level, use `mutateAsync` in callbacks
   - Handle 409 errors in component (existing logic for duplicate URL / archived URL)

### Testing Strategy
- Test each mutation invalidates correct query keys
- Test `mutateAsync` works in toast undo callbacks
- Test error handling for failed mutations
- Test 409 conflict handling still works
- Test tag suggestions update after adding bookmark with new tag

### Dependencies
Milestone 2

### Risk Factors
- Ensure undo toast callbacks have access to mutation functions (solved by calling hooks at component level)

---

## Milestone 4: Cleanup and Polish

### Goal
Remove old code, handle edge cases, ensure everything works smoothly.

### Success Criteria
- `useBookmarks.ts` removed or reduced to just `fetchMetadata` and `trackBookmarkUsage`
- No dead code remains
- All tests pass
- DevTools show expected caching behavior

### Key Changes

1. **Slim down or remove `useBookmarks.ts`**:
   - Keep `fetchMetadata` (not cached, on-demand for form)
   - Keep `trackBookmarkUsage` (fire-and-forget)
   - Remove everything else OR delete file and move utilities elsewhere

2. **Update/remove tests** - Replace `useBookmarks.test.ts` with tests for new hooks

3. **Clean up imports** - Remove unused imports from modified files

4. **Single bookmark fetch for edit modal** - Call API service directly (not cached)

### Testing Strategy
- Run full test suite
- Manual testing:
  - All CRUD operations (create, edit, delete, archive, unarchive, restore)
  - Undo functionality in toasts
  - Pagination shows spinner, loads new page
  - View switching uses cache when available
  - **Multi-tab sync:** Open two tabs, edit in Tab A, switch to Tab B, verify Tab B refreshes
  - **Window focus:** Switch to another app, return, verify background refetch happens
- Verify cache behavior in DevTools matches User Experience Scenarios

### Dependencies
Milestone 3

### Risk Factors
- Ensure no component still imports from deleted/modified hooks

---

## Summary of Files Changed

### New Files
- `src/lib/queryClient.ts` - Query client configuration
- `src/hooks/useBookmarksQuery.ts` - Query hook and key factory
- `src/hooks/useBookmarkMutations.ts` - Mutation hooks

### Modified Files
- `src/main.tsx` - Add QueryClientProvider
- `src/pages/Bookmarks.tsx` - Use new hooks

### Deleted/Reduced Files
- `src/hooks/useBookmarks.ts` - Removed or reduced to utilities only
- `src/hooks/useBookmarks.test.ts` - Replaced with new hook tests
