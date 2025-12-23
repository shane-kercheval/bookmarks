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
}

/** Data for updating an existing bookmark */
export interface BookmarkUpdate {
  url?: string
  title?: string | null
  description?: string | null
  content?: string | null
  tags?: string[]
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
  sort_by?: 'created_at' | 'updated_at' | 'last_used_at' | 'title'
  sort_order?: 'asc' | 'desc'
  offset?: number
  limit?: number
  view?: 'active' | 'archived' | 'deleted'
  list_id?: number
}

// =============================================================================
// BookmarkList Types
// =============================================================================

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

/** BookmarkList data returned from the API */
export interface BookmarkList {
  id: number
  name: string
  filter_expression: FilterExpression
  default_sort_by: string | null
  default_sort_ascending: boolean | null
  created_at: string
  updated_at: string
}

/** Data for creating a new bookmark list */
export interface BookmarkListCreate {
  name: string
  filter_expression: FilterExpression
  default_sort_by?: string | null
  default_sort_ascending?: boolean | null
}

/** Data for updating an existing bookmark list */
export interface BookmarkListUpdate {
  name?: string
  filter_expression?: FilterExpression
  default_sort_by?: string | null
  default_sort_ascending?: boolean | null
}

// =============================================================================
// User Settings Types
// =============================================================================

/** User settings data returned from the API */
export interface UserSettings {
  tab_order: string[] | null
  updated_at: string
}

/** Data for updating user settings */
export interface UserSettingsUpdate {
  tab_order?: string[] | null
}

/** Tab order item with resolved label */
export interface TabOrderItem {
  key: string
  label: string
  type: 'builtin' | 'list'
}

/** Computed tab order response */
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
