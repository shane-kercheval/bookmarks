/**
 * CodeMirror-based plain text editor.
 * Provides syntax highlighting and formatting shortcuts for markdown editing.
 *
 * This is the main editor used by ContentEditor.
 * Includes optional "Reading" mode that shows read-only Milkdown preview.
 */
import { useMemo, useRef, useCallback, useState, useEffect } from 'react'
import type { ReactNode } from 'react'
import CodeMirror, { type ReactCodeMirrorRef } from '@uiw/react-codemirror'
import { markdown } from '@codemirror/lang-markdown'
import { languages } from '@codemirror/language-data'
import { keymap, EditorView } from '@codemirror/view'
import { markdownStyleExtension, createFontTheme } from '../utils/markdownStyleExtension'
import type { KeyBinding } from '@codemirror/view'
import { autocompletion, completionStatus } from '@codemirror/autocomplete'
import { Prec, Compartment, EditorState } from '@codemirror/state'
import { indentUnit } from '@codemirror/language'
import { search } from '@codemirror/search'
import { CopyToClipboardButton } from './ui/CopyToClipboardButton'
import { Tooltip } from './ui/Tooltip'
import { MilkdownEditor } from './MilkdownEditor'
import {
  ToolbarSeparator,
  BoldIcon,
  ItalicIcon,
  StrikethroughIcon,
  HighlightIcon,
  InlineCodeIcon,
  CodeBlockIcon,
  LinkIcon,
  BulletListIcon,
  OrderedListIcon,
  ChecklistIcon,
  BlockquoteIcon,
  HorizontalRuleIcon,
  HeadingIcon,
  SaveIcon,
  JinjaVariableIcon,
  JinjaIfIcon,
  JinjaIfTrimIcon,
  WrapIcon,
  LineNumbersIcon,
  MonoFontIcon,
  TableOfContentsIcon,
  ReadingIcon,
} from './editor/EditorToolbarIcons'
import { useRightSidebarStore } from '../stores/rightSidebarStore'
import { CloseIcon, HistoryIcon } from './icons'
import { JINJA_VARIABLE, JINJA_IF_BLOCK, JINJA_IF_BLOCK_TRIM } from './editor/jinjaTemplates'
import { createSlashCommandSource, slashCommandAddToOptions, scrollFadePlugin } from '../utils/slashCommands'
import { wasEditorFocused } from '../utils/editorUtils'
import { toCodeMirrorKeymap } from '../shortcuts/adapters/codemirror'
import { dispatchRegistryShortcut } from '../shortcuts/dispatch'
import { getShortcut, type ShortcutId } from '../shortcuts/registry'
import { CAPTURE_PHASE_IDS } from '../shortcuts/capturePhase'
import { findMatchingShortcut } from '../shortcuts/matcher'
import { assertNoDuplicateMatchShapes } from '../shortcuts/useGlobalShortcuts'
import { shortcutTooltipContent } from './editor/shortcutTooltip'
import {
  toggleWrapMarkers,
  toggleLinePrefix,
  insertLink,
  insertCodeBlock,
  insertHorizontalRule,
  insertText,
  LINE_PREFIXES,
} from '../utils/editorFormatting'
import { buildEditorCommands, type MenuCallbacks, type EditorCommand } from './editor/editorCommands'
import { EditorCommandMenu } from './editor/EditorCommandMenu'
import { readReadingMode, touchReadingMode, writeReadingMode } from '../utils/readingModeCache'
import { findRenderedHeading } from '../utils/headingNavigation'

/** Markdown formatting markers for wrap-style formatting. */
const MARKERS = {
  bold: { before: '**', after: '**' },
  italic: { before: '*', after: '*' },
  strikethrough: { before: '~~', after: '~~' },
  highlight: { before: '==', after: '==' },
  inlineCode: { before: '`', after: '`' },
} as const

