import { Outlet } from 'react-router-dom'
import type { ReactNode } from 'react'
import { PublicHeader } from './PublicHeader'
import { Footer } from './Footer'
import { useRightSidebarStore } from '../stores/rightSidebarStore'
import { useEffectiveSidebarMetrics } from '../hooks/useResizableSidebar'

/**
 * Layouts for standalone public pages (changelog, roadmap, pricing, shared
 * items). Split into shared chrome + two content variants so header/footer
 * stay single-sourced while the shared note/prompt routes get their own
 * content geometry (the ToC sidebar margin):
 *
 *   PublicChromeLayout            — PublicHeader + <Outlet/> + Footer
 *   ├─ PublicContentLayout        — standard centered main
 *   │    (changelog, roadmap, pricing, shared bookmarks — no ToC)
 *   └─ PublicSharedTocLayout      — sidebar-margined, then centered, main
 *        (shared notes and prompts — the ToC-capable pages)
 */

export function PublicChromeLayout(): ReactNode {
  return (
    <div className="flex min-h-screen flex-col bg-white">
      <PublicHeader />
      <Outlet />
      <Footer />
    </div>
  )
}

/** Standard centered content area, without a docs sidebar. */
export function PublicContentLayout(): ReactNode {
  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-6 py-12 sm:px-8 lg:px-12">
      <Outlet />
    </main>
  )
}

/**
 * Content area for the ToC-capable shared pages (notes/prompts). The sidebar
 * margin is applied to the full-width main BEFORE the max-w-5xl centering —
 * applying it inside an already-centered column can only squeeze that column
 * against its fixed left edge (at large sidebar widths content collapsed to
 * ~56px while real viewport space sat unused). Margin-then-center means the
 * content lays out in `viewport − sidebar`, whose 600px floor the sidebar's
 * own max-width math already guarantees (see computeMaxWidth).
 *
 * Scoping this layout to exactly the note/prompt shared routes (not shared
 * bookmarks, which have no ToC) makes the bookmark exclusion synchronous —
 * there is no margin logic on that route to flash before an effect cleans up.
 */
export function PublicSharedTocLayout(): ReactNode {
  const tocOpen = useRightSidebarStore((state) => state.activePanel === 'toc')
  const { effectiveWidth, isDesktop } = useEffectiveSidebarMetrics()
  // Desktop only: below the breakpoint the sidebar is a full-width overlay.
  const marginRight = tocOpen && isDesktop ? effectiveWidth : 0

  return (
    <main
      className="w-full flex-1 px-6 py-12 sm:px-8 lg:px-12"
      style={marginRight > 0 ? { marginRight } : undefined}
    >
      <div className="mx-auto w-full max-w-5xl">
        <Outlet />
      </div>
    </main>
  )
}
