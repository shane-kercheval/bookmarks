# Implementation Plan: Settings Page and Lists Feature

## Overview

Add a Settings page with:
1. Personal Access Token (PAT) management
2. Custom "Lists" - saved bookmark collections based on tag filters with AND/OR boolean logic
3. Tab ordering - ability to reorder all tabs including built-in ones (All Bookmarks, Archived, Trash)

---

## Confirmed Design Decisions

1. **List Filter UI**: Visual builder with "Add Group" / "Add Tag" buttons
   - Each group uses AND logic internally
   - Groups are combined with OR
   - Example: `(my_work AND high_priority) OR (critical)`

2. **Tab Ordering**: All tabs fully reorderable
   - Custom lists, "All Bookmarks", "Archived", and "Trash" can all be reordered
   - Default order: `[All Bookmarks] [Archived] [Trash]` with new lists appearing at the start

3. **List Contents**: Filter active bookmarks only (not archived or deleted)

4. **Settings Navigation**: Gear icon in header, next to logout button

---

## Architecture Decisions

### List Filter Expression Storage

Store as JSON in PostgreSQL with a simple schema supporting AND groups combined by OR:

```python
# Database storage format
{
    "groups": [
        {"tags": ["my_work", "high_priority"], "operator": "AND"},
        {"tags": ["critical"], "operator": "AND"}
    ],
    "group_operator": "OR"  # How groups combine
}

# Evaluates to: (my_work AND high_priority) OR (critical)
```

This format:
- Supports all reasonable use cases
- Easy to build UI for (add group, add tag to group)
- Easy to translate to SQL WHERE clause
- Extensible for future enhancements

### Tab Order Storage

Add a `UserSettings` model for user preferences including tab order:

```python
class UserSettings:
    user_id: int (PK, FK)
    tab_order: JSON  # ["list:1", "all", "list:2", "archived", "trash"]
    created_at, updated_at
```

Special tab identifiers:
- `"all"` - All Bookmarks
- `"archived"` - Archived
- `"trash"` - Trash
- `"list:{id}"` - Custom list by ID

---

## Milestone 1: Backend - User Settings Model

### Goal
Create the UserSettings model for storing user preferences (tab order, future settings).

### Success Criteria
- UserSettings model with one-to-one User relationship
- Migration runs successfully
- CRUD operations work in tests

### Key Changes

1. **Create `backend/src/models/user_settings.py`**
```python
class UserSettings(Base, TimestampMixin):
    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    tab_order: Mapped[list | None] = mapped_column(JSONB, nullable=True)  # null = default order

    user: Mapped["User"] = relationship("User", back_populates="settings")
```

2. **Update `backend/src/models/user.py`** - Add settings relationship

3. **Create migration** for user_settings table

4. **Create `backend/src/schemas/user_settings.py`**
```python
class UserSettingsUpdate(BaseModel):
    tab_order: list[str] | None  # ["all", "list:1", "archived", "trash"]

class UserSettingsResponse(BaseModel):
    tab_order: list[str] | None
    updated_at: datetime
```

### Testing Strategy
- Test model creation and relationship with User
- Test JSON storage/retrieval for tab_order
- Test cascade delete when user is deleted

### Dependencies
None

### Risk Factors
- JSONB type compatibility with SQLAlchemy 2.0 (low risk - well documented)

---

## Milestone 2: Backend - List Model and CRUD

### Goal
Create the List model and service layer for custom bookmark lists.

### Success Criteria
- List model with filter expression storage
- Full CRUD operations via service
- Proper user scoping (multi-tenant)

### Key Changes

1. **Create `backend/src/models/list.py`**
```python
class List(Base, TimestampMixin):
    __tablename__ = "lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    filter_expression: Mapped[dict] = mapped_column(JSONB, nullable=False)
    display_order: Mapped[int] = mapped_column(default=0)  # Lower = earlier in list

    user: Mapped["User"] = relationship("User", back_populates="lists")
```

2. **Create migration** for lists table

3. **Create `backend/src/schemas/list.py`**
```python
class FilterGroup(BaseModel):
    tags: list[str]
    operator: Literal["AND"] = "AND"

class FilterExpression(BaseModel):
    groups: list[FilterGroup]
    group_operator: Literal["OR"] = "OR"

class ListCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    filter_expression: FilterExpression

class ListUpdate(BaseModel):
    name: str | None = None
    filter_expression: FilterExpression | None = None
    display_order: int | None = None

class ListResponse(BaseModel):
    id: int
    name: str
    filter_expression: FilterExpression
    display_order: int
    created_at: datetime
    updated_at: datetime
```