interface CodeMirrorEditorProps {
  /** Current content value */
  value: string
  /** Called when content changes */
  onChange: (value: string) => void
  /** Whether the editor is disabled (not focusable, for deleted/non-interactive items) */
  disabled?: boolean
  /** Whether the editor is read-only (focusable but not editable, e.g. during save) */
  readOnly?: boolean
  /**
   * Reader mode (public share view): hides the text-formatting toolbar entirely
   * (those buttons mutate content) while keeping the view-only controls (wrap,
   * line numbers, mono, reading, copy). Pair with readOnly + non-disabled so the
   * content stays selectable/copyable but not editable.
   */
  readerMode?: boolean
  /** Initial value for the reading-mode toggle in reader mode (renders Milkdown preview by default). */
  defaultReadingMode?: boolean
  /**
   * Item ID for per-item reading-mode persistence (see utils/readingModeCache).
   * Undefined during create (no ID yet → no entry → markdown mode). Unlike the
   * parents' React `key` (which must NOT contain the item ID — see the
   * contentKey comments in Note/Prompt), this is an ordinary prop and does not
   * affect remounting.
   */
  itemId?: string
  /**
   * Asserts that an in-place `undefined → itemId` assignment continues the
   * create→edit transition (the parent just saved a brand-new item without
   * remounting this editor), authorizing migration of the current reading mode
   * to the new ID. The editor cannot infer this itself: navigating from a
   * create view to an EXISTING item also delivers an ID in place (one render
   * before the parent's corrective contentKey remount), and writing on that
   * would poison the existing item's remembered mode. Parents derive this from
   * their fromCreate contract; parents without an in-place create→edit
   * transition simply never assert it.
   */
  itemIdWasJustCreated?: boolean
  /** Minimum height for the editor */
  minHeight?: string
  /** Placeholder text shown when empty */
  placeholder?: string
  /** Whether to wrap long lines */
  wrapText?: boolean
  /** Called when wrap text preference changes */
  onWrapTextChange?: (wrap: boolean) => void
  /** Whether to show line numbers */
  showLineNumbers?: boolean
  /** Called when line numbers preference changes */
  onLineNumbersChange?: (show: boolean) => void
  /** Whether to use monospace font */
  monoFont?: boolean
  /** Called when mono font preference changes */
  onMonoFontChange?: (mono: boolean) => void
  /** Remove padding to align text with other elements */
  noPadding?: boolean
  /** Content for the copy button (if provided, copy button is shown) */
  copyContent?: string
  /** Show Jinja2 template tools in toolbar (for prompts) */
  showJinjaTools?: boolean
  /** Called when a modal opens/closes (for beforeunload handlers) */
  onModalStateChange?: (isOpen: boolean) => void
  /** Save and close callback for command menu */
  onSaveAndClose?: () => void
  /** Discard changes callback for command menu (always shown, greyed out when !isDirty).
   *  CodeMirrorEditor replaces editor content via CM dispatch (preserving undo history)
   *  before calling this callback, so the parent only needs to reset metadata state. */
  onDiscard?: () => void
  /** Original content to restore on discard (used for CM dispatch instead of remount) */
  originalContent?: string
  /** Whether the editor has unsaved changes (controls discard command disabled state) */
  isDirty?: boolean
  /**
   * Ref that receives a scroll-to-line callback for external navigation
   * (e.g., ToC). Mode-dependent semantics, by design: in markdown mode any
   * valid line scrolls; in reading mode the line must identify a parsed
   * heading (resolved against the rendered DOM via headingNavigation.ts) and
   * anything else safely no-ops — a dead click beats a wrong jump.
   */
  scrollToLineRef?: React.MutableRefObject<((line: number) => void) | null>
  /** Whether to show the ToC toggle button in the toolbar */
  showTocToggle?: boolean
}

/**
 * Registry ids the CodeMirror keymap owns. Order is the source of truth for
 * the emitted KeyBinding[] (CM tries each in turn; first to return true wins).
 *
 * Includes 'app.showShortcuts' for the passthrough binding — CM consumes
 * Cmd+Shift+/ to prevent CM's default `toggleComment`, then dispatches a
 * synthetic event that the global hook picks up via the matcher.
 */
const CM_KEYMAP_IDS = [
  'editor.bold',
  'editor.italic',
  'editor.strikethrough',
  'editor.highlight',
  'editor.blockquote',
  'editor.inlineCode',
  'editor.codeBlock',
  'editor.bulletList',
  'editor.numberedList',
  'editor.checklist',
  'editor.insertLink',
  'editor.horizontalRule',
  'app.showShortcuts',
] as const satisfies readonly ShortcutId[]

type CmHandlers = Record<typeof CM_KEYMAP_IDS[number], (view: EditorView) => boolean>

/** Wrap a command so it no-ops when the editor is readOnly. */
function ifWritable(cmd: (view: EditorView) => boolean): (view: EditorView) => boolean {
  return (view) => view.state.readOnly ? false : cmd(view)
}

function createMarkdownKeyBindings(): KeyBinding[] {
  const handlers: CmHandlers = {
    'editor.bold': ifWritable((view) => toggleWrapMarkers(view, MARKERS.bold.before, MARKERS.bold.after)),
    'editor.italic': ifWritable((view) => toggleWrapMarkers(view, MARKERS.italic.before, MARKERS.italic.after)),
    'editor.strikethrough': ifWritable((view) => toggleWrapMarkers(view, MARKERS.strikethrough.before, MARKERS.strikethrough.after)),
    'editor.highlight': ifWritable((view) => toggleWrapMarkers(view, MARKERS.highlight.before, MARKERS.highlight.after)),
    'editor.blockquote': ifWritable((view) => toggleLinePrefix(view, LINE_PREFIXES.blockquote)),
    'editor.inlineCode': ifWritable((view) => toggleWrapMarkers(view, MARKERS.inlineCode.before, MARKERS.inlineCode.after)),
    'editor.codeBlock': ifWritable((view) => insertCodeBlock(view)),
    'editor.bulletList': ifWritable((view) => toggleLinePrefix(view, LINE_PREFIXES.bulletList)),
    'editor.numberedList': ifWritable((view) => toggleLinePrefix(view, LINE_PREFIXES.numberedList)),
    'editor.checklist': ifWritable((view) => toggleLinePrefix(view, LINE_PREFIXES.checklist)),
    'editor.insertLink': ifWritable((view) => insertLink(view)),
    'editor.horizontalRule': ifWritable((view) => insertHorizontalRule(view)),
    // Passthrough: consume locally so CM's default keymap doesn't fire, then
    // dispatch a synthetic event the global hook picks up.
    'app.showShortcuts': () => {
      dispatchRegistryShortcut('app.showShortcuts')
      return true
    },
  }
  return toCodeMirrorKeymap(CM_KEYMAP_IDS, handlers)
}


