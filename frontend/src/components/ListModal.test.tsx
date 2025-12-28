import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ListModal } from './ListModal'
import type { ContentList, TagCount } from '../types'

const mockSuggestions: TagCount[] = [
  { name: 'react', count: 5 },
  { name: 'typescript', count: 3 },
  { name: 'javascript', count: 8 },
]

const mockList: ContentList = {
  id: 1,
  name: 'Work Resources',
  content_types: ['bookmark'],
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
          content_types: ['bookmark', 'note'],  // Default to all types
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
          content_types: mockList.content_types,
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
          content_types: ['bookmark', 'note'],
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

  describe('sort configuration', () => {
    it('should render sort dropdown with system default selected', () => {
      render(
        <ListModal
          isOpen={true}
          onClose={vi.fn()}
          tagSuggestions={mockSuggestions}
        />
      )

      const sortDropdown = screen.getByLabelText('Default Sort')
      expect(sortDropdown).toBeInTheDocument()
      expect(sortDropdown).toHaveValue('')
      expect(screen.getByText('System default (Last Used)')).toBeInTheDocument()
    })

    it('should show all base sort options in dropdown', () => {
      render(
        <ListModal
          isOpen={true}
          onClose={vi.fn()}
          tagSuggestions={mockSuggestions}
        />
      )

      const sortDropdown = screen.getByLabelText('Default Sort')

      // Check all sort options are present
      expect(sortDropdown.querySelector('option[value="last_used_at"]')).toBeInTheDocument()
      expect(sortDropdown.querySelector('option[value="created_at"]')).toBeInTheDocument()
      expect(sortDropdown.querySelector('option[value="updated_at"]')).toBeInTheDocument()
      expect(sortDropdown.querySelector('option[value="title"]')).toBeInTheDocument()
    })

    it('should not show ascending checkbox when system default is selected', () => {
      render(
        <ListModal
          isOpen={true}
          onClose={vi.fn()}
          tagSuggestions={mockSuggestions}
        />
      )

      expect(screen.queryByLabelText('Ascending')).not.toBeInTheDocument()
    })

    it('should show ascending checkbox when sort option is selected', async () => {
      const user = userEvent.setup()

      render(
        <ListModal
          isOpen={true}
          onClose={vi.fn()}
          tagSuggestions={mockSuggestions}
        />
      )

      const sortDropdown = screen.getByLabelText('Default Sort')
      await user.selectOptions(sortDropdown, 'title')

      expect(screen.getByLabelText('Ascending')).toBeInTheDocument()
    })

    it('should hide ascending checkbox when switching back to system default', async () => {
      const user = userEvent.setup()

      render(
        <ListModal
          isOpen={true}
          onClose={vi.fn()}
          tagSuggestions={mockSuggestions}
        />
      )

      const sortDropdown = screen.getByLabelText('Default Sort')

      // Select a sort option
      await user.selectOptions(sortDropdown, 'title')
      expect(screen.getByLabelText('Ascending')).toBeInTheDocument()

      // Switch back to system default
      await user.selectOptions(sortDropdown, '')
      expect(screen.queryByLabelText('Ascending')).not.toBeInTheDocument()
    })

    it('should submit with custom sort configuration', async () => {
      const onCreate = vi.fn().mockResolvedValue({
        id: 1,
        name: 'Test',
        filter_expression: {},
        default_sort_by: 'title',
        default_sort_ascending: true,
        created_at: '',
        updated_at: '',
      })
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
      await user.type(nameInput, 'Sorted List')

      // Add a tag
      const tagInput = screen.getByPlaceholderText('Add tag...')
      await user.type(tagInput, 'react{Enter}')
      await waitFor(() => {
        expect(screen.getByText('react')).toBeInTheDocument()
      })

      // Select sort option
      const sortDropdown = screen.getByLabelText('Default Sort')
      await user.selectOptions(sortDropdown, 'title')

      // Check ascending
      const ascendingCheckbox = screen.getByLabelText('Ascending')
      await user.click(ascendingCheckbox)

      // Submit
      const submitButton = screen.getByRole('button', { name: 'Create List' })
      await user.click(submitButton)

      await waitFor(() => {
        expect(onCreate).toHaveBeenCalledWith({
          name: 'Sorted List',
          content_types: ['bookmark', 'note'],
          filter_expression: {
            groups: [{ tags: ['react'], operator: 'AND' }],
            group_operator: 'OR',
          },
          default_sort_by: 'title',
          default_sort_ascending: true,
        })
      })
    })

    it('should submit with sort by only (ascending false)', async () => {
      const onCreate = vi.fn().mockResolvedValue({
        id: 1,
        name: 'Test',
        filter_expression: {},
        default_sort_by: 'created_at',
        default_sort_ascending: false,
        created_at: '',
        updated_at: '',
      })
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
      await user.type(screen.getByLabelText('List Name'), 'My List')

      // Add a tag
      await user.type(screen.getByPlaceholderText('Add tag...'), 'test{Enter}')
      await waitFor(() => {
        expect(screen.getByText('test')).toBeInTheDocument()
      })

      // Select sort option (don't check ascending)
      await user.selectOptions(screen.getByLabelText('Default Sort'), 'created_at')

      // Submit
      await user.click(screen.getByRole('button', { name: 'Create List' }))

      await waitFor(() => {
        expect(onCreate).toHaveBeenCalledWith(
          expect.objectContaining({
            default_sort_by: 'created_at',
            default_sort_ascending: false,
          })
        )
      })
    })

    it('should pre-populate sort config when editing list with sort', async () => {
      const listWithSort: ContentList = {
        ...mockList,
        default_sort_by: 'created_at',
        default_sort_ascending: true,
      }

      render(
        <ListModal
          isOpen={true}
          onClose={vi.fn()}
          list={listWithSort}
          tagSuggestions={mockSuggestions}
        />
      )

      // Sort dropdown should have the value
      const sortDropdown = screen.getByLabelText('Default Sort')
      expect(sortDropdown).toHaveValue('created_at')

      // Ascending checkbox should be visible and checked
      const ascendingCheckbox = screen.getByLabelText('Ascending')
      expect(ascendingCheckbox).toBeInTheDocument()
      expect(ascendingCheckbox).toBeChecked()
    })

    it('should pre-populate sort config with ascending false', () => {
      const listWithSort: ContentList = {
        ...mockList,
        default_sort_by: 'title',
        default_sort_ascending: false,
      }

      render(
        <ListModal
          isOpen={true}
          onClose={vi.fn()}
          list={listWithSort}
          tagSuggestions={mockSuggestions}
        />
      )

      const sortDropdown = screen.getByLabelText('Default Sort')
      expect(sortDropdown).toHaveValue('title')

      const ascendingCheckbox = screen.getByLabelText('Ascending')
      expect(ascendingCheckbox).not.toBeChecked()
    })

    it('should update existing list with new sort config', async () => {
      const onUpdate = vi.fn().mockResolvedValue(mockList)
      const user = userEvent.setup()

      render(
        <ListModal
          isOpen={true}
          onClose={vi.fn()}
          list={mockList}
          tagSuggestions={mockSuggestions}
          onUpdate={onUpdate}
        />
      )

      // Change sort config
      const sortDropdown = screen.getByLabelText('Default Sort')
      await user.selectOptions(sortDropdown, 'updated_at')

      const ascendingCheckbox = screen.getByLabelText('Ascending')
      await user.click(ascendingCheckbox)

      // Submit
      await user.click(screen.getByText('Save Changes'))

      await waitFor(() => {
        expect(onUpdate).toHaveBeenCalledWith(1, {
          name: 'Work Resources',
          content_types: mockList.content_types,
          filter_expression: mockList.filter_expression,
          default_sort_by: 'updated_at',
          default_sort_ascending: true,
        })
      })
    })

    it('should clear sort config when changing to system default', async () => {
      const listWithSort: ContentList = {
        ...mockList,
        default_sort_by: 'title',
        default_sort_ascending: true,
      }
      const onUpdate = vi.fn().mockResolvedValue(mockList)
      const user = userEvent.setup()

      render(
        <ListModal
          isOpen={true}
          onClose={vi.fn()}
          list={listWithSort}
          tagSuggestions={mockSuggestions}
          onUpdate={onUpdate}
        />
      )

      // Change to system default
      const sortDropdown = screen.getByLabelText('Default Sort')
      await user.selectOptions(sortDropdown, '')

      // Submit
      await user.click(screen.getByText('Save Changes'))

      await waitFor(() => {
        expect(onUpdate).toHaveBeenCalledWith(1, {
          name: 'Work Resources',
          content_types: listWithSort.content_types,
          filter_expression: mockList.filter_expression,
          default_sort_by: null,
          default_sort_ascending: null,
        })
      })
    })
  })

  describe('content types configuration', () => {
    it('should render content types checkboxes', () => {
      render(
        <ListModal
          isOpen={true}
          onClose={vi.fn()}
          tagSuggestions={mockSuggestions}
        />
      )

      expect(screen.getByText('Content Types')).toBeInTheDocument()
      expect(screen.getByLabelText('Bookmarks')).toBeInTheDocument()
      expect(screen.getByLabelText('Notes')).toBeInTheDocument()
    })

    it('should default to both types checked for new list', () => {
      render(
        <ListModal
          isOpen={true}
          onClose={vi.fn()}
          tagSuggestions={mockSuggestions}
        />
      )

      expect(screen.getByLabelText('Bookmarks')).toBeChecked()
      expect(screen.getByLabelText('Notes')).toBeChecked()
    })

    it('should populate content types from existing list', () => {
      const bookmarkOnlyList: ContentList = {
        ...mockList,
        content_types: ['bookmark'],
      }

      render(
        <ListModal
          isOpen={true}
          onClose={vi.fn()}
          list={bookmarkOnlyList}
          tagSuggestions={mockSuggestions}
        />
      )

      expect(screen.getByLabelText('Bookmarks')).toBeChecked()
      expect(screen.getByLabelText('Notes')).not.toBeChecked()
    })

    it('should allow toggling content types', async () => {
      const user = userEvent.setup()

      render(
        <ListModal
          isOpen={true}
          onClose={vi.fn()}
          tagSuggestions={mockSuggestions}
        />
      )

      // Both should be checked by default
      expect(screen.getByLabelText('Bookmarks')).toBeChecked()
      expect(screen.getByLabelText('Notes')).toBeChecked()

      // Uncheck Notes
      await user.click(screen.getByLabelText('Notes'))
      expect(screen.getByLabelText('Notes')).not.toBeChecked()

      // Bookmarks should still be checked
      expect(screen.getByLabelText('Bookmarks')).toBeChecked()
    })

    it('should not allow unchecking the last content type', async () => {
      const user = userEvent.setup()

      render(
        <ListModal
          isOpen={true}
          onClose={vi.fn()}
          tagSuggestions={mockSuggestions}
        />
      )

      // Uncheck Notes first
      await user.click(screen.getByLabelText('Notes'))
      expect(screen.getByLabelText('Notes')).not.toBeChecked()

      // Try to uncheck Bookmarks - should be disabled
      const bookmarksCheckbox = screen.getByLabelText('Bookmarks')
      expect(bookmarksCheckbox).toBeDisabled()
    })

    it('should submit with modified content types', async () => {
      const onCreate = vi.fn().mockResolvedValue({
        id: 1,
        name: 'Test',
        content_types: ['bookmark'],
        filter_expression: {},
        created_at: '',
        updated_at: '',
      })
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
      await user.type(screen.getByLabelText('List Name'), 'Bookmarks Only')

      // Add a tag
      await user.type(screen.getByPlaceholderText('Add tag...'), 'test{Enter}')
      await waitFor(() => {
        expect(screen.getByText('test')).toBeInTheDocument()
      })

      // Uncheck Notes
      await user.click(screen.getByLabelText('Notes'))

      // Submit
      await user.click(screen.getByRole('button', { name: 'Create List' }))

      await waitFor(() => {
        expect(onCreate).toHaveBeenCalledWith({
          name: 'Bookmarks Only',
          content_types: ['bookmark'],
          filter_expression: {
            groups: [{ tags: ['test'], operator: 'AND' }],
            group_operator: 'OR',
          },
          default_sort_by: null,
          default_sort_ascending: null,
        })
      })
    })

    it('should update list with modified content types', async () => {
      const onUpdate = vi.fn().mockResolvedValue(mockList)
      const user = userEvent.setup()

      render(
        <ListModal
          isOpen={true}
          onClose={vi.fn()}
          list={mockList}
          tagSuggestions={mockSuggestions}
          onUpdate={onUpdate}
        />
      )

      // Check Notes (mockList has only bookmark)
      await user.click(screen.getByLabelText('Notes'))

      // Submit
      await user.click(screen.getByText('Save Changes'))

      await waitFor(() => {
        expect(onUpdate).toHaveBeenCalledWith(1, {
          name: 'Work Resources',
          content_types: ['bookmark', 'note'],
          filter_expression: mockList.filter_expression,
          default_sort_by: null,
          default_sort_ascending: null,
        })
      })
    })
  })
})
