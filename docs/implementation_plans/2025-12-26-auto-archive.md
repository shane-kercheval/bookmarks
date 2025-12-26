# Auto-Archive Feature Implementation Plan

## Overview

Add the ability to schedule bookmarks for automatic archiving at a future date. Users can set an `archived_at` date in the future when creating or editing a bookmark, and the bookmark will automatically appear in the archived view once that date passes.

### Key Design Decision

Rather than adding a separate `auto_archive_at` field and background job, we reuse the existing `archived_at` column with future dates. The "is archived" check changes from `archived_at IS NOT NULL` to `archived_at IS NOT NULL AND archived_at <= NOW()`. This is implemented via a SQLAlchemy `hybrid_property` on the Bookmark model for centralized, consistent logic.

**Rationale**: Avoids infrastructure complexity (no cron jobs, schedulers, or background workers). The datetime comparison is evaluated at query time by PostgreSQL, providing instant "archiving" when the scheduled time passes.

### Design Decision: No Validation on `archived_at` Dates

We intentionally do **not** validate that `archived_at` is in the future when creating/updating bookmarks. If a user sets a past date, the bookmark simply appears in the archived view immediately - functionally equivalent to using the archive endpoint. This avoids:
- Extra validation code in schemas
- Additional test cases for validation errors
- A confusing UX where setting a past date errors instead of just working

Future dates schedule auto-archive; past dates result in immediate archiving. Both are valid use cases.

---

## Milestone 1: Backend - Add `is_archived` Hybrid Property

### Goal
Add a `hybrid_property` to the Bookmark model that centralizes the "is archived" logic, supporting both future-dated auto-archive and immediate archive.

### Success Criteria
- `Bookmark.is_archived` works at Python level (instance check)
- `Bookmark.is_archived` works at SQL level (query expressions)
- All existing tests pass without modification
- New tests cover the hybrid property behavior

### Key Changes

**1. Update `backend/src/models/bookmark.py`:**

```python
from datetime import datetime, timezone
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy import and_

class Bookmark(Base, TimestampMixin):
    # ... existing fields ...

    @hybrid_property
    def is_archived(self) -> bool:
        """Check if bookmark is currently archived (past or present archived_at)."""
        if self.archived_at is None:
            return False
        # Handle both timezone-aware and naive datetimes
        now = datetime.now(timezone.utc)
        archived_at = self.archived_at
        if archived_at.tzinfo is None:
            archived_at = archived_at.replace(tzinfo=timezone.utc)
        return archived_at <= now

    @is_archived.expression
    def is_archived(cls):
        """SQL expression for archived check."""
        return and_(
            cls.archived_at.is_not(None),
            cls.archived_at <= func.now()
        )
```

### Testing Strategy
- Test `is_archived` returns `False` when `archived_at` is `None`
- Test `is_archived` returns `True` when `archived_at` is in the past
- Test `is_archived` returns `False` when `archived_at` is in the future
- Test SQL expression generates correct query (check query string or use explain)
- Test edge case: `archived_at` exactly equal to now

### Dependencies
None - this is the foundation for subsequent milestones.

### Risk Factors
- Timezone handling between Python and PostgreSQL must be consistent
- The model uses `DateTime(timezone=True)`, so PostgreSQL stores as `timestamptz`

---

## Milestone 2: Backend - Update Service Layer to Use `is_archived`

### Goal
Replace all direct `archived_at` null checks with the new `is_archived` hybrid property throughout the service layer.

### Success Criteria
- All archive-related filtering uses `Bookmark.is_archived`
- Existing tests pass (behavior unchanged for immediate archives)
- New tests verify future-dated bookmarks appear in correct views

### Key Changes

**1. Update `backend/src/services/bookmark_service.py`:**

| Line | Current | Change To |
|------|---------|-----------|
| 164 | `existing.archived_at is not None` | `existing.is_archived` |
| 232 | `Bookmark.archived_at.is_(None)` | `Bookmark.is_archived == False` |
| 291 | `Bookmark.archived_at.is_(None)` | `Bookmark.is_archived == False` |
| 297 | `Bookmark.archived_at.is_not(None)` | `Bookmark.is_archived == True` |
| 610 | `Bookmark.archived_at.is_not(None)` | `Bookmark.is_archived == True` |

