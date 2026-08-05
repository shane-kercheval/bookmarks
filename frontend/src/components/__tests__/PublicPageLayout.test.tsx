/**
 * Tests for the public layout family: chrome composition (header/footer,
 * single-sourced across both content variants) and the ToC-capable shared
 * layout's content geometry — the margin is applied to the full-width main
 * BEFORE centering, so content lays out in `viewport − sidebar` (the previous
 * inside-the-centered-column approach collapsed content to ~56px under a
 * maximized sidebar).
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import {
  PublicChromeLayout,
  PublicContentLayout,
  PublicSharedTocLayout,
} from '../PublicPageLayout'
import { useRightSidebarStore, computeMaxWidth, getEffectiveSidebarWidth, MIN_CONTENT_WIDTH } from '../../stores/rightSidebarStore'

const REAL_INNER_WIDTH = window.innerWidth

function setViewportWidth(width: number): void {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: width })
}

function renderTree(initialPath: string): HTMLElement {
  const router = createMemoryRouter(
    [
      {
        element: <PublicChromeLayout />,
        children: [
          {
            element: <PublicContentLayout />,
            children: [
              { path: '/changelog', element: <div>Changelog Content</div> },
              { path: '/roadmap', element: <div>Roadmap Content</div> },
              { path: '/shared/bookmarks/:token', element: <div>Bookmark Content</div> },
            ],
          },
          {
            element: <PublicSharedTocLayout />,
            children: [
              { path: '/shared/notes/:token', element: <div>Note Content</div> },
            ],
          },
        ],
      },
    ],
    { initialEntries: [initialPath] }
  )

  const { container } = render(<RouterProvider router={router} />)
  return container
}

beforeEach(() => {
  useRightSidebarStore.setState({ activePanel: null, width: 400, maximized: false })
})

afterEach(() => {
  setViewportWidth(REAL_INNER_WIDTH)
})

describe('public layout chrome (single-sourced across variants)', () => {
  it('standard content pages render header, footer, and content', () => {
    renderTree('/changelog')

    expect(screen.getByLabelText('Home')).toBeInTheDocument()
    // "Docs" appears in both header and footer
    expect(screen.getAllByRole('link', { name: 'Docs' }).length).toBe(2)
    expect(screen.getByText('Changelog Content')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Privacy Policy' })).toBeInTheDocument()
  })

  it('shared ToC pages render the same chrome', () => {
    renderTree('/shared/notes/tok')

    expect(screen.getByLabelText('Home')).toBeInTheDocument()
    expect(screen.getByText('Note Content')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Privacy Policy' })).toBeInTheDocument()
  })

  it('does not render the docs sidebar', () => {
    renderTree('/changelog')
    expect(screen.queryByRole('link', { name: 'Getting Started' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'AI Integration' })).not.toBeInTheDocument()
  })
})

describe('PublicSharedTocLayout — content offset while the ToC is open', () => {
  // No left sidebar exists on public pages, so the effective width derives
  // from the viewport alone — deterministic per width.
  it.each([
    [1024, false],
    [1440, false],
    [1920, true], // maximized: the collapse case the old geometry failed
  ])('at %spx (maximized: %s) the main margin equals the effective sidebar width and content keeps the 600px floor', (viewport: number, maximized: boolean) => {
    setViewportWidth(viewport)
    useRightSidebarStore.setState({ activePanel: 'toc', maximized })
    const container = renderTree('/shared/notes/tok')

    const expected = getEffectiveSidebarWidth(400, maximized, computeMaxWidth(viewport, 0))
    const main = container.querySelector('main')
    expect(main?.style.marginRight).toBe(`${expected}px`)
    // Content region = viewport − sidebar; the store's max-width math reserves
    // MIN_CONTENT_WIDTH, so readability holds by construction.
    expect(viewport - expected).toBeGreaterThanOrEqual(MIN_CONTENT_WIDTH)
  })

  it('applies no margin below the desktop breakpoint (mobile overlay)', () => {
    setViewportWidth(500)
    useRightSidebarStore.setState({ activePanel: 'toc' })
    const container = renderTree('/shared/notes/tok')

    expect(container.querySelector('main')?.style.marginRight).toBe('')
  })

  it('applies no margin when the panel is closed or is history', () => {
    setViewportWidth(1440)
    useRightSidebarStore.setState({ activePanel: 'history' })
    const container = renderTree('/shared/notes/tok')

    expect(container.querySelector('main')?.style.marginRight).toBe('')
  })

  it('the standard layout never margins, even with the ToC open (bookmark route)', () => {
    // Structural exclusion: shared bookmarks live under PublicContentLayout,
    // which has no margin logic — nothing to flash before an effect cleans up.
    setViewportWidth(1440)
    useRightSidebarStore.setState({ activePanel: 'toc' })
    const container = renderTree('/shared/bookmarks/tok')

    expect(screen.getByText('Bookmark Content')).toBeInTheDocument()
    expect(container.querySelector('main')?.style.marginRight).toBe('')
  })
})
