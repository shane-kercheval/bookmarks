/**
 * Remark plugin: lower GitHub-style alert blockquotes into docs callouts.
 *
 * Authors write a callout as a blockquote whose first line is an alert marker:
 *
 *   > [!tip]
 *   > **Optional bold title**
 *   >
 *   > Body prose.
 *
 * This is valid, portable markdown (GitHub renders the same markers) and stays
 * readable as raw `.md` for agents. The plugin strips the `[!variant]` marker
 * and tags the blockquote with a `callout callout-<variant>` class; the markdown
 * renderer's `blockquote` component maps that class to the legacy `<InfoCallout>`
 * styling. The title, when present, is just authored bold markdown — no out-of-band
 * metadata — so it round-trips with the rest of the body.
 *
 * The marker GRAMMAR is shared with the editor and reading-mode pipelines
 * (utils/callouts.ts — optional `!`, case-insensitive, aliased keywords), so
 * the three renderers can't drift on which spellings they accept. The five
 * canonical variants then collapse onto the docs' deliberately smaller
 * three-style palette (note/important → info, warning/caution → warning) — a
 * docs PRESENTATION choice, kept so shipped docs pages don't change
 * appearance. An inline Obsidian-style title after the marker is left in
 * place as body prose (docs use the bold-line title convention instead).
 */
import type { Root, Blockquote, Paragraph, Text } from 'mdast'
import type { CalloutVariant } from '../../pages/docs/components/calloutStyles'
import { matchCalloutMarker, type CalloutVariant as CanonicalVariant } from '../../utils/callouts'

const CANONICAL_TO_DOCS: Record<CanonicalVariant, CalloutVariant> = {
  note: 'info',
  important: 'info',
  tip: 'tip',
  warning: 'warning',
  caution: 'warning',
}

/** Strips the leading `[!variant]` marker; returns the resolved docs variant. */
function extractMarker(blockquote: Blockquote): CalloutVariant | null {
  const firstChild = blockquote.children[0]
  if (firstChild === undefined || firstChild.type !== 'paragraph') return null
  const paragraph = firstChild as Paragraph
  const firstText = paragraph.children[0]
  if (firstText === undefined || firstText.type !== 'text') return null
  const text = firstText as Text

  const marker = matchCalloutMarker(text.value)
  if (marker === null) return null

  // Strip the marker plus trailing spaces and (at most) the newline that
  // separated it from the body.
  text.value = text.value.slice(marker.markerEnd).replace(/^[ \t]*\n?/, '')
  // Drop the marker's now-empty text node (and paragraph, if it held only the marker).
  if (text.value === '') {
    paragraph.children.shift()
    // A hard line-break (trailing-spaces newline) after the marker parses as a
    // `break` node — drop it too, or the body starts with a stray blank line.
    if (paragraph.children[0]?.type === 'break') {
      paragraph.children.shift()
    }
    if (paragraph.children.length === 0) blockquote.children.shift()
  }
  return CANONICAL_TO_DOCS[marker.variant]
}

// Note: this visitor recurses into nested blockquotes, so `> > [!tip]` becomes
// a callout here — a docs-only behavior (the editor and reading-mode pipelines
// treat nested quotes as plain). Pre-existing and harmless for curated docs
// prose; recorded in the editor-improvements plan.
function visit(node: { type: string; children?: unknown[] }): void {
  if (node.type === 'blockquote') {
    const variant = extractMarker(node as Blockquote)
    if (variant !== null) {
      const data = ((node as Blockquote).data ??= {})
      data.hProperties = { ...(data.hProperties ?? {}), className: ['callout', `callout-${variant}`] }
    }
  }
  if (Array.isArray(node.children)) {
    for (const child of node.children) {
      visit(child as { type: string; children?: unknown[] })
    }
  }
}

export function remarkCallouts() {
  return (tree: Root): void => {
    visit(tree as unknown as { type: string; children?: unknown[] })
  }
}
