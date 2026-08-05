/**
 * Tests for the shared callout marker grammar (see callouts.ts). Exhaustive at
 * this layer — the three consumers (CodeMirror, Milkdown, docs remark plugin)
 * spot-check integration and rely on these for grammar coverage.
 */
import { describe, it, expect } from 'vitest'
import {
  matchCalloutMarker,
  matchCalloutMarkerInLine,
  resolveCalloutKeyword,
  CALLOUT_VARIANTS,
  type CalloutVariant,
} from './callouts'

const ALIASES: Record<CalloutVariant, string[]> = {
  note: ['note', 'info', 'information'],
  tip: ['tip', 'hint', 'success', 'check', 'done'],
  important: ['important'],
  warning: ['warning', 'attention'],
  caution: ['caution', 'danger', 'error', 'bug', 'failure'],
}

describe('resolveCalloutKeyword', () => {
  it('resolves every alias to its canonical variant, case-insensitively', () => {
    for (const variant of CALLOUT_VARIANTS) {
      for (const alias of ALIASES[variant]) {
        expect(resolveCalloutKeyword(alias)).toBe(variant)
        expect(resolveCalloutKeyword(alias.toUpperCase())).toBe(variant)
        expect(resolveCalloutKeyword(alias[0].toUpperCase() + alias.slice(1))).toBe(variant)
      }
    }
  })

  it('returns null for unknown keywords', () => {
    expect(resolveCalloutKeyword('foo')).toBeNull()
    expect(resolveCalloutKeyword('warn')).toBeNull()
    expect(resolveCalloutKeyword('')).toBeNull()
  })
})

describe('matchCalloutMarker (post-parse text, no > prefix)', () => {
  it('matches every alias with and without the bang', () => {
    for (const variant of CALLOUT_VARIANTS) {
      for (const alias of ALIASES[variant]) {
        expect(matchCalloutMarker(`[!${alias}]`)?.variant).toBe(variant)
        expect(matchCalloutMarker(`[${alias}]`)?.variant).toBe(variant)
        expect(matchCalloutMarker(`[!${alias.toUpperCase()}]`)?.variant).toBe(variant)
      }
    }
  })

  it('reports marker offsets', () => {
    const marker = matchCalloutMarker('[!WARNING] rest')
    expect(marker).toMatchObject({ markerStart: 0, markerEnd: 10 })
  })

  it('captures a custom title with its span', () => {
    const marker = matchCalloutMarker('[!note]  My Title ')
    expect(marker?.title).toBe('My Title')
    expect('[!note]  My Title '.slice(marker!.titleStart, marker!.titleEnd)).toBe('My Title')
  })

  it('no title → null title with a zero-length span at markerEnd', () => {
    const marker = matchCalloutMarker('[!note]')
    expect(marker?.title).toBeNull()
    expect(marker?.titleStart).toBe(marker?.markerEnd)
    expect(marker?.titleEnd).toBe(marker?.markerEnd)
  })

  it('bounds the title to the marker line (soft-break newlines in input)', () => {
    const marker = matchCalloutMarker('[!WARNING] Title here\nBody continues')
    expect(marker?.title).toBe('Title here')
    expect(marker?.titleEnd).toBeLessThan('[!WARNING] Title here'.length + 1)
  })

  it('body after a newline is not a title', () => {
    const marker = matchCalloutMarker('[!WARNING]\nBody')
    expect(marker?.title).toBeNull()
  })

  it.each([
    ['no brackets', 'WARNING'],
    ['empty brackets', '[]'],
    ['bang only', '[!]'],
    ['non-alpha keyword', '[!123]'],
    ['space after bang', '[! note]'],
    ['space in brackets', '[warning ]'],
    ['unknown keyword', '[!FOO]'],
    ['marker not at start', 'text [!note]'],
    ['leading whitespace', ' [!note]'],
  ])('%s → null', (_label: string, text: string) => {
    expect(matchCalloutMarker(text)).toBeNull()
  })
})

describe('matchCalloutMarkerInLine (raw source with > prefix)', () => {
  it('matches with the common prefix shapes and offsets into line coordinates', () => {
    expect(matchCalloutMarkerInLine('> [!WARNING]')).toMatchObject({
      variant: 'warning',
      markerStart: 2,
      markerEnd: 12,
    })
    expect(matchCalloutMarkerInLine('>[!note]')).toMatchObject({ markerStart: 1, markerEnd: 8 })
    expect(matchCalloutMarkerInLine('>   [!tip]')?.variant).toBe('tip')
  })

  it('title span is offset into line coordinates', () => {
    const line = '> [!note] Custom'
    const marker = matchCalloutMarkerInLine(line)
    expect(line.slice(marker!.titleStart, marker!.titleEnd)).toBe('Custom')
  })

  it('non-blockquote lines never match', () => {
    expect(matchCalloutMarkerInLine('[!note]')).toBeNull()
    expect(matchCalloutMarkerInLine('  > [!note]')).toBeNull() // indented > isn't a blockquote to the CM parser
  })

  it('a plain blockquote line is not a callout', () => {
    expect(matchCalloutMarkerInLine('> just a quote')).toBeNull()
    expect(matchCalloutMarkerInLine('>')).toBeNull()
  })
})
