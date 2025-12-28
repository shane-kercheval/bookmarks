/**
 * Hook for deriving bookmark view from route params.
 *
 * Routes:
 * - /app/bookmarks → view: 'active', listId: undefined
 * - /app/bookmarks/archived → view: 'archived', listId: undefined
 * - /app/bookmarks/trash → view: 'deleted', listId: undefined
 * - /app/bookmarks/lists/:listId → view: 'active', listId: number
 */
import { useContentView } from './useContentView'
import type { ContentView, UseContentViewReturn } from './useContentView'

// Re-export the view type with bookmark-specific name for API compatibility
export type BookmarkView = ContentView

export type UseBookmarkViewReturn = UseContentViewReturn

/**
 * Hook for deriving bookmark view from route.
 *
 * Usage:
 * ```tsx
 * const { currentView, currentListId } = useBookmarkView()
 *
 * // Use in API calls
 * fetchBookmarks({ view: currentView, list_id: currentListId })
 * ```
 */
export function useBookmarkView(): UseBookmarkViewReturn {
  return useContentView('/app/bookmarks')
}