4. **Create `backend/src/services/list_service.py`**
   - `create_list(db, user_id, data)` - Create new list
   - `get_lists(db, user_id)` - Get all lists for user (ordered by display_order)
   - `get_list(db, user_id, list_id)` - Get single list
   - `update_list(db, user_id, list_id, data)` - Update list
   - `delete_list(db, user_id, list_id)` - Delete list
   - `reorder_lists(db, user_id, list_ids)` - Bulk update display_order

### Testing Strategy
- Test CRUD operations with proper user scoping
- Test filter expression validation (valid tags, proper structure)
- Test display_order updates on reorder
- Test cascade delete when user deleted
- Test invalid filter expressions are rejected

### Dependencies
- Milestone 1 (UserSettings for tab ordering context, though not strictly required)

### Risk Factors
- Filter expression validation complexity (medium - use Pydantic)

---

## Milestone 3: Backend - List API Endpoints

### Goal
Create REST API endpoints for list management and settings.

### Success Criteria
- Full REST API for lists (CRUD + reorder)
- Settings endpoints for tab order
- Endpoints properly authenticated and user-scoped

### Key Changes

1. **Create `backend/src/api/routers/lists.py`**
```python
@router.post("/", response_model=ListResponse)
async def create_list(data: ListCreate, ...)

@router.get("/", response_model=list[ListResponse])
async def get_lists(...)

@router.get("/{list_id}", response_model=ListResponse)
async def get_list(list_id: int, ...)

@router.patch("/{list_id}", response_model=ListResponse)
async def update_list(list_id: int, data: ListUpdate, ...)

@router.delete("/{list_id}", status_code=204)
async def delete_list(list_id: int, ...)

@router.post("/reorder", status_code=204)
async def reorder_lists(list_ids: list[int], ...)
```

2. **Create `backend/src/api/routers/settings.py`**
```python
@router.get("/", response_model=UserSettingsResponse)
async def get_settings(...)  # Returns settings or defaults if none exist

@router.patch("/", response_model=UserSettingsResponse)
async def update_settings(data: UserSettingsUpdate, ...)

@router.get("/tab-order", response_model=TabOrderResponse)
async def get_tab_order(...)  # Computed tab order including lists
```

3. **Register routers in `backend/src/api/main.py`**

### Testing Strategy
- Test all endpoints with authenticated user
- Test 404 for non-existent lists
- Test 403/404 for lists belonging to other users
- Test reorder endpoint with valid and invalid list IDs
- Test settings creation on first access

### Dependencies
- Milestone 2 (List model and service)

### Risk Factors
- Tab order computation with dynamic list IDs (medium - handle missing lists gracefully)

---

## Milestone 4: Backend - List Bookmark Query

### Goal
Implement querying bookmarks by list filter expression.

### Success Criteria
- Bookmarks can be filtered by list ID
- Filter expression correctly evaluates AND/OR logic
- Performance is acceptable with proper indexes

### Key Changes

1. **Extend `backend/src/services/bookmark_service.py`**
   - Add `list_id` parameter to `search_bookmarks()`
   - Build dynamic WHERE clause from filter expression:
```python
def _build_filter_from_expression(expression: dict):
    """
    Converts: {"groups": [{"tags": ["a", "b"]}, {"tags": ["c"]}], "group_operator": "OR"}
    To: (tags @> ARRAY['a', 'b']) OR (tags @> ARRAY['c'])
    """
```

2. **Update `backend/src/api/routers/bookmarks.py`**
   - Add optional `list_id: int | None` query parameter
   - Validate list belongs to user before filtering

3. **Ensure GIN index on tags** (already exists, verify)

### Testing Strategy
- Test AND logic: bookmark must have ALL tags in group
- Test OR logic: bookmark matches if ANY group matches
- Test empty groups (edge case)
- Test non-existent tags (should return no matches for that group)
- Test with real bookmarks and various tag combinations
- Test performance with many bookmarks

### Dependencies
- Milestone 2 (List model)
- Milestone 3 (API endpoints for list retrieval)

### Risk Factors
- SQL injection via dynamic query building (mitigate: use parameterized queries)
- Performance with complex expressions (mitigate: limit groups/tags per list)

---

## Milestone 5: Frontend - Settings Page Structure

### Goal
Create the Settings page with routing and basic structure.

### Success Criteria
- Settings page accessible via navigation
- Tab-based layout for different settings sections
- Responsive design matching existing UI

### Key Changes

1. **Create `frontend/src/pages/Settings.tsx`**
   - Tab layout: "Personal Access Tokens" | "Lists" | "Display"
   - Each tab renders corresponding component

2. **Update `frontend/src/App.tsx`**
   - Add route: `/settings` → Settings page (protected)

