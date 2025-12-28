/**
 * Generic hook for deriving content view from route params.
 *
 * This is the shared implementation used by useBookmarkView and useNoteView.
 * It extracts the view state (active/archived/deleted) and optional list ID
 * from the current route.
 */
import { useMemo } from 'react'
import { useLocation, useParams } from 'react-router-dom'

export type ContentView = 'active' | 'archived' | 'deleted'

export interface UseContentViewReturn {
  /** Current view for API calls */
  currentView: ContentView
  /** List ID for custom list views */
  currentListId: number | undefined
}

/**
 * Generic hook for deriving content view from route.
 *
 * @param basePath - The base path for this content type (e.g., '/app/bookmarks', '/app/notes')
 *
 * Routes handled:
 * - {basePath} → view: 'active', listId: undefined
 * - {basePath}/archived → view: 'archived', listId: undefined
 * - {basePath}/trash → view: 'deleted', listId: undefined
 * - {basePath}/lists/:listId → view: 'active', listId: number
 */
export function useContentView(basePath: string): UseContentViewReturn {
  const location = useLocation()
  const params = useParams<{ listId?: string }>()

  const { currentView, currentListId } = useMemo(() => {
    const path = location.pathname

    if (path === `${basePath}/archived`) {
      return { currentView: 'archived' as ContentView, currentListId: undefined }
    }

    if (path === `${basePath}/trash`) {
      return { currentView: 'deleted' as ContentView, currentListId: undefined }
    }

    if (path.startsWith(`${basePath}/lists/`) && params.listId) {
      const listId = parseInt(params.listId, 10)
      return {
        currentView: 'active' as ContentView,
        currentListId: isNaN(listId) ? undefined : listId,
      }
    }

    // Default: base path
    return { currentView: 'active' as ContentView, currentListId: undefined }
  }, [basePath, location.pathname, params.listId])

  return { currentView, currentListId }
}
