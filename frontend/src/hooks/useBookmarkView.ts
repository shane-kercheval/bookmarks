/**
 * Hook for deriving bookmark view from route params.
 *
 * Replaces useTabNavigation for route-based navigation.
 * Routes:
 * - /app/bookmarks → view: 'active', listId: undefined
 * - /app/bookmarks/archived → view: 'archived', listId: undefined
 * - /app/bookmarks/trash → view: 'deleted', listId: undefined
 * - /app/bookmarks/lists/:listId → view: 'active', listId: number
 */
import { useMemo } from 'react'
import { useLocation, useParams } from 'react-router-dom'

export type BookmarkView = 'active' | 'archived' | 'deleted'

export interface UseBookmarkViewReturn {
  /** Current view for API calls */
  currentView: BookmarkView
  /** List ID for custom list views */
  currentListId: number | undefined
}

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
  const location = useLocation()
  const params = useParams<{ listId?: string }>()

  const { currentView, currentListId } = useMemo(() => {
    const path = location.pathname

    if (path === '/app/bookmarks/archived') {
      return { currentView: 'archived' as BookmarkView, currentListId: undefined }
    }

    if (path === '/app/bookmarks/trash') {
      return { currentView: 'deleted' as BookmarkView, currentListId: undefined }
    }

    if (path.startsWith('/app/bookmarks/lists/') && params.listId) {
      const listId = parseInt(params.listId, 10)
      return {
        currentView: 'active' as BookmarkView,
        currentListId: isNaN(listId) ? undefined : listId,
      }
    }

    // Default: /app/bookmarks
    return { currentView: 'active' as BookmarkView, currentListId: undefined }
  }, [location.pathname, params.listId])

  return { currentView, currentListId }
}
