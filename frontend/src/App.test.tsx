import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

// Mock all modules that make network requests or have complex dependencies
vi.mock('./hooks/useBookmarks', () => ({
  useBookmarks: () => ({
    bookmarks: [],
    total: 0,
    isLoading: false,
    error: null,
    hasInitiallyLoaded: true,
    fetchBookmarks: vi.fn(),
    fetchBookmark: vi.fn(),
    createBookmark: vi.fn(),
    updateBookmark: vi.fn(),
    deleteBookmark: vi.fn(),
    restoreBookmark: vi.fn(),
    archiveBookmark: vi.fn(),
    unarchiveBookmark: vi.fn(),
    fetchMetadata: vi.fn(),
    trackBookmarkUsage: vi.fn(),
    clearError: vi.fn(),
  }),
}))

vi.mock('./hooks/useBookmarksQuery', () => ({
  useBookmarksQuery: () => ({
    data: { items: [], total: 0, offset: 0, limit: 20, has_more: false },
    isLoading: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
  }),
}))

vi.mock('./hooks/useBookmarkMutations', () => ({
  useCreateBookmark: () => ({ mutateAsync: vi.fn() }),
  useUpdateBookmark: () => ({ mutateAsync: vi.fn() }),
  useDeleteBookmark: () => ({ mutateAsync: vi.fn() }),
  useRestoreBookmark: () => ({ mutateAsync: vi.fn() }),
  useArchiveBookmark: () => ({ mutateAsync: vi.fn() }),
  useUnarchiveBookmark: () => ({ mutateAsync: vi.fn() }),
}))

vi.mock('./hooks/useNoteMutations', () => ({
  useCreateNote: () => ({ mutateAsync: vi.fn() }),
  useUpdateNote: () => ({ mutateAsync: vi.fn() }),
  useDeleteNote: () => ({ mutateAsync: vi.fn() }),
  useRestoreNote: () => ({ mutateAsync: vi.fn() }),
  useArchiveNote: () => ({ mutateAsync: vi.fn() }),
  useUnarchiveNote: () => ({ mutateAsync: vi.fn() }),
}))

vi.mock('./hooks/usePromptMutations', () => ({
  useCreatePrompt: () => ({ mutateAsync: vi.fn() }),
  useUpdatePrompt: () => ({ mutateAsync: vi.fn() }),
  useDeletePrompt: () => ({ mutateAsync: vi.fn() }),
  useRestorePrompt: () => ({ mutateAsync: vi.fn() }),
  useArchivePrompt: () => ({ mutateAsync: vi.fn() }),
  useUnarchivePrompt: () => ({ mutateAsync: vi.fn() }),
}))

vi.mock('./hooks/useContentQuery', () => ({
  useContentQuery: () => ({
    data: { items: [], total: 0, offset: 0, limit: 20, has_more: false },
    isLoading: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
  }),
}))

vi.mock('./stores/tagsStore', () => ({
  useTagsStore: (selector?: (state: Record<string, unknown>) => unknown) => {
    const state = {
      tags: [],
      isLoading: false,
      error: null,
      fetchTags: vi.fn(),
      clearError: vi.fn(),
    }
    return selector ? selector(state) : state
  },
}))

vi.mock('./stores/settingsStore', () => ({
  useSettingsStore: (selector?: (state: Record<string, unknown>) => unknown) => {
    const state = {
      sidebar: {
        version: 1,
        items: [
          { type: 'builtin', key: 'all', name: 'All Content' },
          { type: 'builtin', key: 'archived', name: 'Archived' },
          { type: 'builtin', key: 'trash', name: 'Trash' },
        ],
      },
      fetchSidebar: vi.fn(),
    }
    return selector ? selector(state) : state
  },
}))

vi.mock('./stores/sidebarStore', () => ({
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

vi.mock('./stores/filtersStore', () => ({
  useFiltersStore: (selector?: (state: Record<string, unknown>) => unknown) => {
    const state = {
      filters: [],
      isLoading: false,
      error: null,
      fetchFilters: vi.fn(),
      createFilter: vi.fn(),
      updateFilter: vi.fn(),
      deleteFilter: vi.fn(),
    }
    return selector ? selector(state) : state
  },
}))

// Mock the config module to control isDevMode
vi.mock('./config', () => ({
  config: {
    apiUrl: 'http://localhost:8000',
  },
  isDevMode: true,
}))

// Must import App AFTER mocks are set up
import App from './App'

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should render and redirect to content page in dev mode', async () => {
    render(<App />)

    // In dev mode, the landing page redirects to content
    // Wait for the redirect and content page to appear
    await waitFor(
      () => {
        expect(screen.getByPlaceholderText('Search All Content...')).toBeInTheDocument()
      },
      { timeout: 3000 }
    )
  })

  it('should show sidebar navigation items', async () => {
    render(<App />)

    await waitFor(
      () => {
        // Sidebar has "All Content" builtin navigation item
        expect(screen.getAllByText('All Content').length).toBeGreaterThanOrEqual(1)
      },
      { timeout: 3000 }
    )
  })

  it('should show quick-add menu', async () => {
    render(<App />)

    await waitFor(
      () => {
        // Quick-add menu trigger button
        expect(screen.getByTestId('quick-add-menu-trigger')).toBeInTheDocument()
      },
      { timeout: 3000 }
    )
  })

  it('should show empty state when no content exists', async () => {
    render(<App />)

    await waitFor(
      () => {
        expect(screen.getByText('No content yet')).toBeInTheDocument()
      },
      { timeout: 3000 }
    )
  })
})
