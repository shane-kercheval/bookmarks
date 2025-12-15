# Implementation Plan: Extend fetch-metadata to Return Content

## Overview

Extend the `/bookmarks/fetch-metadata` endpoint to optionally extract and return page content, and add UI to display/copy this content in the Add Bookmark form.

## Milestone 1: Backend - Add Content to fetch-metadata

**Goal**: Extend the fetch-metadata endpoint to optionally return extracted page content.

**Success Criteria**:
- `GET /bookmarks/fetch-metadata?url=...&include_content=true` returns content field
- `GET /bookmarks/fetch-metadata?url=...` (default) does NOT return content (backward compatible)
- Existing tests pass without modification

**Key Changes**:

1. **Update `MetadataPreviewResponse` schema** (`backend/src/schemas/bookmark.py`):
   ```python
   class MetadataPreviewResponse(BaseModel):
       url: str
       final_url: str | None = None
       title: str | None = None
       description: str | None = None
       content: str | None = None  # Add this field
       error: str | None = None
   ```

2. **Update fetch-metadata endpoint** (`backend/src/api/routers/bookmarks.py`):
   - Add `include_content: bool = False` query parameter
   - When `include_content=True`, call `extract_content(html)` and include in response
   - When `False`, omit content (or set to `None`)

**Testing Strategy**:
- Add test: `test__fetch_metadata__with_include_content_true__returns_content`
- Add test: `test__fetch_metadata__with_include_content_false__no_content` (verify backward compat)
- Verify existing `test__fetch_metadata__*` tests still pass

**Dependencies**: None

**Risk Factors**:
- `extract_content()` adds processing time - acceptable for single-URL preview use case

---

## Milestone 2: Frontend - Display Content in Add Bookmark Form

**Goal**: Show extracted content in a collapsible section with copy functionality.

**Success Criteria**:
- Clicking "Fetch Metadata" also fetches content
- Content appears in a collapsible/expandable section below the form
- User can copy content to clipboard with a button
- Content preview is read-only (not editable)

**Key Changes**:

1. **Update API service** (`frontend/src/services/api.ts` or similar):
   - Update `fetchMetadata` call to include `include_content=true` parameter
   - Update response type to include `content: string | null`

2. **Update BookmarkForm component** (`frontend/src/components/BookmarkForm.tsx`):
   - Store fetched content in component state
   - Add collapsible section (e.g., `<details>`/`<summary>` or custom accordion)
   - Add "Copy Content" button using `navigator.clipboard.writeText()`
   - Clear content state when URL changes or form resets

**Testing Strategy**:
- Test that content state is populated after metadata fetch
- Test copy button functionality (if feasible in test environment)
- Test content clears on URL change

**Dependencies**: Milestone 1 must be complete

**Risk Factors**:
- Large content could make the form unwieldy - consider max-height with scroll
- Copy to clipboard requires HTTPS in production (should already be the case)

---

## Implementation Notes

- The `extract_content()` function already exists in `backend/src/services/url_scraper.py` using trafilatura
- No database changes required - this is preview-only functionality
- Content field already exists on Bookmark model for storage (separate from this feature)
