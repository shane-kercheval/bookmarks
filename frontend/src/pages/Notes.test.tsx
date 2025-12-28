/**
 * Tests for Notes page sort functionality.
 *
 * Tests the sort dropdown options, override indicator, and reset behavior.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { Notes } from './Notes'
import { SORT_LABELS, BASE_SORT_OPTIONS } from '../constants/sortOptions'
import type { SortByOption, SortOrderOption } from '../constants/sortOptions'

// Mock toast
vi.mock('react-hot-toast', () => ({
  default: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

// Mock all the hooks used by Notes
const mockSetSort = vi.fn()

vi.mock('../hooks/useNotes', () => ({
  useNotes: () => ({
    fetchNote: vi.fn(),
    trackNoteUsage: vi.fn(),
  }),
}))

vi.mock('../hooks/useNotesQuery', () => ({
  useNotesQuery: () => ({
    data: { items: [], total: 0, offset: 0, limit: 20, has_more: false },
    isLoading: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
  }),
}))

vi.mock('../hooks/useNoteMutations', () => ({
  useCreateNote: () => ({ mutateAsync: vi.fn() }),
  useUpdateNote: () => ({ mutateAsync: vi.fn() }),
  useDeleteNote: () => ({ mutateAsync: vi.fn() }),
  useRestoreNote: () => ({ mutateAsync: vi.fn() }),
  useArchiveNote: () => ({ mutateAsync: vi.fn() }),
  useUnarchiveNote: () => ({ mutateAsync: vi.fn() }),
}))

vi.mock('../hooks/useKeyboardShortcuts', () => ({
  useKeyboardShortcuts: () => {},
}))

vi.mock('../hooks/useDebouncedValue', () => ({
  useDebouncedValue: (value: string) => value,
}))

vi.mock('../hooks/useNoteView', () => ({
  useNoteView: () => ({
    currentView: 'active',
    currentListId: null,
    currentList: null,
  }),
}))

vi.mock('../hooks/useNoteUrlParams', () => ({
  useNoteUrlParams: () => ({
    searchQuery: '',
    offset: 0,
    updateParams: vi.fn(),
  }),
}))

// This mock needs to be configurable per test
let mockEffectiveSort: {
  sortBy: SortByOption
  sortOrder: SortOrderOption
  setSort: typeof mockSetSort
  availableSortOptions: readonly SortByOption[]
} = {
  sortBy: 'last_used_at',
  sortOrder: 'desc',
  setSort: mockSetSort,
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

// Helper to render Notes with router
function renderWithRouter(initialRoute: string = '/app/notes'): void {
  render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <Routes>
        <Route path="/app/notes" element={<Notes />} />
        <Route path="/app/notes/archived" element={<Notes />} />
        <Route path="/app/notes/trash" element={<Notes />} />
        <Route path="/app/notes/lists/:listId" element={<Notes />} />
      </Routes>
    </MemoryRouter>
  )
}

describe('Notes page sort functionality', () => {
  beforeEach(() => {
    vi.clearAllMocks()

    // Reset to default sort state
    mockEffectiveSort = {
      sortBy: 'last_used_at',
      sortOrder: 'desc',
      setSort: mockSetSort,
      availableSortOptions: BASE_SORT_OPTIONS,
    }
  })

  describe('sort dropdown options', () => {
    it('should render sort dropdown', async () => {
      renderWithRouter('/app/notes')

      await waitFor(() => {
        const sortDropdown = document.querySelector('select')
        expect(sortDropdown).toBeInTheDocument()
      })
    })

    it('should show base sort options', async () => {
      renderWithRouter('/app/notes')

      await waitFor(() => {
        const sortDropdown = document.querySelector('select')
        expect(sortDropdown).toBeInTheDocument()
      })

      // Check base options are present (both ascending and descending)
      for (const option of BASE_SORT_OPTIONS) {
        expect(screen.getByText(new RegExp(`${SORT_LABELS[option]}.*↓`))).toBeInTheDocument()
        expect(screen.getByText(new RegExp(`${SORT_LABELS[option]}.*↑`))).toBeInTheDocument()
      }
    })

    it('should show archived_at option when available', async () => {
      mockEffectiveSort = {
        ...mockEffectiveSort,
        sortBy: 'archived_at',
        availableSortOptions: [...BASE_SORT_OPTIONS, 'archived_at'],
      }

      renderWithRouter('/app/notes/archived')

      await waitFor(() => {
        expect(screen.getByText(/Archived At.*↓/)).toBeInTheDocument()
        expect(screen.getByText(/Archived At.*↑/)).toBeInTheDocument()
      })
    })

    it('should show deleted_at option when available', async () => {
      mockEffectiveSort = {
        ...mockEffectiveSort,
        sortBy: 'deleted_at',
        availableSortOptions: [...BASE_SORT_OPTIONS, 'deleted_at'],
      }

      renderWithRouter('/app/notes/trash')

      await waitFor(() => {
        expect(screen.getByText(/Deleted At.*↓/)).toBeInTheDocument()
        expect(screen.getByText(/Deleted At.*↑/)).toBeInTheDocument()
      })
    })

    it('should not show archived_at when not in availableSortOptions', async () => {
      renderWithRouter('/app/notes')

      await waitFor(() => {
        const sortDropdown = document.querySelector('select')
        expect(sortDropdown).toBeInTheDocument()
      })

      expect(screen.queryByText(/Archived At.*↓/)).not.toBeInTheDocument()
    })

    it('should not show deleted_at when not in availableSortOptions', async () => {
      renderWithRouter('/app/notes')

      await waitFor(() => {
        const sortDropdown = document.querySelector('select')
        expect(sortDropdown).toBeInTheDocument()
      })

      expect(screen.queryByText(/Deleted At.*↓/)).not.toBeInTheDocument()
    })
  })

  describe('sort dropdown interaction', () => {
    it('should call setSort when sort dropdown changes', async () => {
      const user = userEvent.setup()

      renderWithRouter('/app/notes')

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

      renderWithRouter('/app/notes')

      await waitFor(() => {
        const sortDropdown = document.querySelector('select')
        expect(sortDropdown).toHaveValue('title-asc')
      })
    })

    it('should call setSort with correct values for descending', async () => {
      const user = userEvent.setup()

      renderWithRouter('/app/notes')

      await waitFor(() => {
        const sortDropdown = document.querySelector('select')
        expect(sortDropdown).toBeInTheDocument()
      })

      const sortDropdown = document.querySelector('select')!
      await user.selectOptions(sortDropdown, 'created_at-desc')

      expect(mockSetSort).toHaveBeenCalledWith('created_at', 'desc')
    })
  })

  describe('empty states', () => {
    it('should show empty state for active view with no notes', async () => {
      renderWithRouter('/app/notes')

      await waitFor(() => {
        expect(screen.getByText('No notes yet')).toBeInTheDocument()
        expect(screen.getByText('Get started by creating your first note.')).toBeInTheDocument()
      })
    })
  })

  describe('new note button', () => {
    it('should show new note button in active view', async () => {
      renderWithRouter('/app/notes')

      await waitFor(() => {
        const addButton = screen.getByRole('button', { name: 'New note' })
        expect(addButton).toBeInTheDocument()
      })
    })
  })
})
