/**
 * Tests for SectionTabOrderEditor component.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SectionTabOrderEditor } from './SectionTabOrderEditor'
import type { TabOrderSection, SectionName } from '../types'
import { useSettingsStore } from '../stores/settingsStore'

// Mock the store
vi.mock('../stores/settingsStore', () => ({
  useSettingsStore: vi.fn(),
}))

// Mock react-hot-toast
vi.mock('react-hot-toast', () => ({
  default: {
    error: vi.fn(),
    success: vi.fn(),
  },
}))

const mockSections: TabOrderSection[] = [
  {
    name: 'shared',
    label: 'Shared',
    items: [
      { key: 'all', label: 'All', type: 'builtin' },
      { key: 'archived', label: 'Archived', type: 'builtin' },
      { key: 'trash', label: 'Trash', type: 'builtin' },
    ],
    collapsible: false,
  },
  {
    name: 'bookmarks',
    label: 'Bookmarks',
    items: [
      { key: 'all-bookmarks', label: 'All Bookmarks', type: 'builtin' },
      { key: 'list:1', label: 'Work Links', type: 'list' },
    ],
    collapsible: true,
  },
  {
    name: 'notes',
    label: 'Notes',
    items: [
      { key: 'all-notes', label: 'All Notes', type: 'builtin' },
    ],
    collapsible: true,
  },
]

const mockSectionOrder: SectionName[] = ['shared', 'bookmarks', 'notes']

describe('SectionTabOrderEditor', () => {
  const mockUpdateTabOrder = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    mockUpdateTabOrder.mockResolvedValue(undefined)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    vi.mocked(useSettingsStore).mockImplementation((selector?: any) => {
      const state = { updateTabOrder: mockUpdateTabOrder }
      return selector ? selector(state) : state
    })
  })

  describe('rendering', () => {
    it('should render loading state', () => {
      render(
        <SectionTabOrderEditor
          sections={[]}
          sectionOrder={[]}
          isLoading={true}
        />
      )

      expect(screen.getByText('Loading sidebar order...')).toBeInTheDocument()
    })

    it('should render empty state', () => {
      render(
        <SectionTabOrderEditor
          sections={[]}
          sectionOrder={[]}
          isLoading={false}
        />
      )

      expect(screen.getByText('Using default sidebar order.')).toBeInTheDocument()
    })

    it('should render all sections', () => {
      render(
        <SectionTabOrderEditor
          sections={mockSections}
          sectionOrder={mockSectionOrder}
          isLoading={false}
        />
      )

      expect(screen.getByText('Shared')).toBeInTheDocument()
      expect(screen.getByText('Bookmarks')).toBeInTheDocument()
      expect(screen.getByText('Notes')).toBeInTheDocument()
    })

    it('should render items within sections', () => {
      render(
        <SectionTabOrderEditor
          sections={mockSections}
          sectionOrder={mockSectionOrder}
          isLoading={false}
        />
      )

      expect(screen.getByText('All')).toBeInTheDocument()
      expect(screen.getByText('Archived')).toBeInTheDocument()
      expect(screen.getByText('All Bookmarks')).toBeInTheDocument()
      expect(screen.getByText('Work Links')).toBeInTheDocument()
      expect(screen.getByText('All Notes')).toBeInTheDocument()
    })

    it('should mark builtin items', () => {
      render(
        <SectionTabOrderEditor
          sections={mockSections}
          sectionOrder={mockSectionOrder}
          isLoading={false}
        />
      )

      // Builtin items should have "(built-in)" label
      const builtInLabels = screen.getAllByText('(built-in)')
      expect(builtInLabels.length).toBeGreaterThan(0)
    })
  })

  describe('section reordering', () => {
    it('should disable move up button for first section', () => {
      render(
        <SectionTabOrderEditor
          sections={mockSections}
          sectionOrder={mockSectionOrder}
          isLoading={false}
        />
      )

      // First section's move up button should be disabled
      const moveUpButtons = screen.getAllByTitle('Move section up')
      expect(moveUpButtons[0]).toBeDisabled()
    })

    it('should disable move down button for last section', () => {
      render(
        <SectionTabOrderEditor
          sections={mockSections}
          sectionOrder={mockSectionOrder}
          isLoading={false}
        />
      )

      // Last section's move down button should be disabled
      const moveDownButtons = screen.getAllByTitle('Move section down')
      expect(moveDownButtons[moveDownButtons.length - 1]).toBeDisabled()
    })

    it('should move section down when clicking move down', async () => {
      const user = userEvent.setup()

      render(
        <SectionTabOrderEditor
          sections={mockSections}
          sectionOrder={mockSectionOrder}
          isLoading={false}
        />
      )

      // Click move down on first section (Shared)
      const moveDownButtons = screen.getAllByTitle('Move section down')
      await user.click(moveDownButtons[0])

      // Should show Save/Reset buttons after making changes
      expect(screen.getByRole('button', { name: 'Save Order' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Reset' })).toBeInTheDocument()
    })

    it('should move section up when clicking move up', async () => {
      const user = userEvent.setup()

      render(
        <SectionTabOrderEditor
          sections={mockSections}
          sectionOrder={mockSectionOrder}
          isLoading={false}
        />
      )

      // Click move up on second section (Bookmarks)
      const moveUpButtons = screen.getAllByTitle('Move section up')
      await user.click(moveUpButtons[1])

      // Should show Save/Reset buttons
      expect(screen.getByRole('button', { name: 'Save Order' })).toBeInTheDocument()
    })
  })

  describe('item reordering', () => {
    it('should disable move up button for first item in section', () => {
      render(
        <SectionTabOrderEditor
          sections={mockSections}
          sectionOrder={mockSectionOrder}
          isLoading={false}
        />
      )

      // First item's move up button in each section should be disabled
      const moveUpButtons = screen.getAllByTitle('Move item up')
      expect(moveUpButtons[0]).toBeDisabled() // First item in Shared
    })

    it('should disable move down button for last item in section', () => {
      render(
        <SectionTabOrderEditor
          sections={mockSections}
          sectionOrder={mockSectionOrder}
          isLoading={false}
        />
      )

      // Last item's move down button should be disabled
      // Items: All, Archived, Trash (shared), All Bookmarks, Work Links (bookmarks), All Notes (notes)
      const moveDownButtons = screen.getAllByTitle('Move item down')
      // Trash is the last item in shared section
      expect(moveDownButtons[2]).toBeDisabled()
    })

    it('should move item down when clicking move down', async () => {
      const user = userEvent.setup()

      render(
        <SectionTabOrderEditor
          sections={mockSections}
          sectionOrder={mockSectionOrder}
          isLoading={false}
        />
      )

      // Click move down on first item in Shared section
      const moveDownButtons = screen.getAllByTitle('Move item down')
      await user.click(moveDownButtons[0])

      // Should show Save/Reset buttons
      expect(screen.getByRole('button', { name: 'Save Order' })).toBeInTheDocument()
    })
  })

  describe('save and reset', () => {
    it('should not show save/reset buttons initially', () => {
      render(
        <SectionTabOrderEditor
          sections={mockSections}
          sectionOrder={mockSectionOrder}
          isLoading={false}
        />
      )

      expect(screen.queryByRole('button', { name: 'Save Order' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Reset' })).not.toBeInTheDocument()
    })

    it('should call updateTabOrder when saving', async () => {
      const user = userEvent.setup()

      render(
        <SectionTabOrderEditor
          sections={mockSections}
          sectionOrder={mockSectionOrder}
          isLoading={false}
        />
      )

      // Make a change first
      const moveDownButtons = screen.getAllByTitle('Move section down')
      await user.click(moveDownButtons[0])

      // Click save
      const saveButton = screen.getByRole('button', { name: 'Save Order' })
      await user.click(saveButton)

      await waitFor(() => {
        expect(mockUpdateTabOrder).toHaveBeenCalledWith(expect.objectContaining({
          sections: expect.any(Object),
          section_order: expect.any(Array),
        }))
      })
    })

    it('should reset changes when clicking reset', async () => {
      const user = userEvent.setup()

      render(
        <SectionTabOrderEditor
          sections={mockSections}
          sectionOrder={mockSectionOrder}
          isLoading={false}
        />
      )

      // Make a change
      const moveDownButtons = screen.getAllByTitle('Move section down')
      await user.click(moveDownButtons[0])

      // Should show buttons
      expect(screen.getByRole('button', { name: 'Save Order' })).toBeInTheDocument()

      // Click reset
      const resetButton = screen.getByRole('button', { name: 'Reset' })
      await user.click(resetButton)

      // Buttons should disappear
      expect(screen.queryByRole('button', { name: 'Save Order' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Reset' })).not.toBeInTheDocument()
    })

    it('should hide buttons after successful save', async () => {
      const user = userEvent.setup()

      render(
        <SectionTabOrderEditor
          sections={mockSections}
          sectionOrder={mockSectionOrder}
          isLoading={false}
        />
      )

      // Make a change
      const moveDownButtons = screen.getAllByTitle('Move section down')
      await user.click(moveDownButtons[0])

      // Click save
      const saveButton = screen.getByRole('button', { name: 'Save Order' })
      await user.click(saveButton)

      await waitFor(() => {
        expect(screen.queryByRole('button', { name: 'Save Order' })).not.toBeInTheDocument()
      })
    })

    it('should show error toast on save failure', async () => {
      const toast = await import('react-hot-toast')
      mockUpdateTabOrder.mockRejectedValue(new Error('Network error'))
      const user = userEvent.setup()

      render(
        <SectionTabOrderEditor
          sections={mockSections}
          sectionOrder={mockSectionOrder}
          isLoading={false}
        />
      )

      // Make a change
      const moveDownButtons = screen.getAllByTitle('Move section down')
      await user.click(moveDownButtons[0])

      // Click save
      const saveButton = screen.getByRole('button', { name: 'Save Order' })
      await user.click(saveButton)

      await waitFor(() => {
        expect(toast.default.error).toHaveBeenCalledWith('Failed to save sidebar order')
      })
    })
  })

  describe('empty section', () => {
    it('should show message for empty section', () => {
      const sectionsWithEmpty: TabOrderSection[] = [
        {
          name: 'shared',
          label: 'Shared',
          items: [],
          collapsible: false,
        },
      ]

      render(
        <SectionTabOrderEditor
          sections={sectionsWithEmpty}
          sectionOrder={['shared']}
          isLoading={false}
        />
      )

      expect(screen.getByText('No items in this section')).toBeInTheDocument()
    })
  })
})
