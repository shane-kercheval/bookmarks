/**
 * TanStack Query hook for fetching unified content (bookmarks + notes).
 *
 * Used for the shared views (All, Archived, Trash) that display
 * both bookmarks and notes in a single unified list.
 */
import { useQuery } from '@tanstack/react-query'
import { api } from '../services/api'
import type { ContentListResponse, ContentSearchParams } from '../types'

/**
 * Query key factory for consistent cache keys.
 *
 * Key Structure (view segment BEFORE params for prefix matching):
 * - ['content', 'list', 'active', params]  - active view queries
 * - ['content', 'list', 'archived', params] - archived view queries
 * - ['content', 'list', 'deleted', params] - deleted view queries
 *
 * Invalidation Keys (prefix matching):
 * - contentKeys.view('active')  → ['content', 'list', 'active'] - all active queries
 * - contentKeys.view('archived') → ['content', 'list', 'archived'] - all archived queries
 * - contentKeys.view('deleted') → ['content', 'list', 'deleted'] - all deleted queries
 * - contentKeys.lists()         → ['content', 'list'] - ALL list queries
 */
export const contentKeys = {
  all: ['content'] as const,
  lists: () => [...contentKeys.all, 'list'] as const,

  /** Invalidation key for a specific view type (active/archived/deleted) */
  view: (view: 'active' | 'archived' | 'deleted') =>
    [...contentKeys.lists(), view] as const,

  /** Query key for fetching - includes view segment for granular invalidation */
  list: (params: ContentSearchParams) => {
    return [...contentKeys.view(params.view ?? 'active'), params] as const
  },
}

/**
 * Build URL query string from search params.
 */
function buildQueryString(params: ContentSearchParams): string {
  const queryParams = new URLSearchParams()

  if (params.q) {
    queryParams.set('q', params.q)
  }
  if (params.tags && params.tags.length > 0) {
    params.tags.forEach((tag) => queryParams.append('tags', tag))
  }
  if (params.tag_match) {
    queryParams.set('tag_match', params.tag_match)
  }
  if (params.sort_by) {
    queryParams.set('sort_by', params.sort_by)
  }
  if (params.sort_order) {
    queryParams.set('sort_order', params.sort_order)
  }
  if (params.offset !== undefined) {
    queryParams.set('offset', String(params.offset))
  }
  if (params.limit !== undefined) {
    queryParams.set('limit', String(params.limit))
  }
  if (params.view) {
    queryParams.set('view', params.view)
  }
  if (params.list_id !== undefined) {
    queryParams.set('list_id', String(params.list_id))
  }

  return queryParams.toString()
}

/**
 * Fetch content from API.
 */
async function fetchContent(params: ContentSearchParams): Promise<ContentListResponse> {
  const queryString = buildQueryString(params)
  const url = queryString ? `/content/?${queryString}` : '/content/'
  const response = await api.get<ContentListResponse>(url)
  return response.data
}

interface UseContentQueryOptions {
  /** Whether to enable the query. Defaults to true. */
  enabled?: boolean
}

/**
 * Hook for fetching unified content with TanStack Query caching.
 *
 * @param params - Search/filter/pagination parameters
 * @param options - Query options (enabled, etc.)
 *
 * @returns Query result with data, loading states, and error
 *
 * @example
 * ```tsx
 * const { data, isLoading, isFetching, error } = useContentQuery({
 *   view: 'active',
 *   q: debouncedSearchQuery,
 *   tags: selectedTags,
 *   sort_by: 'created_at',
 *   sort_order: 'desc',
 *   offset: 0,
 *   limit: 20,
 * })
 * ```
 */
export function useContentQuery(
  params: ContentSearchParams,
  options: UseContentQueryOptions = {}
) {
  const { enabled = true } = options

  return useQuery({
    queryKey: contentKeys.list(params),
    queryFn: () => fetchContent(params),
    enabled,
  })
}
