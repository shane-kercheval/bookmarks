/**
 * Note detail page - handles view, edit, and create modes.
 *
 * Routes:
 * - /app/notes/:id - View mode
 * - /app/notes/:id/edit - Edit mode
 * - /app/notes/new - Create new note
 */
import { useState, useEffect, useCallback, useMemo } from 'react'
import type { ReactNode } from 'react'
import { useParams, useLocation, useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { NoteView } from '../components/NoteView'
import { NoteEditor } from '../components/NoteEditor'
import { LoadingSpinnerCentered, ErrorState } from '../components/ui'
import { useNotes } from '../hooks/useNotes'
import {
  useCreateNote,
  useUpdateNote,
  useDeleteNote,
  useRestoreNote,
  useArchiveNote,
  useUnarchiveNote,
} from '../hooks/useNoteMutations'
import { useTagsStore } from '../stores/tagsStore'
import { useTagFilterStore } from '../stores/tagFilterStore'
import { useUIPreferencesStore } from '../stores/uiPreferencesStore'
import type { Note, NoteCreate, NoteUpdate } from '../types'

type PageMode = 'view' | 'edit' | 'create'
type NoteViewState = 'active' | 'archived' | 'deleted'

/**
 * Determine the view state of a note based on its data.
 */
function getNoteViewState(note: Note): NoteViewState {
  if (note.deleted_at) return 'deleted'
  if (note.archived_at) return 'archived'
  return 'active'
}

/**
 * NoteDetail handles viewing, editing, and creating notes.
 */
export function NoteDetail(): ReactNode {
  const { id } = useParams<{ id: string }>()
  const location = useLocation()
  const navigate = useNavigate()

  // Determine mode from route
  const mode: PageMode = useMemo(() => {
    if (!id || id === 'new') return 'create'
    if (location.pathname.endsWith('/edit')) return 'edit'
    return 'view'
  }, [id, location.pathname])

  const noteId = mode !== 'create' ? parseInt(id!, 10) : undefined
  const isValidId = noteId !== undefined && !isNaN(noteId)

  // State
  const [note, setNote] = useState<Note | null>(null)
  const [isLoading, setIsLoading] = useState(mode !== 'create')
  const [error, setError] = useState<string | null>(null)

  // Get initial tags from navigation state or tag filter
  const locationState = location.state as { initialTags?: string[] } | undefined
  const { selectedTags, addTag } = useTagFilterStore()
  const initialTags = locationState?.initialTags ?? (selectedTags.length > 0 ? selectedTags : undefined)

  // Hooks
  const { fetchNote, trackNoteUsage } = useNotes()
  const { tags: tagSuggestions } = useTagsStore()
  const fullWidthLayout = useUIPreferencesStore((state) => state.fullWidthLayout)
  const createMutation = useCreateNote()
  const updateMutation = useUpdateNote()
  const deleteMutation = useDeleteNote()
  const restoreMutation = useRestoreNote()
  const archiveMutation = useArchiveNote()
  const unarchiveMutation = useUnarchiveNote()

  // Derive view state from note
  const viewState: NoteViewState = note ? getNoteViewState(note) : 'active'

  // Fetch note on mount (for view/edit modes)
  useEffect(() => {
    if (mode === 'create') {
      setIsLoading(false)
      return
    }

    if (!isValidId) {
      setError('Invalid note ID')
      setIsLoading(false)
      return
    }

    const loadNote = async (): Promise<void> => {
      setIsLoading(true)
      setError(null)
      try {
        const fetchedNote = await fetchNote(noteId!)
        setNote(fetchedNote)
        // Track usage when viewing
        if (mode === 'view') {
          trackNoteUsage(noteId!)
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load note')
      } finally {
        setIsLoading(false)
      }
    }

    loadNote()
  }, [mode, noteId, isValidId, fetchNote, trackNoteUsage])

  // Navigation helpers
  const navigateToList = useCallback((): void => {
    navigate('/app/notes')
  }, [navigate])

  const navigateToView = useCallback((noteId: number): void => {
    navigate(`/app/notes/${noteId}`)
  }, [navigate])

  const handleBack = useCallback((): void => {
    navigateToList()
  }, [navigateToList])

  const handleEdit = useCallback((): void => {
    if (noteId) {
      navigate(`/app/notes/${noteId}/edit`)
    }
  }, [noteId, navigate])

  const handleTagClick = useCallback((tag: string): void => {
    // Navigate to notes list with tag filter
    addTag(tag)
    navigateToList()
  }, [addTag, navigateToList])

  // Action handlers
  const handleSubmitCreate = useCallback(
    async (data: NoteCreate | NoteUpdate): Promise<void> => {
      try {
        const newNote = await createMutation.mutateAsync(data as NoteCreate)
        navigateToView(newNote.id)
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to create note'
        toast.error(message)
        throw err
      }
    },
    [createMutation, navigateToView]
  )

  const handleSubmitUpdate = useCallback(
    async (data: NoteCreate | NoteUpdate): Promise<void> => {
      if (!noteId) return

      try {
        const updatedNote = await updateMutation.mutateAsync({
          id: noteId,
          data: data as NoteUpdate,
        })
        setNote(updatedNote)
        navigateToView(noteId)
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to save note'
        toast.error(message)
        throw err
      }
    },
    [noteId, updateMutation, navigateToView]
  )

  const handleCancel = useCallback((): void => {
    if (mode === 'create') {
      navigateToList()
    } else if (noteId) {
      navigateToView(noteId)
    }
  }, [mode, noteId, navigateToList, navigateToView])

  const handleArchive = useCallback(async (): Promise<void> => {
    if (!noteId) return
    try {
      const archivedNote = await archiveMutation.mutateAsync(noteId)
      setNote(archivedNote)
    } catch {
      toast.error('Failed to archive note')
    }
  }, [noteId, archiveMutation])

  const handleUnarchive = useCallback(async (): Promise<void> => {
    if (!noteId) return
    try {
      const unarchivedNote = await unarchiveMutation.mutateAsync(noteId)
      setNote(unarchivedNote)
    } catch {
      toast.error('Failed to unarchive note')
    }
  }, [noteId, unarchiveMutation])

  const handleDelete = useCallback(async (): Promise<void> => {
    if (!noteId) return
    try {
      const isPermanent = viewState === 'deleted'
      await deleteMutation.mutateAsync({ id: noteId, permanent: isPermanent })
      navigateToList()
    } catch {
      toast.error('Failed to delete note')
    }
  }, [noteId, viewState, deleteMutation, navigateToList])

  const handleRestore = useCallback(async (): Promise<void> => {
    if (!noteId) return
    try {
      const restoredNote = await restoreMutation.mutateAsync(noteId)
      setNote(restoredNote)
    } catch {
      toast.error('Failed to restore note')
    }
  }, [noteId, restoreMutation])

  // Render loading state
  if (isLoading) {
    return <LoadingSpinnerCentered label="Loading note..." />
  }

  // Render error state
  if (error) {
    return <ErrorState message={error} onRetry={() => navigate(0)} />
  }

  // Render create mode
  if (mode === 'create') {
    return (
      <div className={`flex flex-col h-full w-full ${fullWidthLayout ? '' : 'max-w-4xl mx-auto'}`}>
        <NoteEditor
          tagSuggestions={tagSuggestions}
          onSubmit={handleSubmitCreate}
          onCancel={handleCancel}
          isSubmitting={createMutation.isPending}
          initialTags={initialTags}
        />
      </div>
    )
  }

  // Render view/edit modes (requires note to be loaded)
  if (!note) {
    return <ErrorState message="Note not found" />
  }

  // Edit mode
  if (mode === 'edit') {
    return (
      <div className={`flex flex-col h-full w-full ${fullWidthLayout ? '' : 'max-w-4xl mx-auto'}`}>
        <NoteEditor
          note={note}
          tagSuggestions={tagSuggestions}
          onSubmit={handleSubmitUpdate}
          onCancel={handleCancel}
          isSubmitting={updateMutation.isPending}
          onArchive={viewState === 'active' ? handleArchive : undefined}
          onDelete={handleDelete}
        />
      </div>
    )
  }

  // View mode
  return (
    <NoteView
      note={note}
      view={viewState}
      fullWidth={fullWidthLayout}
      onEdit={viewState !== 'deleted' ? handleEdit : undefined}
      onArchive={viewState === 'active' ? handleArchive : undefined}
      onUnarchive={viewState === 'archived' ? handleUnarchive : undefined}
      onDelete={handleDelete}
      onRestore={viewState === 'deleted' ? handleRestore : undefined}
      onTagClick={handleTagClick}
      onBack={handleBack}
    />
  )
}
