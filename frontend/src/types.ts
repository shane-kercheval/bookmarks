/**
 * TypeScript types for API responses and data models.
 */

/**
 * Bookmark item in list responses (excludes content for performance).
 *
 * The content field can be up to 500KB per bookmark, making list responses
 * unnecessarily large. Use GET /bookmarks/:id to fetch full bookmark with content.
 */
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

/**
 * Full bookmark data (includes content).
 *
 * Returned by GET /bookmarks/:id and mutation endpoints.
 */
export interface Bookmark extends BookmarkListItem {
  content: string | null
}

/** Data for creating a new bookmark */
export interface BookmarkCreate {
  url: string
  title?: string | null
  description?: string | null
  content?: string | null
  tags?: string[]
  archived_at?: string | null  // ISO 8601 datetime string for scheduling auto-archive
}

/** Data for updating an existing bookmark */
export interface BookmarkUpdate {
  url?: string
  title?: string | null
  description?: string | null
  content?: string | null
  tags?: string[]
  archived_at?: string | null  // ISO 8601 datetime string, or null to cancel schedule
}

/** Paginated list response from GET /bookmarks/ */
export interface BookmarkListResponse {
  items: BookmarkListItem[]
  total: number
  offset: number
  limit: number
  has_more: boolean
}

/** Metadata preview response from GET /bookmarks/fetch-metadata */
export interface MetadataPreviewResponse {
  url: string
  final_url: string
  title: string | null
  description: string | null
  content: string | null
  error: string | null
}

// =============================================================================
// Note Types
// =============================================================================

/**
 * Note item in list responses (excludes content for performance).
 *
 * The content field can be up to 2MB per note, making list responses
 * unnecessarily large. Use GET /notes/:id to fetch full note with content.
 */
export interface NoteListItem {
  id: number
  title: string
  description: string | null
  tags: string[]
  created_at: string
  updated_at: string
  last_used_at: string
  deleted_at: string | null
  archived_at: string | null
  version: number
}

/**
 * Full note data (includes content).
 *
 * Returned by GET /notes/:id and mutation endpoints.
 */
export interface Note extends NoteListItem {
  content: string | null
}

/** Data for creating a new note */
export interface NoteCreate {
  title: string  // Required for notes
  description?: string | null
  content?: string | null
  tags?: string[]
  archived_at?: string | null  // ISO 8601 datetime string for scheduling auto-archive
}

/** Data for updating an existing note */
export interface NoteUpdate {
  title?: string
  description?: string | null
  content?: string | null
  tags?: string[]
  archived_at?: string | null  // ISO 8601 datetime string, or null to cancel schedule
}

/** Paginated list response from GET /notes/ */
export interface NoteListResponse {
  items: NoteListItem[]
  total: number
  offset: number
  limit: number
  has_more: boolean
}

/** Search and filter parameters for listing notes */
export interface NoteSearchParams {
  q?: string
  tags?: string[]
  tag_match?: 'all' | 'any'
  sort_by?: 'created_at' | 'updated_at' | 'last_used_at' | 'title' | 'archived_at' | 'deleted_at'
  sort_order?: 'asc' | 'desc'
  offset?: number
  limit?: number
  view?: 'active' | 'archived' | 'deleted'
  list_id?: number
}

/** Tag with usage count */
export interface TagCount {
  name: string
  count: number
}

/** Tags list response from GET /tags/ */
export interface TagListResponse {
  tags: TagCount[]
}

/** Full tag object returned by rename endpoint */
export interface Tag {
  id: number
  name: string
  created_at: string
}

/** Request body for renaming a tag */
export interface TagRenameRequest {
  new_name: string
}

/** Search and filter parameters for listing bookmarks */
export interface BookmarkSearchParams {
  q?: string
  tags?: string[]
  tag_match?: 'all' | 'any'
  sort_by?: 'created_at' | 'updated_at' | 'last_used_at' | 'title' | 'archived_at' | 'deleted_at'
  sort_order?: 'asc' | 'desc'
  offset?: number
  limit?: number
  view?: 'active' | 'archived' | 'deleted'
  list_id?: number
}