**Keep unchanged** (these SET the value, not check it):
- Line 574-575: `bookmark.archived_at = func.now()`
- Line 538: `bookmark.archived_at = None`
- Line 622: `bookmark.archived_at = None`

**2. Update `backend/src/services/tag_service.py`:**

| Line | Current | Change To |
|------|---------|-----------|
| 101 | `Bookmark.archived_at.is_(None)` | `Bookmark.is_archived == False` |
| 122 | `Bookmark.archived_at.is_(None)` | `Bookmark.is_archived == False` |

### Testing Strategy
- Test bookmark with future `archived_at` appears in "active" view
- Test bookmark with past `archived_at` appears in "archived" view
- Test bookmark transitions from "active" to "archived" when time passes (mock `func.now()`)
- Test `_check_url_exists` correctly identifies future-scheduled bookmarks as not-yet-archived
- Test tag counts exclude future-scheduled (not-yet-archived) bookmarks

### Dependencies
Milestone 1 (hybrid property must exist)

### Risk Factors
- Must find ALL locations that check archive status
- Run `grep -n "archived_at" backend/src/services/` to verify completeness

---

## Milestone 3: Backend - Update Schemas and API for Auto-Archive

### Goal
Allow setting `archived_at` to a future date when creating or updating bookmarks.

### Success Criteria
- `BookmarkCreate` and `BookmarkUpdate` schemas accept `archived_at`
- Service layer passes `archived_at` through to the model
- Response schemas already include `archived_at` (no change needed)

### Key Changes

**1. Update `backend/src/schemas/bookmark.py`:**

```python
class BookmarkCreate(BaseModel):
    # ... existing fields ...
    archived_at: datetime | None = None

class BookmarkUpdate(BaseModel):
    # ... existing fields ...
    archived_at: datetime | None = None
```

No validation needed - if the user sets a past date, the bookmark simply appears in the archived view immediately (same as using the archive endpoint). Future dates schedule auto-archive.

**2. Update `backend/src/services/bookmark_service.py` - `create_bookmark` and `update_bookmark`:**

Pass through `archived_at` from the schema to the model. The service functions likely already handle arbitrary fields, but verify.

### Testing Strategy
- Test creating bookmark with future `archived_at` - appears in active view
- Test creating bookmark with past `archived_at` - appears in archived view
- Test updating bookmark to set `archived_at` succeeds
- Test updating bookmark to clear `archived_at` (set to None) succeeds

### Dependencies
Milestone 2 (service layer must use `is_archived`)

### Risk Factors
- Timezone handling in validation must match database storage
- Consider whether manually archived bookmarks (via `/archive` endpoint) should clear any scheduled date

---

## Milestone 4: Frontend - Add Auto-Archive Date Picker to Form

### Goal
Add a date/time picker to the bookmark form for scheduling auto-archive.

### Success Criteria
- Users can select a future date for auto-archive when creating/editing
- Quick presets available: "1 week", "1 month", "End of month"
- Can clear the scheduled date

### Key Changes

**1. Update `frontend/src/types.ts`:**

```typescript
export interface BookmarkCreate {
  // ... existing fields ...
  archived_at?: string | null  // ISO 8601 datetime string
}

export interface BookmarkUpdate {
  // ... existing fields ...
  archived_at?: string | null
}
```

**2. Update `frontend/src/components/BookmarkForm.tsx`:**

Add new form state and field:
- Add `archivedAt: string` to `FormState`
- Add dropdown below Content field with label "Auto-archive"
- Include `archived_at` in submit payload

**UI Pattern**:
```
Auto-archive
[Dropdown: None | 1 week | 1 month | End of month | Custom ▼]

[If "Custom" selected, show <input type="datetime-local"> below]
```

