/**
 * Tests for NoteForm component.
 */
import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import toast from 'react-hot-toast'
import { NoteForm } from './NoteForm'
import { useUpdateNote } from '../hooks/useNoteMutations'
import type { Note, TagCount } from '../types'

// Mock dependencies
vi.mock('react-hot-toast', () => ({
  default: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

vi.mock('../hooks/useNoteMutations', () => ({
  useUpdateNote: vi.fn(),
}))

// Mock NoteView and NoteEditor to simplify tests
vi.mock('./NoteView', () => ({
  NoteView: vi.fn(({ onEdit, onArchive, onUnarchive, onDelete, onRestore, onBack, onTagClick }) => (
    <div data-testid="note-view">
      <button onClick={onEdit}>Edit</button>
      {onArchive && <button onClick={onArchive}>Archive</button>}
      {onUnarchive && <button onClick={onUnarchive}>Unarchive</button>}
      {onDelete && <button onClick={onDelete}>Delete</button>}
      {onRestore && <button onClick={onRestore}>Restore</button>}
      {onBack && <button onClick={onBack}>Back</button>}
      {onTagClick && <button onClick={() => onTagClick('test-tag')}>Tag</button>}
    </div>
  )),
}))

vi.mock('./NoteEditor', () => ({
  NoteEditor: vi.fn(({ onSubmit, onCancel, isSubmitting }) => (
    <div data-testid="note-editor">
      <button
        onClick={() => {
          // Catch re-thrown errors to prevent unhandled rejections in tests
          onSubmit({ title: 'Updated Title' }).catch(() => {})
        }}
        disabled={isSubmitting}
      >
        Save
      </button>
      <button onClick={onCancel}>Cancel</button>
      {isSubmitting && <span>Submitting...</span>}
    </div>
  )),
}))

const mockNote: Note = {
  id: 1,
  title: 'Test Note',
  description: 'A test description',
  content: '# Test Content',
  tags: ['test', 'example'],
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-02T00:00:00Z',
  last_used_at: '2024-01-01T00:00:00Z',
  deleted_at: null,
  archived_at: null,
  version: 1,
}

const mockTagSuggestions: TagCount[] = [
  { name: 'test', count: 5 },
  { name: 'example', count: 3 },
]

describe('NoteForm', () => {
  let mockMutateAsync: Mock
  let mockUpdateNote: { mutateAsync: Mock; isPending: boolean }

  beforeEach(() => {
    vi.clearAllMocks()
    mockMutateAsync = vi.fn()
    mockUpdateNote = {
      mutateAsync: mockMutateAsync,
      isPending: false,
    }
    ;(useUpdateNote as Mock).mockReturnValue(mockUpdateNote)
  })

  describe('mode switching', () => {
    it('should render NoteView by default', () => {
      render(<NoteForm note={mockNote} tagSuggestions={mockTagSuggestions} />)

      expect(screen.getByTestId('note-view')).toBeInTheDocument()
      expect(screen.queryByTestId('note-editor')).not.toBeInTheDocument()
    })

    it('should render NoteEditor when initialEditMode is true', () => {
      render(
        <NoteForm
          note={mockNote}
          tagSuggestions={mockTagSuggestions}
          initialEditMode={true}
        />
      )

      expect(screen.getByTestId('note-editor')).toBeInTheDocument()
      expect(screen.queryByTestId('note-view')).not.toBeInTheDocument()
    })

    it('should switch to edit mode when Edit button is clicked', async () => {
      const user = userEvent.setup()
      render(<NoteForm note={mockNote} tagSuggestions={mockTagSuggestions} />)

      expect(screen.getByTestId('note-view')).toBeInTheDocument()

      await user.click(screen.getByRole('button', { name: /edit/i }))

      expect(screen.getByTestId('note-editor')).toBeInTheDocument()
      expect(screen.queryByTestId('note-view')).not.toBeInTheDocument()
    })

    it('should switch back to view mode when Cancel is clicked', async () => {
      const user = userEvent.setup()
      render(
        <NoteForm
          note={mockNote}
          tagSuggestions={mockTagSuggestions}
          initialEditMode={true}
        />
      )

      expect(screen.getByTestId('note-editor')).toBeInTheDocument()

      await user.click(screen.getByRole('button', { name: /cancel/i }))

      expect(screen.getByTestId('note-view')).toBeInTheDocument()
      expect(screen.queryByTestId('note-editor')).not.toBeInTheDocument()
    })

    it('should switch back to view mode after successful save', async () => {
      const user = userEvent.setup()
      const updatedNote = { ...mockNote, title: 'Updated Title' }
      mockMutateAsync.mockResolvedValue(updatedNote)

      render(
        <NoteForm
          note={mockNote}
          tagSuggestions={mockTagSuggestions}
          initialEditMode={true}
        />
      )

      await user.click(screen.getByRole('button', { name: /save/i }))

      await waitFor(() => {
        expect(screen.getByTestId('note-view')).toBeInTheDocument()
      })
    })
  })

  describe('save functionality', () => {
    it('should call updateNote mutation on save', async () => {
      const user = userEvent.setup()
      const updatedNote = { ...mockNote, title: 'Updated Title' }
      mockMutateAsync.mockResolvedValue(updatedNote)

      render(
        <NoteForm
          note={mockNote}
          tagSuggestions={mockTagSuggestions}
          initialEditMode={true}
        />
      )

      await user.click(screen.getByRole('button', { name: /save/i }))

      expect(mockMutateAsync).toHaveBeenCalledWith({
        id: 1,
        data: { title: 'Updated Title' },
      })
    })

    it('should call onSaveSuccess with updated note after save', async () => {
      const user = userEvent.setup()
      const onSaveSuccess = vi.fn()
      const updatedNote = { ...mockNote, title: 'Updated Title' }
      mockMutateAsync.mockResolvedValue(updatedNote)

      render(
        <NoteForm
          note={mockNote}
          tagSuggestions={mockTagSuggestions}
          initialEditMode={true}
          onSaveSuccess={onSaveSuccess}
        />
      )

      await user.click(screen.getByRole('button', { name: /save/i }))

      await waitFor(() => {
        expect(onSaveSuccess).toHaveBeenCalledWith(updatedNote)
      })
    })

    it('should show error toast on save failure', async () => {
      const user = userEvent.setup()
      mockMutateAsync.mockRejectedValue(new Error('Network error'))

      render(
        <NoteForm
          note={mockNote}
          tagSuggestions={mockTagSuggestions}
          initialEditMode={true}
        />
      )

      await user.click(screen.getByRole('button', { name: /save/i }))

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Network error')
      })
    })

    it('should show generic error toast when error has no message', async () => {
      const user = userEvent.setup()
      mockMutateAsync.mockRejectedValue('Unknown error')

      render(
        <NoteForm
          note={mockNote}
          tagSuggestions={mockTagSuggestions}
          initialEditMode={true}
        />
      )

      await user.click(screen.getByRole('button', { name: /save/i }))

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Failed to save note')
      })
    })

    it('should stay in edit mode on save failure', async () => {
      const user = userEvent.setup()
      mockMutateAsync.mockRejectedValue(new Error('Network error'))

      render(
        <NoteForm
          note={mockNote}
          tagSuggestions={mockTagSuggestions}
          initialEditMode={true}
        />
      )

      await user.click(screen.getByRole('button', { name: /save/i }))

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalled()
      })

      // Should still be in edit mode
      expect(screen.getByTestId('note-editor')).toBeInTheDocument()
    })
  })

  describe('archive functionality', () => {
    it('should call onArchive', async () => {
      const user = userEvent.setup()
      const onArchive = vi.fn().mockResolvedValue(undefined)

      render(
        <NoteForm
          note={mockNote}
          tagSuggestions={mockTagSuggestions}
          onArchive={onArchive}
        />
      )

      await user.click(screen.getByRole('button', { name: /archive/i }))

      await waitFor(() => {
        expect(onArchive).toHaveBeenCalled()
      })
    })

    it('should show error toast on archive failure', async () => {
      const user = userEvent.setup()
      const onArchive = vi.fn().mockRejectedValue(new Error('Archive failed'))

      render(
        <NoteForm
          note={mockNote}
          tagSuggestions={mockTagSuggestions}
          onArchive={onArchive}
        />
      )

      await user.click(screen.getByRole('button', { name: /archive/i }))

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Archive failed')
      })
    })
  })

  describe('unarchive functionality', () => {
    it('should call onUnarchive', async () => {
      const user = userEvent.setup()
      const onUnarchive = vi.fn().mockResolvedValue(undefined)

      render(
        <NoteForm
          note={mockNote}
          tagSuggestions={mockTagSuggestions}
          view="archived"
          onUnarchive={onUnarchive}
        />
      )

      await user.click(screen.getByRole('button', { name: /unarchive/i }))

      await waitFor(() => {
        expect(onUnarchive).toHaveBeenCalled()
      })
    })

    it('should show error toast on unarchive failure', async () => {
      const user = userEvent.setup()
      const onUnarchive = vi.fn().mockRejectedValue(new Error('Restore failed'))

      render(
        <NoteForm
          note={mockNote}
          tagSuggestions={mockTagSuggestions}
          view="archived"
          onUnarchive={onUnarchive}
        />
      )

      await user.click(screen.getByRole('button', { name: /unarchive/i }))

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Restore failed')
      })
    })
  })

  describe('delete functionality', () => {
    it('should call onDelete in active view', async () => {
      const user = userEvent.setup()
      const onDelete = vi.fn().mockResolvedValue(undefined)

      render(
        <NoteForm
          note={mockNote}
          tagSuggestions={mockTagSuggestions}
          view="active"
          onDelete={onDelete}
        />
      )

      await user.click(screen.getByRole('button', { name: /delete/i }))

      await waitFor(() => {
        expect(onDelete).toHaveBeenCalled()
      })
    })

    it('should call onDelete in deleted view', async () => {
      const user = userEvent.setup()
      const onDelete = vi.fn().mockResolvedValue(undefined)

      render(
        <NoteForm
          note={mockNote}
          tagSuggestions={mockTagSuggestions}
          view="deleted"
          onDelete={onDelete}
        />
      )

      await user.click(screen.getByRole('button', { name: /delete/i }))

      await waitFor(() => {
        expect(onDelete).toHaveBeenCalled()
      })
    })

    it('should show error toast on delete failure', async () => {
      const user = userEvent.setup()
      const onDelete = vi.fn().mockRejectedValue(new Error('Delete failed'))

      render(
        <NoteForm
          note={mockNote}
          tagSuggestions={mockTagSuggestions}
          onDelete={onDelete}
        />
      )

      await user.click(screen.getByRole('button', { name: /delete/i }))

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Delete failed')
      })
    })
  })

  describe('restore functionality', () => {
    it('should call onRestore', async () => {
      const user = userEvent.setup()
      const onRestore = vi.fn().mockResolvedValue(undefined)

      render(
        <NoteForm
          note={mockNote}
          tagSuggestions={mockTagSuggestions}
          view="deleted"
          onRestore={onRestore}
        />
      )

      await user.click(screen.getByRole('button', { name: /restore/i }))

      await waitFor(() => {
        expect(onRestore).toHaveBeenCalled()
      })
    })

    it('should show error toast on restore failure', async () => {
      const user = userEvent.setup()
      const onRestore = vi.fn().mockRejectedValue(new Error('Restore failed'))

      render(
        <NoteForm
          note={mockNote}
          tagSuggestions={mockTagSuggestions}
          view="deleted"
          onRestore={onRestore}
        />
      )

      await user.click(screen.getByRole('button', { name: /restore/i }))

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Restore failed')
      })
    })
  })

  describe('back button', () => {
    it('should render back button when onBack is provided in view mode', () => {
      render(
        <NoteForm
          note={mockNote}
          tagSuggestions={mockTagSuggestions}
          onBack={vi.fn()}
        />
      )

      expect(screen.getByRole('button', { name: /back/i })).toBeInTheDocument()
    })

    it('should not render back button in edit mode (Cancel serves this purpose)', () => {
      render(
        <NoteForm
          note={mockNote}
          tagSuggestions={mockTagSuggestions}
          onBack={vi.fn()}
          initialEditMode={true}
        />
      )

      // In edit mode, Cancel button replaces Back functionality
      expect(screen.queryByRole('button', { name: /back/i })).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
    })

    it('should call onBack when back button is clicked', async () => {
      const user = userEvent.setup()
      const onBack = vi.fn()

      render(
        <NoteForm
          note={mockNote}
          tagSuggestions={mockTagSuggestions}
          onBack={onBack}
        />
      )

      await user.click(screen.getByRole('button', { name: /back/i }))

      expect(onBack).toHaveBeenCalled()
    })
  })

  describe('tag click', () => {
    it('should call onTagClick when a tag is clicked', async () => {
      const user = userEvent.setup()
      const onTagClick = vi.fn()

      render(
        <NoteForm
          note={mockNote}
          tagSuggestions={mockTagSuggestions}
          onTagClick={onTagClick}
        />
      )

      await user.click(screen.getByRole('button', { name: /tag/i }))

      expect(onTagClick).toHaveBeenCalledWith('test-tag')
    })
  })

  describe('submitting state', () => {
    it('should pass isPending to NoteEditor', async () => {
      mockUpdateNote.isPending = true
      ;(useUpdateNote as Mock).mockReturnValue(mockUpdateNote)

      render(
        <NoteForm
          note={mockNote}
          tagSuggestions={mockTagSuggestions}
          initialEditMode={true}
        />
      )

      // The mock NoteEditor shows "Submitting..." when isSubmitting is true
      expect(screen.getByText('Submitting...')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /save/i })).toBeDisabled()
    })
  })
})
