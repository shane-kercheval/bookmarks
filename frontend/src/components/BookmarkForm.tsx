/**
 * Form component for adding or editing a bookmark.
 */
import { useState, useEffect, useRef } from 'react'
import type { ReactNode, FormEvent } from 'react'
import { TagInput } from './TagInput'
import type { TagInputHandle } from './TagInput'
import type { Bookmark, BookmarkCreate, BookmarkUpdate, TagCount } from '../types'
import { normalizeUrl, isValidUrl, TAG_PATTERN } from '../utils'

interface BookmarkFormProps {
  /** Existing bookmark when editing, undefined when creating */
  bookmark?: Bookmark
  /** Available tags for autocomplete */
  tagSuggestions: TagCount[]
  /** Called when form is submitted */
  onSubmit: (data: BookmarkCreate | BookmarkUpdate) => Promise<void>
  /** Called when user cancels */
  onCancel: () => void
  /** Function to fetch metadata for a URL */
  onFetchMetadata?: (url: string) => Promise<{ title: string | null; description: string | null; error: string | null }>
  /** Whether the form is being submitted */
  isSubmitting?: boolean
}

interface FormState {
  url: string
  title: string
  description: string
  tags: string[]
  storeContent: boolean
}

interface FormErrors {
  url?: string
  title?: string
  tags?: string
  general?: string
}

/**
 * BookmarkForm for creating or editing bookmarks.
 *
 * Features:
 * - URL input with "Fetch Metadata" button
 * - Auto-populated title and description from metadata
 * - Tag input with suggestions
 * - "Save page content" checkbox
 * - Validation with inline errors
 */
