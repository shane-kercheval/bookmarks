import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BookmarkForm } from './BookmarkForm'
import type { Bookmark, TagCount } from '../types'

const mockTagSuggestions: TagCount[] = [
  { name: 'react', count: 5 },
  { name: 'typescript', count: 3 },
]

const mockBookmark: Bookmark = {
  id: 1,
  url: 'https://example.com',
  title: 'Example Site',
  description: 'A sample description',
  summary: null,
  tags: ['react'],
  created_at: '2024-01-15T12:00:00Z',
  updated_at: '2024-01-15T12:00:00Z',
}

describe('BookmarkForm', () => {
  const defaultProps = {
    tagSuggestions: mockTagSuggestions,
    onSubmit: vi.fn(),
    onCancel: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('create mode', () => {
    it('should render empty form for creating new bookmark', () => {
      render(<BookmarkForm {...defaultProps} />)

      expect(screen.getByLabelText(/URL/)).toHaveValue('')
      expect(screen.getByLabelText(/Title/)).toHaveValue('')
      expect(screen.getByLabelText(/Description/)).toHaveValue('')
      expect(screen.getByRole('button', { name: 'Add Bookmark' })).toBeInTheDocument()
    })

    it('should show fetch metadata button in create mode', () => {
      render(<BookmarkForm {...defaultProps} />)

      expect(screen.getByRole('button', { name: 'Fetch metadata from URL' })).toBeInTheDocument()
    })

    it('should show required indicator for URL', () => {
      render(<BookmarkForm {...defaultProps} />)

      const urlLabel = screen.getByText(/^URL/)
      expect(urlLabel).toContainHTML('<span class="text-red-500">*</span>')
    })

    it('should show store content checkbox in create mode', () => {
      render(<BookmarkForm {...defaultProps} />)

      expect(screen.getByLabelText(/Save for search/)).toBeInTheDocument()
    })

    it('should disable Add Bookmark button when URL is empty', () => {
      render(<BookmarkForm {...defaultProps} />)

      expect(screen.getByRole('button', { name: 'Add Bookmark' })).toBeDisabled()
    })

    it('should enable Add Bookmark button when URL has value', async () => {
      const user = userEvent.setup()
      render(<BookmarkForm {...defaultProps} />)

      await user.type(screen.getByLabelText(/URL/), 'example.com')

      expect(screen.getByRole('button', { name: 'Add Bookmark' })).not.toBeDisabled()
    })
  })

  describe('edit mode', () => {
    it('should populate form with existing bookmark data', () => {
      render(<BookmarkForm {...defaultProps} bookmark={mockBookmark} />)

      expect(screen.getByLabelText(/URL/)).toHaveValue('https://example.com')
      expect(screen.getByLabelText(/Title/)).toHaveValue('Example Site')
      expect(screen.getByLabelText(/Description/)).toHaveValue('A sample description')
      expect(screen.getByText('react')).toBeInTheDocument()
    })

    it('should show Save Changes button in edit mode', () => {
      render(<BookmarkForm {...defaultProps} bookmark={mockBookmark} />)

      expect(screen.getByRole('button', { name: 'Save Changes' })).toBeInTheDocument()
    })

    it('should show fetch metadata button in edit mode', () => {
      render(<BookmarkForm {...defaultProps} bookmark={mockBookmark} />)

      expect(screen.getByRole('button', { name: 'Fetch metadata from URL' })).toBeInTheDocument()
    })

    it('should show content field and checkbox in edit mode', () => {
      render(<BookmarkForm {...defaultProps} bookmark={mockBookmark} />)

      expect(screen.getByLabelText(/Content/)).toBeInTheDocument()
      expect(screen.getByLabelText(/Save for search/)).toBeInTheDocument()
    })
  })

  describe('form submission', () => {
    it('should call onSubmit with form data on create', async () => {
      const onSubmit = vi.fn().mockResolvedValue(undefined)
      const user = userEvent.setup()

      render(<BookmarkForm {...defaultProps} onSubmit={onSubmit} />)

      await user.type(screen.getByLabelText(/URL/), 'example.com')
      await user.type(screen.getByLabelText(/Title/), 'Test Title')
      await user.click(screen.getByRole('button', { name: 'Add Bookmark' }))

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalledWith({
          url: 'https://example.com',
          title: 'Test Title',
          description: undefined,
          tags: [],
          store_content: true,
        })
      })
    })

    it('should call onSubmit with only changed fields on edit', async () => {
      const onSubmit = vi.fn().mockResolvedValue(undefined)
      const user = userEvent.setup()

      render(
        <BookmarkForm {...defaultProps} bookmark={mockBookmark} onSubmit={onSubmit} />
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

      render(<BookmarkForm {...defaultProps} onCancel={onCancel} />)

      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      expect(onCancel).toHaveBeenCalled()
    })
  })

  describe('validation', () => {
    it('should disable fetch metadata button when URL is empty', () => {
      render(<BookmarkForm {...defaultProps} />)

      const fetchButton = screen.getByRole('button', { name: 'Fetch metadata from URL' })
      expect(fetchButton).toBeDisabled()
    })

    it('should show error for invalid URL', async () => {
      const user = userEvent.setup()
      render(<BookmarkForm {...defaultProps} />)

      await user.type(screen.getByLabelText(/URL/), 'not a valid url with spaces')
      await user.click(screen.getByRole('button', { name: 'Fetch metadata from URL' }))

      expect(screen.getByText('Please enter a valid URL')).toBeInTheDocument()
    })

    it('should clear URL error when user types', async () => {
      const user = userEvent.setup()
      render(<BookmarkForm {...defaultProps} />)

      await user.type(screen.getByLabelText(/URL/), 'invalid url with spaces')
      await user.click(screen.getByRole('button', { name: 'Fetch metadata from URL' }))

      expect(screen.getByText('Please enter a valid URL')).toBeInTheDocument()

      await user.type(screen.getByLabelText(/URL/), 'x')

      expect(screen.queryByText('Please enter a valid URL')).not.toBeInTheDocument()
    })
  })

  describe('fetch metadata', () => {
    it('should fetch metadata when button is clicked', async () => {
      const onFetchMetadata = vi.fn().mockResolvedValue({
        title: 'Fetched Title',
        description: 'Fetched Description',
        content: null,
        error: null,
      })
      const user = userEvent.setup()

      render(
        <BookmarkForm
          {...defaultProps}
          onFetchMetadata={onFetchMetadata}
        />
      )

      await user.type(screen.getByLabelText(/URL/), 'example.com')
      await user.click(screen.getByRole('button', { name: 'Fetch metadata from URL' }))

      await waitFor(() => {
        expect(onFetchMetadata).toHaveBeenCalledWith('https://example.com')
      })

      expect(screen.getByLabelText(/Title/)).toHaveValue('Fetched Title')
      expect(screen.getByLabelText(/Description/)).toHaveValue('Fetched Description')
    })

    it('should overwrite existing title/description with fetched metadata', async () => {
      const onFetchMetadata = vi.fn().mockResolvedValue({
        title: 'Fetched Title',
        description: 'Fetched Description',
        content: 'Fetched Content',
        error: null,
      })
      const user = userEvent.setup()

      render(
        <BookmarkForm
          {...defaultProps}
          onFetchMetadata={onFetchMetadata}
        />
      )

      await user.type(screen.getByLabelText(/URL/), 'example.com')
      await user.type(screen.getByLabelText(/Title/), 'My Title')
      await user.click(screen.getByRole('button', { name: 'Fetch metadata from URL' }))

      await waitFor(() => {
        expect(onFetchMetadata).toHaveBeenCalled()
      })

      // Fetch should overwrite existing values
      expect(screen.getByLabelText(/Title/)).toHaveValue('Fetched Title')
      expect(screen.getByLabelText(/Description/)).toHaveValue('Fetched Description')
      expect(screen.getByLabelText(/Content/)).toHaveValue('Fetched Content')
    })

    it('should show success message after fetching metadata', async () => {
      const onFetchMetadata = vi.fn().mockResolvedValue({
        title: 'Test Title',
        description: null,
        content: null,
        error: null,
      })
      const user = userEvent.setup()

      render(
        <BookmarkForm
          {...defaultProps}
          onFetchMetadata={onFetchMetadata}
        />
      )

      await user.type(screen.getByLabelText(/URL/), 'example.com')
      await user.click(screen.getByRole('button', { name: 'Fetch metadata from URL' }))

      await waitFor(() => {
        // After successful fetch, title should be populated
        expect(screen.getByLabelText(/Title/)).toHaveValue('Test Title')
      })
    })

    it('should show warning when metadata fetch returns error', async () => {
      const onFetchMetadata = vi.fn().mockResolvedValue({
        title: null,
        description: null,
        content: null,
        error: 'Page not accessible',
      })
      const user = userEvent.setup()

      render(
        <BookmarkForm
          {...defaultProps}
          onFetchMetadata={onFetchMetadata}
        />
      )

      await user.type(screen.getByLabelText(/URL/), 'example.com')
      await user.click(screen.getByRole('button', { name: 'Fetch metadata from URL' }))

      await waitFor(() => {
        expect(screen.getByText(/Could not fetch metadata: Page not accessible/)).toBeInTheDocument()
      })
    })

    it('should disable fetch button while fetching metadata', async () => {
      let resolveMetadata: (value: unknown) => void
      const onFetchMetadata = vi.fn().mockImplementation(
        () => new Promise((resolve) => { resolveMetadata = resolve })
      )
      const user = userEvent.setup()

      render(
        <BookmarkForm
          {...defaultProps}
          onFetchMetadata={onFetchMetadata}
        />
      )

      await user.type(screen.getByLabelText(/URL/), 'example.com')
      const fetchButton = screen.getByRole('button', { name: 'Fetch metadata from URL' })
      await user.click(fetchButton)

      // Button should be disabled while fetching
      expect(fetchButton).toBeDisabled()

      resolveMetadata!({ title: 'Title', description: null, content: null, error: null })

      await waitFor(() => {
        expect(fetchButton).not.toBeDisabled()
      })
    })
  })

  describe('disabled state', () => {
    it('should disable all inputs when isSubmitting is true', () => {
      render(<BookmarkForm {...defaultProps} isSubmitting={true} />)

      expect(screen.getByLabelText(/URL/)).toBeDisabled()
      expect(screen.getByLabelText(/Title/)).toBeDisabled()
      expect(screen.getByLabelText(/Description/)).toBeDisabled()
      expect(screen.getByLabelText(/Save for search/)).toBeDisabled()
    })

    it('should show Saving... on submit button when isSubmitting', () => {
      render(
        <BookmarkForm
          {...defaultProps}
          bookmark={mockBookmark}
          isSubmitting={true}
        />
      )

      expect(screen.getByText('Saving...')).toBeInTheDocument()
    })
  })
})
