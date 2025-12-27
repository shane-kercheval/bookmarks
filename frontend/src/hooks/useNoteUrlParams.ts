/**
 * Hook for managing note URL parameters.
 *
 * Handles:
 * - Parsing search and pagination params from URL
 * - Providing typed updateParams function with smart defaults
 *
 * Note: Tag filters are managed by useTagFilterStore for persistence.
 * Sort preferences are managed by useEffectiveSort for per-view persistence.
 */
import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'

export interface NoteUrlParams {
  searchQuery: string
  offset: number
}

export interface NoteUrlParamUpdates {
  q?: string
  offset?: number
}

export interface UseNoteUrlParamsReturn extends NoteUrlParams {
  /** Update one or more URL params. Handles default value optimization. */
  updateParams: (updates: NoteUrlParamUpdates) => void
}

/**
 * Hook for managing note URL parameters.
 *
 * Usage:
 * ```tsx
 * const { searchQuery, offset, updateParams } = useNoteUrlParams()
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
export function useNoteUrlParams(): UseNoteUrlParamsReturn {
  const [searchParams, setSearchParams] = useSearchParams()

  // Parse URL params
  const searchQuery = searchParams.get('q') || ''
  const offset = parseInt(searchParams.get('offset') || '0', 10)

  // Update URL params
  const updateParams = useCallback(
    (updates: NoteUrlParamUpdates) => {
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
