/**
 * Tests for the ToC in reading mode: the scroll-to-line branch that targets
 * the rendered Milkdown DOM (resolution logic itself is covered in
 * utils/headingNavigation.test.ts — this exercises the wiring), the ToC
 * toggle/shortcut being available in reading mode, and the command menu
 * intentionally staying closed there (it's the guard keeping mutating
 * commands away from the hidden CodeMirror doc).
 *
 * jsdom reports a non-Mac platform, so Mod maps to ctrlKey.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { act } from 'react'
import type { MutableRefObject } from 'react'
import { CodeMirrorEditor } from './CodeMirrorEditor'
import { writeReadingMode } from '../utils/readingModeCache'
import { useRightSidebarStore } from '../stores/rightSidebarStore'

// Render a minimal reading view: top-level h1 per `# ` line, inside the
// .milkdown-wrapper the scroll branch queries. Enough DOM for wiring tests.
vi.mock('./MilkdownEditor', () => ({
  MilkdownEditor: ({ value }: { value: string }) => (
    <div className="milkdown-wrapper">
      <div className="milkdown">
        {value
          .split('\n')
          .filter((line) => line.startsWith('# '))
          .map((line, i) => (
            <h1 key={i}>{line.slice(2)}</h1>
          ))}
      </div>
    </div>
  ),
}))

const CONTENT = '# Alpha\n\ntext\n\n# Beta'

beforeEach(() => {
  localStorage.clear()
  useRightSidebarStore.setState({ activePanel: null })
  // jsdom doesn't implement scrollIntoView.
  Element.prototype.scrollIntoView = vi.fn()
})

function dispatch(init: KeyboardEventInit): void {
  act(() => {
    document.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, cancelable: true, ...init }))
  })
}

/** Mount in reading mode (seeded via the per-item cache) with a scroll ref. */
function renderReading(props: Record<string, unknown> = {}): {
  container: HTMLElement
  scrollRef: MutableRefObject<((line: number) => void) | null>
} {
  writeReadingMode('item-1', true)
  const scrollRef: MutableRefObject<((line: number) => void) | null> = { current: null }
  const { container } = render(
    <CodeMirrorEditor value={CONTENT} onChange={() => {}} itemId="item-1" scrollToLineRef={scrollRef} {...props} />,
  )
  expect(container.querySelector('[class*="milkdown-wrapper"]')).not.toBeNull()
  return { container, scrollRef }
}

describe('CodeMirrorEditor — ToC navigation in reading mode', () => {
  it('scrolls the rendered heading, without focusing the hidden CodeMirror', () => {
    const { container, scrollRef } = renderReading()

    act(() => scrollRef.current?.(5)) // line of "# Beta"

    const beta = Array.from(container.querySelectorAll('h1')).find((h) => h.textContent === 'Beta')
    expect(beta).toBeDefined()
    expect(beta?.scrollIntoView).toHaveBeenCalledWith({ block: 'start' })
    expect(document.activeElement?.closest('.cm-content')).toBeNull()
  })

  it('a line with no matching heading is a safe no-op', () => {
    const { scrollRef } = renderReading()
    act(() => scrollRef.current?.(3)) // "text" line
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled()
  })

  it('markdown mode still scrolls CodeMirror (focus moves into the editor)', () => {
    const scrollRef: MutableRefObject<((line: number) => void) | null> = { current: null }
    render(<CodeMirrorEditor value={CONTENT} onChange={() => {}} scrollToLineRef={scrollRef} />)

    act(() => scrollRef.current?.(5))

    expect(document.activeElement?.closest('.cm-content')).not.toBeNull()
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled()
  })
})

describe('CodeMirrorEditor — ToC control in reading mode', () => {
  it('the ToC toolbar button renders in reading mode when enabled', () => {
    const { container: withToc } = renderReading({ showTocToggle: true })
    writeReadingMode('item-2', true)
    const { container: withoutToc } = render(
      <CodeMirrorEditor value={CONTENT} onChange={() => {}} itemId="item-2" />,
    )
    expect(withToc.querySelectorAll('button').length).toBe(
      withoutToc.querySelectorAll('button').length + 1,
    )
  })

  it('the shortcut toggles the ToC panel while reading mode is on', () => {
    renderReading({ showTocToggle: true })

    dispatch({ code: 'KeyT', altKey: true })
    expect(useRightSidebarStore.getState().activePanel).toBe('toc')

    dispatch({ code: 'KeyT', altKey: true })
    expect(useRightSidebarStore.getState().activePanel).toBeNull()
  })

  it('the shortcut rejects a disabled editor, matching the disabled toolbar button', () => {
    // Deleted-item views expose showTocToggle with a disabled editor; the
    // shortcut must not act where the visible control says it can't.
    render(
      <CodeMirrorEditor value={CONTENT} onChange={() => {}} showTocToggle disabled />,
    )

    dispatch({ code: 'KeyT', altKey: true })
    expect(useRightSidebarStore.getState().activePanel).toBeNull()
  })

  it('the command menu stays closed in reading mode (mutation guard)', () => {
    renderReading({ showTocToggle: true })

    dispatch({ code: 'Slash', ctrlKey: true })
    expect(screen.queryByRole('listbox', { name: 'Editor commands' })).toBeNull()
  })

  it('the command menu still opens in markdown mode', () => {
    render(<CodeMirrorEditor value={CONTENT} onChange={() => {}} />)

    dispatch({ code: 'Slash', ctrlKey: true })
    expect(screen.getByRole('listbox', { name: 'Editor commands' })).toBeInTheDocument()
  })
})
