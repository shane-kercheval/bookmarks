/**
 * Tests for the Layout component.
 *
 * Key behavior: Layout fetches shared data (tab order, lists, tags) exactly once on mount.
 * This centralized fetching prevents duplicate API calls from child components.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { ReactNode } from 'react'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { Layout } from './Layout'

// Create mock functions that we can spy on
const mockFetchTabOrder = vi.fn()
const mockFetchLists = vi.fn()
const mockFetchTags = vi.fn()

vi.mock('../stores/settingsStore', () => ({
  useSettingsStore: (selector?: (state: Record<string, unknown>) => unknown) => {
    const state = {
      computedTabOrder: [
        { key: 'all', label: 'All Bookmarks', type: 'builtin' },
      ],
      fetchTabOrder: mockFetchTabOrder,
    }
    return selector ? selector(state) : state
  },
}))

vi.mock('../stores/listsStore', () => ({
  useListsStore: (selector?: (state: Record<string, unknown>) => unknown) => {
    const state = {
      lists: [],
      fetchLists: mockFetchLists,
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
      expandedSections: ['bookmarks'],
      toggleCollapse: vi.fn(),
      toggleMobile: vi.fn(),
      closeMobile: vi.fn(),
      toggleSection: vi.fn(),
    }
    return selector ? selector(state) : state
  },
}))

function TestPage(): ReactNode {
  return <div data-testid="test-page">Test Page Content</div>
}

function renderLayout(): void {
  render(
    <MemoryRouter initialEntries={['/app/bookmarks']}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/app/bookmarks" element={<TestPage />} />
        </Route>
      </Routes>
    </MemoryRouter>
  )
}

describe('Layout', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('centralized data fetching', () => {
    it('should fetch tab order exactly once on mount', () => {
      renderLayout()

      expect(mockFetchTabOrder).toHaveBeenCalledTimes(1)
    })

    it('should fetch lists exactly once on mount', () => {
      renderLayout()

      expect(mockFetchLists).toHaveBeenCalledTimes(1)
    })

    it('should fetch tags exactly once on mount', () => {
      renderLayout()

      expect(mockFetchTags).toHaveBeenCalledTimes(1)
    })

    it('should fetch all shared data in a single mount cycle', () => {
      renderLayout()

      // All three should be called exactly once
      expect(mockFetchTabOrder).toHaveBeenCalledTimes(1)
      expect(mockFetchLists).toHaveBeenCalledTimes(1)
      expect(mockFetchTags).toHaveBeenCalledTimes(1)
    })
  })

  describe('rendering', () => {
    it('should render child routes via Outlet', () => {
      renderLayout()

      expect(screen.getByTestId('test-page')).toBeInTheDocument()
    })

    it('should render the sidebar', () => {
      renderLayout()

      // Sidebar contains the Bookmarks section (appears in both mobile and desktop sidebars)
      expect(screen.getAllByText('Bookmarks').length).toBeGreaterThanOrEqual(1)
    })
  })
})
