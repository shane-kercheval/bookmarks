import { Outlet } from 'react-router-dom'
import type { ReactNode } from 'react'
import { PublicHeader } from './PublicHeader'
import { Footer } from './Footer'
import { useRightSidebarStore } from '../stores/rightSidebarStore'
import { useEffectiveSidebarMetrics } from '../hooks/useResizableSidebar'

/**
 * Layouts for standalone public pages. Two route-level variants sharing one
 * chrome component, so header/footer stay single-sourced:
 *
 *   PublicPageLayout       — changelog, roadmap, pricing, shared bookmarks
 *   PublicSharedTocLayout  — shared notes/prompts (the ToC-capable pages)
 *
 * Splitting at the route level (rather than reacting to sidebar state on every
 * public page) keeps the no-ToC pages structurally incapable of picking up a
 * sidebar margin — nothing to flash before an effect could clean it up.
 */

interface PublicChromeProps {
  children: ReactNode
  /** Right offset reserved for an open sidebar; shrinks header, content, and footer together. */
  marginRight?: number
}

function PublicChrome({ children, marginRight = 0 }: PublicChromeProps): ReactNode {
  return (
    // The offset lives on the OUTER box so the sticky header and footer shrink
    // with the content — the app's Layout likewise puts its whole content
    // column inside the margined element. Offsetting only <main> leaves the
    // header's right-aligned actions (e.g. "Open app") under the sidebar.
    <div
      className="flex min-h-screen flex-col bg-white transition-[margin] duration-200"
      style={marginRight > 0 ? { marginRight } : undefined}
    >
      <PublicHeader />
      {children}
      <Footer />
    </div>
  )
}

/** Standard centered content area, without a docs sidebar. */
export function PublicPageLayout(): ReactNode {
  return (
    <PublicChrome>
      <main className="mx-auto w-full max-w-5xl flex-1 px-6 py-12 sm:px-8 lg:px-12">
        <Outlet />
      </main>
    </PublicChrome>
  )
}

/**
 * The ToC-capable shared pages (notes/prompts). The sidebar offset shrinks the
 * whole page box, and the content column then centers INSIDE what's left —
 * offsetting within an already-centered column can only squeeze it against its
 * fixed left edge (at large sidebar widths content collapsed to ~56px while
 * real viewport space sat unused).
 *
 * Two known width limitations, both recorded in the editor-improvements plan:
 *
 * 1. `computeMaxWidth` reserves MIN_CONTENT_WIDTH (600px) for content, but
 *    floors the sidebar at MIN_SIDEBAR_WIDTH (280px) — so the floor only
 *    actually holds from ~880px viewport up. Between the 768px desktop
 *    breakpoint and 880px the content column is 488–599px. (The authenticated
 *    app shares this squeeze; its editor content narrows the same way.)
 * 2. Shrinking this box does NOT change PublicHeader's and Footer's `sm:`/`md:`
 *    breakpoints, which are keyed to the VIEWPORT — so at a wide viewport with
 *    a maximized sidebar they lay out for the window, not for the ~600px box
 *    they're in. Unlike (1) this is specific to the public pages: the app never
 *    renders its footer inside a sidebar-margined layout. Container queries on
 *    the chrome are the durable fix if it proves visibly cramped.
 */
export function PublicSharedTocLayout(): ReactNode {
  const tocOpen = useRightSidebarStore((state) => state.activePanel === 'toc')
  const { effectiveWidth, isDesktop } = useEffectiveSidebarMetrics()
  // Desktop only: below the breakpoint the sidebar is a full-width overlay.
  const marginRight = tocOpen && isDesktop ? effectiveWidth : 0

  return (
    <PublicChrome marginRight={marginRight}>
      <main className="mx-auto w-full max-w-5xl flex-1 px-6 py-12 sm:px-8 lg:px-12">
        <Outlet />
      </main>
    </PublicChrome>
  )
}
