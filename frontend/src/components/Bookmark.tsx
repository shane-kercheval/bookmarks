/**
 * Unified Bookmark component for viewing and editing bookmarks.
 *
 * Replaces separate BookmarkForm with a unified always-editable experience
 * using inline editable components.
 *
 * Features:
 * - Inline editable URL (monospace), title, tags, description
 * - Archive scheduling with inline editing
 * - ContentEditor with Markdown/Text toggle for content
 * - Save/Discard buttons appear when dirty
 * - Keyboard shortcuts: Cmd+S to save, Escape to cancel
 * - beforeunload warning when dirty
 * - Fetch metadata functionality
 */
import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import type { ReactNode, FormEvent, MouseEvent as ReactMouseEvent } from 'react'
import axios from 'axios'
import toast from 'react-hot-toast'
import { InlineEditableUrl } from './InlineEditableUrl'
import { InlineEditableTitle } from './InlineEditableTitle'
import { InlineEditableTags, type InlineEditableTagsHandle } from './InlineEditableTags'
import { InlineEditableText } from './InlineEditableText'
import { InlineEditableArchiveSchedule } from './InlineEditableArchiveSchedule'
import { ContentEditor } from './ContentEditor'
import { LinkedContentChips, type LinkedContentChipsHandle } from './LinkedContentChips'
import { UnsavedChangesDialog, StaleDialog, DeletedDialog, ConflictDialog, Tooltip, ContentAreaSpinner } from './ui'
import { SaveOverlay } from './ui/SaveOverlay'
import { ArchiveIcon, RestoreIcon, TrashIcon, CloseIcon, CheckIcon, HistoryIcon, TagIcon, LinkIcon, ChevronRightIcon, ChevronDownIcon, HelpIcon } from './icons'
import { formatDate, normalizeUrl, isValidUrl, TAG_PATTERN } from '../utils'
import { useLimits, PUBLIC_VIEW_LIMITS } from '../hooks/useLimits'
import { useDiscardConfirmation } from '../hooks/useDiscardConfirmation'
import { useDraftAutosave } from '../hooks/useDraftAutosave'
import { draftKey } from '../utils/drafts'
import { DraftRestorePrompt } from './DraftRestorePrompt'
import { useSaveAndClose } from '../hooks/useSaveAndClose'
import { useStaleCheck } from '../hooks/useStaleCheck'
import { useUnsavedChangesWarning } from '../hooks/useUnsavedChangesWarning'
import { useBookmarks } from '../hooks/useBookmarks'
import { useRelationshipState } from '../hooks/useRelationshipState'
import { useQuickCreateLinked } from '../hooks/useQuickCreateLinked'
import { useAITagIntegration } from '../hooks/useAITagIntegration'
import { useAIRelationshipIntegration } from '../hooks/useAIRelationshipIntegration'
import { useAIMetadataIntegration } from '../hooks/useAIMetadataIntegration'
import { toRelationshipInputs, relationshipsEqual } from '../utils/relationships'
import type { LinkedItem } from '../utils/relationships'
import type { Bookmark as BookmarkType, BookmarkCreate, BookmarkUpdate, RelationshipInputPayload, TagCount, UserLimits } from '../types'
import type { ArchivePreset } from '../utils'

/** Prepare fetched metadata for form state. Content is truncated to tier limits; title/description pass through so the exceeded UI can surface. */
function prepareMetadata(
  metadata: { title: string | null; description: string | null; content: string | null },
  limits: UserLimits | undefined,
): { title?: string; description?: string; content?: string } {
  const result: { title?: string; description?: string; content?: string } = {}
  if (metadata.title != null) {
    result.title = metadata.title
  }
  if (metadata.description != null) {
    result.description = metadata.description
  }
  if (metadata.content != null) {
    result.content = limits ? metadata.content.slice(0, limits.max_bookmark_content_length) : metadata.content
  }
  return result
}

/** Conflict state for 409 responses */
interface ConflictState {
  serverUpdatedAt: string
}

/** Result of building update payload */
interface BuildUpdatesResult {
  updates: BookmarkUpdate
  tagsToSubmit: string[]
}

/** Form state for the bookmark */
interface BookmarkState {
  url: string
  title: string
  description: string
  content: string
  tags: string[]
  relationships: RelationshipInputPayload[]
  archivedAt: string
  archivePreset: ArchivePreset
}

/** Validation errors */
interface FormErrors {
  url?: string
  title?: string
  description?: string
  content?: string
}

