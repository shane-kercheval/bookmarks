/**
 * Tests for NoteDetail page.
 *
 * Tests view, edit, and create modes for notes.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { NoteDetail } from './NoteDetail'
import type { Note } from '../types'

// Mock toast
vi.mock('react-hot-toast', () => ({
  default: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

// Mock note data
const mockNote: Note = {
  id: 1,
  title: 'Test Note',
  description: 'Test description',
  content: '# Hello World\n\nThis is a test note.',
  tags: ['test', 'example'],
  version: 1,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
  last_used_at: '2024-01-01T00:00:00Z',
  deleted_at: null,
  archived_at: null,
}

// Mock hooks
const mockFetchNote = vi.fn()
const mockTrackNoteUsage = vi.fn()
const mockCreateMutateAsync = vi.fn()
const mockUpdateMutateAsync = vi.fn()
const mockDeleteMutateAsync = vi.fn()
const mockArchiveMutateAsync = vi.fn()
const mockUnarchiveMutateAsync = vi.fn()
const mockRestoreMutateAsync = vi.fn()
const mockNavigate = vi.fn()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

vi.mock('../hooks/useNotes', () => ({
  useNotes: () => ({
    fetchNote: mockFetchNote,
    trackNoteUsage: mockTrackNoteUsage,
  }),
}))

vi.mock('../hooks/useNoteMutations', () => ({
  useCreateNote: () => ({
    mutateAsync: mockCreateMutateAsync,
    isPending: false,
  }),
  useUpdateNote: () => ({
    mutateAsync: mockUpdateMutateAsync,
    isPending: false,
  }),
  useDeleteNote: () => ({
    mutateAsync: mockDeleteMutateAsync,
  }),
  useRestoreNote: () => ({
    mutateAsync: mockRestoreMutateAsync,
  }),
  useArchiveNote: () => ({
    mutateAsync: mockArchiveMutateAsync,
  }),
  useUnarchiveNote: () => ({
    mutateAsync: mockUnarchiveMutateAsync,
  }),
}))

vi.mock('../stores/tagsStore', () => ({
  useTagsStore: () => ({
    tags: [{ name: 'test', count: 5 }, { name: 'example', count: 3 }],
  }),
}))

vi.mock('../stores/tagFilterStore', () => ({
  useTagFilterStore: Object.assign(
    () => ({
      selectedTags: [],
      addTag: vi.fn(),
    }),
    {
      getState: () => ({
        addTag: vi.fn(),
      }),
    }
  ),
}))

// Helper to render NoteDetail with router
function renderWithRouter(initialRoute: string): void {
  render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <Routes>
        <Route path="/app/notes/new" element={<NoteDetail />} />
        <Route path="/app/notes/:id" element={<NoteDetail />} />
        <Route path="/app/notes/:id/edit" element={<NoteDetail />} />
        <Route path="/app/notes" element={<div>Notes List</div>} />
      </Routes>
    </MemoryRouter>
  )
}

describe('NoteDetail page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockFetchNote.mockResolvedValue(mockNote)
  })

  describe('create mode', () => {
    it('should render create form for /app/notes/new', async () => {
      renderWithRouter('/app/notes/new')

      await waitFor(() => {
        // Create mode shows the NoteEditor with Create Note button
        expect(screen.getByText('Create Note')).toBeInTheDocument()
      })
    })

    it('should not fetch note in create mode', async () => {
      renderWithRouter('/app/notes/new')

      await waitFor(() => {
        expect(screen.getByText('Create Note')).toBeInTheDocument()
      })

      expect(mockFetchNote).not.toHaveBeenCalled()
    })

    it('should have cancel button in create mode', async () => {
      renderWithRouter('/app/notes/new')

      await waitFor(() => {
        // Cancel button serves as "back" in edit/create mode
        expect(screen.getByText('Cancel')).toBeInTheDocument()
      })
    })

    it('should show create note button', async () => {
      renderWithRouter('/app/notes/new')

      await waitFor(() => {
        expect(screen.getByText('Create Note')).toBeInTheDocument()
      })
    })
  })

  describe('view mode', () => {
    it('should fetch note by ID', async () => {
      renderWithRouter('/app/notes/1')

      await waitFor(() => {
        expect(mockFetchNote).toHaveBeenCalledWith(1)
      })
    })

    it('should track note usage in view mode', async () => {
      renderWithRouter('/app/notes/1')

      await waitFor(() => {
        expect(mockTrackNoteUsage).toHaveBeenCalledWith(1)
      })
    })

    it('should render note title', async () => {
      renderWithRouter('/app/notes/1')

      await waitFor(() => {
        expect(screen.getByText('Test Note')).toBeInTheDocument()
      })
    })

    it('should render note description', async () => {
      renderWithRouter('/app/notes/1')

      await waitFor(() => {
        expect(screen.getByText('Test description')).toBeInTheDocument()
      })
    })

    it('should render note tags', async () => {
      renderWithRouter('/app/notes/1')

      await waitFor(() => {
        expect(screen.getByText('test')).toBeInTheDocument()
        expect(screen.getByText('example')).toBeInTheDocument()
      })
    })

    it('should show edit button in view mode', async () => {
      renderWithRouter('/app/notes/1')

      await waitFor(() => {
        expect(screen.getByText('Edit')).toBeInTheDocument()
      })
    })

    it('should show archive button for active notes', async () => {
      renderWithRouter('/app/notes/1')

      await waitFor(() => {
        expect(screen.getByText('Archive')).toBeInTheDocument()
      })
    })
  })

  describe('edit mode', () => {
    it('should render edit form for /app/notes/:id/edit', async () => {
      renderWithRouter('/app/notes/1/edit')

      await waitFor(() => {
        // Edit mode shows the NoteEditor with Save Changes button
        expect(screen.getByText('Save Changes')).toBeInTheDocument()
      })
    })

    it('should fetch note in edit mode', async () => {
      renderWithRouter('/app/notes/1/edit')

      await waitFor(() => {
        expect(mockFetchNote).toHaveBeenCalledWith(1)
      })
    })

    it('should not track usage in edit mode', async () => {
      renderWithRouter('/app/notes/1/edit')

      await waitFor(() => {
        expect(mockFetchNote).toHaveBeenCalled()
      })

      expect(mockTrackNoteUsage).not.toHaveBeenCalled()
    })

    it('should show save changes button', async () => {
      renderWithRouter('/app/notes/1/edit')

      await waitFor(() => {
        expect(screen.getByText('Save Changes')).toBeInTheDocument()
      })
    })

    it('should show cancel button', async () => {
      renderWithRouter('/app/notes/1/edit')

      await waitFor(() => {
        expect(screen.getByText('Cancel')).toBeInTheDocument()
      })
    })
  })

  describe('error handling', () => {
    it('should show error state when note fetch fails', async () => {
      mockFetchNote.mockRejectedValue(new Error('Network error'))

      renderWithRouter('/app/notes/1')

      await waitFor(() => {
        expect(screen.getByText('Network error')).toBeInTheDocument()
      })
    })

    it('should show error for invalid note ID', async () => {
      renderWithRouter('/app/notes/invalid')

      await waitFor(() => {
        expect(screen.getByText('Invalid note ID')).toBeInTheDocument()
      })
    })
  })

  describe('loading state', () => {
    it('should show loading spinner while fetching note', async () => {
      mockFetchNote.mockImplementation(() => new Promise(() => {})) // Never resolves

      renderWithRouter('/app/notes/1')

      expect(screen.getByText('Loading note...')).toBeInTheDocument()
    })
  })

  describe('navigation', () => {
    it('should navigate to list when back is clicked', async () => {
      const user = userEvent.setup()

      renderWithRouter('/app/notes/1')

      await waitFor(() => {
        expect(screen.getByText('Back')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Back'))

      expect(mockNavigate).toHaveBeenCalledWith('/app/notes')
    })
  })
})
