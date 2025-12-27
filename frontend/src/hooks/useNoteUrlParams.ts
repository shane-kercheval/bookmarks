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
import { useContentUrlParams } from './useContentUrlParams'
import type { ContentUrlParams, ContentUrlParamUpdates, UseContentUrlParamsReturn } from './useContentUrlParams'

// Re-export types with note-specific names for API compatibility
export type NoteUrlParams = ContentUrlParams
export type NoteUrlParamUpdates = ContentUrlParamUpdates
export type UseNoteUrlParamsReturn = UseContentUrlParamsReturn

/**
 * Hook for managing note URL parameters.
 *
 * Usage:
 * ```tsx
 * const { searchQuery, offset, updateParams } = useNoteUrlParams()
 *
 * // Update search
 * updateParams({ q: 'markdown tips' })
 *
 * // Clear search (removes from URL rather than storing empty string)
 * updateParams({ q: '' })
 *
 * // Update pagination
 * updateParams({ offset: 50 })
 * ```
 */
export function useNoteUrlParams(): UseNoteUrlParamsReturn {
  return useContentUrlParams()
}
