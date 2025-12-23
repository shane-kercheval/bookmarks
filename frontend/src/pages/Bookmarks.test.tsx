/**
 * Tests for Bookmarks page sort functionality.
 *
 * Tests the sort dropdown options, override indicator, and reset behavior.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { Bookmarks } from './Bookmarks'
import { SORT_LABELS, BASE_SORT_OPTIONS } from '../constants/sortOptions'

// Mock toast
vi.mock('react-hot-toast', () => ({
  default: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

// Mock all the hooks used by Bookmarks
const mockSetSort = vi.fn()
const mockClearOverride = vi.fn()

vi.mock('../hooks/useBookmarks', () => ({
  useBookmarks: () => ({
    bookmarks: [],
    total: 0,
    isLoading: false,
    hasMore: false,
    error: null,
    fetchBookmarks: vi.fn(),
    fetchMore: vi.fn(),
    createBookmark: vi.fn(),
    updateBookmark: vi.fn(),
    deleteBookmark: vi.fn(),
    archiveBookmark: vi.fn(),
    unarchiveBookmark: vi.fn(),
    restoreBookmark: vi.fn(),
    fetchMetadata: vi.fn(),
    trackUsage: vi.fn(),
  }),
}))

vi.mock('../hooks/useKeyboardShortcuts', () => ({
  useKeyboardShortcuts: () => {},
}))

vi.mock('../hooks/useDebouncedValue', () => ({
  useDebouncedValue: (value: string) => value,
}))

vi.mock('../hooks/useBookmarkView', () => ({
  useBookmarkView: () => ({
    currentView: 'active',
    currentListId: null,
    currentList: null,
  }),
}))

vi.mock('../hooks/useBookmarkUrlParams', () => ({
  useBookmarkUrlParams: () => ({
    searchQuery: '',
    offset: 0,
    updateParams: vi.fn(),
  }),
}))

// This mock needs to be configurable per test
let mockEffectiveSort = {
  sortBy: 'last_used_at' as const,
  sortOrder: 'desc' as const,
  setSort: mockSetSort,
  isOverridden: false,
  clearOverride: mockClearOverride,
  availableSortOptions: BASE_SORT_OPTIONS,
}

vi.mock('../hooks/useEffectiveSort', () => ({
  useEffectiveSort: () => mockEffectiveSort,
  getViewKey: (view: string, listId: number | null) => listId ? `list:${listId}` : view === 'active' ? 'all' : view,
}))

vi.mock('../stores/tagsStore', () => ({
  useTagsStore: () => ({
    tags: [],
    fetchTags: vi.fn(),
  }),
}))

vi.mock('../stores/listsStore', () => ({
  useListsStore: () => ({
    lists: [],
    isLoading: false,
    fetchLists: vi.fn(),
  }),
}))

vi.mock('../stores/tagFilterStore', () => ({
  useTagFilterStore: () => ({
    selectedTags: [],
    tagMatch: 'all',
    setSelectedTags: vi.fn(),
    setTagMatch: vi.fn(),
    addTag: vi.fn(),
    removeTag: vi.fn(),
    clearTags: vi.fn(),
  }),
}))

// Helper to render Bookmarks with router
function renderWithRouter(initialRoute: string = '/app/bookmarks'): void {
  render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <Routes>
        <Route path="/app/bookmarks" element={<Bookmarks />} />
        <Route path="/app/bookmarks/archived" element={<Bookmarks />} />
        <Route path="/app/bookmarks/trash" element={<Bookmarks />} />
        <Route path="/app/bookmarks/lists/:listId" element={<Bookmarks />} />
      </Routes>
    </MemoryRouter>
  )
}

describe('Bookmarks page sort functionality', () => {
  beforeEach(() => {
    vi.clearAllMocks()

    // Reset to default sort state
    mockEffectiveSort = {
      sortBy: 'last_used_at',
      sortOrder: 'desc',
      setSort: mockSetSort,
      isOverridden: false,
      clearOverride: mockClearOverride,
      availableSortOptions: BASE_SORT_OPTIONS,
    }
  })

  describe('sort dropdown options', () => {
    it('should render sort dropdown', async () => {
      renderWithRouter('/app/bookmarks')

      await waitFor(() => {
        const sortDropdown = document.querySelector('select')
        expect(sortDropdown).toBeInTheDocument()
      })
    })

    it('should show base sort options', async () => {
      renderWithRouter('/app/bookmarks')

      await waitFor(() => {
        const sortDropdown = document.querySelector('select')
        expect(sortDropdown).toBeInTheDocument()
      })

      // Check base options are present (both ascending and descending)
      for (const option of BASE_SORT_OPTIONS) {
        expect(screen.getByText(`${SORT_LABELS[option]} ↓`)).toBeInTheDocument()
        expect(screen.getByText(`${SORT_LABELS[option]} ↑`)).toBeInTheDocument()
      }
    })

    it('should show archived_at option when available', async () => {
      mockEffectiveSort = {
        ...mockEffectiveSort,
        sortBy: 'archived_at',
        availableSortOptions: [...BASE_SORT_OPTIONS, 'archived_at'],
      }

      renderWithRouter('/app/bookmarks/archived')

      await waitFor(() => {
        expect(screen.getByText('Archived At ↓')).toBeInTheDocument()
        expect(screen.getByText('Archived At ↑')).toBeInTheDocument()
      })
    })

    it('should show deleted_at option when available', async () => {
      mockEffectiveSort = {
        ...mockEffectiveSort,
        sortBy: 'deleted_at',
        availableSortOptions: [...BASE_SORT_OPTIONS, 'deleted_at'],
      }

      renderWithRouter('/app/bookmarks/trash')

      await waitFor(() => {
        expect(screen.getByText('Deleted At ↓')).toBeInTheDocument()
        expect(screen.getByText('Deleted At ↑')).toBeInTheDocument()
      })
    })

    it('should not show archived_at when not in availableSortOptions', async () => {
      renderWithRouter('/app/bookmarks')

      await waitFor(() => {
        const sortDropdown = document.querySelector('select')
        expect(sortDropdown).toBeInTheDocument()
      })

      expect(screen.queryByText('Archived At ↓')).not.toBeInTheDocument()
    })

    it('should not show deleted_at when not in availableSortOptions', async () => {
      renderWithRouter('/app/bookmarks')

      await waitFor(() => {
        const sortDropdown = document.querySelector('select')
        expect(sortDropdown).toBeInTheDocument()
      })

      expect(screen.queryByText('Deleted At ↓')).not.toBeInTheDocument()
    })
  })

  describe('override indicator', () => {
    it('should not show Reset button when using default sort', async () => {
      mockEffectiveSort = {
        ...mockEffectiveSort,
        isOverridden: false,
      }

      renderWithRouter('/app/bookmarks')

      await waitFor(() => {
        const sortDropdown = document.querySelector('select')
        expect(sortDropdown).toBeInTheDocument()
      })

      // Reset button should not be visible
      expect(screen.queryByRole('button', { name: /reset/i })).not.toBeInTheDocument()
    })

    it('should show Reset button when sort is overridden', async () => {
      mockEffectiveSort = {
        ...mockEffectiveSort,
        sortBy: 'created_at',
        sortOrder: 'asc',
        isOverridden: true,
      }

      renderWithRouter('/app/bookmarks')

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /reset/i })).toBeInTheDocument()
      })
    })

    it('should have correct title on Reset button', async () => {
      mockEffectiveSort = {
        ...mockEffectiveSort,
        isOverridden: true,
      }

      renderWithRouter('/app/bookmarks')

      await waitFor(() => {
        const resetButton = screen.getByRole('button', { name: /reset/i })
        expect(resetButton).toHaveAttribute('title', 'Reset to default sort')
      })
    })

    it('should call clearOverride when Reset is clicked', async () => {
      const user = userEvent.setup()

      mockEffectiveSort = {
        ...mockEffectiveSort,
        isOverridden: true,
      }

      renderWithRouter('/app/bookmarks')

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /reset/i })).toBeInTheDocument()
      })

      const resetButton = screen.getByRole('button', { name: /reset/i })
      await user.click(resetButton)

      expect(mockClearOverride).toHaveBeenCalledTimes(1)
    })
  })

  describe('sort dropdown interaction', () => {
    it('should call setSort when sort dropdown changes', async () => {
      const user = userEvent.setup()

      renderWithRouter('/app/bookmarks')

      await waitFor(() => {
        const sortDropdown = document.querySelector('select')
        expect(sortDropdown).toBeInTheDocument()
      })

      const sortDropdown = document.querySelector('select')!
      await user.selectOptions(sortDropdown, 'title-asc')

      expect(mockSetSort).toHaveBeenCalledWith('title', 'asc')
    })

    it('should reflect current effective sort in dropdown value', async () => {
      mockEffectiveSort = {
        ...mockEffectiveSort,
        sortBy: 'title',
        sortOrder: 'asc',
      }

      renderWithRouter('/app/bookmarks')

      await waitFor(() => {
        const sortDropdown = document.querySelector('select')
        expect(sortDropdown).toHaveValue('title-asc')
      })
    })

    it('should call setSort with correct values for descending', async () => {
      const user = userEvent.setup()

      renderWithRouter('/app/bookmarks')

      await waitFor(() => {
        const sortDropdown = document.querySelector('select')
        expect(sortDropdown).toBeInTheDocument()
      })

      const sortDropdown = document.querySelector('select')!
      await user.selectOptions(sortDropdown, 'created_at-desc')

      expect(mockSetSort).toHaveBeenCalledWith('created_at', 'desc')
    })
  })

})