3. **Update `frontend/src/components/Layout.tsx`**
   - Add gear icon button next to logout button
   - Icon links to `/settings` route

4. **Create base components**
   - `frontend/src/components/settings/SettingsLayout.tsx` - Tab container
   - `frontend/src/components/settings/TokensSettings.tsx` - Placeholder
   - `frontend/src/components/settings/ListsSettings.tsx` - Placeholder
   - `frontend/src/components/settings/DisplaySettings.tsx` - Placeholder

### Testing Strategy
- Test routing to settings page
- Test tab switching
- Test navigation from header menu
- Test protected route (redirects if not authenticated)

### Dependencies
None (frontend-only)

### Risk Factors
- None significant

---

## Milestone 6: Frontend - PAT Management UI

### Goal
Implement full PAT management in Settings page.

### Success Criteria
- List existing tokens with metadata
- Create new token with name and optional expiration
- Show token ONCE on creation (copy button)
- Delete/revoke tokens with confirmation

### Key Changes

1. **Create `frontend/src/hooks/useTokens.ts`**
```typescript
export function useTokens() {
  const [tokens, setTokens] = useState<Token[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchTokens = async () => {...}
  const createToken = async (name: string, expiresInDays?: number) => {...}
  const deleteToken = async (id: number) => {...}

  return { tokens, loading, fetchTokens, createToken, deleteToken };
}
```

2. **Create `frontend/src/types/token.ts`** (or add to types.ts)
```typescript
interface Token {
  id: number;
  name: string;
  token_prefix: string;
  last_used_at: string | null;
  expires_at: string | null;
  created_at: string;
}

interface TokenCreateResponse extends Token {
  token: string;  // Only on creation
}
```

3. **Implement `frontend/src/components/settings/TokensSettings.tsx`**
   - Token list table with columns: Name, Prefix, Last Used, Expires, Actions
   - "Create Token" button → modal
   - Delete button with confirmation dialog
   - Empty state when no tokens

4. **Create `frontend/src/components/settings/CreateTokenModal.tsx`**
   - Name input (required)
   - Expiration dropdown (Never, 30 days, 90 days, 1 year, Custom)
   - After creation: show token with copy button, warning it won't be shown again

### Testing Strategy
- Test token list rendering
- Test create flow including token display
- Test delete with confirmation
- Test empty state
- Test loading states
- Test error handling (API failures)

### Dependencies
- Milestone 5 (Settings page structure)
- Backend token endpoints (already exist)

### Risk Factors
- Secure token display UX (ensure copy works, clear warning)

---

## Milestone 7: Frontend - Lists Management UI

### Goal
Implement list creation, editing, and deletion in Settings.

### Success Criteria
- List all custom lists with filter preview
- Create/edit list with visual filter builder
- Delete list with confirmation
- Reorder lists via drag-and-drop or arrows

### Key Changes

1. **Create `frontend/src/hooks/useLists.ts`**
```typescript
export function useLists() {
  const fetchLists = async () => {...}
  const createList = async (data: ListCreate) => {...}
  const updateList = async (id: number, data: ListUpdate) => {...}
  const deleteList = async (id: number) => {...}
  const reorderLists = async (listIds: number[]) => {...}

  return { lists, loading, ...methods };
}
```

2. **Create `frontend/src/types/list.ts`**
```typescript
interface FilterGroup {
  tags: string[];
  operator: 'AND';
}

interface FilterExpression {
  groups: FilterGroup[];
  group_operator: 'OR';
}

interface List {
  id: number;
  name: string;
  filter_expression: FilterExpression;
  display_order: number;
  created_at: string;
  updated_at: string;
}
```

3. **Implement `frontend/src/components/settings/ListsSettings.tsx`**
   - List of custom lists with name and filter preview
   - "Create List" button
   - Edit/Delete actions per list
   - Drag-and-drop or up/down arrows for reordering

4. **Create `frontend/src/components/settings/ListFormModal.tsx`**
   - Name input
   - Visual filter builder (see below)
   - Preview of matching bookmark count (optional enhancement)

5. **Create `frontend/src/components/settings/FilterBuilder.tsx`**
   - Visual component for building filter expressions
   - "Add Group" button - creates new OR group
   - Each group has tag multiselect with "AND" label
   - Remove group/tag buttons
   - Human-readable preview: "(work AND priority) OR (urgent)"

### Testing Strategy
- Test list CRUD operations
- Test filter builder produces correct expression
- Test reordering updates display_order
- Test validation (name required, at least one tag)
- Test with existing tags from useTags hook

### Dependencies
- Milestone 5 (Settings page)
- Milestone 3 (Backend list endpoints)
- useTags hook for tag suggestions

