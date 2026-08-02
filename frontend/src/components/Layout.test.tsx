/**
 * Tests for the Layout component.
 *
 * Key behavior: Layout fetches shared data (sidebar, filters, tags) exactly once on mount.
 * This centralized fetching prevents duplicate API calls from child components.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { ReactNode } from 'react'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { Layout } from './Layout'
import * as config from '../config'

// Mock useLimits - track calls to verify prefetch behavior
const mockUseLimits = vi.fn().mockReturnValue({
  limits: undefined,
  isLoading: false,
  error: null,
})

vi.mock('../hooks/useLimits', () => ({
  useLimits: (...args: unknown[]) => mockUseLimits(...args),
}))

// Mock the config module
vi.mock('../config', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../config')>()
  return {
    ...actual,
    isDevMode: true,
  }
})

// Create mock functions that we can spy on
const mockFetchSidebar = vi.fn()
const mockFetchFilters = vi.fn()
const mockFetchTags = vi.fn()

vi.mock('../stores/settingsStore', () => ({
  useSettingsStore: (selector?: (state: Record<string, unknown>) => unknown) => {
    const state = {
      sidebar: {
        version: 1,
        items: [
          { type: 'builtin', key: 'all', name: 'All Content' },
          { type: 'builtin', key: 'archived', name: 'Archived' },
          { type: 'builtin', key: 'trash', name: 'Trash' },
          { type: 'filter', id: 1, name: 'My Filter', content_types: ['bookmark', 'note'] },
        ],
      },
      fetchSidebar: mockFetchSidebar,
    }
    return selector ? selector(state) : state
  },
}))

vi.mock('../stores/filtersStore', () => ({
  useFiltersStore: (selector?: (state: Record<string, unknown>) => unknown) => {
    const state = {
      filters: [],
      fetchFilters: mockFetchFilters,
    }
    return selector ? selector(state) : state
  },
}))

vi.mock('../stores/tagsStore', () => ({
  useTagsStore: (selector?: (state: Record<string, unknown>) => unknown) => {
    const state = {
      tags: [],
      fetchTags: mockFetchTags,
    }
    return selector ? selector(state) : state
  },
}))

vi.mock('../stores/uiPreferencesStore', () => ({
  useUIPreferencesStore: (selector?: (state: Record<string, unknown>) => unknown) => {
    const state = {
      fullWidthLayout: false,
      toggleFullWidthLayout: vi.fn(),
    }
    return selector ? selector(state) : state
  },
}))

vi.mock('../stores/sidebarStore', () => ({
  useSidebarStore: (selector?: (state: Record<string, unknown>) => unknown) => {
    const state = {
      isCollapsed: false,
      isMobileOpen: false,
      expandedSections: ['settings'],
      collapsedGroupIds: [],
      toggleCollapse: vi.fn(),
      toggleMobile: vi.fn(),
      closeMobile: vi.fn(),
      toggleSection: vi.fn(),
      toggleGroup: vi.fn(),
      isGroupCollapsed: () => false,
    }
    return selector ? selector(state) : state
  },
}))

// Track right sidebar state for tests
let mockActivePanel: string | null = null
let mockMaximized = false
const mockRightSidebarWidth = 384
const mockToggleMaximized = vi.fn()
vi.mock('../stores/rightSidebarStore', () => ({
  useRightSidebarStore: (selector?: (state: Record<string, unknown>) => unknown) => {
    const state = {
      activePanel: mockActivePanel,
      width: mockRightSidebarWidth,
      maximized: mockMaximized,
      setActivePanel: vi.fn(),
      togglePanel: vi.fn(),
      setWidth: vi.fn(),
      setMaximized: vi.fn(),
      toggleMaximized: mockToggleMaximized,
    }
    return selector ? selector(state) : state
  },
  MIN_SIDEBAR_WIDTH: 280,
  MIN_CONTENT_WIDTH: 600,
  // Used by measureMaxSidebarWidth (via Layout's getRightSidebarMargin).
  computeMaxWidth: (innerWidth: number, leftSidebarWidth: number) =>
    Math.max(280, innerWidth - leftSidebarWidth - 600),
}))

function setWindowWidth(width: number): void {
  Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: width })
}

/** Dispatch the ⌘⌥\ (maximize sidebar) shortcut as a real keydown on document. */
function pressMaximizeShortcut(): void {
  document.dispatchEvent(
    new KeyboardEvent('keydown', { metaKey: true, altKey: true, code: 'Backslash', bubbles: true }),
  )
}

function TestPage(): ReactNode {
  return <div data-testid="test-page">Test Page Content</div>
}

function renderLayout(route = '/app/bookmarks'): void {
  render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/app/bookmarks" element={<TestPage />} />
          <Route path="/app/notes/:id" element={<TestPage />} />
        </Route>
      </Routes>
    </MemoryRouter>
  )
}