/**
 * Toolbar button for CodeMirror editor.
 *
 * Uses wasEditorFocused() guard to prevent clicks on invisible buttons.
 * When the toolbar is hidden (opacity-0), clicking where a button would be
 * should just focus the editor and reveal the toolbar, not trigger the action.
 */
interface ToolbarButtonProps {
  onClick: () => void
  /** Tooltip content. ReactNode so multi-line label-on-top, shortcut-below renders. */
  title: ReactNode
  children: ReactNode
}

function ToolbarButton({ onClick, title, children }: ToolbarButtonProps): ReactNode {
  return (
    <Tooltip content={title} compact delay={500}>
      <button
        type="button"
        tabIndex={-1}
        onMouseDown={(e) => {
          // On mobile (< md), buttons are always visible so always execute
          // On desktop, only execute if editor was already focused (toolbar visible)
          const isMobileView = window.innerWidth < 768
          if (isMobileView || wasEditorFocused(e.currentTarget)) {
            e.preventDefault()
            onClick()
          }
          // If editor wasn't focused (desktop), let the click naturally focus the editor
          // which will reveal the toolbar (but won't execute the action)
        }}
        className="p-1.5 rounded text-gray-500 hover:text-gray-700 hover:bg-gray-100 transition-colors flex-shrink-0"
      >
        {children}
      </button>
    </Tooltip>
  )
}

/**
 * CodeMirrorEditor provides a raw markdown editor with syntax highlighting.
 *
 * Features:
 * - CodeMirror editor with markdown syntax highlighting
 * - Formatting toolbar with buttons for common markdown operations
 * - Keyboard shortcuts for formatting (Cmd+B, Cmd+I, Cmd+K, Cmd+Shift+X)
 * - Optional text wrapping
 */
