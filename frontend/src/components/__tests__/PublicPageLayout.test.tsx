/**
 * Tests for the public layout family: chrome composition (header/footer,
 * single-sourced across both route-level variants) and the ToC-capable shared
 * layout's geometry — the sidebar offset shrinks the whole page box (header,
 * content, and footer together) and the content column centers inside what's
 * left. Offsetting within an already-centered column collapsed content to
 * ~56px under a maximized sidebar; offsetting only <main> left the header's
 * right-aligned actions under the sidebar.
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { PublicPageLayout, PublicSharedTocLayout } from '../PublicPageLayout'
import { useRightSidebarStore, computeMaxWidth, getEffectiveSidebarWidth, MIN_CONTENT_WIDTH } from '../../stores/rightSidebarStore'

const REAL_INNER_WIDTH = window.innerWidth

function setViewportWidth(width: number): void {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: width })
}

function renderTree(initialPath: string): HTMLElement {
  const router = createMemoryRouter(
    [
      {
        element: <PublicPageLayout />,
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
    { initialEntries: [initialPath] }
  )

  const { container } = render(<RouterProvider router={router} />)
  return container
}

/** The page box the sidebar offset is applied to (chrome wrapper). */
function pageBox(container: HTMLElement): HTMLElement {
  return container.firstElementChild as HTMLElement
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
  ])('at %spx (maximized: %s) the page offset equals the effective sidebar width', (viewport: number, maximized: boolean) => {
    setViewportWidth(viewport)
    useRightSidebarStore.setState({ activePanel: 'toc', maximized })
    const container = renderTree('/shared/notes/tok')

    const expected = getEffectiveSidebarWidth(400, maximized, computeMaxWidth(viewport, 0))
    expect(pageBox(container).style.marginRight).toBe(`${expected}px`)
  })

  // The MIN_CONTENT_WIDTH reserve is NOT a guarantee across the whole desktop
  // range: computeMaxWidth floors the sidebar at MIN_SIDEBAR_WIDTH, so between
  // the 768px desktop breakpoint and 880px the content column is narrower than
  // the reserve. Pinned explicitly rather than skipped — an earlier matrix
  // tested only ≥1024px and read as if the floor always held.
  it.each([
    [768, 488],
    [879, 599],
    [880, 600],
    [1024, 624],
  ])('at %spx the remaining content column is %spx', (viewport: number, remaining: number) => {
    setViewportWidth(viewport)
    useRightSidebarStore.setState({ activePanel: 'toc' })
    const container = renderTree('/shared/notes/tok')

    const offset = parseInt(pageBox(container).style.marginRight, 10)
    expect(viewport - offset).toBe(remaining)
    // The floor holds only from 880px up.
    expect(viewport - offset >= MIN_CONTENT_WIDTH).toBe(viewport >= 880)
  })

  it('offsets the whole page box — header and footer shrink with the content', () => {
    // Regression guard: offsetting only <main> left the header's right-aligned
    // actions ("Open app") underneath the sidebar. jsdom computes no layout,
    // so assert containment — the header and footer must live inside the
    // offset box, and <main> must not carry a competing offset of its own.
    setViewportWidth(1440)
    useRightSidebarStore.setState({ activePanel: 'toc' })
    const container = renderTree('/shared/notes/tok')

    const box = pageBox(container)
    expect(box.style.marginRight).not.toBe('')
    expect(box.contains(screen.getByLabelText('Home'))).toBe(true)
    expect(box.contains(screen.getByRole('link', { name: 'Privacy Policy' }))).toBe(true)
    expect(container.querySelector('main')?.style.marginRight ?? '').toBe('')
  })

  it('the offset box has no explicit width, so the offset shrinks it', () => {
    // Regression guard for a shipped bug jsdom can't otherwise catch: with
    // `w-full` (width: 100%) the margin pushed the element into overflow
    // instead of shrinking it, leaving content underneath the sidebar.
    setViewportWidth(1440)
    useRightSidebarStore.setState({ activePanel: 'toc' })
    const container = renderTree('/shared/notes/tok')

    expect(pageBox(container).className).not.toMatch(/\bw-full\b/)
  })

  it('applies no offset below the desktop breakpoint (mobile overlay)', () => {
    setViewportWidth(500)
    useRightSidebarStore.setState({ activePanel: 'toc' })
    const container = renderTree('/shared/notes/tok')

    expect(pageBox(container).style.marginRight).toBe('')
  })

  it('applies no offset when the panel is closed or is history', () => {
    setViewportWidth(1440)
    useRightSidebarStore.setState({ activePanel: 'history' })
    const container = renderTree('/shared/notes/tok')

    expect(pageBox(container).style.marginRight).toBe('')
  })

  it('the standard layout never offsets, even with the ToC open (bookmark route)', () => {
    // Structural exclusion: shared bookmarks live under PublicPageLayout,
    // which has no offset logic — nothing to flash before an effect cleans up.
    setViewportWidth(1440)
    useRightSidebarStore.setState({ activePanel: 'toc' })
    const container = renderTree('/shared/bookmarks/tok')

    expect(screen.getByText('Bookmark Content')).toBeInTheDocument()
    expect(pageBox(container).style.marginRight).toBe('')
    expect(container.querySelector('main')?.style.marginRight ?? '').toBe('')
  })
})
