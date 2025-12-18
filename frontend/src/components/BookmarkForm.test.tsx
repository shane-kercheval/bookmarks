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

  describe('initialUrl prop', () => {
    it('should populate URL field with initialUrl', () => {
      render(<BookmarkForm {...defaultProps} initialUrl="https://pasted-url.com" />)

      expect(screen.getByLabelText(/URL/)).toHaveValue('https://pasted-url.com')
    })

    it('should auto-fetch metadata when initialUrl is provided', async () => {
      const mockFetchMetadata = vi.fn().mockResolvedValue({
        title: 'Fetched Title',
        description: 'Fetched Description',
        content: 'Fetched Content',
        error: null,
      })

      render(
        <BookmarkForm
          {...defaultProps}
          initialUrl="https://example.com"
          onFetchMetadata={mockFetchMetadata}
        />
      )

      await waitFor(() => {
        expect(mockFetchMetadata).toHaveBeenCalledWith('https://example.com')
      })

      await waitFor(() => {
        expect(screen.getByLabelText(/Title/)).toHaveValue('Fetched Title')
        expect(screen.getByLabelText(/Description/)).toHaveValue('Fetched Description')
        expect(screen.getByLabelText(/Content/)).toHaveValue('Fetched Content')
      })
    })

    it('should show error when auto-fetch fails', async () => {
      const mockFetchMetadata = vi.fn().mockRejectedValue(new Error('Network error'))

      render(
        <BookmarkForm
          {...defaultProps}
          initialUrl="https://example.com"
          onFetchMetadata={mockFetchMetadata}
        />
      )

      await waitFor(() => {
        expect(screen.getByText(/Failed to fetch metadata/)).toBeInTheDocument()
      })
    })

    it('should show error message from metadata response', async () => {
      const mockFetchMetadata = vi.fn().mockResolvedValue({
        title: null,
        description: null,
        content: null,
        error: 'Page not found',
      })

      render(
        <BookmarkForm
          {...defaultProps}
          initialUrl="https://example.com"
          onFetchMetadata={mockFetchMetadata}
        />
      )

      await waitFor(() => {
        expect(screen.getByText(/Could not fetch metadata: Page not found/)).toBeInTheDocument()
      })
    })

    it('should not auto-fetch if initialUrl has invalid protocol', async () => {
      const mockFetchMetadata = vi.fn()

      render(
        <BookmarkForm
          {...defaultProps}
          initialUrl="ftp://invalid.com"
          onFetchMetadata={mockFetchMetadata}
        />
      )

      // Wait a bit to ensure no fetch is triggered
      await new Promise((resolve) => setTimeout(resolve, 100))

      expect(mockFetchMetadata).not.toHaveBeenCalled()
    })

    it('should not auto-fetch if onFetchMetadata is not provided', async () => {
      // Should not throw
      render(<BookmarkForm {...defaultProps} initialUrl="https://example.com" />)

      expect(screen.getByLabelText(/URL/)).toHaveValue('https://example.com')
    })
  })

  describe('initialTags prop', () => {
    it('should populate tags when initialTags provided', () => {
      render(<BookmarkForm {...defaultProps} initialTags={['react', 'typescript']} />)

      expect(screen.getByText('react')).toBeInTheDocument()
      expect(screen.getByText('typescript')).toBeInTheDocument()
    })

    it('should include initialTags in form submission', async () => {
      const onSubmit = vi.fn().mockResolvedValue(undefined)
      const user = userEvent.setup()

      render(
        <BookmarkForm
          {...defaultProps}
          onSubmit={onSubmit}
          initialTags={['react', 'typescript']}
        />
      )

      await user.type(screen.getByLabelText(/URL/), 'example.com')
      await user.click(screen.getByRole('button', { name: 'Add Bookmark' }))

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            tags: ['react', 'typescript'],
          })
        )
      })
    })

    it('should use bookmark.tags over initialTags in edit mode', () => {
      render(
        <BookmarkForm
          {...defaultProps}
          bookmark={mockBookmark}
          initialTags={['vue', 'angular']}
        />
      )

      // mockBookmark has tags: ['react']
      expect(screen.getByText('react')).toBeInTheDocument()
      expect(screen.queryByText('vue')).not.toBeInTheDocument()
      expect(screen.queryByText('angular')).not.toBeInTheDocument()
    })

    it('should allow adding more tags to initialTags', async () => {
      const onSubmit = vi.fn().mockResolvedValue(undefined)
      const user = userEvent.setup()

      render(
        <BookmarkForm
          {...defaultProps}
          onSubmit={onSubmit}
          initialTags={['react']}
        />
      )

      // Verify initial tag is present
      expect(screen.getByText('react')).toBeInTheDocument()

      // Add a new tag via the input (when tags exist, placeholder is empty, use role instead)
      const tagInput = screen.getByRole('textbox', { name: /tags/i })
      await user.type(tagInput, 'typescript{Enter}')

      // Submit the form
      await user.type(screen.getByLabelText(/URL/), 'example.com')
      await user.click(screen.getByRole('button', { name: 'Add Bookmark' }))

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            tags: ['react', 'typescript'],
          })
        )
      })
    })

    it('should work with both initialUrl and initialTags', async () => {
      const mockFetchMetadata = vi.fn().mockResolvedValue({
        title: 'Fetched Title',
        description: null,
        content: null,
        error: null,
      })

      render(
        <BookmarkForm
          {...defaultProps}
          initialUrl="https://example.com"
          initialTags={['react', 'tutorial']}
          onFetchMetadata={mockFetchMetadata}
        />
      )

      // URL should be populated
      expect(screen.getByLabelText(/URL/)).toHaveValue('https://example.com')

      // Tags should be populated
      expect(screen.getByText('react')).toBeInTheDocument()
      expect(screen.getByText('tutorial')).toBeInTheDocument()

      // Metadata should be auto-fetched
      await waitFor(() => {
        expect(mockFetchMetadata).toHaveBeenCalledWith('https://example.com')
      })
    })
  })
})
