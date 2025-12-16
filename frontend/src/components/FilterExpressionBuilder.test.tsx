import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FilterExpressionBuilder } from './FilterExpressionBuilder'
import type { FilterExpression, TagCount } from '../types'

const mockSuggestions: TagCount[] = [
  { name: 'react', count: 5 },
  { name: 'typescript', count: 3 },
  { name: 'javascript', count: 8 },
  { name: 'frontend', count: 2 },
  { name: 'backend', count: 4 },
]

function createEmptyExpression(): FilterExpression {
  return {
    groups: [{ tags: [], operator: 'AND' }],
    group_operator: 'OR',
  }
}

function createExpressionWithTags(tags: string[]): FilterExpression {
  return {
    groups: [{ tags, operator: 'AND' }],
    group_operator: 'OR',
  }
}

function createMultiGroupExpression(): FilterExpression {
  return {
    groups: [
      { tags: ['react', 'typescript'], operator: 'AND' },
      { tags: ['backend'], operator: 'AND' },
    ],
    group_operator: 'OR',
  }
}

describe('FilterExpressionBuilder', () => {
  describe('rendering', () => {
    it('should render empty state with one group', () => {
      render(
        <FilterExpressionBuilder
          value={createEmptyExpression()}
          onChange={vi.fn()}
          tagSuggestions={mockSuggestions}
        />
      )

      expect(screen.getByText('Group 1 (AND)')).toBeInTheDocument()
      expect(screen.getByText('No tags selected')).toBeInTheDocument()
      expect(screen.getByPlaceholderText('Add tag...')).toBeInTheDocument()
    })

    it('should render existing tags in group', () => {
      render(
        <FilterExpressionBuilder
          value={createExpressionWithTags(['react', 'typescript'])}
          onChange={vi.fn()}
          tagSuggestions={mockSuggestions}
        />
      )

      expect(screen.getByText('react')).toBeInTheDocument()
      expect(screen.getByText('typescript')).toBeInTheDocument()
      expect(screen.queryByText('No tags selected')).not.toBeInTheDocument()
    })

    it('should render multiple groups with OR separator', () => {
      render(
        <FilterExpressionBuilder
          value={createMultiGroupExpression()}
          onChange={vi.fn()}
          tagSuggestions={mockSuggestions}
        />
      )

      expect(screen.getByText('Group 1 (AND)')).toBeInTheDocument()
      expect(screen.getByText('Group 2 (AND)')).toBeInTheDocument()
      expect(screen.getByText('OR')).toBeInTheDocument()
    })
  })

  describe('adding tags', () => {
    it('should add tag on Enter key', async () => {
      const onChange = vi.fn()
      const user = userEvent.setup()

      render(
        <FilterExpressionBuilder
          value={createEmptyExpression()}
          onChange={onChange}
          tagSuggestions={mockSuggestions}
        />
      )

      const input = screen.getByPlaceholderText('Add tag...')
      await user.type(input, 'newtag{Enter}')

      expect(onChange).toHaveBeenCalledWith({
        groups: [{ tags: ['newtag'], operator: 'AND' }],
        group_operator: 'OR',
      })
    })

    it('should normalize tags to lowercase and trim whitespace', async () => {
      const onChange = vi.fn()
      const user = userEvent.setup()

      render(
        <FilterExpressionBuilder
          value={createEmptyExpression()}
          onChange={onChange}
          tagSuggestions={mockSuggestions}
        />
      )

      const input = screen.getByPlaceholderText('Add tag...')
      await user.type(input, '  MyTag  {Enter}')

      expect(onChange).toHaveBeenCalledWith({
        groups: [{ tags: ['mytag'], operator: 'AND' }],
        group_operator: 'OR',
      })
    })

    it('should not add duplicate tags to the same group', async () => {
      const onChange = vi.fn()
      const user = userEvent.setup()

      render(
        <FilterExpressionBuilder
          value={createExpressionWithTags(['react'])}
          onChange={onChange}
          tagSuggestions={mockSuggestions}
        />
      )

      const input = screen.getByPlaceholderText('Add tag...')
      await user.type(input, 'react{Enter}')

      // onChange should not be called since 'react' already exists
      expect(onChange).not.toHaveBeenCalled()
    })

    it('should add tag from suggestion click', async () => {
      const onChange = vi.fn()
      const user = userEvent.setup()

      render(
        <FilterExpressionBuilder
          value={createEmptyExpression()}
          onChange={onChange}
          tagSuggestions={mockSuggestions}
        />
      )

      const input = screen.getByPlaceholderText('Add tag...')
      await user.click(input)
      await user.type(input, 'type')

      // Click the typescript suggestion
      const suggestion = screen.getByText('typescript')
      await user.click(suggestion)

      expect(onChange).toHaveBeenCalledWith({
        groups: [{ tags: ['typescript'], operator: 'AND' }],
        group_operator: 'OR',
      })
    })
  })

  describe('removing tags', () => {
    it('should remove tag when clicking close button', async () => {
      const onChange = vi.fn()
      const user = userEvent.setup()

      render(
        <FilterExpressionBuilder
          value={createExpressionWithTags(['react', 'typescript'])}
          onChange={onChange}
          tagSuggestions={mockSuggestions}
        />
      )

      // Find the react tag and click its close button
      const reactTag = screen.getByText('react')
      const closeButton = reactTag.parentElement?.querySelector('button')
      expect(closeButton).toBeTruthy()
      await user.click(closeButton!)

      expect(onChange).toHaveBeenCalledWith({
        groups: [{ tags: ['typescript'], operator: 'AND' }],
        group_operator: 'OR',
      })
    })
  })

  describe('managing groups', () => {
    it('should add new OR group when clicking "Add OR group"', async () => {
      const onChange = vi.fn()
      const user = userEvent.setup()

      render(
        <FilterExpressionBuilder
          value={createExpressionWithTags(['react'])}
          onChange={onChange}
          tagSuggestions={mockSuggestions}
        />
      )

      const addButton = screen.getByText('Add OR group')
      await user.click(addButton)

      expect(onChange).toHaveBeenCalledWith({
        groups: [
          { tags: ['react'], operator: 'AND' },
          { tags: [], operator: 'AND' },
        ],
        group_operator: 'OR',
      })
    })

    it('should remove group when clicking "Remove group"', async () => {
      const onChange = vi.fn()
      const user = userEvent.setup()

      render(
        <FilterExpressionBuilder
          value={createMultiGroupExpression()}
          onChange={onChange}
          tagSuggestions={mockSuggestions}
        />
      )

      // Should have two "Remove group" buttons
      const removeButtons = screen.getAllByText('Remove group')
      expect(removeButtons).toHaveLength(2)

      // Remove the first group
      await user.click(removeButtons[0])

      expect(onChange).toHaveBeenCalledWith({
        groups: [{ tags: ['backend'], operator: 'AND' }],
        group_operator: 'OR',
      })
    })

    it('should not show "Remove group" when only one group exists', () => {
      render(
        <FilterExpressionBuilder
          value={createEmptyExpression()}
          onChange={vi.fn()}
          tagSuggestions={mockSuggestions}
        />
      )

      expect(screen.queryByText('Remove group')).not.toBeInTheDocument()
    })
  })

  describe('suggestions filtering', () => {
    it('should filter suggestions based on input', async () => {
      const user = userEvent.setup()

      render(
        <FilterExpressionBuilder
          value={createEmptyExpression()}
          onChange={vi.fn()}
          tagSuggestions={mockSuggestions}
        />
      )

      const input = screen.getByPlaceholderText('Add tag...')
      await user.click(input)
      await user.type(input, 'script')

      // Should show typescript and javascript
      expect(screen.getByText('typescript')).toBeInTheDocument()
      expect(screen.getByText('javascript')).toBeInTheDocument()
      // Should not show react, frontend, backend
      expect(screen.queryByText('react')).not.toBeInTheDocument()
    })

    it('should exclude already selected tags from suggestions', async () => {
      const user = userEvent.setup()

      render(
        <FilterExpressionBuilder
          value={createExpressionWithTags(['react'])}
          onChange={vi.fn()}
          tagSuggestions={mockSuggestions}
        />
      )

      const input = screen.getByPlaceholderText('Add tag...')
      await user.click(input)
      await user.type(input, 'r')

      // Should show frontend but not react (already selected)
      expect(screen.getByText('frontend')).toBeInTheDocument()
      // The 'react' text exists as a tag chip, not as a suggestion
      const suggestions = screen.getAllByText('react')
      expect(suggestions).toHaveLength(1) // Only the chip, not a suggestion
    })
  })
})
