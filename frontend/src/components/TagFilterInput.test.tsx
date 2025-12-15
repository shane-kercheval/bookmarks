import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TagFilterInput } from './TagFilterInput'
import type { TagCount } from '../types'

const mockSuggestions: TagCount[] = [
  { name: 'react', count: 10 },
  { name: 'typescript', count: 8 },
  { name: 'javascript', count: 5 },
  { name: 'python', count: 3 },
  { name: 'redis', count: 2 },
]

describe('TagFilterInput', () => {
  describe('rendering', () => {
    it('should render with placeholder', () => {
      render(
        <TagFilterInput
          suggestions={mockSuggestions}
          selectedTags={[]}
          onTagSelect={vi.fn()}
          placeholder="Filter by tag..."
        />
      )

      expect(screen.getByPlaceholderText('Filter by tag...')).toBeInTheDocument()
    })

    it('should show suggestions on focus', async () => {
      const user = userEvent.setup()
      render(
        <TagFilterInput
          suggestions={mockSuggestions}
          selectedTags={[]}
          onTagSelect={vi.fn()}
        />
      )

      const input = screen.getByRole('textbox')
      await user.click(input)

      expect(screen.getByText('react')).toBeInTheDocument()
      expect(screen.getByText('typescript')).toBeInTheDocument()
    })

    it('should show tag counts in suggestions', async () => {
      const user = userEvent.setup()
      render(
        <TagFilterInput
          suggestions={mockSuggestions}
          selectedTags={[]}
          onTagSelect={vi.fn()}
        />
      )

      const input = screen.getByRole('textbox')
      await user.click(input)

      expect(screen.getByText('10')).toBeInTheDocument() // react count
      expect(screen.getByText('8')).toBeInTheDocument() // typescript count
    })
  })

  describe('filtering', () => {
    it('should filter suggestions based on input', async () => {
      const user = userEvent.setup()
      render(
        <TagFilterInput
          suggestions={mockSuggestions}
          selectedTags={[]}
          onTagSelect={vi.fn()}
        />
      )

      const input = screen.getByRole('textbox')
      await user.type(input, 'type')

      expect(screen.getByText('typescript')).toBeInTheDocument()
      expect(screen.queryByText('react')).not.toBeInTheDocument()
      expect(screen.queryByText('python')).not.toBeInTheDocument()
    })

    it('should exclude already selected tags from suggestions', async () => {
      const user = userEvent.setup()
      render(
        <TagFilterInput
          suggestions={mockSuggestions}
          selectedTags={['react', 'typescript']}
          onTagSelect={vi.fn()}
        />
      )

      const input = screen.getByRole('textbox')
      await user.click(input)

      expect(screen.queryByText('react')).not.toBeInTheDocument()
      expect(screen.queryByText('typescript')).not.toBeInTheDocument()
      expect(screen.getByText('javascript')).toBeInTheDocument()
      expect(screen.getByText('python')).toBeInTheDocument()
    })

    it('should show no matching tags message when no results', async () => {
      const user = userEvent.setup()
      render(
        <TagFilterInput
          suggestions={mockSuggestions}
          selectedTags={[]}
          onTagSelect={vi.fn()}
        />
      )

      const input = screen.getByRole('textbox')
      await user.type(input, 'nonexistent')

      expect(screen.getByText('No matching tags')).toBeInTheDocument()
    })
  })

  describe('selection', () => {
    it('should call onTagSelect when clicking a suggestion', async () => {
      const user = userEvent.setup()
      const onTagSelect = vi.fn()
      render(
        <TagFilterInput
          suggestions={mockSuggestions}
          selectedTags={[]}
          onTagSelect={onTagSelect}
        />
      )

      const input = screen.getByRole('textbox')
      await user.click(input)
      await user.click(screen.getByText('react'))

      expect(onTagSelect).toHaveBeenCalledWith('react')
    })

    it('should clear input after selection', async () => {
      const user = userEvent.setup()
      render(
        <TagFilterInput
          suggestions={mockSuggestions}
          selectedTags={[]}
          onTagSelect={vi.fn()}
        />
      )

      const input = screen.getByRole('textbox')
      await user.type(input, 'rea')
      await user.click(screen.getByText('react'))

      expect(input).toHaveValue('')
    })

    it('should auto-select single match on Enter', async () => {
      const user = userEvent.setup()
      const onTagSelect = vi.fn()
      render(
        <TagFilterInput
          suggestions={mockSuggestions}
          selectedTags={[]}
          onTagSelect={onTagSelect}
        />
      )

      const input = screen.getByRole('textbox')
      await user.type(input, 'typescript')
      await user.keyboard('{Enter}')

      expect(onTagSelect).toHaveBeenCalledWith('typescript')
    })

    it('should select highlighted suggestion on Enter', async () => {
      const user = userEvent.setup()
      const onTagSelect = vi.fn()
      render(
        <TagFilterInput
          suggestions={mockSuggestions}
          selectedTags={[]}
          onTagSelect={onTagSelect}
        />
      )

      const input = screen.getByRole('textbox')
      await user.click(input)
      await user.keyboard('{ArrowDown}{ArrowDown}{Enter}')

      // Second item in list (typescript)
      expect(onTagSelect).toHaveBeenCalledWith('typescript')
    })

    it('should select first suggestion on Tab', async () => {
      const user = userEvent.setup()
      const onTagSelect = vi.fn()
      render(
        <TagFilterInput
          suggestions={mockSuggestions}
          selectedTags={[]}
          onTagSelect={onTagSelect}
        />
      )

      const input = screen.getByRole('textbox')
      await user.click(input)
      await user.keyboard('{Tab}')

      expect(onTagSelect).toHaveBeenCalledWith('react')
    })
  })

  describe('keyboard navigation', () => {
    it('should navigate suggestions with arrow keys', async () => {
      const user = userEvent.setup()
      render(
        <TagFilterInput
          suggestions={mockSuggestions}
          selectedTags={[]}
          onTagSelect={vi.fn()}
        />
      )

      const input = screen.getByRole('textbox')
      await user.click(input)
      await user.keyboard('{ArrowDown}')

      // First item should be highlighted
      const buttons = screen.getAllByRole('button')
      expect(buttons[0]).toHaveAttribute('aria-selected', 'true')

      await user.keyboard('{ArrowDown}')
      expect(buttons[0]).toHaveAttribute('aria-selected', 'false')
      expect(buttons[1]).toHaveAttribute('aria-selected', 'true')

      await user.keyboard('{ArrowUp}')
      expect(buttons[0]).toHaveAttribute('aria-selected', 'true')
      expect(buttons[1]).toHaveAttribute('aria-selected', 'false')
    })

    it('should close suggestions on Escape', async () => {
      const user = userEvent.setup()
      render(
        <TagFilterInput
          suggestions={mockSuggestions}
          selectedTags={[]}
          onTagSelect={vi.fn()}
        />
      )

      const input = screen.getByRole('textbox')
      await user.click(input)

      expect(screen.getByText('react')).toBeInTheDocument()

      await user.keyboard('{Escape}')

      expect(screen.queryByText('react')).not.toBeInTheDocument()
    })
  })

  describe('click outside', () => {
    it('should close suggestions when clicking outside', async () => {
      const user = userEvent.setup()
      render(
        <div>
          <TagFilterInput
            suggestions={mockSuggestions}
            selectedTags={[]}
            onTagSelect={vi.fn()}
          />
          <button>Outside</button>
        </div>
      )

      const input = screen.getByRole('textbox')
      await user.click(input)

      expect(screen.getByText('react')).toBeInTheDocument()

      // Click outside
      fireEvent.mouseDown(screen.getByText('Outside'))

      expect(screen.queryByText('react')).not.toBeInTheDocument()
    })
  })

  describe('disabled state', () => {
    it('should disable input when disabled prop is true', () => {
      render(
        <TagFilterInput
          suggestions={mockSuggestions}
          selectedTags={[]}
          onTagSelect={vi.fn()}
          disabled={true}
        />
      )

      expect(screen.getByRole('textbox')).toBeDisabled()
    })
  })
})