interface BookmarkProps {
  /** Existing bookmark when editing, undefined when creating */
  bookmark?: BookmarkType
  /** Available tags for autocomplete */
  tagSuggestions: TagCount[]
  /** Called when bookmark is saved */
  onSave: (data: BookmarkCreate | BookmarkUpdate) => Promise<void>
  /** Called when user closes/cancels */
  onClose: () => void
  /** Whether a save is in progress */
  isSaving?: boolean
  /** Initial URL to populate (e.g., from paste) */
  initialUrl?: string
  /** Initial tags to populate (e.g., from current list filter) */
  initialTags?: string[]
  /** Function to fetch metadata for a URL */
  onFetchMetadata?: (url: string) => Promise<{
    title: string | null
    description: string | null
    content: string | null
    error: string | null
  }>
  /** Called when bookmark is archived */
  onArchive?: () => void
  /** Called when bookmark is unarchived */
  onUnarchive?: () => void
  /** Called when bookmark is deleted */
  onDelete?: () => void
  /** Called when bookmark is restored from trash */
  onRestore?: () => void
  /** View state for conditional action buttons */
  viewState?: 'active' | 'archived' | 'deleted'
  /** Whether to use full width layout */
  fullWidth?: boolean
  /** Called to refresh the bookmark from server (for stale check). Returns the refreshed bookmark on success. */
  onRefresh?: () => Promise<BookmarkType | null>
  /** Called when history button is clicked */
  onShowHistory?: () => void
  /** Called when a linked content item is clicked for navigation */
  onNavigateToLinked?: (item: LinkedItem, event?: ReactMouseEvent) => void
  /** Pre-populated relationships from navigation state (quick-create linked) */
  initialRelationships?: RelationshipInputPayload[]
  /** Pre-populated linked item display cache from navigation state */
  initialLinkedItems?: LinkedItem[]
  /** Whether AI features are available for this user's tier */
  aiAvailable?: boolean
  /**
   * Public read-only mode: hides all owner UI (toolbars, tags, relationships,
   * history) and disables editing. Distinct from the deleted-item read-only
   * state (viewState === 'deleted'), which disables editing but still shows the
   * owner's organizational metadata.
   */
  readOnly?: boolean
  /** Owner share control, rendered in the action toolbar. Omitted in create/readOnly. */
  shareControl?: ReactNode
}

/**
 * Get initial archive state from existing bookmark.
 */
function getInitialArchiveState(bookmark?: BookmarkType): { archivedAt: string; archivePreset: ArchivePreset } {
  if (!bookmark?.archived_at) {
    return { archivedAt: '', archivePreset: 'none' }
  }
  // If there's an existing date, set to custom so user can see/edit it
  return { archivedAt: bookmark.archived_at, archivePreset: 'custom' }
}

/**
 * Bookmark provides a unified view/edit experience for bookmarks.
 */
