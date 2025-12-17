# Refactor Bookmark List Endpoint to Exclude Content

## Overview

The `GET /bookmarks/` endpoint currently returns the full `content` field (up to 500KB per bookmark) in list responses. This is wasteful since:
- The list UI only displays title, url, description, and tags
- Content is only needed when editing a bookmark
- A list of 50 bookmarks could return up to 25MB of unnecessary data

**Solution:** Create a lighter `BookmarkListItem` schema for list responses (without content), and have the frontend fetch the full bookmark via `GET /bookmarks/:id` when editing.

## Research Summary

### Backend Analysis
- `GET /bookmarks/` (list) uses `BookmarkResponse` which includes `content`
- `GET /bookmarks/:id` (single) already exists and returns full `BookmarkResponse` with content
- No other endpoints have similar issues:
  - `/lists/` - filter_expression is small
  - `/tags/` - only names and counts
  - `/tokens/` - correctly omits plaintext token in list

### Frontend Analysis
- `useBookmarks` hook has no `fetchBookmark(id)` function
- Edit modal receives bookmark object from list via `setEditingBookmark(bookmark)`
- `BookmarkForm` uses `bookmark?.content` to populate the content textarea
- Flow: Click edit → pass bookmark from list → open modal with full data

### Current Data Flow
```
List View → Click Edit → Pass bookmark from state → Open Modal
```

### Proposed Data Flow
```
List View → Click Edit → Fetch full bookmark by ID → Open Modal
```

---

## Milestone 1: Backend Schema Changes

### Goal
Create a `BookmarkListItem` schema without `content` field and use it for list responses.

### Success Criteria
- `GET /bookmarks/` returns items without `content` field
- `GET /bookmarks/:id` continues to return full `BookmarkResponse` with `content`
- All existing backend tests pass (with necessary updates)

### Key Changes

**`backend/src/schemas/bookmark.py`:**
```python
class BookmarkListItem(BaseModel):
    """Schema for bookmark list items (excludes content for performance)."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    title: str | None
    description: str | None
    summary: str | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime
    deleted_at: datetime | None = None
    archived_at: datetime | None = None
    # Note: content intentionally excluded for list performance


class BookmarkListResponse(BaseModel):
    """Schema for paginated bookmark list responses."""
    items: list[BookmarkListItem]  # Changed from BookmarkResponse
    total: int
    offset: int
    limit: int
    has_more: bool
```

**`backend/src/api/routers/bookmarks.py`:**
- Update `list_bookmarks` to use `BookmarkListItem` in the response construction

### Testing Strategy
- Update any tests that assert on `content` field presence in list responses
- Verify `GET /bookmarks/:id` still returns `content`
- Add test confirming list items don't include `content`

### Dependencies
None

### Risk Factors
- Tests may need updates if they check for `content` in list responses

---

## Milestone 2: Frontend Type Updates

### Goal
Update TypeScript types to reflect the new API response structure.

### Success Criteria
- Types accurately represent list items (no content) vs full bookmark (with content)
- No TypeScript errors after changes

### Key Changes

**`frontend/src/types.ts`:**
```typescript
/** Bookmark item in list responses (excludes content for performance) */
export interface BookmarkListItem {
  id: number
  url: string
  title: string | null
  description: string | null
  summary: string | null
  tags: string[]
  created_at: string
  updated_at: string
  last_used_at: string
  deleted_at: string | null
  archived_at: string | null
}

/** Full bookmark data (includes content) - returned by GET /bookmarks/:id */
export interface Bookmark extends BookmarkListItem {
  content: string | null
}

/** Paginated list response from GET /bookmarks/ */
export interface BookmarkListResponse {
  items: BookmarkListItem[]  // Changed from Bookmark[]
  total: number
  offset: number
  limit: number
  has_more: boolean
}
```

### Testing Strategy
- TypeScript compiler will catch any type mismatches
- Run `npm run lint` to verify

