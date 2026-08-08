/**
 * Content editor wrapper component.
 *
 * ARCHITECTURE NOTE (Jan 2026):
 * Previously supported a Markdown/Text mode toggle: Markdown mode used
 * MilkdownEditor (rich editing with inline rendering), Text mode used
 * CodeMirrorEditor (raw markdown with syntax highlighting). Milkdown caused
 * AST/cursor/formatting edge-case issues, so we simplified to always use
 * CodeMirrorEditor with custom visual markdown styling. MilkdownEditor is
 * now only used as a read-only preview (via "Reading" toggle in toolbar).
 *
 * Current features:
 * - CodeMirror-based editing with visual markdown styling
 * - "Reading" mode toggle for rendered preview (uses MilkdownEditor read-only)
 * - Wrap text preference persisted to localStorage
 * - All formatting shortcuts work via toolbar and keyboard
 */
import { useState, useCallback } from 'react'
import type { ReactNode } from 'react'
import { CodeMirrorEditor } from './CodeMirrorEditor'
import { useCharacterLimit } from '../hooks/useCharacterLimit'

/** localStorage key for wrap text preference */
const WRAP_TEXT_KEY = 'editor_wrap_text'

/** localStorage key for line numbers preference */
const LINE_NUMBERS_KEY = 'editor_line_numbers'

/** localStorage key for mono font preference */
const MONO_FONT_KEY = 'editor_mono_font'

/**
 * Load wrap text preference from localStorage.
 * Defaults to true (wrap on) if not set.
 */
function loadWrapTextPreference(): boolean {
  try {
    const stored = localStorage.getItem(WRAP_TEXT_KEY)
    return stored === null ? true : stored === 'true'
  } catch {
    return true
  }
}

/**
 * Save wrap text preference to localStorage.
 */
function saveWrapTextPreference(wrap: boolean): void {
  try {
    localStorage.setItem(WRAP_TEXT_KEY, String(wrap))
  } catch {
    // Ignore storage errors
  }
}

/**
 * Load line numbers preference from localStorage.
 * Defaults to false (line numbers off) if not set.
 */
function loadLineNumbersPreference(): boolean {
  try {
    const stored = localStorage.getItem(LINE_NUMBERS_KEY)
    return stored === 'true'
  } catch {
    return false
  }
}

/**
 * Save line numbers preference to localStorage.
 */
function saveLineNumbersPreference(show: boolean): void {
  try {
    localStorage.setItem(LINE_NUMBERS_KEY, String(show))
  } catch {
    // Ignore storage errors
  }
}

/**
 * Load mono font preference from localStorage.
 * Defaults to false (Inter) if not set.
 */
function loadMonoFontPreference(): boolean {
  try {
    const stored = localStorage.getItem(MONO_FONT_KEY)
    return stored === 'true'
  } catch {
    return false
  }
}

/**
 * Save mono font preference to localStorage.
 */
function saveMonoFontPreference(mono: boolean): void {
  try {
    localStorage.setItem(MONO_FONT_KEY, String(mono))
  } catch {
    // Ignore storage errors
  }
}

interface ContentEditorProps {
  /** Current content value (markdown string) */
  value: string
  /** Called when content changes */
  onChange: (value: string) => void
  /** Whether the editor is disabled (not focusable, for deleted/non-interactive items) */
  disabled?: boolean
  /** Whether the editor is read-only (focusable but not editable, e.g. during save) */
  readOnly?: boolean
  /**
   * Reader mode (public share view): renders content read-only but selectable,
   * hides the formatting toolbar and character counter, and keeps view-only
   * controls. Overrides `disabled`/`readOnly` for the underlying editor.
   */
  readerMode?: boolean
  /** In reader mode, default to the rendered reading view (prose) vs. raw source (prompts). */
  defaultReadingMode?: boolean
  /** Item ID for per-item reading-mode persistence (undefined during create). */
  itemId?: string
  /**
   * Asserts that an in-place itemId assignment continues a create→edit save
   * (see CodeMirrorEditor). Parents derive this from their fromCreate contract.
   */
  itemIdWasJustCreated?: boolean
  /** Whether there's an error */
  hasError?: boolean
  /** Minimum height for the editor */
  minHeight?: string
  /** Placeholder text shown when empty */
  placeholder?: string
  /** Helper text shown below the editor */
  helperText?: string
  /** Label for the field */
  label?: string
  /** Maximum content length for counter */
  maxLength?: number
  /** Error message to display */
  errorMessage?: string
  /** Whether to show border around editor */
  showBorder?: boolean
  /** Use subtle ring style instead of solid border (matches title/description focus style) */
  subtleBorder?: boolean
  /** Show Jinja2 template tools in toolbar (for prompts) */
  showJinjaTools?: boolean
  /** Called when a modal opens/closes (for beforeunload handlers) */
  onModalStateChange?: (isOpen: boolean) => void
  /** Save and close callback for command menu */
  onSaveAndClose?: () => void
  /** Discard changes callback for command menu (always shown, greyed out when !isDirty) */
  onDiscard?: () => void
  /** Original content to restore on discard (preserves undo history) */
  originalContent?: string
  /** Whether the editor has unsaved changes */
  isDirty?: boolean
  /** Ref that receives a scroll-to-line callback for external navigation (e.g., ToC) */
  scrollToLineRef?: React.MutableRefObject<((line: number) => void) | null>
  /** Whether to show the ToC toggle button in the toolbar */
  showTocToggle?: boolean
}

