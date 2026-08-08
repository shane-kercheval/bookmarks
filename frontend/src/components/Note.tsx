/**
 * Unified Note component for viewing and editing notes.
 *
 * Replaces separate NoteView and NoteEditor components with a single
 * always-editable experience using inline editable components.
 *
 * Features:
 * - Inline editable title, tags, description
 * - ContentEditor with Markdown/Text toggle
 * - Save/Discard buttons appear when dirty
 * - Keyboard shortcuts: Cmd+S to save, Escape to cancel
 * - beforeunload warning when dirty
 * - Read-only mode for deleted items
 */
import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import type { ReactNode, FormEvent, MouseEvent as ReactMouseEvent } from 'react'
import axios from 'axios'
import toast from 'react-hot-toast'
import { InlineEditableTitle } from './InlineEditableTitle'
import { InlineEditableTags, type InlineEditableTagsHandle } from './InlineEditableTags'
import { InlineEditableText } from './InlineEditableText'
import { InlineEditableArchiveSchedule } from './InlineEditableArchiveSchedule'
import { ContentEditor } from './ContentEditor'
import { TableOfContentsSidebar } from './TableOfContentsSidebar'
import { UnsavedChangesDialog, StaleDialog, DeletedDialog, ConflictDialog, Tooltip, ContentAreaSpinner } from './ui'
import { SaveOverlay } from './ui/SaveOverlay'
import { ArchiveIcon, RestoreIcon, TrashIcon, CloseIcon, CheckIcon, HistoryIcon, TagIcon, LinkIcon } from './icons'
import { formatDate, TAG_PATTERN } from '../utils'
import type { ArchivePreset } from '../utils'
import { useLimits, PUBLIC_VIEW_LIMITS } from '../hooks/useLimits'
import { useRightSidebarStore } from '../stores/rightSidebarStore'
import { useDiscardConfirmation } from '../hooks/useDiscardConfirmation'
import { useDraftAutosave } from '../hooks/useDraftAutosave'
import { draftKey } from '../utils/drafts'
import { DraftRestorePrompt } from './DraftRestorePrompt'
import { useSaveAndClose } from '../hooks/useSaveAndClose'
import { useStaleCheck } from '../hooks/useStaleCheck'
import { useUnsavedChangesWarning } from '../hooks/useUnsavedChangesWarning'
import { useNotes } from '../hooks/useNotes'
import { LinkedContentChips, type LinkedContentChipsHandle } from './LinkedContentChips'
import { useRelationshipState } from '../hooks/useRelationshipState'
import { useQuickCreateLinked } from '../hooks/useQuickCreateLinked'
import { useAITagIntegration } from '../hooks/useAITagIntegration'
import { useAIRelationshipIntegration } from '../hooks/useAIRelationshipIntegration'
import { useAIMetadataIntegration } from '../hooks/useAIMetadataIntegration'
import { toRelationshipInputs, relationshipsEqual } from '../utils/relationships'
import type { LinkedItem } from '../utils/relationships'
import type { Note as NoteType, NoteCreate, NoteUpdate, RelationshipInputPayload, TagCount } from '../types'

/** Conflict state for 409 responses */
interface ConflictState {
  serverUpdatedAt: string
}

/** Result of building update payload */
interface BuildUpdatesResult {
  updates: NoteUpdate
  tagsToSubmit: string[]
}

/** Form state for the note */
interface NoteState {
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
  title?: string
  description?: string
  content?: string
}

