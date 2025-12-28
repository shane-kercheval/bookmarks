/**
 * Component for editing note content with CodeMirror markdown editor.
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import type { ReactNode, FormEvent } from 'react'
import CodeMirror from '@uiw/react-codemirror'
import { markdown } from '@codemirror/lang-markdown'
import { keymap } from '@codemirror/view'
import type { KeyBinding } from '@codemirror/view'
import type { EditorView } from '@codemirror/view'
import { Prec } from '@codemirror/state'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeSanitize from 'rehype-sanitize'
import { TagInput } from './TagInput'
import type { TagInputHandle } from './TagInput'
import type { Note, NoteCreate, NoteUpdate, TagCount } from '../types'
import { TAG_PATTERN } from '../utils'
import { config } from '../config'
import { ArchiveIcon, TrashIcon } from './icons'

/** Key prefix for localStorage draft storage */
const DRAFT_KEY_PREFIX = 'note_draft_'

interface DraftData {
  title: string
  description: string
  content: string
  tags: string[]
  savedAt: number
}

interface NoteEditorProps {
  /** Existing note when editing, undefined when creating */
  note?: Note
  /** Available tags for autocomplete */
  tagSuggestions: TagCount[]
  /** Called when form is submitted */
  onSubmit: (data: NoteCreate | NoteUpdate) => Promise<void>
  /** Called when user cancels */
  onCancel: () => void
  /** Whether the form is being submitted */
  isSubmitting?: boolean
  /** Initial tags to populate (e.g., from current list filter) */
  initialTags?: string[]
  /** Called when note is archived (shown in header when provided) */
  onArchive?: () => void
  /** Called when note is deleted (shown in header when provided) */
  onDelete?: () => void
}

interface FormState {
  title: string
  description: string
  content: string
  tags: string[]
}

interface FormErrors {
  title?: string
  description?: string
  content?: string
  tags?: string
  general?: string
}

/**
 * Get the localStorage key for a note draft.
 */
function getDraftKey(noteId?: number): string {
  return noteId ? `${DRAFT_KEY_PREFIX}${noteId}` : `${DRAFT_KEY_PREFIX}new`
}

/**
 * Load draft from localStorage if available.
 */
function loadDraft(noteId?: number): DraftData | null {
  try {
    const key = getDraftKey(noteId)
    const stored = localStorage.getItem(key)
    if (stored) {
      return JSON.parse(stored) as DraftData
    }
  } catch {
    // Ignore parse errors
  }
  return null
}

/**
 * Save draft to localStorage.
 */
function saveDraft(noteId: number | undefined, data: DraftData): void {
  try {
    const key = getDraftKey(noteId)
    localStorage.setItem(key, JSON.stringify(data))
  } catch {
    // Ignore storage errors (e.g., quota exceeded)
  }
}

/**
 * Clear draft from localStorage.
 */
function clearDraft(noteId?: number): void {
  try {
    const key = getDraftKey(noteId)
    localStorage.removeItem(key)
  } catch {
    // Ignore errors
  }
}

/**
 * Wrap selected text with markdown markers.
 * If no selection, insert markers and place cursor between them.
 */
function wrapWithMarkers(view: EditorView, before: string, after: string): boolean {
  const { state } = view
  const { from, to } = state.selection.main
  const selectedText = state.sliceDoc(from, to)

  if (selectedText) {
    // Wrap selected text
    view.dispatch({
      changes: { from, to, insert: `${before}${selectedText}${after}` },
      selection: { anchor: from + before.length, head: to + before.length },
    })
  } else {
    // No selection - insert markers and place cursor between them
    view.dispatch({
      changes: { from, insert: `${before}${after}` },
      selection: { anchor: from + before.length },
    })
  }
  return true
}

/**
 * Insert a markdown link. If text is selected, use it as the link text.
 */
