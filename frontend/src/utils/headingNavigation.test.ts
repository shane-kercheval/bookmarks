/**
 * Tests for reading-mode heading resolution (see headingNavigation.ts).
 *
 * The rendered DOM is constructed directly (the real Milkdown output shape:
 * block elements as children of a root, nested headings inside
 * blockquote/li) so the parity, verification, and fallback layers can each be
 * exercised — including adversarial cases where the source parser and the
 * renderer disagree about which headings exist.
 */
import { describe, it, expect } from 'vitest'
import { findRenderedHeading } from './headingNavigation'

function dom(html: string): HTMLElement {
  const root = document.createElement('div')
  root.innerHTML = html
  return root
}

describe('findRenderedHeading', () => {
  it('resolves headings by ordinal in the common case', () => {
    const markdown = '# Alpha\n\ntext\n\n## Beta\n\n# Gamma'
    const root = dom('<h1>Alpha</h1><p>text</p><h2>Beta</h2><h1>Gamma</h1>')

    expect(findRenderedHeading(root, markdown, 5)?.textContent).toBe('Beta')
    expect(findRenderedHeading(root, markdown, 7)?.textContent).toBe('Gamma')
  })

  it('excludes blockquote-nested headings from the candidate set (parity)', () => {
    // `# Usage` / `> # Usage` / `# Usage`: the source parser reports two
    // root-level headings; the DOM renders three h1 elements. Without the
    // nesting filter, "the 2nd parsed Usage" would resolve to the blockquote's
    // copy.
    const markdown = '# Usage\n\n> # Usage\n\n# Usage'
    const root = dom('<h1>Usage</h1><blockquote><h1>Usage</h1></blockquote><h1>Usage</h1>')

    const resolved = findRenderedHeading(root, markdown, 5)
    expect(resolved).not.toBeNull()
    expect(resolved?.parentElement?.tagName).not.toBe('BLOCKQUOTE')
    expect(resolved).toBe(root.children[2])
  })

  it('excludes list-nested headings from the candidate set (parity)', () => {
    const markdown = '# First\n\n- item\n\n# Second'
    const root = dom('<h1>First</h1><ul><li><h1>In list</h1></li></ul><h1>Second</h1>')

    expect(findRenderedHeading(root, markdown, 5)?.textContent).toBe('Second')
  })

  it('duplicate headings straddling a setext heading resolve correctly', () => {
    const markdown = '# Usage\n\nMiddle\n===\n\n# Usage'
    const root = dom('<h1>Usage</h1><h1>Middle</h1><h1>Usage</h1>')

    expect(findRenderedHeading(root, markdown, 6)).toBe(root.children[2])
  })

  it('verifies by text after link normalization', () => {
    const markdown = '# See [the docs](https://example.com)'
    const root = dom('<h1>See <a href="https://example.com">the docs</a></h1>')

    expect(findRenderedHeading(root, markdown, 1)).toBe(root.children[0])
  })

  it('multi-line setext headings match exactly against the full rendered text', () => {
    // The AST parser reports the whole promoted paragraph as heading text
    // (anchored to its first line), matching the DOM — no suffix tolerance
    // needed or applied.
    const markdown = 'First line\nsecond line\n===\n'
    const root = dom('<h1>First line second line</h1>')

    expect(findRenderedHeading(root, markdown, 1)).toBe(root.children[0])
  })

  it('falls back to occurrence matching when an unparsed heading skews ordinals', () => {
    // Raw HTML headings in markdown render as real elements but are invisible
    // to any markdown AST — residual skew the verification layer must catch.
    const markdown = '# Usage\n\n<h1>Injected</h1>\n\n# Usage'
    const root = dom('<h1>Usage</h1><h1>Injected</h1><h1>Usage</h1>')

    // Ordinal for the 2nd parsed Usage points at "Injected" — text verification
    // rejects it, and occurrence matching (2nd "Usage" h1) recovers.
    expect(findRenderedHeading(root, markdown, 5)).toBe(root.children[2])
  })

  it('does not bind to a superstring when verification fails', () => {
    // "Usage" must not resolve to "Advanced Usage" — a dead click is safer
    // than a wrong jump.
    const markdown = '# Usage\n\n<h1>Injected</h1>'
    const root = dom('<h1>Advanced Usage</h1><h1>Injected</h1>')

    expect(findRenderedHeading(root, markdown, 1)).toBeNull()
  })

  it('rejects an ordinal whose level does not match', () => {
    const markdown = '## Title'
    const root = dom('<h1>Title</h1>')

    expect(findRenderedHeading(root, markdown, 1)).toBeNull()
  })

  it('returns null for a line with no parsed heading (safe no-op)', () => {
    const markdown = '# Alpha\n\ntext'
    const root = dom('<h1>Alpha</h1><p>text</p>')

    expect(findRenderedHeading(root, markdown, 3)).toBeNull()
    expect(findRenderedHeading(root, markdown, 99)).toBeNull()
  })

  it('empty headings resolve by ordinal but never by text fallback', () => {
    const markdown = '# \n\n# ' // two empty headings
    const root = dom('<h1></h1><h1></h1>')

    expect(findRenderedHeading(root, markdown, 3)).toBe(root.children[1])
  })
})
