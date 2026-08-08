import { useState, useEffect, useRef, useCallback, Suspense } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import type { CSSProperties, ReactNode } from 'react'
import { Sidebar } from './sidebar'
import { ShortcutsDialog } from './ShortcutsDialog'
import { CommandPalette } from './CommandPalette'
import { Footer } from './Footer'
import { ContentAreaSpinner } from './ui'
import { useUIPreferencesStore } from '../stores/uiPreferencesStore'
import { useSidebarStore } from '../stores/sidebarStore'
import { useSettingsStore } from '../stores/settingsStore'
import { useFiltersStore } from '../stores/filtersStore'
import { useTagsStore } from '../stores/tagsStore'
import { useRightSidebarStore, getEffectiveSidebarWidth } from '../stores/rightSidebarStore'
import { useGlobalShortcuts } from '../shortcuts/useGlobalShortcuts'
import type { ShortcutId } from '../shortcuts/registry'
import { useLimits } from '../hooks/useLimits'
import { measureMaxSidebarWidth } from '../hooks/useResizableSidebar'
import { DESKTOP_SIDEBAR_ID } from '../constants/sidebar'

/**
 * Layout component that wraps authenticated pages.
 * Includes sidebar with navigation and user controls.
 *
 * Responsibilities:
 * - Fetch shared data (sidebar, filters, tags) once on mount
 * - Render sidebar and main content area
 * - Handle global keyboard shortcuts
 * - Render command palette overlay
 *
 * Renders under AppLayout, which is now a pass-through — see that component for
 * why the nesting level still exists.
 */
/** Tailwind md breakpoint */
const MD_BREAKPOINT = 768

const APP_GLOBAL_IDS = [
  'app.showShortcuts',
  'app.commandPalette',
  'app.toggleSidebar',
  'app.toggleHistorySidebar',
  'app.toggleSidebarMaxWidth',
  'app.toggleWidth',
  'app.focusSearch',
  'app.escape',
] as const satisfies readonly ShortcutId[]

