import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TabOrderEditor } from './TabOrderEditor'
import type { TabOrderItem } from '../types'

const mockItems: TabOrderItem[] = [
  { key: 'all', label: 'All Bookmarks', type: 'builtin' },
  { key: 'archived', label: 'Archived', type: 'builtin' },
  { key: 'trash', label: 'Trash', type: 'builtin' },
  { key: 'list:1', label: 'Work Resources', type: 'list' },
  { key: 'list:2', label: 'Reading List', type: 'list' },
]

describe('TabOrderEditor', () => {
  describe('rendering', () => {
    it('should render loading state', () => {
      render(
        <TabOrderEditor
          items={[]}
          isLoading={true}
          onSave={vi.fn()}
        />
      )

      expect(screen.getByText('Loading tab order...')).toBeInTheDocument()
    })

    it('should render empty state when no items', () => {
      render(
        <TabOrderEditor
          items={[]}
          isLoading={false}
          onSave={vi.fn()}
        />
      )

      expect(screen.getByText('Using default tab order.')).toBeInTheDocument()
    })

    it('should render all items with labels', () => {
      render(
        <TabOrderEditor
          items={mockItems}
          isLoading={false}
          onSave={vi.fn()}
        />
      )

      expect(screen.getByText('All Bookmarks')).toBeInTheDocument()
      expect(screen.getByText('Archived')).toBeInTheDocument()
      expect(screen.getByText('Trash')).toBeInTheDocument()
      expect(screen.getByText('Work Resources')).toBeInTheDocument()
      expect(screen.getByText('Reading List')).toBeInTheDocument()
    })

    it('should show type indicator for each item', () => {
      render(
        <TabOrderEditor
          items={mockItems}
          isLoading={false}
          onSave={vi.fn()}
        />
      )

      // Built-in tabs show "(built-in)" label, custom lists don't show a label
      expect(screen.getAllByText('(built-in)')).toHaveLength(3)
      expect(screen.queryByText('(list)')).not.toBeInTheDocument()
    })
  })

  describe('reordering', () => {
    it('should move item up when clicking up button', async () => {
      const user = userEvent.setup()

      render(
        <TabOrderEditor
          items={mockItems}
          isLoading={false}
          onSave={vi.fn()}
        />
      )

      // Get all items before reorder
      const itemsBefore = screen.getAllByText(/(All Bookmarks|Archived|Trash|Work Resources|Reading List)/)
        .filter(el => el.classList.contains('font-medium'))
      expect(itemsBefore[0]).toHaveTextContent('All Bookmarks')
      expect(itemsBefore[1]).toHaveTextContent('Archived')

      // Find the up button for the second item (Archived)
      const upButtons = screen.getAllByTitle('Move up')
      await user.click(upButtons[1]) // Second item's up button

      // After reorder, Archived should be first
      const itemsAfter = screen.getAllByText(/(All Bookmarks|Archived|Trash|Work Resources|Reading List)/)
        .filter(el => el.classList.contains('font-medium'))
      expect(itemsAfter[0]).toHaveTextContent('Archived')
      expect(itemsAfter[1]).toHaveTextContent('All Bookmarks')
    })

    it('should move item down when clicking down button', async () => {
      const user = userEvent.setup()

      render(
        <TabOrderEditor
          items={mockItems}
          isLoading={false}
          onSave={vi.fn()}
        />
      )

      // Find the down button for the first item (All Bookmarks)
      const downButtons = screen.getAllByTitle('Move down')
      await user.click(downButtons[0]) // First item's down button

      // After reorder, Archived should be first
      const itemsAfter = screen.getAllByText(/(All Bookmarks|Archived|Trash|Work Resources|Reading List)/)
        .filter(el => el.classList.contains('font-medium'))
      expect(itemsAfter[0]).toHaveTextContent('Archived')
      expect(itemsAfter[1]).toHaveTextContent('All Bookmarks')
    })

    it('should disable up button for first item', () => {
      render(
        <TabOrderEditor
          items={mockItems}
          isLoading={false}
          onSave={vi.fn()}
        />
      )

      const upButtons = screen.getAllByTitle('Move up')
      expect(upButtons[0]).toBeDisabled()
    })

    it('should disable down button for last item', () => {
      render(
        <TabOrderEditor
          items={mockItems}
          isLoading={false}
          onSave={vi.fn()}
        />
      )

      const downButtons = screen.getAllByTitle('Move down')
      expect(downButtons[downButtons.length - 1]).toBeDisabled()
    })
  })

  describe('save and reset', () => {
    it('should not show save/reset buttons before any changes', () => {
      render(
        <TabOrderEditor
          items={mockItems}
          isLoading={false}
          onSave={vi.fn()}
        />
      )

      expect(screen.queryByText('Save Order')).not.toBeInTheDocument()
      expect(screen.queryByText('Reset')).not.toBeInTheDocument()
    })

    it('should show save/reset buttons after making changes', async () => {
      const user = userEvent.setup()

      render(
        <TabOrderEditor
          items={mockItems}
          isLoading={false}
          onSave={vi.fn()}
        />
      )

      // Make a change
      const downButtons = screen.getAllByTitle('Move down')
      await user.click(downButtons[0])

      expect(screen.getByText('Save Order')).toBeInTheDocument()
      expect(screen.getByText('Reset')).toBeInTheDocument()
    })

    it('should call onSave with correct order when clicking save', async () => {
      const onSave = vi.fn().mockResolvedValue(undefined)
      const user = userEvent.setup()

      render(
        <TabOrderEditor
          items={mockItems}
          isLoading={false}
          onSave={onSave}
        />
      )

      // Move first item down
      const downButtons = screen.getAllByTitle('Move down')
      await user.click(downButtons[0])

      // Save
      const saveButton = screen.getByText('Save Order')
      await user.click(saveButton)

      await waitFor(() => {
        expect(onSave).toHaveBeenCalledWith([
          'archived', // Was second, now first
          'all',      // Was first, now second
          'trash',
          'list:1',
          'list:2',
        ])
      })
    })

    it('should reset to original order when clicking reset', async () => {
      const user = userEvent.setup()

      render(
        <TabOrderEditor
          items={mockItems}
          isLoading={false}
          onSave={vi.fn()}
        />
      )

      // Make a change
      const downButtons = screen.getAllByTitle('Move down')
      await user.click(downButtons[0])

      // Verify change was made
      let items = screen.getAllByText(/(All Bookmarks|Archived|Trash|Work Resources|Reading List)/)
        .filter(el => el.classList.contains('font-medium'))
      expect(items[0]).toHaveTextContent('Archived')

      // Reset
      const resetButton = screen.getByText('Reset')
      await user.click(resetButton)

      // Verify reset to original order
      items = screen.getAllByText(/(All Bookmarks|Archived|Trash|Work Resources|Reading List)/)
        .filter(el => el.classList.contains('font-medium'))
      expect(items[0]).toHaveTextContent('All Bookmarks')

      // Save/Reset buttons should be hidden after reset
      expect(screen.queryByText('Save Order')).not.toBeInTheDocument()
    })

    it('should hide save/reset buttons after successful save', async () => {
      const onSave = vi.fn().mockResolvedValue(undefined)
      const user = userEvent.setup()

      render(
        <TabOrderEditor
          items={mockItems}
          isLoading={false}
          onSave={onSave}
        />
      )

      // Make a change
      const downButtons = screen.getAllByTitle('Move down')
      await user.click(downButtons[0])

      // Save
      const saveButton = screen.getByText('Save Order')
      await user.click(saveButton)

      await waitFor(() => {
        expect(screen.queryByText('Save Order')).not.toBeInTheDocument()
      })
    })

    it('should show saving state while saving', async () => {
      // Create a promise we can control
      let resolvePromise: () => void
      const savePromise = new Promise<void>((resolve) => {
        resolvePromise = resolve
      })
      const onSave = vi.fn().mockReturnValue(savePromise)
      const user = userEvent.setup()

      render(
        <TabOrderEditor
          items={mockItems}
          isLoading={false}
          onSave={onSave}
        />
      )

      // Make a change
      const downButtons = screen.getAllByTitle('Move down')
      await user.click(downButtons[0])

      // Save
      const saveButton = screen.getByText('Save Order')
      await user.click(saveButton)

      // Should show saving state
      expect(screen.getByText('Saving...')).toBeInTheDocument()

      // Resolve the promise
      resolvePromise!()

      await waitFor(() => {
        expect(screen.queryByText('Saving...')).not.toBeInTheDocument()
      })
    })
  })
})
