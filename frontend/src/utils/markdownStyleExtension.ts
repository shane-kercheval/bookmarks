/**
 * CodeMirror 6 extension for visual markdown styling.
 *
 * Adds visual enhancements to markdown editing while preserving exact source:
 * - Larger/styled headers (H1-H6)
 * - Styled lists (bullet, numbered)
 * - Code block backgrounds
 * - Clickable checkboxes
 * - Strikethrough text
 * - Horizontal rules
 * - Styled links (Cmd+click to open)
 * - Styled images (alt text in green, syntax dimmed)
 *
 * This is a "text-first" approach - the source is never modified by the styling,
 * only decorated visually.
 */
import {
  ViewPlugin,
  Decoration,
  EditorView,
} from '@codemirror/view'
import type { DecorationSet, ViewUpdate } from '@codemirror/view'
import { RangeSetBuilder } from '@codemirror/state'
import { matchCalloutMarkerInLine, type CalloutVariant } from './callouts'

// Shared styles for dimmed markdown syntax (brackets, #, >, etc.)
const SYNTAX_COLOR = '#c0c5cc'
const SYNTAX_FONT_SIZE = '0.9em'

/**
 * Parse a line and return decoration info if it matches a markdown pattern.
 */
interface LineInfo {
  type: 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6' | 'bullet' | 'numbered' | 'checklist' | 'blockquote' | 'code-start' | 'code-end' | 'code-content' | 'hr'
  checked?: boolean
  bracketPos?: number   // Position of [ character for editing
  // For list-type lines (bullet/numbered/checklist): number of characters from
  // the start of the line through the marker's trailing space. Used for
  // hanging-indent so wrapped lines align with the content start (KAN-111).
  prefixLen?: number
  // Blockquote lines whose first line is a callout marker (`> [!WARNING]`):
  // the resolved variant plus the marker's span for dim styling. The variant
  // is carried across the quote's continuation lines by buildDecorations.
  callout?: CalloutVariant
  calloutMarker?: { from: number; to: number }
}

function parseLine(text: string, inCodeBlock: boolean): LineInfo | null {
  // Code block detection
  if (text.startsWith('```')) {
    return inCodeBlock ? { type: 'code-end' } : { type: 'code-start' }
  }

  // Inside code block - mark as code content
  if (inCodeBlock) {
    return { type: 'code-content' }
  }

  // Headers
  if (text.startsWith('# ')) return { type: 'h1' }
  if (text.startsWith('## ')) return { type: 'h2' }
  if (text.startsWith('### ')) return { type: 'h3' }
  if (text.startsWith('#### ')) return { type: 'h4' }
  if (text.startsWith('##### ')) return { type: 'h5' }
  if (text.startsWith('###### ')) return { type: 'h6' }

  // Checklist - check for [ ] or [x]
  const checklistMatch = text.match(/^(\s*)([-*+])\s+\[([ xX])\]\s/)
  if (checklistMatch) {
    const checked = checklistMatch[3].toLowerCase() === 'x'
    // bracketPos: position of [ character — computed from the actual match so
    // it stays correct for multi-space variants like "-  [ ]". Used by the
    // click-to-toggle handler to dispatch the 3-char checkbox replacement.
    const bracketPos = checklistMatch[0].indexOf('[')
    return { type: 'checklist', checked, bracketPos, prefixLen: checklistMatch[0].length }
  }

  // Bullet lists
  const bulletMatch = text.match(/^\s*[-*+]\s/)
  if (bulletMatch) return { type: 'bullet', prefixLen: bulletMatch[0].length }

  // Numbered lists
  const numberedMatch = text.match(/^\s*\d+\.\s/)
  if (numberedMatch) return { type: 'numbered', prefixLen: numberedMatch[0].length }

  // Blockquotes — a first-line callout marker upgrades the quote to a callout
  if (text.startsWith('>')) {
    const marker = matchCalloutMarkerInLine(text)
    if (marker) {
      return {
        type: 'blockquote',
        callout: marker.variant,
        calloutMarker: { from: marker.markerStart, to: marker.markerEnd },
      }
    }
    return { type: 'blockquote' }
  }

  // Horizontal rules (---, ***, ___)
  if (/^(-{3,}|\*{3,}|_{3,})\s*$/.test(text)) return { type: 'hr' }

  return null
}

/**
 * Match info for inline code (backticks).
 * Separates marker positions from content for independent styling.
 */
interface InlineCodeMatch {
  from: number           // Start of full match
  to: number             // End of full match
  markerStart: number    // Position of opening backtick
  contentStart: number   // Start of content
  contentEnd: number     // End of content
  markerEnd: number      // Position after closing backtick
}

/**
 * Find all inline code spans in a line (text between single backticks).
 * Returns structured info for separate marker/content styling.
 */
function findInlineCode(text: string): InlineCodeMatch[] {
  const results: InlineCodeMatch[] = []
  let i = 0

  while (i < text.length) {
    // Find opening backtick (but not triple backtick for code blocks)
    if (text[i] === '`' && text[i + 1] !== '`') {
      const start = i
      i++
      // Find closing backtick
      while (i < text.length && text[i] !== '`') {
        i++
      }
      if (i < text.length && text[i] === '`') {
        // Found complete inline code span
        results.push({
          from: start,
          to: i + 1,
          markerStart: start,
          contentStart: start + 1,
          contentEnd: i,
          markerEnd: i + 1,
        })
      }
      i++
    } else {
      i++
    }
  }

  return results
}

/**
 * Match info for inline formatting (bold, italic, strikethrough, highlight).
 * Separates marker positions from content for independent styling.
 */
interface InlineFormatMatch {
  from: number           // Start of full match
  to: number             // End of full match
  markerStart: number    // Start of opening marker
  markerStartEnd: number // End of opening marker
  contentStart: number   // Start of content
  contentEnd: number     // End of content
  markerEndStart: number // Start of closing marker
  markerEnd: number      // End of closing marker
}

/**
 * Match info for Jinja2 template expressions.
 * Separates delimiter positions from content for independent styling.
 */
interface JinjaMatch {
  type: 'variable' | 'tag' | 'comment'
  from: number              // Start of full match
  to: number                // End of full match
  openDelimFrom: number     // Start of opening delimiter
  openDelimTo: number       // End of opening delimiter
  contentStart: number      // Start of inner content
  contentEnd: number        // End of inner content
  closeDelimFrom: number    // Start of closing delimiter
  closeDelimTo: number      // End of closing delimiter
}

/**
 * Find all strikethrough spans in a line (text between ~~).
 * Returns structured info for separate marker/content styling.
 */
function findStrikethrough(text: string): InlineFormatMatch[] {
  const results: InlineFormatMatch[] = []
  const regex = /~~([^~]+)~~/g
  let match

  while ((match = regex.exec(text)) !== null) {
    const start = match.index
    const content = match[1]
    results.push({
      from: start,
      to: start + match[0].length,
      markerStart: start,
      markerStartEnd: start + 2,
      contentStart: start + 2,
      contentEnd: start + 2 + content.length,
      markerEndStart: start + 2 + content.length,
      markerEnd: start + match[0].length,
    })
  }

  return results
}

/**
 * Find all highlight spans in a line (text between ==).
 * Returns structured info for separate marker/content styling.
 */
function findHighlight(text: string): InlineFormatMatch[] {
  const results: InlineFormatMatch[] = []
  const regex = /==([^=]+)==/g
  let match

  while ((match = regex.exec(text)) !== null) {
    const start = match.index
    const content = match[1]
    results.push({
      from: start,
      to: start + match[0].length,
      markerStart: start,
      markerStartEnd: start + 2,
      contentStart: start + 2,
      contentEnd: start + 2 + content.length,
      markerEndStart: start + 2 + content.length,
      markerEnd: start + match[0].length,
    })
  }

  return results
}

