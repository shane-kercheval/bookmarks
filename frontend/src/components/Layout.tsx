import { useState, useEffect, useRef } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import type { ReactNode } from 'react'
import { Sidebar } from './sidebar'
import { ShortcutsDialog } from './ShortcutsDialog'
import { Footer } from './Footer'
import { useUIPreferencesStore } from '../stores/uiPreferencesStore'
import { useSidebarStore } from '../stores/sidebarStore'
import { useSettingsStore } from '../stores/settingsStore'
import { useListsStore } from '../stores/listsStore'
import { useTagsStore } from '../stores/tagsStore'
import { useKeyboardShortcuts } from '../hooks/useKeyboardShortcuts'

/**
 * Layout component that wraps authenticated pages.
 * Includes sidebar with navigation and user controls.
 *
 * Responsibilities:
 * - Fetch shared data (tab order, lists, tags) once on mount
 * - Render sidebar and main content area
 * - Handle global keyboard shortcuts
 */
export function Layout(): ReactNode {
  const fullWidthLayout = useUIPreferencesStore((state) => state.fullWidthLayout)
  const toggleFullWidthLayout = useUIPreferencesStore((state) => state.toggleFullWidthLayout)
  const toggleSidebar = useSidebarStore((state) => state.toggleCollapse)
  const fetchTabOrder = useSettingsStore((state) => state.fetchTabOrder)
  const fetchLists = useListsStore((state) => state.fetchLists)
  const fetchTags = useTagsStore((state) => state.fetchTags)
  const [showShortcuts, setShowShortcuts] = useState(false)
  const location = useLocation()
  const showFooter = location.pathname.startsWith('/app/settings')
  const hasFetchedRef = useRef(false)

  // Fetch shared data once on mount (used by Sidebar and child pages)
  useEffect(() => {
    if (!hasFetchedRef.current) {
      hasFetchedRef.current = true
      fetchTabOrder()
      fetchLists()
      fetchTags()
    }
  }, [fetchTabOrder, fetchLists, fetchTags])

  // Global keyboard shortcuts (work on all pages)
  useKeyboardShortcuts({
    onShowShortcuts: () => setShowShortcuts(true),
    onToggleSidebar: toggleSidebar,
    onToggleWidth: toggleFullWidthLayout,
    onEscape: () => {
      if (showShortcuts) setShowShortcuts(false)
    },
  })

  return (
    <div className="flex min-h-screen bg-white">
      <Sidebar />
      <main className="flex-1 overflow-auto flex flex-col">
        <div className={`flex-1 px-6 py-8 md:px-10 ${fullWidthLayout ? '' : 'max-w-5xl'}`}>
          <Outlet />
        </div>
        {showFooter && <Footer />}
      </main>
      <ShortcutsDialog isOpen={showShortcuts} onClose={() => setShowShortcuts(false)} />
    </div>
  )
}