export function BookmarkForm({
  bookmark,
  tagSuggestions,
  onSubmit,
  onCancel,
  onFetchMetadata,
  isSubmitting = false,
}: BookmarkFormProps): ReactNode {
  const isEditing = !!bookmark

  const [form, setForm] = useState<FormState>({
    url: bookmark?.url || '',
    title: bookmark?.title || '',
    description: bookmark?.description || '',
    tags: bookmark?.tags || [],
    storeContent: true,
  })

  const [errors, setErrors] = useState<FormErrors>({})
  const [isFetchingMetadata, setIsFetchingMetadata] = useState(false)
  const [metadataFetched, setMetadataFetched] = useState(false)
  const tagInputRef = useRef<TagInputHandle>(null)

  // Track previous URL to detect changes
  const prevUrlRef = useRef(form.url)

  // Clear URL error only when URL actually changes (user is typing)
  useEffect(() => {
    if (errors.url && form.url !== prevUrlRef.current) {
      setErrors((prev) => ({ ...prev, url: undefined }))
    }
    prevUrlRef.current = form.url
  }, [form.url, errors.url])

  const handleFetchMetadata = async (): Promise<void> => {
    if (!form.url.trim()) {
      setErrors((prev) => ({ ...prev, url: 'URL is required' }))
      return
    }

    if (!isValidUrl(form.url)) {
      setErrors((prev) => ({ ...prev, url: 'Please enter a valid URL' }))
      return
    }

    if (!onFetchMetadata) return

    setIsFetchingMetadata(true)
    setErrors({})

    try {
      const metadata = await onFetchMetadata(normalizeUrl(form.url))

      if (metadata.error) {
        setErrors((prev) => ({
          ...prev,
          general: `Could not fetch metadata: ${metadata.error}`,
        }))
      }

      // Only update empty fields
      setForm((prev) => ({
        ...prev,
        title: prev.title || metadata.title || '',
        description: prev.description || metadata.description || '',
      }))

      setMetadataFetched(true)
    } catch {
      setErrors((prev) => ({
        ...prev,
        general: 'Failed to fetch metadata. You can still save the bookmark.',
      }))
    } finally {
      setIsFetchingMetadata(false)
    }
  }

  const validate = (): boolean => {
    const newErrors: FormErrors = {}

    if (!isEditing) {
      if (!form.url.trim()) {
        newErrors.url = 'URL is required'
      } else if (!isValidUrl(form.url)) {
        newErrors.url = 'Please enter a valid URL'
      }
    }

    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleSubmit = async (e: FormEvent): Promise<void> => {
    e.preventDefault()

    if (!validate()) return

    // Get any pending tag text and include it
    const pendingTag = tagInputRef.current?.getPendingValue() || ''
    const tagsToSubmit = [...form.tags]
    if (pendingTag) {
      const normalized = pendingTag.toLowerCase().trim()
      // Only add if valid and not already present
      if (TAG_PATTERN.test(normalized) && !tagsToSubmit.includes(normalized)) {
        tagsToSubmit.push(normalized)
        tagInputRef.current?.clearPending()
      }
    }

    try {
      if (isEditing) {
        // For updates, only send changed fields
        const updates: BookmarkUpdate = {}
        const normalizedUrl = normalizeUrl(form.url)
        if (normalizedUrl !== bookmark?.url) updates.url = normalizedUrl
        if (form.title !== bookmark?.title) updates.title = form.title || null
        if (form.description !== bookmark?.description)
          updates.description = form.description || null
        if (JSON.stringify(tagsToSubmit) !== JSON.stringify(bookmark?.tags))
          updates.tags = tagsToSubmit

        await onSubmit(updates)
      } else {
        // For creates, send all data (normalize URL to include protocol)
        const createData: BookmarkCreate = {
          url: normalizeUrl(form.url),
          title: form.title || undefined,
          description: form.description || undefined,
          tags: tagsToSubmit,
          store_content: form.storeContent,
        }
        await onSubmit(createData)
      }
    } catch {
      // Error handling is done in the parent component
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* General error */}
      {errors.general && (
        <div className="alert-warning">
          <p className="text-sm">{errors.general}</p>
        </div>
      )}

      {/* URL field */}
      <div>
        <label htmlFor="url" className="label">
          URL {!isEditing && <span className="text-red-500">*</span>}
        </label>
        <div className="mt-1 flex gap-2">
          <input
            type="text"
            id="url"
            value={form.url}
            onChange={(e) => setForm((prev) => ({ ...prev, url: e.target.value }))}
            placeholder="https://example.com"
            disabled={isSubmitting}
            className={`input flex-1 ${errors.url ? 'input-error' : ''}`}
          />
          {!isEditing && (
            <button
              type="button"
              onClick={handleFetchMetadata}
              disabled={isSubmitting || isFetchingMetadata || !form.url.trim()}
              className="btn-ghost shrink-0"
            >
              {isFetchingMetadata ? (
                <span className="flex items-center gap-1.5">
                  <div className="spinner-sm" />
                  Fetching...
                </span>
              ) : (
                'Fetch Metadata'
              )}
            </button>
          )}
        </div>
        {errors.url && <p className="error-text">{errors.url}</p>}
        {!isEditing && metadataFetched && !errors.general && (
          <p className="mt-1 text-sm text-green-600">Metadata fetched successfully</p>
        )}
      </div>

      {/* Title field */}
      <div>
        <label htmlFor="title" className="label">
          Title
        </label>
        <input
          type="text"
          id="title"
          value={form.title}
          onChange={(e) => setForm((prev) => ({ ...prev, title: e.target.value }))}
          placeholder="Page title"
          disabled={isSubmitting}
          className="input mt-1"
        />
      </div>

      {/* Description field */}
      <div>
        <label htmlFor="description" className="label">
          Description
        </label>
        <textarea
          id="description"
          value={form.description}
          onChange={(e) =>
            setForm((prev) => ({ ...prev, description: e.target.value }))
          }
          placeholder="Add a description..."
          rows={3}
          disabled={isSubmitting}
          className="input mt-1"
        />
      </div>

      {/* Tags field */}
      <div>
        <label htmlFor="tags" className="label">
          Tags
        </label>
        <div className="mt-1">
          <TagInput
            ref={tagInputRef}
            id="tags"
            value={form.tags}
            onChange={(tags) => setForm((prev) => ({ ...prev, tags }))}
            suggestions={tagSuggestions}
            placeholder="Add tags..."
            disabled={isSubmitting}
            error={errors.tags}
          />
        </div>
        <p className="helper-text">
          Type and press Enter to add. Use lowercase letters, numbers, and hyphens.
        </p>
      </div>

      {/* Store content checkbox (only for new bookmarks) */}
      {!isEditing && (
        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="storeContent"
            checked={form.storeContent}
            onChange={(e) =>
              setForm((prev) => ({ ...prev, storeContent: e.target.checked }))
            }
            disabled={isSubmitting}
            className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
          />
          <label htmlFor="storeContent" className="text-sm text-gray-700">
            Save page content (for search)
          </label>
        </div>
      )}

      {/* Form actions */}
      <div className="flex justify-end gap-3 pt-4">
        <button
          type="button"
          onClick={onCancel}
          disabled={isSubmitting}
          className="btn-secondary"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={isSubmitting || (!isEditing && !form.url.trim())}
          className="btn-primary"
        >
          {isSubmitting ? (
            <span className="flex items-center gap-1.5">
              <div className="spinner-sm" />
              Saving...
            </span>
          ) : isEditing ? (
            'Save Changes'
          ) : (
            'Add Bookmark'
          )}
        </button>
      </div>
    </form>
  )
}
