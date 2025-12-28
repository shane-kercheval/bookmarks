/**
 * Hook for deriving note view from route params.
 *
 * Routes:
 * - /app/notes → view: 'active', listId: undefined
 * - /app/notes/archived → view: 'archived', listId: undefined
 * - /app/notes/trash → view: 'deleted', listId: undefined
 * - /app/notes/lists/:listId → view: 'active', listId: number
 */
import { useContentView } from './useContentView'
import type { ContentView, UseContentViewReturn } from './useContentView'

// Re-export the view type with note-specific name for API compatibility
export type NoteView = ContentView

export type UseNoteViewReturn = UseContentViewReturn

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
  return useContentView('/app/notes')
}