export function CodeMirrorEditor({
  value,
  onChange,
  disabled = false,
  readOnly = false,
  readerMode = false,
  defaultReadingMode = false,
  itemId,
  itemIdWasJustCreated = false,
  minHeight = '200px',
  placeholder = 'Write your content in markdown...',
  wrapText = false,
  onWrapTextChange,
  showLineNumbers = false,
  onLineNumbersChange,
  monoFont = false,
  onMonoFontChange,
  noPadding = false,
  copyContent,
  showJinjaTools = false,
  onModalStateChange: _onModalStateChange, // eslint-disable-line @typescript-eslint/no-unused-vars
  onSaveAndClose,
  onDiscard,
  originalContent,
  isDirty = false,
  scrollToLineRef,
  showTocToggle = false,
}: CodeMirrorEditorProps): ReactNode {
  const editorRef = useRef<ReactCodeMirrorRef>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // ToC sidebar state (only subscribed when showTocToggle is true for button active state)
  const tocActive = useRightSidebarStore((state) => state.activePanel === 'toc')
  const togglePanel = useRightSidebarStore((state) => state.togglePanel)

  // Forward-declared ref for openCommandMenu (defined later, used by document-level keydown handler and CM keybinding)
  const openCommandMenuRef = useRef<() => void>(() => {})

  // Reading mode state, remembered per item (see utils/readingModeCache).
  //
  // Seeded at INITIALIZATION only, never as a live effect: a live cache
  // override would flip the mode mid-session on the create→edit transition
  // (which deliberately does not remount this editor — see the contentKey
  // comments in Note/Prompt). Every path that needs the mode re-derived
  // (document switch, server sync, refresh) already remounts via the parent's
  // contentKey, so the initializer re-runs exactly when it should.
  //
  // Reader mode (public share view) is fully isolated from the cache — it
  // seeds from defaultReadingMode (on for notes/bookmarks, omitted for prompts
  // so shared templates open as raw source) and never reads or writes, so a
  // visitor toggling a shared page can't perturb their own account's items.
  // The truthiness check on itemId also covers the public adapters'
  // synthesized empty-string IDs.
  const persistable = !readerMode && !!itemId
  const [readingMode, setReadingMode] = useState(
    () => readerMode ? defaultReadingMode : (!!itemId && readReadingMode(itemId)),
  )

  // Opening a remembered item refreshes its LRU recency (touch is a no-op on
  // miss); without this, an item read daily but toggled once would age out.
  useEffect(() => {
    if (persistable && itemId) touchReadingMode(itemId)
  }, [persistable, itemId])

  // Persist a mode toggled during create once the item first gains an ID: the
  // create→edit transition doesn't remount, so the initializer never re-runs,
  // and the pre-save toggle happened before there was an ID to write under.
  //
  // The `undefined → ID` transition alone does NOT prove a create→edit save —
  // navigating from /new to an EXISTING item renders this same instance once
  // with that item's ID before the parent's sync effect bumps contentKey (child
  // effects run before parent effects), and an unguarded write here would
  // poison the existing item's remembered mode with the draft's toggle state.
  // So the write additionally requires itemIdWasJustCreated — the parent's
  // explicit assertion of create provenance, which this editor must not infer.
  // Parents with no in-place create→edit transition (bookmarks: navigate-away
  // save, ID-keyed remount) never assert it and are excluded structurally.
  const prevItemIdRef = useRef(itemId)
  useEffect(() => {
    const prevId = prevItemIdRef.current
    prevItemIdRef.current = itemId
    if (prevId === undefined && persistable && itemId && itemIdWasJustCreated && readingMode) {
      writeReadingMode(itemId, true)
    }
  }, [itemId, itemIdWasJustCreated, persistable, readingMode])

  // Store scroll position when toggling modes to preserve reading position
  const scrollPositionRef = useRef<number>(0)

  // Toggle reading mode with scroll position preservation.
  // Central disabled guard: the toggle now writes durable per-item state, and
  // effectiveReadingMode would mask the flip visually on a disabled (e.g.
  // deleted-item) view — an invisible mutation of the persisted preference.
  const toggleReadingMode = useCallback((): void => {
    if (disabled) return
    if (!readingMode) {
      // Switching TO reading mode - save scroll position
      const scroller = containerRef.current?.querySelector('.cm-scroller')
      if (scroller) {
        scrollPositionRef.current = scroller.scrollTop
      }
    }
    if (persistable && itemId) {
      writeReadingMode(itemId, !readingMode)
    }
    setReadingMode((prev) => !prev)
  }, [readingMode, persistable, itemId, disabled])

  // Restore scroll position when switching back from reading mode
  useEffect(() => {
    if (!readingMode && scrollPositionRef.current > 0) {
      // Switching FROM reading mode - restore scroll position
      // Use requestAnimationFrame to ensure CodeMirror has rendered
      requestAnimationFrame(() => {
        const scroller = containerRef.current?.querySelector('.cm-scroller')
        if (scroller) {
          scroller.scrollTop = scrollPositionRef.current
        }
      })
    }
  }, [readingMode])

  // Derive effective reading mode - disabled editor can't be in reading mode
  // This prevents user from being stuck in reading mode when disabled
  const effectiveReadingMode = readingMode && !disabled

  // Capture-phase keyboard shortcuts. Uses capture phase to intercept before
  // macOS converts Option+letter to special characters (Ω for Alt+Z, etc.).
  //
  // Listener walks CAPTURE_PHASE_IDS via findMatchingShortcut. The match alone
  // doesn't consume the event — each handler decides whether it acted (didHandle)
  // and only THEN do we preventDefault + stopPropagation. This preserves
  // matcher/handler symmetry: when a runtime precondition fails (reading mode,
  // missing optional callback), the event bubbles unchanged, same as before
  // the registry migration.
  //
  // Handlers read state through a ref so the listener installs once on mount
  // and reads fresh state on each event, avoiding install/teardown churn.
  const buildCaptureState = (): {
    toggleReadingMode: () => void
    effectiveReadingMode: boolean
    wrapText: boolean
    onWrapTextChange: ((wrap: boolean) => void) | undefined
    showLineNumbers: boolean
    onLineNumbersChange: ((show: boolean) => void) | undefined
    monoFont: boolean
    onMonoFontChange: ((mono: boolean) => void) | undefined
    showTocToggle: boolean
    togglePanel: (panel: 'history' | 'toc') => void
    disabled: boolean
    readOnly: boolean
    openCommandMenuRef: typeof openCommandMenuRef
  } => ({
    toggleReadingMode,
    effectiveReadingMode,
    wrapText,
    onWrapTextChange,
    showLineNumbers,
    onLineNumbersChange,
    monoFont,
    onMonoFontChange,
    showTocToggle,
    togglePanel,
    disabled,
    readOnly,
    openCommandMenuRef,
  })
  const captureHandlersRef = useRef(buildCaptureState())
  useEffect(() => {
    captureHandlersRef.current = buildCaptureState()
  })

  useEffect(() => {
    const shortcuts = CAPTURE_PHASE_IDS.map(getShortcut)

    if (import.meta.env.DEV) {
      assertNoDuplicateMatchShapes(shortcuts)
    }

    const handleKeyDown = (e: KeyboardEvent): void => {
      const matched = findMatchingShortcut(e, shortcuts)
      if (!matched) return

      const s = captureHandlersRef.current

      // Exhaustive switch — TS catches a missing case when CAPTURE_PHASE_IDS grows.
      // `matched.id` is structurally one of CAPTURE_PHASE_IDS because
      // findMatchingShortcut iterates `CAPTURE_PHASE_IDS.map(getShortcut)`.
      const id = matched.id as typeof CAPTURE_PHASE_IDS[number]
      let didHandle = false
      switch (id) {
        case 'editor.toggleReadingMode':
          // disabled only — NOT readOnly: toggling on a public-share (readOnly)
          // view is a deliberate visitor feature. Disabled must not consume the
          // event either, since the toggle it maps to is rejected.
          if (!s.disabled) {
            s.toggleReadingMode()
            didHandle = true
          }
          break
        case 'editor.toggleWordWrap':
          if (!s.effectiveReadingMode && s.onWrapTextChange) {
            s.onWrapTextChange(!s.wrapText)
            didHandle = true
          }
          break
        case 'editor.toggleLineNumbers':
          if (!s.effectiveReadingMode && s.onLineNumbersChange) {
            s.onLineNumbersChange(!s.showLineNumbers)
            didHandle = true
          }
          break
        case 'editor.toggleMonoFont':
          if (!s.effectiveReadingMode && s.onMonoFontChange) {
            s.onMonoFontChange(!s.monoFont)
            didHandle = true
          }
          break
        case 'editor.toggleToc':
          // Works in reading mode too — the ToC navigates the rendered view
          // via the reading-mode branch of scrollToLineRef. Rejects disabled
          // (deleted-item views) to match the toolbar button, leaving the
          // event unconsumed per the handler contract above.
          if (s.showTocToggle && !s.disabled) {
            s.togglePanel('toc')
            didHandle = true
          }
          break
        case 'editor.commandMenu':
          // The command menu intentionally stays closed in reading mode: this
          // gate is also the guard keeping the menu's mutating commands (bold,
          // insert link, ...) from dispatching edits into the hidden CodeMirror
          // doc — handleCommandExecute only checks CM's readOnly, which is
          // false in ordinary app-side reading mode. ToC in reading mode is
          // reachable via the toolbar button and shortcut instead.
          if (!s.effectiveReadingMode && !s.disabled && !s.readOnly) {
            s.openCommandMenuRef.current()
            didHandle = true
          }
          break
        default: {
          // Compile-time exhaustiveness check. Adding an id to CAPTURE_PHASE_IDS
          // without a switch case fails to compile here.
          const _exhaustive: never = id
          throw new Error(`Unhandled capture-phase id: ${String(_exhaustive)}`)
        }
      }

      if (didHandle) {
        e.preventDefault()
        e.stopPropagation()
      }
    }

    document.addEventListener('keydown', handleKeyDown, true)
    return () => document.removeEventListener('keydown', handleKeyDown, true)
  }, [])

  // Get the EditorView from ref
  const getView = useCallback((): EditorView | undefined => {
    return editorRef.current?.view
  }, [])

  /**
   * Run an action on the editor view, then refocus.
   * Centralizes the common pattern of: get view -> run action -> focus.
   */
  const runAction = useCallback((action: (view: EditorView) => boolean): void => {
    const view = getView()
    if (view && !view.state.readOnly) {
      action(view)
      view.focus()
    }
  }, [getView])

  // --- Command menu state ---
  const [commandMenuOpen, setCommandMenuOpen] = useState(false)
  const [commandMenuCoords, setCommandMenuCoords] = useState<{ x: number; y: number } | null>(null)
  const [savedSelection, setSavedSelection] = useState<{ from: number; to: number } | null>(null)

  // Build command list — wrap onDiscard to replace editor content via CM dispatch
  // (preserving undo history) before calling the parent's metadata reset callback.
  const handleDiscard = useCallback((): void => {
    const view = getView()
    if (view && originalContent !== undefined) {
      const doc = view.state.doc
      view.dispatch({
        changes: { from: 0, to: doc.length, insert: originalContent },
        selection: { anchor: 0 },
      })
    }
    onDiscard?.()
  }, [getView, originalContent, onDiscard])

  const menuCallbacks: MenuCallbacks = useMemo(() => ({
    onSaveAndClose,
    onDiscard: onDiscard ? handleDiscard : undefined,
    onToggleReadingMode: toggleReadingMode,
  }), [onSaveAndClose, onDiscard, handleDiscard, toggleReadingMode])

  const editorCommands = useMemo(() => buildEditorCommands({
    showJinja: showJinjaTools,
    callbacks: menuCallbacks,
    isDirty,
    showTocToggle,
    icons: {
      bold: () => <BoldIcon />,
      italic: () => <ItalicIcon />,
      strikethrough: () => <StrikethroughIcon />,
      highlight: () => <HighlightIcon />,
      inlineCode: () => <InlineCodeIcon />,
      codeBlock: () => <CodeBlockIcon />,
      link: () => <LinkIcon />,
      bulletList: () => <BulletListIcon />,
      orderedList: () => <OrderedListIcon />,
      checklist: () => <ChecklistIcon />,
      blockquote: () => <BlockquoteIcon />,
      horizontalRule: () => <HorizontalRuleIcon />,
      heading1: () => <HeadingIcon level={1} />,
      heading2: () => <HeadingIcon level={2} />,
      heading3: () => <HeadingIcon level={3} />,
      jinjaVariable: () => <JinjaVariableIcon />,
      jinjaIf: () => <JinjaIfIcon />,
      jinjaIfTrim: () => <JinjaIfTrimIcon />,
      save: () => <SaveIcon />,
      close: () => <CloseIcon className="h-4 w-4" />,
      tableOfContents: () => <TableOfContentsIcon />,
      versionHistory: () => <HistoryIcon className="w-4 h-4" />,
      readingMode: () => <ReadingIcon />,
    },
  }), [showJinjaTools, menuCallbacks, isDirty, showTocToggle])

  // Open command menu: capture cursor position and selection.
  // Focus moves to the menu's filter input via ref callback (synchronous during commit),
  // which inherently blurs CM — no explicit blur() needed.
  const openCommandMenu = useCallback((): void => {
    const view = getView()
    if (view) {
      const sel = view.state.selection.main
      setSavedSelection({ from: sel.from, to: sel.to })
      const coords = view.coordsAtPos(sel.head)
      if (coords) {
        setCommandMenuCoords({ x: coords.left, y: coords.bottom })
      } else {
        setCommandMenuCoords(null)
      }
    } else {
      setSavedSelection(null)
      setCommandMenuCoords(null)
    }
    setCommandMenuOpen(true)
  }, [getView])

  // Close command menu and refocus editor
  const closeCommandMenu = useCallback((): void => {
    setCommandMenuOpen(false)
    const view = getView()
    if (view) {
      view.focus()
    }
  }, [getView])

  // Execute a command from the menu
  const handleCommandExecute = useCallback((command: EditorCommand): void => {
    setCommandMenuOpen(false)
    const view = getView()
    if (view) {
      view.focus()
      if (view.state.readOnly) return
      // Restore saved selection before running the command
      if (savedSelection) {
        view.dispatch({
          selection: { anchor: savedSelection.from, head: savedSelection.to },
        })
      }
      command.action(view)
    }
  }, [getView, savedSelection])

  // Semi-controlled mode: pass value for initial render, ignore prop updates after mount.
  // This works around a Safari bug in @uiw/react-codemirror where content disappears
  // after fast typing then pausing (controlled value sync issue).
  // See: https://github.com/uiwjs/react-codemirror/issues/694
  //
  // How it works:
  // - useState(value) captures the initial value once on mount
  // - User edits flow through onChange, keeping parent state in sync
  // - Subsequent value prop changes are ignored (initialValue never updates)
  //
  // This is safe because:
  // - Document switching and programmatic content changes (e.g., version restore)
  //   increment contentKey in the parent, which changes the key prop and forces
  //   remount with the new value via fresh useState
  const [initialValue] = useState(value)

  // Manage readOnly via our own Compartment so toggling it doesn't trigger
  // @uiw/react-codemirror's full extension reconfigure (which recreates
  // basicSetup including history(), destroying undo history).
  const [readOnlyCompartment] = useState(() => new Compartment())

  useEffect(() => {
    const view = editorRef.current?.view
    if (view) {
      view.dispatch({
        effects: readOnlyCompartment.reconfigure(
          readOnly ? EditorState.readOnly.of(true) : []
        ),
      })
    }
  }, [readOnly, readOnlyCompartment])

  // Keep ref in sync so CM extension and document-level handler use latest callback
  useEffect(() => {
    openCommandMenuRef.current = openCommandMenu
  })

  // Expose scroll-to-line function for external navigation (e.g., ToC sidebar)
  useEffect(() => {
    if (scrollToLineRef) {
      scrollToLineRef.current = (lineNumber: number): void => {
        // Reading mode: the CodeMirror view is inside a hidden wrapper, so
        // scrolling it is a no-op (and focusing it would steal focus into a
        // hidden element). Resolve the heading against the rendered Milkdown
        // DOM instead — see headingNavigation.ts for the parity/verification
        // strategy. scroll-margin-top on the rendered headings (index.css)
        // keeps the target clear of the sticky toolbars/headers.
        if (effectiveReadingMode) {
          const wrapper = containerRef.current?.querySelector('.milkdown-wrapper')
          if (!wrapper) return
          const el = findRenderedHeading(wrapper, value, lineNumber)
          el?.scrollIntoView({ block: 'start' })
          return
        }
        const view = getView()
        if (view) {
          const maxLine = view.state.doc.lines
          if (lineNumber < 1 || lineNumber > maxLine) return
          const line = view.state.doc.line(lineNumber)
          view.dispatch({
            selection: { anchor: line.from },
            effects: EditorView.scrollIntoView(line.from, { y: 'start', yMargin: 50 }),
          })
          view.focus()
        }
      }
    }
    return () => {
      if (scrollToLineRef) {
        scrollToLineRef.current = null
      }
    }
  })

  // Build extensions array with optional line wrapping and keybindings
  const extensions = useMemo(() => {
    const bindings = createMarkdownKeyBindings()
    const slashSource = createSlashCommandSource(showJinjaTools)
    const exts = [
      indentUnit.of('    '),
      EditorState.tabSize.of(4),
      markdown({ codeLanguages: languages }),
      Prec.highest(keymap.of(bindings)),
      markdownStyleExtension,
      createFontTheme(monoFont),
      // readOnly managed via Compartment — see useEffect above
      readOnlyCompartment.of(readOnly ? EditorState.readOnly.of(true) : []),
      autocompletion({
        override: [slashSource],
        icons: false,
        selectOnOpen: true,
        addToOptions: slashCommandAddToOptions,
      }),
      search({ top: true }),
      scrollFadePlugin,
      // Prevent Escape from bubbling to parent handlers (e.g. discard confirmation)
      // when closing the autocomplete dropdown. Prec.highest ensures this runs
      // before CM's keymap handler (Prec.default) which would close the dropdown
      // and break the handler loop before we can call stopPropagation.
      Prec.highest(
        EditorView.domEventHandlers({
          keydown(event, view) {
            if (event.key === 'Escape') {
              // Stop Escape from bubbling to parent handlers (e.g. discard confirmation)
              // when CM has a UI element that consumes it (autocomplete or search panel)
              if (completionStatus(view.state) !== null || view.dom.querySelector('.cm-search')) {
                event.stopPropagation()
              }
            }
            return false // let CM's keymap handle the event normally
          },
        }),
      ),
    ]
    if (wrapText) {
      exts.push(EditorView.lineWrapping)
    }
    return exts
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wrapText, monoFont, showJinjaTools, readOnlyCompartment])

  return (
    <div ref={containerRef} className={`w-full ${noPadding ? 'codemirror-no-padding' : ''}`}>
      {/* Toolbar - formatting buttons fade in on focus, copy button stays visible (doesn't fade) */}
      {/* Always render toolbar to prevent layout shift; buttons are disabled when editor is disabled */}
      {/* min-h and transform-gpu prevent Safari reflow issues during focus/blur transitions */}
      {/* Mobile: flex-wrap, all buttons visible. Desktop: no-wrap, buttons fade in on focus */}
      {/* In reader mode the left formatting group is gone, so right-align the
          remaining toggles on mobile (they're already ml-auto at md+). */}
      <div className={`flex items-center flex-wrap md:flex-nowrap gap-0.5 md:gap-0 md:justify-between px-2 py-1 min-h-[34px] transform-gpu transition-colors ${readerMode ? 'justify-end' : 'border-b border-solid border-transparent group-focus-within/editor:border-gray-200 bg-transparent group-focus-within/editor:bg-gray-50/50'}`}>
        {/* Left: formatting buttons — hidden entirely in reader mode (they mutate content) */}
        {/* On mobile: 'contents' flattens structure so all buttons wrap together as siblings */}
        {!readerMode && (
        <div className={`contents md:flex md:flex-nowrap md:items-center md:gap-0.5 md:opacity-0 md:pointer-events-none md:group-focus-within/editor:opacity-100 md:group-focus-within/editor:pointer-events-auto transition-opacity ${disabled || readOnly ? 'pointer-events-none' : ''}`}>
          {/* Text formatting */}
          <ToolbarButton onClick={() => runAction((v) => toggleWrapMarkers(v, MARKERS.bold.before, MARKERS.bold.after))} title={shortcutTooltipContent('editor.bold')}>
            <BoldIcon />
          </ToolbarButton>
          <ToolbarButton onClick={() => runAction((v) => toggleWrapMarkers(v, MARKERS.italic.before, MARKERS.italic.after))} title={shortcutTooltipContent('editor.italic')}>
            <ItalicIcon />
          </ToolbarButton>
          <ToolbarButton onClick={() => runAction((v) => toggleWrapMarkers(v, MARKERS.strikethrough.before, MARKERS.strikethrough.after))} title={shortcutTooltipContent('editor.strikethrough')}>
            <StrikethroughIcon />
          </ToolbarButton>
          <ToolbarButton onClick={() => runAction((v) => toggleWrapMarkers(v, MARKERS.highlight.before, MARKERS.highlight.after))} title={shortcutTooltipContent('editor.highlight')}>
            <HighlightIcon />
          </ToolbarButton>
          <ToolbarButton onClick={() => runAction((v) => toggleLinePrefix(v, LINE_PREFIXES.blockquote))} title={shortcutTooltipContent('editor.blockquote')}>
            <BlockquoteIcon />
          </ToolbarButton>

          <ToolbarSeparator />

          {/* Code */}
          <ToolbarButton onClick={() => runAction((v) => toggleWrapMarkers(v, MARKERS.inlineCode.before, MARKERS.inlineCode.after))} title={shortcutTooltipContent('editor.inlineCode')}>
            <InlineCodeIcon />
          </ToolbarButton>
          <ToolbarButton onClick={() => runAction(insertCodeBlock)} title={shortcutTooltipContent('editor.codeBlock')}>
            <CodeBlockIcon />
          </ToolbarButton>

          <ToolbarSeparator />

          {/* Lists */}
          <ToolbarButton onClick={() => runAction((v) => toggleLinePrefix(v, LINE_PREFIXES.bulletList))} title={shortcutTooltipContent('editor.bulletList')}>
            <BulletListIcon />
          </ToolbarButton>
          <ToolbarButton onClick={() => runAction((v) => toggleLinePrefix(v, LINE_PREFIXES.numberedList))} title={shortcutTooltipContent('editor.numberedList')}>
            <OrderedListIcon />
          </ToolbarButton>
          <ToolbarButton onClick={() => runAction((v) => toggleLinePrefix(v, LINE_PREFIXES.checklist))} title={shortcutTooltipContent('editor.checklist')}>
            <ChecklistIcon />
          </ToolbarButton>

          <ToolbarSeparator />

          {/* Links and dividers */}
          <ToolbarButton onClick={() => runAction(insertLink)} title={shortcutTooltipContent('editor.insertLink')}>
            <LinkIcon />
          </ToolbarButton>
          <ToolbarButton onClick={() => runAction(insertHorizontalRule)} title={shortcutTooltipContent('editor.horizontalRule')}>
            <HorizontalRuleIcon />
          </ToolbarButton>

          {/* Jinja2 template tools (for prompts) */}
          {showJinjaTools && (
            <>
              <ToolbarSeparator />
              <ToolbarButton onClick={() => runAction((v) => insertText(v, JINJA_VARIABLE))} title="Insert Variable {{ }}">
                <JinjaVariableIcon />
              </ToolbarButton>
              <ToolbarButton onClick={() => runAction((v) => insertText(v, JINJA_IF_BLOCK))} title="If Block {% if %}">
                <JinjaIfIcon />
              </ToolbarButton>
              <ToolbarButton onClick={() => runAction((v) => insertText(v, JINJA_IF_BLOCK_TRIM))} title="If Block with Whitespace Trim {%- if %}">
                <JinjaIfTrimIcon />
              </ToolbarButton>
            </>
          )}
        </div>
        )}

        {/* Right: Toggle icons (Wrap, Lines, Reading) and Copy */}
        {/* On mobile: 'contents' flattens structure so buttons flow with others. On desktop: stays at right */}
        <div className="contents md:flex md:items-center md:gap-0.5 md:ml-auto">
          {/* Separator only on mobile (other separators are hidden on mobile).
              Skip it in reader mode, where the left formatting group it would
              divide from doesn't render — otherwise it's a stray leading divider. */}
          {!readerMode && <div className="w-px h-5 bg-gray-200 mx-1 md:hidden" />}
          {/* Wrap toggle - always visible, only shown when not in reading mode */}
          {onWrapTextChange && !effectiveReadingMode && (
            <Tooltip content={shortcutTooltipContent('editor.toggleWordWrap')} compact>
              <button
                type="button"
                tabIndex={-1}
                disabled={disabled}
                onMouseDown={(e) => {
                  e.preventDefault()
                  if (!disabled) {
                    onWrapTextChange(!wrapText)
                  }
                }}
                className={`p-1.5 rounded transition-colors flex-shrink-0 ${
                  wrapText
                    ? 'text-gray-700 bg-gray-200'
                    : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
                } ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}
              >
                <WrapIcon />
              </button>
            </Tooltip>
          )}

          {/* Line numbers toggle - always visible, only shown when not in reading mode */}
          {onLineNumbersChange && !effectiveReadingMode && (
            <Tooltip content={shortcutTooltipContent('editor.toggleLineNumbers')} compact>
              <button
                type="button"
                tabIndex={-1}
                disabled={disabled}
                onMouseDown={(e) => {
                  e.preventDefault()
                  if (!disabled) {
                    onLineNumbersChange(!showLineNumbers)
                  }
                }}
                className={`p-1.5 rounded transition-colors flex-shrink-0 ${
                  showLineNumbers
                    ? 'text-gray-700 bg-gray-200'
                    : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
                } ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}
              >
                <LineNumbersIcon />
              </button>
            </Tooltip>
          )}

          {/* Mono font toggle - only shown when not in reading mode */}
          {onMonoFontChange && !effectiveReadingMode && (
            <Tooltip content={shortcutTooltipContent('editor.toggleMonoFont')} compact>
              <button
                type="button"
                tabIndex={-1}
                disabled={disabled}
                onMouseDown={(e) => {
                  e.preventDefault()
                  if (!disabled) {
                    onMonoFontChange(!monoFont)
                  }
                }}
                className={`p-1.5 rounded transition-colors flex-shrink-0 ${
                  monoFont
                    ? 'text-gray-700 bg-gray-200'
                    : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
                } ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}
              >
                <MonoFontIcon />
              </button>
            </Tooltip>
          )}

          {/* Table of Contents toggle - shown in both modes (the ToC navigates
              the rendered view in reading mode) */}
          {showTocToggle && (
            <Tooltip content={shortcutTooltipContent('editor.toggleToc')} compact>
              <button
                type="button"
                tabIndex={-1}
                disabled={disabled}
                onMouseDown={(e) => {
                  e.preventDefault()
                  if (!disabled) {
                    togglePanel('toc')
                  }
                }}
                className={`p-1.5 rounded transition-colors flex-shrink-0 ${
                  tocActive
                    ? 'text-gray-700 bg-gray-200'
                    : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
                } ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}
              >
                <TableOfContentsIcon />
              </button>
            </Tooltip>
          )}

          {/* Reading mode toggle - always visible */}
          <Tooltip content={shortcutTooltipContent('editor.toggleReadingMode')} compact>
            <button
              type="button"
              tabIndex={-1}
              disabled={disabled}
              onMouseDown={(e) => {
                if (!disabled) {
                  e.preventDefault()
                  toggleReadingMode()
                }
              }}
              className={`p-1.5 rounded transition-colors flex-shrink-0 ${
                effectiveReadingMode
                  ? 'text-gray-700 bg-gray-200'
                  : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
              } ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}
            >
              <ReadingIcon />
            </button>
          </Tooltip>

          {/* Copy button - always visible but disabled when editor is disabled */}
          {copyContent !== undefined && (
            <CopyToClipboardButton content={copyContent} title="Copy content" disabled={disabled} />
          )}
        </div>
      </div>
      {/* Reading mode: show Milkdown preview */}
      {effectiveReadingMode && (
        <MilkdownEditor
          value={value}
          onChange={() => {}} // Read-only: ignore changes
          disabled={false}
          readOnly={true}
          minHeight={minHeight}
          placeholder={placeholder}
          noPadding={noPadding}
        />
      )}
      {/* CodeMirror: always mounted to preserve state, hidden when in reading mode */}
      {/* This prevents loss of edits when toggling modes (initialValue pattern) */}
      <div className={`overflow-hidden ${effectiveReadingMode ? 'hidden' : ''}`}>
        <CodeMirror
          ref={editorRef}
          value={initialValue}
          onChange={onChange}
          extensions={extensions}
          minHeight={minHeight}
          placeholder={placeholder}
          editable={!disabled}
          basicSetup={{
            lineNumbers: showLineNumbers,
            foldGutter: false,
            highlightActiveLine: false,
            autocompletion: false,
          }}

        />
      </div>

      {/* Editor command menu (Cmd+/) — conditionally rendered so
          React unmounts/remounts it, giving fresh state each time. */}
      {commandMenuOpen && (
        <EditorCommandMenu
          onClose={closeCommandMenu}
          onExecute={handleCommandExecute}
          commands={editorCommands}
          anchorCoords={commandMenuCoords}
        />
      )}
    </div>
  )
}
