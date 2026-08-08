/**
 * Resolves a markdown heading (identified by source line) to its element in
 * the rendered (Milkdown/ProseMirror) reading view, for ToC click navigation.
 *
 * Strategy: candidate-set parity, then ordinal matching, with verification.
 * Both sides of the match come from the same grammar — markdownHeadings.ts
 * parses with remark, the engine the renderer itself uses — so ordinals agree
 * by construction for everything markdown-native. The DOM candidate set
 * excludes headings nested in blockquotes/list items (the source side reports
 * root-level headings only — e.g. `# Usage` / `> # Usage` / `# Usage` would
 * otherwise make "the 2nd parsed Usage" resolve to the blockquote's copy).
 * Residual skew is still possible from constructs no markdown AST sees (raw
 * HTML `<h1>` blocks render as real headings); text+level verification catches
 * it, with an occurrence-counting fallback. If that fails too, callers no-op —
 * a dead click is safer than silently scrolling to the wrong section.
 */
import { parseMarkdownHeadings } from './markdownHeadings'

/** Collapse whitespace so parsed text compares against DOM textContent. */
function normalize(text: string): string {
  return text.replace(/\s+/g, ' ').trim()
}

export function findRenderedHeading(
  root: Element,
  markdown: string,
  targetLine: number,
): HTMLElement | null {
  const headings = parseMarkdownHeadings(markdown)
  const targetIdx = headings.findIndex((h) => h.line === targetLine)
  if (targetIdx === -1) return null
  const target = headings[targetIdx]
  const targetText = normalize(target.text)
  const targetTag = `H${target.level}`

  const candidates = Array.from(
    root.querySelectorAll<HTMLElement>('h1, h2, h3, h4, h5, h6'),
  ).filter((el) => {
    const nested = el.closest('blockquote, li')
    return nested === null || !root.contains(nested)
  })

  const ordinal = candidates[targetIdx]
  if (
    ordinal !== undefined &&
    ordinal.tagName === targetTag &&
    normalize(ordinal.textContent ?? '') === targetText
  ) {
    return ordinal
  }

  // Fallback: the Nth same-text-same-level rendered heading, where N is this
  // heading's occurrence index among the parsed headings. Exact text only —
  // any tolerance here could bind "Usage" to "Advanced Usage".
  let occurrence = 0
  for (let i = 0; i < targetIdx; i++) {
    if (headings[i].level === target.level && normalize(headings[i].text) === targetText) {
      occurrence++
    }
  }
  const sameHeadings = candidates.filter(
    (el) => el.tagName === targetTag && normalize(el.textContent ?? '') === targetText,
  )
  return sameHeadings[occurrence] ?? null
}
