/**
 * Extracts top-level headings from markdown source for the ToC sidebar and
 * reading-mode navigation.
 *
 * Parses with the REAL markdown parser (remark) rather than approximating the
 * grammar by hand. This matters beyond convenience: reading-mode navigation
 * resolves headings by ordinal against the rendered DOM, so the set of
 * headings this module reports must match what the renderer emits — and the
 * renderer (Milkdown) parses through the same remark/mdast engine with the
 * same GFM extension (`@milkdown/kit/preset/gfm` is remark-gfm-backed). Using
 * remark here makes that parity true by construction: setext headings, closing
 * sequences (`# Title #`), bare `#` (a valid empty heading), indentation
 * rules, and inline normalization all agree with the renderer for free.
 *
 * Only ROOT-LEVEL headings are reported — headings nested in blockquotes or
 * list items are excluded, matching the candidate-set filter in
 * headingNavigation.ts.
 */
import { unified } from 'unified'
import remarkParse from 'remark-parse'
import remarkGfm from 'remark-gfm'
import type { Heading, PhrasingContent } from 'mdast'

export interface MarkdownHeading {
  level: number // 1-6
  text: string // heading text as the rendered DOM would show it (no markers)
  /**
   * 1-based source line the heading starts on. For setext headings this is the
   * FIRST line of the promoted paragraph (a multi-line paragraph is all
   * heading text) — navigation should land at the heading's start.
   */
  line: number
}

// Module-scope processor: `parse()` runs only the syntax layer (no
// transformers), and remark-gfm participates at that layer via its micromark
// extensions, so one frozen processor serves every call.
const processor = unified().use(remarkParse).use(remarkGfm)

/**
 * Flatten a heading's inline nodes the way DOM textContent would.
 * Deliberately NOT mdast-util-to-string: that includes image alt text, which
 * an <img> does not contribute to textContent — and reading-mode verification
 * compares this output against textContent. Images and raw inline HTML
 * contribute nothing; everything else contributes its literal value or its
 * children's flattening.
 */
function flattenInlineText(nodes: PhrasingContent[]): string {
  let out = ''
  for (const node of nodes) {
    if (node.type === 'image' || node.type === 'imageReference' || node.type === 'html') continue
    if ('value' in node) {
      out += node.value
    } else if ('children' in node) {
      out += flattenInlineText(node.children as PhrasingContent[])
    }
  }
  return out
}

/**
 * Strip Milkdown's non-GFM inline extensions so parsed text matches what its
 * renderer shows. Milkdown's commonmark preset includes remarkMarker
 * (==highlight== → <mark>), which plain remark-gfm leaves as literal text.
 */
function stripNonStandardMarks(text: string): string {
  return text.replace(/==(.+?)==/g, '$1')
}

export function parseMarkdownHeadings(text: string): MarkdownHeading[] {
  const root = processor.parse(text)
  const headings: MarkdownHeading[] = []
  for (const node of root.children) {
    if (node.type !== 'heading') continue
    const heading = node as Heading
    const line = heading.position?.start.line
    if (line === undefined) continue
    headings.push({
      level: heading.depth,
      text: stripNonStandardMarks(flattenInlineText(heading.children)).replace(/\s+/g, ' ').trim(),
      line,
    })
  }
  return headings
}
