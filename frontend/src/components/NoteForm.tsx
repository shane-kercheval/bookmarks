/**
 * Wrapper component that coordinates view/edit modes for notes.
 * Handles API calls and mode switching.
 */
import { useState, useCallback } from 'react'
import type { ReactNode } from 'react'
import toast from 'react-hot-toast'
import { NoteView } from './NoteView'
import { NoteEditor } from './NoteEditor'
import type { Note, NoteCreate, NoteUpdate, TagCount } from '../types'
import { useUpdateNote } from '../hooks/useNoteMutations'

interface NoteFormProps {
  /** The note to display/edit */
  note: Note
  /** Current view state (active, archived, deleted) */
  view?: 'active' | 'archived' | 'deleted'
  /** Whether to start in edit mode */
  initialEditMode?: boolean
  /** Whether to use full width layout */
  fullWidth?: boolean
  /** Available tags for autocomplete */
  tagSuggestions: TagCount[]
  /** Called when navigating back to list */
  onBack?: () => void
  /** Called when a tag is clicked for filtering */
  onTagClick?: (tag: string) => void
  /** Called when note is archived */
  onArchive?: () => Promise<void>
  /** Called when note is unarchived */
  onUnarchive?: () => Promise<void>
  /** Called when note is deleted */
  onDelete?: () => Promise<void>
  /** Called when note is restored from trash */
  onRestore?: () => Promise<void>
  /** Called after successful save, receives updated note */
  onSaveSuccess?: (note: Note) => void
}

/**
 * NoteForm coordinates view and edit modes for a note.
 *
 * Features:
 * - Toggle between view and edit modes
 * - Handles update API calls
 * - Provides consistent action handlers for archive/delete/restore
 * - Shows toast notifications for success/error states
 *
 * Note: This component uses the `note` prop directly rather than copying to local state.
 * The parent is responsible for updating the note prop after save (via onSaveSuccess).
 * This prevents stale state bugs when the note is updated elsewhere.
 */
export function NoteForm({
  note,
  view = 'active',
  initialEditMode = false,
  fullWidth = false,
  tagSuggestions,
  onBack,
  onTagClick,
  onArchive,
  onUnarchive,
  onDelete,
  onRestore,
  onSaveSuccess,
}: NoteFormProps): ReactNode {
  const [isEditing, setIsEditing] = useState(initialEditMode)

  const updateNoteMutation = useUpdateNote()

  const handleEdit = useCallback((): void => {
    setIsEditing(true)
  }, [])

  const handleCancel = useCallback((): void => {
    setIsEditing(false)
  }, [])

  const handleSubmit = useCallback(
    async (data: NoteCreate | NoteUpdate): Promise<void> => {
      try {
        const updatedNote = await updateNoteMutation.mutateAsync({
          id: note.id,
          data: data as NoteUpdate,
        })
        setIsEditing(false)
        onSaveSuccess?.(updatedNote)
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Failed to save note'
        toast.error(message)
        throw error // Re-throw so the editor knows submission failed
      }
    },
    [note.id, updateNoteMutation, onSaveSuccess]
  )

  const handleArchive = useCallback(async (): Promise<void> => {
    try {
      await onArchive?.()
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to archive note'
      toast.error(message)
    }
  }, [onArchive])

  const handleUnarchive = useCallback(async (): Promise<void> => {
    try {
      await onUnarchive?.()
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to unarchive note'
      toast.error(message)
    }
  }, [onUnarchive])

  const handleDelete = useCallback(async (): Promise<void> => {
    try {
      await onDelete?.()
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to delete note'
      toast.error(message)
    }
  }, [onDelete])

  const handleRestore = useCallback(async (): Promise<void> => {
    try {
      await onRestore?.()
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to restore note'
      toast.error(message)
    }
  }, [onRestore])

  if (isEditing) {
    return (
      <div className={`flex flex-col h-full w-full ${fullWidth ? '' : 'max-w-4xl mx-auto'}`}>
        <NoteEditor
          note={note}
          tagSuggestions={tagSuggestions}
          onSubmit={handleSubmit}
          onCancel={handleCancel}
          isSubmitting={updateNoteMutation.isPending}
          onArchive={view === 'active' && onArchive ? handleArchive : undefined}
          onDelete={onDelete ? handleDelete : undefined}
        />
      </div>
    )
  }

  return (
    <NoteView
      note={note}
      view={view}
      fullWidth={fullWidth}
      onEdit={handleEdit}
      onArchive={onArchive ? handleArchive : undefined}
      onUnarchive={onUnarchive ? handleUnarchive : undefined}
      onDelete={onDelete ? handleDelete : undefined}
      onRestore={onRestore ? handleRestore : undefined}
      onTagClick={onTagClick}
      onBack={onBack}
    />
  )
}
