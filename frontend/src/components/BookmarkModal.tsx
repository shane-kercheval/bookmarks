/**
 * Modal wrapper for the bookmark form.
 */
import type { ReactNode } from 'react'
import { BookmarkForm } from './BookmarkForm'
import type { Bookmark, BookmarkCreate, BookmarkUpdate, TagCount } from '../types'
import { Modal } from './ui/Modal'

interface BookmarkModalProps {
  /** Whether the modal is open */
  isOpen: boolean
  /** Called when the modal should close */
  onClose: () => void
  /** Existing bookmark when editing, undefined when creating */
  bookmark?: Bookmark
  /** Available tags for autocomplete */
  tagSuggestions: TagCount[]
  /** Called when form is submitted */
  onSubmit: (data: BookmarkCreate | BookmarkUpdate) => Promise<void>
  /** Function to fetch metadata for a URL */
  onFetchMetadata?: (url: string) => Promise<{ title: string | null; description: string | null; content: string | null; error: string | null }>
  /** Whether the form is being submitted */
  isSubmitting?: boolean
  /** Initial URL to populate (e.g., from paste) - triggers auto-fetch */
  initialUrl?: string
  /** Initial tags to populate (e.g., from current list filter) */
  initialTags?: string[]
}

/**
 * Modal component for adding or editing bookmarks.
 * Uses the shared Modal component for backdrop, escape key, focus management, and scroll lock.
 */
export function BookmarkModal({
  isOpen,
  onClose,
  bookmark,
  tagSuggestions,
  onSubmit,
  onFetchMetadata,
  isSubmitting = false,
  initialUrl,
  initialTags,
}: BookmarkModalProps): ReactNode {
  const isEditing = !!bookmark

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={isEditing ? 'Edit Bookmark' : 'Add Bookmark'}
      maxWidth="max-w-2xl"
      canClose={!isSubmitting}
    >
      <BookmarkForm
        bookmark={bookmark}
        tagSuggestions={tagSuggestions}
        onSubmit={onSubmit}
        onCancel={onClose}
        onFetchMetadata={onFetchMetadata}
        isSubmitting={isSubmitting}
        initialUrl={initialUrl}
        initialTags={initialTags}
      />
    </Modal>
  )
}
