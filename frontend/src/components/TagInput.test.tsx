import { describe, it, expect, vi } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TagInput } from './TagInput'
import type { TagCount } from '../types'

const mockSuggestions: TagCount[] = [
  { name: 'react', count: 5 },
  { name: 'typescript', count: 3 },
  { name: 'javascript', count: 8 },
  { name: 'frontend', count: 2 },
]

describe('TagInput', () => {
  describe('rendering', () => {
    it('should render with placeholder when no tags', () => {
      render(
        <TagInput
          value={[]}
          onChange={vi.fn()}
          suggestions={mockSuggestions}
          placeholder="Add tags..."
        />
      )

      expect(screen.getByPlaceholderText('Add tags...')).toBeInTheDocument()
    })

    it('should render existing tags as chips', () => {
      render(
        <TagInput
          value={['react', 'typescript']}
          onChange={vi.fn()}
          suggestions={mockSuggestions}
        />
      )

      expect(screen.getByText('react')).toBeInTheDocument()
      expect(screen.getByText('typescript')).toBeInTheDocument()
    })

    it('should not show placeholder when tags exist', () => {
      render(
        <TagInput
          value={['react']}
          onChange={vi.fn()}
          suggestions={mockSuggestions}
          placeholder="Add tags..."
        />
      )

      expect(screen.queryByPlaceholderText('Add tags...')).not.toBeInTheDocument()
    })
  })

  describe('adding tags', () => {
    it('should add tag on Enter key', async () => {
      const onChange = vi.fn()
      const user = userEvent.setup()

      render(
        <TagInput
          value={[]}
          onChange={onChange}
          suggestions={mockSuggestions}
        />
      )

      const input = screen.getByRole('textbox')
      await user.type(input, 'newtag{Enter}')

      expect(onChange).toHaveBeenCalledWith(['newtag'])
    })

    it('should add tag on comma key', async () => {
      const onChange = vi.fn()
      const user = userEvent.setup()

      render(
        <TagInput
          value={[]}
          onChange={onChange}
          suggestions={mockSuggestions}
        />
      )

      const input = screen.getByRole('textbox')
      await user.type(input, 'newtag,')

      expect(onChange).toHaveBeenCalledWith(['newtag'])
    })

    it('should normalize tag to lowercase', async () => {
      const onChange = vi.fn()
      const user = userEvent.setup()

      render(
        <TagInput
          value={[]}
          onChange={onChange}
          suggestions={mockSuggestions}
        />
      )

      const input = screen.getByRole('textbox')
      await user.type(input, 'MyTag{Enter}')

      expect(onChange).toHaveBeenCalledWith(['mytag'])
    })

    it('should not add duplicate tags', async () => {
      const onChange = vi.fn()
      const user = userEvent.setup()

      render(
        <TagInput
          value={['existing']}
          onChange={onChange}
          suggestions={mockSuggestions}
        />
      )

      const input = screen.getByRole('textbox')
      await user.type(input, 'existing{Enter}')

      // onChange should not be called since it's a duplicate
      expect(onChange).not.toHaveBeenCalled()
    })

    it('should show error for invalid tag format', async () => {
      const onChange = vi.fn()
      const user = userEvent.setup()

      render(
        <TagInput
          value={[]}
          onChange={onChange}
          suggestions={mockSuggestions}
        />
      )

      const input = screen.getByRole('textbox')
      await user.type(input, 'invalid tag{Enter}')

      expect(screen.getByText(/Tags must be lowercase/)).toBeInTheDocument()
      expect(onChange).not.toHaveBeenCalled()
    })
  })

  describe('removing tags', () => {
    it('should remove tag when clicking X button', async () => {
      const onChange = vi.fn()
      const user = userEvent.setup()

      render(
        <TagInput
          value={['react', 'typescript']}
          onChange={onChange}
          suggestions={mockSuggestions}
        />
      )

      const removeButton = screen.getByRole('button', { name: 'Remove tag react' })
      await user.click(removeButton)

      expect(onChange).toHaveBeenCalledWith(['typescript'])
    })

    it('should remove last tag on backspace when input is empty', async () => {
      const onChange = vi.fn()
      const user = userEvent.setup()

      render(
        <TagInput
          value={['react', 'typescript']}
          onChange={onChange}
          suggestions={mockSuggestions}
        />
      )

      const input = screen.getByRole('textbox')
      await user.click(input)
      await user.keyboard('{Backspace}')

      expect(onChange).toHaveBeenCalledWith(['react'])
    })
  })

  describe('suggestions', () => {
    it('should show suggestions on focus when available', async () => {
      const user = userEvent.setup()

      render(
        <TagInput
          value={[]}
          onChange={vi.fn()}
          suggestions={mockSuggestions}
        />
      )

      const input = screen.getByRole('textbox')
      await user.click(input)

      expect(screen.getByText('react')).toBeInTheDocument()
      expect(screen.getByText('typescript')).toBeInTheDocument()
    })

    it('should filter suggestions based on input', async () => {
      const user = userEvent.setup()

      render(
        <TagInput
          value={[]}
          onChange={vi.fn()}
          suggestions={mockSuggestions}
        />
      )

      const input = screen.getByRole('textbox')
      await user.type(input, 'type')

      expect(screen.getByText('typescript')).toBeInTheDocument()
      expect(screen.queryByText('react')).not.toBeInTheDocument()
    })

    it('should not show already selected tags in suggestions', async () => {
      const user = userEvent.setup()

      render(
        <TagInput
          value={['react']}
          onChange={vi.fn()}
          suggestions={mockSuggestions}
        />
      )

      const input = screen.getByRole('textbox')
      await user.click(input)

      // 'react' should only appear as a chip, not in suggestions
      const reactElements = screen.getAllByText('react')
      expect(reactElements).toHaveLength(1) // Only the chip
    })

    it('should select suggestion on click', async () => {
      const onChange = vi.fn()
      const user = userEvent.setup()

      render(
        <TagInput
          value={[]}
          onChange={onChange}
          suggestions={mockSuggestions}
        />
      )

      const input = screen.getByRole('textbox')
      await user.click(input)

      const suggestionButton = screen.getByRole('button', { name: /react/ })
      await user.click(suggestionButton)

      expect(onChange).toHaveBeenCalledWith(['react'])
    })

    it('should select first suggestion on Tab', async () => {
      const onChange = vi.fn()
      const user = userEvent.setup()

      render(
        <TagInput
          value={[]}
          onChange={onChange}
          suggestions={mockSuggestions}
        />
      )

      const input = screen.getByRole('textbox')
      await user.type(input, 'type')
      await user.keyboard('{Tab}')

      expect(onChange).toHaveBeenCalledWith(['typescript'])
    })

    it('should hide suggestions on Escape', async () => {
      const user = userEvent.setup()

      render(
        <TagInput
          value={[]}
          onChange={vi.fn()}
          suggestions={mockSuggestions}
        />
      )

      const input = screen.getByRole('textbox')
      await user.click(input)

      expect(screen.getByText('react')).toBeInTheDocument()

      await user.keyboard('{Escape}')

      // Suggestions dropdown should be hidden
      expect(screen.queryByRole('button', { name: /react/ })).not.toBeInTheDocument()
    })
  })

  describe('keyboard navigation', () => {
    it('should navigate suggestions with arrow keys', async () => {
      const user = userEvent.setup()

      render(
        <TagInput
          value={[]}
          onChange={vi.fn()}
          suggestions={mockSuggestions}
        />
      )

      const input = screen.getByRole('textbox')
      await user.click(input)
      await user.keyboard('{ArrowDown}')

      // First suggestion should be highlighted (has bg-blue-50 class)
      const firstSuggestion = screen.getByRole('button', { name: /react/ })
      expect(firstSuggestion).toHaveClass('bg-blue-50')
    })

    it('should select highlighted suggestion on Enter', async () => {
      const onChange = vi.fn()
      const user = userEvent.setup()

      render(
        <TagInput
          value={[]}
          onChange={onChange}
          suggestions={mockSuggestions}
        />
      )

      const input = screen.getByRole('textbox')
      await user.click(input)
      await user.keyboard('{ArrowDown}')
      await user.keyboard('{Enter}')

      expect(onChange).toHaveBeenCalledWith(['react'])
    })
  })

  describe('ref methods', () => {
    it('should expose getPendingValue method', async () => {
      const ref = { current: null as { getPendingValue: () => string; clearPending: () => void } | null }
      const user = userEvent.setup()

      render(
        <TagInput
          ref={ref}
          value={[]}
          onChange={vi.fn()}
          suggestions={mockSuggestions}
        />
      )

      const input = screen.getByRole('textbox')
      await user.type(input, 'pending')

      expect(ref.current?.getPendingValue()).toBe('pending')
    })

    it('should expose clearPending method', async () => {
      const ref = { current: null as { getPendingValue: () => string; clearPending: () => void } | null }
      const user = userEvent.setup()

      render(
        <TagInput
          ref={ref}
          value={[]}
          onChange={vi.fn()}
          suggestions={mockSuggestions}
        />
      )

      const input = screen.getByRole('textbox')
      await user.type(input, 'pending')

      expect(ref.current?.getPendingValue()).toBe('pending')

      act(() => {
        ref.current?.clearPending()
      })

      expect(ref.current?.getPendingValue()).toBe('')
    })
  })

  describe('disabled state', () => {
    it('should disable input when disabled prop is true', () => {
      render(
        <TagInput
          value={[]}
          onChange={vi.fn()}
          suggestions={mockSuggestions}
          disabled={true}
        />
      )

      expect(screen.getByRole('textbox')).toBeDisabled()
    })

    it('should disable remove buttons when disabled', () => {
      render(
        <TagInput
          value={['react']}
          onChange={vi.fn()}
          suggestions={mockSuggestions}
          disabled={true}
        />
      )

      expect(screen.getByRole('button', { name: 'Remove tag react' })).toBeDisabled()
    })
  })

  describe('error display', () => {
    it('should show external error prop', () => {
      render(
        <TagInput
          value={[]}
          onChange={vi.fn()}
          suggestions={mockSuggestions}
          error="External error message"
        />
      )

      expect(screen.getByText('External error message')).toBeInTheDocument()
    })
  })
})
