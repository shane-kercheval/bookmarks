/**
 * Form component for adding or editing a bookmark.
 */
import { useState, useEffect, useRef } from 'react'
import type { ReactNode, FormEvent } from 'react'
import { TagInput } from './TagInput'
import type { TagInputHandle } from './TagInput'
import type { Bookmark, BookmarkCreate, BookmarkUpdate, TagCount } from '../types'
import { normalizeUrl, isValidUrl, TAG_PATTERN } from '../utils'
import { config } from '../config'

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
  onFetchMetadata?: (url: string) => Promise<{
    title: string | null
    description: string | null
    content: string | null
    error: string | null
  }>
  /** Whether the form is being submitted */
  isSubmitting?: boolean
  /** Initial URL to populate (e.g., from paste) - triggers auto-fetch */
  initialUrl?: string
  /** Initial tags to populate (e.g., from current list filter) */
  initialTags?: string[]
}

interface FormState {
  url: string
  title: string
  description: string
  content: string
  tags: string[]
}

interface FormErrors {
  url?: string
  title?: string
  description?: string
  content?: string
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
 * - Validation with inline errors
 */
export function BookmarkForm({
  bookmark,
  tagSuggestions,
  onSubmit,
  onCancel,
  onFetchMetadata,
  isSubmitting = false,
  initialUrl,
  initialTags,
}: BookmarkFormProps): ReactNode {
  const isEditing = !!bookmark

  const [form, setForm] = useState<FormState>({
    url: bookmark?.url || initialUrl || '',
    title: bookmark?.title || '',
    description: bookmark?.description || '',
    content: bookmark?.content || '',
    tags: bookmark?.tags || initialTags || [],
  })

  // Track if we've already auto-fetched for this initialUrl
  const autoFetchedRef = useRef<string | null>(null)

  const [errors, setErrors] = useState<FormErrors>({})
  const [isFetchingMetadata, setIsFetchingMetadata] = useState(false)
  const [showFetchSuccess, setShowFetchSuccess] = useState(false)
  const tagInputRef = useRef<TagInputHandle>(null)
  const successTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Track previous URL to detect changes
  const prevUrlRef = useRef(form.url)

  // Clear URL error only when URL actually changes (user is typing)
  useEffect(() => {
    if (errors.url && form.url !== prevUrlRef.current) {
      setErrors((prev) => ({ ...prev, url: undefined }))
    }
    prevUrlRef.current = form.url
  }, [form.url, errors.url])

  // Auto-fetch metadata when initialUrl is provided (e.g., from paste)
  useEffect(() => {
    if (
      initialUrl &&
      onFetchMetadata &&
      autoFetchedRef.current !== initialUrl &&
      isValidUrl(initialUrl)
    ) {
      autoFetchedRef.current = initialUrl
      setIsFetchingMetadata(true)
      setErrors({})

      onFetchMetadata(normalizeUrl(initialUrl))
        .then((metadata) => {
          if (metadata.error) {
            setErrors((prev) => ({
              ...prev,
              general: `Could not fetch metadata: ${metadata.error}`,
            }))
          }

          setForm((prev) => ({
            ...prev,
            title: metadata.title || '',
            description: metadata.description || '',
            content: metadata.content || '',
          }))

          setShowFetchSuccess(true)
          if (successTimeoutRef.current) {
            clearTimeout(successTimeoutRef.current)
          }
          successTimeoutRef.current = setTimeout(() => setShowFetchSuccess(false), 2000)
        })
        .catch(() => {
          setErrors((prev) => ({
            ...prev,
            general: 'Failed to fetch metadata. You can still save the bookmark.',
          }))
        })
        .finally(() => {
          setIsFetchingMetadata(false)
        })
    }
  }, [initialUrl, onFetchMetadata])

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (successTimeoutRef.current) {
        clearTimeout(successTimeoutRef.current)
      }
    }
  }, [])

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

      // Override fields with fetched values
      setForm((prev) => ({
        ...prev,
        title: metadata.title || '',
        description: metadata.description || '',
        content: metadata.content || '',
      }))

      // Show success checkmark temporarily
      setShowFetchSuccess(true)
      if (successTimeoutRef.current) {
        clearTimeout(successTimeoutRef.current)
      }
      successTimeoutRef.current = setTimeout(() => setShowFetchSuccess(false), 2000)
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

    if (form.title.length > config.limits.maxTitleLength) {
      newErrors.title = `Title exceeds ${config.limits.maxTitleLength.toLocaleString()} characters`
    }

    if (form.description.length > config.limits.maxDescriptionLength) {
      newErrors.description = `Description exceeds ${config.limits.maxDescriptionLength.toLocaleString()} characters`
    }

    if (form.content.length > config.limits.maxContentLength) {
      newErrors.content = `Content exceeds ${config.limits.maxContentLength.toLocaleString()} characters`
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
        if (form.content) updates.content = form.content
        if (JSON.stringify(tagsToSubmit) !== JSON.stringify(bookmark?.tags))
          updates.tags = tagsToSubmit

        await onSubmit(updates)
      } else {
        // For creates, send all data (normalize URL to include protocol)
        const createData: BookmarkCreate = {
          url: normalizeUrl(form.url),
          title: form.title || undefined,
          description: form.description || undefined,
          content: form.content || undefined,
          tags: tagsToSubmit,
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
          <button
            type="button"
            onClick={handleFetchMetadata}
            disabled={isSubmitting || isFetchingMetadata || !form.url.trim()}
            className="btn-icon shrink-0"
            title="Fetch metadata from URL"
          >
            {isFetchingMetadata ? (
              <div className="spinner-sm" />
            ) : showFetchSuccess ? (
              <svg className="h-5 w-5 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            ) : (
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            )}
          </button>
        </div>
        {errors.url && <p className="error-text">{errors.url}</p>}
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
          maxLength={config.limits.maxTitleLength}
          className={`input mt-1 ${errors.title ? 'input-error' : ''}`}
        />
        {errors.title && <p className="error-text">{errors.title}</p>}
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
          maxLength={config.limits.maxDescriptionLength}
          className={`input mt-1 ${errors.description ? 'input-error' : ''}`}
        />
        <div className="flex justify-between items-center">
          {errors.description ? (
            <p className="error-text">{errors.description}</p>
          ) : (
            <span />
          )}
          <span className="helper-text">
            {form.description.length.toLocaleString()}/{config.limits.maxDescriptionLength.toLocaleString()}
          </span>
        </div>
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

      {/* Content field */}
      <div>
        <label htmlFor="content" className="label">
          Content
        </label>
        <textarea
          id="content"
          value={form.content}
          onChange={(e) =>
            setForm((prev) => ({ ...prev, content: e.target.value }))
          }
          placeholder="Page content (auto-filled when fetching metadata, or paste for private URLs)..."
          rows={4}
          disabled={isSubmitting}
          className={`input mt-1 text-sm ${errors.content ? 'input-error' : ''}`}
        />
        <div className="flex justify-between items-center">
          <p className="helper-text">
            {errors.content || 'Auto-populated from public URLs or paste manually for private pages.'}
          </p>
          <span className="helper-text">
            {form.content.length.toLocaleString()}/{config.limits.maxContentLength.toLocaleString()}
          </span>
        </div>
      </div>

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