export function Layout(): ReactNode {
  // Prefetch limits so detail pages don't wait for a sequential fetch.
  useLimits()
  const fullWidthLayout = useUIPreferencesStore((state) => state.fullWidthLayout)
  const toggleFullWidthLayout = useUIPreferencesStore((state) => state.toggleFullWidthLayout)
  const toggleSidebar = useSidebarStore((state) => state.toggleCollapse)
  const fetchSidebar = useSettingsStore((state) => state.fetchSidebar)
  const fetchFilters = useFiltersStore((state) => state.fetchFilters)
  const fetchTags = useTagsStore((state) => state.fetchTags)
  const [showShortcuts, setShowShortcuts] = useState(false)
  const [isDesktop, setIsDesktop] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth >= MD_BREAKPOINT : true
  )
  const location = useLocation()
  const showFooter = location.pathname.startsWith('/app/settings')
  // Right sidebar only renders on detail pages (e.g., /app/notes/abc-123), not create pages
  const isDetailPage = /^\/app\/(bookmarks|notes|prompts)\/(?!new$)[^/]+$/.test(location.pathname)
  const hasFetchedRef = useRef(false)
  const rightSidebarOpen = useRightSidebarStore((state) => state.activePanel !== null)
  const rightSidebarWidth = useRightSidebarStore((state) => state.width)
  const rightSidebarMaximized = useRightSidebarStore((state) => state.maximized)
  const toggleSidebarMaximized = useRightSidebarStore((state) => state.toggleMaximized)

  // Command palette state
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [paletteInitialView, setPaletteInitialView] = useState<'commands' | 'search'>('commands')

  const openPalette = useCallback((view: 'commands' | 'search') => {
    setPaletteInitialView(view)
    setPaletteOpen(true)
  }, [])

  const closePalette = useCallback(() => {
    setPaletteOpen(false)
  }, [])

  // Fetch shared data once on mount (used by Sidebar and child pages).
  // `hasFetchedRef` (not state) prevents re-fetching on subsequent re-renders.
  // No readiness gate is needed: this component renders under ProtectedRoute,
  // which withholds its Outlet until auth has resolved.
  useEffect(() => {
    if (!hasFetchedRef.current) {
      hasFetchedRef.current = true
      fetchSidebar()
      fetchFilters()
      fetchTags()
    }
  }, [fetchSidebar, fetchFilters, fetchTags])

  // Track viewport size for responsive behavior and to recalculate sidebar margin
  const [, setResizeCount] = useState(0)
  useEffect(() => {
    const handleResize = (): void => {
      setIsDesktop(window.innerWidth >= MD_BREAKPOINT)
      // Force re-render to recalculate history sidebar margin
      if (rightSidebarOpen) {
        setResizeCount((c) => c + 1)
      }
    }
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [rightSidebarOpen])

  // Recompute the right-sidebar margin when the left sidebar's width changes.
  // Collapsing/expanding it animates (w-12 ↔ w-72), and the margin depends on
  // that width (see getRightSidebarMargin). A ResizeObserver tracks the live
  // width across the transition — a state subscription would re-render once at
  // the animation's start and read the stale pre-transition width. Keeping the
  // margin in sync also keeps the Cmd+F search panel offset correct, since it
  // reads the --right-sidebar-margin variable set below.
  useEffect(() => {
    if (!rightSidebarOpen) return
    const leftSidebar = document.getElementById(DESKTOP_SIDEBAR_ID)
    if (!leftSidebar) return
    // Guard for environments without ResizeObserver (matches DropdownPortal);
    // the window-resize handler above remains the fallback for margin recompute.
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(() => setResizeCount((c) => c + 1))
    observer.observe(leftSidebar)
    return () => observer.disconnect()
  }, [rightSidebarOpen])

  const togglePanel = useRightSidebarStore((state) => state.togglePanel)

  // Global keyboard shortcuts (work on all pages).
  //
  // Handlers below close over render-time state (`showShortcuts`,
  // `isDetailPage`). useGlobalShortcuts reads handlers through a ref, so
  // each event runs the LATEST closure — not the mount-time one. This means
  // a state change re-renders Layout, the ref updates, and the next keypress
  // sees the new value. Don't memoize handlers thinking it's required.
  //
  // Conditional handlers (toggleHistorySidebar) stay in the tuple
  // unconditionally and short-circuit when the precondition fails — the tuple
  // is a stable contract between consumer and registry.
  useGlobalShortcuts(APP_GLOBAL_IDS, {
    'app.showShortcuts': () => setShowShortcuts(true),
    'app.toggleSidebar': toggleSidebar,
    'app.toggleWidth': toggleFullWidthLayout,
    'app.focusSearch': () => openPalette('search'),
    'app.commandPalette': () => openPalette('commands'),
    'app.toggleHistorySidebar': () => {
      if (!isDetailPage) return
      togglePanel('history')
    },
    'app.toggleSidebarMaxWidth': () => {
      // Desktop-only, mirroring the button: on mobile the sidebar is full-width
      // and maximize has no visible effect, so toggling would silently mutate
      // the persisted flag and surprise the user on their next desktop session.
      if (!isDetailPage || !rightSidebarOpen || !isDesktop) return
      toggleSidebarMaximized()
    },
    'app.escape': () => {
      if (showShortcuts) setShowShortcuts(false)
    },
  })

  // Calculate constrained margin for right sidebar
  // Uses the same logic as sidebar components to ensure they stay in sync
  const getRightSidebarMargin = (): number => {
    if (!rightSidebarOpen || !isDesktop || !isDetailPage) return 0
    // Shared clamp/maximize math so margin and sidebar width agree.
    return getEffectiveSidebarWidth(rightSidebarWidth, rightSidebarMaximized, measureMaxSidebarWidth())
  }

  // Single source of truth for the content offset. Exposed as a CSS variable so
  // the CodeMirror search panel (position: fixed) can offset by the same amount
  // and shift with the content instead of hiding behind the right sidebar.
  const rightSidebarMargin = getRightSidebarMargin()

  return (
    <div data-viewport-locked className="flex h-dvh bg-white overflow-hidden">
      <Sidebar onOpenPalette={() => openPalette('commands')} />
      {/* Note: id="main-content" is used by SaveOverlay.tsx for portal rendering */}
      <main
        id="main-content"
        className="flex-1 flex flex-col min-w-0 relative overflow-x-hidden transition-[margin] duration-200"
        style={{ marginRight: `${rightSidebarMargin}px`, '--right-sidebar-margin': `${rightSidebarMargin}px` } as CSSProperties}
      >
        <div className="flex-1 overflow-y-auto overflow-x-hidden relative">
          <div className={`flex flex-col min-h-0 px-4 pb-4 md:px-5 ${fullWidthLayout ? 'max-w-full' : 'max-w-5xl'}`}>
            <Suspense fallback={<ContentAreaSpinner />}><Outlet /></Suspense>
          </div>
        </div>
        {showFooter && <Footer />}
      </main>
      <ShortcutsDialog isOpen={showShortcuts} onClose={() => setShowShortcuts(false)} />
      <CommandPalette isOpen={paletteOpen} initialView={paletteInitialView} onClose={closePalette} onShowShortcuts={() => setShowShortcuts(true)} />
    </div>
  )
}
