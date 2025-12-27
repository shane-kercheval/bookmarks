/**
 * Generic hook for managing content URL parameters.
 *
 * This is the shared implementation used by useBookmarkUrlParams and useNoteUrlParams.
 * It handles parsing and updating search query and pagination parameters in the URL.
 *
 * Note: Tag filters are managed by useTagFilterStore for persistence.
 * Sort preferences are managed by useEffectiveSort for per-view persistence.
 */
import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'

export interface ContentUrlParams {
  searchQuery: string
  offset: number
}

export interface ContentUrlParamUpdates {
  q?: string
  offset?: number
}

export interface UseContentUrlParamsReturn extends ContentUrlParams {
  /** Update one or more URL params. Handles default value optimization. */
  updateParams: (updates: ContentUrlParamUpdates) => void
}

/**
 * Generic hook for managing content URL parameters.
 *
 * Usage:
 * ```tsx
 * const { searchQuery, offset, updateParams } = useContentUrlParams()
 *
 * // Update search
 * updateParams({ q: 'react hooks' })
 *
 * // Clear search (removes from URL rather than storing empty string)
 * updateParams({ q: '' })
 *
 * // Update pagination
 * updateParams({ offset: 50 })
 * ```
 */
export function useContentUrlParams(): UseContentUrlParamsReturn {
  const [searchParams, setSearchParams] = useSearchParams()

  // Parse URL params
  const searchQuery = searchParams.get('q') || ''
  const offset = parseInt(searchParams.get('offset') || '0', 10)

  // Update URL params
  const updateParams = useCallback(
    (updates: ContentUrlParamUpdates) => {
      const newParams = new URLSearchParams(searchParams)

      if ('q' in updates) {
        if (updates.q) {
          newParams.set('q', updates.q)
        } else {
          newParams.delete('q')
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
    offset,
    updateParams,
  }
}
