/**
 * Tests for ListCard component.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ListCard } from './ListCard'
import type { ContentList } from '../types'

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

describe('ListCard', () => {
  describe('rendering', () => {
    it('should render list name', () => {
      render(
        <ListCard
          list={mockList}
          onEdit={vi.fn()}
          onDelete={vi.fn()}
        />
      )

      expect(screen.getByText('Work Resources')).toBeInTheDocument()
    })

    it('should render filter expression tags', () => {
      render(
        <ListCard
          list={mockList}
          onEdit={vi.fn()}
          onDelete={vi.fn()}
        />
      )

      expect(screen.getByText('work')).toBeInTheDocument()
      expect(screen.getByText('resources')).toBeInTheDocument()
    })

    it('should render "No filters" when filter expression is empty', () => {
      const listWithNoFilters: ContentList = {
        ...mockList,
        filter_expression: { groups: [], group_operator: 'OR' },
      }

      render(
        <ListCard
          list={listWithNoFilters}
          onEdit={vi.fn()}
          onDelete={vi.fn()}
        />
      )

      expect(screen.getByText('No filters')).toBeInTheDocument()
    })

    it('should render edit and delete buttons', () => {
      render(
        <ListCard
          list={mockList}
          onEdit={vi.fn()}
          onDelete={vi.fn()}
        />
      )

      expect(screen.getByTitle('Edit list')).toBeInTheDocument()
      expect(screen.getByTitle('Delete list')).toBeInTheDocument()
    })
  })

  describe('content types display', () => {
    it('should show bookmark icon for bookmark-only list', () => {
      const bookmarkOnlyList: ContentList = {
        ...mockList,
        content_types: ['bookmark'],
      }

      render(
        <ListCard
          list={bookmarkOnlyList}
          onEdit={vi.fn()}
          onDelete={vi.fn()}
        />
      )

      expect(screen.getByTitle('Bookmarks only')).toBeInTheDocument()
    })

    it('should show note icon for note-only list', () => {
      const noteOnlyList: ContentList = {
        ...mockList,
        content_types: ['note'],
      }

      render(
        <ListCard
          list={noteOnlyList}
          onEdit={vi.fn()}
          onDelete={vi.fn()}
        />
      )

      expect(screen.getByTitle('Notes only')).toBeInTheDocument()
    })

    it('should not show content type icon for mixed list', () => {
      const mixedList: ContentList = {
        ...mockList,
        content_types: ['bookmark', 'note'],
      }

      render(
        <ListCard
          list={mixedList}
          onEdit={vi.fn()}
          onDelete={vi.fn()}
        />
      )

      expect(screen.queryByTitle('Bookmarks only')).not.toBeInTheDocument()
      expect(screen.queryByTitle('Notes only')).not.toBeInTheDocument()
    })
  })

  describe('sort display', () => {
    it('should not show sort when default_sort_by is null', () => {
      render(
        <ListCard
          list={mockList}
          onEdit={vi.fn()}
          onDelete={vi.fn()}
        />
      )

      // No sort text should be present
      expect(screen.queryByText(/newest/i)).not.toBeInTheDocument()
      expect(screen.queryByText(/oldest/i)).not.toBeInTheDocument()
    })

    it('should show sort order when configured', () => {
      const listWithSort: ContentList = {
        ...mockList,
        default_sort_by: 'created_at',
        default_sort_ascending: false,
      }

      render(
        <ListCard
          list={listWithSort}
          onEdit={vi.fn()}
          onDelete={vi.fn()}
        />
      )

      expect(screen.getByText(/Date Added.*newest/)).toBeInTheDocument()
    })

    it('should show ascending sort order', () => {
      const listWithSort: ContentList = {
        ...mockList,
        default_sort_by: 'created_at',
        default_sort_ascending: true,
      }

      render(
        <ListCard
          list={listWithSort}
          onEdit={vi.fn()}
          onDelete={vi.fn()}
        />
      )

      expect(screen.getByText(/Date Added.*oldest/)).toBeInTheDocument()
    })

    it('should show title sort with A-Z/Z-A', () => {
      const listWithTitleSort: ContentList = {
        ...mockList,
        default_sort_by: 'title',
        default_sort_ascending: true,
      }

      render(
        <ListCard
          list={listWithTitleSort}
          onEdit={vi.fn()}
          onDelete={vi.fn()}
        />
      )

      expect(screen.getByText(/Title.*A-Z/)).toBeInTheDocument()
    })
  })

  describe('filter expression display', () => {
    it('should show OR between groups', () => {
      const listWithMultipleGroups: ContentList = {
        ...mockList,
        filter_expression: {
          groups: [
            { tags: ['work'], operator: 'AND' },
            { tags: ['personal'], operator: 'AND' },
          ],
          group_operator: 'OR',
        },
      }

      render(
        <ListCard
          list={listWithMultipleGroups}
          onEdit={vi.fn()}
          onDelete={vi.fn()}
        />
      )

      expect(screen.getByText('work')).toBeInTheDocument()
      expect(screen.getByText('or')).toBeInTheDocument()
      expect(screen.getByText('personal')).toBeInTheDocument()
    })

    it('should show + between tags in same group', () => {
      render(
        <ListCard
          list={mockList}
          onEdit={vi.fn()}
          onDelete={vi.fn()}
        />
      )

      expect(screen.getByText('work')).toBeInTheDocument()
      expect(screen.getByText('+')).toBeInTheDocument()
      expect(screen.getByText('resources')).toBeInTheDocument()
    })
  })

  describe('interactions', () => {
    it('should call onEdit when edit button is clicked', async () => {
      const onEdit = vi.fn()
      const user = userEvent.setup()

      render(
        <ListCard
          list={mockList}
          onEdit={onEdit}
          onDelete={vi.fn()}
        />
      )

      await user.click(screen.getByTitle('Edit list'))

      expect(onEdit).toHaveBeenCalledWith(mockList)
    })

    it('should call onDelete when delete is confirmed', async () => {
      const onDelete = vi.fn().mockResolvedValue(undefined)
      const user = userEvent.setup()

      render(
        <ListCard
          list={mockList}
          onEdit={vi.fn()}
          onDelete={onDelete}
        />
      )

      // First click - shows "Confirm"
      await user.click(screen.getByTitle('Delete list'))

      // Second click - confirms delete
      await user.click(screen.getByTitle('Click again to confirm'))

      await waitFor(() => {
        expect(onDelete).toHaveBeenCalledWith(mockList)
      })
    })

    it('should reset confirm state when clicking outside', async () => {
      const onDelete = vi.fn()
      const user = userEvent.setup()

      render(
        <ListCard
          list={mockList}
          onEdit={vi.fn()}
          onDelete={onDelete}
        />
      )

      // Click delete button - shows confirm state
      await user.click(screen.getByTitle('Delete list'))
      expect(screen.getByText('Confirm')).toBeInTheDocument()

      // Click outside (on the list name)
      await user.click(screen.getByText('Work Resources'))

      // Should reset to delete button
      await waitFor(() => {
        expect(screen.queryByText('Confirm')).not.toBeInTheDocument()
      })

      expect(onDelete).not.toHaveBeenCalled()
    })
  })
})
