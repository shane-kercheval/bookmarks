/**
 * Store for right sidebar panel state (history, table of contents).
 * Only one panel can be open at a time. Used by Layout to apply margin.
 */
import { create } from 'zustand'

export type SidebarPanel = 'history' | 'toc'

/** Default sidebar width in pixels */
export const DEFAULT_SIDEBAR_WIDTH = 400
export const MIN_SIDEBAR_WIDTH = 280
/** Minimum space reserved for content area (header buttons + padding) */
export const MIN_CONTENT_WIDTH = 600

/**
 * Largest the right sidebar may grow to, given the viewport and the current
 * left-sidebar width. Pure so it can be unit-tested without a DOM/window;
 * callers supply the measured values (see measureMaxSidebarWidth). Floored at
 * MIN_SIDEBAR_WIDTH so it never returns a negative or sub-minimum width on
 * narrow viewports.
 */
export function computeMaxWidth(innerWidth: number, leftSidebarWidth: number): number {
  return Math.max(MIN_SIDEBAR_WIDTH, innerWidth - leftSidebarWidth - MIN_CONTENT_WIDTH)
}

/**
 * The sidebar's effective rendered width on desktop: the live max when
 * maximized, otherwise the stored width clamped to it. Clamping here (not by
 * mutating the store) keeps the user's chosen width intact as the restore
 * target across viewport changes. Single-sourced because the sidebar itself,
 * the app layout's content margin, and the public shared-item layout must all
 * agree on this number.
 */
export function getEffectiveSidebarWidth(
  storeWidth: number,
  maximized: boolean,
  maxWidth: number,
): number {
  return maximized ? maxWidth : Math.min(storeWidth, maxWidth)
}

// Storage keys for persisting state
const WIDTH_STORAGE_KEY = 'right-sidebar-width'
const PANEL_STORAGE_KEY = 'right-sidebar-panel'
const MAXIMIZED_STORAGE_KEY = 'right-sidebar-maximized'

// Load initial width from localStorage
function getInitialWidth(): number {
  if (typeof window === 'undefined') return DEFAULT_SIDEBAR_WIDTH
  const stored = localStorage.getItem(WIDTH_STORAGE_KEY)
  if (stored) {
    const parsed = parseInt(stored, 10)
    if (!isNaN(parsed) && parsed >= MIN_SIDEBAR_WIDTH) {
      return parsed
    }
  }
  return DEFAULT_SIDEBAR_WIDTH
}

// Load initial panel from localStorage (only 'history' is persisted; 'toc' is session-only)
function getInitialPanel(): SidebarPanel | null {
  if (typeof window === 'undefined') return null
  const stored = localStorage.getItem(PANEL_STORAGE_KEY)
  if (stored === 'history') return stored
  return null
}

// Load initial maximized state from localStorage
function getInitialMaximized(): boolean {
  if (typeof window === 'undefined') return false
  return localStorage.getItem(MAXIMIZED_STORAGE_KEY) === 'true'
}

interface RightSidebarState {
  activePanel: SidebarPanel | null
  width: number
  /**
   * When true, the sidebar renders at its current maximum width instead of
   * `width`. `width` is preserved untouched as the restore target — toggling
   * off returns to it. A property of the sidebar shell, shared across panels.
   */
  maximized: boolean
  setActivePanel: (panel: SidebarPanel | null) => void
  togglePanel: (panel: SidebarPanel) => void
  setWidth: (width: number) => void
  setMaximized: (maximized: boolean) => void
  toggleMaximized: () => void
}

export const useRightSidebarStore = create<RightSidebarState>((set, get) => ({
  activePanel: getInitialPanel(),
  width: getInitialWidth(),
  maximized: getInitialMaximized(),
  setActivePanel: (panel) => {
    // Only persist 'history' to localStorage; 'toc' is session-only
    // (ToC requires specific page support and shouldn't restore on reload/navigation)
    try {
      localStorage.setItem(PANEL_STORAGE_KEY, panel === 'history' ? 'history' : '')
    } catch {
      // Ignore storage errors - in-memory state still updates
    }
    set({ activePanel: panel })
  },
  togglePanel: (panel) => {
    const current = get().activePanel
    const next = current === panel ? null : panel
    try {
      localStorage.setItem(PANEL_STORAGE_KEY, next === 'history' ? 'history' : '')
    } catch {
      // Ignore storage errors - in-memory state still updates
    }
    set({ activePanel: next })
  },
  setWidth: (width) => {
    const clampedWidth = Math.max(MIN_SIDEBAR_WIDTH, width)
    try {
      localStorage.setItem(WIDTH_STORAGE_KEY, String(clampedWidth))
    } catch {
      // Ignore storage errors - in-memory state still updates
    }
    set({ width: clampedWidth })
  },
  setMaximized: (maximized) => {
    try {
      localStorage.setItem(MAXIMIZED_STORAGE_KEY, String(maximized))
    } catch {
      // Ignore storage errors - in-memory state still updates
    }
    set({ maximized })
  },
  toggleMaximized: () => {
    get().setMaximized(!get().maximized)
  },
}))