**Preset calculations** (default to 8:00 AM user's local time):
- "1 week": 7 days from now, 8:00 AM
- "1 month": Same day next month, 8:00 AM
- "End of month": Last day of current month, 8:00 AM
- "Custom": Show native datetime-local picker

**Timezone handling**:
- Native `datetime-local` input works in user's local timezone
- Convert to ISO 8601 UTC string before sending: `new Date(localValue).toISOString()`
- Backend stores as `timestamptz` (UTC)
- Display uses existing `formatDate` utility which converts to local time

### Testing Strategy
- Test form displays current `archived_at` when editing
- Test selecting a date updates form state
- Test quick presets calculate correct dates
- Test "Clear" removes the scheduled date
- Test past date shows validation error
- Test submit includes `archived_at` in payload

### Dependencies
Milestone 3 (API must accept `archived_at`)

### Risk Factors
- Date picker UX varies by browser for native inputs
- Timezone display: show in user's local time, send as UTC/ISO

---

## Milestone 5: Frontend - Display Scheduled Archive Status

### Goal
Show users when a bookmark is scheduled for auto-archive.

### Success Criteria
- Active bookmarks with future `archived_at` show scheduled date
- Display is concise and doesn't clutter the card

### Key Changes

**1. Update `frontend/src/components/BookmarkCard.tsx`:**

Current date display location (line 344-346):
```typescript
<span className="text-xs text-gray-400">
  {getDateDisplay()}  // "Created: Jan 15, 2025"
</span>
```

**Add second line when scheduled** (active view only):
```typescript
<span className="text-xs text-gray-400">
  {getDateDisplay()}
</span>
{/* Show scheduled archive date if set and in the future */}
{view === 'active' && bookmark.archived_at && new Date(bookmark.archived_at) > new Date() && (
  <span className="text-xs text-amber-600 flex items-center gap-1">
    <ClockIcon className="w-3 h-3" />
    Archiving: {formatDate(bookmark.archived_at)}
  </span>
)}
```

**Result**: Two lines in bottom-right when scheduled:
```
Created: Jan 15, 2025
🕐 Archiving: Feb 1, 2025
```

### Testing Strategy
- Test bookmark with future `archived_at` shows "Archiving: [date]"
- Test bookmark with past/null `archived_at` shows only the sort-based date
- Test scheduled indicator only appears in active view (not archived/deleted)

### Dependencies
Milestone 4 (form changes should be complete first)

### Risk Factors
- Client/server time skew could cause brief inconsistencies
- Decide whether to show scheduled date in active view only, or also hint in archived view

---

## Milestone 6: Edge Cases and Polish

### Goal
Handle edge cases and improve UX for the complete feature.

### Success Criteria
- Archive endpoint clears scheduled date (archiving now supersedes schedule)
- Unarchive endpoint clears `archived_at` entirely (returns to active, no schedule)
- Restore from trash clears `archived_at` (existing behavior, verify)
- Clear documentation of the feature

### Key Changes

**1. Update `archive_bookmark` service function:**

When manually archiving, set `archived_at = func.now()` regardless of any existing future date. Current implementation already does this.

**2. Verify `unarchive_bookmark` behavior:**

Should clear `archived_at` entirely (not just set to future). Current implementation already does this.

**3. Verify `restore_bookmark` behavior:**

Should clear both `deleted_at` and `archived_at`. Current implementation already does this.

**4. Add user-facing documentation** (if applicable) explaining auto-archive feature.

### Testing Strategy
- Test archiving a bookmark with future `archived_at` sets it to now
- Test unarchiving clears `archived_at` completely
- Test restoring clears both timestamps
- End-to-end test: create with schedule -> verify in active -> archive manually -> verify in archived with new date

### Dependencies
All previous milestones

### Risk Factors
- Ensure no regression in existing archive/unarchive/restore flows

---

## Summary

| Milestone | Component | Effort |
|-----------|-----------|--------|
| 1 | Hybrid Property | Small |
| 2 | Service Layer Updates | Medium |
| 3 | Schema/API Updates | Small |
| 4 | Frontend Form | Medium |
| 5 | Frontend Display | Small |
| 6 | Edge Cases | Small |

Total: 6 milestones, can be completed incrementally with human review after each.