export function Bookmark({
  bookmark,
  tagSuggestions,
  onSave,
  onClose,
  isSaving = false,
  initialUrl,
  initialTags,
  onFetchMetadata,
  onArchive,
  onUnarchive,
  onDelete,
  onRestore,
  viewState = 'active',
  fullWidth = false,
  onRefresh,
  onShowHistory,
  onNavigateToLinked,
  initialRelationships,
  initialLinkedItems,
  aiAvailable = false,
  readOnly = false,
  shareControl,
}: BookmarkProps): ReactNode {
  const isCreate = !bookmark

  // Fetch tier limits
  const { limits: fetchedLimits, isLoading: isLoadingLimits, error: limitsError } = useLimits()
  // Public read-only view: limits aren't fetched (no auth) and aren't needed
  // (editing is disabled). Fall back to permissive limits so we don't spin forever.
  const limits = fetchedLimits ?? (readOnly ? PUBLIC_VIEW_LIMITS : undefined)

  // Stale check hook
  const { fetchBookmarkMetadata } = useBookmarks()
  const fetchUpdatedAt = useCallback(async (id: string): Promise<string> => {
    const metadata = await fetchBookmarkMetadata(id)
    return metadata.updated_at
  }, [fetchBookmarkMetadata])
  const { isStale, isDeleted, serverUpdatedAt, dismiss: dismissStale } = useStaleCheck({
    // Public read-only view: disable the stale check by intent (it would fire an
    // authed `GET /bookmarks/{id}/metadata`). Passing undefined expresses "read-only ⇒
    // no stale check" rather than relying on the adapter's synthetic empty id.
    entityId: readOnly ? undefined : bookmark?.id,
    loadedUpdatedAt: bookmark?.updated_at,
    fetchUpdatedAt,
  })

  // Initialize state from bookmark or defaults
  const getInitialState = (): BookmarkState => {
    const archiveState = getInitialArchiveState(bookmark)
    return {
      url: bookmark?.url ?? initialUrl ?? '',
      title: bookmark?.title ?? '',
      description: bookmark?.description ?? '',
      content: bookmark?.content ?? '',
      tags: bookmark?.tags ?? initialTags ?? [],
      relationships: bookmark?.relationships
        ? toRelationshipInputs(bookmark.relationships, 'bookmark', bookmark.id)
        : (initialRelationships ?? []),
      archivedAt: archiveState.archivedAt,
      archivePreset: archiveState.archivePreset,
    }
  }

  const [original, setOriginal] = useState<BookmarkState>(getInitialState)
  const [current, setCurrent] = useState<BookmarkState>(getInitialState)
  const [errors, setErrors] = useState<FormErrors>({})
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [isContentExpanded, setIsContentExpanded] = useState(false)
  const [conflictState, setConflictState] = useState<ConflictState | null>(null)
  // Skip useEffect sync for a specific updated_at when manually handling refresh (e.g., from StaleDialog)
  const skipSyncForUpdatedAtRef = useRef<string | null>(null)
  // Track current content for detecting external changes (e.g., version restore) in the sync effect.
  // Using a ref avoids stale closure issues and doesn't need to be in the effect's dependency array.
  const currentContentRef = useRef(current.content)
  currentContentRef.current = current.content

  // Relationship state management (display items, add/remove handlers, cache)
  // Must be called before syncStateFromBookmark which depends on clearNewItemsCache
  const { linkedItems, handleAddRelationship, handleRemoveRelationship, clearNewItemsCache } = useRelationshipState({
    contentType: 'bookmark',
    entityId: bookmark?.id,
    serverRelationships: bookmark?.relationships,
    currentRelationships: current.relationships,
    setCurrent,
    initialLinkedItems,
  })

  const syncStateFromBookmark = useCallback(
    (nextBookmark: BookmarkType, resetEditor = false): void => {
    const archiveState = nextBookmark.archived_at
      ? { archivedAt: nextBookmark.archived_at, archivePreset: 'custom' as ArchivePreset }
      : { archivedAt: '', archivePreset: 'none' as ArchivePreset }
    const newState: BookmarkState = {
      url: nextBookmark.url,
      title: nextBookmark.title ?? '',
      description: nextBookmark.description ?? '',
      content: nextBookmark.content ?? '',
      tags: nextBookmark.tags ?? [],
      relationships: nextBookmark.relationships
        ? toRelationshipInputs(nextBookmark.relationships, 'bookmark', nextBookmark.id)
        : [],
      archivedAt: archiveState.archivedAt,
      archivePreset: archiveState.archivePreset,
    }
    setOriginal(newState)
    setCurrent(newState)
    setConflictState(null)
    clearNewItemsCache()
    if (resetEditor) {
      setContentKey((prev) => prev + 1)
    }
  }, [clearNewItemsCache])

  // Sync internal state when bookmark prop changes (e.g., after refresh from conflict resolution)
  // This is intentional - deriving form state from props when they change is a valid pattern
  useEffect(() => {
    if (!bookmark) return
    // Skip if we just manually handled the sync for this specific version (e.g., StaleDialog "Load Latest Version")
    // This prevents a race condition where this effect runs without resetEditor after
    // the manual sync already ran with resetEditor, causing the editor not to refresh
    if (skipSyncForUpdatedAtRef.current === bookmark.updated_at) {
      skipSyncForUpdatedAtRef.current = null
      return
    }
    // Reset editor if content changed externally (e.g., version restore from history sidebar).
    // After normal saves, currentContentRef already matches bookmark.content so no reset occurs.
    const needsEditorReset = (bookmark.content ?? '') !== currentContentRef.current
    syncStateFromBookmark(bookmark, needsEditorReset)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookmark?.id, bookmark?.updated_at, syncStateFromBookmark])

  // Metadata fetch state
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [isFetchingMetadata, setIsFetchingMetadata] = useState(false)
  const [showFetchSuccess, setShowFetchSuccess] = useState(false)
  const [contentKey, setContentKey] = useState(0) // Force editor remount when content is fetched
  const autoFetchedRef = useRef<string | null>(null)
  const successTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // AI tag suggestions
  const { aiTagSuggestions, isAiTagsLoading, aiTagsHasError, handleTagInputOpen, handleTagInputClose, handleTagsChange } =
    useAITagIntegration(current, setCurrent, aiAvailable, 'bookmark')
  const { aiRelationshipSuggestions, isAiRelationshipsLoading, aiRelationshipsHasError, handleLinkedContentOpen, handleLinkedContentClose, handleAddRelationshipWithDismiss } =
    useAIRelationshipIntegration({ ...current, contentId: bookmark?.id ?? null }, aiAvailable)
  const { titleSuggestProps, descriptionSuggestProps } =
    useAIMetadataIntegration(current, setCurrent, aiAvailable)

  // Refs
  const tagInputRef = useRef<InlineEditableTagsHandle>(null)
  const linkedChipsRef = useRef<LinkedContentChipsHandle>(null)
  const formRef = useRef<HTMLFormElement>(null)
  const urlInputRef = useRef<HTMLInputElement>(null)
  // Read-only mode: deleted items (restore-to-edit) or the public share view.
  const isReadOnly = readOnly || viewState === 'deleted'

  // Compute dirty state - optimized to avoid deep comparison overhead
  const isDirty = useMemo(
    () =>
      current.url !== original.url ||
      current.title !== original.title ||
      current.description !== original.description ||
      current.content.length !== original.content.length ||
      current.content !== original.content ||
      current.tags.length !== original.tags.length ||
      current.tags.some((tag, i) => tag !== original.tags[i]) ||
      !relationshipsEqual(current.relationships, original.relationships) ||
      current.archivedAt !== original.archivedAt,
    [current, original]
  )

  // Draft autosave (plan M3 step 8): protects unsaved work against tab close,
  // crash, power loss, and expired sessions. Keyed per item; 'new' covers a
  // not-yet-created one. Cleared automatically when a save lands (isDirty
  // falls false); a lingering draft surfaces as the restore prompt below.
  const { pendingDraft, restoreDraft, discardDraft, clearDraft } = useDraftAutosave<BookmarkState>({
    storageKey: draftKey('bookmark', bookmark?.id ?? 'new'),
    current,
    isDirty,
    disabled: isReadOnly,
  })

  const handleRestoreDraft = (): void => {
    const draft = restoreDraft()
    if (draft) {
      setCurrent(draft)
      // Remount the editor so it picks up the restored content.
      setContentKey((prev) => prev + 1)
    }
  }

  // Compute validity for save button
  const isValid = useMemo(() => {
    if (!limits) return false // Limits not loaded yet
    // URL is required for new bookmarks
    if (isCreate && !current.url.trim()) return false
    if (current.url.trim() && !isValidUrl(current.url)) return false
    if (current.url.length > limits.max_url_length) return false
    if (current.title.length > limits.max_title_length) return false
    if (current.description.length > limits.max_description_length) return false
    if (current.content.length > limits.max_bookmark_content_length) return false
    return true
  }, [isCreate, current.url, current.title, current.description, current.content, limits])

  // Can save when form is dirty and valid
  const canSave = isDirty && isValid

  // Navigation blocking when dirty
  const { showDialog, handleStay, handleLeave, confirmLeave } = useUnsavedChangesWarning(isDirty)

  // Discard confirmation (shows "Discard?" for 3 seconds on first click)
  const { isConfirming, requestDiscard, resetConfirmation } = useDiscardConfirmation({
    isDirty,
    onDiscard: onClose,
    onConfirmLeave: confirmLeave,
  })

  // Save and close (Cmd+Shift+S)
  const { requestSaveAndClose, checkAndClose, clearRequest: clearSaveAndClose } = useSaveAndClose({
    confirmLeave,
    onClose,
  })

  // Build update payload for existing bookmarks (shared between handleSubmit and handleConflictSaveMyVersion)
  const buildUpdates = useCallback((): BuildUpdatesResult | null => {
    if (!bookmark) return null

    // Get any pending tag text and include it
    const pendingTag = tagInputRef.current?.getPendingValue() ?? ''
    const tagsToSubmit = [...current.tags]
    if (pendingTag) {
      const normalized = pendingTag.toLowerCase().trim()
      if (TAG_PATTERN.test(normalized) && !tagsToSubmit.includes(normalized)) {
        tagsToSubmit.push(normalized)
        tagInputRef.current?.clearPending()
      }
    }

    // Only send changed fields
    const updates: BookmarkUpdate = {}
    const normalizedUrl = normalizeUrl(current.url)
    if (normalizedUrl !== bookmark.url) updates.url = normalizedUrl
    if (current.title !== (bookmark.title ?? '')) updates.title = current.title || null
    if (current.description !== (bookmark.description ?? '')) {
      updates.description = current.description || null
    }
    if (current.content !== (bookmark.content ?? '')) {
      updates.content = current.content || null
    }
    if (JSON.stringify(tagsToSubmit) !== JSON.stringify(bookmark.tags ?? [])) {
      updates.tags = tagsToSubmit
    }
    if (!relationshipsEqual(current.relationships, original.relationships)) {
      updates.relationships = current.relationships
    }
    const newArchivedAt = current.archivedAt || null
    const oldArchivedAt = bookmark.archived_at || null
    if (newArchivedAt !== oldArchivedAt) {
      updates.archived_at = newArchivedAt
    }

    return { updates, tagsToSubmit }
  }, [bookmark, current, original.relationships])

  // Auto-focus URL for new bookmarks only (if no initialUrl)
  useEffect(() => {
    if (isCreate && !initialUrl && urlInputRef.current) {
      const timer = setTimeout(() => {
        urlInputRef.current?.focus()
      }, 0)
      return () => clearTimeout(timer)
    }
  }, [isCreate, initialUrl])

  // Auto-fetch metadata when initialUrl is provided
  useEffect(() => {
    if (
      initialUrl &&
      onFetchMetadata &&
      autoFetchedRef.current !== initialUrl &&
      isValidUrl(initialUrl)
    ) {
      autoFetchedRef.current = initialUrl
      setIsFetchingMetadata(true)
      setFetchError(null)
      setShowFetchSuccess(false)
      if (successTimeoutRef.current) {
        clearTimeout(successTimeoutRef.current)
        successTimeoutRef.current = null
      }

      onFetchMetadata(normalizeUrl(initialUrl))
        .then((metadata) => {
          if (metadata.error) {
            setFetchError(`Could not retrieve info: ${metadata.error}`)
          }

          const prepared = prepareMetadata(metadata, limits)

          setCurrent((prev) => ({
            ...prev,
            ...prepared,
          }))

          // Force editor remount when content is fetched
          if (prepared.content != null) {
            setContentKey((prev) => prev + 1)
          }

          if (!metadata.error) {
            setShowFetchSuccess(true)
            if (successTimeoutRef.current) {
              clearTimeout(successTimeoutRef.current)
            }
            successTimeoutRef.current = setTimeout(() => setShowFetchSuccess(false), 2000)
          }
        })
        .catch(() => {
          setShowFetchSuccess(false)
          setFetchError('Failed to retrieve URL info. You can still save the bookmark.')
        })
        .finally(() => {
          setIsFetchingMetadata(false)
        })
    }
  }, [initialUrl, onFetchMetadata, limits])

  // Clean up any orphaned drafts from previous versions
  useEffect(() => {
    const keysToRemove: string[] = []
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (key?.startsWith('bookmark_draft_')) {
        keysToRemove.push(key)
      }
    }
    keysToRemove.forEach((key) => localStorage.removeItem(key))
  }, [])

  // beforeunload handler for navigation warning
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent): void => {
      // Only warn if dirty AND no modal is open
      if (isDirty && !isModalOpen) {
        e.preventDefault()
        e.returnValue = '' // Required for Chrome to show the dialog
      }
    }

    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [isDirty, isModalOpen])

  // Cleanup timeouts on unmount
  useEffect(() => {
    return () => {
      if (successTimeoutRef.current) {
        clearTimeout(successTimeoutRef.current)
      }
    }
  }, [])

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent): void => {
      // Cmd+Shift+S or Ctrl+Shift+S to save and close
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === 's') {
        e.preventDefault()
        if (!isReadOnly && isDirty && !isSaving) {
          requestSaveAndClose()
          formRef.current?.requestSubmit()
        }
        return
      }

      // Cmd+S or Ctrl+S to save (only if there are changes)
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault()
        if (!isReadOnly && isDirty && !isSaving) {
          formRef.current?.requestSubmit()
        }
      }

      // Don't intercept Escape when CM search panel is open — let CM handle it
      // (CM's domEventHandlers only fires for .cm-scroller events, not .cm-panels,
      // so the search panel Escape must be guarded here at the document level)
      if (e.key === 'Escape' && (e.target as HTMLElement)?.closest?.('.cm-search')) {
        return
      }

      // When confirming discard: Escape backs out, Enter confirms
      if (isConfirming) {
        if (e.key === 'Escape') {
          e.preventDefault()
          resetConfirmation()
        } else if (e.key === 'Enter') {
          e.preventDefault()
          confirmLeave() // Prevent navigation blocker from showing
          onClose()
        }
        return
      }

      // Escape to start discard (with confirmation if dirty)
      if (e.key === 'Escape') {
        requestDiscard()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [requestDiscard, isConfirming, resetConfirmation, onClose, isReadOnly, isDirty, isSaving, confirmLeave, requestSaveAndClose])

  // Fetch metadata handler
  const handleFetchMetadata = useCallback(async (): Promise<void> => {
    if (!current.url.trim()) {
      setErrors((prev) => ({ ...prev, url: 'URL is required' }))
      return
    }

    if (!isValidUrl(current.url)) {
      setErrors((prev) => ({ ...prev, url: 'Please enter a valid URL' }))
      return
    }

    if (!onFetchMetadata) return

    setIsFetchingMetadata(true)
    setFetchError(null)
    setShowFetchSuccess(false)
    if (successTimeoutRef.current) {
      clearTimeout(successTimeoutRef.current)
      successTimeoutRef.current = null
    }

    try {
      const metadata = await onFetchMetadata(normalizeUrl(current.url))

      if (metadata.error) {
        setFetchError(`Could not retrieve info: ${metadata.error}`)
      }

      const prepared = prepareMetadata(metadata, limits)

      setCurrent((prev) => ({
        ...prev,
        ...prepared,
      }))

      // Force editor remount when content is fetched
      if (prepared.content != null) {
        setContentKey((prev) => prev + 1)
      }

      if (!metadata.error) {
        setShowFetchSuccess(true)
        if (successTimeoutRef.current) {
          clearTimeout(successTimeoutRef.current)
        }
        successTimeoutRef.current = setTimeout(() => setShowFetchSuccess(false), 2000)
      }
    } catch {
      setShowFetchSuccess(false)
      setFetchError('Failed to retrieve URL info. You can still save the bookmark.')
    } finally {
      setIsFetchingMetadata(false)
    }
  }, [current.url, onFetchMetadata, limits])

  // Validation (only called after loading guard, so limits is guaranteed to exist)
  const validate = (): boolean => {
    if (!limits) return false // Type guard, should never happen in practice

    const newErrors: FormErrors = {}

    if (isCreate) {
      if (!current.url.trim()) {
        newErrors.url = 'URL is required'
      } else if (!isValidUrl(current.url)) {
        newErrors.url = 'Please enter a valid URL'
      }
    } else if (current.url.trim() && !isValidUrl(current.url)) {
      newErrors.url = 'Please enter a valid URL'
    }

    if (!newErrors.url && current.url.length > limits.max_url_length) {
      newErrors.url = 'Character limit exceeded'
    }

    if (current.title.length > limits.max_title_length) {
      newErrors.title = 'Character limit exceeded'
    }

    if (current.description.length > limits.max_description_length) {
      newErrors.description = 'Character limit exceeded'
    }

    if (current.content.length > limits.max_bookmark_content_length) {
      newErrors.content = 'Character limit exceeded'
    }

    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  // Submit handler
  const handleSubmit = async (e: FormEvent): Promise<void> => {
    e.preventDefault()

    if (isReadOnly || !validate()) return

    let tagsToSubmit: string[]

    try {
      if (isCreate) {
        // Get any pending tag text for create
        const pendingTag = tagInputRef.current?.getPendingValue() ?? ''
        tagsToSubmit = [...current.tags]
        if (pendingTag) {
          const normalized = pendingTag.toLowerCase().trim()
          if (TAG_PATTERN.test(normalized) && !tagsToSubmit.includes(normalized)) {
            tagsToSubmit.push(normalized)
            tagInputRef.current?.clearPending()
          }
        }

        const createData: BookmarkCreate = {
          url: normalizeUrl(current.url),
          title: current.title || undefined,
          description: current.description || undefined,
          content: current.content || undefined,
          tags: tagsToSubmit,
          relationships: current.relationships.length > 0 ? current.relationships : undefined,
          archived_at: current.archivedAt || undefined,
        }
        // For creates, onSave navigates away - prevent blocker from showing
        confirmLeave()
        await onSave(createData)
      } else {
        const result = buildUpdates()
        if (!result) return
        const { updates, tagsToSubmit: tags } = result
        tagsToSubmit = tags

        // Nothing changed — still honour close request, but skip the API call
        if (Object.keys(updates).length === 0) {
          checkAndClose()
          return
        }

        // Include expected_updated_at for optimistic locking (prevents overwriting concurrent edits)
        if (bookmark?.updated_at) {
          updates.expected_updated_at = bookmark.updated_at
        }

        await onSave(updates)
      }

      // Update original to match current (form is now clean)
      setOriginal({ ...current, tags: tagsToSubmit })
      // Immediately after a successful save, while the closure still holds the
      // pre-save storage key (':new' for creates, before navigation re-keys it).
      clearDraft()

      // Close if requested (Cmd+Shift+S)
      if (checkAndClose()) return
    } catch (err) {
      // Check for 409 Conflict (version mismatch)
      if (axios.isAxiosError(err) && err.response?.status === 409) {
        const detail = err.response.data?.detail
        if (detail?.error === 'conflict' && detail?.server_state) {
          setConflictState({
            serverUpdatedAt: detail.server_state.updated_at,
          })
          clearSaveAndClose()
          return
        }
      }
      // Other errors: let parent handle
      clearSaveAndClose()
      throw err
    }
  }

  // Update handlers - memoized to prevent unnecessary child re-renders
  const handleUrlChange = useCallback((url: string): void => {
    setCurrent((prev) => ({ ...prev, url }))
    setErrors((prev) => (prev.url ? { ...prev, url: undefined } : prev))
    setFetchError(null)
  }, [])

  const handleTitleChange = useCallback((title: string): void => {
    setCurrent((prev) => ({ ...prev, title }))
    setErrors((prev) => (prev.title ? { ...prev, title: undefined } : prev))
  }, [])

  const handleDescriptionChange = useCallback((description: string): void => {
    setCurrent((prev) => ({ ...prev, description }))
    setErrors((prev) => (prev.description ? { ...prev, description: undefined } : prev))
  }, [])

  const handleContentChange = useCallback((content: string): void => {
    setCurrent((prev) => ({ ...prev, content }))
    setErrors((prev) => (prev.content ? { ...prev, content: undefined } : prev))
  }, [])


  const handleArchiveScheduleChange = useCallback((archivedAt: string): void => {
    setCurrent((prev) => ({ ...prev, archivedAt }))
  }, [])

  const handleArchivePresetChange = useCallback((archivePreset: ArchivePreset): void => {
    setCurrent((prev) => ({ ...prev, archivePreset }))
  }, [])

  // Quick-create linked entity navigation
  const handleQuickCreate = useQuickCreateLinked({
    contentType: 'bookmark',
    contentId: bookmark?.id ?? null,
    contentTitle: bookmark?.title ?? (current.title || null),
    contentUrl: bookmark?.url ?? (current.url || null),
  })

  // Conflict resolution handlers
  const handleConflictLoadServerVersion = useCallback(async (): Promise<void> => {
    const refreshed = await onRefresh?.()
    if (refreshed) {
      // Set flag to skip the prop sync for this specific version since we're handling it here
      // with resetEditor=true. Otherwise the useEffect would run without resetEditor
      // and the editor wouldn't refresh properly.
      skipSyncForUpdatedAtRef.current = refreshed.updated_at
      syncStateFromBookmark(refreshed, true)
    }
  }, [onRefresh, syncStateFromBookmark])

  const handleConflictSaveMyVersion = useCallback(async (): Promise<void> => {
    const result = buildUpdates()
    if (!result) return

    const { updates, tagsToSubmit } = result

    // Guard against no-op updates (user may have reverted changes while dialog was open)
    if (Object.keys(updates).length === 0) {
      setConflictState(null)
      return
    }

    // Note: NOT including expected_updated_at - this forces the save to overwrite server version

    try {
      await onSave(updates)
      setOriginal({ ...current, tags: tagsToSubmit })
      setConflictState(null)
    } catch {
      // Show feedback so user knows save failed
      toast.error('Failed to save - please try again')
    }
  }, [buildUpdates, current, onSave])

  const handleConflictDoNothing = useCallback((): void => {
    setConflictState(null)
  }, [])

  // Prevent form submission on Enter in inputs
  const handleKeyDown = (e: React.KeyboardEvent): void => {
    if (e.key === 'Enter' && e.target instanceof HTMLInputElement) {
      e.preventDefault()
    }
  }

  // Error state: show message if limits fetch failed
  if (limitsError) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center p-4">
          <p className="text-red-600 font-medium">Failed to load configuration</p>
          <p className="text-sm text-gray-500 mt-1">Please refresh the page to try again.</p>
        </div>
      </div>
    )
  }

  // Loading guard: don't render form until limits are available
  if (isLoadingLimits || !limits) {
    return <ContentAreaSpinner label="Loading bookmark..." />
  }

  return (
    <form
      ref={formRef}
      onSubmit={handleSubmit}
      onKeyDown={handleKeyDown}
      className={`flex flex-col h-full w-full ${fullWidth ? '' : 'max-w-4xl'}`}
    >
      <SaveOverlay isVisible={isSaving} />

      {/* Sticky header (owner controls) — hidden entirely in the public read view. */}
      {!readOnly && (
      <div className="sticky top-0 z-10 shrink-0 bg-white -ml-2 pl-2 -mr-2 pr-2">
        <div className="flex items-center justify-between py-1.5 border-b border-gray-200">
          <div className="flex items-center gap-2">
          {/* Close button */}
          <button
            type="button"
            onClick={requestDiscard}
            disabled={isSaving}
            aria-label={isConfirming ? 'Discard changes' : 'Close'}
            className={`flex items-center gap-1.5 ${
              isConfirming
                ? 'btn-ghost text-red-600 hover:text-red-700 bg-red-50'
                : 'btn-ghost'
            }`}
          >
            <CloseIcon className="h-4 w-4" />
            {isConfirming ? (
              <span>Discard?</span>
            ) : (
              <span className="hidden md:inline">Close</span>
            )}
          </button>

          {/* Create/Save button - enabled when dirty and valid */}
          {!isReadOnly && (
            <button
              type="submit"
              disabled={isSaving || !canSave}
              aria-label={isCreate ? 'Create' : 'Save'}
              className="btn-primary flex items-center gap-1.5"
            >
              <CheckIcon className="h-4 w-4" />
              <span className="hidden md:inline">{isCreate ? 'Create' : 'Save'}</span>
            </button>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Share control - existing items only (omitted in create/readOnly/trash) */}
          {shareControl}

          {/* History button - existing bookmarks only */}
          {!isCreate && onShowHistory && (
            <button
              type="button"
              onClick={onShowHistory}
              disabled={isSaving}
              aria-label="History"
              className="btn-ghost flex items-center gap-2"
            >
              <HistoryIcon className="h-4 w-4" />
              <span className="hidden md:inline">History</span>
            </button>
          )}

          {/* Archive button - active bookmarks only */}
          {viewState === 'active' && onArchive && (
            <button
              type="button"
              onClick={onArchive}
              disabled={isSaving}
              aria-label="Archive"
              className="btn-ghost flex items-center gap-2"
            >
              <ArchiveIcon className="h-4 w-4" />
              <span className="hidden md:inline">Archive</span>
            </button>
          )}

          {/* Unarchive button - archived bookmarks only */}
          {viewState === 'archived' && onUnarchive && (
            <button
              type="button"
              onClick={onUnarchive}
              disabled={isSaving}
              aria-label="Restore"
              className="btn-ghost flex items-center gap-2"
            >
              <RestoreIcon />
              <span className="hidden md:inline">Restore</span>
            </button>
          )}

          {/* Restore button - deleted bookmarks only */}
          {viewState === 'deleted' && onRestore && (
            <button
              type="button"
              onClick={onRestore}
              disabled={isSaving}
              aria-label="Restore"
              className="btn-primary flex items-center gap-2"
            >
              <RestoreIcon />
              <span className="hidden md:inline">Restore</span>
            </button>
          )}

          {/* Delete button */}
          {onDelete && (
            <button
              type="button"
              onClick={onDelete}
              disabled={isSaving}
              aria-label={viewState === 'deleted' ? 'Delete permanently' : 'Delete'}
              className="btn-ghost text-red-600 hover:text-red-700 hover:bg-red-50 flex items-center gap-2"
            >
              <TrashIcon />
              <span className="hidden md:inline">
                {viewState === 'deleted' ? 'Delete Permanently' : 'Delete'}
              </span>
            </button>
          )}
          </div>
        </div>
      </div>
      )}

      {/* Scrollable content - padding with negative margin gives room for focus rings to show */}
      <div className="flex-1 overflow-y-auto min-h-0 pr-2 pl-2 -ml-2 -mr-2 pt-5 -mt-1">
        {/* Header section: banners, URL, title, description, metadata */}
        <div className="space-y-1">
          {/* Trash banner — deleted items only, never the public read view. */}
          {viewState === 'deleted' && (
            <div className="alert-warning">
              <p className="text-sm">This bookmark is in trash and cannot be edited. Restore it to make changes.</p>
            </div>
          )}

          {pendingDraft && (
            <DraftRestorePrompt
              savedAt={pendingDraft.savedAt}
              onRestore={handleRestoreDraft}
              onDiscard={discardDraft}
            />
          )}

          {/* URL with Fetch Metadata button */}
          <InlineEditableUrl
            ref={urlInputRef}
            value={current.url}
            onChange={handleUrlChange}
            placeholder="https://example.com"
            required={isCreate}
            disabled={isSaving || isReadOnly}
            readOnly={readOnly}
            error={errors.url}
            maxLength={limits.max_url_length}
            onFetchMetadata={onFetchMetadata ? handleFetchMetadata : undefined}
            isFetchingMetadata={isFetchingMetadata}
            showFetchSuccess={showFetchSuccess}
            fetchError={fetchError ?? undefined}
          />

          {/* Title */}
          <InlineEditableTitle
            value={current.title}
            onChange={handleTitleChange}
            placeholder="Page title"
            disabled={isSaving || isReadOnly}
            readOnly={readOnly}
            error={errors.title}
            maxLength={limits.max_title_length}
            {...titleSuggestProps}
          />

          {/* Description */}
          <InlineEditableText
            value={current.description}
            onChange={handleDescriptionChange}
            placeholder="Short summary displayed in lists and used in search results."
            disabled={isSaving || isReadOnly}
            readOnly={readOnly}
            maxLength={limits.max_description_length}
            error={errors.description}
            {...descriptionSuggestProps}
          />

          {/* Metadata: icons row + chips row */}
          <div className="space-y-1.5 pb-1">
            {/* Row 1: action icons + auto-archive + timestamps */}
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-gray-400">
              {/* Editing affordances (add tag / link / archive-schedule) — owner only. */}
              {!readOnly && (<>
              {/* Add tag button */}
              <Tooltip content="Add tag" compact delay={500}>
                <button
                  type="button"
                  onClick={() => tagInputRef.current?.startAdding()}
                  disabled={isSaving || isReadOnly}
                  className={`inline-flex items-center h-5 px-1 text-gray-500 rounded transition-colors ${
                    isSaving || isReadOnly ? 'cursor-not-allowed' : 'hover:text-gray-700 hover:bg-gray-100'
                  }`}
                  aria-label="Add tag"
                >
                  <TagIcon className="h-4 w-4" />
                </button>
              </Tooltip>

              {/* Add link button */}
              <Tooltip content="Link content" compact delay={500}>
                <button
                  type="button"
                  onClick={() => linkedChipsRef.current?.startAdding()}
                  disabled={isSaving || isReadOnly}
                  className={`inline-flex items-center h-5 px-1 text-gray-500 rounded transition-colors ${
                    isSaving || isReadOnly ? 'cursor-not-allowed' : 'hover:text-gray-700 hover:bg-gray-100'
                  }`}
                  aria-label="Link content"
                >
                  <LinkIcon className="h-4 w-4" />
                </button>
              </Tooltip>

              <span className="text-gray-300">·</span>

              <InlineEditableArchiveSchedule
                value={current.archivedAt}
                onChange={handleArchiveScheduleChange}
                preset={current.archivePreset}
                onPresetChange={handleArchivePresetChange}
                disabled={isSaving || isReadOnly}
              />
              </>)}

              {bookmark && (
                <>
                  {!readOnly && <span className="text-gray-300">·</span>}
                  <span>Created {formatDate(bookmark.created_at)}</span>
                  {bookmark.updated_at !== bookmark.created_at && (
                    <>
                      <span className="text-gray-300">·</span>
                      <span>Updated {formatDate(bookmark.updated_at)}</span>
                    </>
                  )}
                </>
              )}
            </div>

            {/* Row 2: tag pills + linked content chips — owner only; hidden in the public read view. */}
            {!readOnly && (
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-gray-400">
              <InlineEditableTags
                ref={tagInputRef}
                value={current.tags}
                onChange={handleTagsChange}
                suggestions={tagSuggestions}
                disabled={isSaving || isReadOnly}
                showAddButton={false}
                aiSuggestions={aiTagSuggestions}
                isAiLoading={isAiTagsLoading}
                aiHasError={aiTagsHasError}
                aiAvailable={aiAvailable}
                onOpen={handleTagInputOpen}
                onClose={handleTagInputClose}
              />

              <LinkedContentChips
                ref={linkedChipsRef}
                contentType="bookmark"
                contentId={bookmark?.id ?? null}
                items={linkedItems}
                onAdd={(item) => handleAddRelationshipWithDismiss(item, handleAddRelationship)}
                onRemove={handleRemoveRelationship}
                onNavigate={onNavigateToLinked}
                disabled={isSaving || isReadOnly}
                showAddButton={false}
                onQuickCreate={handleQuickCreate}
                aiSuggestions={aiRelationshipSuggestions}
                isAiLoading={isAiRelationshipsLoading}
                aiHasError={aiRelationshipsHasError}
                aiAvailable={aiAvailable}
                onOpen={handleLinkedContentOpen}
                onClose={handleLinkedContentClose}
              />
            </div>
            )}
          </div>
        </div>

        {/* Collapsible search content section */}
        <div className="mt-2">
          <div className="flex items-center gap-1.5 py-1.5 text-xs text-gray-400">
            <button
              type="button"
              onClick={() => setIsContentExpanded((prev) => !prev)}
              aria-expanded={isContentExpanded}
              className="flex items-center gap-1.5 hover:text-gray-500 transition-colors"
            >
              {isContentExpanded
                ? <ChevronDownIcon className="h-3.5 w-3.5" />
                : <ChevronRightIcon className="h-3.5 w-3.5" />
              }
              <span>Page Content</span>
            </button>
            <Tooltip
              content={<>Page content is auto-filled using the <svg className="inline h-3 w-3 -mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg> button above or can be added manually. This content helps Tiddly find the bookmark when searching. It is optimized for search and scraped without retaining formatting.</>}
            >
              <HelpIcon className="h-3.5 w-3.5" />
            </Tooltip>
          </div>
          {isContentExpanded && (
            // No itemIdWasJustCreated: bookmark create-saves navigate away
            // (BookmarkDetail) and this editor's key includes the id, so there
            // is no in-place create→edit transition. Accepted consequence: a
            // reading-mode toggle made while creating is not persisted
            // (self-heals on the first toggle after save) — see the
            // editor-improvements implementation plan.
            <ContentEditor
              key={`${bookmark?.id ?? 'new'}-${contentKey}`}
              value={current.content}
              onChange={handleContentChange}
              disabled={isReadOnly}
              readOnly={isSaving}
              readerMode={readOnly}
              defaultReadingMode={readOnly}
              itemId={bookmark?.id}
              hasError={!!errors.content}
              minHeight="200px"
              placeholder="Paste or type content to make this bookmark searchable. Auto-filled when you retrieve URL info."
              maxLength={limits.max_bookmark_content_length}
              errorMessage={errors.content}
              label=""
              showBorder={true}
              subtleBorder={true}
              onModalStateChange={setIsModalOpen}
              onSaveAndClose={!isReadOnly ? () => { requestSaveAndClose(); formRef.current?.requestSubmit() } : undefined}
              onDiscard={!isReadOnly ? () => { setCurrent(original); resetConfirmation() } : undefined}
              originalContent={original.content}
              isDirty={isDirty}
            />
          )}
        </div>
      </div>

      {/* Unsaved changes warning dialog */}
      <UnsavedChangesDialog
        isOpen={showDialog}
        onStay={handleStay}
        onLeave={handleLeave}
      />

      {/* Stale check dialogs */}
      {serverUpdatedAt && (
        <StaleDialog
          isOpen={isStale}
          isDirty={isDirty}
          entityType="bookmark"
          currentContent={current.content}
          onLoadServerVersion={async () => {
            const refreshed = await onRefresh?.()
            if (refreshed) {
              // Set flag to skip the prop sync for this specific version since we're handling it here
              // with resetEditor=true. Otherwise the useEffect would run without resetEditor
              // and the editor wouldn't refresh properly.
              skipSyncForUpdatedAtRef.current = refreshed.updated_at
              syncStateFromBookmark(refreshed, true)
              dismissStale()
            }
          }}
          onContinueEditing={dismissStale}
        />
      )}
      <DeletedDialog
        isOpen={isDeleted}
        entityType="bookmark"
        onGoBack={onClose}
      />

      {/* Conflict dialog (shown when save returns 409) */}
      {conflictState && (
        <ConflictDialog
          isOpen={true}
          currentContent={current.content}
          onLoadServerVersion={handleConflictLoadServerVersion}
          onSaveMyVersion={handleConflictSaveMyVersion}
          onDoNothing={handleConflictDoNothing}
        />
      )}
    </form>
  )
}