interface NoteProps {
  /** Existing note when editing, undefined when creating */
  note?: NoteType
  /** Available tags for autocomplete */
  tagSuggestions: TagCount[]
  /** Called when note is saved */
  onSave: (data: NoteCreate | NoteUpdate) => Promise<void>
  /** Called when user closes/cancels */
  onClose: () => void
  /** Whether a save is in progress */
  isSaving?: boolean
  /** Initial tags to populate (e.g., from current list filter) */
  initialTags?: string[]
  /** Called when note is archived */
  onArchive?: () => void
  /** Called when note is unarchived */
  onUnarchive?: () => void
  /** Called when note is deleted */
  onDelete?: () => void
  /** Called when note is restored from trash */
  onRestore?: () => void
  /** View state for conditional action buttons */
  viewState?: 'active' | 'archived' | 'deleted'
  /** Whether to use full width layout */
  fullWidth?: boolean
  /** Called to refresh the note from server (for stale check). Returns the refreshed note on success. */
  onRefresh?: () => Promise<NoteType | null>
  /** Called when history button is clicked */
  onShowHistory?: () => void
  /** Called when a linked content item is clicked for navigation */
  onNavigateToLinked?: (item: LinkedItem, event?: ReactMouseEvent) => void
  /** Pre-populated relationships from navigation state (quick-create linked) */
  initialRelationships?: RelationshipInputPayload[]
  /** Pre-populated linked item display cache from navigation state */
  initialLinkedItems?: LinkedItem[]
  /** Whether to show the Table of Contents toggle in the toolbar */
  showTocToggle?: boolean
  /** Whether this is a create→edit transition (preserves editor state) */
  fromCreate?: boolean
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
 * Note provides a unified view/edit experience for notes.
 */
export function Note({
  note,
  tagSuggestions,
  onSave,
  onClose,
  isSaving = false,
  initialTags,
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
  showTocToggle = false,
  fromCreate = false,
  aiAvailable = false,
  readOnly = false,
  shareControl,
}: NoteProps): ReactNode {
  const isCreate = !note

  // Fetch tier limits
  const { limits: fetchedLimits, isLoading: isLoadingLimits, error: limitsError } = useLimits()
  // Public read-only view: limits aren't fetched (no auth) and aren't needed
  // (editing is disabled). Fall back to permissive limits so we don't spin forever.
  const limits = fetchedLimits ?? (readOnly ? PUBLIC_VIEW_LIMITS : undefined)

  // Stale check hook
  const { fetchNoteMetadata } = useNotes()
  const fetchUpdatedAt = useCallback(async (id: string): Promise<string> => {
    const metadata = await fetchNoteMetadata(id)
    return metadata.updated_at
  }, [fetchNoteMetadata])
  const { isStale, isDeleted, serverUpdatedAt, dismiss: dismissStale } = useStaleCheck({
    // Public read-only view: disable the stale check by intent (it would fire an
    // authed `GET /notes/{id}/metadata`). Passing undefined expresses "read-only ⇒
    // no stale check" rather than relying on the adapter's synthetic empty id.
    entityId: readOnly ? undefined : note?.id,
    loadedUpdatedAt: note?.updated_at,
    fetchUpdatedAt,
  })

  // Get initial archive state from note
  const getInitialArchiveState = (): { archivedAt: string; archivePreset: ArchivePreset } => {
    if (!note?.archived_at) {
      return { archivedAt: '', archivePreset: 'none' }
    }
    return { archivedAt: note.archived_at, archivePreset: 'custom' }
  }

  // Initialize state from note or defaults
  // Note: useState only calls the initializer once, so useCallback would be unnecessary here
  const getInitialState = (): NoteState => {
    const archiveState = getInitialArchiveState()
    return {
      title: note?.title ?? '',
      description: note?.description ?? '',
      content: note?.content ?? '',
      tags: note?.tags ?? initialTags ?? [],
      relationships: note?.relationships
        ? toRelationshipInputs(note.relationships, 'note', note.id)
        : (initialRelationships ?? []),
      archivedAt: archiveState.archivedAt,
      archivePreset: archiveState.archivePreset,
    }
  }

  const [original, setOriginal] = useState<NoteState>(getInitialState)
  const [current, setCurrent] = useState<NoteState>(getInitialState)
  const [errors, setErrors] = useState<FormErrors>({})
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [conflictState, setConflictState] = useState<ConflictState | null>(null)
  const linkedChipsRef = useRef<LinkedContentChipsHandle>(null)
  const [contentKey, setContentKey] = useState(0)
  // Skip useEffect sync for a specific updated_at when manually handling refresh (e.g., from StaleDialog)
  const skipSyncForUpdatedAtRef = useRef<string | null>(null)
  // Track current content for detecting external changes (e.g., version restore) in the sync effect.
  // Using a ref avoids stale closure issues and doesn't need to be in the effect's dependency array.
  const currentContentRef = useRef(current.content)
  currentContentRef.current = current.content
  // Track previous note ID to distinguish create→edit transitions (which should
  // preserve editor state) from document switches (which must reset the editor).
  // See the sync effect below for how this is used.
  const previousNoteIdRef = useRef<string | undefined>(note?.id)

  // Relationship state management (display items, add/remove handlers, cache)
  // Must be called before syncStateFromNote which depends on clearNewItemsCache
  const { linkedItems, handleAddRelationship, handleRemoveRelationship, clearNewItemsCache } = useRelationshipState({
    contentType: 'note',
    entityId: note?.id,
    serverRelationships: note?.relationships,
    currentRelationships: current.relationships,
    setCurrent,
    initialLinkedItems,
  })

  const syncStateFromNote = useCallback((nextNote: NoteType, resetEditor = false): void => {
    const archiveState = nextNote.archived_at
      ? { archivedAt: nextNote.archived_at, archivePreset: 'custom' as ArchivePreset }
      : { archivedAt: '', archivePreset: 'none' as ArchivePreset }
    const newState: NoteState = {
      title: nextNote.title ?? '',
      description: nextNote.description ?? '',
      content: nextNote.content ?? '',
      tags: nextNote.tags ?? [],
      relationships: nextNote.relationships
        ? toRelationshipInputs(nextNote.relationships, 'note', nextNote.id)
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

  // Sync internal state when note prop changes (e.g., after refresh from conflict resolution)
  // This is intentional - deriving form state from props when they change is a valid pattern
  useEffect(() => {
    if (!note) return
    // Skip if we just manually handled the sync for this specific version (e.g., StaleDialog "Load Latest Version")
    // This prevents a race condition where this effect runs without resetEditor after
    // the manual sync already ran with resetEditor, causing the editor not to refresh
    if (skipSyncForUpdatedAtRef.current === note.updated_at) {
      skipSyncForUpdatedAtRef.current = null
      return
    }
    // Detect document switch: navigating to a different note than the one currently loaded.
    // This forces an editor reset even when content is identical, because undo history
    // and cursor position belong to the previous document.
    // The only exception is the create→edit transition (fromCreate), where the user just
    // saved what they were typing — editor state (focus, cursor, scroll, undo) is preserved.
    // All other undefined→UUID transitions (e.g., browser back from /new to /:id) ARE
    // document switches and must reset the editor.
    const isCreateToEdit = previousNoteIdRef.current === undefined && fromCreate
    const isDocumentSwitch = !isCreateToEdit && note.id !== previousNoteIdRef.current
    const needsEditorReset = isDocumentSwitch || (note.content ?? '') !== currentContentRef.current
    previousNoteIdRef.current = note.id
    syncStateFromNote(note, needsEditorReset)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [note?.id, note?.updated_at, syncStateFromNote])

  // Reset form state when transitioning from edit mode to create mode.
  // Without this, navigating from /notes/:id to /notes/new would keep the
  // previous note's state because useState(getInitialState) only runs on mount
  // and the sync effect skips when note is undefined.
  // Dependencies use note?.id (not note) to avoid re-running on every save where
  // setNote(updatedNote) creates a new reference. The effect only cares about
  // the defined→undefined transition, which note?.id captures.
  useEffect(() => {
    if (note) {
      // In edit mode — nothing to reset. The sync effect handles edit→edit.
      return
    }
    if (previousNoteIdRef.current === undefined) {
      // Was already in create mode (or initial mount) — no transition to handle.
      return
    }
    // Edit → create transition: reset form to fresh create-mode state.
    // Uses getInitialState() to stay in sync with initial mount behavior.
    previousNoteIdRef.current = undefined
    const freshState = getInitialState()
    setOriginal(freshState)
    setCurrent(freshState)
    setErrors({})
    setConflictState(null)
    clearNewItemsCache()
    setContentKey(prev => prev + 1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [note?.id, initialTags, initialRelationships])

  // AI tag suggestions
  const { aiTagSuggestions, isAiTagsLoading, aiTagsHasError, handleTagInputOpen, handleTagInputClose, handleTagsChange } =
    useAITagIntegration(current, setCurrent, aiAvailable, 'note')
  const { aiRelationshipSuggestions, isAiRelationshipsLoading, aiRelationshipsHasError, handleLinkedContentOpen, handleLinkedContentClose, handleAddRelationshipWithDismiss } =
    useAIRelationshipIntegration({ ...current, contentId: note?.id ?? null }, aiAvailable)
  const { titleSuggestProps, descriptionSuggestProps } =
    useAIMetadataIntegration(current, setCurrent, aiAvailable)

  // Refs
  const tagInputRef = useRef<InlineEditableTagsHandle>(null)
  const formRef = useRef<HTMLFormElement>(null)
  const titleInputRef = useRef<HTMLInputElement>(null)
  // ToC sidebar state
  const scrollToLineRef = useRef<((line: number) => void) | null>(null)
  const showToc = useRightSidebarStore((state) => state.activePanel === 'toc')

  // Read-only mode: deleted items (restore-to-edit) or the public share view.
  const isReadOnly = readOnly || viewState === 'deleted'

  // Compute dirty state - optimized to avoid deep comparison overhead
  // Check lengths first for quick short-circuit on large content
  const isDirty = useMemo(
    () =>
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
  const { pendingDraft, restoreDraft, discardDraft, clearDraft } = useDraftAutosave<NoteState>({
    storageKey: draftKey('note', note?.id ?? 'new'),
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

  // Compute validity for save button (doesn't show error messages, just checks if saveable)
  const isValid = useMemo(
    () =>
      current.title.trim().length > 0 &&
      current.title.length <= (limits?.max_title_length ?? Infinity) &&
      current.description.length <= (limits?.max_description_length ?? Infinity) &&
      current.content.length <= (limits?.max_note_content_length ?? Infinity),
    [current.title, current.description, current.content, limits]
  )

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

  // Build update payload for existing notes (shared between handleSubmit and handleConflictSaveMyVersion)
  const buildUpdates = useCallback((): BuildUpdatesResult | null => {
    if (!note) return null

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
    const updates: NoteUpdate = {}
    if (current.title !== note.title) updates.title = current.title
    if (current.description !== (note.description ?? '')) {
      updates.description = current.description || null
    }
    if (current.content !== (note.content ?? '')) {
      updates.content = current.content || null
    }
    if (JSON.stringify(tagsToSubmit) !== JSON.stringify(note.tags ?? [])) {
      updates.tags = tagsToSubmit
    }
    if (!relationshipsEqual(current.relationships, original.relationships)) {
      updates.relationships = current.relationships
    }
    const newArchivedAt = current.archivedAt || null
    const oldArchivedAt = note.archived_at || null
    if (newArchivedAt !== oldArchivedAt) {
      updates.archived_at = newArchivedAt
    }

    return { updates, tagsToSubmit }
  }, [note, current, original.relationships])

  // Auto-focus title for new notes only
  useEffect(() => {
    if (isCreate && titleInputRef.current) {
      // Small delay to ensure component is fully mounted
      const timer = setTimeout(() => {
        titleInputRef.current?.focus()
      }, 0)
      return () => clearTimeout(timer)
    }
  }, [isCreate])

  // Clean up any orphaned drafts from previous versions
  useEffect(() => {
    const keysToRemove: string[] = []
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (key?.startsWith('note_draft_')) {
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

  // Validation (only called after loading guard, so limits is guaranteed to exist)
  const validate = (): boolean => {
    if (!limits) return false // Type guard, should never happen in practice

    const newErrors: FormErrors = {}

    if (!current.title.trim()) {
      newErrors.title = 'Title is required'
    } else if (current.title.length > limits.max_title_length) {
      newErrors.title = 'Character limit exceeded'
    }

    if (current.description.length > limits.max_description_length) {
      newErrors.description = 'Character limit exceeded'
    }

    if (current.content.length > limits.max_note_content_length) {
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

        const createData: NoteCreate = {
          title: current.title,
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
        if (note?.updated_at) {
          updates.expected_updated_at = note.updated_at
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
          // Don't propagate error - we're handling it with the dialog
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
    contentType: 'note',
    contentId: note?.id ?? null,
    contentTitle: note?.title ?? (current.title || null),
  })

  // Conflict resolution handlers
  const handleConflictLoadServerVersion = useCallback(async (): Promise<void> => {
    // Use onRefresh to fetch latest version from server
    // This updates the parent's state, which will flow down as new props
    const refreshed = await onRefresh?.()
    if (refreshed) {
      // Set flag to skip the prop sync for this specific version since we're handling it here
      // with resetEditor=true. Otherwise the useEffect would run without resetEditor
      // and the editor wouldn't refresh properly.
      skipSyncForUpdatedAtRef.current = refreshed.updated_at
      syncStateFromNote(refreshed, true)
    }
  }, [onRefresh, syncStateFromNote])

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
    return <ContentAreaSpinner label="Loading note..." />
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

          {/* History button - existing notes only */}
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

          {/* Archive button - active notes only */}
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

          {/* Unarchive button - archived notes only */}
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

          {/* Restore button - deleted notes only */}
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
        {/* Header section: banners, title, description, metadata */}
        <div className="space-y-1">
          {/* Trash banner — deleted items only, never the public read view. */}
          {viewState === 'deleted' && (
            <div className="alert-warning">
              <p className="text-sm">This note is in trash and cannot be edited. Restore it to make changes.</p>
            </div>
          )}

          {pendingDraft && (
            <DraftRestorePrompt
              savedAt={pendingDraft.savedAt}
              onRestore={handleRestoreDraft}
              onDiscard={discardDraft}
            />
          )}

          {/* Title */}
          <InlineEditableTitle
            ref={titleInputRef}
            value={current.title}
            onChange={handleTitleChange}
            placeholder="Note title"
            required
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
            placeholder="Add a description..."
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

              {note && (
                <>
                  {!readOnly && <span className="text-gray-300">·</span>}
                  <span>Created {formatDate(note.created_at)}</span>
                  {note.updated_at !== note.created_at && (
                    <>
                      <span className="text-gray-300">·</span>
                      <span>Updated {formatDate(note.updated_at)}</span>
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
                contentType="note"
                contentId={note?.id ?? null}
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

        {/* Content editor */}
        {/* Key uses contentKey only (not note?.id) so that the create→edit transition
          * does NOT remount CodeMirror. The sync effect above handles incrementing
          * contentKey for all cases that need a remount: document switch between
          * existing notes, version restore, and conflict resolution.
          * DO NOT add note?.id back to this key — it would destroy editor state on save. */}
        <ContentEditor
          key={contentKey}
          value={current.content}
          onChange={handleContentChange}
          disabled={isReadOnly}
          readOnly={isSaving}
          readerMode={readOnly}
          defaultReadingMode={readOnly}
          itemId={note?.id}
          itemIdWasJustCreated={fromCreate}
          hasError={!!errors.content}
          minHeight="200px"
          placeholder="Write your note in markdown..."
          maxLength={limits.max_note_content_length}
          errorMessage={errors.content}
          label=""
          showBorder={true}
          subtleBorder={true}
          onModalStateChange={setIsModalOpen}
          onSaveAndClose={!isReadOnly ? () => { requestSaveAndClose(); formRef.current?.requestSubmit() } : undefined}
          onDiscard={!isReadOnly ? () => { setCurrent(original); resetConfirmation() } : undefined}
          originalContent={original.content}
          isDirty={isDirty}
          scrollToLineRef={scrollToLineRef}
          showTocToggle={showTocToggle}
        />
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
          entityType="note"
          currentContent={current.content}
          onLoadServerVersion={async () => {
            const refreshed = await onRefresh?.()
            if (refreshed) {
              // Set flag to skip the prop sync for this specific version since we're handling it here
              // with resetEditor=true. Otherwise the useEffect would run without resetEditor
              // and the editor wouldn't refresh properly.
              skipSyncForUpdatedAtRef.current = refreshed.updated_at
              syncStateFromNote(refreshed, true)
              dismissStale()
            }
          }}
          onContinueEditing={dismissStale}
        />
      )}
      <DeletedDialog
        isOpen={isDeleted}
        entityType="note"
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

      {/* Table of Contents sidebar */}
      {showTocToggle && showToc && (
        <TableOfContentsSidebar
          content={current.content}
          onHeadingClick={(line) => scrollToLineRef.current?.(line)}
        />
      )}
    </form>
  )
}
