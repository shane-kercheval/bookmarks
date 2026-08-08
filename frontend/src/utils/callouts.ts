/**
 * Shared callout (GitHub-style alert) marker grammar — the single source of
 * truth for what counts as a callout and which visual variant it maps to.
 *
 * THREE rendering pipelines consume this module and must not drift on which
 * spellings they accept:
 *   - the CodeMirror editor (utils/markdownStyleExtension.ts) via the
 *     raw-source adapter `matchCalloutMarkerInLine` (its input still carries
 *     the blockquote `>` prefix),
 *   - the reading-mode Milkdown preview (components/MilkdownEditor.tsx) via
 *     `matchCalloutMarker` (post-parse text, `>` already consumed),
 *   - the docs prose pipeline (components/markdown/remarkCallouts.ts), also
 *     post-parse (mdast text values), which maps the five canonical variants
 *     down to its deliberately smaller three-style docs palette.
 *
 * Grammar is forgiving by design — content pasted from GitHub, typed from
 * memory, or written by an agent should all render: the `!` is optional, the
 * keyword is case-insensitive, common aliases are accepted, and an optional
 * custom title may follow on the marker line (Obsidian-style
 * `[!note] My title`). Unknown keywords are NOT callouts (`null`) — every
 * consumer falls through to plain-blockquote rendering, so nothing ever
 * breaks (fail soft).
 */

export type CalloutVariant = 'note' | 'tip' | 'important' | 'warning' | 'caution'

export const CALLOUT_VARIANTS: readonly CalloutVariant[] = [
  'note',
  'tip',
  'important',
  'warning',
  'caution',
]

/** Display labels for callouts without a custom title. */
export const CALLOUT_LABELS: Record<CalloutVariant, string> = {
  note: 'Note',
  tip: 'Tip',
  important: 'Important',
  warning: 'Warning',
  caution: 'Caution',
}

// Aliases collapse onto GitHub's five canonical variants. Keys must be
// lowercase (lookups lowercase the keyword).
const KEYWORD_TO_VARIANT: Record<string, CalloutVariant> = {
  note: 'note',
  info: 'note',
  information: 'note',
  tip: 'tip',
  hint: 'tip',
  success: 'tip',
  check: 'tip',
  done: 'tip',
  important: 'important',
  warning: 'warning',
  attention: 'warning',
  caution: 'caution',
  danger: 'caution',
  error: 'caution',
  bug: 'caution',
  failure: 'caution',
}

/** Resolve a keyword (any case) to its canonical variant, or null if unknown. */
export function resolveCalloutKeyword(keyword: string): CalloutVariant | null {
  return KEYWORD_TO_VARIANT[keyword.toLowerCase()] ?? null
}

export interface CalloutMarker {
  variant: CalloutVariant
  /** Offset of `[` within the input text (0 for the core matcher). */
  markerStart: number
  /** Offset just past `]`. */
  markerEnd: number
  /** Trimmed custom title on the marker line, or null when absent. */
  title: string | null
  /** Offsets of the raw title span (equal to markerEnd when no title). */
  titleStart: number
  titleEnd: number
}

// Marker must start the text: `[!KEYWORD]` or `[KEYWORD]`, letters only, no
// space after the bang (matching GitHub's grammar).
const MARKER_RE = /^\[!?([A-Za-z]+)\]/

/**
 * Match a callout marker at the START of post-parse text (no blockquote `>`).
 * The input may contain the rest of the paragraph (soft-break newlines
 * included) — the custom title is bounded to the marker's own line.
 */
export function matchCalloutMarker(text: string): CalloutMarker | null {
  const match = MARKER_RE.exec(text)
  if (match === null) return null
  const variant = resolveCalloutKeyword(match[1])
  if (variant === null) return null

  const markerEnd = match[0].length
  const newlineIdx = text.indexOf('\n', markerEnd)
  const lineEnd = newlineIdx === -1 ? text.length : newlineIdx
  const rawTitle = text.slice(markerEnd, lineEnd)
  const title = rawTitle.trim()
  if (title === '') {
    return { variant, markerStart: 0, markerEnd, title: null, titleStart: markerEnd, titleEnd: markerEnd }
  }
  const titleStart = markerEnd + (rawTitle.length - rawTitle.trimStart().length)
  return { variant, markerStart: 0, markerEnd, title, titleStart, titleEnd: titleStart + title.length }
}

// Blockquote prefix as the CodeMirror line parser recognizes it: `>` at line
// start (markdownStyleExtension's parseLine does not treat indented `>` as a
// blockquote, so neither does this adapter — keeping the two in agreement).
const BLOCKQUOTE_PREFIX_RE = /^>[ \t]*/

/**
 * Raw-source adapter: match a callout marker on a blockquote SOURCE line
 * (`> [!WARNING] ...`). Returned offsets are in line coordinates, ready for
 * CodeMirror inline decorations.
 */
export function matchCalloutMarkerInLine(lineText: string): CalloutMarker | null {
  const prefix = BLOCKQUOTE_PREFIX_RE.exec(lineText)
  if (prefix === null) return null
  const offset = prefix[0].length
  const marker = matchCalloutMarker(lineText.slice(offset))
  if (marker === null) return null
  return {
    ...marker,
    markerStart: marker.markerStart + offset,
    markerEnd: marker.markerEnd + offset,
    titleStart: marker.titleStart + offset,
    titleEnd: marker.titleEnd + offset,
  }
}
