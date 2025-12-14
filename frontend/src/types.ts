/**
 * TypeScript types for API responses and data models.
 */

/** Bookmark data returned from the API */
export interface Bookmark {
  id: number
  url: string
  title: string | null
  description: string | null
  summary: string | null
  tags: string[]
  created_at: string
  updated_at: string
}

/** Data for creating a new bookmark */
export interface BookmarkCreate {
  url: string
  title?: string | null
  description?: string | null
  content?: string | null
  tags?: string[]
  store_content?: boolean
}

/** Data for updating an existing bookmark */
export interface BookmarkUpdate {
  title?: string | null
  description?: string | null
  content?: string | null
  tags?: string[]
}

/** Paginated list response from GET /bookmarks/ */
export interface BookmarkListResponse {
  items: Bookmark[]
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

/** Search and filter parameters for listing bookmarks */
export interface BookmarkSearchParams {
  q?: string
  tags?: string[]
  tag_match?: 'all' | 'any'
  sort_by?: 'created_at' | 'title'
  sort_order?: 'asc' | 'desc'
  offset?: number
  limit?: number
}
