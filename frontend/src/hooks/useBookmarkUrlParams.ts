/**
 * Hook for managing bookmark URL parameters.
 *
 * Handles:
 * - Parsing search, filter, sort, and pagination params from URL
 * - Providing typed updateParams function with smart defaults
 * - Memoizing array params to prevent re-render loops
 */
import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

export type SortByOption = 'created_at' | 'updated_at' | 'last_used_at' | 'title'
export type SortOrderOption = 'asc' | 'desc'
export type TagMatchOption = 'all' | 'any'

export interface BookmarkUrlParams {
  searchQuery: string
  selectedTags: string[]
  tagMatch: TagMatchOption
  sortBy: SortByOption
  sortOrder: SortOrderOption
  offset: number
}

export interface BookmarkUrlParamUpdates {
  q?: string
  tags?: string[]
  tag_match?: TagMatchOption
  sort_by?: SortByOption
  sort_order?: SortOrderOption
  offset?: number
}

export interface UseBookmarkUrlParamsReturn extends BookmarkUrlParams {
  /** Update one or more URL params. Handles default value optimization. */
  updateParams: (updates: BookmarkUrlParamUpdates) => void
  /** Whether any search or tag filters are active */
  hasFilters: boolean
}

/**
 * Hook for managing bookmark URL parameters.
 *
 * Usage:
 * ```tsx
 * const { searchQuery, selectedTags, sortBy, updateParams, hasFilters } = useBookmarkUrlParams()
 *
 * // Update search
 * updateParams({ q: 'react hooks' })
 *
 * // Update multiple params
 * updateParams({ sort_by: 'title', sort_order: 'asc' })
 *
 * // Clear search (removes from URL rather than storing empty string)
 * updateParams({ q: '' })
 * ```
 */
export function useBookmarkUrlParams(): UseBookmarkUrlParamsReturn {
  const [searchParams, setSearchParams] = useSearchParams()

  // Parse URL params with defaults
  const searchQuery = searchParams.get('q') || ''
  const selectedTagsRaw = searchParams.getAll('tags')
  // Create a stable key for memoization (getAll returns new array each call)
  const selectedTagsKey = selectedTagsRaw.join(',')
  // Memoize selectedTags to prevent infinite re-renders
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const selectedTags = useMemo(() => selectedTagsRaw, [selectedTagsKey])
  const tagMatch = (searchParams.get('tag_match') as TagMatchOption) || 'all'
  const sortBy = (searchParams.get('sort_by') as SortByOption) || 'created_at'
  const sortOrder = (searchParams.get('sort_order') as SortOrderOption) || 'desc'
  const offset = parseInt(searchParams.get('offset') || '0', 10)

  // Derive hasFilters
  const hasFilters = searchQuery.length > 0 || selectedTags.length > 0

  // Update URL params with smart defaults (removes default values from URL)
  const updateParams = useCallback(
    (updates: BookmarkUrlParamUpdates) => {
      const newParams = new URLSearchParams(searchParams)

      if ('q' in updates) {
        if (updates.q) {
          newParams.set('q', updates.q)
        } else {
          newParams.delete('q')
        }
      }

      if ('tags' in updates) {
        newParams.delete('tags')
        updates.tags?.forEach((tag) => newParams.append('tags', tag))
      }

      if ('tag_match' in updates) {
        if (updates.tag_match && updates.tag_match !== 'all') {
          newParams.set('tag_match', updates.tag_match)
        } else {
          newParams.delete('tag_match')
        }
      }

      if ('sort_by' in updates) {
        if (updates.sort_by && updates.sort_by !== 'created_at') {
          newParams.set('sort_by', updates.sort_by)
        } else {
          newParams.delete('sort_by')
        }
      }

      if ('sort_order' in updates) {
        if (updates.sort_order && updates.sort_order !== 'desc') {
          newParams.set('sort_order', updates.sort_order)
        } else {
          newParams.delete('sort_order')
        }
      }

      if ('offset' in updates) {
        if (updates.offset && updates.offset > 0) {
          newParams.set('offset', String(updates.offset))
        } else {
          newParams.delete('offset')
        }
      }

      setSearchParams(newParams, { replace: true })
    },
    [searchParams, setSearchParams]
  )

  return {
    searchQuery,
    selectedTags,
    tagMatch,
    sortBy,
    sortOrder,
    offset,
    updateParams,
    hasFilters,
  }
}