/**
 * Find all bold spans in a line (text between **).
 * Returns structured info for separate marker/content styling.
 * Careful to not match *** which could be bold+italic.
 */
function findBold(text: string): InlineFormatMatch[] {
  const results: InlineFormatMatch[] = []
  // Match ** not followed by another * (to avoid ***), content without *, then **
  const regex = /\*\*(?!\*)([^*]+)\*\*(?!\*)/g
  let match

  while ((match = regex.exec(text)) !== null) {
    const start = match.index
    const content = match[1]
    results.push({
      from: start,
      to: start + match[0].length,
      markerStart: start,
      markerStartEnd: start + 2,
      contentStart: start + 2,
      contentEnd: start + 2 + content.length,
      markerEndStart: start + 2 + content.length,
      markerEnd: start + match[0].length,
    })
  }

  return results
}

/**
 * Find all italic spans in a line (text between single *).
 * Must exclude bold (**) spans to avoid conflicts.
 * Returns structured info for separate marker/content styling.
 */
function findItalic(text: string, boldMatches: InlineFormatMatch[]): InlineFormatMatch[] {
  const results: InlineFormatMatch[] = []
  // Match single * not preceded or followed by another *
  const regex = /(?<!\*)\*(?!\*)([^*]+)\*(?!\*)/g
  let match

  while ((match = regex.exec(text)) !== null) {
    const start = match.index
    const content = match[1]
    const end = start + match[0].length

    // Check if this italic span overlaps with any bold span
    const overlapsWithBold = boldMatches.some(
      (bold) => (start >= bold.from && start < bold.to) || (end > bold.from && end <= bold.to)
    )

    if (!overlapsWithBold) {
      results.push({
        from: start,
        to: end,
        markerStart: start,
        markerStartEnd: start + 1,
        contentStart: start + 1,
        contentEnd: start + 1 + content.length,
        markerEndStart: start + 1 + content.length,
        markerEnd: end,
      })
    }
  }

  return results
}

/**
 * Find all markdown images in a line.
 * Returns structured info about each image for styling.
 */
interface ImageMatch {
  from: number
  to: number
  exclamation: number     // !
  openBracket: number     // [
  altStart: number        // start of alt text
  altEnd: number          // end of alt text
  closeBracket: number    // ]
  openParen: number       // (
  urlStart: number        // start of URL
  urlEnd: number          // end of URL
  closeParen: number      // )
}

function findImages(text: string): ImageMatch[] {
  const results: ImageMatch[] = []
  // Match ![alt](url) - the ! prefix distinguishes from links
  const regex = /!\[([^\]]*)\]\(([^)]+)\)/g
  let match

  while ((match = regex.exec(text)) !== null) {
    const fullMatch = match[0]
    const altText = match[1]
    const url = match[2]
    const start = match.index

    results.push({
      from: start,
      to: start + fullMatch.length,
      exclamation: start,
      openBracket: start + 1,
      altStart: start + 2,
      altEnd: start + 2 + altText.length,
      closeBracket: start + 2 + altText.length,
      openParen: start + 2 + altText.length + 1,
      urlStart: start + 2 + altText.length + 2,
      urlEnd: start + 2 + altText.length + 2 + url.length,
      closeParen: start + fullMatch.length - 1,
    })
  }

  return results
}

/**
 * Find all markdown links in a line.
 * Returns structured info about each link for different styling.
 */
interface LinkMatch {
  // Full match positions
  from: number
  to: number
  // Component positions (relative to line start)
  openBracket: number      // [
  textStart: number        // start of link text
  textEnd: number          // end of link text
  closeBracket: number     // ]
  openParen: number        // (
  urlStart: number         // start of URL
  urlEnd: number           // end of URL
  closeParen: number       // )
  // The actual URL for click handling
  url: string
}

function findLinks(text: string): LinkMatch[] {
  const results: LinkMatch[] = []
  // Match [text](url) - non-greedy, handles nested brackets poorly but works for most cases
  const regex = /\[([^\]]+)\]\(([^)]+)\)/g
  let match

  while ((match = regex.exec(text)) !== null) {
    const fullMatch = match[0]
    const linkText = match[1]
    const url = match[2]
    const start = match.index

    results.push({
      from: start,
      to: start + fullMatch.length,
      openBracket: start,
      textStart: start + 1,
      textEnd: start + 1 + linkText.length,
      closeBracket: start + 1 + linkText.length,
      openParen: start + 1 + linkText.length + 1,
      urlStart: start + 1 + linkText.length + 2,
      urlEnd: start + 1 + linkText.length + 2 + url.length,
      closeParen: start + fullMatch.length - 1,
      url,
    })
  }

  return results
}

// Shared decoration for all syntax markers (**, *, ~~, ==, `)
const syntaxMarkerMark = Decoration.mark({ class: 'cm-md-syntax-marker' })

// Decorations for inline code (backticks)
const inlineCodeContentMark = Decoration.mark({ class: 'cm-md-inline-code-content' })

// Decorations for strikethrough
const strikethroughContentMark = Decoration.mark({ class: 'cm-md-strikethrough-content' })

// Decorations for highlight
const highlightContentMark = Decoration.mark({ class: 'cm-md-highlight-content' })

// Decorations for bold
const boldContentMark = Decoration.mark({ class: 'cm-md-bold-content' })

// Decorations for italic
const italicContentMark = Decoration.mark({ class: 'cm-md-italic-content' })

// Decoration for checklist syntax
const checklistSyntaxMark = Decoration.mark({ class: 'cm-md-checklist-syntax' })

// Decorations for clickable checkbox text ([ ] or [x])
const checklistCheckboxUncheckedMark = Decoration.mark({ class: 'cm-md-checklist-checkbox cm-md-checklist-checkbox-unchecked' })
const checklistCheckboxCheckedMark = Decoration.mark({ class: 'cm-md-checklist-checkbox cm-md-checklist-checkbox-checked' })

// Decoration for checked checklist content (strikethrough)
const checklistCheckedContentMark = Decoration.mark({ class: 'cm-md-checklist-checked-content' })

// Decoration for header syntax
const headerSyntaxMark = Decoration.mark({ class: 'cm-md-header-syntax' })

// Decoration for blockquote syntax
const blockquoteSyntaxMark = Decoration.mark({ class: 'cm-md-blockquote-syntax' })

// Decoration for a callout marker (`[!WARNING]`). Styled dim but kept visible
// and editable — this is a live editor, and hiding the marker behind a replace
// decoration would fight the cursor. The rendered views hide it instead.
const calloutMarkerMark = Decoration.mark({ class: 'cm-md-callout-marker' })

/**
 * Find checklist syntax in a line (e.g., "- [ ] " or "- [x] ").
 * Returns the range to gray out, or null if not a checklist line.
 */
function findChecklistSyntax(text: string): { from: number; to: number } | null {
  const match = text.match(/^(\s*)[-*+]\s+\[([ xX])\]\s/)
  if (match) {
    return { from: match[1].length, to: match[0].length }
  }
  return null
}

/**
 * Find header syntax in a line (e.g., "# " or "## ").
 * Returns the range of the # marks and space, or null if not a header.
 */