function insertLink(view: EditorView): boolean {
  const { state } = view
  const { from, to } = state.selection.main
  const selectedText = state.sliceDoc(from, to)

  if (selectedText) {
    // Use selected text as link text, place cursor in URL position
    const linkText = `[${selectedText}](url)`
    view.dispatch({
      changes: { from, to, insert: linkText },
      selection: { anchor: from + selectedText.length + 3, head: from + selectedText.length + 6 },
    })
  } else {
    // Insert empty link template, place cursor in text position
    view.dispatch({
      changes: { from, insert: '[text](url)' },
      selection: { anchor: from + 1, head: from + 5 },
    })
  }
  return true
}

/**
 * Dispatch a keyboard event to the document for global handlers to catch.
 * Used to pass shortcuts through from CodeMirror to global handlers.
 */
function dispatchGlobalShortcut(key: string, metaKey: boolean): void {
  const event = new KeyboardEvent('keydown', {
    key,
    metaKey,
    ctrlKey: !metaKey, // Use ctrlKey on non-Mac
    bubbles: true,
  })
  document.dispatchEvent(event)
}

/**
 * CodeMirror keybindings for markdown formatting.
 * For global shortcuts, we consume the event (return true) to prevent
 * CodeMirror's default handling, then dispatch to global handlers.
 */
const markdownKeyBindings: KeyBinding[] = [
  // Formatting shortcuts
  { key: 'Mod-b', run: (view) => wrapWithMarkers(view, '**', '**') },
  { key: 'Mod-i', run: (view) => wrapWithMarkers(view, '*', '*') },
  { key: 'Mod-k', run: (view) => insertLink(view) },
  { key: 'Mod-Shift-x', run: (view) => wrapWithMarkers(view, '~~', '~~') },
  // Pass through to global handlers (consume event, then dispatch globally)
  {
    key: 'Mod-/',
    run: () => {
      dispatchGlobalShortcut('/', true)
      return true // Consume to prevent CodeMirror's comment toggle
    },
  },
  {
    key: 'Mod-\\',
    run: () => {
      dispatchGlobalShortcut('\\', true)
      return true
    },
  },
]

/**
 * NoteEditor provides a form for creating or editing notes.
 *
 * Features:
 * - CodeMirror editor with markdown syntax highlighting
 * - Title and description inputs
 * - Tag input with autocomplete
 * - Preview mode toggle
 * - Draft autosave to localStorage (every 30 seconds)
 * - Keyboard shortcuts: Cmd+S to save, Esc to cancel
 */