// =============================================================================
// Unified Content Types (for shared views)
// =============================================================================

/**
 * Unified content item for list views.
 *
 * This type represents both bookmarks and notes in a unified format.
 * The `type` field indicates the content type, and type-specific fields
 * (url for bookmarks, version for notes) may be null for other types.
 */
export interface ContentListItem {
  type: 'bookmark' | 'note'
  id: number
  title: string | null
  description: string | null
  tags: string[]
  created_at: string
  updated_at: string
  last_used_at: string
  deleted_at: string | null
  archived_at: string | null
  // Bookmark-specific (null for notes)
  url: string | null
  // Note-specific (null for bookmarks)
  version: number | null
}

/** Paginated list response from GET /content/ */
export interface ContentListResponse {
  items: ContentListItem[]
  total: number
  offset: number
  limit: number
  has_more: boolean
}

/** Search and filter parameters for listing all content */
export interface ContentSearchParams {
  q?: string
  tags?: string[]
  tag_match?: 'all' | 'any'
  sort_by?: 'created_at' | 'updated_at' | 'last_used_at' | 'title' | 'archived_at' | 'deleted_at'
  sort_order?: 'asc' | 'desc'
  offset?: number
  limit?: number
  view?: 'active' | 'archived' | 'deleted'
  list_id?: number
}

// =============================================================================
// ContentList Types
// =============================================================================

/** Valid content types for lists */
export type ContentType = 'bookmark' | 'note'

/** A group of tags combined with AND logic */
export interface FilterGroup {
  tags: string[]
  operator: 'AND'
}

/** Filter expression with AND groups combined by OR */
export interface FilterExpression {
  groups: FilterGroup[]
  group_operator: 'OR'
}

/** ContentList data returned from the API */
export interface ContentList {
  id: number
  name: string
  content_types: ContentType[]
  filter_expression: FilterExpression
  default_sort_by: string | null
  default_sort_ascending: boolean | null
  created_at: string
  updated_at: string
}

/** Data for creating a new content list */
export interface ContentListCreate {
  name: string
  content_types?: ContentType[]  // Defaults to ["bookmark", "note"]
  filter_expression: FilterExpression
  default_sort_by?: string | null
  default_sort_ascending?: boolean | null
}

/** Data for updating an existing content list */
export interface ContentListUpdate {
  name?: string
  content_types?: ContentType[]
  filter_expression?: FilterExpression
  default_sort_by?: string | null
  default_sort_ascending?: boolean | null
}


// =============================================================================
// User Settings Types
// =============================================================================

/** Valid section names for tab order */
export type SectionName = 'shared' | 'bookmarks' | 'notes'

/** Tab order sections structure */
export interface TabOrderSections {
  shared: string[]
  bookmarks: string[]
  notes: string[]
}

/** Structured tab order with sections */
export interface TabOrder {
  sections: TabOrderSections
  section_order: SectionName[]
}

/** User settings data returned from the API */
export interface UserSettings {
  tab_order: TabOrder | null
  updated_at: string
}

/** Data for updating user settings */
export interface UserSettingsUpdate {
  tab_order?: TabOrder | null
}

/** Tab order item with resolved label */
export interface TabOrderItem {
  key: string
  label: string
  type: 'builtin' | 'list'
}

/** A section in the computed tab order */
export interface TabOrderSection {
  name: SectionName
  label: string
  items: TabOrderItem[]
  collapsible: boolean
}

/** Computed tab order response with sections */
export interface ComputedTabOrderResponse {
  sections: TabOrderSection[]
  section_order: SectionName[]
}

/** @deprecated Use ComputedTabOrderResponse instead */
export interface TabOrderResponse {
  items: TabOrderItem[]
}

// =============================================================================
// Token Types
// =============================================================================

/** API Token (PAT) data returned from the API */
export interface Token {
  id: number
  name: string
  token_prefix: string
  last_used_at: string | null
  expires_at: string | null
  created_at: string
}

/** Token creation response includes the plaintext token */
export interface TokenCreateResponse extends Token {
  token: string
}

/** Data for creating a new token */
export interface TokenCreate {
  name: string
  expires_in_days?: number
}