### Risk Factors
- Filter builder UX complexity (mitigate: keep it simple with AND groups + OR)
- Drag-and-drop library choice (recommend @dnd-kit or react-beautiful-dnd)

---

## Milestone 8: Frontend - Tab Order Settings

### Goal
Implement tab ordering in Display settings section.

### Success Criteria
- Show all tabs in current order (lists + built-in)
- Reorder via drag-and-drop
- Changes persist and apply immediately

### Key Changes

1. **Create `frontend/src/hooks/useSettings.ts`**
```typescript
export function useSettings() {
  const fetchSettings = async () => {...}
  const updateTabOrder = async (order: string[]) => {...}

  return { settings, loading, updateTabOrder };
}
```

2. **Implement `frontend/src/components/settings/DisplaySettings.tsx`**
   - "Tab Order" section
   - Draggable list of all tabs
   - Labels for built-in tabs (All Bookmarks, Archived, Trash)
   - Labels for custom lists by name
   - Reset to default button

3. **Create shared drag-and-drop list component** (reuse with ListsSettings if similar)

### Testing Strategy
- Test rendering tabs in correct order
- Test drag-and-drop reordering
- Test persistence after page reload
- Test reset to default

### Dependencies
- Milestone 7 (Lists must exist to appear in order)
- Milestone 3 (Settings backend endpoints)

### Risk Factors
- Syncing list deletion with tab order (handle missing list IDs gracefully)

---

## Milestone 9: Frontend - Tabs Integration

### Goal
Update the main Bookmarks page to show custom lists as tabs and respect tab order.

### Success Criteria
- Custom lists appear as tabs
- Tabs follow user-defined order
- Clicking list tab shows filtered bookmarks
- Active tab state works correctly

### Key Changes

1. **Update `frontend/src/pages/Bookmarks.tsx`**
   - Fetch lists and settings on mount
   - Generate tabs from settings.tab_order (fallback to default)
   - Add "list" view type alongside "active", "archived", "deleted"
   - Pass list_id to bookmark fetch when list tab active

2. **Update `frontend/src/hooks/useBookmarks.ts`**
   - Add `list_id` parameter to `fetchBookmarks()`

3. **Update tab styling**
   - Visual distinction for custom lists (optional - icon or color)
   - Handle many tabs gracefully (scrollable tabs or overflow menu)

### Testing Strategy
- Test tabs render in correct order
- Test clicking list tab filters bookmarks correctly
- Test URL state includes list selection
- Test empty list state
- Test list with no matching bookmarks

### Dependencies
- Milestone 4 (Backend list filtering)
- Milestone 7 (Lists exist in system)
- Milestone 8 (Tab order settings)

### Risk Factors
- Many tabs UX (mitigate: scrollable tabs or dropdown)
- State management complexity (mitigate: clear URL parameters)

---

## Milestone 10: Polish and Edge Cases

### Goal
Handle edge cases, improve UX, and ensure robustness.

### Success Criteria
- Graceful handling of deleted lists in tab order
- Loading states throughout
- Error handling with user feedback
- Empty states with helpful messages

### Key Changes

1. **Edge case handling**
   - Tab order references deleted list → filter out, don't crash
   - List with tags that no longer exist → still filter, show empty
   - Very long list names → truncate in tabs

2. **Loading states**
   - Skeleton loaders for settings sections
   - Disabled buttons during operations

3. **Error handling**
   - Toast notifications for failures
   - Retry options where appropriate

4. **Empty states**
   - No tokens: "Create your first token..."
   - No lists: "Create a custom list..."
   - List has no bookmarks: "No bookmarks match this filter"

5. **Documentation**
   - Update CLAUDE.md with new features
   - Add inline help/tooltips for filter builder

### Testing Strategy
- Test all edge cases mentioned above
- Manual QA for UX polish
- Test on different screen sizes

### Dependencies
- All previous milestones

### Risk Factors
- Scope creep (keep polish focused)

---

## Summary

| Milestone | Focus | Estimated Complexity |
|-----------|-------|---------------------|
| 1 | UserSettings model | Low |
| 2 | List model + service | Medium |
| 3 | List API endpoints | Medium |
| 4 | List bookmark filtering | Medium |
| 5 | Settings page structure | Low |
| 6 | PAT management UI | Medium |
| 7 | Lists management UI | High |
| 8 | Tab order settings | Medium |
| 9 | Tabs integration | Medium |
| 10 | Polish + edge cases | Low |

**Key architectural decisions:**
- Filter expressions stored as JSON with AND groups combined by OR
- Tab order stored in user settings as JSON array
- All tabs (including built-in) fully reorderable
- Visual filter builder (not text-based) for better UX
- Settings accessed via gear icon next to logout