export function NoteEditor({
  note,
  tagSuggestions,
  onSubmit,
  onCancel,
  isSubmitting = false,
  initialTags,
  onArchive,
  onDelete,
}: NoteEditorProps): ReactNode {
  const isEditing = !!note

  const [form, setForm] = useState<FormState>({
    title: note?.title || '',
    description: note?.description || '',
    content: note?.content || '',
    tags: note?.tags || initialTags || [],
  })

  const [errors, setErrors] = useState<FormErrors>({})
  const [showPreview, setShowPreview] = useState(false)

  // Check for existing draft on mount - compute initial value with initializer function
  const [hasDraft, setHasDraft] = useState(() => {
    const draft = loadDraft(note?.id)
    if (!draft) return false

    // Only show prompt if draft is different from current note
    const isDifferent = isEditing
      ? draft.title !== note?.title ||
        draft.description !== (note?.description || '') ||
        draft.content !== (note?.content || '') ||
        JSON.stringify(draft.tags) !== JSON.stringify(note?.tags || [])
      : draft.title || draft.description || draft.content || draft.tags.length > 0

    return Boolean(isDifferent)
  })

  // Track if form has unsaved changes (for draft saving)
  const isDirty =
    form.title !== (note?.title || '') ||
    form.description !== (note?.description || '') ||
    form.content !== (note?.content || '') ||
    JSON.stringify(form.tags) !== JSON.stringify(note?.tags || initialTags || [])

  const tagInputRef = useRef<TagInputHandle>(null)
  const draftTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const formRef = useRef<HTMLFormElement>(null)
  const editorContainerRef = useRef<HTMLDivElement>(null)

  // Auto-save draft every 30 seconds, but only when form has changes
  useEffect(() => {
    if (!isDirty) {
      // No changes to save - clear any existing timer
      if (draftTimerRef.current) {
        clearInterval(draftTimerRef.current)
        draftTimerRef.current = null
      }
      return
    }

    draftTimerRef.current = setInterval(() => {
      const draftData: DraftData = {
        title: form.title,
        description: form.description,
        content: form.content,
        tags: form.tags,
        savedAt: Date.now(),
      }
      saveDraft(note?.id, draftData)
    }, 30000)

    return () => {
      if (draftTimerRef.current) {
        clearInterval(draftTimerRef.current)
      }
    }
  }, [form, note?.id, isDirty])

  // Handle keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent): void => {
      // Cmd+S or Ctrl+S to save
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault()
        formRef.current?.requestSubmit()
      }
      // Escape to cancel - but not when focused in an input, textarea, or the CodeMirror editor
      if (e.key === 'Escape') {
        const activeElement = document.activeElement
        const isInInput = activeElement?.tagName === 'INPUT' || activeElement?.tagName === 'TEXTAREA'
        const isInEditor = editorContainerRef.current?.contains(activeElement as Node)

        if (!isInInput && !isInEditor) {
          onCancel()
        }
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onCancel])

  const restoreDraft = useCallback((): void => {
    const draft = loadDraft(note?.id)
    if (draft) {
      setForm({
        title: draft.title,
        description: draft.description,
        content: draft.content,
        tags: draft.tags,
      })
    }
    setHasDraft(false)
  }, [note?.id])

  const discardDraft = useCallback((): void => {
    clearDraft(note?.id)
    setHasDraft(false)
  }, [note?.id])

  const validate = (): boolean => {
    const newErrors: FormErrors = {}

    // Title is required for notes
    if (!form.title.trim()) {
      newErrors.title = 'Title is required'
    } else if (form.title.length > config.limits.maxTitleLength) {
      newErrors.title = `Title exceeds ${config.limits.maxTitleLength.toLocaleString()} characters`
    }

    if (form.description.length > config.limits.maxDescriptionLength) {
      newErrors.description = `Description exceeds ${config.limits.maxDescriptionLength.toLocaleString()} characters`
    }

    if (form.content.length > config.limits.maxNoteContentLength) {
      newErrors.content = `Content exceeds ${config.limits.maxNoteContentLength.toLocaleString()} characters`
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
        const updates: NoteUpdate = {}
        if (form.title !== note?.title) updates.title = form.title
        if (form.description !== (note?.description || ''))
          updates.description = form.description || null
        if (form.content !== (note?.content || ''))
          updates.content = form.content || null
        if (JSON.stringify(tagsToSubmit) !== JSON.stringify(note?.tags || []))
          updates.tags = tagsToSubmit

        await onSubmit(updates)
      } else {
        // For creates, send all data
        const createData: NoteCreate = {
          title: form.title,
          description: form.description || undefined,
          content: form.content || undefined,
          tags: tagsToSubmit,
        }
        await onSubmit(createData)
      }

      // Clear draft on successful save
      clearDraft(note?.id)
    } catch {
      // Error handling is done in the parent component
    }
  }

  return (
    <form ref={formRef} onSubmit={handleSubmit} className="flex flex-col h-full">
      {/* Fixed header with action buttons */}
      <div className="shrink-0 bg-white flex items-center justify-between pb-4 mb-4 border-b border-gray-200">
        <div className="flex items-center gap-2">
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
            disabled={isSubmitting || !form.title.trim()}
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
              'Create Note'
            )}
          </button>
          <span className="text-xs text-gray-400 ml-2">
            <kbd className="px-1.5 py-0.5 bg-gray-100 rounded text-xs">⌘S</kbd>
          </span>
        </div>

        <div className="flex items-center gap-2">
          {onArchive && (
            <button
              type="button"
              onClick={onArchive}
              className="btn-secondary flex items-center gap-2"
              title="Archive note"
            >
              <ArchiveIcon className="h-4 w-4" />
              Archive
            </button>
          )}
          {onDelete && (
            <button
              type="button"
              onClick={onDelete}
              className="btn-secondary text-red-600 hover:text-red-700 hover:border-red-300 flex items-center gap-2"
              title="Delete note"
            >
              <TrashIcon />
              Delete
            </button>
          )}
        </div>
      </div>

      {/* Scrollable form content */}
      <div className="flex-1 overflow-y-auto min-h-0 space-y-6 pr-2">
        {/* Draft restoration prompt */}
        {hasDraft && (
        <div className="alert-info flex items-center justify-between">
          <p className="text-sm">
            You have an unsaved draft from a previous session.
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={restoreDraft}
              className="btn-secondary text-sm py-1 px-3"
            >
              Restore Draft
            </button>
            <button
              type="button"
              onClick={discardDraft}
              className="btn-secondary text-sm py-1 px-3"
            >
              Discard
            </button>
          </div>
        </div>
      )}

      {/* General error */}
      {errors.general && (
        <div className="alert-warning">
          <p className="text-sm">{errors.general}</p>
        </div>
      )}

      {/* Title field - required */}
      <div>
        <label htmlFor="title" className="label">
          Title <span className="text-red-500">*</span>
        </label>
        <input
          type="text"
          id="title"
          value={form.title}
          onChange={(e) => {
            setForm((prev) => ({ ...prev, title: e.target.value }))
            if (errors.title) {
              setErrors((prev) => ({ ...prev, title: undefined }))
            }
          }}
          placeholder="Note title"
          disabled={isSubmitting}
          maxLength={config.limits.maxTitleLength}
          className={`input mt-1 ${errors.title ? 'input-error' : ''}`}
          autoFocus
        />
        {errors.title && <p className="error-text">{errors.title}</p>}
      </div>

      {/* Description field - optional */}
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
          placeholder="Brief summary or metadata..."
          rows={2}
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

      {/* Content field with preview toggle */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <label htmlFor="content" className="label">
            Content
          </label>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setShowPreview(false)}
              className={`text-sm px-2 py-1 rounded ${
                !showPreview
                  ? 'bg-gray-200 text-gray-900'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              Edit
            </button>
            <button
              type="button"
              onClick={() => setShowPreview(true)}
              className={`text-sm px-2 py-1 rounded ${
                showPreview
                  ? 'bg-gray-200 text-gray-900'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              Preview
            </button>
          </div>
        </div>

        {showPreview ? (
          <div className="border border-gray-200 rounded-lg p-4 min-h-[200px] bg-white flex-1 overflow-y-auto">
            {form.content ? (
              <div className="prose prose-gray max-w-none">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  rehypePlugins={[rehypeSanitize]}
                >
                  {form.content}
                </ReactMarkdown>
              </div>
            ) : (
              <p className="text-gray-400 italic">No content to preview</p>
            )}
          </div>
        ) : (
          <div
            ref={editorContainerRef}
            className={`border rounded-lg overflow-hidden flex-1 ${errors.content ? 'border-red-300' : 'border-gray-200'}`}
          >
            <CodeMirror
              value={form.content}
              onChange={(value) =>
                setForm((prev) => ({ ...prev, content: value }))
              }
              extensions={[markdown(), Prec.highest(keymap.of(markdownKeyBindings))]}
              minHeight="200px"
              placeholder="Write your note in markdown..."
              editable={!isSubmitting}
              basicSetup={{
                lineNumbers: false,
                foldGutter: false,
                highlightActiveLine: true,
              }}
              className="text-sm"
            />
          </div>
        )}
        <div className="flex justify-between items-center mt-1">
          {errors.content ? (
            <p className="error-text">{errors.content}</p>
          ) : (
            <p className="helper-text">
              Supports Markdown: **bold**, *italic*, `code`, [links](url), lists, tables, etc.
            </p>
          )}
          <span className="helper-text">
            {form.content.length.toLocaleString()}/{config.limits.maxNoteContentLength.toLocaleString()}
          </span>
        </div>
      </div>
      </div>
    </form>
  )
}
