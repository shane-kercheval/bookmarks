/**
 * Tests for NoteView component.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { NoteView } from './NoteView'
import type { Note } from '../types'

const mockNote: Note = {
  id: 1,
  title: 'Test Note',
  description: 'A sample description',
  content: '# Hello World\n\nThis is **bold** text.',
  tags: ['react', 'typescript'],
  created_at: '2024-01-15T12:00:00Z',
  updated_at: '2024-01-16T12:00:00Z',
  last_used_at: '2024-01-15T12:00:00Z',
  deleted_at: null,
  archived_at: null,
  version: 3,
}

describe('NoteView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('rendering', () => {
    it('should render note title', () => {
      render(<NoteView note={mockNote} />)

      expect(screen.getByRole('heading', { name: 'Test Note' })).toBeInTheDocument()
    })

    it('should render note description', () => {
      render(<NoteView note={mockNote} />)

      expect(screen.getByText('A sample description')).toBeInTheDocument()
    })

    it('should render tags', () => {
      render(<NoteView note={mockNote} />)

      expect(screen.getByText('react')).toBeInTheDocument()
      expect(screen.getByText('typescript')).toBeInTheDocument()
    })

    it('should render created date', () => {
      render(<NoteView note={mockNote} />)

      expect(screen.getByText(/Created:/)).toBeInTheDocument()
    })

    it('should render updated date when different from created', () => {
      render(<NoteView note={mockNote} />)

      expect(screen.getByText(/Updated:/)).toBeInTheDocument()
    })

    it('should not render updated date when same as created', () => {
      const noteWithSameDate = {
        ...mockNote,
        updated_at: mockNote.created_at,
      }
      render(<NoteView note={noteWithSameDate} />)

      expect(screen.queryByText(/Updated:/)).not.toBeInTheDocument()
    })

    it('should show version number when > 1', () => {
      render(<NoteView note={mockNote} />)

      expect(screen.getByText('v3')).toBeInTheDocument()
    })

    it('should not show version number when version is 1', () => {
      const noteV1 = { ...mockNote, version: 1 }
      render(<NoteView note={noteV1} />)

      expect(screen.queryByText('v1')).not.toBeInTheDocument()
    })

    it('should render markdown content', () => {
      render(<NoteView note={mockNote} />)

      // ReactMarkdown renders the heading
      expect(screen.getByText('Hello World')).toBeInTheDocument()
    })

    it('should show "No content" when content is empty', () => {
      const noteWithoutContent = { ...mockNote, content: null }
      render(<NoteView note={noteWithoutContent} />)

      expect(screen.getByText('No content')).toBeInTheDocument()
    })

    it('should not render description section when empty', () => {
      const noteWithoutDesc = { ...mockNote, description: null }
      render(<NoteView note={noteWithoutDesc} />)

      expect(screen.queryByText('A sample description')).not.toBeInTheDocument()
    })
  })

  describe('back button', () => {
    it('should render back button when onBack is provided', () => {
      render(<NoteView note={mockNote} onBack={vi.fn()} />)

      expect(screen.getByRole('button', { name: /back/i })).toBeInTheDocument()
    })

    it('should not render back button when onBack is not provided', () => {
      render(<NoteView note={mockNote} />)

      expect(screen.queryByRole('button', { name: /back/i })).not.toBeInTheDocument()
    })

    it('should call onBack when back button is clicked', async () => {
      const onBack = vi.fn()
      const user = userEvent.setup()

      render(<NoteView note={mockNote} onBack={onBack} />)

      await user.click(screen.getByRole('button', { name: /back/i }))

      expect(onBack).toHaveBeenCalled()
    })
  })

  describe('action buttons - active view', () => {
    it('should show edit button when onEdit is provided', () => {
      render(<NoteView note={mockNote} view="active" onEdit={vi.fn()} />)

      expect(screen.getByRole('button', { name: /edit/i })).toBeInTheDocument()
    })

    it('should show archive button when onArchive is provided', () => {
      render(<NoteView note={mockNote} view="active" onArchive={vi.fn()} />)

      expect(screen.getByRole('button', { name: /archive/i })).toBeInTheDocument()
    })

    it('should show delete button when onDelete is provided', () => {
      render(<NoteView note={mockNote} view="active" onDelete={vi.fn()} />)

      expect(screen.getByRole('button', { name: /delete/i })).toBeInTheDocument()
    })

    it('should call onEdit when edit button is clicked', async () => {
      const onEdit = vi.fn()
      const user = userEvent.setup()

      render(<NoteView note={mockNote} view="active" onEdit={onEdit} />)

      await user.click(screen.getByRole('button', { name: /edit/i }))

      expect(onEdit).toHaveBeenCalled()
    })

    it('should call onArchive when archive button is clicked', async () => {
      const onArchive = vi.fn()
      const user = userEvent.setup()

      render(<NoteView note={mockNote} view="active" onArchive={onArchive} />)

      await user.click(screen.getByRole('button', { name: /archive/i }))

      expect(onArchive).toHaveBeenCalled()
    })

    it('should call onDelete when delete button is clicked', async () => {
      const onDelete = vi.fn()
      const user = userEvent.setup()

      render(<NoteView note={mockNote} view="active" onDelete={onDelete} />)

      await user.click(screen.getByRole('button', { name: /delete/i }))

      expect(onDelete).toHaveBeenCalled()
    })
  })

  describe('action buttons - archived view', () => {
    it('should show restore button when onUnarchive is provided', () => {
      render(<NoteView note={mockNote} view="archived" onUnarchive={vi.fn()} />)

      expect(screen.getByRole('button', { name: /restore/i })).toBeInTheDocument()
    })

    it('should not show archive button in archived view', () => {
      render(
        <NoteView
          note={mockNote}
          view="archived"
          onArchive={vi.fn()}
          onUnarchive={vi.fn()}
        />
      )

      expect(screen.queryByRole('button', { name: /^archive$/i })).not.toBeInTheDocument()
    })

    it('should call onUnarchive when restore button is clicked', async () => {
      const onUnarchive = vi.fn()
      const user = userEvent.setup()

      render(<NoteView note={mockNote} view="archived" onUnarchive={onUnarchive} />)

      await user.click(screen.getByRole('button', { name: /restore/i }))

      expect(onUnarchive).toHaveBeenCalled()
    })
  })

  describe('action buttons - deleted view', () => {
    it('should show restore button when onRestore is provided', () => {
      render(<NoteView note={mockNote} view="deleted" onRestore={vi.fn()} />)

      expect(screen.getByRole('button', { name: /restore/i })).toBeInTheDocument()
    })

    it('should not show edit button in deleted view', () => {
      render(<NoteView note={mockNote} view="deleted" onEdit={vi.fn()} />)

      expect(screen.queryByRole('button', { name: /edit/i })).not.toBeInTheDocument()
    })

    it('should show "Delete Permanently" button text in deleted view', () => {
      render(<NoteView note={mockNote} view="deleted" onDelete={vi.fn()} />)

      expect(screen.getByRole('button', { name: /delete permanently/i })).toBeInTheDocument()
    })

    it('should call onRestore when restore button is clicked', async () => {
      const onRestore = vi.fn()
      const user = userEvent.setup()

      render(<NoteView note={mockNote} view="deleted" onRestore={onRestore} />)

      await user.click(screen.getByRole('button', { name: /restore/i }))

      expect(onRestore).toHaveBeenCalled()
    })
  })

  describe('tag clicks', () => {
    it('should call onTagClick when a tag is clicked', async () => {
      const onTagClick = vi.fn()
      const user = userEvent.setup()

      render(<NoteView note={mockNote} onTagClick={onTagClick} />)

      await user.click(screen.getByRole('button', { name: 'react' }))

      expect(onTagClick).toHaveBeenCalledWith('react')
    })
  })
})
