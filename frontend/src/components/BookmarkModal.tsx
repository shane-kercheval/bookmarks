/**
 * Modal wrapper for the bookmark form.
 */
import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { BookmarkForm } from './BookmarkForm'
import type { Bookmark, BookmarkCreate, BookmarkUpdate, TagCount } from '../types'

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
}

/**
 * Modal component for adding or editing bookmarks.
 *
 * Features:
 * - Focuses first input on open
 * - Closes on Escape key
 * - Closes on backdrop click
 * - Prevents body scroll when open
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
}: BookmarkModalProps): ReactNode {
  const modalRef = useRef<HTMLDivElement>(null)
  const previousActiveElement = useRef<HTMLElement | null>(null)
  const isEditing = !!bookmark

  // Prevent body scroll and handle escape key when modal is open
  useEffect(() => {
    if (!isOpen) return

    // Store previously focused element
    previousActiveElement.current = document.activeElement as HTMLElement
    document.body.style.overflow = 'hidden'

    // Handle escape key
    function handleKeyDown(e: KeyboardEvent): void {
      if (e.key === 'Escape' && !isSubmitting) {
        onClose()
      }
    }

    document.addEventListener('keydown', handleKeyDown)

    return () => {
      document.body.style.overflow = ''
      document.removeEventListener('keydown', handleKeyDown)

      // Restore focus
      if (previousActiveElement.current) {
        previousActiveElement.current.focus()
      }
    }
  }, [isOpen, isSubmitting, onClose])

  // Focus the modal on open
  useEffect(() => {
    if (isOpen && modalRef.current) {
      // Small delay to ensure the modal is rendered
      const timeout = setTimeout(() => {
        const firstInput = modalRef.current?.querySelector<HTMLInputElement>(
          'input:not([type="checkbox"]), textarea'
        )
        firstInput?.focus()
      }, 50)
      return () => clearTimeout(timeout)
    }
  }, [isOpen])

  // Handle backdrop click
  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>): void => {
    if (e.target === e.currentTarget && !isSubmitting) {
      onClose()
    }
  }

  if (!isOpen) return null

  return (
    <div
      className="modal-backdrop overflow-y-auto"
      onClick={handleBackdropClick}
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      <div
        ref={modalRef}
        className="modal-content max-w-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
          <h2 id="modal-title" className="text-base font-semibold text-gray-900">
            {isEditing ? 'Edit Bookmark' : 'Add Bookmark'}
          </h2>
          <button
            onClick={onClose}
            disabled={isSubmitting}
            className="btn-icon"
            aria-label="Close modal"
          >
            <svg
              className="h-5 w-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-4">
          <BookmarkForm
            bookmark={bookmark}
            tagSuggestions={tagSuggestions}
            onSubmit={onSubmit}
            onCancel={onClose}
            onFetchMetadata={onFetchMetadata}
            isSubmitting={isSubmitting}
            initialUrl={initialUrl}
          />
        </div>
      </div>
    </div>
  )
}
