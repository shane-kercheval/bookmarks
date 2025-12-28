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
      computedTabOrder: [
        { key: 'all', label: 'All', type: 'builtin' },
        { key: 'archived', label: 'Archived', type: 'builtin' },
        { key: 'trash', label: 'Trash', type: 'builtin' },
        { key: 'all-bookmarks', label: 'All Bookmarks', type: 'builtin' },
        { key: 'all-notes', label: 'All Notes', type: 'builtin' },
      ],
      computedSections: [
        {
          name: 'shared',
          label: 'Shared',
          items: [
            { key: 'all', label: 'All', type: 'builtin' },
            { key: 'archived', label: 'Archived', type: 'builtin' },
            { key: 'trash', label: 'Trash', type: 'builtin' },
          ],
          collapsible: false,
        },
        {
          name: 'bookmarks',
          label: 'Bookmarks',
          items: [{ key: 'all-bookmarks', label: 'All Bookmarks', type: 'builtin' }],
          collapsible: true,
        },
        {
          name: 'notes',
          label: 'Notes',
          items: [{ key: 'all-notes', label: 'All Notes', type: 'builtin' }],
          collapsible: true,
        },
      ],
      sectionOrder: ['shared', 'bookmarks', 'notes'],
      fetchTabOrder: vi.fn(),
    }
    return selector ? selector(state) : state
  },
}))

vi.mock('./stores/listsStore', () => ({
  useListsStore: (selector?: (state: Record<string, unknown>) => unknown) => {
    const state = {
      lists: [],
      isLoading: false,
      error: null,
      fetchLists: vi.fn(),
      createList: vi.fn(),
      updateList: vi.fn(),
      deleteList: vi.fn(),
    }
    return selector ? selector(state) : state
  },
}))

// Mock the config module to control isDevMode
vi.mock('./config', () => ({
  config: {
    apiUrl: 'http://localhost:8000',
    auth0: {
      domain: '',
      clientId: '',
      audience: '',
    },
  },
  isDevMode: true,
}))

// Must import App AFTER mocks are set up
import App from './App'

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should render and redirect to bookmarks page in dev mode', async () => {
    render(<App />)

    // In dev mode, the landing page redirects to bookmarks
    // Wait for the redirect and bookmarks content to appear
    await waitFor(
      () => {
        expect(screen.getByPlaceholderText('Search bookmarks...')).toBeInTheDocument()
      },
      { timeout: 3000 }
    )
  })

  it('should show dev user indicator in dev mode', async () => {
    render(<App />)

    await waitFor(
      () => {
        // Dev User badge appears in sidebar user section
        const devUserElements = screen.getAllByText(/Dev User/i)
        expect(devUserElements.length).toBeGreaterThanOrEqual(1)
      },
      { timeout: 3000 }
    )
  })

  it('should show Bookmarks section in sidebar', async () => {
    render(<App />)

    await waitFor(
      () => {
        // Sidebar has "Bookmarks" as a section header button
        expect(screen.getAllByText('Bookmarks').length).toBeGreaterThanOrEqual(1)
      },
      { timeout: 3000 }
    )
  })

  it('should show Add Bookmark button in header', async () => {
    render(<App />)

    await waitFor(
      () => {
        // There are two "Add Bookmark" buttons - one in header and one in empty state
        const buttons = screen.getAllByText('Add Bookmark')
        expect(buttons.length).toBeGreaterThanOrEqual(1)
      },
      { timeout: 3000 }
    )
  })

  it('should show empty state when no bookmarks exist', async () => {
    render(<App />)

    await waitFor(
      () => {
        expect(screen.getByText('No bookmarks yet')).toBeInTheDocument()
      },
      { timeout: 3000 }
    )
  })
})