describe('Layout', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockActivePanel = null
    mockMaximized = false
    setWindowWidth(1024) // desktop by default
    vi.mocked(config).isDevMode = true
  })

  describe('centralized data fetching', () => {
    it('should fetch sidebar exactly once on mount', () => {
      renderLayout()

      expect(mockFetchSidebar).toHaveBeenCalledTimes(1)
    })

    it('should fetch filters exactly once on mount', () => {
      renderLayout()

      expect(mockFetchFilters).toHaveBeenCalledTimes(1)
    })

    it('should fetch tags exactly once on mount', () => {
      renderLayout()

      expect(mockFetchTags).toHaveBeenCalledTimes(1)
    })

    it('should fetch all shared data in a single mount cycle', () => {
      renderLayout()

      // All three should be called exactly once
      expect(mockFetchSidebar).toHaveBeenCalledTimes(1)
      expect(mockFetchFilters).toHaveBeenCalledTimes(1)
      expect(mockFetchTags).toHaveBeenCalledTimes(1)
    })
  })

  describe('rendering', () => {
    it('should render child routes via Outlet', () => {
      renderLayout()

      expect(screen.getByTestId('test-page')).toBeInTheDocument()
    })

    it('should render the sidebar with navigation items', () => {
      renderLayout()

      // Sidebar contains the builtin "All Content" item (appears in both mobile and desktop sidebars)
      expect(screen.getAllByText('All Content').length).toBeGreaterThanOrEqual(1)
    })
  })

  describe('shared-data fetching', () => {
    it('fetches sidebar, filters, and tags once on mount', () => {
      // No readiness gate since the consent gate was removed (2026-08-01):
      // Layout renders under ProtectedRoute, which withholds its Outlet until
      // auth resolves, so there is nothing further to wait for.
      renderLayout()

      expect(mockFetchSidebar).toHaveBeenCalledTimes(1)
      expect(mockFetchFilters).toHaveBeenCalledTimes(1)
      expect(mockFetchTags).toHaveBeenCalledTimes(1)
    })
  })

  describe('limits prefetching', () => {
    it('prefetches tier limits so detail pages do not wait on a sequential fetch', () => {
      renderLayout()

      expect(mockUseLimits).toHaveBeenCalledWith()
    })
  })

  describe('right sidebar margin', () => {
    it('should not apply margin when sidebar is closed', () => {
      mockActivePanel = null
      renderLayout('/app/notes/abc-123')

      const main = screen.getByRole('main')
      expect(main.style.marginRight).toBe('0px')
    })

    it('should apply margin when sidebar is open on detail page', () => {
      mockActivePanel = 'history'
      renderLayout('/app/notes/abc-123')

      const main = screen.getByRole('main')
      expect(main.style.marginRight).toBe(`${mockRightSidebarWidth}px`)
    })

    it('should not apply margin on non-detail pages even when sidebar is open', () => {
      mockActivePanel = 'history'
      renderLayout('/app/bookmarks')

      const main = screen.getByRole('main')
      expect(main.style.marginRight).toBe('0px')
    })

    // The CodeMirror Cmd+F search panel (position: fixed) offsets its `right`
    // by --right-sidebar-margin so it shifts with the content instead of
    // hiding behind the sidebar. The variable must always equal marginRight.
    it('should expose the margin as the --right-sidebar-margin variable when open', () => {
      mockActivePanel = 'history'
      renderLayout('/app/notes/abc-123')

      const main = screen.getByRole('main')
      expect(main.style.getPropertyValue('--right-sidebar-margin')).toBe(`${mockRightSidebarWidth}px`)
      expect(main.style.getPropertyValue('--right-sidebar-margin')).toBe(main.style.marginRight)
    })

    it('should set --right-sidebar-margin to 0px when sidebar is closed', () => {
      mockActivePanel = null
      renderLayout('/app/notes/abc-123')

      const main = screen.getByRole('main')
      expect(main.style.getPropertyValue('--right-sidebar-margin')).toBe('0px')
    })

    it('should apply the max width as margin when maximized, ignoring the smaller stored width', () => {
      // jsdom: innerWidth 1024, no measurable left sidebar → max = 1024 - 0 - 600 = 424,
      // larger than the stored width (384), so maximize widens the margin.
      mockActivePanel = 'history'
      mockMaximized = true
      renderLayout('/app/notes/abc-123')

      const main = screen.getByRole('main')
      expect(main.style.marginRight).toBe('424px')
      expect(main.style.getPropertyValue('--right-sidebar-margin')).toBe('424px')
    })
  })

  describe('maximize shortcut (⌘⌥\\)', () => {
    it('toggles maximize on a detail page with a panel open (desktop)', () => {
      mockActivePanel = 'history'
      renderLayout('/app/notes/abc-123')

      pressMaximizeShortcut()

      expect(mockToggleMaximized).toHaveBeenCalledTimes(1)
    })

    it('is a no-op on mobile, so it cannot silently flip the persisted flag', () => {
      setWindowWidth(600) // below the md breakpoint
      mockActivePanel = 'history'
      renderLayout('/app/notes/abc-123')

      pressMaximizeShortcut()

      expect(mockToggleMaximized).not.toHaveBeenCalled()
    })

    it('is a no-op when no sidebar panel is open', () => {
      mockActivePanel = null
      renderLayout('/app/notes/abc-123')

      pressMaximizeShortcut()

      expect(mockToggleMaximized).not.toHaveBeenCalled()
    })

    it('is a no-op on non-detail pages', () => {
      mockActivePanel = 'history'
      renderLayout('/app/bookmarks')

      pressMaximizeShortcut()

      expect(mockToggleMaximized).not.toHaveBeenCalled()
    })
  })
})
