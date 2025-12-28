/**
 * Hook for managing bookmark URL parameters.
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

// Re-export types with bookmark-specific names for API compatibility
export type BookmarkUrlParams = ContentUrlParams
export type BookmarkUrlParamUpdates = ContentUrlParamUpdates
export type UseBookmarkUrlParamsReturn = UseContentUrlParamsReturn

/**
 * Hook for managing bookmark URL parameters.
 *
 * Usage:
 * ```tsx
 * const { searchQuery, offset, updateParams } = useBookmarkUrlParams()
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
export function useBookmarkUrlParams(): UseBookmarkUrlParamsReturn {
  return useContentUrlParams()
}
