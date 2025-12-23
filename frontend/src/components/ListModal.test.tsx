import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ListModal } from './ListModal'
import type { BookmarkList, TagCount } from '../types'

const mockSuggestions: TagCount[] = [
  { name: 'react', count: 5 },
  { name: 'typescript', count: 3 },
  { name: 'javascript', count: 8 },
]

const mockList: BookmarkList = {
  id: 1,
  name: 'Work Resources',
  filter_expression: {
    groups: [{ tags: ['work', 'resources'], operator: 'AND' }],
    group_operator: 'OR',
  },
  default_sort_by: null,
  default_sort_ascending: null,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
}

describe('ListModal', () => {
  describe('rendering', () => {
    it('should not render when closed', () => {
      render(
        <ListModal
          isOpen={false}
          onClose={vi.fn()}
          tagSuggestions={mockSuggestions}
        />
      )

      expect(screen.queryByText('Create List')).not.toBeInTheDocument()
    })

    it('should render create mode when no list provided', () => {
      render(
        <ListModal
          isOpen={true}
          onClose={vi.fn()}
          tagSuggestions={mockSuggestions}
        />
      )

      expect(screen.getByRole('heading', { name: 'Create List' })).toBeInTheDocument()
      expect(screen.getByLabelText('List Name')).toHaveValue('')
    })

    it('should render edit mode with populated form when list provided', () => {
      render(
        <ListModal
          isOpen={true}
          onClose={vi.fn()}
          list={mockList}
          tagSuggestions={mockSuggestions}
        />
      )

      expect(screen.getByText('Edit List')).toBeInTheDocument()
      expect(screen.getByLabelText('List Name')).toHaveValue('Work Resources')
      expect(screen.getByText('work')).toBeInTheDocument()
      expect(screen.getByText('resources')).toBeInTheDocument()
    })
  })

  describe('validation', () => {
    it('should show error when submitting with no tags', async () => {
      const onCreate = vi.fn()
      const user = userEvent.setup()

      render(
        <ListModal
          isOpen={true}
          onClose={vi.fn()}
          tagSuggestions={mockSuggestions}
          onCreate={onCreate}
        />
      )

      // Enter a name but no tags
      const nameInput = screen.getByLabelText('List Name')
      await user.type(nameInput, 'My List')

      const submitButton = screen.getByRole('button', { name: 'Create List' })
      await user.click(submitButton)

      expect(screen.getByText('At least one tag filter is required')).toBeInTheDocument()
      expect(onCreate).not.toHaveBeenCalled()
    })

    it('should disable submit button when name is empty', () => {
      render(
        <ListModal
          isOpen={true}
          onClose={vi.fn()}
          tagSuggestions={mockSuggestions}
          onCreate={vi.fn()}
        />
      )

      const submitButton = screen.getByRole('button', { name: 'Create List' })
      expect(submitButton).toBeDisabled()
    })
  })

  describe('form submission', () => {
    it('should call onCreate with trimmed name and cleaned expression', async () => {
      const onCreate = vi.fn().mockResolvedValue({ id: 1, name: 'Test', filter_expression: {}, created_at: '', updated_at: '' })
      const onClose = vi.fn()
      const user = userEvent.setup()

      render(
        <ListModal
          isOpen={true}
          onClose={onClose}
          tagSuggestions={mockSuggestions}
          onCreate={onCreate}
        />
      )

      // Enter name with extra whitespace
      const nameInput = screen.getByLabelText('List Name')
      await user.type(nameInput, '  My New List  ')

      // Add a tag and wait for it to appear
      const tagInput = screen.getByPlaceholderText('Add tag...')
      await user.type(tagInput, 'react{Enter}')

      // Wait for tag to be added before submitting
      await waitFor(() => {
        expect(screen.getByText('react')).toBeInTheDocument()
      })

      // Submit
      const submitButton = screen.getByRole('button', { name: 'Create List' })
      await user.click(submitButton)

      await waitFor(() => {
        expect(onCreate).toHaveBeenCalledWith({
          name: 'My New List',
          filter_expression: {
            groups: [{ tags: ['react'], operator: 'AND' }],
            group_operator: 'OR',
          },
          default_sort_by: null,
          default_sort_ascending: null,
        })
      })

      expect(onClose).toHaveBeenCalled()
    })

    it('should call onUpdate when editing existing list', async () => {
      const onUpdate = vi.fn().mockResolvedValue(mockList)
      const onClose = vi.fn()
      const user = userEvent.setup()

      render(
        <ListModal
          isOpen={true}
          onClose={onClose}
          list={mockList}
          tagSuggestions={mockSuggestions}
          onUpdate={onUpdate}
        />
      )

      // Change the name
      const nameInput = screen.getByLabelText('List Name')
      await user.clear(nameInput)
      await user.type(nameInput, 'Updated Name')

      // Submit
      const submitButton = screen.getByText('Save Changes')
      await user.click(submitButton)

      await waitFor(() => {
        expect(onUpdate).toHaveBeenCalledWith(1, {
          name: 'Updated Name',
          filter_expression: mockList.filter_expression,
          default_sort_by: null,
          default_sort_ascending: null,
        })
      })

      expect(onClose).toHaveBeenCalled()
    })

    it('should clean up empty groups before submitting', async () => {
      const onCreate = vi.fn().mockResolvedValue({ id: 1, name: 'Test', filter_expression: {}, created_at: '', updated_at: '' })
      const user = userEvent.setup()

      render(
        <ListModal
          isOpen={true}
          onClose={vi.fn()}
          tagSuggestions={mockSuggestions}
          onCreate={onCreate}
        />
      )

      // Enter name
      const nameInput = screen.getByLabelText('List Name')
      await user.type(nameInput, 'Test List')

      // Add a tag to first group
      const tagInput = screen.getByPlaceholderText('Add tag...')
      await user.type(tagInput, 'react{Enter}')

      // Wait for tag to be added before continuing
      await waitFor(() => {
        expect(screen.getByText('react')).toBeInTheDocument()
      })

      // Add an OR group (will be empty)
      const addGroupButton = screen.getByText('Add OR group')
      await user.click(addGroupButton)

      // Submit - empty group should be cleaned up
      const submitButton = screen.getByRole('button', { name: 'Create List' })
      await user.click(submitButton)

      await waitFor(() => {
        expect(onCreate).toHaveBeenCalledWith({
          name: 'Test List',
          filter_expression: {
            groups: [{ tags: ['react'], operator: 'AND' }],
            group_operator: 'OR',
          },
          default_sort_by: null,
          default_sort_ascending: null,
        })
      })
    })

    it('should show error message when submission fails', async () => {
      const onCreate = vi.fn().mockRejectedValue(new Error('Network error'))
      const user = userEvent.setup()

      render(
        <ListModal
          isOpen={true}
          onClose={vi.fn()}
          tagSuggestions={mockSuggestions}
          onCreate={onCreate}
        />
      )

      const nameInput = screen.getByLabelText('List Name')
      await user.type(nameInput, 'Test List')

      const tagInput = screen.getByPlaceholderText('Add tag...')
      await user.type(tagInput, 'react{Enter}')

      // Wait for tag to be added before continuing
      await waitFor(() => {
        expect(screen.getByText('react')).toBeInTheDocument()
      })

      const submitButton = screen.getByRole('button', { name: 'Create List' })
      await user.click(submitButton)

      await waitFor(() => {
        expect(screen.getByText('Network error')).toBeInTheDocument()
      })
    })
  })

  describe('modal interactions', () => {
    it('should close when clicking Cancel', async () => {
      const onClose = vi.fn()
      const user = userEvent.setup()

      render(
        <ListModal
          isOpen={true}
          onClose={onClose}
          tagSuggestions={mockSuggestions}
        />
      )

      const cancelButton = screen.getByText('Cancel')
      await user.click(cancelButton)

      expect(onClose).toHaveBeenCalled()
    })

    it('should NOT close when clicking backdrop (prevents accidental data loss)', async () => {
      const onClose = vi.fn()
      const user = userEvent.setup()

      render(
        <ListModal
          isOpen={true}
          onClose={onClose}
          tagSuggestions={mockSuggestions}
        />
      )

      // Click the backdrop (the modal-backdrop overlay)
      const backdrop = document.querySelector('.modal-backdrop')
      expect(backdrop).toBeTruthy()
      await user.click(backdrop!)

      // Modal should NOT close on backdrop click
      expect(onClose).not.toHaveBeenCalled()
    })

    it('should close when clicking close button', async () => {
      const onClose = vi.fn()
      const user = userEvent.setup()

      render(
        <ListModal
          isOpen={true}
          onClose={onClose}
          tagSuggestions={mockSuggestions}
        />
      )

      // Find the close button (X icon in header)
      const closeButtons = screen.getAllByRole('button')
      const closeButton = closeButtons.find(btn => btn.querySelector('svg'))
      expect(closeButton).toBeTruthy()
      await user.click(closeButton!)

      expect(onClose).toHaveBeenCalled()
    })
  })
})