/**
 * ContentEditor provides a unified markdown editor with Markdown/Text mode toggle.
 *
 * Usage:
 * ```tsx
 * <ContentEditor
 *   key={contentKey}  // Increment to force remount (document switch, version restore)
 *   value={content}
 *   onChange={setContent}
 * />
 * ```
 *
 * Note: The parent component manages `contentKey` and increments it when the editor
 * needs a full reset (document switch, version restore). Do NOT include a document ID
 * in the key — that would destroy editor state during create→edit transitions.
 */
export function ContentEditor({
  value,
  onChange,
  disabled = false,
  readOnly = false,
  readerMode = false,
  defaultReadingMode = false,
  itemId,
  itemIdWasJustCreated = false,
  hasError = false,
  minHeight = '200px',
  placeholder = 'Write your content in markdown...',
  helperText,
  label = 'Content',
  maxLength,
  errorMessage,
  showBorder = true,
  subtleBorder = false,
  showJinjaTools = false,
  onModalStateChange,
  onSaveAndClose,
  onDiscard,
  originalContent,
  isDirty,
  scrollToLineRef,
  showTocToggle,
}: ContentEditorProps): ReactNode {
  const limit = useCharacterLimit(value.length, maxLength, { alwaysShow: true })

  // Wrap text preference
  const [wrapText, setWrapText] = useState(loadWrapTextPreference)

  // Handle wrap text change
  const handleWrapTextChange = useCallback((wrap: boolean): void => {
    setWrapText(wrap)
    saveWrapTextPreference(wrap)
  }, [])

  // Line numbers preference
  const [showLineNumbers, setShowLineNumbers] = useState(loadLineNumbersPreference)

  // Handle line numbers change
  const handleLineNumbersChange = useCallback((show: boolean): void => {
    setShowLineNumbers(show)
    saveLineNumbersPreference(show)
  }, [])

  // Mono font preference
  const [monoFont, setMonoFont] = useState(loadMonoFontPreference)

  // Handle mono font change
  const handleMonoFontChange = useCallback((mono: boolean): void => {
    setMonoFont(mono)
    saveMonoFontPreference(mono)
  }, [])

  // Note: Option+Z (wrap toggle) handler moved to CodeMirrorEditor
  // where it can check readingMode state

  // Compute container border classes based on props
  // Three modes: no border, solid border, or subtle ring on focus
  const getContainerBorderClasses = (): string => {
    // Reader mode (public view) shows no editor chrome — no box/ring around content.
    if (readerMode || !showBorder) {
      return ''
    }

    if (subtleBorder) {
      // Ring style that appears on focus (matches title/description)
      const ringColor = (hasError || limit.exceeded) ? 'ring-red-200 ring-2' : 'ring-gray-900/5'
      return `group-focus-within/editor:ring-2 ${ringColor}`
    }

    // Solid border style
    const borderColor = (hasError || limit.exceeded) ? 'border-red-300' : 'border-gray-200'
    return `border ${borderColor}`
  }


  return (
    <div className="group/editor">
      <div className="mb-1">
        {label && <label className="label">{label}</label>}
      </div>

      {/* Top divider — separates the metadata above from the content. In the
          normal editor it hides on focus (the ring takes over); in reader mode
          there's no ring, so it stays as the only separator. */}
      <div className={`h-0.5 bg-gray-100 mx-2 transition-opacity ${readerMode ? '' : 'group-focus-within/editor:opacity-0'}`} />

      {/* Editor container - always CodeMirror with Reading/Wrap toggles in toolbar */}
      {/* overflow-hidden clips child content to rounded corners */}
      <div className={`rounded-lg overflow-hidden transition-shadow ${getContainerBorderClasses()}`}>
        <CodeMirrorEditor
          value={value}
          onChange={onChange}
          disabled={readerMode ? false : disabled}
          readOnly={readerMode ? true : readOnly}
          readerMode={readerMode}
          defaultReadingMode={defaultReadingMode}
          itemId={itemId}
          itemIdWasJustCreated={itemIdWasJustCreated}
          minHeight={minHeight}
          placeholder={placeholder}
          wrapText={wrapText}
          onWrapTextChange={handleWrapTextChange}
          showLineNumbers={showLineNumbers}
          onLineNumbersChange={handleLineNumbersChange}
          monoFont={monoFont}
          onMonoFontChange={handleMonoFontChange}
          noPadding={subtleBorder || !showBorder}
          copyContent={value}
          showJinjaTools={showJinjaTools}
          onModalStateChange={onModalStateChange}
          onSaveAndClose={onSaveAndClose}
          onDiscard={onDiscard}
          originalContent={originalContent}
          isDirty={isDirty}
          scrollToLineRef={scrollToLineRef}
          showTocToggle={showTocToggle}
        />
      </div>

      {/* Footer (helper text, error, char counter) — hidden in reader mode */}
      {!readerMode && (
      <div className={`flex justify-between items-center mt-1 transition-opacity ${
        errorMessage || helperText || limit.showCounter ? 'opacity-100' : 'opacity-0 group-focus-within/editor:opacity-100'
      }`}>
        {errorMessage ? (
          <p className="error-text">{errorMessage}</p>
        ) : limit.message ? (
          <span className="text-xs" style={{ color: limit.color }}>{limit.message}</span>
        ) : helperText ? (
          <p className="helper-text">{helperText}</p>
        ) : (
          <span />
        )}
        {maxLength !== undefined && (
          <span className="text-xs" style={{ color: limit.color }}>
            {limit.counterText}
          </span>
        )}
      </div>
      )}
    </div>
  )
}