### Dependencies
- Milestone 1 (backend changes)

### Risk Factors
- Components accessing `content` from list items will get compile errors (expected - guides us to fix them)

---

## Milestone 3: Frontend Hook and Edit Flow

### Goal
Add `fetchBookmark(id)` to the `useBookmarks` hook and update the edit flow to fetch full bookmark before opening modal.

### Success Criteria
- `fetchBookmark(id)` function available in hook
- Edit button shows loading spinner while fetching
- Modal opens only after fetch completes with full bookmark data
- Errors handled gracefully (toast notification)

### UX Design Decision
**Option chosen: Wait then open**
- Show small spinner on/near the edit button while fetching
- Fetch completes → open modal with all data
- Simpler implementation, and delay is minimal (~100ms for single bookmark fetch)

### Key Changes

**`frontend/src/hooks/useBookmarks.ts`:**
```typescript
// Add to UseBookmarksReturn interface:
fetchBookmark: (id: number) => Promise<Bookmark>

// Add implementation:
const fetchBookmark = useCallback(async (id: number): Promise<Bookmark> => {
  const response = await api.get<Bookmark>(`/bookmarks/${id}`)
  return response.data
}, [])
```

**`frontend/src/pages/Bookmarks.tsx`:**
- Add `loadingBookmarkId: number | null` state to track which bookmark is being fetched
- When edit is clicked:
  1. Set `loadingBookmarkId` to the bookmark's ID
  2. Call `fetchBookmark(id)`
  3. On success: set `editingBookmark` with full data, clear `loadingBookmarkId`
  4. On error: show toast, clear `loadingBookmarkId`
- Pass `loadingBookmarkId` to `BookmarkCard` to show spinner on edit button

**`frontend/src/components/BookmarkCard.tsx`:**
- Add `isLoading?: boolean` prop
- When `isLoading` is true, show spinner instead of edit icon (or disable button with spinner)

### Testing Strategy
- Test `fetchBookmark` returns full bookmark with content
- Test edit button shows loading state while fetching
- Test modal opens only after fetch completes
- Test error handling when fetch fails (toast shown, loading cleared)

### Dependencies
- Milestone 2 (type updates)

### Risk Factors
- Need to handle race conditions if user clicks edit on different bookmarks quickly (use `loadingBookmarkId` to track)

---

## Milestone 4: Component Updates and Cleanup

### Goal
Update any components that incorrectly assume `content` is available on list items.

### Success Criteria
- All components work correctly with new types
- No runtime errors when accessing bookmark properties
- Edit functionality works end-to-end

### Key Changes

**`frontend/src/components/BookmarkCard.tsx`:**
- Verify it doesn't access `content` (it shouldn't for display)
- Update type annotation if needed to use `BookmarkListItem`

**`frontend/src/pages/Bookmarks.tsx`:**
- Update `bookmarks` state type to `BookmarkListItem[]`
- Ensure `editingBookmark` is typed as `Bookmark | null` (full type)

### Testing Strategy
- Run full test suite
- Manual testing of list view, edit flow, create flow
- Verify content displays correctly in edit modal

### Dependencies
- Milestone 3 (hook updates)

### Risk Factors
- May discover additional components that need updates

---

## Summary

| Milestone | Component | Changes |
|-----------|-----------|---------|
| 1 | Backend | New `BookmarkListItem` schema, update list endpoint |
| 2 | Frontend Types | Split `Bookmark` into list item and full types |
| 3 | Frontend Hook | Add `fetchBookmark(id)`, update edit flow |
| 4 | Frontend Components | Update type annotations, verify functionality |

## Other Endpoints

**No other endpoints have similar issues:**
- `GET /lists/` - Returns `filter_expression` which is small JSON
- `GET /tags/` - Returns only tag names and counts
- `GET /tokens/` - Correctly excludes plaintext token in list (only in create response)

The bookmarks endpoint is the only one returning unnecessarily large payloads.
