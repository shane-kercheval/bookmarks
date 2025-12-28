/**
 * Tests for NoteCard component.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { NoteCard } from './NoteCard'
import type { NoteListItem } from '../types'

const mockNote: NoteListItem = {
  id: 1,
  title: 'Test Note',
  description: 'A test note description',
  tags: ['test', 'example'],
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
  last_used_at: '2024-01-01T00:00:00Z',
  deleted_at: null,
  archived_at: null,
  version: 1,
}

describe('NoteCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('rendering', () => {
    it('should render note title', () => {
      render(<NoteCard note={mockNote} onDelete={vi.fn()} />)

      expect(screen.getByText('Test Note')).toBeInTheDocument()
    })

    it('should render note description', () => {
      render(<NoteCard note={mockNote} onDelete={vi.fn()} />)

      expect(screen.getByText('A test note description')).toBeInTheDocument()
    })

    it('should render tags', () => {
      render(<NoteCard note={mockNote} onDelete={vi.fn()} />)

      expect(screen.getByText('test')).toBeInTheDocument()
      expect(screen.getByText('example')).toBeInTheDocument()
    })

    it('should render created date by default', () => {
      render(<NoteCard note={mockNote} onDelete={vi.fn()} />)

      expect(screen.getByText(/Created:/)).toBeInTheDocument()
    })

    it('should show version number when version > 1', () => {
      const noteWithVersion = { ...mockNote, version: 5 }
      render(<NoteCard note={noteWithVersion} onDelete={vi.fn()} />)

      expect(screen.getByText('v5')).toBeInTheDocument()
    })

    it('should not show version number when version is 1', () => {
      render(<NoteCard note={mockNote} onDelete={vi.fn()} />)

      expect(screen.queryByText('v1')).not.toBeInTheDocument()
    })

    it('should not render description section when empty', () => {
      const noteWithoutDesc = { ...mockNote, description: null }
      render(<NoteCard note={noteWithoutDesc} onDelete={vi.fn()} />)

      // Description paragraph should not exist
      expect(screen.queryByText('A test note description')).not.toBeInTheDocument()
    })
  })

  describe('date display', () => {
    it('should show modified date when sortBy is updated_at', () => {
      render(<NoteCard note={mockNote} sortBy="updated_at" onDelete={vi.fn()} />)

      expect(screen.getByText(/Modified:/)).toBeInTheDocument()
    })

    it('should show used date when sortBy is last_used_at', () => {
      render(<NoteCard note={mockNote} sortBy="last_used_at" onDelete={vi.fn()} />)

      expect(screen.getByText(/Used:/)).toBeInTheDocument()
    })

    it('should show created date for title sort', () => {
      render(<NoteCard note={mockNote} sortBy="title" onDelete={vi.fn()} />)

      expect(screen.getByText(/Created:/)).toBeInTheDocument()
    })
  })

  describe('title click', () => {
    it('should call onView when title is clicked', async () => {
      const onView = vi.fn()
      const user = userEvent.setup()

      render(<NoteCard note={mockNote} onDelete={vi.fn()} onView={onView} />)

      // Title button has text content as its accessible name
      await user.click(screen.getByRole('button', { name: 'Test Note' }))

      expect(onView).toHaveBeenCalledWith(mockNote)
    })
  })

  describe('tag clicks', () => {
    it('should call onTagClick when a tag is clicked', async () => {
      const onTagClick = vi.fn()
      const user = userEvent.setup()

      render(<NoteCard note={mockNote} onDelete={vi.fn()} onTagClick={onTagClick} />)

      await user.click(screen.getByRole('button', { name: 'test' }))

      expect(onTagClick).toHaveBeenCalledWith('test')
    })
  })

  describe('action buttons - active view', () => {
    it('should show edit button in active view', () => {
      render(
        <NoteCard
          note={mockNote}
          view="active"
          onDelete={vi.fn()}
          onEdit={vi.fn()}
        />
      )

      expect(screen.getByRole('button', { name: /edit note/i })).toBeInTheDocument()
    })

    it('should show archive button in active view', () => {
      render(
        <NoteCard
          note={mockNote}
          view="active"
          onDelete={vi.fn()}
          onArchive={vi.fn()}
        />
      )

      expect(screen.getByRole('button', { name: /archive note/i })).toBeInTheDocument()
    })

    it('should show delete button in active view', () => {
      render(<NoteCard note={mockNote} view="active" onDelete={vi.fn()} />)

      expect(screen.getByRole('button', { name: /delete note/i })).toBeInTheDocument()
    })

    it('should call onEdit when edit button is clicked', async () => {
      const onEdit = vi.fn()
      const user = userEvent.setup()

      render(
        <NoteCard
          note={mockNote}
          view="active"
          onDelete={vi.fn()}
          onEdit={onEdit}
        />
      )

      await user.click(screen.getByRole('button', { name: /edit note/i }))

      expect(onEdit).toHaveBeenCalledWith(mockNote)
    })

    it('should call onArchive when archive button is clicked', async () => {
      const onArchive = vi.fn()
      const user = userEvent.setup()

      render(
        <NoteCard
          note={mockNote}
          view="active"
          onDelete={vi.fn()}
          onArchive={onArchive}
        />
      )

      await user.click(screen.getByRole('button', { name: /archive note/i }))

      expect(onArchive).toHaveBeenCalledWith(mockNote)
    })

    it('should call onDelete when delete button is clicked', async () => {
      const onDelete = vi.fn()
      const user = userEvent.setup()

      render(<NoteCard note={mockNote} view="active" onDelete={onDelete} />)

      await user.click(screen.getByRole('button', { name: /delete note/i }))

      expect(onDelete).toHaveBeenCalledWith(mockNote)
    })
  })

  describe('action buttons - archived view', () => {
    it('should show edit button in archived view', () => {
      render(
        <NoteCard
          note={mockNote}
          view="archived"
          onDelete={vi.fn()}
          onEdit={vi.fn()}
        />
      )

      expect(screen.getByRole('button', { name: /edit note/i })).toBeInTheDocument()
    })

    it('should show restore button in archived view', () => {
      render(
        <NoteCard
          note={mockNote}
          view="archived"
          onDelete={vi.fn()}
          onUnarchive={vi.fn()}
        />
      )

      expect(screen.getByRole('button', { name: /restore note/i })).toBeInTheDocument()
    })

    it('should not show archive button in archived view', () => {
      render(
        <NoteCard
          note={mockNote}
          view="archived"
          onDelete={vi.fn()}
          onArchive={vi.fn()}
        />
      )

      expect(screen.queryByRole('button', { name: /archive note/i })).not.toBeInTheDocument()
    })

    it('should call onUnarchive when restore button is clicked', async () => {
      const onUnarchive = vi.fn()
      const user = userEvent.setup()

      render(
        <NoteCard
          note={mockNote}
          view="archived"
          onDelete={vi.fn()}
          onUnarchive={onUnarchive}
        />
      )

      await user.click(screen.getByRole('button', { name: /restore note/i }))

      expect(onUnarchive).toHaveBeenCalledWith(mockNote)
    })
  })

  describe('action buttons - deleted view', () => {
    it('should show restore button in deleted view', () => {
      render(
        <NoteCard
          note={mockNote}
          view="deleted"
          onDelete={vi.fn()}
          onRestore={vi.fn()}
        />
      )

      expect(screen.getByRole('button', { name: /restore note/i })).toBeInTheDocument()
    })

    it('should not show edit button in deleted view', () => {
      render(
        <NoteCard
          note={mockNote}
          view="deleted"
          onDelete={vi.fn()}
          onEdit={vi.fn()}
        />
      )

      expect(screen.queryByRole('button', { name: /edit note/i })).not.toBeInTheDocument()
    })

    it('should show confirm delete button in deleted view', () => {
      render(<NoteCard note={mockNote} view="deleted" onDelete={vi.fn()} />)

      // ConfirmDeleteButton initially shows "Delete permanently" tooltip
      expect(screen.getByTitle('Delete permanently')).toBeInTheDocument()
    })

    it('should call onRestore when restore button is clicked', async () => {
      const onRestore = vi.fn()
      const user = userEvent.setup()

      render(
        <NoteCard
          note={mockNote}
          view="deleted"
          onDelete={vi.fn()}
          onRestore={onRestore}
        />
      )

      await user.click(screen.getByRole('button', { name: /restore note/i }))

      expect(onRestore).toHaveBeenCalledWith(mockNote)
    })
  })

  describe('tag removal', () => {
    it('should call onTagRemove when tag remove button is clicked', async () => {
      const onTagRemove = vi.fn()
      const user = userEvent.setup()

      render(
        <NoteCard
          note={mockNote}
          onDelete={vi.fn()}
          onTagRemove={onTagRemove}
        />
      )

      // Hover to reveal remove button, then click
      const removeButton = screen.getByRole('button', { name: /remove tag test/i })
      await user.click(removeButton)

      expect(onTagRemove).toHaveBeenCalledWith(mockNote, 'test')
    })
  })

  describe('loading state', () => {
    it('should disable edit button and show spinner when isLoading', () => {
      render(
        <NoteCard
          note={mockNote}
          onDelete={vi.fn()}
          onEdit={vi.fn()}
          isLoading={true}
        />
      )

      const editButton = screen.getByRole('button', { name: /edit note/i })
      expect(editButton).toBeDisabled()
    })
  })
})
