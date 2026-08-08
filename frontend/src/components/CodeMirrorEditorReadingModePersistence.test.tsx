/**
 * Tests for per-item reading-mode persistence in CodeMirrorEditor
 * (see utils/readingModeCache.ts for the storage semantics).
 *
 * Covers the seeding contract (cache hit → reading mode, miss/create →
 * markdown), write-through on toggle, the create→save (undefined → ID)
 * transition write, and reader-mode isolation (public views neither read nor
 * write the cache).
 *
 * Reading mode is toggled via the registry shortcut (Mod+Shift+M, matched on
 * code KeyM) dispatched at the document, exercising the real capture-phase
 * path. jsdom reports a non-Mac platform, so Mod maps to ctrlKey.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import { act } from 'react'
import { CodeMirrorEditor } from './CodeMirrorEditor'
import { readReadingMode, writeReadingMode } from '../utils/readingModeCache'
import { vi } from 'vitest'

// Reading mode renders the (heavy) Milkdown preview; stub it to a marker div.
vi.mock('./MilkdownEditor', () => ({
  MilkdownEditor: ({ value }: { value: string }) => <div data-testid="reading">{value}</div>,
}))

beforeEach(() => {
  localStorage.clear()
})

function isReadingMode(container: HTMLElement): boolean {
  return container.querySelector('[data-testid="reading"]') !== null
}

function toggleReadingModeViaShortcut(): void {
  act(() => {
    document.dispatchEvent(
      new KeyboardEvent('keydown', {
        code: 'KeyM',
        ctrlKey: true,
        shiftKey: true,
        bubbles: true,
        cancelable: true,
      }),
    )
  })
}

describe('CodeMirrorEditor — per-item reading-mode persistence', () => {
  it('cache hit seeds reading mode, and it survives a remount (refresh / contentKey bump)', () => {
    writeReadingMode('item-1', true)

    const first = render(<CodeMirrorEditor value="# hi" onChange={() => {}} itemId="item-1" />)
    expect(isReadingMode(first.container)).toBe(true)
    first.unmount()

    // Remount simulates both a page refresh and the parents' contentKey bump
    // on server sync — the initializer re-reads the cache either way.
    const second = render(<CodeMirrorEditor value="# hi" onChange={() => {}} itemId="item-1" />)
    expect(isReadingMode(second.container)).toBe(true)
  })

  it('cache miss opens in markdown mode', () => {
    const { container } = render(
      <CodeMirrorEditor value="# hi" onChange={() => {}} itemId="never-toggled" />,
    )
    expect(isReadingMode(container)).toBe(false)
  })

  it('create mode (no itemId) opens an editable markdown editor', () => {
    const { container } = render(<CodeMirrorEditor value="" onChange={() => {}} />)
    expect(isReadingMode(container)).toBe(false)
    expect(container.querySelector('.cm-content')?.getAttribute('contenteditable')).toBe('true')
  })

  it('toggling writes through: on inserts the entry, off deletes it', () => {
    const { container } = render(
      <CodeMirrorEditor value="# hi" onChange={() => {}} itemId="item-2" />,
    )
    expect(isReadingMode(container)).toBe(false)

    toggleReadingModeViaShortcut()
    expect(isReadingMode(container)).toBe(true)
    expect(readReadingMode('item-2')).toBe(true)

    toggleReadingModeViaShortcut()
    expect(isReadingMode(container)).toBe(false)
    expect(readReadingMode('item-2')).toBe(false)
  })

  it('a mode toggled during create is written when the item first gains an ID (with the create signal)', () => {
    // create → toggle reading on → save (ID appears without a remount, parent
    // asserts itemIdWasJustCreated per its fromCreate contract) → the pre-save
    // toggle must be persisted under the new ID, and a later fresh mount
    // (refresh) must restore it.
    const { rerender, unmount } = render(<CodeMirrorEditor value="# hi" onChange={() => {}} />)

    toggleReadingModeViaShortcut()
    expect(readReadingMode('new-id')).toBe(false) // no ID yet — nothing written

    rerender(<CodeMirrorEditor value="# hi" onChange={() => {}} itemId="new-id" itemIdWasJustCreated />)
    expect(readReadingMode('new-id')).toBe(true)
    unmount()

    const refreshed = render(<CodeMirrorEditor value="# hi" onChange={() => {}} itemId="new-id" />)
    expect(isReadingMode(refreshed.container)).toBe(true)
  })

  it('an in-place ID assignment WITHOUT the create signal never writes (poison regression)', () => {
    // Browser-back (or sidebar click) from /new to an EXISTING item: the same
    // editor instance renders once with the existing item's ID before the
    // parent's corrective contentKey remount. The draft's toggled-on mode must
    // NOT be written under that item — without the itemIdWasJustCreated gate,
    // this poisoned the existing item's remembered mode.
    const { rerender, unmount } = render(<CodeMirrorEditor value="# draft" onChange={() => {}} />)

    toggleReadingModeViaShortcut()

    rerender(<CodeMirrorEditor value="# draft" onChange={() => {}} itemId="existing-note" />)
    expect(readReadingMode('existing-note')).toBe(false)
    expect(localStorage.getItem('tiddly:reading-mode')).toBeNull()
    unmount()

    // After the corrective remount (fresh mount), the item opens per its own
    // (absent) entry — markdown — and the cache is still clean.
    const remounted = render(<CodeMirrorEditor value="# note" onChange={() => {}} itemId="existing-note" />)
    expect(isReadingMode(remounted.container)).toBe(false)
    expect(localStorage.getItem('tiddly:reading-mode')).toBeNull()
  })

  it('a markdown-mode create writes nothing when the ID appears', () => {
    const { rerender } = render(<CodeMirrorEditor value="# hi" onChange={() => {}} />)
    rerender(<CodeMirrorEditor value="# hi" onChange={() => {}} itemId="saved-id" itemIdWasJustCreated />)
    expect(readReadingMode('saved-id')).toBe(false)
    expect(localStorage.getItem('tiddly:reading-mode')).toBeNull()
  })

  it('a document switch (remount with a new ID) does not cross-write entries', () => {
    writeReadingMode('doc-a', true)

    const first = render(<CodeMirrorEditor value="# a" onChange={() => {}} itemId="doc-a" />)
    expect(isReadingMode(first.container)).toBe(true)
    first.unmount()

    // Parents remount via contentKey on document switch; the new document must
    // seed from ITS OWN entry (miss → markdown), not inherit doc-a's mode.
    const second = render(<CodeMirrorEditor value="# b" onChange={() => {}} itemId="doc-b" />)
    expect(isReadingMode(second.container)).toBe(false)
    expect(readReadingMode('doc-b')).toBe(false)
    expect(readReadingMode('doc-a')).toBe(true)
  })
})

describe('CodeMirrorEditor — disabled editor (e.g. deleted item view)', () => {
  // The shortcut must not mutate the persisted preference on a disabled view:
  // effectiveReadingMode masks the flip visually, so an unguarded toggle would
  // silently change durable state. Both persistence directions matter — an
  // insert (miss → entry) and a delete (entry → gone) are each half the bug.
  it('the shortcut cannot INSERT an entry (miss stays miss, mode unchanged)', () => {
    const { container } = render(
      <CodeMirrorEditor value="# hi" onChange={() => {}} itemId="deleted-1" disabled />,
    )
    toggleReadingModeViaShortcut()

    expect(isReadingMode(container)).toBe(false)
    expect(readReadingMode('deleted-1')).toBe(false)
    expect(localStorage.getItem('tiddly:reading-mode')).toBeNull()
  })

  it('the shortcut cannot DELETE an existing entry', () => {
    writeReadingMode('deleted-2', true)
    render(<CodeMirrorEditor value="# hi" onChange={() => {}} itemId="deleted-2" disabled />)

    toggleReadingModeViaShortcut()
    expect(readReadingMode('deleted-2')).toBe(true)
  })
})

describe('CodeMirrorEditor — reader mode (public view) cache isolation', () => {
  it('seeds from defaultReadingMode, ignoring the cache', () => {
    // No cache entry, yet reader mode opens rendered (notes/bookmarks default).
    const rendered = render(
      <CodeMirrorEditor value="# hi" onChange={() => {}} readerMode defaultReadingMode itemId="pub-1" />,
    )
    expect(isReadingMode(rendered.container)).toBe(true)
    rendered.unmount()

    // Cache entry present, yet the prompt-style default (raw source) wins.
    writeReadingMode('pub-2', true)
    const raw = render(
      <CodeMirrorEditor value="{{ x }}" onChange={() => {}} readerMode itemId="pub-2" />,
    )
    expect(isReadingMode(raw.container)).toBe(false)
  })

  it('a visitor toggling the mode does not write to the cache', () => {
    const { container } = render(
      <CodeMirrorEditor value="# hi" onChange={() => {}} readerMode defaultReadingMode itemId="pub-3" />,
    )
    expect(isReadingMode(container)).toBe(true)

    toggleReadingModeViaShortcut() // off
    toggleReadingModeViaShortcut() // back on — an insert would happen here if not isolated
    expect(localStorage.getItem('tiddly:reading-mode')).toBeNull()
  })
})