function findHeaderSyntax(text: string): { from: number; to: number } | null {
  const match = text.match(/^(#{1,6})\s/)
  if (match) {
    return { from: 0, to: match[0].length }
  }
  return null
}

/**
 * Find blockquote syntax in a line (e.g., "> " or ">").
 * Returns the range of the > and optional space, or null if not a blockquote.
 */
function findBlockquoteSyntax(text: string): { from: number; to: number } | null {
  const match = text.match(/^>\s?/)
  if (match) {
    return { from: 0, to: match[0].length }
  }
  return null
}

/**
 * Find all Jinja2 expressions in a line.
 * Detects {{ ... }}, {% ... %} / {%- ... -%}, and {# ... #}.
 * Uses lazy matching to handle multiple expressions on one line.
 */
function findJinjaExpressions(text: string): JinjaMatch[] {
  const results: JinjaMatch[] = []
  // Match all three Jinja syntax types with lazy quantifiers
  // Group 1: variable {{ ... }}
  // Group 2: tag {%- or {% ... -%} or %}
  // Group 3: comment {# ... #}
  const regex = /\{\{(.*?)\}\}|\{%-?\s*(.*?)\s*-?%\}|\{#(.*?)#\}/g
  let match

  while ((match = regex.exec(text)) !== null) {
    const fullStart = match.index
    const fullEnd = fullStart + match[0].length

    if (match[1] !== undefined) {
      // Variable: {{ ... }}
      results.push({
        type: 'variable',
        from: fullStart,
        to: fullEnd,
        openDelimFrom: fullStart,
        openDelimTo: fullStart + 2,       // {{
        contentStart: fullStart + 2,
        contentEnd: fullEnd - 2,
        closeDelimFrom: fullEnd - 2,
        closeDelimTo: fullEnd,            // }}
      })
    } else if (match[2] !== undefined) {
      // Tag: {% ... %} or {%- ... -%}
      const openDelim = match[0].startsWith('{%-') ? '{%-' : '{%'
      const closeDelim = match[0].endsWith('-%}') ? '-%}' : '%}'
      const openLen = openDelim.length
      const closeLen = closeDelim.length
      results.push({
        type: 'tag',
        from: fullStart,
        to: fullEnd,
        openDelimFrom: fullStart,
        openDelimTo: fullStart + openLen,
        contentStart: fullStart + openLen,
        contentEnd: fullEnd - closeLen,
        closeDelimFrom: fullEnd - closeLen,
        closeDelimTo: fullEnd,
      })
    } else if (match[3] !== undefined) {
      // Comment: {# ... #}
      results.push({
        type: 'comment',
        from: fullStart,
        to: fullEnd,
        openDelimFrom: fullStart,
        openDelimTo: fullStart + 2,       // {#
        contentStart: fullStart + 2,
        contentEnd: fullEnd - 2,
        closeDelimFrom: fullEnd - 2,
        closeDelimTo: fullEnd,            // #}
      })
    }
  }

  return results
}

// Decorations for links
const linkBracketMark = Decoration.mark({ class: 'cm-md-link-bracket' })
const linkTextMark = Decoration.mark({ class: 'cm-md-link-text' })
const linkUrlMark = Decoration.mark({ class: 'cm-md-link-url' })

// Decorations for images
const imageSyntaxMark = Decoration.mark({ class: 'cm-md-image-syntax' })
const imageAltMark = Decoration.mark({ class: 'cm-md-image-alt' })
const imageUrlMark = Decoration.mark({ class: 'cm-md-image-url' })

// Decorations for Jinja2 template syntax
const jinjaDelimiterMark = Decoration.mark({ class: 'cm-md-jinja-delimiter' })
const jinjaVariableContentMark = Decoration.mark({ class: 'cm-md-jinja-variable-content' })
const jinjaTagContentMark = Decoration.mark({ class: 'cm-md-jinja-tag-content' })
const jinjaCommentMark = Decoration.mark({ class: 'cm-md-jinja-comment' })

/**
 * Build a cache key capturing the dimensions that actually affect a prefix's
 * rendered width: type, indent width, and marker shape (marker char for
 * bullets, digit count for numbered, checked state for checklists).
 *
 * Intentional trade-off: two structurally distinct prefixes of equal length
 * can collide in theory (and their widths may differ sub-pixel in
 * proportional fonts), but within a single list all items share the same
 * structure, so this keeps the cache O(distinct list structures) instead of
 * O(distinct prefix texts) — important for, e.g., a 500-item numbered list
 * where keying on literal prefix would cause 500 forced layouts on first
 * render.
 */
function prefixCacheKey(info: LineInfo, prefix: string): string {
  if (info.type === 'checklist' && info.bracketPos !== undefined) {
    const indent = info.bracketPos - 2 // "- " between indent and "[" is 2 chars
    return `c|${indent}|${info.checked ? 1 : 0}`
  }
  if (info.type === 'numbered') {
    const m = prefix.match(/^(\s*)(\d+)/)
    if (m) return `n|${m[1].length}|${m[2].length}`
  }
  if (info.type === 'bullet') {
    const m = prefix.match(/^(\s*)([-*+])/)
    if (m) return `b|${m[1].length}|${m[2]}`
  }
  return `${info.type}|${prefix}` // fallback
}

/**
 * Measure the pixel width of a list line's prefix as it renders in the editor.
 * Uses a hidden probe appended to a measurement host that sits as a child of
 * view.dom — NOT view.contentDOM — so it doesn't trigger CM6's
 * MutationObserver on the contenteditable region (which could misinterpret
 * the mutation as user input).
 *
 * For checklists, the probe mirrors the inline decoration structure
 * (`cm-md-checklist-syntax` on "- ", `cm-md-checklist-checkbox` on
 * "[ ]"/"[x]"), which differ from plain text in font-family, font-size,
 * font-weight, and padding — without this, wrapped checklist lines would be
 * under-indented by several pixels.
 *
 * Results are cached per prefixCacheKey; the cache is cleared by the plugin
 * on geometry changes (e.g., font swaps). Failed measurements (width === 0,
 * e.g., jsdom or a detached host) are deliberately NOT cached so a later
 * successful measurement can populate the cache.
 */
function measurePrefixWidth(
  host: HTMLElement,
  info: LineInfo,
  prefix: string,
  cache: Map<string, number>,
): number {
  const key = prefixCacheKey(info, prefix)
  const cached = cache.get(key)
  if (cached !== undefined) return cached

  const probe = document.createElement('span')
  probe.style.cssText = 'white-space:pre;'

  if (info.type === 'checklist' && info.bracketPos !== undefined) {
    // Mirror the inline decorations applied to the real prefix:
    //   [plain leading indent][syntax span: "- "][checkbox span: "[ ]"][plain trailing space]
    const syntaxFrom = info.bracketPos - 2 // where "- " starts = indent length
    const bracketEnd = info.bracketPos + 3 // after "[ ]" or "[x]"

    if (syntaxFrom > 0) {
      probe.appendChild(document.createTextNode(prefix.slice(0, syntaxFrom)))
    }
    const syntax = document.createElement('span')
    syntax.className = 'cm-md-checklist-syntax'
    syntax.textContent = prefix.slice(syntaxFrom, info.bracketPos)
    probe.appendChild(syntax)

    const checkbox = document.createElement('span')
    checkbox.className = info.checked
      ? 'cm-md-checklist-checkbox cm-md-checklist-checkbox-checked'
      : 'cm-md-checklist-checkbox cm-md-checklist-checkbox-unchecked'
    checkbox.textContent = prefix.slice(info.bracketPos, bracketEnd)
    probe.appendChild(checkbox)

    if (bracketEnd < prefix.length) {
      probe.appendChild(document.createTextNode(prefix.slice(bracketEnd)))
    }
  } else {
    probe.textContent = prefix
  }

  host.appendChild(probe)
  const width = probe.getBoundingClientRect().width
  host.removeChild(probe)

  if (width > 0) cache.set(key, width)
  return width
}

/**
 * Build decorations for the entire document.
 */
function buildDecorations(
  view: EditorView,
  prefixWidthCache: Map<string, number>,
  measurementHost: HTMLElement,
): DecorationSet {
  const builder = new RangeSetBuilder<Decoration>()
  let inCodeBlock = false
  // Callout state, threaded line-by-line like inCodeBlock: an OPENING marker
  // line starts a callout whose variant applies to the quote's continuation
  // lines until the blockquote ends (any non-blockquote line, including blank).
  let currentCallout: CalloutVariant | null = null
  let prevLineWasBlockquote = false

  for (let i = 1; i <= view.state.doc.lines; i++) {
    const line = view.state.doc.line(i)
    const info = parseLine(line.text, inCodeBlock)

    // Track code block state
    if (info?.type === 'code-start') {
      inCodeBlock = true
    } else if (info?.type === 'code-end') {
      inCodeBlock = false
    }

    // A marker is honored only on a line that OPENS a quote in the line model
    // (the previous line wasn't a `>` line) — matching the rendered pipelines,
    // which read only a blockquote's opening. A marker-shaped line deeper
    // inside an open quote is plain body text there, so here it must neither
    // (re)set the variant nor receive marker styling. Note "opens" is
    // line-model scoped (contiguous explicitly-quoted lines), not AST-level —
    // see the callout parity comment at the theme section.
    const opensLineBlockquote = info?.type === 'blockquote' && !prevLineWasBlockquote
    if (info?.type === 'blockquote') {
      if (opensLineBlockquote && info.callout !== undefined) {
        currentCallout = info.callout
      }
    } else {
      currentCallout = null
    }
    prevLineWasBlockquote = info?.type === 'blockquote'

    // Add line decoration if we have line-level styling
    if (info) {
      let lineClass = `cm-md-${info.type}`
      // Add checked class for completed checklist items
      if (info.type === 'checklist' && info.checked) {
        lineClass += ' cm-md-checklist-checked'
      }
      if (info.type === 'blockquote' && currentCallout !== null) {
        lineClass += ` cm-md-callout-${currentCallout}`
      }
      const spec: Parameters<typeof Decoration.line>[0] = { class: lineClass }
      if (info.prefixLen !== undefined) {
        // Per-line hanging-indent width (KAN-111) so wrapped list lines align
        // with the content after the marker. See measurePrefixWidth.
        const prefix = line.text.slice(0, info.prefixLen)
        const width = measurePrefixWidth(measurementHost, info, prefix, prefixWidthCache)
        if (width > 0) {
          spec.attributes = { style: `--md-list-indent: ${width}px` }
        }
      }
      builder.add(line.from, line.from, Decoration.line(spec))
    }

    // Add inline decorations (only outside of code blocks)
    if (!inCodeBlock) {
      // Collect all inline decorations with their positions
      const inlineDecorations: Array<{ from: number; to: number; decoration: Decoration }> = []

      // Checklist syntax and clickable checkbox
      const checklistSyntax = findChecklistSyntax(line.text)
      if (checklistSyntax && info?.type === 'checklist' && info.bracketPos !== undefined) {
        const bracketPos = line.from + info.bracketPos   // Where [ is in the document

        // Style "- " before the checkbox as dimmed syntax
        if (info.bracketPos > checklistSyntax.from) {
          inlineDecorations.push({
            from: line.from + checklistSyntax.from,
            to: bracketPos,
            decoration: checklistSyntaxMark,
          })
        }

        // Mark [x] or [ ] as clickable (text stays visible, no widget replacement)
        inlineDecorations.push({
          from: bracketPos,
          to: bracketPos + 3,
          decoration: info.checked ? checklistCheckboxCheckedMark : checklistCheckboxUncheckedMark,
        })
        // Apply strikethrough to content after checkbox when checked
        if (info?.type === 'checklist' && info.checked && checklistSyntax.to < line.text.length) {
          inlineDecorations.push({
            from: line.from + checklistSyntax.to,
            to: line.to,
            decoration: checklistCheckedContentMark,
          })
        }
      }

      // Header syntax (# or ## etc)
      const headerSyntax = findHeaderSyntax(line.text)
      if (headerSyntax) {
        inlineDecorations.push({ from: line.from + headerSyntax.from, to: line.from + headerSyntax.to, decoration: headerSyntaxMark })
      }

      // Blockquote syntax (> )
      const blockquoteSyntax = findBlockquoteSyntax(line.text)
      if (blockquoteSyntax) {
        inlineDecorations.push({ from: line.from + blockquoteSyntax.from, to: line.from + blockquoteSyntax.to, decoration: blockquoteSyntaxMark })
      }

      // Callout marker (`[!WARNING]`) — dim, visible, editable. Only on the
      // quote-opening line; a marker-shaped continuation line is body text.
      if (opensLineBlockquote && info?.calloutMarker !== undefined) {
        inlineDecorations.push({
          from: line.from + info.calloutMarker.from,
          to: line.from + info.calloutMarker.to,
          decoration: calloutMarkerMark,
        })
      }

      // Bold - must be processed before italic to handle ** vs *
      const bolds = findBold(line.text)
      for (const bold of bolds) {
        // Opening **
        inlineDecorations.push({ from: line.from + bold.markerStart, to: line.from + bold.markerStartEnd, decoration: syntaxMarkerMark })
        // Bold content
        if (bold.contentEnd > bold.contentStart) {
          inlineDecorations.push({ from: line.from + bold.contentStart, to: line.from + bold.contentEnd, decoration: boldContentMark })
        }
        // Closing **
        inlineDecorations.push({ from: line.from + bold.markerEndStart, to: line.from + bold.markerEnd, decoration: syntaxMarkerMark })
      }

      // Italic - exclude spans that overlap with bold
      const italics = findItalic(line.text, bolds)
      for (const italic of italics) {
        // Opening *
        inlineDecorations.push({ from: line.from + italic.markerStart, to: line.from + italic.markerStartEnd, decoration: syntaxMarkerMark })
        // Italic content
        if (italic.contentEnd > italic.contentStart) {
          inlineDecorations.push({ from: line.from + italic.contentStart, to: line.from + italic.contentEnd, decoration: italicContentMark })
        }
        // Closing *
        inlineDecorations.push({ from: line.from + italic.markerEndStart, to: line.from + italic.markerEnd, decoration: syntaxMarkerMark })
      }

      // Inline code
      const inlineCodes = findInlineCode(line.text)
      for (const code of inlineCodes) {
        // Opening backtick
        inlineDecorations.push({ from: line.from + code.markerStart, to: line.from + code.contentStart, decoration: syntaxMarkerMark })
        // Code content
        if (code.contentEnd > code.contentStart) {
          inlineDecorations.push({ from: line.from + code.contentStart, to: line.from + code.contentEnd, decoration: inlineCodeContentMark })
        }
        // Closing backtick
        inlineDecorations.push({ from: line.from + code.contentEnd, to: line.from + code.markerEnd, decoration: syntaxMarkerMark })
      }

      // Strikethrough
      const strikethroughs = findStrikethrough(line.text)
      for (const strike of strikethroughs) {
        // Opening ~~
        inlineDecorations.push({ from: line.from + strike.markerStart, to: line.from + strike.markerStartEnd, decoration: syntaxMarkerMark })
        // Strikethrough content
        if (strike.contentEnd > strike.contentStart) {
          inlineDecorations.push({ from: line.from + strike.contentStart, to: line.from + strike.contentEnd, decoration: strikethroughContentMark })
        }
        // Closing ~~
        inlineDecorations.push({ from: line.from + strike.markerEndStart, to: line.from + strike.markerEnd, decoration: syntaxMarkerMark })
      }

      // Highlight
      const highlights = findHighlight(line.text)
      for (const highlight of highlights) {
        // Opening ==
        inlineDecorations.push({ from: line.from + highlight.markerStart, to: line.from + highlight.markerStartEnd, decoration: syntaxMarkerMark })
        // Highlight content
        if (highlight.contentEnd > highlight.contentStart) {
          inlineDecorations.push({ from: line.from + highlight.contentStart, to: line.from + highlight.contentEnd, decoration: highlightContentMark })
        }
        // Closing ==
        inlineDecorations.push({ from: line.from + highlight.markerEndStart, to: line.from + highlight.markerEnd, decoration: syntaxMarkerMark })
      }

      // Images - style syntax similar to links but with different color for alt text
      const images = findImages(line.text)
      for (const image of images) {
        // ! and opening bracket ![
        inlineDecorations.push({ from: line.from + image.exclamation, to: line.from + image.openBracket + 1, decoration: imageSyntaxMark })
        // Alt text
        if (image.altEnd > image.altStart) {
          inlineDecorations.push({ from: line.from + image.altStart, to: line.from + image.altEnd, decoration: imageAltMark })
        }
        // Closing bracket ]
        inlineDecorations.push({ from: line.from + image.closeBracket, to: line.from + image.closeBracket + 1, decoration: imageSyntaxMark })
        // Opening paren and URL (url)
        inlineDecorations.push({ from: line.from + image.openParen, to: line.from + image.closeParen + 1, decoration: imageUrlMark })
      }

      // Links - multiple decorations per link (exclude images which start with !)
      const links = findLinks(line.text).filter(link => {
        // Check if this link is actually part of an image (preceded by !)
        return link.openBracket === 0 || line.text[link.openBracket - 1] !== '!'
      })
      for (const link of links) {
        // Opening bracket [
        inlineDecorations.push({ from: line.from + link.openBracket, to: line.from + link.openBracket + 1, decoration: linkBracketMark })
        // Link text
        inlineDecorations.push({ from: line.from + link.textStart, to: line.from + link.textEnd, decoration: linkTextMark })
        // Closing bracket ]
        inlineDecorations.push({ from: line.from + link.closeBracket, to: line.from + link.closeBracket + 1, decoration: linkBracketMark })
        // Opening paren and URL (
        inlineDecorations.push({ from: line.from + link.openParen, to: line.from + link.closeParen + 1, decoration: linkUrlMark })
      }

      // Jinja2 template syntax ({{ }}, {% %}, {# #})
      const jinjaMatches = findJinjaExpressions(line.text)
      for (const jinja of jinjaMatches) {
        // Skip if overlapping with inline code (inline code wins)
        const overlapsCode = inlineCodes.some(
          (code) => jinja.from < code.to && jinja.to > code.from
        )
        if (overlapsCode) continue

        if (jinja.type === 'comment') {
          // Comments: single decoration spanning entire match
          inlineDecorations.push({ from: line.from + jinja.from, to: line.from + jinja.to, decoration: jinjaCommentMark })
        } else {
          // Variables and tags: three decorations (open delimiter, content, close delimiter)
          const contentMark = jinja.type === 'variable' ? jinjaVariableContentMark : jinjaTagContentMark
          // Opening delimiter
          inlineDecorations.push({ from: line.from + jinja.openDelimFrom, to: line.from + jinja.openDelimTo, decoration: jinjaDelimiterMark })
          // Content
          if (jinja.contentEnd > jinja.contentStart) {
            inlineDecorations.push({ from: line.from + jinja.contentStart, to: line.from + jinja.contentEnd, decoration: contentMark })
          }
          // Closing delimiter
          inlineDecorations.push({ from: line.from + jinja.closeDelimFrom, to: line.from + jinja.closeDelimTo, decoration: jinjaDelimiterMark })
        }
      }

      // Sort by position and add to builder (RangeSetBuilder requires sorted order)
      inlineDecorations.sort((a, b) => a.from - b.from || a.to - b.to)
      for (const { from, to, decoration } of inlineDecorations) {
        builder.add(from, to, decoration)
      }
    }
  }

  return builder.finish()
}

/**
 * Check if a position is inside a code block (or on a code fence line).
 */
function isPositionInCodeBlock(view: EditorView, pos: number): boolean {
  const line = view.state.doc.lineAt(pos)

  // If current line is a code fence, it has dark background - return true
  if (line.text.startsWith('```')) {
    return true
  }

  let inCodeBlock = false

  // Scan from start of document to current line
  for (let i = 1; i <= line.number; i++) {
    const l = view.state.doc.line(i)
    if (l.text.startsWith('```')) {
      inCodeBlock = !inCodeBlock
    }
  }

  return inCodeBlock
}

/**
 * ViewPlugin that adds a class to editor when cursor is in a code block.
 * This allows styling the cursor color based on context.
 */
const cursorInCodeBlockPlugin = ViewPlugin.fromClass(
  class {
    constructor(view: EditorView) {
      this.updateClass(view)
    }

    update(update: ViewUpdate): void {
      // Always update - catches typing, selection, and any other changes
      this.updateClass(update.view)
    }

    updateClass(view: EditorView): void {
      const pos = view.state.selection.main.head
      const inCode = isPositionInCodeBlock(view, pos)

      if (inCode) {
        view.dom.classList.add('cm-cursor-in-code')
      } else {
        view.dom.classList.remove('cm-cursor-in-code')
      }
    }

    destroy(): void {
      // Class will be removed when element is destroyed
    }
  }
)

/**
 * ViewPlugin that maintains markdown decorations.
 */
const markdownDecorationPlugin = ViewPlugin.fromClass(
  class {
    decorations: DecorationSet
    // Cache of measured prefix widths (see measurePrefixWidth). Cleared when
    // geometry changes so font swaps (mono ↔ proportional) remeasure.
    prefixWidthCache = new Map<string, number>()
    // Off-screen host for prefix measurement probes. Lives under view.dom
    // (not view.contentDOM) to avoid triggering CM6's MutationObserver on the
    // contenteditable region.
    measurementHost: HTMLElement

    constructor(view: EditorView) {
      this.measurementHost = document.createElement('div')
      this.measurementHost.className = 'cm-md-measure'
      this.measurementHost.style.cssText =
        'position:absolute;visibility:hidden;pointer-events:none;top:0;left:-9999px;white-space:pre;'
      view.dom.appendChild(this.measurementHost)
      this.decorations = buildDecorations(view, this.prefixWidthCache, this.measurementHost)
    }

    update(update: ViewUpdate): void {
      if (update.geometryChanged) {
        this.prefixWidthCache.clear()
      }
      if (update.docChanged || update.viewportChanged || update.geometryChanged) {
        this.decorations = buildDecorations(update.view, this.prefixWidthCache, this.measurementHost)
      }
    }

    destroy(): void {
      this.measurementHost.remove()
    }
  },
  {
    decorations: (v) => v.decorations,
  }
)

/**
 * Base theme for markdown styling.
 * Uses CSS variables for customization.
 */
const markdownBaseTheme = EditorView.theme({
  // Font-family and font-size are set dynamically via createFontTheme()
  '.cm-line': {
    lineHeight: '1.5 !important',
  },

  // Pointer cursor shown when Cmd/Ctrl is held over a link. The class is
  // toggled on view.dom by handleEditorMousemove / handleEditorMouseleave.
  '&.cm-md-link-hover .cm-content': {
    cursor: 'pointer',
  },

  // Remove underlines from default markdown heading syntax highlighting
  // Try multiple selectors to catch whatever CodeMirror is using
  '.cmt-heading, .cmt-heading1, .cmt-heading2, .cmt-heading3, .cmt-heading4, .cmt-heading5, .cmt-heading6': {
    textDecoration: 'none !important',
  },
  '.cm-header, .cm-header-1, .cm-header-2, .cm-header-3, .cm-header-4, .cm-header-5, .cm-header-6': {
    textDecoration: 'none !important',
  },
  '.tok-heading, .tok-heading1, .tok-heading2, .tok-heading3, .tok-heading4, .tok-heading5, .tok-heading6': {
    textDecoration: 'none !important',
  },
  // Nuclear option - remove underlines from header lines entirely
  '.cm-md-h1 *, .cm-md-h2 *, .cm-md-h3 *, .cm-md-h4 *, .cm-md-h5 *, .cm-md-h6 *': {
    textDecoration: 'none !important',
  },
  '.cm-md-h1, .cm-md-h2, .cm-md-h3, .cm-md-h4, .cm-md-h5, .cm-md-h6': {
    textDecoration: 'none !important',
  },

  // Headers - progressively smaller sizes
  '.cm-md-h1': {
    fontSize: '1.75em',
    fontWeight: '700',
    lineHeight: '1.3',
    color: '#111827',
    textDecoration: 'none',
  },
  '.cm-md-h2': {
    fontSize: '1.5em',
    fontWeight: '600',
    lineHeight: '1.35',
    color: '#1f2937',
    textDecoration: 'none',
  },
  '.cm-md-h3': {
    fontSize: '1.25em',
    fontWeight: '600',
    lineHeight: '1.4',
    color: '#374151',
    textDecoration: 'none',
  },
  '.cm-md-h4': {
    fontSize: '1.125em',
    fontWeight: '600',
    lineHeight: '1.45',
    color: '#374151',
    textDecoration: 'none',
  },
  '.cm-md-h5': {
    fontSize: '1em',
    fontWeight: '600',
    lineHeight: '1.5',
    color: '#4b5563',
    textDecoration: 'none',
  },
  '.cm-md-h6': {
    fontSize: '0.925em',
    fontWeight: '600',
    lineHeight: '1.5',
    color: '#6b7280',
    textDecoration: 'none',
  },

  // Lists — hanging indent so wrapped lines align with content after the
  // marker (KAN-111). The --md-list-indent custom property is set per line in
  // buildDecorations from a pixel measurement of the actual prefix text.
  // text-indent pulls the first visual line back to column 0 while
  // padding-left applies to wrapped lines.
  '.cm-md-bullet, .cm-md-numbered, .cm-md-checklist': {
    paddingLeft: 'calc(0.5em + var(--md-list-indent, 0px))',
    textIndent: 'calc(-1 * var(--md-list-indent, 0px))',
  },

  // Checklist items
  '.cm-md-checklist': {
    position: 'relative',
  },

  // Completed checklist items - dimmed color (strikethrough applied to content only)
  '.cm-md-checklist-checked': {
    color: '#6b7280',
  },

  // Completed checklist content - strikethrough only on text, not full line
  '.cm-md-checklist-checked-content': {
    textDecoration: 'line-through',
    textDecorationColor: '#6b7280',
  },

  // Blockquotes
  '.cm-md-blockquote': {
    borderLeft: '3px solid #6366f1',
    paddingLeft: '1em',
  },

  // Callouts (`> [!WARNING]` etc.) — variant-tinted left rule + background.
  // Compound selectors so they override the base blockquote border. The marker
  // text stays visible/editable in the editor (dim, below); the rendered views
  // do the icon-and-title treatment.
  //
  // Parity boundary: callout detection follows this extension's LINE-BASED
  // blockquote model (unindented `>`, backtick fences only, no lazy
  // continuation) — deliberately no more structurally accurate than the quote
  // styling it extends. The rendered pipelines (real markdown ASTs) are ground
  // truth; residual differences are recorded in the editor-improvements plan.
  '.cm-md-blockquote.cm-md-callout-note': { borderLeftColor: '#3b82f6', backgroundColor: '#eff6ff' },
  '.cm-md-blockquote.cm-md-callout-tip': { borderLeftColor: '#22c55e', backgroundColor: '#f0fdf4' },
  '.cm-md-blockquote.cm-md-callout-important': { borderLeftColor: '#a855f7', backgroundColor: '#faf5ff' },
  '.cm-md-blockquote.cm-md-callout-warning': { borderLeftColor: '#f59e0b', backgroundColor: '#fffbeb' },
  '.cm-md-blockquote.cm-md-callout-caution': { borderLeftColor: '#ef4444', backgroundColor: '#fef2f2' },
  '.cm-md-callout-marker, .cm-md-callout-marker *': {
    color: `${SYNTAX_COLOR} !important`,
    fontSize: SYNTAX_FONT_SIZE,
  },

  // Code blocks - light gray background, monospace font
  // Use mix-blend-mode so text selection shows through the background
  '.cm-md-code-start, .cm-md-code-end, .cm-md-code-content': {
    backgroundColor: '#f5f7f8',
    mixBlendMode: 'multiply',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace !important',
    fontSize: '13px !important',
    marginRight: '4px',
  },
  // Code fence lines (``` and ```language) - dimmer gray
  '.cm-md-code-start, .cm-md-code-start *, .cm-md-code-end, .cm-md-code-end *': {
    color: '#6b7280 !important',
  },
  '.cm-md-code-start': {
    borderTopLeftRadius: '6px',
    borderTopRightRadius: '6px',
    paddingTop: '0.5em',
  },
  '.cm-md-code-end': {
    borderBottomLeftRadius: '6px',
    borderBottomRightRadius: '6px',
    paddingBottom: '0.0em',
  },
  // Custom cursor - thicker and red like Bear notes
  '.cm-cursor, .cm-cursor-primary': {
    borderLeftColor: '#f87171 !important',
    borderLeftWidth: '2px !important',
    transform: 'scaleY(1.2)',
    transformOrigin: 'center',
  },

  // Shared syntax marker style for all inline formatting (**, *, ~~, ==, `)
  // Using a slightly lighter gray for better readability
  '.cm-md-syntax-marker, .cm-md-syntax-marker *': {
    color: `${SYNTAX_COLOR} !important`,
    fontWeight: 'normal !important',
    fontStyle: 'normal !important',
    textDecoration: 'none !important',
    fontSize: SYNTAX_FONT_SIZE,
  },

  // Inline code content - light blue background with blue text
  // Use mix-blend-mode so text selection shows through the background
  '.cm-md-inline-code-content': {
    backgroundColor: '#eff6ff',
    mixBlendMode: 'multiply',
    color: '#2563eb',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace !important',
    fontSize: '13px !important',
    padding: '0.1em 0.2em',
    borderRadius: '3px',
  },

  // Bold content
  '.cm-md-bold-content, .cm-md-bold-content *': {
    fontWeight: '700 !important',
  },

  // Italic content
  '.cm-md-italic-content, .cm-md-italic-content *': {
    fontStyle: 'italic !important',
  },

  // Highlight content - yellow/amber background
  // Use mix-blend-mode so text selection shows through the background
  '.cm-md-highlight-content': {
    backgroundColor: '#fef3c7',
    mixBlendMode: 'multiply',
    color: '#92400e',
    padding: '0.1em 0.2em',
    borderRadius: '3px',
  },

  // Clickable checkbox text ([ ] or [x]) - click to toggle
  '.cm-md-checklist-checkbox': {
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    cursor: 'pointer',
    borderRadius: '3px',
    padding: '1px 2px',
    transition: 'background-color 0.15s',
  },
  '.cm-md-checklist-checkbox:hover': {
    backgroundColor: 'rgba(0, 0, 0, 0.08)',
  },
  '.cm-md-checklist-checkbox-unchecked': {
    color: '#374151',
    fontWeight: 'bold',
  },
  '.cm-md-checklist-checkbox-checked': {
    color: '#6b7280',
    fontWeight: 'bold',
    textDecoration: 'none !important',
  },
  '.cm-md-checklist-checkbox-checked *': {
    textDecoration: 'none !important',
  },

  // Checklist syntax (- [ ] or - [x]) - dimmed gray like other markdown syntax
  '.cm-md-checklist-syntax': {
    color: `${SYNTAX_COLOR} !important`,
    textDecoration: 'none !important',
    fontSize: SYNTAX_FONT_SIZE,
  },
  '.cm-md-checklist-syntax *': {
    color: `${SYNTAX_COLOR} !important`,
    textDecoration: 'none !important',
  },

  // Header syntax (# marks) - dimmed gray (using shared lighter gray)
  '.cm-md-header-syntax': {
    color: `${SYNTAX_COLOR} !important`,
    fontWeight: 'normal !important',
    fontSize: `${SYNTAX_FONT_SIZE} !important`,
  },
  '.cm-md-header-syntax *': {
    color: `${SYNTAX_COLOR} !important`,
    fontWeight: 'normal !important',
    fontSize: 'inherit !important',
  },

  // Blockquote syntax (> ) - light gray, subtle
  '.cm-md-blockquote-syntax, .cm-md-blockquote-syntax *': {
    color: `${SYNTAX_COLOR} !important`,
    fontStyle: 'normal !important',
    fontSize: SYNTAX_FONT_SIZE,
  },

  // Strikethrough content
  '.cm-md-strikethrough-content, .cm-md-strikethrough-content *': {
    textDecoration: 'line-through !important',
    color: '#9ca3af !important',
  },

  // Horizontal rule - full width line with --- text visible
  '.cm-md-hr': {
    background: 'linear-gradient(transparent 42.5%, #d1d5db 42.5%, #d1d5db 57.5%, transparent 57.5%)',
    color: '#374151',
    marginLeft: '0.5em',
    marginRight: '0.5em',
  },

  // Links - text looks like a link, brackets/URL are dimmed gray (using shared lighter gray)
  '.cm-md-link-bracket': {
    color: `${SYNTAX_COLOR} !important`,
    textDecoration: 'none !important',
    fontSize: SYNTAX_FONT_SIZE,
  },
  '.cm-md-link-text': {
    color: '#2563eb !important',
    textDecoration: 'underline !important',
    textDecorationColor: '#93c5fd',
  },
  '.cm-md-link-url': {
    color: `${SYNTAX_COLOR} !important`,
    textDecoration: 'none !important',
    fontSize: SYNTAX_FONT_SIZE,
  },
  // Override any nested syntax highlighting in links
  '.cm-md-link-bracket *, .cm-md-link-url *': {
    color: `${SYNTAX_COLOR} !important`,
    textDecoration: 'none !important',
  },

  // Images - similar to links but with green alt text to distinguish
  '.cm-md-image-syntax': {
    color: `${SYNTAX_COLOR} !important`,
    textDecoration: 'none !important',
    fontSize: SYNTAX_FONT_SIZE,
  },
  '.cm-md-image-alt': {
    color: '#059669 !important',
    textDecoration: 'none !important',
  },
  '.cm-md-image-url': {
    color: `${SYNTAX_COLOR} !important`,
    textDecoration: 'none !important',
    fontSize: SYNTAX_FONT_SIZE,
  },
  // Override any nested syntax highlighting in images
  '.cm-md-image-syntax *, .cm-md-image-url *': {
    color: `${SYNTAX_COLOR} !important`,
    textDecoration: 'none !important',
  },

  // Jinja2 template syntax - delimiters ({{ }}, {% %}, {# #})
  '.cm-md-jinja-delimiter': {
    color: '#d1955a !important',
  },

  // Jinja2 variable content (between {{ }})
  '.cm-md-jinja-variable-content': {
    backgroundColor: 'rgba(226, 166, 107, 0.1)',
    mixBlendMode: 'multiply',
    color: '#b37a3a !important',
    padding: '0.1em 0.1em',
    borderRadius: '2px',
  },

  // Jinja2 tag content (between {% %})
  '.cm-md-jinja-tag-content': {
    backgroundColor: 'rgba(226, 166, 107, 0.08)',
    mixBlendMode: 'multiply',
    color: '#c4843e !important',
    fontStyle: 'italic',
    padding: '0.1em 0.1em',
    borderRadius: '2px',
  },

  // Jinja2 comments ({# ... #})
  '.cm-md-jinja-comment': {
    color: '#9ca3af !important',
    fontStyle: 'italic',
  },

  // --- Slash command autocomplete dropdown ---
  // Use `& ` prefix for scoped specificity to override CM's built-in baseTheme.
  // CM defaults: monospace font, maxHeight 10em, blue/white selected state.
  '& .cm-tooltip.cm-tooltip-autocomplete': {
    backgroundColor: '#ffffff',
    border: '1px solid #e5e7eb',
    borderRadius: '12px',
    boxShadow: '0 8px 24px rgba(0, 0, 0, 0.12), 0 0 0 1px rgba(0, 0, 0, 0.02)',
    padding: '4px',
    minWidth: '300px',
    maxWidth: '340px',
    overflow: 'hidden',
  },
  // Fade overlay managed by scrollFadePlugin in slashCommands.ts.
  // Only visible when the list has more items below the visible area.
  // Insets match tooltip padding above so the fade covers the content area, not the border.
  '& .cm-autocomplete-fade': {
    position: 'absolute',
    bottom: '0',
    left: '4px',
    right: '4px',
    height: '64px',
    background: 'linear-gradient(to bottom, rgba(255,255,255,0) 0%, rgba(255,255,255,1) 60%)',
    pointerEvents: 'none',
    transition: 'opacity 150ms',
  },
  '& .cm-tooltip.cm-tooltip-autocomplete > ul': {
    fontFamily: 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif !important',
    maxHeight: '400px',
    minWidth: '300px',
    scrollbarWidth: 'none',  // Hide scrollbar (Firefox)
  },
  '& .cm-tooltip.cm-tooltip-autocomplete > ul::-webkit-scrollbar': {
    display: 'none',  // Hide scrollbar (Chrome/Safari)
  },
  '& .cm-tooltip-autocomplete ul li': {
    padding: '1px 8px 1px 10px !important',
    borderRadius: '6px',
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    cursor: 'pointer',
    height: '28px',
    lineHeight: '1',
  },
  '& .cm-tooltip-autocomplete ul li:hover': {
    backgroundColor: '#f3f4f6',  // gray-100, matches app hover states
  },
  '& .cm-tooltip-autocomplete ul li[aria-selected]': {
    backgroundColor: '#eff6ff',  // blue-50
    color: 'inherit',
  },
  // Section headers are <completion-section> custom elements, not .cm-completionSection
  // Section headers — uppercase, matching EditorCommandMenu style
  '& .cm-tooltip-autocomplete ul completion-section': {
    fontSize: '11px !important',
    fontWeight: '500',
    fontFamily: 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif !important',
    color: '#9ca3af !important',
    letterSpacing: '0.05em',
    textTransform: 'uppercase',
    // margin: 0 8px insets the border-top to match command menu's mx-2 dividers
    // padding: 8px 0 keeps text at same 12px from tooltip edge (4px tooltip + 8px margin + 0px padding)
    padding: '8px 0 4px !important',
    margin: '4px 8px 0 !important',
    borderBottom: 'none !important',
    borderTop: '1px solid #e5e7eb',
    opacity: '1 !important',
    lineHeight: '1.2 !important',
  },
  '& .cm-tooltip-autocomplete ul completion-section:first-child': {
    borderTop: 'none !important',
    marginTop: '0 !important',
    paddingTop: '8px !important',
  },
  '& .cm-completionLabel': {
    fontSize: '14px',
    color: '#374151',
    flex: '1',
  },
  '& .cm-tooltip-autocomplete ul li[aria-selected] .cm-completionLabel': {
    color: '#1d4ed8',  // blue-700
  },
  '& .cm-completionDetail': {
    fontSize: '12px',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
    color: '#d1d5db',
    fontStyle: 'normal',
    marginLeft: 'auto',
    flexShrink: '0',
  },
  '& .cm-tooltip-autocomplete ul li[aria-selected] .cm-completionDetail': {
    color: '#93c5fd',  // blue-300
  },
  '& .cm-completionMatchedText': {
    textDecoration: 'none',
    fontWeight: '600',
    color: '#111827',
  },
  '& .cm-tooltip-autocomplete ul li[aria-selected] .cm-completionMatchedText': {
    color: '#1d4ed8',
  },
  '& .cm-completionIcon': {
    display: 'none',
  },
  '& .cm-slash-icon': {
    width: '22px',
    height: '22px',
    color: '#9ca3af',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: '0',
  },
  '& .cm-tooltip-autocomplete ul li[aria-selected] .cm-slash-icon': {
    color: '#3b82f6',  // blue-500
  },
  '& .cm-slash-icon svg': {
    width: '18px',
    height: '18px',
  },
  '& .cm-slash-shortcut': {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'flex-end',
    gap: '2px',
    marginLeft: '4px',
    flexShrink: '0',
    width: '72px',  // fixed width for 3 keys; empty spacer for items without shortcuts
  },
  '& .cm-slash-shortcut kbd': {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    minWidth: '18px',
    height: '18px',
    padding: '0 3px',
    fontSize: '10px',
    fontFamily: 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif',
    fontWeight: '500',
    color: '#9ca3af',
    backgroundColor: '#f3f4f6',
    borderRadius: '3px',
    border: '1px solid #e5e7eb',
  },
  '& .cm-tooltip-autocomplete ul li[aria-selected] .cm-slash-shortcut kbd': {
    color: '#93c5fd',
    backgroundColor: '#dbeafe',
    borderColor: '#bfdbfe',
  },
  // Footer hint for command menu shortcut
  '& .cm-slash-footer': {
    position: 'relative',
    backgroundColor: '#ffffff',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '4px',
    padding: '5px 8px',
    borderTop: '1px solid #e5e7eb',
    fontSize: '11px',
    color: '#9ca3af',
    fontFamily: 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif',
  },
  '& .cm-slash-footer kbd': {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    minWidth: '16px',
    height: '16px',
    padding: '0 3px',
    fontSize: '10px',
    fontWeight: '500',
    fontFamily: 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif',
    color: '#9ca3af',
    backgroundColor: '#f3f4f6',
    borderRadius: '3px',
    border: '1px solid #e5e7eb',
  },
})

/**
 * Find link at a given position in the document.
 * Returns the URL if position is within a link, null otherwise.
 */
function findLinkAtPosition(view: EditorView, pos: number): string | null {
  const line = view.state.doc.lineAt(pos)
  const links = findLinks(line.text)
  const offsetInLine = pos - line.from

  for (const link of links) {
    if (offsetInLine >= link.from && offsetInLine < link.to) {
      return link.url
    }
  }

  return null
}

const LINK_HOVER_CLASS = 'cm-md-link-hover'

/**
 * Handle mousedown on the editor. Toggles checklist checkboxes, and intercepts
 * Cmd/Ctrl+mousedown over a link so CodeMirror doesn't add a secondary cursor.
 *
 * Browsers still fire the subsequent `click` event even when `mousedown` is
 * defaultPrevented (as long as mouseup lands on the same element), so the
 * click handler below runs and opens the link. That's how we suppress the
 * multi-cursor side effect without breaking cmd+click-to-open.
 */
function handleEditorMousedown(event: MouseEvent, view: EditorView): boolean {
  if (event.button !== 0) return false

  if (event.metaKey || event.ctrlKey) {
    const pos = view.posAtCoords({ x: event.clientX, y: event.clientY })
    if (pos !== null && findLinkAtPosition(view, pos)) {
      event.preventDefault()
      return true
    }
  }

  const target = event.target as HTMLElement
  if (!target.classList.contains('cm-md-checklist-checkbox') &&
      !target.closest('.cm-md-checklist-checkbox')) {
    return false
  }

  const pos = view.posAtCoords({ x: event.clientX, y: event.clientY })
  if (pos === null) return false

  const line = view.state.doc.lineAt(pos)
  const info = parseLine(line.text, false)
  if (info?.type !== 'checklist' || info.bracketPos === undefined) return false

  const bracketPos = line.from + info.bracketPos
  const newText = info.checked ? '[ ]' : '[x]'

  // Save current selection and restore it after the toggle
  const selection = view.state.selection
  view.dispatch({
    changes: { from: bracketPos, to: bracketPos + 3, insert: newText },
    selection,
  })
  event.preventDefault()
  return true
}

/** Cmd+click (Mac) or Ctrl+click (Windows/Linux) to open links. */
function handleEditorClick(event: MouseEvent, view: EditorView): boolean {
  if (event.button !== 0) return false
  if (!event.metaKey && !event.ctrlKey) {
    return false
  }

  const pos = view.posAtCoords({ x: event.clientX, y: event.clientY })
  if (pos === null) {
    return false
  }

  const url = findLinkAtPosition(view, pos)
  if (url) {
    let finalUrl = url
    if (!url.match(/^[a-zA-Z][a-zA-Z0-9+.-]*:/)) {
      finalUrl = 'https://' + url
    }
    window.open(finalUrl, '_blank', 'noopener,noreferrer')
    event.preventDefault()
    return true
  }

  return false
}

/**
 * Show a pointer cursor when Cmd/Ctrl is held over a link by toggling
 * LINK_HOVER_CLASS on view.dom (the theme supplies the actual cursor style).
 *
 * Known limitation: the affordance only updates on mousemove and keyup — if
 * the user rests the mouse on a link and then presses Cmd/Ctrl without moving,
 * the cursor won't change until they move again. Fixing it would require
 * tracking the last mouse coords and reacting to keydown; we've decided the
 * extra state isn't worth it for the uncommon "hover, then press modifier"
 * ordering. Revisit if users report it.
 */
function handleEditorMousemove(event: MouseEvent, view: EditorView): boolean {
  let wantHover = false
  if (event.metaKey || event.ctrlKey) {
    const pos = view.posAtCoords({ x: event.clientX, y: event.clientY })
    wantHover = pos !== null && findLinkAtPosition(view, pos) !== null
  }
  view.dom.classList.toggle(LINK_HOVER_CLASS, wantHover)
  return false
}

function handleEditorMouseleave(_event: MouseEvent, view: EditorView): boolean {
  view.dom.classList.remove(LINK_HOVER_CLASS)
  return false
}

/** Clear the pointer cursor when the modifier is released without moving the mouse. */
function handleEditorKeyup(event: KeyboardEvent, view: EditorView): boolean {
  if (!event.metaKey && !event.ctrlKey) {
    view.dom.classList.remove(LINK_HOVER_CLASS)
  }
  return false
}

const clickHandler = EditorView.domEventHandlers({
  mousedown: handleEditorMousedown,
  click: handleEditorClick,
  mousemove: handleEditorMousemove,
  mouseleave: handleEditorMouseleave,
  keyup: handleEditorKeyup,
})

/**
 * Create a dynamic font theme for the editor.
 * @param monoFont - If true, use JetBrains Mono at 14px; otherwise Inter at 15px.
 */
export function createFontTheme(monoFont: boolean): ReturnType<typeof EditorView.theme> {
  const fontFamily = monoFont
    ? '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace !important'
    : '"Inter", ui-sans-serif, system-ui, -apple-system, sans-serif !important'
  const fontSize = monoFont ? '14px !important' : '15px !important'

  return EditorView.theme({
    '&': { fontFamily, fontSize },
    '.cm-content': { fontFamily, fontSize },
    // Only fontFamily on .cm-line — fontSize is inherited from .cm-content
    // so that header em-based sizes (1.75em, 1.5em, etc.) aren't overridden
    '.cm-line': { fontFamily },
  })
}

/**
 * Complete markdown styling extension.
 * Add this to your CodeMirror extensions array.
 */
export const markdownStyleExtension = [
  markdownDecorationPlugin,
  cursorInCodeBlockPlugin,
  markdownBaseTheme,
  clickHandler,
]

// Export helper functions for testing
export const _testExports = {
  findImages,
  findLinks,
  findInlineCode,
  findStrikethrough,
  findHighlight,
  findBold,
  findItalic,
  findBlockquoteSyntax,
  findJinjaExpressions,
  parseLine,
  findLinkAtPosition,
  handleEditorMousedown,
  handleEditorClick,
  handleEditorMousemove,
  handleEditorMouseleave,
  handleEditorKeyup,
}
