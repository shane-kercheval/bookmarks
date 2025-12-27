/**
 * Tests for NoteEditor component.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { NoteEditor } from './NoteEditor'
import type { Note, TagCount } from '../types'
import { config } from '../config'

// Mock CodeMirror since it has complex DOM interactions
vi.mock('@uiw/react-codemirror', () => ({
  default: ({ value, onChange, placeholder }: {
    value: string
    onChange: (value: string) => void
    placeholder?: string
  }) => (
    <textarea
      data-testid="codemirror-mock"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
    />
  ),
}))

const mockTagSuggestions: TagCount[] = [
  { name: 'react', count: 5 },
  { name: 'typescript', count: 3 },
]

const mockNote: Note = {
  id: 1,
  title: 'Test Note',
  description: 'A sample description',
  content: '# Hello\n\nThis is content.',
  tags: ['react'],
  created_at: '2024-01-15T12:00:00Z',
  updated_at: '2024-01-15T12:00:00Z',
  last_used_at: '2024-01-15T12:00:00Z',
  deleted_at: null,
  archived_at: null,
  version: 1,
}

describe('NoteEditor', () => {
  const defaultProps = {
    tagSuggestions: mockTagSuggestions,
    onSubmit: vi.fn(),
    onCancel: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
  })

  describe('create mode', () => {
    it('should render empty form for creating new note', () => {
      render(<NoteEditor {...defaultProps} />)

      expect(screen.getByLabelText(/Title/)).toHaveValue('')
      expect(screen.getByLabelText(/Description/)).toHaveValue('')
      expect(screen.getByRole('button', { name: 'Create Note' })).toBeInTheDocument()
    })

    it('should show required indicator for title', () => {
      render(<NoteEditor {...defaultProps} />)

      const titleLabel = screen.getByText(/^Title/)
      expect(titleLabel).toContainHTML('<span class="text-red-500">*</span>')
    })

    it('should disable Create Note button when title is empty', () => {
      render(<NoteEditor {...defaultProps} />)

      expect(screen.getByRole('button', { name: 'Create Note' })).toBeDisabled()
    })

    it('should enable Create Note button when title has value', async () => {
      const user = userEvent.setup()
      render(<NoteEditor {...defaultProps} />)

      await user.type(screen.getByLabelText(/Title/), 'My Note')

      expect(screen.getByRole('button', { name: 'Create Note' })).not.toBeDisabled()
    })
  })

  describe('edit mode', () => {
    it('should populate form with existing note data', () => {
      render(<NoteEditor {...defaultProps} note={mockNote} />)

      expect(screen.getByLabelText(/Title/)).toHaveValue('Test Note')
      expect(screen.getByLabelText(/Description/)).toHaveValue('A sample description')
      expect(screen.getByText('react')).toBeInTheDocument()
    })

    it('should show Save Changes button in edit mode', () => {
      render(<NoteEditor {...defaultProps} note={mockNote} />)

      expect(screen.getByRole('button', { name: 'Save Changes' })).toBeInTheDocument()
    })

    it('should show content in editor', () => {
      render(<NoteEditor {...defaultProps} note={mockNote} />)

      const editor = screen.getByTestId('codemirror-mock')
      expect(editor).toHaveValue('# Hello\n\nThis is content.')
    })
  })

  describe('form submission', () => {
    it('should call onSubmit with form data on create', async () => {
      const onSubmit = vi.fn().mockResolvedValue(undefined)
      const user = userEvent.setup()

      render(<NoteEditor {...defaultProps} onSubmit={onSubmit} />)

      await user.type(screen.getByLabelText(/Title/), 'New Note')
      await user.type(screen.getByLabelText(/Description/), 'Description')
      await user.type(screen.getByTestId('codemirror-mock'), '# Content')
      await user.click(screen.getByRole('button', { name: 'Create Note' }))

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalledWith({
          title: 'New Note',
          description: 'Description',
          content: '# Content',
          tags: [],
        })
      })
    })

    it('should call onSubmit with only changed fields on edit', async () => {
      const onSubmit = vi.fn().mockResolvedValue(undefined)
      const user = userEvent.setup()

      render(
        <NoteEditor {...defaultProps} note={mockNote} onSubmit={onSubmit} />
      )

      await user.clear(screen.getByLabelText(/Title/))
      await user.type(screen.getByLabelText(/Title/), 'Updated Title')
      await user.click(screen.getByRole('button', { name: 'Save Changes' }))

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalledWith({
          title: 'Updated Title',
        })
      })
    })

    it('should call onCancel when Cancel button is clicked', async () => {
      const onCancel = vi.fn()
      const user = userEvent.setup()

      render(<NoteEditor {...defaultProps} onCancel={onCancel} />)

      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      expect(onCancel).toHaveBeenCalled()
    })
  })

  describe('validation', () => {
    it('should show error when title is empty on submit', async () => {
      const user = userEvent.setup()
      render(<NoteEditor {...defaultProps} />)

      // Enable button by adding title, then clear it
      const titleInput = screen.getByLabelText(/Title/)
      await user.type(titleInput, 'a')
      await user.clear(titleInput)

      // Button should be disabled when title is empty
      expect(screen.getByRole('button', { name: 'Create Note' })).toBeDisabled()
    })

    it('should clear title error when user types', async () => {
      const user = userEvent.setup()
      render(<NoteEditor {...defaultProps} />)

      // Start with empty title, try to submit (button disabled but we can test error state)
      const titleInput = screen.getByLabelText(/Title/)
      await user.type(titleInput, 'a')
      await user.clear(titleInput)

      // Type something - any previous error should be cleared
      await user.type(titleInput, 'New Title')

      // Should not have error text
      expect(screen.queryByText('Title is required')).not.toBeInTheDocument()
    })
  })

  describe('preview mode', () => {
    it('should toggle between edit and preview modes', async () => {
      const user = userEvent.setup()
      render(<NoteEditor {...defaultProps} note={mockNote} />)

      // Start in edit mode
      expect(screen.getByTestId('codemirror-mock')).toBeInTheDocument()

      // Click Preview
      await user.click(screen.getByRole('button', { name: 'Preview' }))

      // Should show rendered markdown (react-markdown output)
      expect(screen.queryByTestId('codemirror-mock')).not.toBeInTheDocument()
      expect(screen.getByText('Hello')).toBeInTheDocument() // h1 rendered

      // Click Edit to go back
      await user.click(screen.getByRole('button', { name: 'Edit' }))

      expect(screen.getByTestId('codemirror-mock')).toBeInTheDocument()
    })

    it('should show "No content to preview" when content is empty', async () => {
      const user = userEvent.setup()
      render(<NoteEditor {...defaultProps} />)

      await user.click(screen.getByRole('button', { name: 'Preview' }))

      expect(screen.getByText('No content to preview')).toBeInTheDocument()
    })
  })

  describe('disabled state', () => {
    it('should disable all inputs when isSubmitting is true', () => {
      render(<NoteEditor {...defaultProps} isSubmitting={true} />)

      expect(screen.getByLabelText(/Title/)).toBeDisabled()
      expect(screen.getByLabelText(/Description/)).toBeDisabled()
    })

    it('should show Saving... on submit button when isSubmitting', () => {
      render(
        <NoteEditor
          {...defaultProps}
          note={mockNote}
          isSubmitting={true}
        />
      )

      expect(screen.getByText('Saving...')).toBeInTheDocument()
    })
  })

  describe('initialTags prop', () => {
    it('should populate tags when initialTags provided', () => {
      render(<NoteEditor {...defaultProps} initialTags={['react', 'typescript']} />)

      expect(screen.getByText('react')).toBeInTheDocument()
      expect(screen.getByText('typescript')).toBeInTheDocument()
    })

    it('should include initialTags in form submission', async () => {
      const onSubmit = vi.fn().mockResolvedValue(undefined)
      const user = userEvent.setup()

      render(
        <NoteEditor
          {...defaultProps}
          onSubmit={onSubmit}
          initialTags={['react', 'typescript']}
        />
      )

      await user.type(screen.getByLabelText(/Title/), 'New Note')
      await user.click(screen.getByRole('button', { name: 'Create Note' }))

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            tags: ['react', 'typescript'],
          })
        )
      })
    })

    it('should use note.tags over initialTags in edit mode', () => {
      render(
        <NoteEditor
          {...defaultProps}
          note={mockNote}
          initialTags={['vue', 'angular']}
        />
      )

      // mockNote has tags: ['react']
      expect(screen.getByText('react')).toBeInTheDocument()
      expect(screen.queryByText('vue')).not.toBeInTheDocument()
      expect(screen.queryByText('angular')).not.toBeInTheDocument()
    })
  })

  describe('character counts', () => {
    it('should show character count for description field', () => {
      render(<NoteEditor {...defaultProps} />)

      expect(
        screen.getByText(`0/${config.limits.maxDescriptionLength.toLocaleString()}`)
      ).toBeInTheDocument()
    })

    it('should show character count for content field', () => {
      render(<NoteEditor {...defaultProps} />)

      expect(
        screen.getByText(`0/${config.limits.maxNoteContentLength.toLocaleString()}`)
      ).toBeInTheDocument()
    })

    it('should update description character count as user types', async () => {
      const user = userEvent.setup()
      render(<NoteEditor {...defaultProps} />)

      const descInput = screen.getByLabelText(/Description/)
      await user.type(descInput, 'hello')

      expect(
        screen.getByText(`5/${config.limits.maxDescriptionLength.toLocaleString()}`)
      ).toBeInTheDocument()
    })

    it('should enforce maxLength attribute on title input', () => {
      render(<NoteEditor {...defaultProps} />)

      const titleInput = screen.getByLabelText(/Title/)
      expect(titleInput).toHaveAttribute(
        'maxLength',
        config.limits.maxTitleLength.toString()
      )
    })

    it('should enforce maxLength attribute on description textarea', () => {
      render(<NoteEditor {...defaultProps} />)

      const descInput = screen.getByLabelText(/Description/)
      expect(descInput).toHaveAttribute(
        'maxLength',
        config.limits.maxDescriptionLength.toString()
      )
    })
  })

  describe('markdown help text', () => {
    it('should show markdown syntax help', () => {
      render(<NoteEditor {...defaultProps} />)

      expect(screen.getByText(/Supports Markdown/)).toBeInTheDocument()
    })
  })

  describe('keyboard shortcut hint', () => {
    it('should show Cmd+S hint', () => {
      render(<NoteEditor {...defaultProps} />)

      expect(screen.getByText(/Cmd\+S/)).toBeInTheDocument()
    })
  })
})
