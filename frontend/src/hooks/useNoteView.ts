/**
 * Hook for deriving note view from route params.
 *
 * Routes:
 * - /app/notes → view: 'active', listId: undefined
 * - /app/notes/archived → view: 'archived', listId: undefined
 * - /app/notes/trash → view: 'deleted', listId: undefined
 * - /app/notes/lists/:listId → view: 'active', listId: number
 */
import { useMemo } from 'react'
import { useLocation, useParams } from 'react-router-dom'

export type NoteView = 'active' | 'archived' | 'deleted'

export interface UseNoteViewReturn {
  /** Current view for API calls */
  currentView: NoteView
  /** List ID for custom list views */
  currentListId: number | undefined
}

/**
 * Hook for deriving note view from route.
 *
 * Usage:
 * ```tsx
 * const { currentView, currentListId } = useNoteView()
 *
 * // Use in API calls
 * fetchNotes({ view: currentView, list_id: currentListId })
 * ```
 */
export function useNoteView(): UseNoteViewReturn {
  const location = useLocation()
  const params = useParams<{ listId?: string }>()

  const { currentView, currentListId } = useMemo(() => {
    const path = location.pathname

    if (path === '/app/notes/archived') {
      return { currentView: 'archived' as NoteView, currentListId: undefined }
    }

    if (path === '/app/notes/trash') {
      return { currentView: 'deleted' as NoteView, currentListId: undefined }
    }

    if (path.startsWith('/app/notes/lists/') && params.listId) {
      const listId = parseInt(params.listId, 10)
      return {
        currentView: 'active' as NoteView,
        currentListId: isNaN(listId) ? undefined : listId,
      }
    }

    // Default: /app/notes
    return { currentView: 'active' as NoteView, currentListId: undefined }
  }, [location.pathname, params.listId])

  return { currentView, currentListId }
}
